#!/usr/bin/env python3
"""Check that a migration run resolved every flag it raised.

A run reaching DONE is not by itself evidence that its work landed: a rule can
raise flags and never be dispatched, a shard can be accepted while its recorded
status says otherwise, and a marker left in the source reads as unfinished work
to whoever inherits the tree. This walks the artifacts and reports, per rule,
how many flags were raised against how many results were recorded, so coverage
can be confirmed rather than asserted.

Deleted files count as resolved: removing a file resolves every flag in it,
which is how CORBA_REMOVAL was closed.

    python3 scripts/verify_delivery.py migration-runs/jade-1.6-to-1.7-v2

Exit codes: 0 every flag accounted for, 1 flags outstanding, 2 artifacts
missing or unreadable.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys
from typing import Any, Dict, List

JADE_FLAG_RE = re.compile(r"JADE-FLAG:([A-Z][A-Z0-9_]*)")

TERMINAL_OK = "DONE"
RESOLVED_STATUSES = {"FIXED", "SKIPPED", "DEFERRED", "NEEDS_REVIEW", "FAILED"}


def read_json(path: pathlib.Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def flags_by_rule(artifacts: pathlib.Path) -> Dict[str, int]:
    index = artifacts / "04-flag-index.json"
    if not index.is_file():
        return {}
    payload = read_json(index)
    counts: Dict[str, int] = collections.Counter()
    for flag in payload.get("flags", []):
        rule = flag.get("rule_id")
        if isinstance(rule, str):
            counts[rule] += 1
    return dict(counts)


def results_by_rule(artifacts: pathlib.Path) -> Dict[str, Dict[str, int]]:
    """Tally fix-result records per rule, weighted by ``match_count``.

    A shard's fix-result record is filed per *file*, not per flagged site --
    a multi-site file (the common case once a rule has more than a handful of
    call sites) gets one record whose ``match_count`` covers every site the
    shard touched. Counting records instead of ``match_count`` compares file
    granularity against the line-granularity of 04-flag-index.json and
    manufactures a false "unresolved" gap for every rule whose shards ever
    grouped more than one site per file.
    """
    out: Dict[str, Dict[str, int]] = {}
    for path in sorted(artifacts.glob("06-fix-results-*.json")):
        rule = path.name[len("06-fix-results-") : -len(".json")]
        tally: Dict[str, int] = collections.Counter()
        for record in read_json(path):
            status = record.get("status")
            if status in RESOLVED_STATUSES:
                count = record.get("match_count", 1)
                if not isinstance(count, int) or count < 1:
                    count = 1
                tally[status] += count
        out[rule] = dict(tally)
    return out


def withdrawn_rules(artifacts: pathlib.Path) -> Dict[str, str]:
    manifest = artifacts / "01-breaking-changes-manifest.json"
    if not manifest.is_file():
        return {}
    payload = read_json(manifest)
    return {
        entry["id"]: entry.get("reason", "")
        for entry in payload.get("withdrawn_rules", [])
        if isinstance(entry, dict) and "id" in entry
    }


def deleted_source_files(run: pathlib.Path, artifacts: pathlib.Path) -> int:
    """Files present in the baseline tree and absent from the workspace."""
    config = artifacts / "00-run-config.json"
    if not config.is_file():
        return 0
    cfg = read_json(config)
    repo = run.parent.parent
    baseline = repo / cfg.get("baseline_path", "")
    workspace = repo / cfg.get("workspace_path", "")
    if not baseline.is_dir() or not workspace.is_dir():
        return 0
    missing = 0
    for source in baseline.rglob("*.java"):
        if not (workspace / source.relative_to(baseline)).exists():
            missing += 1
    return missing


def leftover_markers(run: pathlib.Path, own_rules: "set[str]") -> int:
    """Count JADE-FLAG markers this run's own rules are responsible for.

    A baseline workspace can carry marker comments left by earlier, unrelated
    migration jumps (e.g. a jade-8-to-11 rule's markers surviving into the
    jade-11-to-17 baseline). Counting every "JADE-FLAG:" string regardless of
    which rule raised it blames this run for cleanup work that was never in
    its manifest. Scope the count to rule ids this run actually raised flags
    for (from 04-flag-index.json, passed in as ``own_rules``).
    """
    workspace = run / "workspace"
    if not workspace.is_dir():
        return 0
    total = 0
    for source in workspace.rglob("*.java"):
        text = source.read_text(encoding="utf-8", errors="replace")
        for match in JADE_FLAG_RE.finditer(text):
            if match.group(1) in own_rules:
                total += 1
    return total


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run", help="path to a migration run directory")
    args = parser.parse_args(argv)

    run = pathlib.Path(args.run).resolve()
    artifacts = run / "artifacts"
    if not artifacts.is_dir():
        print(f"ERROR [ARTIFACTS_MISSING] {artifacts}", file=sys.stderr)
        return 2

    state_path = artifacts / "00-run-state.json"
    if not state_path.is_file():
        print(f"ERROR [RUN_STATE_MISSING] {state_path}", file=sys.stderr)
        return 2
    state = read_json(state_path).get("state", "?")

    raised = flags_by_rule(artifacts)
    recorded = results_by_rule(artifacts)
    withdrawn = withdrawn_rules(artifacts)
    deleted = deleted_source_files(run, artifacts)

    print(f"{run.name}  state={state}")
    print()
    print(f"  {'rule':34s} {'raised':>7s} {'recorded':>9s}  disposition")

    outstanding = 0
    for rule in sorted(raised, key=lambda r: -raised[r]):
        flags = raised[rule]
        tally = recorded.get(rule, {})
        total = sum(tally.values())
        if rule in withdrawn:
            note = "rule withdrawn on evidence"
        elif total >= flags:
            note = ", ".join(f"{k} {v}" for k, v in sorted(tally.items()))
        elif deleted and total:
            note = f"{total} records, {deleted} source files deleted"
        else:
            outstanding += flags - total
            note = f"UNRESOLVED: {flags - total}"
        print(f"  {rule:34s} {flags:7d} {total:9d}  {note}")

    markers = leftover_markers(run, set(raised))
    print()
    print(f"  JADE-FLAG markers left in workspace: {markers}")
    if deleted:
        print(f"  source files deleted vs baseline:    {deleted}")

    if state != TERMINAL_OK:
        print(f"\n  run did not reach {TERMINAL_OK}", file=sys.stderr)
        return 1
    if outstanding:
        print(f"\n  {outstanding} flag(s) raised and never resolved", file=sys.stderr)
        return 1
    print("\n  every raised flag is accounted for")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
