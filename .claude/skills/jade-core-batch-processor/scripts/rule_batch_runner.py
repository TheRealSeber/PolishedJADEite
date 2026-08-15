#!/usr/bin/env python3
"""JADE Rule Batch Processor — enforces Rule-by-Rule Sequential Batching.

Process exactly ONE rule_id batch at a time:
  1. Read 04-flag-index.json and 05-rule-queue.json.
  2. Validate the requested rule_id exists in the queue.
  3. Produce a per-file task list for that rule.
  4. Track completion status per file.
  5. Persist 05-rule-batch-{rule_id}.json and 05-rule-batch-status.json.

No lock manager. No cross-rule parallel execution.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
import importlib.util
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------
FILE_STATUSES = {"PENDING", "IN_PROGRESS", "DONE", "SKIPPED", "FAILED"}
BATCH_STATUSES = {"READY", "IN_PROGRESS", "DONE", "FAILED"}
GRAPH_ARTIFACT = "03.5-knowledge-graph.json"


# ---------------------------------------------------------------------------
# Helpers (mirrors orchestrator.py conventions)
# ---------------------------------------------------------------------------
def iso_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def read_json(path: pathlib.Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: pathlib.Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    tmp.replace(path)


def _graph_helpers():
    """Reuse the scanner's optional graph loader without adding a pipeline dependency."""
    scanner = pathlib.Path(__file__).parents[3] / "skills" / "jade-core-scanner" / "scripts" / "scan_and_tag.py"
    spec = importlib.util.spec_from_file_location("jade_scanner_graph", scanner)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load graph helper: {scanner}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def die(code: str, message: str) -> int:
    print(f"ERROR [{code}] {message}", file=sys.stderr)
    return 2


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------
def load_flag_index(artifacts: pathlib.Path) -> Dict[str, Any]:
    path = artifacts / "04-flag-index.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing required artifact: {path}")
    return read_json(path)


def load_rule_queue(artifacts: pathlib.Path) -> List[str]:
    path = artifacts / "05-rule-queue.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing required artifact: {path}")
    data = read_json(path)
    rules = data.get("rules", [])
    if not isinstance(rules, list):
        raise ValueError("05-rule-queue.json: 'rules' must be a list")
    return rules


