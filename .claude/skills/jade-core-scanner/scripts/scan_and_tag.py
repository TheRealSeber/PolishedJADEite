#!/usr/bin/env python3
"""JADE Scanner — Deterministic source tagger.

Reads a breaking-changes manifest, walks a workspace, matches rule patterns
against source lines via regex, and injects inline comment markers (e.g.
``// JADE-FLAG:<rule_id>`` for ``.java``, ``<!-- JADE-FLAG:... -->`` for
``.xml``, ``# JADE-FLAG:...`` for ``.properties``) exactly once per match.
Fully idempotent — re-running never creates duplicate flags.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import os
import pathlib
import re
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Comment-syntax helpers — extension-aware
# ---------------------------------------------------------------------------

_COMMENT_SYNTAX: Dict[str, Tuple[str, str]] = {
    ".java": ("// ", ""),
    ".xml": ("<!-- ", " -->"),
    ".properties": ("# ", ""),
    ".py": ("# ", ""),
    ".yaml": ("# ", ""),
    ".yml": ("# ", ""),
}
"""Map file extension to (prefix, suffix) for inline flag comments.

Prefix and suffix are appended/prepended so the resulting line is a
valid comment in the target file format.  The suffix should include a
trailing space if the comment style requires it before newline.
"""

_DEFAULT_COMMENT = ("# ", "")


def _comment_syntax(ext: str) -> Tuple[str, str]:
    """Return (prefix, suffix) comment markers for *ext* (lowercased)."""
    return _COMMENT_SYNTAX.get(ext.lower(), _DEFAULT_COMMENT)


def _flag_pattern_for_ext(ext: str) -> re.Pattern:
    """Build a regex that detects an existing ``JADE-FLAG`` comment for *ext*."""
    prefix, _ = _comment_syntax(ext)
    # Escape the prefix for use in a regex
    escaped = re.escape(prefix.strip())
    return re.compile(rf"^\s*{escaped}\s*JADE-FLAG:\s*(\S+)")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXCLUSION_GLOBS: List[str] = [
    ".git",
    ".svn",
    "node_modules",
    "__pycache__",
    "*.class",
    "*.jar",
    "*.war",
    "*.zip",
    "*.tar",
    "*.gz",
    "target",
    "build",
    "out",
    "bin",
]
"""Directory / file globs that the walker always skips."""


# ---------------------------------------------------------------------------
# Small helpers
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


def write_json_atomic(path: pathlib.Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class PatternDef:
    """A single pattern inside a manifest rule."""

    def __init__(self, raw: Dict[str, Any]) -> None:
        self.type: str = raw.get("type", "regex")
        if self.type != "regex":
            raise ValueError(f"Unsupported pattern type: {self.type}")
        self.pattern_str: str = raw["pattern"]
        if not self.pattern_str.strip():
            raise ValueError(
                "Empty pattern string — skipping rule (would match every line)"
            )
        self.compiled: re.Pattern = re.compile(raw["pattern"])
        self.target_extensions: List[str] = raw.get("target_extensions", [".java"])
        self.reason: str = raw.get("reason", "")
        self.confidence: str = raw.get("confidence", "MEDIUM")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "pattern": self.pattern_str,
            "target_extensions": self.target_extensions,
            "reason": self.reason,
            "confidence": self.confidence,
        }


class RuleDef:
    """A single rule in the manifest."""

    def __init__(self, raw: Dict[str, Any]) -> None:
        self.id: str = raw["id"]
        self.name: str = raw.get("name", raw["id"])
        self.severity: str = raw.get("severity", "MEDIUM")
        self.patterns: List[PatternDef] = [
            PatternDef(p) for p in raw.get("patterns", [])
        ]

    def extensions(self) -> Set[str]:
        exts: Set[str] = set()
        for pat in self.patterns:
            exts.update(pat.target_extensions)
        return exts

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "severity": self.severity,
            "patterns": [p.to_dict() for p in self.patterns],
        }


class FlagEntry:
    """One injected flag, serialised into 04-flag-index.json."""

    def __init__(
        self, rule_id: str, file: str, line: int, confidence: str, reason: str
    ) -> None:
        self.rule_id = rule_id
        self.file = file
        self.line = line
        self.confidence = confidence
        self.reason = reason

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "file": self.file,
            "line": self.line,
            "confidence": self.confidence,
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------


def load_manifest(artifacts: pathlib.Path) -> Tuple[List[RuleDef], List[RuleDef]]:
    """Load manifest and optional linter findings.

    Returns (user_rules, linter_rules).  Linter rules get a ``LINT:`` prefix.
    """
    manifest_path = artifacts / "01-breaking-changes-manifest.json"
    if not manifest_path.exists():
        print(f"ERROR [MANIFEST_MISSING] {manifest_path}", file=sys.stderr)
        sys.exit(2)

    raw = read_json(manifest_path)
    rules: List[RuleDef] = []
    for entry in raw.get("rules", []):
        if not isinstance(entry, dict):
            continue
        rules.append(RuleDef(entry))

    linter_rules: List[RuleDef] = []
    linter_path = artifacts / "02-linter-findings.json"
    if linter_path.exists():
        linter_raw = read_json(linter_path)
        for entry in linter_raw.get("rules", []):
            if not isinstance(entry, dict):
                continue
            entry["id"] = f"LINT:{entry['id']}"
            linter_rules.append(RuleDef(entry))

    return rules, linter_rules


# ---------------------------------------------------------------------------
# File walking
# ---------------------------------------------------------------------------


def _is_excluded(rel_path: str) -> bool:
    for glob in EXCLUSION_GLOBS:
        if fnmatch.fnmatch(rel_path, glob) or fnmatch.fnmatch(
            rel_path, f"*{os.sep}{glob}{os.sep}*"
        ):
            return True
        parts = rel_path.replace("\\", "/").split("/")
        if glob in parts:
            return True
    return False


def collect_candidate_files(
    workspace: pathlib.Path, all_extensions: Set[str]
) -> List[pathlib.Path]:
    """Walk workspace and return files whose extension is in *all_extensions*."""
    candidates: List[pathlib.Path] = []
    for root, dirs, files in os.walk(workspace):
        rel_root = os.path.relpath(root, workspace)
        if rel_root == ".":
            rel_root = ""
        dirs[:] = [d for d in dirs if not _is_excluded(os.path.join(rel_root, d))]
        for fn in files:
            rel = os.path.join(rel_root, fn)
            if _is_excluded(rel):
                continue
            ext = os.path.splitext(fn)[1]
            if ext in all_extensions:
                candidates.append(pathlib.Path(root) / fn)
    return candidates


# ---------------------------------------------------------------------------
# Idempotent injection
# ---------------------------------------------------------------------------


def _flag_exists(
    lines: List[str], match_line_idx: int, rule_id: str, file_ext: str
) -> bool:
    """Return True if a flag for *rule_id* already exists among the consecutive
    ``JADE-FLAG:`` lines immediately following *match_line_idx*.

    Comment syntax is selected based on *file_ext* (e.g. ``.java``, ``.xml``).
    """
    target = f"JADE-FLAG:{rule_id}"
    flag_re = _flag_pattern_for_ext(file_ext)
    for offset in range(1, 51):
        idx = match_line_idx + offset
        if idx >= len(lines):
            return False
        stripped = lines[idx].strip()
        if flag_re.match(stripped):
            if target in stripped:
                return True
        elif stripped:
            return False
    return False


def _format_flag_line(rule_id: str, reason: str, confidence: str, file_ext: str) -> str:
    """Format a flag injection line using the correct comment syntax for *file_ext*."""
    prefix, suffix = _comment_syntax(file_ext)
    return f"{prefix}JADE-FLAG:{rule_id} {reason} {confidence}{suffix}\n"


def _comment_skip_prefixes(ext: str) -> Tuple[str, ...]:
    """Return tuple of comment-start strings to skip when scanning *ext* files."""
    e = ext.lower()
    if e == ".java":
        return ("//", "/*", "*")
    if e == ".xml":
        return ("<!--",)
    if e in (".properties", ".py", ".yaml", ".yml"):
        return ("#",)
    return ("#", "//")


def scan_and_tag_file(
    file_path: pathlib.Path,
    rules: List[RuleDef],
    workspace: pathlib.Path,
) -> List[FlagEntry]:
    """Scan a single file, inject flags, return list of NEW flags.

    If no new flags are injected the file is left untouched (no write).
    """
    try:
        with file_path.open("r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except Exception:
        return []

    new_flags: List[FlagEntry] = []
    modified = False
    rel_path = str(file_path.relative_to(workspace)).replace("\\", "/")
    ext = file_path.suffix

    for rule in rules:
        for pattern in rule.patterns:
            allowed = {e.lower() for e in pattern.target_extensions}
            if ext.lower() not in allowed:
                continue

            compiled = pattern.compiled
            comment_prefixes = _comment_skip_prefixes(ext)
            # Iterate backwards so insertions do not shift subsequent indices.
            for i in range(len(lines) - 1, -1, -1):
                line = lines[i]
                stripped = line.strip()
                if stripped.startswith(comment_prefixes):
                    continue
                if compiled.search(line):
                    if _flag_exists(lines, i, rule.id, ext):
                        continue
                    flag_line = _format_flag_line(
                        rule.id, pattern.reason, pattern.confidence, ext
                    )
                    lines.insert(i + 1, flag_line)
                    modified = True
                    new_flags.append(
                        FlagEntry(
                            rule_id=rule.id,
                            file=rel_path,
                            line=(i + 1)
                            + 1,  # 1-based: insertion position + 1-based offset
                            confidence=pattern.confidence,
                            reason=pattern.reason,
                        )
                    )

    if modified:
        tmp = file_path.with_suffix(file_path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            fh.writelines(lines)
        tmp.replace(file_path)

    return new_flags


# ---------------------------------------------------------------------------
# Artifact writers
# ---------------------------------------------------------------------------


def build_flag_index(
    run_id: str,
    workspace_str: str,
    all_flags: List[FlagEntry],
    total_files_scanned: int = 0,
) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "generated_at": iso_now(),
        "workspace": workspace_str,
        "total_flags": len(all_flags),
        "total_files_scanned": total_files_scanned,
        "flags": [f.to_dict() for f in all_flags],
    }


def build_scan_summary(
    run_id: str,
    workspace_str: str,
    total_files_scanned: int,
    all_flags: List[FlagEntry],
    idempotent_skips: int,
    elapsed: float,
    rules: List[RuleDef],
) -> Dict[str, Any]:
    by_rule: Dict[str, Dict[str, Any]] = {}
    by_confidence: Dict[str, int] = {}
    for flag in all_flags:
        by_rule.setdefault(
            flag.rule_id,
            {"name": flag.rule_id, "severity": "UNKNOWN", "count": 0},
        )["count"] += 1
        by_confidence[flag.confidence] = by_confidence.get(flag.confidence, 0) + 1

    # Merge rule metadata (name, severity) from manifest
    for rule in rules:
        if rule.id in by_rule:
            by_rule[rule.id]["name"] = rule.name
            by_rule[rule.id]["severity"] = rule.severity

    return {
        "run_id": run_id,
        "generated_at": iso_now(),
        "workspace": workspace_str,
        "total_files_scanned": total_files_scanned,
        "total_new_flags": len(all_flags),
        "idempotent_skips": idempotent_skips,
        "elapsed_seconds": round(elapsed, 2),
        "by_rule": by_rule,
        "by_confidence": by_confidence,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="JADE deterministic source scanner")
    parser.add_argument(
        "--workspace",
        required=True,
        help="Path to workspace directory containing source files",
    )
    parser.add_argument(
        "--artifacts",
        required=True,
        help="Path to artifacts directory (reads manifest, writes outputs)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs only — do not modify files or write artifacts",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Override run_id (default: read from 00-run-config.json or use workspace dirname)",
    )
    args = parser.parse_args()

    workspace = pathlib.Path(args.workspace).resolve()
    artifacts = pathlib.Path(args.artifacts).resolve()

    # ------------------------------------------------------------------
    # Validate
    # ------------------------------------------------------------------
    if not workspace.is_dir():
        print(f"ERROR [WORKSPACE_MISSING] {workspace}", file=sys.stderr)
        return 2
    if not artifacts.is_dir():
        print(f"ERROR [ARTIFACTS_MISSING] {artifacts}", file=sys.stderr)
        return 2

    # Determine run_id
    run_id = args.run_id
    if not run_id:
        config_path = artifacts / "00-run-config.json"
        if config_path.exists():
            cfg = read_json(config_path)
            run_id = cfg.get("run_id", workspace.name)
        else:
            run_id = workspace.name

    # Load rules
    user_rules, linter_rules = load_manifest(artifacts)
    all_rules = user_rules + linter_rules
    if not all_rules:
        # No rules → write empty artifacts and exit clean
        if not args.dry_run:
            write_json_atomic(
                artifacts / "04-flag-index.json",
                build_flag_index(run_id, str(args.workspace), []),
            )
            write_json_atomic(
                artifacts / "04-scan-summary.json",
                {
                    "run_id": run_id,
                    "generated_at": iso_now(),
                    "workspace": str(args.workspace),
                    "total_files_scanned": 0,
                    "total_new_flags": 0,
                    "idempotent_skips": 0,
                    "elapsed_seconds": 0.0,
                    "by_rule": {},
                    "by_confidence": {},
                },
            )
            print("No rules in manifest — wrote empty artifacts.")
        return 0

    # Collect candidate extensions
    all_extensions: Set[str] = set()
    for rule in all_rules:
        all_extensions.update(rule.extensions())
    # Normalise to lowercase
    all_extensions = {e.lower() for e in all_extensions}

    if args.dry_run:
        candidates = collect_candidate_files(workspace, all_extensions)
        print(
            f"DRY-RUN OK | workspace={workspace} | rules={len(all_rules)} "
            f"| extensions={all_extensions} | candidate_files={len(candidates)}"
        )
        return 0

    # ------------------------------------------------------------------
    # Scan
    # ------------------------------------------------------------------
    t0 = time.monotonic()

    candidates = collect_candidate_files(workspace, all_extensions)

    all_flags: List[FlagEntry] = []
    for fp in candidates:
        flags = scan_and_tag_file(fp, all_rules, workspace)
        all_flags.extend(flags)

    elapsed = time.monotonic() - t0

    # Idempotent skips are impossible to know precisely without a second
    # pass.  We report 0 here; a second run that produces zero new flags
    # confirms idempotency.
    idempotent_skips = 0

    # ------------------------------------------------------------------
    # Write artifacts
    # ------------------------------------------------------------------
    flag_index = build_flag_index(
        run_id, str(args.workspace), all_flags, total_files_scanned=len(candidates)
    )
    write_json_atomic(artifacts / "04-flag-index.json", flag_index)

    summary = build_scan_summary(
        run_id=run_id,
        workspace_str=str(args.workspace),
        total_files_scanned=len(candidates),
        all_flags=all_flags,
        idempotent_skips=idempotent_skips,
        elapsed=elapsed,
        rules=all_rules,
    )
    write_json_atomic(artifacts / "04-scan-summary.json", summary)

    print(
        f"SCAN COMPLETE | files_scanned={len(candidates)} | flags_injected={len(all_flags)} | elapsed={elapsed:.2f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
