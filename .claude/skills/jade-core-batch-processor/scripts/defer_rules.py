#!/usr/bin/env python3
"""JADE Rule Deferral — rewrite JADE-FLAG markers to deferred status.

When a user chooses NOT to apply a modernization rule, this script rewrites
``// JADE-FLAG:<rule_id>`` → ``// JADE-MODERNIZATION-DEFERRED:<rule_id> <reason>``
in the workspace source files.  The rewritten markers are permanently visible
as technical-debt indicators but are ignored by subsequent scanner runs.

Usage:
    python defer_rules.py --workspace migration-runs/X/workspace \\
                          --artifacts migration-runs/X/artifacts \\
                          --rule-id STRINGS_IN_SWITCH \\
                          --reason "Not applicable to JADE codebase"
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from typing import Any, Dict, List, Tuple

# ---------------------------------------------------------------------------
# Comment syntax map (mirrors scan_and_tag.py)
# ---------------------------------------------------------------------------
_COMMENT_SYNTAX: Dict[str, Tuple[str, str]] = {
    ".java": ("//", ""),
    ".properties": ("#", ""),
    ".xml": ("<!--", "-->"),
    ".gradle": ("//", ""),
    ".kt": ("//", ""),
    ".scala": ("//", ""),
    ".groovy": ("//", ""),
}

_DEFAULT_COMMENT: Tuple[str, str] = ("//", "")


def _comment_syntax(ext: str) -> Tuple[str, str]:
    return _COMMENT_SYNTAX.get(ext.lower(), _DEFAULT_COMMENT)


# ---------------------------------------------------------------------------
# Flag detection
# ---------------------------------------------------------------------------
def _is_flag_line(line: str, rule_id: str, ext: str) -> bool:
    """Check if *line* is a JADE-FLAG comment for *rule_id*."""
    prefix, suffix = _comment_syntax(ext)
    flag_start = f"{prefix} JADE-FLAG:{rule_id} ".lstrip()
    alt_start = f"{prefix}JADE-FLAG:{rule_id} ".lstrip()
    stripped = line.strip()
    return stripped.startswith(flag_start) or stripped.startswith(alt_start)


def _rewrite_flag_line(line: str, rule_id: str, reason: str, ext: str) -> str:
    """Replace JADE-FLAG with JADE-MODERNIZATION-DEFERRED in *line*."""
    prefix, suffix = _comment_syntax(ext)
    indent = line[: len(line) - len(line.lstrip())]
    return f"{indent}{prefix} JADE-MODERNIZATION-DEFERRED:{rule_id} {reason}{suffix}\n"


# ---------------------------------------------------------------------------
# Helpers (mirrors rule_batch_runner.py conventions)
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


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------
def defer_rule(
    workspace: pathlib.Path,
    artifacts: pathlib.Path,
    rule_id: str,
    reason: str,
) -> Tuple[int, List[str]]:
    """Rewrite all JADE-FLAG markers for *rule_id* to deferred markers.

    Returns (exit_code, list_of_modified_files).
    """
    modified: List[str] = []
    flags_rewritten: int = 0

    for fp in workspace.rglob("*.java"):
        try:
            lines = fp.read_text(encoding="utf-8", errors="replace").splitlines(
                keepends=True
            )
        except OSError as exc:
            print(f"WARN [FILE_READ] {fp}: {exc}", file=sys.stderr)
            continue

        ext = fp.suffix.lower()
        rewritten = False
        new_lines: List[str] = []

        for line in lines:
            if _is_flag_line(line, rule_id, ext):
                new_lines.append(_rewrite_flag_line(line, rule_id, reason, ext))
                flags_rewritten += 1
                rewritten = True
            else:
                new_lines.append(line)

        if rewritten:
            tmp = fp.with_name(fp.name + ".defertmp")
            with tmp.open("w", encoding="utf-8") as fh:
                fh.writelines(new_lines)
            tmp.replace(fp)
            modified.append(str(fp.relative_to(workspace)))

    return 0 if flags_rewritten >= 0 else 2, modified


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Defer JADE modernization flags — rewrite to JADE-MODERNIZATION-DEFERRED"
    )
    parser.add_argument("--workspace", required=True, help="Path to workspace root")
    parser.add_argument(
        "--artifacts", required=True, help="Path to artifacts directory"
    )
    parser.add_argument("--rule-id", required=True, help="Rule ID to defer")
    parser.add_argument(
        "--reason", required=True, help="Reason for deferral (preserved in comment)"
    )
    args = parser.parse_args()

    workspace = pathlib.Path(args.workspace)
    artifacts = pathlib.Path(args.artifacts)

    if not workspace.exists():
        print(f"ERROR [WORKSPACE_MISSING] {workspace}", file=sys.stderr)
        return 2

    if not artifacts.exists():
        print(f"ERROR [ARTIFACTS_MISSING] {artifacts}", file=sys.stderr)
        return 2

    reason = args.reason.strip()
    if not reason:
        print("ERROR [REASON_EMPTY] --reason must be non-empty", file=sys.stderr)
        return 2

    print(f"Deferring rule {args.rule_id}: {reason}")

    exit_code, modified = defer_rule(workspace, artifacts, args.rule_id, reason)

    now = iso_now()
    deferred_artifact = {
        "rule_id": args.rule_id,
        "reason": reason,
        "files_modified": len(modified),
        "flags_rewritten": len(modified),
        "files": modified,
        "deferred_at": now,
    }

    # Count total flags from the existing batch artifact for accuracy
    batch_path = artifacts / f"05-rule-batch-{args.rule_id}.json"
    if batch_path.exists():
        try:
            batch = read_json(batch_path)
            deferred_artifact["flags_rewritten"] = batch.get(
                "total_files", len(modified)
            )
        except (json.JSONDecodeError, OSError):
            deferred_artifact["flags_rewritten"] = len(modified)

    deferred_path = artifacts / f"05-deferred-{args.rule_id}.json"
    write_json(deferred_path, deferred_artifact)

    print(
        f"Deferred {deferred_artifact['flags_rewritten']} flag(s) in "
        f"{len(modified)} file(s) for rule {args.rule_id} -> {deferred_path}"
    )

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
