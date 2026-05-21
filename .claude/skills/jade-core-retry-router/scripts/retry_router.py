#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set, Tuple


FAILURE_TYPES = {
    "BUILD_ERROR": "HIGH",
    "SEMANTIC_MISMATCH": "MEDIUM",
    "FIX_FAILED": "HIGH",
    "MISSING_ARTIFACT": "CRITICAL",
    "STALLED": "CRITICAL",
}

PRIORITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

TERMINAL_STATUSES = frozenset({"FAILED", "ERROR", "CRITICAL"})


@dataclass
class FixResult:
    rule_id: str
    attempt: int = 1
    status: str = "UNKNOWN"
    files_modified: List[str] = field(default_factory=list)
    error: Optional[str] = None
    error_hash: Optional[str] = None


@dataclass
class FailureRecord:
    rule_id: str
    attempt: int
    failure_types: List[str] = field(default_factory=list)
    priority: str = "HIGH"
    details: Dict = field(default_factory=dict)


@dataclass
class RetryEntry:
    rule_id: str
    attempt: int
    priority: str
    failure_reason: str
    previous_error: Optional[str] = None


@dataclass
class EscalationEntry:
    rule_id: str
    total_attempts: int
    final_failure: str
    failure_trail: List[Dict] = field(default_factory=list)
    escalated_at: str = ""


