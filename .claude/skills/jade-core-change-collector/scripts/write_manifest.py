#!/usr/bin/env python3
"""write_manifest.py — Schema-validated manifest writer.

Accepts a JSON file of extracted rules. Validates every rule against
the manifest schema. Rejects rules with missing evidence, low confidence,
or duplicate IDs. Writes 01-breaking-changes-manifest.json atomically.

Part of jade-core-change-collector. Never fabricates content.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

TMP_SUFFIX = ".tmp.manifest"

PRECISION_GATE_CONFIG_KEY = "precision_gate"
PRECISION_REPORT_ARTIFACT = "01.5-precision-report.json"
DEFAULT_MANIFEST_EVIDENCE = "digest"
DEFAULT_MIN_PRECISION = 0.7

REQUIRED_RULE_FIELDS = {
    "id": str,
    "name": str,
    "severity": str,
    "patterns": list,
}

VALID_SEVERITIES = {"HIGH", "MEDIUM", "LOW", "INFO", "BLOCKER", "ERROR", "WARNING"}
VALID_CATEGORIES = {
    "API_REMOVAL",
    "DEPRECATION",
    "BEHAVIOR_CHANGE",
    "NAMESPACE",
    "BYTECODE",
    "BUILD",
    "LANGUAGE_CHANGE",
}


def iso_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def read_json(path: pathlib.Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json_atomic(path: pathlib.Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(TMP_SUFFIX)
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def validate_pattern(pattern: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(pattern.get("pattern"), str):
        errors.append("pattern.pattern must be a string")
    elif pattern.get("pattern", "").strip() == "":
        errors.append("pattern.pattern must not be empty (would match every line)")
    if not isinstance(pattern.get("target_extensions"), list):
        errors.append("pattern.target_extensions must be a list")
    if not isinstance(pattern.get("reason"), str):
        errors.append("pattern.reason must be a string")
    if pattern.get("type") not in ("regex", None):
        errors.append(f"pattern.type must be 'regex', got: {pattern.get('type')}")
    if "multiline" in pattern and not isinstance(pattern.get("multiline"), bool):
        errors.append("pattern.multiline must be a boolean when present")
    return errors


def validate_rule(rule: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    rule_id = rule.get("id", "<missing>")

    # Required fields
    for field, expected_type in REQUIRED_RULE_FIELDS.items():
        if field not in rule:
            errors.append(f"Rule {rule_id}: missing required field '{field}'")
        elif not isinstance(rule[field], expected_type):
            errors.append(f"Rule {rule_id}: '{field}' must be {expected_type.__name__}")

    # Severity
    severity = rule.get("severity", "")
    if severity and severity not in VALID_SEVERITIES:
        errors.append(f"Rule {rule_id}: invalid severity '{severity}'")

    # Category
    category = rule.get("category", "")
    if category and category not in VALID_CATEGORIES:
        errors.append(f"Rule {rule_id}: invalid category '{category}'")

    # Evidence
    evidence_ref = rule.get("evidence_ref", "")
    if not evidence_ref:
        errors.append(
            f"Rule {rule_id}: missing evidence_ref (Anti-Hallucination violation)"
        )
    if not rule.get("evidence_hash"):
        errors.append(f"Rule {rule_id}: missing evidence_hash")

    # Confidence
    confidence = rule.get("confidence", 0)
    if confidence < 0.7:
        errors.append(
            f"Rule {rule_id}: confidence {confidence} below minimum 0.7 (Anti-Hallucination gate)"
        )

    # Patterns
    patterns = rule.get("patterns", [])
    if not isinstance(patterns, list):
        errors.append(f"Rule {rule_id}: patterns must be a list")
    elif len(patterns) == 0:
        errors.append(f"Rule {rule_id}: must have at least one pattern")
    else:
        for i, p in enumerate(patterns):
            for e in validate_pattern(p):
                errors.append(f"Rule {rule_id} pattern[{i}]: {e}")

    # fix_strategy
    fix_strategy = rule.get("fix_strategy", "")
    if not fix_strategy:
        errors.append(f"Rule {rule_id}: missing fix_strategy")
    elif not fix_strategy.startswith("recipe:"):
        errors.append(
            f"Rule {rule_id}: fix_strategy must start with 'recipe:', got '{fix_strategy}'"
        )

    # match_pattern
    match_pattern = rule.get("match_pattern", "")
    if match_pattern:
        try:
            re.compile(match_pattern)
        except re.error as exc:
            errors.append(f"Rule {rule_id}: invalid regex in match_pattern: {exc}")

    return errors


def validate_evidence_policy(
    rule: Dict[str, Any],
    source_index: Dict[str, Any],
    mode: str,
) -> List[str]:
    errors: List[str] = []
    rule_id = rule.get("id", "<missing>")
    evidence_ref = rule.get("evidence_ref", "")
    evidence_hash = rule.get("evidence_hash", "")

    if not evidence_ref:
        return errors

    if "::" not in evidence_ref:
        if mode == "production":
            errors.append(
                f"Rule {rule_id}: malformed evidence_ref "
                f"(missing '::' separator), got '{evidence_ref}'"
            )
        else:
            print(
                f"WARNING [LEGACY_REF] Rule {rule_id}: legacy evidence_ref "
                f"format (no '::' separator), allowed in {mode} mode",
                file=sys.stderr,
            )
        return errors

    source_label = evidence_ref.split("::", 1)[0].strip()

    sources = source_index.get("sources", [])
    source_entry: Optional[Dict[str, Any]] = None
    for s in sources:
        if s.get("source_label") == source_label:
            source_entry = s
            break

    if source_entry is None:
        errors.append(
            f"Rule {rule_id}: evidence_ref source_label '{source_label}' "
            f"not found in source index"
        )
        return errors

    if evidence_hash and source_entry.get("content_hash"):
        if evidence_hash != source_entry["content_hash"]:
            errors.append(
                f"Rule {rule_id}: evidence_hash does not match source "
                f"'{source_label}' content_hash"
            )

    if not source_entry.get("is_official", False):
        errors.append(
            f"Rule {rule_id}: evidence source '{source_label}' "
            f"is not official (non-official evidence rejected in all modes)"
        )

    return errors


def validate_manifest(rules: List[Dict], source_labels: List[str]) -> List[str]:
    errors: List[str] = []
    seen_ids: set = set()
    if not isinstance(rules, list):
        return ["Rules must be a list"]

    for rule in rules:
        if not isinstance(rule, dict):
            errors.append("Rule entry is not a dict")
            continue
        rid = rule.get("id", "")
        if rid in seen_ids:
            errors.append(f"Duplicate rule_id: {rid}")
        seen_ids.add(rid)
        errors.extend(validate_rule(rule))

    return errors


def _read_json_safe(path: pathlib.Path) -> Optional[Any]:
    try:
        return read_json(path)
    except (json.JSONDecodeError, OSError):
        return None


def load_run_config_precision(artifacts_dir: pathlib.Path) -> Tuple[Optional[Dict[str, Any]], float, str]:
    """Read ``00-run-config.json#precision_gate`` if present.

    Returns (block_or_None, min_precision_threshold, manifest_evidence_mode).
    Absent block yields the same defaults the orchestrator/scorer use, so a
    rule's ``min_pattern_precision`` can still be sanity-checked even before
    any precision report exists.
    """
    cfg = _read_json_safe(artifacts_dir / "00-run-config.json")
    block = cfg.get(PRECISION_GATE_CONFIG_KEY) if isinstance(cfg, dict) else None
    if not isinstance(block, dict):
        return None, DEFAULT_MIN_PRECISION, DEFAULT_MANIFEST_EVIDENCE
    threshold = block.get("min_precision", DEFAULT_MIN_PRECISION)
    evidence_mode = block.get("manifest_evidence", DEFAULT_MANIFEST_EVIDENCE)
    return block, threshold, evidence_mode


def _rule_pattern_texts(rule: Dict[str, Any]) -> List[Any]:
    return [p.get("pattern") for p in rule.get("patterns", []) if isinstance(p, dict)]


def _load_sample_seed_and_size(
    artifacts_dir: pathlib.Path, rule_id: str
) -> Tuple[Optional[str], Optional[int]]:
    sample = _read_json_safe(artifacts_dir / f"01.5-precision-sample-{rule_id}.json")
    if isinstance(sample, dict):
        sampling = sample.get("sampling", {})
        seed = sampling.get("seed") if isinstance(sampling, dict) else None
        return seed, sample.get("sample_size")
    return None, None


def _build_full_counterexamples(
    artifacts_dir: pathlib.Path, report_entry: Dict[str, Any]
) -> Optional[List[Dict[str, Any]]]:
    """``manifest_evidence: "full"`` -- every judged hit, with full context.

    Unlike the digest form (the report's own already-capped-at-5
    counterexamples), this reads the referenced sample + verdicts artifacts
    to paste the complete judged set, context arrays included.
    """
    sample_name = report_entry.get("sample_artifact")
    verdicts_name = report_entry.get("verdicts_artifact")
    if not sample_name or not verdicts_name:
        return None
    sample = _read_json_safe(artifacts_dir / sample_name)
    verdicts = _read_json_safe(artifacts_dir / verdicts_name)
    if not isinstance(sample, dict) or not isinstance(verdicts, dict):
        return None
    hits_by_id = {h.get("hit_id"): h for h in sample.get("hits", [])}
    full: List[Dict[str, Any]] = []
    for vd in verdicts.get("verdicts", []):
        hit = hits_by_id.get(vd.get("hit_id"), {})
        full.append(
            {
                "hit_id": vd.get("hit_id"),
                "file": hit.get("file"),
                "line": hit.get("line"),
                "line_text": hit.get("line_text"),
                "context_before": hit.get("context_before", []),
                "context_after": hit.get("context_after", []),
                "verdict": vd.get("verdict"),
                "false_positive_class": vd.get("false_positive_class"),
                "reason": vd.get("reason"),
            }
        )
    full.sort(key=lambda c: (c.get("file") or "", c.get("line") or 0, c.get("hit_id") or ""))
    return full


def build_pattern_precision_block(
    artifacts_dir: pathlib.Path,
    rule_id: str,
    report_entry: Dict[str, Any],
    evidence_mode: str,
) -> Dict[str, Any]:
    seed, sample_size = _load_sample_seed_and_size(artifacts_dir, rule_id)
    population = report_entry.get("population", {}) if isinstance(report_entry.get("population"), dict) else {}
    block = {
        "value": report_entry.get("pattern_precision"),
        "status": report_entry.get("status"),
        "judged": report_entry.get("judged"),
        "true_positive": report_entry.get("true_positive"),
        "false_positive": report_entry.get("false_positive"),
        "undecidable": report_entry.get("undecidable"),
        "sample_size": sample_size if sample_size is not None else report_entry.get("judged"),
        "population_total_hits": population.get("total_hits"),
        "wilson_95": report_entry.get("wilson_95"),
        "effective_min_precision": report_entry.get("effective_min_precision"),
        "pattern_revision": report_entry.get("pattern_revision"),
        "seed": seed,
        "sample_artifact": report_entry.get("sample_artifact"),
        "sample_hash": report_entry.get("sample_hash"),
        "verdicts_artifact": report_entry.get("verdicts_artifact"),
        "verdicts_hash": report_entry.get("verdicts_hash"),
        "report_artifact": PRECISION_REPORT_ARTIFACT,
        "false_positive_classes": report_entry.get("false_positive_classes", {}),
    }
    if evidence_mode == "full":
        full = _build_full_counterexamples(artifacts_dir, report_entry)
        block["counterexamples"] = full if full is not None else (report_entry.get("counterexamples") or [])
    else:
        block["counterexamples"] = (report_entry.get("counterexamples") or [])[:5]
    return block


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Schema-validated manifest writer for jade-core-change-collector"
    )
    parser.add_argument(
        "--input", required=True, help="JSON file with extracted rules array"
    )
    parser.add_argument(
        "--artifacts-dir", required=True, help="Path to artifacts directory"
    )
    parser.add_argument("--run-id", required=True, help="Migration run ID")
    parser.add_argument("--source-version", required=True, help="Source Java version")
    parser.add_argument("--target-version", required=True, help="Target Java version")
    parser.add_argument(
        "--source-policy-mode",
        default="production",
        choices=["production", "development"],
        help="Source policy enforcement mode (default: production)",
    )
    parser.add_argument(
        "--precision-report",
        default=None,
        help=(
            "Path to 01.5-precision-report.json (default: "
            "<artifacts-dir>/01.5-precision-report.json if it exists)"
        ),
    )
    parser.add_argument(
        "--require-precision",
        action="store_true",
        help="Fail if any rule lacks a precision-report entry",
    )
    args = parser.parse_args()

    artifacts_dir = pathlib.Path(args.artifacts_dir)
    input_path = pathlib.Path(args.input)

    if not input_path.exists():
        print(f"ERROR [INPUT_NOT_FOUND] {input_path}", file=sys.stderr)
        return 2

    try:
        data = read_json(input_path)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR [JSON_PARSE] {exc}", file=sys.stderr)
        return 2

    rules = data if isinstance(data, list) else data.get("rules", [])

    # Gather source labels and full index data from source index
    source_labels: List[str] = []
    source_index_data: Optional[Dict[str, Any]] = None
    source_index_path = artifacts_dir / "01-source-index.json"
    if source_index_path.exists():
        try:
            source_index_data = read_json(source_index_path)
            source_labels = [
                s.get("source_label", "") for s in source_index_data.get("sources", [])
            ]
        except (json.JSONDecodeError, OSError):
            source_index_data = None

    # Validate
    validation_errors = validate_manifest(rules, source_labels)

    # Evidence policy validation (only when source index exists)
    if source_index_data:
        for rule in rules:
            validation_errors.extend(
                validate_evidence_policy(
                    rule, source_index_data, args.source_policy_mode
                )
            )

    # --- Precision-gate integration (see 00-run-config.json#precision_gate) --
    # Absent both --precision-report and a precision_gate config block, none
    # of this reads or mutates anything: output stays byte-identical to the
    # pre-precision-gate behavior (golden-compare guarantee).
    precision_gate_block, run_threshold, evidence_mode = load_run_config_precision(artifacts_dir)

    report_path: Optional[pathlib.Path]
    if args.precision_report:
        report_path = pathlib.Path(args.precision_report)
        if not report_path.exists():
            validation_errors.append(
                f"PRECISION_REPORT_NOT_FOUND: --precision-report path does not exist: {report_path}"
            )
            report_path = None
    else:
        default_report = artifacts_dir / PRECISION_REPORT_ARTIFACT
        report_path = default_report if default_report.exists() else None

    report_data: Optional[Dict[str, Any]] = None
    if report_path is not None:
        report_data = _read_json_safe(report_path)
        if report_data is None:
            validation_errors.append(
                f"PRECISION_REPORT_NOT_FOUND: could not parse precision report {report_path}"
            )

    report_rules: Dict[str, Any] = (
        report_data.get("rules", {}) if isinstance(report_data, dict) else {}
    )
    precision_mode = bool(report_data) or args.require_precision or bool(precision_gate_block)

    # FORGED_PRECISION — unconditional: an agent must never hand-write these
    # fields into the extracted-rules input. They are script-computed only,
    # injected below strictly from a validated 01.5-precision-report.json.
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        rid = rule.get("id", "<missing>")
        if "pattern_precision" in rule or "queue_eligible" in rule:
            validation_errors.append(
                f"Rule {rid}: FORGED_PRECISION — pattern_precision/queue_eligible must "
                f"never appear in the extracted-rules input; they are injected only from "
                f"a validated {PRECISION_REPORT_ARTIFACT}"
            )

    if args.require_precision:
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            rid = rule.get("id", "<missing>")
            if rid not in report_rules:
                validation_errors.append(
                    f"Rule {rid}: PRECISION_COVERAGE_MISSING — --require-precision set but "
                    f"no entry for this rule in {PRECISION_REPORT_ARTIFACT}"
                )

    if precision_mode:
        old_manifest_path = artifacts_dir / "01-breaking-changes-manifest.json"
        old_manifest = _read_json_safe(old_manifest_path) if old_manifest_path.exists() else None
        old_rules_by_id: Dict[str, Any] = {}
        if isinstance(old_manifest, dict) and isinstance(old_manifest.get("rules"), list):
            old_rules_by_id = {
                r.get("id"): r for r in old_manifest["rules"] if isinstance(r, dict)
            }

        for rule in rules:
            if not isinstance(rule, dict):
                continue
            rid = rule.get("id", "<missing>")

            rule_min = rule.get("min_pattern_precision")
            if isinstance(rule_min, (int, float)) and rule_min < run_threshold:
                validation_errors.append(
                    f"Rule {rid}: THRESHOLD_WEAKENED — min_pattern_precision {rule_min} is "
                    f"below the run threshold {run_threshold}; a rule may only raise its "
                    f"own threshold, never lower it"
                )

            old_rule = old_rules_by_id.get(rid)
            if old_rule is not None:
                old_patterns = _rule_pattern_texts(old_rule)
                new_patterns = _rule_pattern_texts(rule)
                if old_patterns != new_patterns:
                    old_revision = old_rule.get("pattern_revision", 1)
                    new_revision = rule.get("pattern_revision", 1)
                    if not isinstance(old_revision, int):
                        old_revision = 1
                    if not isinstance(new_revision, int) or new_revision <= old_revision:
                        validation_errors.append(
                            f"Rule {rid}: STALE_PATTERN_REVISION — pattern text changed but "
                            f"pattern_revision was not incremented (old={old_revision}, "
                            f"new={new_revision})"
                        )

    if validation_errors:
        print("=== VALIDATION FAILED ===")
        for e in validation_errors:
            print(f"  • {e}")
        print(f"\n{len(validation_errors)} error(s) — manifest NOT written.")
        return 2

    # Inject script-computed precision fields (never present on legacy paths)
    if report_data is not None:
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            rid = rule.get("id")
            entry = report_rules.get(rid)
            if entry is not None:
                rule["pattern_precision"] = build_pattern_precision_block(
                    artifacts_dir, rid, entry, evidence_mode
                )
                rule["queue_eligible"] = entry.get("queue_eligible")

    # Build manifest
    manifest = {
        "run_id": args.run_id,
        "generated_at": iso_now(),
        "source_version": args.source_version,
        "target_version": args.target_version,
        "citation": f"Extracted from {len(source_labels)} source(s): {', '.join(source_labels)}",
        "rules": rules,
    }

    manifest_path = artifacts_dir / "01-breaking-changes-manifest.json"
    write_json_atomic(manifest_path, manifest)
    print(f"Manifest written to {manifest_path}")
    print(f"  Rules: {len(rules)}")
    for r in rules:
        print(
            f"    {r['id']}: {r.get('confidence', 'N/A')} — {r.get('fix_strategy', 'N/A')}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
