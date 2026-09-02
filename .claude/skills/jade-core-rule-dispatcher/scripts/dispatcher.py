#!/usr/bin/env python3
"""jade-core-rule-dispatcher â€” routes rule tasks to registry recipes.

Reads task from batch JSON, rule from manifest, looks up recipe script
in recipe-registry.json, invokes recipe as subprocess, records result.

Contains ZERO transform logic â€” all transforms live in registry recipe scripts.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import pathlib
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

TMP_FILE_SUFFIX = ".tmp.dispatch"
RECIPE_STATUSES = {"FIXED", "FAILED", "SKIPPED", "DEFERRED", "NEEDS_REVIEW"}
RECIPE_REGISTRY_PREFIX = pathlib.PurePosixPath(
    ".claude/skills/java-migration-skill-registry"
).parts
RECIPE_BUCKETS = {"1.5-to-1.6", "1.7", "1.7-to-1.8", "8-to-11", "shared"}

# --- Agent-mode dispatch (recipe registry entries with "mode": "agent") ---
#
# These constants and functions implement the agent side of the dispatcher:
# ``--emit-agent-tasks`` turns a shard plan into a self-contained task list
# for a human/subagent to execute, and ``--record-agent-result`` validates
# and records the envelope that subagent hands back. Script-mode dispatch
# (the code above and below unchanged from before agent mode existed) never
# touches any of this.
AGENT_TASKS_VERSION = 1
AGENT_RESULT_VERSION = 1
NEEDS_REVIEW_THRESHOLD = 0.85
MATCH_QUALITY_FACTORS = {
    "exact": 1.0,       # single exact match, no ambiguity
    "near_miss": 0.9,   # single match, near-miss on an edge case
    "multiple": 0.8,    # multiple matches, first one used
    "ambiguous": 0.6,   # matched but surrounding context ambiguous
}
MANUAL_REVIEW_KEYWORDS = ("manual", "review")
MIGRATION_SKIP_MARKER = "MIGRATION-SKIP"
BEHAVIOR_CHANGE_CATEGORY = "BEHAVIOR_CHANGE"

# Same keys verify_shard.REQUIRED_SHARD_KEYS enforces -- copied rather than
# imported so this script has no cross-skill import dependency.
REQUIRED_SHARD_KEYS = (
    "shard_id",
    "rule_id",
    "class",
    "editable_files",
    "read_only_context",
    "entry_points",
    "invariants",
    "graph_artifact",
    "parallel_safe",
)

# Lazily-loaded handle to registry_modes.py (owned by a separate stream).
# Tests stub this out directly: monkeypatch.setattr(dispatcher, "_registry_modes", fake).
_registry_modes: Any = None


def _load_registry_modes() -> Any:
    """Load registry_modes.py as a module without relying on sys.path[0].

    Uses importlib.util.spec_from_file_location rather than a plain
    ``import registry_modes`` -- a plain import only works when this script
    is run directly (sys.path[0] == this directory); a test harness that
    loads this module through importlib would not have that entry on
    sys.path, and would also collide with the dispatcher's own top-level
    ``import`` machinery. Cached in the module-level ``_registry_modes``
    global so repeated calls (and test monkeypatching) share one handle.
    """
    global _registry_modes
    if _registry_modes is None:
        module_path = pathlib.Path(__file__).resolve().parent / "registry_modes.py"
        spec = importlib.util.spec_from_file_location(
            "jade_dispatcher_registry_modes", module_path
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"could not build a module spec for {module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _registry_modes = module
    return _registry_modes


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


def graph_context_for_flag(flag: Dict[str, Any]) -> Dict[str, Any]:
    """Extract additive advisory graph context from a flag entry.

    The flag's ``graph`` metadata (produced by the scanner / batch
    processor) is copied verbatim â€” source artifact, target node,
    impact files and diagnostics.  Never contains raw graph source and
    is never passed to recipe subprocesses.
    """
    graph = flag.get("graph")
    if "graph" not in flag or graph is None:
        return {
            "status": "unavailable",
            "diagnostics": [
                {"kind": "graph_unavailable", "message": "flag carries no graph metadata"}
            ],
        }
    if not isinstance(graph, dict):
        return {
            "status": "unavailable",
            "diagnostics": [
                {"kind": "graph_malformed", "message": "flag graph metadata is malformed"}
            ],
        }
    impact_files = graph.get("impact_files", [])
    if not isinstance(impact_files, list):
        impact_files = []
    diagnostics = graph.get("diagnostics", [])
    if not isinstance(diagnostics, list):
        diagnostics = []
    return {
        "status": graph.get("status", "available"),
        "source_artifact": graph.get("source_artifact"),
        "target_node": graph.get("declaration"),
        "impact_files": impact_files,
        "diagnostics": diagnostics,
    }


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
    graph_context: Optional[Dict[str, Any]] = None,
    mode: Optional[str] = None,
    shard_id: Optional[str] = None,
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
    if graph_context is not None:
        result["graph_context"] = graph_context
    # Both new params default to None: a script-mode call site (which never
    # passes them) produces a byte-identical record to before agent mode
    # existed -- no new key is ever added to the dict in that case.
    if mode is not None:
        result["mode"] = mode
    if shard_id is not None:
        result["shard_id"] = shard_id

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


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[4]


def _repo_relative_repr(path: pathlib.Path) -> str:
    """Best-effort repo-relative POSIX-style path for an artifact reference.

    Falls back to the path as given when it does not live under the repo
    root (e.g. an absolute tmp-dir path used in tests).
    """
    try:
        return str(path.resolve().relative_to(_repo_root()).as_posix())
    except ValueError:
        return str(path)


def load_shard_plan(path: pathlib.Path, rule_id: str) -> Dict[str, Any]:
    """Load and structurally validate a 05-rule-shards-<rule_id>.json plan.

    Returns the plan dict on success, or ``{"_error": <str>}`` on any
    structural problem -- missing/unreadable file, rule_id mismatch,
    status != "OK", malformed shards list, or a shard missing required keys.
    """
    payload = read_json(path)
    if "_error" in payload:
        return payload
    if payload.get("rule_id") != rule_id:
        return {
            "_error": (
                f"shard plan rule_id {payload.get('rule_id')!r} does not match "
                f"requested rule_id {rule_id!r}"
            )
        }
    if payload.get("status") != "OK":
        return {"_error": f"shard plan status is not OK: {payload.get('status')!r}"}
    shards = payload.get("shards")
    if not isinstance(shards, list):
        return {"_error": "shard plan 'shards' must be a list"}
    shard_count = payload.get("shard_count")
    if shard_count != len(shards):
        return {
            "_error": (
                f"shard_count {shard_count!r} does not match len(shards)={len(shards)}"
            )
        }
    for shard in shards:
        if not isinstance(shard, dict):
            return {"_error": "each shard must be a JSON object"}
        missing = [key for key in REQUIRED_SHARD_KEYS if key not in shard]
        if missing:
            return {
                "_error": (
                    f"shard {shard.get('shard_id', '<unknown>')!r} is missing "
                    f"required keys: {', '.join(missing)}"
                )
            }
    return payload


def shards_overlap_error(shards: List[Dict[str, Any]]) -> Optional[str]:
    """Return an error message when a file appears in >1 shard's editable_files.

    This is the hard precondition for per-shard rollback safety: if two
    shards can both edit the same file, rolling back shard B could discard
    shard A's already-accepted work. ``--emit-agent-tasks`` refuses to run
    (fail closed) rather than emit a task list that could not be safely
    rolled back.
    """
    owner: Dict[str, str] = {}
    for shard in shards:
        shard_id = shard.get("shard_id", "<unknown>")
        for file_rel in shard.get("editable_files", []) or []:
            norm = normalize_file_path(file_rel)
            if norm in owner and owner[norm] != shard_id:
                return (
                    f"file {file_rel!r} appears in editable_files of both "
                    f"shard {owner[norm]!r} and shard {shard_id!r}"
                )
            owner[norm] = shard_id
    return None


def build_agent_task(
    shard: Dict[str, Any],
    rule: Dict[str, Any],
    artifacts_dir: pathlib.Path,
    workspace_root: pathlib.Path,
    shard_plan_repr: str,
) -> Dict[str, Any]:
    """Build one tasks[] entry from a shard plan entry.

    Copies only paths and metadata already present in the shard plan --
    never opens a source file, so the resulting task carries zero bytes of
    source content.
    """
    del shard_plan_repr  # carried by the caller in the artifact's top level
    shard_id = shard.get("shard_id")
    rule_id = shard.get("rule_id")
    a = str(artifacts_dir)
    w = str(workspace_root)
    return {
        "task_id": shard_id,
        "shard_id": shard_id,
        "rule_id": rule_id,
        "class": shard.get("class"),
        "parallel_safe": shard.get("parallel_safe"),
        "editable_files": list(shard.get("editable_files", [])),
        "read_only_context": list(shard.get("read_only_context", [])),
        "entry_points": list(shard.get("entry_points", [])),
        "invariants": list(shard.get("invariants", [])),
        "graph_artifact": shard.get("graph_artifact"),
        "result_file": f"{a}/06-agent-result-{rule_id}-{shard_id}.json",
        "checkpoint_command": (
            "python .claude/skills/jade-core-orchestrator/scripts/shard_checkpoint.py "
            f"--artifacts-dir {a} --rule-id {rule_id} --shard-id {shard_id} "
            f"--workspace {w} --create"
        ),
        "verify_command": (
            "python .claude/skills/jade-core-verification/scripts/verify_shard.py "
            f"--artifacts-dir {a} --rule-id {rule_id} --shard-id {shard_id}"
        ),
        "gate_command": (
            "python .claude/skills/jade-core-verification/scripts/gate_signatures.py "
            f"--artifacts-dir {a} --rule-id {rule_id} --shard-id {shard_id} "
            f"--before-graph {a}/03.5-knowledge-graph.json "
            f"--after-graph {a}/03.5-knowledge-graph-after-{shard_id}.json"
        ),
        "record_command": (
            "python .claude/skills/jade-core-rule-dispatcher/scripts/dispatcher.py "
            f"--artifacts-dir {a} --rule-id {rule_id} --record-agent-result "
            f"--shard-id {shard_id} "
            f"--result-file {a}/06-agent-result-{rule_id}-{shard_id}.json"
        ),
        "accept_command": (
            "python .claude/skills/jade-core-orchestrator/scripts/shard_checkpoint.py "
            f"--artifacts-dir {a} --rule-id {rule_id} --shard-id {shard_id} "
            f"--workspace {w} --accept"
        ),
        "rollback_command": (
            "python .claude/skills/jade-core-orchestrator/scripts/shard_checkpoint.py "
            f"--artifacts-dir {a} --rule-id {rule_id} --shard-id {shard_id} "
            f'--workspace {w} --rollback --reason "<why>"'
        ),
    }


def emit_agent_tasks(
    artifacts_dir: pathlib.Path,
    rule_id: str,
    workspace_root: pathlib.Path,
    shard_plan_path: pathlib.Path,
    output_path: pathlib.Path,
    recipe_entry: Dict[str, Any],
    rule: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """Write the 05-agent-tasks-<rule_id>.json contract artifact.

    Returns ``(payload, warnings)``; ``payload is None`` signals a
    structural error -- nothing is written in that case.
    """
    plan = load_shard_plan(shard_plan_path, rule_id)
    if "_error" in plan:
        print(f"ERROR [SHARD_PLAN_INVALID] {plan['_error']}", file=sys.stderr)
        return None, []

    shards = plan.get("shards", [])
    overlap_error = shards_overlap_error(shards)
    if overlap_error:
        print(f"ERROR [SHARDS_OVERLAP] {overlap_error}", file=sys.stderr)
        return None, []

    shard_plan_repr = _repo_relative_repr(shard_plan_path)
    tasks = [
        build_agent_task(shard, rule, artifacts_dir, workspace_root, shard_plan_repr)
        for shard in shards
    ]
    tasks.sort(key=lambda t: t["shard_id"])

    warnings = list(plan.get("warnings", []))
    warnings.sort(key=lambda w: json.dumps(w, sort_keys=True))

    payload = {
        "schema_version": AGENT_TASKS_VERSION,
        "run_id": plan.get("run_id"),
        "rule_id": rule_id,
        "mode": "agent",
        "recipe_skill": recipe_entry.get("skill"),
        "recipe_skill_md": recipe_entry.get("skill_md"),
        "blast_class": plan.get("blast_class"),
        "shard_plan_artifact": shard_plan_repr,
        "artifacts_dir": str(artifacts_dir),
        "workspace_root": str(workspace_root),
        "verification_hint": rule.get("verification_hint", ""),
        "generated_at": iso_now(),
        "task_count": len(tasks),
        "tasks": tasks,
        "warnings": warnings,
    }
    try:
        write_json_atomic(output_path, payload)
    except OSError as exc:
        print(f"ERROR [WRITE_FAILED] {exc}", file=sys.stderr)
        return None, []
    return payload, warnings


def compute_final_confidence(rule_confidence: Any, match_quality: Any) -> Tuple[float, List[str]]:
    """Combine a rule's declared confidence with the subagent's match quality.

    ``match_quality`` unknown to MATCH_QUALITY_FACTORS degrades to the
    "ambiguous" factor rather than erroring -- an unrecognized quality label
    is not proof of a bad match, just of an unrecognized label.
    """
    reasons: List[str] = []
    factor = MATCH_QUALITY_FACTORS.get(match_quality)
    if factor is None:
        factor = MATCH_QUALITY_FACTORS["ambiguous"]
        reasons.append("match_quality_unknown")
    if (
        isinstance(rule_confidence, (int, float))
        and not isinstance(rule_confidence, bool)
        and 0.0 <= rule_confidence <= 1.0
    ):
        base = float(rule_confidence)
    else:
        base = 0.0
        reasons.append("rule_confidence_missing")
    return round(base * factor, 4), reasons


def needs_review_reasons(
    rule: Dict[str, Any],
    file_entry: Dict[str, Any],
    final_confidence: float,
    shard: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Six independent NEEDS_REVIEW triggers, evaluated from the subagent's
    envelope and the manifest rule -- never by opening the source file.

    ``shard`` is optional (defaults to None) so the three-argument contract
    keeps working for any caller that has no shard context; passing it in
    enables the "diff outside flagged region" check (condition 4), which
    needs the shard's entry_points to compute the flagged line range.
    """
    reasons = set()

    if final_confidence < NEEDS_REVIEW_THRESHOLD:
        reasons.add("low_final_confidence")

    match_count = file_entry.get("match_count")
    if isinstance(match_count, int) and not isinstance(match_count, bool) and match_count > 1:
        reasons.add("multiple_matches")

    fix_strategy = rule.get("fix_strategy", "")
    if isinstance(fix_strategy, str) and any(
        keyword in fix_strategy.lower() for keyword in MANUAL_REVIEW_KEYWORDS
    ):
        reasons.add("manual_review_keyword")

    if shard is not None:
        file_name = file_entry.get("file")
        entry_lines = [
            ep.get("line")
            for ep in shard.get("entry_points", []) or []
            if isinstance(ep, dict)
            and normalize_file_path(ep.get("file", "")) == normalize_file_path(file_name or "")
            and isinstance(ep.get("line"), int)
            and not isinstance(ep.get("line"), bool)
        ]
        if entry_lines:
            entry_min = min(entry_lines)
            entry_max = max(entry_lines)
            touched_start = file_entry.get("touched_line_start")
            touched_end = file_entry.get("touched_line_end")
            if (
                isinstance(touched_start, int)
                and not isinstance(touched_start, bool)
                and isinstance(touched_end, int)
                and not isinstance(touched_end, bool)
                and (touched_start < entry_min or touched_end > entry_max)
            ):
                reasons.add("diff_outside_flagged_region")

    if rule.get("category") == BEHAVIOR_CHANGE_CATEGORY:
        reasons.add("behavior_change_category")

    if file_entry.get("migration_skip_marker") is True:
        reasons.add("migration_skip_marker")

    return sorted(reasons)