@dataclass
class FinalStatus:
    run_id: str = ""
    status: str = "ALL_CLEAR"
    requeued_count: int = 0
    escalated_count: int = 0
    rules: Dict[str, Dict] = field(default_factory=dict)


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
        json.dump(payload, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def append_jsonl(path: pathlib.Path, payload: Dict) -> None:
    if not path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _hash_error(message: str) -> Optional[str]:
    if not message:
        return None
    import hashlib

    return hashlib.sha256(message.encode("utf-8")).hexdigest()[:12]


def discover_fix_results(artifacts: pathlib.Path) -> List[FixResult]:
    if not artifacts.exists():
        return []

    results: List[FixResult] = []

    # Single aggregate file
    agg_path = artifacts / "06-fix-results.json"
    if agg_path.exists():
        data = read_json(agg_path)
        entries = data.get(
            "results", [data] if isinstance(data, dict) and "rule_id" in data else []
        )
        for entry in entries:
            results.append(
                FixResult(
                    rule_id=entry.get("rule_id", "unknown"),
                    attempt=entry.get("attempt", 1),
                    status=entry.get("status", "UNKNOWN"),
                    files_modified=entry.get("files_modified", []),
                    error=entry.get("error"),
                    error_hash=entry.get("error_hash"),
                )
            )
        return results

    # Per-rule files
    for fp in sorted(artifacts.glob("06-fix-result-*.json")):
        data = read_json(fp)
        if isinstance(data, list):
            for entry in data:
                results.append(
                    FixResult(
                        rule_id=entry.get(
                            "rule_id", fp.stem.replace("06-fix-result-", "")
                        ),
                        attempt=entry.get("attempt", 1),
                        status=entry.get("status", "UNKNOWN"),
                        files_modified=entry.get("files_modified", []),
                        error=entry.get("error"),
                        error_hash=entry.get("error_hash"),
                    )
                )
        else:
            results.append(
                FixResult(
                    rule_id=data.get("rule_id", fp.stem.replace("06-fix-result-", "")),
                    attempt=data.get("attempt", 1),
                    status=data.get("status", "UNKNOWN"),
                    files_modified=data.get("files_modified", []),
                    error=data.get("error"),
                    error_hash=data.get("error_hash"),
                )
            )

    return results


def parse_build_log(build_log: pathlib.Path) -> Dict[str, List[str]]:
    if not build_log.exists():
        return {}

    errors: Dict[str, List[str]] = {}
    text = build_log.read_text(encoding="utf-8", errors="replace")

    error_pattern = re.compile(
        r"(?P<file>[^\s:]+\.java):(?P<line>\d+):\s*error:\s*(?P<msg>.*)",
        re.IGNORECASE,
    )
    for m in error_pattern.finditer(text):
        fname = pathlib.Path(m.group("file")).name
        errors.setdefault(fname, []).append(m.group("msg").strip())

    return errors


def parse_semantic_diff(semantic_diff: pathlib.Path) -> Optional[Dict]:
    if not semantic_diff.exists():
        return None
    try:
        return read_json(semantic_diff)
    except (json.JSONDecodeError, ValueError):
        return None


def load_previous_retry_queue(artifacts: pathlib.Path) -> Optional[Dict]:
    rq_path = artifacts / "08-retry-queue.json"
    if rq_path.exists():
        return read_json(rq_path)
    return None


def load_previous_escalations(artifacts: pathlib.Path) -> Optional[Dict]:
    esc_path = artifacts / "08-escalations.json"
    if esc_path.exists():
        return read_json(esc_path)
    return None


def _rule_was_already_escalated(rule_id: str, escalations: Optional[Dict]) -> bool:
    if not escalations:
        return False
    for entry in escalations.get("escalations", []):
        if entry.get("rule_id") == rule_id:
            return True
    return False


def classify_failures(
    fix_results: List[FixResult],
    semantic_diff: Optional[Dict],
    build_errors: Dict[str, List[str]],
) -> List[FailureRecord]:
    records: List[FailureRecord] = []

    # Index semantic mismatches by file
    sem_mismatches_by_file: Dict[str, List[Dict]] = defaultdict(list)
    if semantic_diff:
        for d in semantic_diff.get("diffs", []):
            fname = d.get("file", "")
            sem_mismatches_by_file[fname].append(d)

    for fr in fix_results:
        if fr.status not in TERMINAL_STATUSES:
            continue

        ftypes: List[str] = []
        details: Dict = {}

        if fr.error:
            ftypes.append("FIX_FAILED")
            details["fix_error"] = fr.error

        for fname in fr.files_modified:
            base = pathlib.Path(fname).name
            if base in build_errors:
                ftypes.append("BUILD_ERROR")
                details.setdefault("build_errors", {})[fname] = build_errors[base]
            if base in sem_mismatches_by_file:
                ftypes.append("SEMANTIC_MISMATCH")
                details.setdefault("semantic_mismatches", {})[fname] = (
                    sem_mismatches_by_file[base]
                )

        if not ftypes:
            ftypes.append("FIX_FAILED")
            details["note"] = (
                "No specific failure signature found; treating as generic fix failure"
            )

        if (
            semantic_diff
            and semantic_diff.get("mismatch_count", 0) > 0
            and "SEMANTIC_MISMATCH" not in ftypes
        ):
            ftypes.append("SEMANTIC_MISMATCH")
            details["semantic_summary"] = (
                f"Total mismatches: {semantic_diff['mismatch_count']}"
            )

        priority = "LOW"
        for ft in ftypes:
            p = PRIORITY_ORDER.get(FAILURE_TYPES.get(ft, "LOW"), 3)
            if p < PRIORITY_ORDER[priority]:
                priority = FAILURE_TYPES.get(ft, "LOW")

        records.append(
            FailureRecord(
                rule_id=fr.rule_id,
                attempt=fr.attempt,
                failure_types=ftypes,
                priority=priority,
                details=details,
            )
        )

    return records


def detect_stalled(
    records: List[FailureRecord], previous_queue: Optional[Dict]
) -> List[str]:
    stalled: List[str] = []
    if not previous_queue:
        return stalled

    prev_entries = previous_queue.get("queue", [])
    prev_map: Dict[str, Dict] = {}
    for e in prev_entries:
        prev_map[e.get("rule_id", "")] = e

    for rec in records:
        prev = prev_map.get(rec.rule_id)
        if prev is None:
            continue
        prev_fail = prev.get("failure_reason", "")
        curr_fail = "; ".join(rec.failure_types)
        if prev_fail == curr_fail:
            stalled.append(rec.rule_id)

    return stalled


def route(
    records: List[FailureRecord],
    stalled_rules: List[str],
    max_retries: int,
    escalations: Optional[Dict],
) -> Tuple[List[RetryEntry], List[EscalationEntry]]:
    requeue: List[RetryEntry] = []
    escalated: List[EscalationEntry] = []

    for rec in records:
        if _rule_was_already_escalated(rec.rule_id, escalations):
            continue

        next_attempt = rec.attempt + 1
        fail_sig = "; ".join(sorted(rec.failure_types))

        is_stalled = rec.rule_id in stalled_rules

        if rec.attempt >= max_retries or is_stalled or rec.priority == "CRITICAL":
            entry = EscalationEntry(
                rule_id=rec.rule_id,
                total_attempts=rec.attempt,
                final_failure=fail_sig,
                failure_trail=[asdict(rec)],
                escalated_at=iso_now(),
            )
            if rec.priority == "CRITICAL":
                entry.final_failure = f"CRITICAL: {fail_sig}"
            elif is_stalled:
                entry.final_failure = (
                    f"STALLED: {fail_sig} (unchanged across 2 consecutive attempts)"
                )
            escalated.append(entry)
        else:
            requeue.append(
                RetryEntry(
                    rule_id=rec.rule_id,
                    attempt=next_attempt,
                    priority=rec.priority,
                    failure_reason=fail_sig,
                    previous_error=rec.details.get("fix_error"),
                )
            )

    requeue.sort(key=lambda e: (PRIORITY_ORDER.get(e.priority, 3), e.attempt))
    return requeue, escalated


def determine_overall_status(
    requeue_count: int,
    escalated_count: int,
    total_processed: int,
    clean_rules: int,
) -> str:
    if escalated_count == 0 and requeue_count == 0:
        return "ALL_CLEAR"
    if escalated_count > 0 and requeue_count > 0:
        return "PARTIAL_ESCALATION"
    if escalated_count > 0 and requeue_count == 0:
        if clean_rules > 0:
            return "PARTIAL_ESCALATION"
        return "FULL_ESCALATION"
    return "PARTIAL_RETRY"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Route failed JADE migration rule tasks with bounded retries"
    )
    parser.add_argument(
        "--artifacts",
        default="artifacts",
        help="Path to the artifacts directory",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum fix attempts per rule (default: 3)",
    )
    args = parser.parse_args()

    artifacts = pathlib.Path(args.artifacts)
    max_retries = args.max_retries

    if max_retries < 1:
        print("ERROR [INVALID_CONFIG] max-retries must be >= 1", file=sys.stderr)
        return 2

    # --- Discover inputs ---
    fix_results = discover_fix_results(artifacts)
    if not fix_results:
        print(
            "WARNING [NO_FIX_RESULTS] No 06-fix-result-*.json files found; nothing to route",
            file=sys.stderr,
        )
        write_json(
            artifacts / "08-final-status.json",
            {
                "run_id": "",
                "status": "ALL_CLEAR",
                "requeued_count": 0,
                "escalated_count": 0,
                "rules": {},
                "updated_at": iso_now(),
            },
        )
        return 0

    build_log = artifacts / "07-build.log"
    build_errors = parse_build_log(build_log)

    semantic_diff_path = artifacts / "07-semantic-diff.json"
    semantic_diff = parse_semantic_diff(semantic_diff_path)

    previous_queue = load_previous_retry_queue(artifacts)
    escalations = load_previous_escalations(artifacts)

    # Classify
    records = classify_failures(fix_results, semantic_diff, build_errors)
    if not records:
        # Everything passed — all fix results had non-terminal status
        write_json(
            artifacts / "08-retry-queue.json",
            {"queue": [], "updated_at": iso_now()},
        )
        write_json(
            artifacts / "08-escalations.json",
            {
                "escalations": escalations.get("escalations", [])
                if escalations
                else [],
                "updated_at": iso_now(),
            },
        )
        write_json(
            artifacts / "08-final-status.json",
            {
                "run_id": "",
                "status": "ALL_CLEAR",
                "requeued_count": 0,
                "escalated_count": 0,
                "rules": {},
                "updated_at": iso_now(),
            },
        )
        return 0

    # Detect stalled rules
    stalled_rules = detect_stalled(records, previous_queue)

    # Route
    requeue, escalated = route(records, stalled_rules, max_retries, escalations)
    requeue_count = len(requeue)
    escalated_count = len(escalated)

    clean_rules = sum(1 for fr in fix_results if fr.status not in TERMINAL_STATUSES)
    overall = determine_overall_status(
        requeue_count, escalated_count, len(records), clean_rules
    )

    # Write requeue
    write_json(
        artifacts / "08-retry-queue.json",
        {
            "queue": [asdict(r) for r in requeue],
            "updated_at": iso_now(),
            "meta": {
                "max_retries": max_retries,
                "backoff_base_s": 0,
            },
        },
    )

    # Merge escalations with any pre-existing
    existing_esc = escalations.get("escalations", []) if escalations else []
    all_esc = existing_esc + [asdict(e) for e in escalated]
    write_json(
        artifacts / "08-escalations.json",
        {
            "escalations": all_esc,
            "updated_at": iso_now(),
            "meta": {
                "escalation_threshold": max_retries,
                "escalation_reasons": {
                    "max_retries_exceeded": f"attempt >= {max_retries}",
                    "stalled": "unchanged failure signature across 2 consecutive attempts",
                    "critical": "missing artifact or unparseable output",
                },
            },
        },
    )

    # Write final status
    rules_status: Dict[str, Dict] = {}
    for r in requeue:
        rules_status[r.rule_id] = {"status": "REQUEUED", "next_attempt": r.attempt}
    for e in escalated:
        rules_status[e.rule_id] = {
            "status": "ESCALATED",
            "total_attempts": e.total_attempts,
        }
    for fr in fix_results:
        if fr.rule_id not in rules_status:
            rules_status[fr.rule_id] = {
                "status": "CLEAN" if fr.status not in TERMINAL_STATUSES else fr.status
            }

    write_json(
        artifacts / "08-final-status.json",
        {
            "run_id": "",
            "status": overall,
            "requeued_count": requeue_count,
            "escalated_count": escalated_count,
            "rules": rules_status,
            "updated_at": iso_now(),
        },
    )

    # Append log
    hist_path = artifacts / "phase-history.log.jsonl"
    append_jsonl(
        hist_path,
        {
            "ts": iso_now(),
            "phase": "RETRY_ROUTE",
            "status": "OK" if overall != "FULL_ESCALATION" else "ERROR",
            "message": f"Retry router: {requeue_count} requeued, {escalated_count} escalated, status={overall}",
            "artifacts": [
                "08-retry-queue.json",
                "08-escalations.json",
                "08-final-status.json",
            ],
        },
    )

    print(
        f"RETRY_ROUTE: {requeue_count} requeued, {escalated_count} escalated, overall={overall}"
    )
    return 0 if overall != "FULL_ESCALATION" else 1


if __name__ == "__main__":
    raise SystemExit(main())
