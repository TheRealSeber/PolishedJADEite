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
from typing import Any, Dict, List, Optional

TMP_SUFFIX = ".tmp.manifest"

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
    if not isinstance(pattern.get("target_extensions"), list):
        errors.append("pattern.target_extensions must be a list")
    if not isinstance(pattern.get("reason"), str):
        errors.append("pattern.reason must be a string")
    if pattern.get("type") not in ("regex", None):
        errors.append(f"pattern.type must be 'regex', got: {pattern.get('type')}")
    return errors


def validate_rule(rule: Dict[str, Any], source_labels: List[str]) -> List[str]:
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
        errors.extend(validate_rule(rule, source_labels))

    return errors


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

    # Gather source labels from source index
    source_labels: List[str] = []
    source_index = artifacts_dir / "01-source-index.json"
    if source_index.exists():
        try:
            idx = read_json(source_index)
            source_labels = [s.get("source_label", "") for s in idx.get("sources", [])]
        except (json.JSONDecodeError, OSError):
            pass

    # Validate
    validation_errors = validate_manifest(rules, source_labels)
    if validation_errors:
        print("=== VALIDATION FAILED ===")
        for e in validation_errors:
            print(f"  • {e}")
        print(f"\n{len(validation_errors)} error(s) — manifest NOT written.")
        return 2

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
