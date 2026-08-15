#!/usr/bin/env python3
"""jade-core-rule-dispatcher — routes rule tasks to recipe skills.

Reads task from batch JSON, rule from manifest, looks up recipe script
in recipe-registry.json, invokes recipe as subprocess, records result.

Contains ZERO transform logic — all transforms live in recipe skills.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys
from typing import Any, Dict, List, Optional

TMP_FILE_SUFFIX = ".tmp.dispatch"


def iso_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def read_json(path: pathlib.Path) -> Dict:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        return {"_error": str(exc)}


def write_json_atomic(path: pathlib.Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + TMP_FILE_SUFFIX)
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def load_task(batch_path: pathlib.Path, task_id: str) -> Optional[Dict]:
    if not batch_path.exists():
        return None
    batch = read_json(batch_path)
    if "_error" in batch:
        return None
    tasks: List[Dict] = batch.get("files", [])
    for task in tasks:
        tids = [
            f.get("rule_id", "")
            + "-"
            + f.get("file", "").split("/")[-1].replace(".java", "")
            for f in task.get("flags", [])
        ]
        if task_id in tids:
            return task
    for task in tasks:
        flags = task.get("flags", [])
        for fi, flag in enumerate(flags):
            synthetic_id = f"{flag.get('rule_id', '')}-{fi:04d}"
            if synthetic_id == task_id:
                entry = dict(task)
                entry["_match_index"] = fi
                entry["_flag"] = flag
                return entry
    return None


def validate_flag_line(flag: Dict) -> tuple[bool, str]:
    """Validate the source line before it reaches a recipe subprocess."""
    line = flag.get("line")
    if isinstance(line, bool) or not isinstance(line, int) or line < 1:
        return False, "Flag 'line' must be an integer >= 1"
    return True, ""


def load_rule(manifest_path: pathlib.Path, rule_id: str) -> Optional[Dict]:
    if not manifest_path.exists():
        return None
    manifest = read_json(manifest_path)
    if "_error" in manifest:
        return None
    rules: List[Dict] = manifest.get("rules", [])
    for rule in rules:
        if rule.get("id") == rule_id:
            return rule
    return None


def _fail(
    artifacts_dir: pathlib.Path,
    task_id: str,
    rule_id: str,
    file_rel: str,
    line: int,
    message: str,
) -> int:
    """Record a failed result and return exit code 2."""
    record_result(
        artifacts_dir,
        task_id,
        rule_id,
        file_rel,
        "FAILED",
        0,
        "",
        "",
        "",
        [message],
        [],
        line,
        line,
    )
    return 2


def load_registry() -> Dict:
    registry_path = pathlib.Path(__file__).parent.parent / "recipe-registry.json"
    return read_json(registry_path)


def dispatch_recipe(script_path: str, file_path: str, line: int) -> Dict:
    cmd = [
        sys.executable,
        script_path,
        "--file",
        file_path,
        "--line",
        str(line),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return {
            "status": "FAILED",
            "changes": 0,
            "warnings": [],
            "errors": [
                result.stderr.strip() or f"Recipe exit code {result.returncode}"
            ],
        }
    try:
        return json.loads(result.stdout.strip() or "{}")
    except json.JSONDecodeError:
        return {
            "status": "FAILED",
            "changes": 0,
            "warnings": [],
            "errors": [f"Recipe returned non-JSON: {result.stdout[:200]}"],
        }


def update_batch_status(
    artifacts_dir: pathlib.Path,
    rule_id: str,
    file_rel: str,
    status: str,
) -> None:
    """Atomically update the batch file entry for *file_rel* to *status*.

    Also refreshes ``05-rule-batch-status.json`` so the orchestrator
    can track overall completion without external scripts.
    """
    batch_path = artifacts_dir / f"05-rule-batch-{rule_id}.json"
    if not batch_path.exists():
        return
    try:
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    now = iso_now()
    updated = False
    for entry in batch.get("files", []):
        if entry.get("file") == file_rel:
            entry["status"] = status
            entry["updated_at"] = now
            updated = True
            break

    if not updated:
        return

    write_json_atomic(batch_path, batch)

    files = batch.get("files", [])
    total = len(files)
    counts = {"DONE": 0, "FAILED": 0, "SKIPPED": 0}
    for f in files:
        s = f.get("status", "PENDING")
        if s in counts:
            counts[s] += 1

    pending = total - counts["DONE"] - counts["FAILED"] - counts["SKIPPED"]
    if counts["FAILED"] > 0:
        batch_overall = "FAILED"
    elif counts["DONE"] + counts["SKIPPED"] == total:
        batch_overall = "DONE"
    elif counts["DONE"] + counts["SKIPPED"] > 0 or pending > 0:
        batch_overall = "IN_PROGRESS"
    else:
        batch_overall = "READY"

    status_payload = {
        "run_id": batch.get("run_id", artifacts_dir.name),
        "rule_id": rule_id,
        "total_files": total,
        "completed": counts["DONE"],
        "failed": counts["FAILED"],
        "skipped": counts["SKIPPED"],
        "pending": pending,
        "status": batch_overall,
        "updated_at": now,
    }
    write_json_atomic(artifacts_dir / "05-rule-batch-status.json", status_payload)


def record_result(
    artifacts_dir: pathlib.Path,
    task_id: str,
    rule_id: str,
    file_rel: str,
    status: str,
    match_count: int,
    match_context: str,
    diff_summary: str,
    verification_hint: str,
    errors: List[str],
    warnings: List[str],
    line_start: int,
    line_end: int,
) -> pathlib.Path:
    result = {
        "task_id": task_id,
        "rule_id": rule_id,
        "file": file_rel,
        "status": status,
        "match_count": match_count,
        "match_region": f"lines {line_start}-{line_end}",
        "match_context": match_context,
        "diff_summary": diff_summary,
        "verification_hint": verification_hint,
        "errors": errors,
        "warnings": warnings,
        "applied_at": iso_now(),
    }

    # Aggregate: one file per rule_id, append to array
    aggregate_path = artifacts_dir / f"06-fix-results-{rule_id}.json"
    existing: list = []
    if aggregate_path.exists():
        try:
            existing = json.loads(aggregate_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    existing.append(result)
    write_json_atomic(aggregate_path, existing)
    return aggregate_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="JADE Core Rule Dispatcher — routes rule tasks to recipe skills"
    )
    parser.add_argument("--artifacts-dir", required=True)
    parser.add_argument("--rule-id", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--workspace-root", default=".")
    args = parser.parse_args()

    artifacts_dir = pathlib.Path(args.artifacts_dir)
    if not artifacts_dir.is_dir():
        print(f"ERROR [ARTIFACTS_DIR_MISSING] {artifacts_dir}", file=sys.stderr)
        return 2

    workspace_root = pathlib.Path(args.workspace_root)
    errors: List[str] = []
    warnings: List[str] = []

    batch_path = artifacts_dir / f"05-rule-batch-{args.rule_id}.json"
    manifest_path = artifacts_dir / "01-breaking-changes-manifest.json"

    task = load_task(batch_path, args.task_id)
    if task is None:
        record_result(
            artifacts_dir,
            args.task_id,
            args.rule_id,
            "",
            "FAILED",
            0,
            "",
            "",
            "",
            [f"Task {args.task_id} not found"],
            [],
            0,
            0,
        )
        return 2

    file_rel = task.get("file", "")
    flags = task.get("flags", [])

    # If a synthetic _flag was injected by load_task (single-flag routing),
    # use that. Otherwise loop over all flags in the file entry.
    if "_flag" in task:
        flags = [task["_flag"]]

    if not file_rel:
        record_result(
            artifacts_dir,
            args.task_id,
            args.rule_id,
            "",
            "FAILED",
            0,
            "",
            "",
            "",
            ["Task entry missing 'file'"],
            [],
            0,
            0,
        )
        return 2

    file_path = workspace_root / file_rel
    if not file_path.exists():
        record_result(
            artifacts_dir,
            args.task_id,
            args.rule_id,
            file_rel,
            "FAILED",
            0,
            "",
            "",
            "",
            [f"File not found: {file_path}"],
            [],
            0,
            0,
        )
        return 2

    for fi, flag in enumerate(flags):
        valid, validation_error = validate_flag_line(flag)
        if not valid:
            per_flag_task_id = (
                f"{args.task_id}-f{fi:03d}" if len(flags) > 1 else args.task_id
            )
            record_result(
                artifacts_dir,
                per_flag_task_id,
                args.rule_id,
                file_rel,
                "FAILED",
                0,
                "",
                "",
                "",
                [validation_error],
                [],
                0,
                0,
            )
            update_batch_status(artifacts_dir, args.rule_id, file_rel, "FAILED")
            return 2

    rule = load_rule(manifest_path, args.rule_id)
    if rule is None:
        record_result(
            artifacts_dir,
            args.task_id,
            args.rule_id,
            file_rel,
            "FAILED",
            0,
            "",
            "",
            "",
            [f"Rule {args.rule_id} not found"],
            [],
            0,
            0,
        )
        return 2

    fix_strategy = rule.get("fix_strategy", "")

    if not fix_strategy.startswith("recipe:"):
        record_result(
            artifacts_dir,
            args.task_id,
            args.rule_id,
            file_rel,
            "FAILED",
            0,
            "",
            "",
            "",
            [f"No recipe mapping for fix_strategy: {fix_strategy}"],
            [],
            0,
            0,
        )
        return 2

    registry = load_registry()
    if "_error" in registry:
        record_result(
            artifacts_dir,
            args.task_id,
            args.rule_id,
            file_rel,
            "FAILED",
            0,
            "",
            "",
            "",
            [f"Failed to load recipe registry: {registry['_error']}"],
            [],
            0,
            0,
        )
        return 2

    recipe_entry = registry.get(args.rule_id)
    if recipe_entry is None:
        recipe_entry = registry.get("fallback")
    if recipe_entry is None:
        record_result(
            artifacts_dir,
            args.task_id,
            args.rule_id,
            file_rel,
            "FAILED",
            0,
            "",
            "",
            "",
            [
                f"No recipe registered for rule_id: {args.rule_id} and no fallback available"
            ],
            [],
            0,
            0,
        )
        return 2

    script_path = recipe_entry["script"]

    # Dispatch for every flag in this file entry
    overall_status = "SKIPPED"
    total_changes = 0
    any_failure = False

    for fi, flag in enumerate(flags):
        line_start = flag["line"]
        per_flag_task_id = (
            f"{args.task_id}-f{fi:03d}" if len(flags) > 1 else args.task_id
        )

        print(
            f"DISPATCH {args.rule_id} -> {recipe_entry['skill']} ({file_rel}:{line_start})"
        )
        recipe_result = dispatch_recipe(script_path, str(file_path), line_start)

        status = recipe_result.get("status", "FAILED")
        changes = recipe_result.get("changes", 0)
        recipe_warnings = recipe_result.get("warnings", [])
        recipe_errors = recipe_result.get("errors", [])
        diff_summary = recipe_result.get("diff_summary", f"{changes} change(s)")

        errors.extend(recipe_errors)
        warnings.extend(recipe_warnings)
        total_changes += changes

        if status == "FAILED":
            any_failure = True
            overall_status = "FAILED"
        elif status == "FIXED":
            overall_status = "FIXED"
        elif status == "DEFERRED" and overall_status not in ("FIXED", "FAILED"):
            overall_status = "DEFERRED"

        record_result(
            artifacts_dir,
            per_flag_task_id,
            args.rule_id,
            file_rel,
            status,
            1 if changes > 0 else 0,
            recipe_entry["skill"],
            diff_summary,
            rule.get("verification_hint", ""),
            errors,
            warnings,
            line_start,
            line_start,
        )
        safe_summary = diff_summary.encode("ascii", errors="replace").decode("ascii")
        print(f"{status} | {per_flag_task_id} | {file_rel} | {safe_summary}")

    if len(flags) > 1:
        print(
            f"AGGREGATE | {args.task_id} | {file_rel} | "
            f"{len(flags)} flag(s), {total_changes} change(s), {overall_status}"
        )

    batch_status = (
        "DONE" if overall_status in ("FIXED", "SKIPPED", "DEFERRED") else "FAILED"
    )
    update_batch_status(artifacts_dir, args.rule_id, file_rel, batch_status)

    return 0 if overall_status != "FAILED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
