#!/usr/bin/env python3
"""shard_checkpoint.py -- per-shard git-blob checkpoint/rollback/accept ledger.

Used by agent-mode RULE_BATCH_LOOP recipes (see jade-core-orchestrator's
orchestrator.py: agent_registry_entry / _process_agent_rule /
_agent_shard_instructions) to make one shard's edit safely reversible
without ever creating a commit, moving HEAD, touching the index, or using
git stash. Migration workspaces (migration-runs/*/workspace) are tracked
inside the same repository the orchestrator runs from, so any of those
operations would collide with the surrounding repo's own history.

Mechanism:
  --create   snapshot each of the shard's editable_files as a loose git
             blob (``git hash-object -w``) plus its POSIX permission bits.
  --rollback restore those exact bytes and mode (``git cat-file blob``),
             or delete a file the shard created (existed=false at
             checkpoint time). Touches only this shard's own files --
             a sibling shard of the same rule is never affected.
  --accept   mark the shard closed; the checkpoint blob is no longer
             needed so the ledger entry's file list is slimmed to just
             the file paths.
  --status   print "<shard_id> <state>" per ledger entry, sorted.

See 06-shard-checkpoints-<rule_id>.json for the ledger schema.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional

SHARD_LEDGER_STATES = ("CHECKPOINTED", "ACCEPTED", "ROLLED_BACK")


# ---------------------------------------------------------------------------
# Small IO helpers
# ---------------------------------------------------------------------------
def iso_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def read_json(path: pathlib.Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json_atomic(path: pathlib.Path, payload: Dict[str, Any]) -> None:
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix=".shard-checkpoint-", suffix=".tmp", dir=str(directory)
    )
    tmp_path = pathlib.Path(tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _ledger_path(artifacts_dir: pathlib.Path, rule_id: str) -> pathlib.Path:
    return artifacts_dir / f"06-shard-checkpoints-{rule_id}.json"


def _new_ledger(rule_id: str, run_id: str, workspace: pathlib.Path) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "rule_id": rule_id,
        "workspace_root": str(workspace),
        "repo_root": "",
        "shards": {},
    }


def _load_ledger_for_create(
    artifacts_dir: pathlib.Path, rule_id: str, run_id: str, workspace: pathlib.Path
) -> Dict[str, Any]:
    path = _ledger_path(artifacts_dir, rule_id)
    if not path.exists():
        return _new_ledger(rule_id, run_id, workspace)
    ledger = read_json(path)
    if not isinstance(ledger, dict) or not isinstance(ledger.get("shards"), dict):
        raise ValueError(
            "shard ledger is malformed (not a JSON object with a 'shards' object)"
        )
    return ledger


def _find_shard(plan: Dict[str, Any], shard_id: str) -> Optional[Dict[str, Any]]:
    for shard in plan.get("shards", []):
        if isinstance(shard, dict) and shard.get("shard_id") == shard_id:
            return shard
    return None


# ---------------------------------------------------------------------------
# Git object-store helpers -- ZERO commits, ZERO HEAD movement, ZERO index.
# ---------------------------------------------------------------------------
def _discover_repo_root(workspace: pathlib.Path) -> Optional[str]:
    """Find the git work tree that tracks *workspace*.

    Returns None on any failure (git missing, workspace outside any work
    tree, timeout) -- callers treat that as an environment error.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(workspace), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    out = proc.stdout.strip()
    return out or None