def agent_graph_context_for_shard(shard: Dict[str, Any]) -> Dict[str, Any]:
    """Same 5-key advisory shape as graph_context_for_flag, sourced from the
    shard plan instead of a flag's ``graph`` metadata."""
    return {
        "status": "shard",
        "source_artifact": shard.get("graph_artifact"),
        "target_node": None,
        "impact_files": list(shard.get("read_only_context", [])),
        "diagnostics": [],
    }


def validate_agent_result(payload: Any, shard: Dict[str, Any], rule_id: str) -> Optional[str]:
    """Validate a 06-agent-result-<rule_id>-<shard_id>.json envelope.

    Fail closed on every check -- in particular, every file entry's "file"
    must belong to the shard's editable_files (EDITS_CONFINED_TO_EDITABLE_FILES).
    Returns None when the envelope is valid, else an error string.
    """
    if not isinstance(payload, dict):
        return "agent result envelope must be a JSON object"
    if payload.get("schema_version") != AGENT_RESULT_VERSION:
        return f"agent result schema_version must be {AGENT_RESULT_VERSION}"
    if payload.get("rule_id") != rule_id:
        return (
            f"agent result rule_id {payload.get('rule_id')!r} does not match "
            f"requested rule_id {rule_id!r}"
        )
    if payload.get("shard_id") != shard.get("shard_id"):
        return (
            f"agent result shard_id {payload.get('shard_id')!r} does not match "
            f"shard {shard.get('shard_id')!r}"
        )
    status = payload.get("status")
    if status not in RECIPE_STATUSES:
        return f"agent result status must be one of {sorted(RECIPE_STATUSES)}: {status!r}"
    if not isinstance(payload.get("match_quality"), str):
        return "agent result 'match_quality' must be a string"
    if not isinstance(payload.get("diff_summary"), str):
        return "agent result 'diff_summary' must be a string"

    files = payload.get("files")
    if not isinstance(files, list):
        return "agent result 'files' must be a list"

    editable = {normalize_file_path(f) for f in shard.get("editable_files", []) or []}
    for entry in files:
        if not isinstance(entry, dict):
            return "agent result file entry must be a JSON object"
        file_val = entry.get("file")
        if not isinstance(file_val, str) or not file_val.strip():
            return "agent result file entry 'file' must be a non-empty string"
        for field in ("match_count", "changes", "touched_line_start", "touched_line_end"):
            value = entry.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                return f"agent result file entry {field!r} must be a non-negative integer"
        if not isinstance(entry.get("migration_skip_marker"), bool):
            return "agent result file entry 'migration_skip_marker' must be a boolean"
        if not isinstance(entry.get("diff_summary"), str):
            return "agent result file entry 'diff_summary' must be a string"
        if normalize_file_path(file_val) not in editable:
            return (
                f"agent result file {file_val!r} is not in shard editable_files "
                "(EDITS_CONFINED_TO_EDITABLE_FILES violated)"
            )

    errors = payload.get("errors")
    if not isinstance(errors, list) or not all(isinstance(item, str) for item in errors):
        return "agent result 'errors' must be a list of strings"
    warnings = payload.get("warnings")
    if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
        return "agent result 'warnings' must be a list of strings"
    return None


