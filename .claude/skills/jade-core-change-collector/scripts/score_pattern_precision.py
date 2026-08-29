#!/usr/bin/env python3
"""score_pattern_precision.py -- Score agent verdicts into a precision report.

Phase 2 of the precision gate. Reads a sample artifact (written by
sample_pattern_hits.py) and the agent's verdicts artifact, validates the
verdicts against a strict contract, computes ``pattern_precision`` with a
Wilson 95% confidence interval, and writes ``01.5-precision-report.json``.

There is deliberately no ``--min-precision`` or ``--sample-size`` flag: the
threshold and sample floor come exclusively from ``00-run-config.json``.
A CLI flag for the threshold would let an agent bypass the gate by simply
passing ``--min-precision 0.0`` -- see test 21 (anti-bypass).

Exit codes:
  0 = every scored rule is PASS/NO_POPULATION/OVERRIDDEN
  1 = at least one rule is REJECTED/INCONCLUSIVE/ABANDONED (report written)
  2 = verdict/override contract violation (report NOT written)
  3 = missing input file / environment error
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = 1

PRECISION_GATE_CONFIG_KEY = "precision_gate"

VALID_VERDICTS = {"TRUE_POSITIVE", "FALSE_POSITIVE", "UNDECIDABLE"}
VALID_FP_CLASSES = {
    "NOT_THE_CONSTRUCT",
    "RIGHT_CONSTRUCT_WRONG_CONTEXT",
    "ALREADY_COMPLIANT",
    "COMMENT_OR_STRING",
    "TEST_ONLY",
    "GENERATED_CODE",
    "OTHER",
}
MIN_REASON_LEN = 20

STATUS_PASS = "PASS"
STATUS_REJECTED = "REJECTED"
STATUS_INCONCLUSIVE = "INCONCLUSIVE"
STATUS_NO_POPULATION = "NO_POPULATION"
STATUS_ABANDONED = "ABANDONED"
STATUS_OVERRIDDEN = "OVERRIDDEN"

FP_CLASS_ADVICE = {
    "NOT_THE_CONSTRUCT": (
        "The pattern describes a different syntactic construct than the rule; "
        "add left-hand-side context to the regex so it anchors on the real one."
    ),
    "COMMENT_OR_STRING": (
        "Hits land inside string/comment literals; the pattern needs an anchor "
        "that excludes non-code text."
    ),
    "RIGHT_CONSTRUCT_WRONG_CONTEXT": (
        "The pattern itself is fine, but target_extensions or the directory scope "
        "is too broad; narrow it."
    ),
    "ALREADY_COMPLIANT": (
        "Hits are already in the target form; tighten the pattern to exclude "
        "already-migrated code."
    ),
    "TEST_ONLY": "Hits are confined to test code; consider excluding test paths.",
    "GENERATED_CODE": "Hits are in generated code; exclude generated paths.",
    "OTHER": "See the reason text on each counterexample for specifics.",
}


# ---------------------------------------------------------------------------
# Small IO helpers
# ---------------------------------------------------------------------------


def read_json(path: pathlib.Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json_atomic(path: pathlib.Path, payload: Dict[str, Any]) -> None:
    abs_path = os.path.abspath(str(path))
    directory = os.path.dirname(abs_path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".score-pattern-precision-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, abs_path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rule_content_hash(rule: Dict[str, Any]) -> str:
    """Same algorithm as sample_pattern_hits.rule_content_hash / orchestrator.

    Re-implemented (not imported) intentionally -- these are independent
    scripts communicating only through artifact files on disk.
    """
    return hashlib.sha256(
        json.dumps(rule, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def precision_defaults() -> Dict[str, Any]:
    return {
        "min_precision": 0.7,
        "sample_size": 30,
        "undecidable_max_ratio": 0.2,
        "max_revisions": 3,
        "on_reject": "halt",
        "overrides": {},
    }


def load_policy(run_config: Dict[str, Any]) -> Dict[str, Any]:
    policy = precision_defaults()
    block = run_config.get(PRECISION_GATE_CONFIG_KEY)
    if isinstance(block, dict):
        for key in ("min_precision", "sample_size", "undecidable_max_ratio", "max_revisions", "on_reject", "overrides"):
            if key in block:
                policy[key] = block[key]
    return policy


def wilson_interval(k: int, n: int, z: float = 1.959963984540054) -> Tuple[float, float]:
    """Wilson score 95% confidence interval for a binomial proportion."""
    if n <= 0:
        return (0.0, 1.0)
    phat = k / n
    denom = 1.0 + z * z / n
    center = phat + z * z / (2 * n)
    margin = z * math.sqrt((phat * (1 - phat) + z * z / (4 * n)) / n)
    low = (center - margin) / denom
    high = (center + margin) / denom
    return (max(0.0, low), min(1.0, high))


# ---------------------------------------------------------------------------
# Verdict-carry-forward (nested-sample enlargement helper; see spec section 8)
# ---------------------------------------------------------------------------


def carry_forward_verdicts(
    old_sample: Dict[str, Any], old_verdicts: Dict[str, Any], new_sample: Dict[str, Any]
) -> Dict[str, Any]:
    """Carry forward verdicts whose hit_id AND line_hash are unchanged between
    an old (smaller) sample and a newly enlarged one.

    Because sampling is nested (a larger sample is a superset ordered the
    same way, see sample_pattern_hits.compute_seed/rank_key), a previously
    judged hit_id reappears verbatim in the enlarged sample unless the
    underlying source line changed -- in which case its line_hash differs
    and the old verdict must NOT be reused. Hit ids new to the larger
    sample are simply absent from the result; the agent judges only those.
    """
    old_hits_by_id = {h["hit_id"]: h for h in old_sample.get("hits", [])}
    old_verdicts_by_id = {v["hit_id"]: v for v in old_verdicts.get("verdicts", [])}
    new_hits_by_id = {h["hit_id"]: h for h in new_sample.get("hits", [])}

    carried: List[Dict[str, Any]] = []
    for hit_id, new_hit in new_hits_by_id.items():
        old_hit = old_hits_by_id.get(hit_id)
        verdict = old_verdicts_by_id.get(hit_id)
        if old_hit is None or verdict is None:
            continue
        if old_hit.get("line_hash") != new_hit.get("line_hash"):
            continue
        carried.append(verdict)

    return {
        "schema_version": SCHEMA_VERSION,
        "rule_id": new_sample.get("rule_id"),
        "sample_artifact": old_verdicts.get("sample_artifact"),
        "carried_from_verdicts": True,
        "verdicts": carried,
    }


# ---------------------------------------------------------------------------
# Verdict contract validation
# ---------------------------------------------------------------------------


def validate_verdicts_contract(
    sample: Dict[str, Any], verdicts: Dict[str, Any], sample_path: pathlib.Path
) -> List[str]:
    errors: List[str] = []
    rule_id = sample.get("rule_id", "<unknown>")

    actual_hash = sha256_file(sample_path)
    if verdicts.get("sample_hash") != actual_hash:
        errors.append(
            f"Rule {rule_id}: verdicts.sample_hash does not match the current "
            f"sample file (sample was edited after judging, or verdicts are stale)"
        )
        return errors  # further checks are meaningless against a mismatched sample

    hit_ids = [h.get("hit_id") for h in sample.get("hits", [])]
    hit_id_set = set(hit_ids)
    raw_verdicts = verdicts.get("verdicts", [])
    if not isinstance(raw_verdicts, list):
        errors.append(f"Rule {rule_id}: verdicts.verdicts must be a list")
        return errors

    seen: Dict[str, int] = {}
    for v in raw_verdicts:
        if not isinstance(v, dict):
            errors.append(f"Rule {rule_id}: verdict entry is not an object")
            continue
        hid = v.get("hit_id")
        seen[hid] = seen.get(hid, 0) + 1

    for hid, count in seen.items():
        if hid not in hit_id_set:
            errors.append(f"Rule {rule_id}: verdict references unknown hit_id {hid!r}")
        elif count > 1:
            errors.append(f"Rule {rule_id}: duplicate verdict for hit_id {hid!r}")

    missing = hit_id_set - set(seen.keys())
    for hid in sorted(missing):
        errors.append(f"Rule {rule_id}: missing verdict for hit_id {hid!r}")

    for v in raw_verdicts:
        if not isinstance(v, dict):
            continue
        hid = v.get("hit_id")
        verdict = v.get("verdict")
        if verdict not in VALID_VERDICTS:
            errors.append(f"Rule {rule_id}: hit {hid!r} has invalid verdict {verdict!r}")
        reason = v.get("reason", "")
        if not isinstance(reason, str) or len(reason.strip()) < MIN_REASON_LEN:
            errors.append(
                f"Rule {rule_id}: hit {hid!r} reason must be at least {MIN_REASON_LEN} chars"
            )
        if verdict == "FALSE_POSITIVE":
            fp_class = v.get("false_positive_class")
            if fp_class not in VALID_FP_CLASSES:
                errors.append(
                    f"Rule {rule_id}: hit {hid!r} is FALSE_POSITIVE but false_positive_class "
                    f"is missing/invalid ({fp_class!r})"
                )

    return errors


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _effective_min_precision(policy: Dict[str, Any], manifest_rule: Optional[Dict[str, Any]]) -> Tuple[float, str]:
    base = float(policy["min_precision"])
    if manifest_rule is not None:
        rule_min = manifest_rule.get("min_pattern_precision")
        if isinstance(rule_min, (int, float)) and rule_min > base:
            return float(rule_min), "rule"
    return base, "run-config"


def score_rule(
    rule_id: str,
    sample: Dict[str, Any],
    verdicts: Optional[Dict[str, Any]],
    policy: Dict[str, Any],
    manifest_rule: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    population = sample.get("population", {})
    pattern_revision = sample.get("pattern_revision", 1)

    if sample.get("status") == "NO_POPULATION":
        entry = {
            "status": STATUS_NO_POPULATION,
            "queue_eligible": True,
            "pattern_precision": None,
            "judged": 0,
            "true_positive": 0,
            "false_positive": 0,
            "undecidable": 0,
            "wilson_95": None,
            "effective_min_precision": float(policy["min_precision"]),
            "min_precision_source": "run-config",
            "pattern_revision": pattern_revision,
            "manifest_rule_hash": sample.get("manifest_rule_hash"),
            "sample_artifact": f"01.5-precision-sample-{rule_id}.json",
            "sample_hash": None,
            "verdicts_artifact": None,
            "verdicts_hash": None,
            "per_pattern": {},
            "false_positive_classes": {},
            "counterexamples": [],
            "population": {
                "total_hits": population.get("total_hits", 0),
                "files_with_hits": population.get("files_with_hits", 0),
            },
            "next_action": "NONE",
        }
        return entry

    hits_by_id = {h["hit_id"]: h for h in sample.get("hits", [])}
    raw_verdicts = (verdicts or {}).get("verdicts", [])
    verdicts_by_id = {v["hit_id"]: v for v in raw_verdicts}

    judged = len(raw_verdicts)
    true_positive = sum(1 for v in raw_verdicts if v.get("verdict") == "TRUE_POSITIVE")
    false_positive = sum(1 for v in raw_verdicts if v.get("verdict") == "FALSE_POSITIVE")
    undecidable = sum(1 for v in raw_verdicts if v.get("verdict") == "UNDECIDABLE")

    undecidable_ratio = (undecidable / judged) if judged else 0.0
    denom = judged - undecidable

    effective_min, min_source = _effective_min_precision(policy, manifest_rule)

    precision: Optional[float] = round(true_positive / denom, 4) if denom > 0 else None
    wilson_low, wilson_high = wilson_interval(true_positive, denom) if denom > 0 else (0.0, 1.0)

    next_action = "NONE"
    if undecidable_ratio > policy["undecidable_max_ratio"]:
        status = STATUS_INCONCLUSIVE
        next_action = "REJUDGE_WITH_MORE_CONTEXT"
    elif sample.get("status") == "CENSUS":
        status = STATUS_PASS if precision is not None and precision >= effective_min else STATUS_REJECTED
        next_action = "NONE" if status == STATUS_PASS else "REWRITE_PATTERN"
    else:
        if wilson_low <= effective_min <= wilson_high:
            status = STATUS_INCONCLUSIVE
            next_action = "ENLARGE_SAMPLE"
        else:
            status = STATUS_PASS if precision is not None and precision >= effective_min else STATUS_REJECTED
            next_action = "NONE" if status == STATUS_PASS else "REWRITE_PATTERN"

    if status == STATUS_REJECTED and pattern_revision > policy["max_revisions"]:
        status = STATUS_ABANDONED
        next_action = "HUMAN_DECISION"

    # Per-pattern breakdown
    per_pattern: Dict[str, Dict[str, Any]] = {}
    pattern_hit_ids: Dict[int, List[str]] = {}
    for h in sample.get("hits", []):
        pattern_hit_ids.setdefault(h["pattern_index"], []).append(h["hit_id"])
    for pidx, hids in pattern_hit_ids.items():
        pj = sum(1 for hid in hids if hid in verdicts_by_id)
        ptp = sum(1 for hid in hids if verdicts_by_id.get(hid, {}).get("verdict") == "TRUE_POSITIVE")
        pundec = sum(1 for hid in hids if verdicts_by_id.get(hid, {}).get("verdict") == "UNDECIDABLE")
        pdenom = pj - pundec
        per_pattern[str(pidx)] = {
            "judged": pj,
            "true_positive": ptp,
            "precision": round(ptp / pdenom, 4) if pdenom > 0 else None,
        }

    # False-positive classes and counterexamples
    fp_classes: Dict[str, int] = {}
    counterexamples: List[Dict[str, Any]] = []
    for v in raw_verdicts:
        if v.get("verdict") != "FALSE_POSITIVE":
            continue
        cls = v.get("false_positive_class", "OTHER")
        fp_classes[cls] = fp_classes.get(cls, 0) + 1
        hit = hits_by_id.get(v.get("hit_id"), {})
        counterexamples.append(
            {
                "hit_id": v.get("hit_id"),
                "file": hit.get("file"),
                "line": hit.get("line"),
                "line_text": hit.get("line_text"),
                "false_positive_class": cls,
                "reason": v.get("reason"),
            }
        )
    counterexamples.sort(key=lambda c: (c.get("file") or "", c.get("line") or 0, c.get("hit_id") or ""))
    counterexamples = counterexamples[:5]

    entry = {
        "status": status,
        "queue_eligible": status in (STATUS_PASS,),
        "pattern_precision": precision,
        "judged": judged,
        "true_positive": true_positive,
        "false_positive": false_positive,
        "undecidable": undecidable,
        "wilson_95": [round(wilson_low, 4), round(wilson_high, 4)],
        "effective_min_precision": effective_min,
        "min_precision_source": min_source,
        "pattern_revision": pattern_revision,
        "manifest_rule_hash": sample.get("manifest_rule_hash"),
        "sample_artifact": f"01.5-precision-sample-{rule_id}.json",
        "sample_hash": (verdicts or {}).get("sample_hash"),
        "verdicts_artifact": f"01.5-precision-verdicts-{rule_id}.json",
        "verdicts_hash": None,  # filled in by caller (needs the verdicts file path)
        "per_pattern": per_pattern,
        "false_positive_classes": fp_classes,
        "counterexamples": counterexamples,
        "population": {
            "total_hits": population.get("total_hits", 0),
            "files_with_hits": population.get("files_with_hits", 0),
        },
        "next_action": next_action,
    }
    if next_action == "ENLARGE_SAMPLE":
        requested = sample.get("sampling", {}).get("requested_sample_size", policy["sample_size"])
        entry["suggested_command"] = (
            f"python .claude/skills/jade-core-change-collector/scripts/sample_pattern_hits.py "
            f"--run-config <artifacts>/00-run-config.json --rule-id {rule_id} "
            f"--sample-size {requested * 2}"
        )
    return entry


def _discover_rule_ids(artifacts_dir: pathlib.Path) -> List[str]:
    prefix = "01.5-precision-sample-"
    suffix = ".json"
    ids = []
    for p in sorted(artifacts_dir.glob(f"{prefix}*{suffix}")):
        name = p.name
        rule_id = name[len(prefix): -len(suffix)]
        ids.append(rule_id)
    return ids


def _write_action_required(path: pathlib.Path, rules: Dict[str, Dict[str, Any]]) -> None:
    lines = ["# PRECISION ACTION REQUIRED", ""]
    for rule_id, entry in sorted(rules.items()):
        if entry["status"] not in (STATUS_REJECTED, STATUS_INCONCLUSIVE, STATUS_ABANDONED):
            continue
        lines.append(f"## {rule_id} -- {entry['status']}")
        lines.append("")
        if entry["status"] == STATUS_REJECTED:
            precision = entry.get("pattern_precision")
            lines.append(
                f"Measured precision {precision} is below the effective threshold "
                f"{entry['effective_min_precision']} ({entry['min_precision_source']})."
            )
            for cls, count in sorted(entry.get("false_positive_classes", {}).items()):
                advice = FP_CLASS_ADVICE.get(cls, "")
                lines.append(f"- {cls} ({count}): {advice}")
            lines.append("")
            lines.append("Counterexamples:")
            for ce in entry.get("counterexamples", []):
                lines.append(f"- {ce.get('file')}:{ce.get('line')} -- {ce.get('reason')}")
        elif entry["status"] == STATUS_INCONCLUSIVE:
            lines.append(f"next_action: {entry['next_action']}")
            if entry.get("suggested_command"):
                lines.append("")
                lines.append("```")
                lines.append(entry["suggested_command"])
                lines.append("```")
        elif entry["status"] == STATUS_ABANDONED:
            lines.append(
                f"pattern_revision {entry['pattern_revision']} exceeds max_revisions; "
                f"a human must either drop this rule from the manifest or add an "
                f"explicit override with 'reason' and 'approved_by'."
            )
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Score sampled pattern hits into a precision report (precision gate, phase 2)"
    )
    parser.add_argument("--run-config", required=True, help="Path to 00-run-config.json")
    parser.add_argument(
        "--rule-id",
        action="append",
        default=None,
        help="Rule id to score (repeatable); default: every rule with a sample artifact",
    )
    parser.add_argument("--output", default=None, help="Override output report path")
    parser.add_argument("--dry-run", action="store_true", help="Compute and print without writing")
    args = parser.parse_args(argv)

    run_config_path = pathlib.Path(args.run_config)
    if not run_config_path.is_file():
        print(f"ERROR [INPUT_NOT_FOUND] run-config: {run_config_path}", file=sys.stderr)
        return 3
    try:
        run_config = read_json(run_config_path)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR [INPUT_MALFORMED] run-config: {exc}", file=sys.stderr)
        return 2

    run_id = run_config.get("run_id", "unknown")
    artifacts_dir = pathlib.Path(run_config.get("artifacts_path", run_config_path.parent))
    policy = load_policy(run_config)

    rule_ids = args.rule_id if args.rule_id else _discover_rule_ids(artifacts_dir)
    if not rule_ids:
        print("ERROR [NO_SAMPLE_ARTIFACTS] no 01.5-precision-sample-*.json found", file=sys.stderr)
        return 3

    manifest_path = artifacts_dir / "01-breaking-changes-manifest.json"
    manifest_rules: Dict[str, Dict[str, Any]] = {}
    if manifest_path.is_file():
        try:
            manifest = read_json(manifest_path)
            for r in manifest.get("rules", []):
                if isinstance(r, dict) and r.get("id"):
                    manifest_rules[r["id"]] = r
        except (json.JSONDecodeError, OSError):
            manifest_rules = {}

    contract_errors: List[str] = []
    samples: Dict[str, Dict[str, Any]] = {}
    verdicts_map: Dict[str, Optional[Dict[str, Any]]] = {}
    verdicts_hash_map: Dict[str, Optional[str]] = {}

    for rule_id in rule_ids:
        sample_path = artifacts_dir / f"01.5-precision-sample-{rule_id}.json"
        if not sample_path.is_file():
            print(f"ERROR [SAMPLE_ARTIFACT_MISSING] {sample_path}", file=sys.stderr)
            return 3
        try:
            sample = read_json(sample_path)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"ERROR [INPUT_MALFORMED] sample {rule_id}: {exc}", file=sys.stderr)
            return 2
        samples[rule_id] = sample

        if sample.get("status") == "NO_POPULATION":
            verdicts_map[rule_id] = None
            verdicts_hash_map[rule_id] = None
            continue

        verdicts_path = artifacts_dir / f"01.5-precision-verdicts-{rule_id}.json"
        if not verdicts_path.is_file():
            contract_errors.append(f"Rule {rule_id}: missing verdicts artifact {verdicts_path.name}")
            continue
        try:
            verdicts = read_json(verdicts_path)
        except (json.JSONDecodeError, OSError) as exc:
            contract_errors.append(f"Rule {rule_id}: verdicts artifact is not valid JSON: {exc}")
            continue
        contract_errors.extend(validate_verdicts_contract(sample, verdicts, sample_path))
        verdicts_map[rule_id] = verdicts
        verdicts_hash_map[rule_id] = sha256_file(verdicts_path)

    overrides = policy.get("overrides", {})
    if not isinstance(overrides, dict):
        overrides = {}
    for rule_id in rule_ids:
        if rule_id in overrides:
            entry = overrides[rule_id]
            if not isinstance(entry, dict) or not entry.get("reason") or not entry.get("approved_by"):
                contract_errors.append(
                    f"Rule {rule_id}: override requires non-empty 'reason' and 'approved_by'"
                )

    if contract_errors:
        print("=== VERDICT CONTRACT VIOLATION ===")
        for e in contract_errors:
            print(f"  * {e}")
        print(f"\n{len(contract_errors)} error(s) -- report NOT written.")
        return 2

    rules_report: Dict[str, Dict[str, Any]] = {}
    warnings: List[Dict[str, Any]] = []
    for rule_id in rule_ids:
        sample = samples[rule_id]
        verdicts = verdicts_map[rule_id]
        manifest_rule = manifest_rules.get(rule_id)
        entry = score_rule(rule_id, sample, verdicts, policy, manifest_rule)
        if verdicts_hash_map.get(rule_id):
            entry["verdicts_hash"] = verdicts_hash_map[rule_id]

        if rule_id in overrides:
            override_entry = overrides[rule_id]
            entry["status"] = STATUS_OVERRIDDEN
            entry["queue_eligible"] = True
            entry["next_action"] = "NONE"
            warnings.append(
                {
                    "kind": "precision_override",
                    "rule_id": rule_id,
                    "reason": override_entry.get("reason"),
                    "approved_by": override_entry.get("approved_by"),
                }
            )
        rules_report[rule_id] = entry

    summary = {
        "rules_total": len(rules_report),
        "passed": sum(1 for e in rules_report.values() if e["status"] == STATUS_PASS),
        "rejected": sum(1 for e in rules_report.values() if e["status"] == STATUS_REJECTED),
        "inconclusive": sum(1 for e in rules_report.values() if e["status"] == STATUS_INCONCLUSIVE),
        "no_population": sum(1 for e in rules_report.values() if e["status"] == STATUS_NO_POPULATION),
        "abandoned": sum(1 for e in rules_report.values() if e["status"] == STATUS_ABANDONED),
        "overridden": sum(1 for e in rules_report.values() if e["status"] == STATUS_OVERRIDDEN),
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "policy": {
            "min_precision": policy["min_precision"],
            "sample_size": policy["sample_size"],
            "undecidable_max_ratio": policy["undecidable_max_ratio"],
            "max_revisions": policy["max_revisions"],
            "on_reject": policy["on_reject"],
            "source": "00-run-config.json#precision_gate",
        },
        "rules": rules_report,
        "summary": summary,
        "warnings": warnings,
    }

    output_path = pathlib.Path(args.output) if args.output else artifacts_dir / "01.5-precision-report.json"
    action_path = artifacts_dir / "PRECISION_ACTION_REQUIRED.md"
    needs_action = any(
        e["status"] in (STATUS_REJECTED, STATUS_INCONCLUSIVE, STATUS_ABANDONED) for e in rules_report.values()
    )

    if args.dry_run:
        print(f"DRY-RUN rules={len(rules_report)} summary={json.dumps(summary, sort_keys=True)}")
    else:
        try:
            _write_json_atomic(output_path, report)
            if needs_action:
                _write_action_required(action_path, rules_report)
        except OSError as exc:
            print(f"ERROR [WRITE_FAILED] {exc}", file=sys.stderr)
            return 3
        print(f"Report written: {output_path}")

    for rule_id, entry in sorted(rules_report.items()):
        print(f"  {rule_id}: {entry['status']} precision={entry['pattern_precision']}")

    return 1 if needs_action else 0


if __name__ == "__main__":
    raise SystemExit(main())