def _hash_object(repo_root: str, abs_path: pathlib.Path) -> Optional[str]:
    try:
        proc = subprocess.run(
            ["git", "-C", repo_root, "hash-object", "-w", "--", str(abs_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    sha = proc.stdout.strip()
    return sha or None


def _cat_blob(repo_root: str, sha: str) -> Optional[bytes]:
    try:
        proc = subprocess.run(
            ["git", "-C", repo_root, "cat-file", "blob", sha],
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def _resolve_in_workspace(workspace: pathlib.Path, rel: Any) -> Optional[pathlib.Path]:
    if not isinstance(rel, str) or not rel:
        return None
    try:
        workspace_resolved = workspace.resolve()
        resolved = (workspace / rel).resolve()
        resolved.relative_to(workspace_resolved)
    except (TypeError, ValueError, OSError):
        return None
    return resolved


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------
def cmd_create(args: argparse.Namespace, artifacts_dir: pathlib.Path, workspace: pathlib.Path) -> int:
    shard_plan_path = (
        pathlib.Path(args.shards_artifact)
        if args.shards_artifact
        else artifacts_dir / f"05-rule-shards-{args.rule_id}.json"
    )
    if not shard_plan_path.exists():
        print(f"ERROR [SHARD_PLAN_MISSING] {shard_plan_path}", file=sys.stderr)
        return 3
    try:
        plan = read_json(shard_plan_path)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR [SHARD_PLAN_UNREADABLE] {exc}", file=sys.stderr)
        return 3
    if not isinstance(plan, dict):
        print("ERROR [SHARD_PLAN_INVALID] shard plan must be a JSON object", file=sys.stderr)
        return 3

    shard = _find_shard(plan, args.shard_id)
    if shard is None:
        print(
            f"ERROR [SHARD_NOT_FOUND] shard {args.shard_id!r} not found in {shard_plan_path}",
            file=sys.stderr,
        )
        return 3
    editable = shard.get("editable_files")
    if not isinstance(editable, list) or not editable or not all(
        isinstance(f, str) and f for f in editable
    ):
        print(
            f"ERROR [SHARD_INVALID] shard {args.shard_id!r} has no valid editable_files",
            file=sys.stderr,
        )
        return 3

    repo_root = _discover_repo_root(workspace)
    if repo_root is None:
        print(
            f"ERROR [WORKSPACE_NOT_A_WORKTREE] {workspace} is not inside a git work "
            f"tree, or git is unavailable",
            file=sys.stderr,
        )
        return 3

    try:
        ledger = _load_ledger_for_create(
            artifacts_dir, args.rule_id, plan.get("run_id", ""), workspace
        )
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        print(f"ERROR [LEDGER_INVALID] {exc}", file=sys.stderr)
        return 3
    shards_ledger = ledger["shards"]

    existing = shards_ledger.get(args.shard_id)
    if isinstance(existing, dict) and existing.get("state") == "CHECKPOINTED":
        print(
            f"ERROR [ALREADY_CHECKPOINTED] shard {args.shard_id!r} is already CHECKPOINTED",
            file=sys.stderr,
        )
        return 2

    editable_set = set(editable)
    for other_id, other in shards_ledger.items():
        if other_id == args.shard_id or not isinstance(other, dict):
            continue
        if other.get("state") != "CHECKPOINTED":
            continue
        other_files = {
            f.get("file") for f in other.get("files", []) if isinstance(f, dict)
        }
        overlap = editable_set & other_files
        if overlap:
            print(
                f"ERROR [SHARD_FILE_OVERLAP] files {sorted(overlap)} are already "
                f"checkpointed by shard {other_id!r}",
                file=sys.stderr,
            )
            return 2

    resolved_paths: Dict[str, pathlib.Path] = {}
    for f in editable:
        resolved = _resolve_in_workspace(workspace, f)
        if resolved is None:
            print(
                f"ERROR [PATH_OUTSIDE_WORKSPACE] {f!r} resolves outside {workspace}",
                file=sys.stderr,
            )
            return 2
        resolved_paths[f] = resolved

    file_entries: List[Dict[str, Any]] = []
    for f in editable:
        abs_path = resolved_paths[f]
        if abs_path.exists():
            sha = _hash_object(repo_root, abs_path)
            if sha is None:
                print(
                    f"ERROR [GIT_HASH_OBJECT_FAILED] could not snapshot {f!r}",
                    file=sys.stderr,
                )
                return 3
            mode = stat.S_IMODE(abs_path.stat().st_mode)
            file_entries.append(
                {"file": f, "existed": True, "blob": sha, "mode": mode}
            )
        else:
            file_entries.append(
                {"file": f, "existed": False, "blob": None, "mode": None}
            )

    now = iso_now()
    shards_ledger[args.shard_id] = {
        "state": "CHECKPOINTED",
        "created_at": now,
        "updated_at": now,
        "rollback_reason": None,
        "files": file_entries,
    }
    ledger["repo_root"] = repo_root
    ledger["workspace_root"] = str(workspace)
    _write_json_atomic(_ledger_path(artifacts_dir, args.rule_id), ledger)
    return 0


def _load_ledger_for_mutation(
    artifacts_dir: pathlib.Path, rule_id: str
) -> Optional[Dict[str, Any]]:
    """Load an existing ledger for --rollback/--accept. Returns None (and
    prints its own error) when the ledger is missing or malformed."""
    ledger_path = _ledger_path(artifacts_dir, rule_id)
    if not ledger_path.exists():
        print(f"ERROR [LEDGER_MISSING] {ledger_path}", file=sys.stderr)
        return None
    try:
        ledger = read_json(ledger_path)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR [LEDGER_UNREADABLE] {exc}", file=sys.stderr)
        return None
    if not isinstance(ledger, dict) or not isinstance(ledger.get("shards"), dict):
        print(f"ERROR [LEDGER_INVALID] malformed ledger: {ledger_path}", file=sys.stderr)
        return None
    return ledger


def cmd_rollback(args: argparse.Namespace, artifacts_dir: pathlib.Path, workspace: pathlib.Path) -> int:
    ledger = _load_ledger_for_mutation(artifacts_dir, args.rule_id)
    if ledger is None:
        return 3
    shards_ledger = ledger["shards"]
    entry = shards_ledger.get(args.shard_id)
    if not isinstance(entry, dict):
        print(
            f"ERROR [SHARD_NOT_CHECKPOINTED] shard {args.shard_id!r} has no ledger entry",
            file=sys.stderr,
        )
        return 2
    if entry.get("state") != "CHECKPOINTED":
        print(
            f"ERROR [SHARD_NOT_CHECKPOINTED] shard {args.shard_id!r} state is "
            f"{entry.get('state')!r}, expected CHECKPOINTED",
            file=sys.stderr,
        )
        return 2

    repo_root = ledger.get("repo_root") or _discover_repo_root(workspace)
    if not repo_root:
        print(
            f"ERROR [WORKSPACE_NOT_A_WORKTREE] cannot discover repo root for {workspace}",
            file=sys.stderr,
        )
        return 3

    warnings: List[str] = []
    for file_entry in entry.get("files", []):
        if not isinstance(file_entry, dict):
            continue
        rel = file_entry.get("file")
        resolved = _resolve_in_workspace(workspace, rel)
        if resolved is None:
            print(
                f"ERROR [PATH_OUTSIDE_WORKSPACE] {rel!r} resolves outside {workspace}",
                file=sys.stderr,
            )
            return 2
        if file_entry.get("existed"):
            sha = file_entry.get("blob")
            content = _cat_blob(repo_root, sha) if isinstance(sha, str) and sha else None
            if content is None:
                print(
                    f"ERROR [BLOB_UNREADABLE] cannot restore {rel!r} from blob {sha!r}",
                    file=sys.stderr,
                )
                return 2
            mode = file_entry.get("mode")
            resolved.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".shard-rollback-", dir=str(resolved.parent))
            tmp_path = pathlib.Path(tmp)
            try:
                with os.fdopen(fd, "wb") as tf:
                    tf.write(content)
                    tf.flush()
                    os.fsync(tf.fileno())
                if isinstance(mode, int):
                    os.chmod(tmp_path, mode)
                os.replace(tmp_path, resolved)
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()
        else:
            if resolved.exists():
                resolved.unlink()
            else:
                warnings.append(f"{rel} already absent")

    entry["state"] = "ROLLED_BACK"
    entry["rollback_reason"] = args.reason
    entry["updated_at"] = iso_now()
    _write_json_atomic(_ledger_path(artifacts_dir, args.rule_id), ledger)
    return 1 if warnings else 0


def cmd_accept(args: argparse.Namespace, artifacts_dir: pathlib.Path, workspace: pathlib.Path) -> int:
    ledger = _load_ledger_for_mutation(artifacts_dir, args.rule_id)
    if ledger is None:
        return 3
    shards_ledger = ledger["shards"]
    entry = shards_ledger.get(args.shard_id)
    if not isinstance(entry, dict) or entry.get("state") != "CHECKPOINTED":
        state_val = entry.get("state") if isinstance(entry, dict) else None
        print(
            f"ERROR [SHARD_NOT_CHECKPOINTED] shard {args.shard_id!r} state is "
            f"{state_val!r}, expected CHECKPOINTED",
            file=sys.stderr,
        )
        return 2

    warnings: List[str] = []
    slim_files: List[Dict[str, Any]] = []
    for file_entry in entry.get("files", []):
        if not isinstance(file_entry, dict):
            continue
        rel = file_entry.get("file")
        slim_files.append({"file": rel})
        if file_entry.get("existed"):
            resolved = _resolve_in_workspace(workspace, rel)
            if resolved is None or not resolved.exists():
                warnings.append(f"{rel} no longer exists on disk at accept time")

    entry["state"] = "ACCEPTED"
    entry["updated_at"] = iso_now()
    entry["files"] = slim_files
    _write_json_atomic(_ledger_path(artifacts_dir, args.rule_id), ledger)
    return 1 if warnings else 0


def cmd_status(args: argparse.Namespace, artifacts_dir: pathlib.Path, workspace: pathlib.Path) -> int:
    ledger_path = _ledger_path(artifacts_dir, args.rule_id)
    if not ledger_path.exists():
        return 0
    try:
        ledger = read_json(ledger_path)
    except (json.JSONDecodeError, OSError):
        return 0
    shards_ledger = ledger.get("shards", {}) if isinstance(ledger, dict) else {}
    if not isinstance(shards_ledger, dict):
        return 0
    for shard_id, info in sorted(shards_ledger.items()):
        if args.shard_id and shard_id != args.shard_id:
            continue
        state_val = info.get("state") if isinstance(info, dict) else "UNKNOWN"
        print(f"{shard_id} {state_val}")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Per-shard git-blob checkpoint/rollback/accept ledger for agent-mode rule recipes"
    )
    parser.add_argument("--artifacts-dir", required=True, help="Path to artifacts directory")
    parser.add_argument("--rule-id", required=True, help="Rule id owning the shard")
    parser.add_argument(
        "--shard-id",
        default=None,
        help="Shard id (required for --create/--rollback/--accept; optional filter for --status)",
    )
    parser.add_argument("--workspace", required=True, help="Migration workspace root")
    parser.add_argument(
        "--shards-artifact",
        default=None,
        help="Shard plan artifact (default: <artifacts-dir>/05-rule-shards-<rule-id>.json)",
    )
    parser.add_argument(
        "--reason", default=None, help="Rollback reason (required for --rollback)"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--create", action="store_true")
    group.add_argument("--rollback", action="store_true")
    group.add_argument("--accept", action="store_true")
    group.add_argument("--status", action="store_true")
    args = parser.parse_args(argv)

    if (args.create or args.rollback or args.accept) and not args.shard_id:
        parser.error("--shard-id is required for --create/--rollback/--accept")
    if args.rollback and not args.reason:
        parser.error("--reason is required for --rollback")

    artifacts_dir = pathlib.Path(args.artifacts_dir)
    workspace = pathlib.Path(args.workspace)

    if args.create:
        return cmd_create(args, artifacts_dir, workspace)
    if args.rollback:
        return cmd_rollback(args, artifacts_dir, workspace)
    if args.accept:
        return cmd_accept(args, artifacts_dir, workspace)
    return cmd_status(args, artifacts_dir, workspace)


if __name__ == "__main__":
    raise SystemExit(main())