def record_agent_result(
    artifacts_dir: pathlib.Path,
    rule_id: str,
    shard: Dict[str, Any],
    envelope: Dict[str, Any],
    rule: Dict[str, Any],
    recipe_skill: str = "",
) -> Tuple[str, List[str]]:
    """Record one fix-results entry per file (or a single empty-file entry
    when the envelope carries none), promoting FIXED to NEEDS_REVIEW when
    any file trips a needs_review_reasons() trigger. Returns
    ``(overall_status, task_ids)``.
    """
    shard_id = shard.get("shard_id", "")
    declared_status = envelope.get("status")
    match_quality = envelope.get("match_quality")
    files = envelope.get("files") or []
    graph_context = agent_graph_context_for_shard(shard)
    verification_hint = rule.get("verification_hint", "")
    base_errors = list(envelope.get("errors", []))
    base_warnings = list(envelope.get("warnings", []))

    if not files:
        record_result(
            artifacts_dir,
            shard_id,
            rule_id,
            "",
            declared_status,
            0,
            recipe_skill,
            envelope.get("diff_summary", ""),
            verification_hint,
            base_errors,
            base_warnings,
            0,
            0,
            graph_context=graph_context,
            mode="agent",
            shard_id=shard_id,
        )
        return declared_status, [shard_id]

    per_file_reasons: List[List[str]] = []
    any_reasons = False
    for file_entry in files:
        final_confidence, _ = compute_final_confidence(rule.get("confidence"), match_quality)
        reasons = needs_review_reasons(rule, file_entry, final_confidence, shard)
        per_file_reasons.append(reasons)
        if reasons:
            any_reasons = True

    overall_status = declared_status
    if declared_status == "FIXED" and any_reasons:
        overall_status = "NEEDS_REVIEW"

    task_ids: List[str] = []
    for i, file_entry in enumerate(files):
        task_id = f"{shard_id}-f{i:03d}"
        review_warnings = [f"NEEDS_REVIEW: {reason}" for reason in per_file_reasons[i]]
        record_result(
            artifacts_dir,
            task_id,
            rule_id,
            file_entry.get("file", ""),
            overall_status,
            file_entry.get("match_count", 0),
            recipe_skill,
            file_entry.get("diff_summary", ""),
            verification_hint,
            base_errors,
            base_warnings + review_warnings,
            file_entry.get("touched_line_start", 0),
            file_entry.get("touched_line_end", 0),
            graph_context=graph_context,
            mode="agent",
            shard_id=shard_id,
        )
        task_ids.append(task_id)

    return overall_status, task_ids


