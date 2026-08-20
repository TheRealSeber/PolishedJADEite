#!/usr/bin/env python3
"""jade-core-rule-dispatcher — routes rule tasks to registry recipes.

Reads task from batch JSON, rule from manifest, looks up recipe script
in recipe-registry.json, invokes recipe as subprocess, records result.

Contains ZERO transform logic — all transforms live in registry recipe scripts.
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
RECIPE_STATUSES = {"FIXED", "FAILED", "SKIPPED", "DEFERRED"}
RECIPE_REGISTRY_PREFIX = pathlib.PurePosixPath(
    ".claude/skills/java-migration-skill-registry"
).parts
RECIPE_BUCKETS = {"1.5-to-1.6", "1.7", "1.7-to-1.8", "shared"}


def iso_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def read_json(path: pathlib.Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        return {"_error": str(exc)}
    if not isinstance(payload, dict):
        return {"_error": "JSON root must be an object"}
    return payload


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
    tasks = batch.get("files", [])
    if not isinstance(tasks, list) or not all(isinstance(task, dict) for task in tasks):
        return None
    for task in tasks:
        if "file" in task and not isinstance(task["file"], str):
            return None
        flags = task.get("flags", [])
        if not isinstance(flags, list) or not all(isinstance(flag, dict) for flag in flags):
            return None
        if any(
            ("rule_id" in flag and not isinstance(flag["rule_id"], str))
            or ("file" in flag and not isinstance(flag["file"], str))
            or (
                "line" in flag
                and (not isinstance(flag["line"], int) or isinstance(flag["line"], bool))
            )
            for flag in flags
        ):
            return None
        tids = [
            f.get("rule_id", "")
            + "-"
            + f.get("file", "").split("/")[-1].replace(".java", "")
            for f in flags
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


def validate_flag(flag: Dict[str, Any], expected_rule_id: str) -> Optional[str]:
    """Return a routing error for an incomplete or mismatched flag."""
    for field in ("rule_id", "file", "line"):
        if field not in flag:
            return f"Flag missing required field '{field}'"
    if not isinstance(flag["rule_id"], str) or not flag["rule_id"].strip():
        return "Flag 'rule_id' must be a non-empty string"
    if not isinstance(flag["file"], str) or not flag["file"].strip():
        return "Flag 'file' must be a non-empty string"
    if not isinstance(flag["line"], int) or isinstance(flag["line"], bool) or flag["line"] < 1:
        return "Flag 'line' must be an integer >= 1"
    if flag["rule_id"] != expected_rule_id:
        return (
            f"Flag rule_id {flag['rule_id']!r} does not match requested rule_id "
            f"{expected_rule_id!r}"
        )
    return None


def normalize_file_path(file_path: str) -> str:
    """Use the repository's canonical forward-slash form for relative files."""
    return file_path.replace("\\", "/")


def load_rule(manifest_path: pathlib.Path, rule_id: str) -> Optional[Dict]:
    if not manifest_path.exists():
        return None
    manifest = read_json(manifest_path)
    if "_error" in manifest:
        return None
    rules = manifest.get("rules", [])
    if not isinstance(rules, list) or not all(isinstance(rule, dict) for rule in rules):
        return None
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


def load_registry() -> Any:
    registry_path = pathlib.Path(__file__).parent.parent / "recipe-registry.json"
    return read_json(registry_path)


def resolve_script_path(script_path: str) -> pathlib.Path:
    if not isinstance(script_path, str):
        raise ValueError("Recipe script path must be a string")
    path = pathlib.Path(script_path)
    repo_root = pathlib.Path(__file__).resolve().parents[4]
    resolved = path.resolve() if path.is_absolute() else (repo_root / path).resolve()
    try:
        resolved.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError(f"Recipe script path outside repository: {script_path}") from exc
    relative = pathlib.PurePosixPath(script_path)
    if (
        path.is_absolute()
        or "\\" in script_path
        or relative.parts[: len(RECIPE_REGISTRY_PREFIX)] != RECIPE_REGISTRY_PREFIX
        or len(relative.parts) != len(RECIPE_REGISTRY_PREFIX) + 4
        or relative.parts[-2:] != ("scripts", "apply.py")
    ):
        raise ValueError(
            "Recipe script must be a canonical registry recipe script: "
            f"{script_path}"
        )
    script_on_disk = repo_root / pathlib.Path(script_path)
    if script_on_disk.is_symlink():
        raise ValueError(f"Recipe script must not be a symlink: {script_path}")
    bucket, recipe_name = relative.parts[len(RECIPE_REGISTRY_PREFIX) : len(RECIPE_REGISTRY_PREFIX) + 2]
    if (
        bucket not in RECIPE_BUCKETS
        or not bucket
        or not recipe_name
        or pathlib.PurePath(bucket).parts != (bucket,)
        or pathlib.PurePath(recipe_name).parts != (recipe_name,)
        or bucket in {".", ".."}
        or recipe_name in {".", ".."}
    ):
        raise ValueError(f"Recipe script has unsafe registry path: {script_path}")
    expected = (
        f"{RECIPE_REGISTRY_PREFIX[0]}/{RECIPE_REGISTRY_PREFIX[1]}/"
        f"{RECIPE_REGISTRY_PREFIX[2]}/{bucket}/{recipe_name}/scripts/apply.py"
    )
    if script_path != expected:
        raise ValueError(
            "Recipe script must be a canonical registry recipe script: "
            f"{script_path}"
        )
    registry_root = repo_root / ".claude/skills/java-migration-skill-registry"
    try:
        resolved.relative_to(registry_root.resolve())
    except ValueError as exc:
        raise ValueError(f"Recipe script path outside registry: {script_path}") from exc
    expected = registry_root / bucket / recipe_name / "scripts" / "apply.py"
    if resolved != expected.resolve():
        raise ValueError(f"Recipe script is not the canonical registry path: {script_path}")
    return resolved