def build_file_task_list(
    rule_id: str,
    flag_index: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Extract flagged entries for rule_id, grouped by file.

    Expected flag_index shape:
      {
        "flags": [
          {
            "rule_id": "RAW_TYPES",
            "file": "src/foo/Bar.java",
            "flag": "RAW_INST",
            "line": 42,
            ...
          },
          ...
        ]
      }

    Returns a list of per-file task dicts:
      {
        "file": "src/foo/Bar.java",
        "flags": [...],
        "status": "PENDING",
        "updated_at": null
      }
    """

    flags = flag_index.get("flags", [])
    if not isinstance(flags, list):
        raise ValueError("04-flag-index.json: 'flags' must be a list")

    # Filter to this rule only
    matched = [f for f in flags if f.get("rule_id") == rule_id]
    if not matched:
        print(f"WARNING: No flag entries found for rule_id={rule_id}")
        return []

    # Group by file
    by_file: Dict[str, List[Dict[str, Any]]] = {}
    for entry in sorted(matched, key=lambda f: (f.get("file", ""), f.get("line", 0), json.dumps(f, sort_keys=True))):
        filepath = entry.get("file", "")
        by_file.setdefault(filepath, []).append(entry)

    file_tasks: List[Dict[str, Any]] = []
    for filepath, entries in sorted(by_file.items()):
        file_tasks.append(
            {
                "file": filepath,
                "flags": entries,
                "transform_scope": "DIRECT",
                "status": "PENDING",
                "updated_at": None,
            }
        )

    return file_tasks


def build_impact_only_list(rule_id: str, flag_index: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Collect graph dependents while keeping them out of transformation tasks."""
    direct_files = {
        flag.get("file") for flag in flag_index.get("flags", [])
        if isinstance(flag, dict) and flag.get("rule_id") == rule_id and flag.get("file")
    }
    impact: Dict[str, Dict[str, Any]] = {}
    for flag in flag_index.get("flags", []):
        if not isinstance(flag, dict) or flag.get("rule_id") != rule_id:
            continue
        graph = flag.get("graph", {})
        for path in graph.get("paths", []) if isinstance(graph, dict) else []:
            if not isinstance(path, dict) or not path.get("file") or path["file"] in direct_files:
                continue
            item = impact.setdefault(path["file"], {
                "file": path["file"], "reasons": set(), "paths": [],
                "source_artifact": GRAPH_ARTIFACT,
                "source_identity": graph.get("source_identity", {}),
            })
            item["reasons"].update(path.get("reasons", []))
            item["paths"].append({"path": path.get("path", []), "reasons": path.get("reasons", [])})

    result = []
    for filepath in sorted(impact):
        item = impact[filepath]
        result.append({
            "file": filepath,
            "source_artifact": item["source_artifact"],
            "source_identity": item["source_identity"],
            "transform_scope": "IMPACT_ONLY",
            "reasons": sorted(item["reasons"]),
            "paths": sorted(item["paths"], key=lambda p: (p["path"], p["reasons"])),
        })
    return result


def write_batch_artifact(
    artifacts: pathlib.Path,
    rule_id: str,
    file_tasks: List[Dict[str, Any]],
    impact_only: Optional[List[Dict[str, Any]]] = None,
    graph_metadata: Optional[Dict[str, Any]] = None,
) -> pathlib.Path:
    for task in file_tasks:
        task["transform_scope"] = "DIRECT"
    for item in impact_only or []:
        item["transform_scope"] = "IMPACT_ONLY"
    payload = {
        "rule_id": rule_id,
        "batch_id": f"batch-{rule_id}-{iso_now().replace(':', '-')}",
        "created_at": iso_now(),
        "total_files": len(file_tasks),
        "files": file_tasks,
        "impact_only": impact_only or [],
        "graph": graph_metadata or {
            "status": "unavailable",
            "source_artifact": GRAPH_ARTIFACT,
            "source_identity": {},
            "diagnostics": [{"kind": "graph_unavailable"}],
        },
    }
    path = artifacts / f"05-rule-batch-{rule_id}.json"
    write_json(path, payload)
    return path


def write_batch_status(
    artifacts: pathlib.Path,
    rule_id: str,
    run_id: str,
    file_tasks: List[Dict[str, Any]],
) -> pathlib.Path:
    total = len(file_tasks)
    counts = {"DONE": 0, "FAILED": 0, "SKIPPED": 0}
    for t in file_tasks:
        s = t.get("status", "PENDING")
        if s in counts:
            counts[s] += 1

    pending = total - counts["DONE"] - counts["FAILED"] - counts["SKIPPED"]

    if counts["FAILED"] > 0:
        batch_status = "FAILED"
    elif counts["DONE"] + counts["SKIPPED"] == total:
        batch_status = "DONE"
    elif counts["DONE"] + counts["SKIPPED"] > 0 or pending > 0:
        batch_status = "IN_PROGRESS"
    else:
        batch_status = "READY"

    payload = {
        "run_id": run_id,
        "rule_id": rule_id,
        "total_files": total,
        "completed": counts["DONE"],
        "failed": counts["FAILED"],
        "skipped": counts["SKIPPED"],
        "pending": pending,
        "status": batch_status,
        "updated_at": iso_now(),
    }
    path = artifacts / "05-rule-batch-status.json"
    write_json(path, payload)
    return path


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------
def cmd_prepare(artifacts: pathlib.Path, rule_id: str, run_id: str) -> int:
    """Read flag index, build per-file task list, write batch artifact + status."""

    flag_index = load_flag_index(artifacts)
    rule_queue = load_rule_queue(artifacts)

    if rule_id not in rule_queue:
        return die(
            "RULE_NOT_IN_QUEUE",
            f"rule_id '{rule_id}' not found in 05-rule-queue.json. "
            f"Available: {', '.join(rule_queue)}",
        )

    file_tasks = build_file_task_list(rule_id, flag_index)
    try:
        graph_helpers = _graph_helpers()
        graph_metadata = graph_helpers.enrich_flags_with_graph(flag_index.get("flags", []), artifacts)
        impact_only = build_impact_only_list(rule_id, flag_index)
    except Exception as exc:
        print(f"WARNING [GRAPH] graph impact metadata unavailable: {exc}", file=sys.stderr)
        impact_only = []
        graph_metadata = {
            "status": "unavailable", "source_artifact": GRAPH_ARTIFACT,
            "source_identity": {}, "diagnostics": [{"kind": "graph_invalid", "message": str(exc)}],
        }
    if not file_tasks:
        print(f"No files flagged for rule_id={rule_id}. Marking batch as DONE.")
        # Still produce artifacts so the orchestrator can proceed
        file_tasks = []  # empty, explicit

    batch_path = write_batch_artifact(artifacts, rule_id, file_tasks, impact_only, graph_metadata)
    status_path = write_batch_status(artifacts, rule_id, run_id, file_tasks)

    print(f"PREPARED rule_id={rule_id} — {len(file_tasks)} file(s)")
    print(f"  batch:  {batch_path}")
    print(f"  status: {status_path}")
    return 0


def cmd_update(
    artifacts: pathlib.Path,
    rule_id: str,
    run_id: str,
    file_path: str,
    new_status: str,
) -> int:
    """Update a single file's status in the batch artifact, then refresh status."""

    batch_path = artifacts / f"05-rule-batch-{rule_id}.json"
    if not batch_path.exists():
        return die(
            "BATCH_NOT_FOUND",
            f"No batch artifact for rule_id={rule_id}. Run 'prepare' first.",
        )

    if new_status not in FILE_STATUSES:
        return die(
            "INVALID_STATUS",
            f"'{new_status}' not in {sorted(FILE_STATUSES)}",
        )

    batch = read_json(batch_path)
    files = batch.get("files", [])

    updated = False
    for entry in files:
        if entry.get("file") == file_path:
            entry["status"] = new_status
            entry["updated_at"] = iso_now()
            updated = True
            break

    if not updated:
        return die(
            "FILE_NOT_IN_BATCH",
            f"File '{file_path}' not found in batch for rule_id={rule_id}",
        )

    batch["files"] = files
    write_json(batch_path, batch)
    write_batch_status(artifacts, rule_id, run_id, files)

    print(f"UPDATED {file_path} -> {new_status}")
    return 0


def cmd_status(artifacts: pathlib.Path, rule_id: str) -> int:
    """Print current batch status to stdout."""

    status_path = artifacts / "05-rule-batch-status.json"
    if not status_path.exists():
        print("STATUS: NOT_STARTED")
        return 0

    status = read_json(status_path)
    if status.get("rule_id") != rule_id:
        print(
            f"STATUS: STALE (status.json is for {status.get('rule_id')}, "
            f"requested {rule_id})"
        )
        return 0

    print(
        f"rule_id={status['rule_id']}  "
        f"status={status['status']}  "
        f"done={status['completed']}/{status['total_files']}  "
        f"failed={status['failed']}  "
        f"skipped={status['skipped']}  "
        f"pending={status['pending']}"
    )
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="JADE Rule Batch Processor — one rule_id at a time"
    )
    parser.add_argument(
        "--artifacts",
        default="artifacts",
        help="Path to artifacts directory",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # prepare
    p_prep = sub.add_parser("prepare", help="Build per-file task list for a rule_id")
    p_prep.add_argument("--rule-id", required=True, help="Rule ID to process")
    p_prep.add_argument("--run-id", required=True, help="Migration run ID")

    # update
    p_upd = sub.add_parser("update", help="Mark a file's status in the batch")
    p_upd.add_argument("--rule-id", required=True, help="Rule ID")
    p_upd.add_argument("--run-id", required=True, help="Migration run ID")
    p_upd.add_argument("--file", required=True, help="File path to update")
    p_upd.add_argument(
        "--status",
        required=True,
        choices=sorted(FILE_STATUSES),
        help="New file status",
    )

    # status
    p_stat = sub.add_parser("status", help="Show current batch status")
    p_stat.add_argument("--rule-id", required=True, help="Rule ID")

    args = parser.parse_args()
    artifacts = pathlib.Path(args.artifacts)

    try:
        if args.command == "prepare":
            return cmd_prepare(artifacts, args.rule_id, args.run_id)
        elif args.command == "update":
            return cmd_update(
                artifacts, args.rule_id, args.run_id, args.file, args.status
            )
        elif args.command == "status":
            return cmd_status(artifacts, args.rule_id)
        else:
            return die("UNKNOWN_COMMAND", f"Unknown command: {args.command}")
    except FileNotFoundError as exc:
        return die("ARTIFACT_MISSING", str(exc))
    except (ValueError, json.JSONDecodeError) as exc:
        return die("ARTIFACT_INVALID", str(exc))
    except Exception as exc:
        return die("UNEXPECTED", f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