def _agent_main(args: argparse.Namespace, artifacts_dir: pathlib.Path) -> int:
    """Entry point for --emit-agent-tasks / --record-agent-result.

    Both subcommands share the same registry lookup and mode check: the
    recipe registry entry for --rule-id must exist and be mode="agent"
    (no fallback -- fallback is a script-mode concept), checked *before*
    anything else is read or written, so a mismatch never leaves a partial
    artifact behind.
    """
    registry = load_registry()
    if not isinstance(registry, dict):
        print("ERROR [REGISTRY_INVALID] Recipe registry root must be a JSON object", file=sys.stderr)
        return 3
    if "_error" in registry:
        print(
            f"ERROR [REGISTRY_INVALID] Failed to load recipe registry: {registry['_error']}",
            file=sys.stderr,
        )
        return 3

    recipe_entry = registry.get(args.rule_id)
    if not isinstance(recipe_entry, dict):
        print(f"ERROR [NO_RECIPE] No recipe registered for rule_id: {args.rule_id}", file=sys.stderr)
        return 3

    try:
        mode = _load_registry_modes().entry_mode(recipe_entry)
    except ValueError as exc:
        print(f"ERROR [MODE_INVALID] {exc}", file=sys.stderr)
        return 3
    except Exception as exc:  # module missing / malformed on disk
        print(f"ERROR [REGISTRY_MODES_UNAVAILABLE] {exc}", file=sys.stderr)
        return 3
    if mode != "agent":
        print(
            f"ERROR [MODE_MISMATCH] Recipe registry entry for {args.rule_id} is "
            f"mode={mode!r}; agent subcommands require mode='agent'",
            file=sys.stderr,
        )
        return 3

    manifest_path = artifacts_dir / "01-breaking-changes-manifest.json"
    rule = load_rule(manifest_path, args.rule_id)
    if rule is None:
        print(f"ERROR [RULE_NOT_FOUND] Rule {args.rule_id} not found", file=sys.stderr)
        return 3

    shard_plan_path = (
        pathlib.Path(args.shard_plan)
        if args.shard_plan
        else artifacts_dir / f"05-rule-shards-{args.rule_id}.json"
    )

    if args.emit_agent_tasks:
        workspace_root = pathlib.Path(args.workspace_root)
        output_path = (
            pathlib.Path(args.output)
            if args.output
            else artifacts_dir / f"05-agent-tasks-{args.rule_id}.json"
        )
        payload, warnings = emit_agent_tasks(
            artifacts_dir,
            args.rule_id,
            workspace_root,
            shard_plan_path,
            output_path,
            recipe_entry,
            rule,
        )
        if payload is None:
            return 3
        return 1 if warnings else 0

    # --record-agent-result
    if not args.shard_id:
        print("ERROR [SHARD_ID_REQUIRED] --shard-id is required with --record-agent-result", file=sys.stderr)
        return 3
    if not args.result_file:
        print("ERROR [RESULT_FILE_REQUIRED] --result-file is required with --record-agent-result", file=sys.stderr)
        return 3

    plan = load_shard_plan(shard_plan_path, args.rule_id)
    if "_error" in plan:
        print(f"ERROR [SHARD_PLAN_INVALID] {plan['_error']}", file=sys.stderr)
        return 3

    shard = next(
        (s for s in plan.get("shards", []) if s.get("shard_id") == args.shard_id), None
    )
    if shard is None:
        print(f"ERROR [SHARD_NOT_FOUND] shard_id {args.shard_id!r} not found in shard plan", file=sys.stderr)
        return 3

    envelope = read_json(pathlib.Path(args.result_file))
    if "_error" in envelope:
        print(f"ERROR [RESULT_FILE_INVALID] {envelope['_error']}", file=sys.stderr)
        return 3

    validation_error = validate_agent_result(envelope, shard, args.rule_id)
    if validation_error:
        print(f"ERROR [AGENT_RESULT_INVALID] {validation_error}", file=sys.stderr)
        return 3

    overall_status, _task_ids = record_agent_result(
        artifacts_dir,
        args.rule_id,
        shard,
        envelope,
        rule,
        recipe_skill=recipe_entry.get("skill", ""),
    )
    if overall_status == "FAILED":
        return 2
    if overall_status == "NEEDS_REVIEW":
        return 4
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="JADE Core Rule Dispatcher â€” routes rule tasks to registry recipes"
    )
    parser.add_argument("--artifacts-dir", required=True)
    parser.add_argument("--rule-id", required=True)
    parser.add_argument("--task-id", default=None)
    parser.add_argument("--workspace-root", default=".")
    parser.add_argument("--shard-plan", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--shard-id", default=None)
    parser.add_argument("--result-file", default=None)
    agent_mode_group = parser.add_mutually_exclusive_group()
    agent_mode_group.add_argument("--emit-agent-tasks", action="store_true")
    agent_mode_group.add_argument("--record-agent-result", action="store_true")
    args = parser.parse_args(argv)

    if not args.emit_agent_tasks and not args.record_agent_result and args.task_id is None:
        parser.error("--task-id is required in script mode")

    artifacts_dir = pathlib.Path(args.artifacts_dir)
    if not artifacts_dir.is_dir():
        print(f"ERROR [ARTIFACTS_DIR_MISSING] {artifacts_dir}", file=sys.stderr)
        return 2

    if args.emit_agent_tasks or args.record_agent_result:
        return _agent_main(args, artifacts_dir)

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
    # Route on the entry's "mode" *before* touching the script-mode-only
    # "script" field, so an agent-mode entry fails with a clear mismatch
    # message instead of "missing a valid 'script'". An entry with no
    # "mode" key (or mode=None) is resolved to "script" without consulting
    # registry_modes.py at all -- this is the one hard compatibility
    # guarantee: today's registry entries must keep working byte-for-byte
    # even when registry_modes.py (a separate stream's file) is absent.
    declared_mode = recipe_entry.get("mode")
    if declared_mode is None:
        mode = "script"
    else:
        try:
            mode = _load_registry_modes().entry_mode(recipe_entry)
        except ValueError as exc:
            return _fail(artifacts_dir, args.task_id, args.rule_id, file_rel, 0, str(exc))
        except Exception as exc:  # module missing / malformed on disk
            return _fail(
                artifacts_dir,
                args.task_id,
                args.rule_id,
                file_rel,
                0,
                f"Failed to load registry mode resolver: {exc}",
            )
    if mode != "script":
        return _fail(
            artifacts_dir,
            args.task_id,
            args.rule_id,
            file_rel,
            0,
            f"Recipe registry entry for {args.rule_id} is mode={mode!r}; "
            f"script dispatch refused (use --emit-agent-tasks)",
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
        elif status == "NEEDS_REVIEW" and overall_status not in ("FIXED", "FAILED"):
            overall_status = "NEEDS_REVIEW"

        graph_context = graph_context_for_flag(flag)
        if graph_context.get("status") == "unavailable":
            warnings.extend(graph_context.get("diagnostics", []))

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
            graph_context,
        )
        safe_summary = diff_summary.encode("ascii", errors="replace").decode("ascii")
        print(f"{status} | {per_flag_task_id} | {file_rel} | {safe_summary}")

    if len(flags) > 1:
        print(
            f"AGGREGATE | {args.task_id} | {file_rel} | "
            f"{len(flags)} flag(s), {total_changes} change(s), {overall_status}"
        )

    batch_status = (
        "DONE"
        if overall_status in ("FIXED", "SKIPPED", "DEFERRED", "NEEDS_REVIEW")
        else "FAILED"
    )
    update_batch_status(artifacts_dir, args.rule_id, file_rel, batch_status)

    return 0 if overall_status != "FAILED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
