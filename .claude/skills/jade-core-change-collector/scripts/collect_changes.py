#!/usr/bin/env python3
"""collect_changes.py — Parse fetched sources and produce the breaking-changes manifest.

Part of jade-change-collector-strict.  Reads 01-source-index.json, processes every
successfully-fetched source, extracts version-change rules with evidence backing,
and writes 01-breaking-changes-manifest.json + 01-evidence-map.json.

If zero sources succeeded, writes 01-source-fetch-errors.json and sets run state to
AWAITING_SOURCE_INPUT.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Category taxonomy — Java version breaking change categories
# ---------------------------------------------------------------------------
CATEGORIES = {
    "API_REMOVAL",
    "DEPRECATION",
    "BEHAVIOR_CHANGE",
    "NAMESPACE",
    "BYTECODE",
    "BUILD",
}

SEVERITIES = {"BLOCKER", "ERROR", "WARNING", "INFO"}

RULE_ID_PATTERN = re.compile(r"^BC-\d+\.\d+-\d{4}$")


def iso_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def read_json(path: pathlib.Path) -> Dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: pathlib.Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    tmp.replace(path)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


# ---------------------------------------------------------------------------
# Rule extraction — extend these for each source type
# ---------------------------------------------------------------------------


def extract_from_text(
    text: str,
    source_label: str,
    version_from: str,
    version_to: str,
    confidence_cap: float,
) -> List[Dict]:
    """Parse raw text for breaking-change descriptions.

    This is a template parser.  In production the skill operator (or the agent)
    supplies a custom extraction function tailored to the source's structure —
    e.g. HTML table parsing for Oracle compat guides, structured text for JEPs.

    The default implementation looks for explicit patterns like:
        "Removed: <class/method>"
        "Deprecated in <version>, removed in <version>"
        "The <API> was removed"

    IMPORTANT: This function MUST NOT fabricate rules.  If the text contains no
    recognisable change descriptions, return an empty list.
    """
    rules: List[Dict] = []
    counter = 0
    norm_to = version_to.replace(".", "")

    # Pattern 1: explicit "Removed: <item>" lines
    removed_pat = re.compile(r"^[Rr]emoved:\s*(?P<item>.+?)$", re.MULTILINE)
    for m in removed_pat.finditer(text):
        item = m.group("item").strip()
        if len(item) < 3:
            continue
        snippet = text[max(0, m.start() - 40) : m.end() + 40]
        counter += 1
        rules.append(
            _make_rule(
                counter,
                norm_to,
                version_from,
                version_to,
                "API_REMOVAL",
                "REMOVED",
                item,
                source_label,
                snippet,
                confidence_cap if confidence_cap > 0 else 0.90,
            )
        )

    # Pattern 2: "deprecated in X, removed in Y"
    depr_pat = re.compile(
        r"[Dd]eprecated\s+in\s+\S+\s*\d+[.,;]\s*removed\s+in\s+\S+\s*\d+[.,;]\s*(?P<item>.+?)(?:\.|$)",
        re.MULTILINE,
    )
    for m in depr_pat.finditer(text):
        item = m.group("item").strip()
        if len(item) < 3:
            continue
        snippet = text[max(0, m.start() - 40) : m.end() + 40]
        counter += 1
        rules.append(
            _make_rule(
                counter,
                norm_to,
                version_from,
                version_to,
                "DEPRECATION",
                "DEPRECATED",
                item,
                source_label,
                snippet,
                confidence_cap if confidence_cap > 0 else 0.85,
            )
        )

    # Pattern 3: "No longer available", "was removed", "has been dropped"
    removed_phrase_pat = re.compile(
        r"(?P<item>[A-Z][\w.]{3,}(?:\(\))?)\s+(?:is\s+)?(?:no\s+longer\s+available|was\s+removed|has\s+been\s+dropped|has\s+been\s+removed)",
        re.IGNORECASE,
    )
    for m in removed_phrase_pat.finditer(text):
        item = m.group("item").strip()
        snippet = text[max(0, m.start() - 40) : m.end() + 40]
        counter += 1
        rules.append(
            _make_rule(
                counter,
                norm_to,
                version_from,
                version_to,
                "API_REMOVAL",
                "REMOVED",
                item,
                source_label,
                snippet,
                confidence_cap if confidence_cap > 0 else 0.75,
            )
        )

    return rules


def _make_rule(
    counter: int,
    norm_to: str,
    version_from: str,
    version_to: str,
    category: str,
    severity: str,
    item: str,
    source_label: str,
    evidence_snippet: str,
    confidence: float,
) -> Dict:
    evidence_hash = sha256(evidence_snippet)
    rule_id = f"BC-{version_to}-{counter:04d}"
    return {
        "rule_id": rule_id,
        "version_from": version_from,
        "version_to": version_to,
        "severity": severity,
        "category": category,
        "match_pattern": re.escape(item),
        "fix_strategy": f"Replace or remove usage of: {item}",
        "verification_hint": f"grep -rn '{re.escape(item)}' should yield no results in source",
        "evidence_ref": f"{source_label}::auto-extract",
        "evidence_hash": evidence_hash,
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# Evidence map builder
# ---------------------------------------------------------------------------


def build_evidence_map(
    index: Dict,
    rules: List[Dict],
    rejected: List[Dict],
) -> Dict:
    sources = index.get("sources", [])
    evidence: List[Dict] = []
    for src in sources:
        label = src.get("source_label", "unknown")
        url = src.get("source_url", "")
        status = src.get("fetch_status", "unknown")
        linked_rules = [
            r["rule_id"] for r in rules if r["evidence_ref"].startswith(label)
        ]
        linked_rejected = [r for r in rejected if r.get("source_label") == label]
        evidence.append(
            {
                "source_label": label,
                "source_url": url,
                "fetch_status": status,
                "extracted_rules": linked_rules,
                "rejected_candidates": linked_rejected,
            }
        )

    # Also include sources that produced no rules
    for src in sources:
        label = src.get("source_label", "unknown")
        if not any(e["source_label"] == label for e in evidence):
            evidence.append(
                {
                    "source_label": label,
                    "source_url": src.get("source_url", ""),
                    "fetch_status": src.get("fetch_status", "unknown"),
                    "extracted_rules": [],
                    "rejected_candidates": [],
                }
            )

    return {"run_id": index.get("run_id", ""), "entries": evidence}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect breaking changes from fetched sources"
    )
    parser.add_argument(
        "--run-config",
        required=True,
        help="Path to 00-run-config.json",
    )
    parser.add_argument(
        "--confidence-cap",
        type=float,
        default=1.0,
        help="Max confidence for unofficial sources (0.85 recommended for community)",
    )
    args = parser.parse_args()

    config_path = pathlib.Path(args.run_config)
    if not config_path.exists():
        print(f"ERROR [CONFIG_NOT_FOUND] {config_path}", file=sys.stderr)
        return 2

    cfg = read_json(config_path)
    required = {"run_id", "artifacts_path", "source_version", "target_version"}
    missing = sorted(required - set(cfg.keys()))
    if missing:
        print(
            f"ERROR [CONFIG_INVALID] Missing keys: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 2

    run_id = cfg["run_id"]
    artifacts_dir = pathlib.Path(cfg["artifacts_path"])
    version_from = cfg["source_version"]
    version_to = cfg["target_version"]

    index_path = artifacts_dir / "01-source-index.json"
    if not index_path.exists():
        print(
            f"ERROR [INDEX_MISSING] {index_path} — run fetch_source.py first",
            file=sys.stderr,
        )
        return 2

    index = read_json(index_path)
    sources: List[Dict] = index.get("sources", [])

    # Count successes
    successes = [s for s in sources if s.get("fetch_status") == "success"]
    if not successes:
        errors_path = artifacts_dir / "01-source-fetch-errors.json"
        errors_payload: Dict[str, Any] = {
            "run_id": run_id,
            "generated_at": iso_now(),
            "errors": [
                {
                    "source_label": s.get("source_label", "unknown"),
                    "source_url": s.get("source_url", ""),
                    "error_type": s.get("error_type", "UNKNOWN"),
                    "error_message": s.get("error_message", ""),
                }
                for s in sources
            ],
            "message": "All sources failed. Provide local file paths to proceed.",
        }
        write_json(errors_path, errors_payload)

        state_path = artifacts_dir / "00-run-state.json"
        if state_path.exists():
            state = read_json(state_path)
            state["state"] = "AWAITING_SOURCE_INPUT"
            state["updated_at"] = iso_now()
            state["failure_reason"] = "ALL_SOURCES_FAILED"
            write_json(state_path, state)

        print("HALT [ALL_SOURCES_FAILED] → 01-source-fetch-errors.json written")
        print(
            "Provide local file paths (PDF, HTML, plaintext) and re-run fetch_source.py."
        )
        return 3

    # Extract rules from each successful source
    all_rules: List[Dict] = []
    rejected_candidates: List[Dict] = []
    confidence_cap = args.confidence_cap

    for src in successes:
        content = src.get("content")
        if not content:
            # Content may have been trimmed; fetch_source.py with --full-content needed
            content = src.get("content_snippet", "")

        label = src.get("source_label", "unknown")
        url = src.get("source_url", "")

        # Determine confidence cap by source type
        source_cap = confidence_cap
        if any(
            official in url.lower()
            for official in (
                "oracle.com",
                "openjdk.org",
                "bugs.openjdk",
                "jcp.org/en/jsr",
            )
        ):
            source_cap = 1.0
        elif any(
            comm in url.lower()
            for comm in (
                "stackoverflow.com",
                "github.com",
                "medium.com",
                "blog",
                "wiki",
            )
        ):
            source_cap = min(source_cap, 0.85)

        rules = extract_from_text(content, label, version_from, version_to, source_cap)
        for r in rules:
            all_rules.append(r)

    # Filter low-confidence rules into rejected
    final_rules: List[Dict] = []
    for r in all_rules:
        if r["confidence"] < 0.7:
            rejected_candidates.append(
                {
                    "suspected_change": r["match_pattern"],
                    "reason": f"confidence_too_low:{r['confidence']}",
                    "source_label": r["evidence_ref"].split("::")[0],
                    "source_snippet_hash": r["evidence_hash"],
                }
            )
        else:
            final_rules.append(r)

    # Deduplicate by evidence_hash
    seen_hashes: set = set()
    deduped_rules: List[Dict] = []
    for r in final_rules:
        if r["evidence_hash"] not in seen_hashes:
            seen_hashes.add(r["evidence_hash"])
            deduped_rules.append(r)
        else:
            rejected_candidates.append(
                {
                    "suspected_change": r["match_pattern"],
                    "reason": "duplicate_evidence",
                    "source_label": r["evidence_ref"].split("::")[0],
                    "source_snippet_hash": r["evidence_hash"],
                }
            )

    # Build evidence map
    evidence_map = build_evidence_map(index, deduped_rules, rejected_candidates)

    # Write outputs
    manifest_path = artifacts_dir / "01-breaking-changes-manifest.json"
    manifest: Dict[str, Any] = {
        "run_id": run_id,
        "generated_at": iso_now(),
        "source_version": version_from,
        "target_version": version_to,
        "rules": deduped_rules,
    }
    write_json(manifest_path, manifest)

    evidence_path = artifacts_dir / "01-evidence-map.json"
    write_json(evidence_path, evidence_map)

    print(f"DONE — {len(deduped_rules)} rules, {len(rejected_candidates)} rejected")
    print(f"  Manifest: {manifest_path}")
    print(f"  Evidence:  {evidence_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