def _failed_recipe_result(message: str) -> Dict[str, Any]:
    return {
        "status": "FAILED",
        "changes": 0,
        "warnings": [],
        "errors": [message],
        "diff_summary": message,
    }


def _validate_recipe_result(result: Any) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return _failed_recipe_result("Recipe returned non-object JSON")
    status = result.get("status")
    changes = result.get("changes")
    warnings = result.get("warnings")
    errors = result.get("errors")
    diff_summary = result.get("diff_summary")
    if status not in RECIPE_STATUSES:
        return _failed_recipe_result(f"Recipe returned unknown status: {status!r}")
    if not isinstance(changes, int) or isinstance(changes, bool) or changes < 0:
        return _failed_recipe_result("Recipe result 'changes' must be a non-negative integer")
    if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
        return _failed_recipe_result("Recipe result 'warnings' must be a list of strings")
    if not isinstance(errors, list) or not all(isinstance(item, str) for item in errors):
        return _failed_recipe_result("Recipe result 'errors' must be a list of strings")
    if not isinstance(diff_summary, str):
        return _failed_recipe_result("Recipe result 'diff_summary' must be a string")
    return result


def dispatch_recipe(script_path: str, file_path: str, line: int) -> Dict:
    try:
        resolved_script = resolve_script_path(script_path)
    except (TypeError, ValueError, OSError) as exc:
        return _failed_recipe_result(str(exc))
    if not resolved_script.is_file():
        return _failed_recipe_result(f"Recipe script not found: {script_path}")
    cmd = [
        sys.executable,
        str(resolved_script),
        "--file",
        file_path,
        "--line",
        str(line),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as exc:
        return _failed_recipe_result(f"Failed to execute recipe: {exc}")
    if result.returncode != 0:
        stderr = result.stderr.strip() if isinstance(result.stderr, str) else ""
        return _failed_recipe_result(stderr or f"Recipe exit code {result.returncode}")
    try:
        recipe_result = json.loads(result.stdout.strip() or "{}")
    except (json.JSONDecodeError, TypeError):
        stdout = result.stdout if isinstance(result.stdout, str) else repr(result.stdout)
        return _failed_recipe_result(f"Recipe returned non-JSON: {stdout[:200]}")
    return _validate_recipe_result(recipe_result)


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


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="JADE Core Rule Dispatcher — routes rule tasks to registry recipes"
    )
    parser.add_argument("--artifacts-dir", required=True)
    parser.add_argument("--rule-id", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--workspace-root", default=".")
    args = parser.parse_args(argv)

    artifacts_dir = pathlib.Path(args.artifacts_dir)
    if not artifacts_dir.is_dir():
        print(f"ERROR [ARTIFACTS_DIR_MISSING] {artifacts_dir}", file=sys.stderr)
        return 2

    workspace_root = pathlib.Path(args.workspace_root).resolve()
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

    for flag in flags:
        flag_error = validate_flag(flag, args.rule_id)
        if flag_error:
            record_result(
                artifacts_dir,
                args.task_id,
                args.rule_id,
                task.get("file", ""),
                "FAILED",
                0,
                "",
                "",
                "",
                [flag_error],
                [],
                0,
                0,
            )
            return 2
        if normalize_file_path(flag["file"]) != normalize_file_path(file_rel):
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
                    f"Flag file {flag['file']!r} does not match task file "
                    f"{file_rel!r}"
                ],
                [],
                flag["line"],
                flag["line"],
            )
            return 2

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

    try:
        file_path = (workspace_root / file_rel).resolve()
        file_path.relative_to(workspace_root)
    except (TypeError, ValueError, OSError) as exc:
        return _fail(
            artifacts_dir,
            args.task_id,
            args.rule_id,
            file_rel,
            0,
            f"File path outside workspace: {file_rel} ({exc})",
        )
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

    if not isinstance(fix_strategy, str) or not fix_strategy.startswith("recipe:"):
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
    if not isinstance(registry, dict):
        return _fail(
            artifacts_dir,
            args.task_id,
            args.rule_id,
            file_rel,
            0,
            "Recipe registry root must be a JSON object",
        )
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

    if not isinstance(recipe_entry, dict):
        return _fail(
            artifacts_dir,
            args.task_id,
            args.rule_id,
            file_rel,
            0,
            "Recipe registry entry must be a JSON object",
        )
    script_path = recipe_entry.get("script")
    if not isinstance(script_path, str) or not script_path.strip():
        return _fail(
            artifacts_dir,
            args.task_id,
            args.rule_id,
            file_rel,
            0,
            "Recipe registry entry is missing a valid 'script'",
        )
    skill_name = recipe_entry.get("skill", "<unknown recipe>")

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
            f"DISPATCH {args.rule_id} -> {skill_name} ({file_rel}:{line_start})"
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
            skill_name,
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
