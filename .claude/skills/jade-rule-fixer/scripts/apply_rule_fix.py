#!/usr/bin/env python3
"""apply_rule_fix.py — apply one rule fix to one file from a rule batch task.

Inputs:
    artifacts/05-rule-batch-{rule_id}.json  — task entry list
    artifacts/01-breaking-changes-manifest.json  — rule definitions

Outputs:
    artifacts/06-fix-result-{task_id}.json  — per-task fix record
    Modified workspace file (atomic tmp+replace)

Exit codes:
    0 — FIXED or NEEDS_REVIEW (fix applied successfully)
    2 — FAILED (halt — fix could not be applied)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NEEDS_REVIEW_CONFIDENCE_THRESHOLD = 0.85
TMP_FILE_SUFFIX = ".tmp.fix"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def iso_now() -> str:
    """Return current UTC time in ISO-8601 compact format (Z suffix)."""
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def read_json(path: pathlib.Path) -> Dict:
    """Read a JSON file, returning the parsed dict."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json_atomic(path: pathlib.Path, payload: Dict) -> None:
    """Write JSON to a temp file, then atomically rename onto *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + TMP_FILE_SUFFIX)
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def atomic_file_write(file_path: pathlib.Path, content: str) -> None:
    """Write *content* to a temp sibling, then atomically replace the target."""
    tmp = file_path.with_name(file_path.name + TMP_FILE_SUFFIX)
    with tmp.open("w", encoding="utf-8") as f:
        f.write(content)
    tmp.replace(file_path)


def exit_fail(code: str, message: str) -> int:
    """Print error to stderr and return exit code 2."""
    print(f"ERROR [{code}] {message}", file=sys.stderr)
    return 2


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def load_task(
    batch_path: pathlib.Path, task_id: str
) -> Tuple[Optional[Dict], Optional[str]]:
    """Load the task entry with *task_id* from the batch file.

    Returns (task_dict, None) on success or (None, error_message).
    """
    if not batch_path.exists():
        return None, f"Batch file not found: {batch_path}"
    try:
        batch = read_json(batch_path)
    except (json.JSONDecodeError, OSError) as exc:
        return None, f"Failed to parse batch file: {exc}"

    tasks: List[Dict] = batch.get("tasks", [])
    if not isinstance(tasks, list):
        return None, "Batch file 'tasks' field is not a list"

    for task in tasks:
        if task.get("task_id") == task_id:
            return task, None

    return None, f"Task {task_id} not found in {batch_path}"


def load_rule(
    manifest_path: pathlib.Path, rule_id: str
) -> Tuple[Optional[Dict], Optional[str]]:
    """Load the rule entry with *rule_id* from the breaking-changes manifest.

    Returns (rule_dict, None) on success or (None, error_message).
    """
    if not manifest_path.exists():
        return None, f"Manifest file not found: {manifest_path}"
    try:
        manifest = read_json(manifest_path)
    except (json.JSONDecodeError, OSError) as exc:
        return None, f"Failed to parse manifest: {exc}"

    rules: List[Dict] = manifest.get("rules", [])
    if not isinstance(rules, list):
        return None, "Manifest 'rules' field is not a list"

    for rule in rules:
        if rule.get("rule_id") == rule_id:
            return rule, None

    return None, f"Rule {rule_id} not found in {manifest_path}"


def compute_confidence(
    rule_confidence: float, match_count: int, match_context: str
) -> float:
    """Compute final confidence from rule confidence and match quality.

    *match_context* is a free-text summary of the match situation used to
    detect ambiguity hints (e.g. "multiple matches", "ambiguous context").
    """
    if match_count == 1:
        quality = 1.0
    elif match_count == 0:
        quality = 0.0
    else:
        quality = 0.8

    if "ambiguous" in match_context.lower():
        quality = min(quality, 0.6)

    return round(rule_confidence * quality, 4)


def should_needs_review(
    final_confidence: float,
    match_count: int,
    fix_strategy: str,
    rule_category: str,
    diff_spill: bool,
    file_content: str,
) -> bool:
    """Return True when the result should be NEEDS_REVIEW instead of FIXED."""
    if final_confidence < NEEDS_REVIEW_CONFIDENCE_THRESHOLD:
        return True
    if match_count > 1:
        return True
    if fix_strategy and any(
        keyword in fix_strategy.lower() for keyword in ("manual", "review")
    ):
        return True
    if rule_category == "BEHAVIOR_CHANGE":
        return True
    if diff_spill:
        return True
    if "MIGRATION-SKIP" in file_content:
        return True
    return False


def extract_flagged_region(
    lines: List[str], line_start: int, line_end: int
) -> Tuple[str, str, str]:
    """Split file content into *before*, *region*, and *after* strings.

    Values are 1-based, inclusive.
    Returns (before, region, after) where *region* is the flagged slice.
    """
    total = len(lines)
    before_idx = max(0, line_start - 1)
    after_idx = min(total, line_end)

    # region lines inclusive (1-based → 0-based slice)
    before = "".join(lines[:before_idx])
    region = "".join(lines[before_idx:after_idx])
    after = "".join(lines[after_idx:])
    return before, region, after


def plan_fix(
    rule: Dict, region_text: str, line_start: int, line_end: int
) -> Tuple[Optional[str], Optional[str], int, str]:
    """Apply match_pattern to region and generate replacement.

    Returns (replacement_text, error, match_count, match_context).
    """
    match_pattern = rule.get("match_pattern", "")
    fix_strategy = rule.get("fix_strategy", "")

    if not match_pattern:
        return None, "Rule has no match_pattern", 0, ""

    try:
        regex = re.compile(match_pattern, re.MULTILINE)
    except re.error as exc:
        return None, f"Invalid regex in match_pattern: {exc}", 0, ""

    matches = list(regex.finditer(region_text))
    match_count = len(matches)

    if match_count == 0:
        return (
            None,
            f"match_pattern did not match anything in flagged region "
            f"(lines {line_start}-{line_end})",
            0,
            "no match",
        )

    # Build replacement using fix_strategy
    if match_count > 1:
        match_context = f"multiple matches ({match_count})"
    else:
        match_context = "single match"

    # Resolve fix_strategy: if it is a JSON template {"replace": ..., "with": ...}
    replacement = _resolve_fix_strategy(fix_strategy, region_text, matches)

    return replacement, None, match_count, match_context


def _resolve_fix_strategy(
    fix_strategy: str,
    region_text: str,
    matches: List[re.Match],
) -> Optional[str]:
    """Resolve the fix_strategy into a replacement region_text.

    Supports:
    - Structured JSON template: {"replace": "pattern", "with": "replacement"}
    - Python function-style: uses re.sub semantics when fix_strategy looks
      like a sed expression s/pattern/replacement/flags.
    - Plain string instruction: returned as-is for manual resolution.
    """
    # Try JSON template
    try:
        template = json.loads(fix_strategy)
        if isinstance(template, dict):
            replace_pattern = template.get("replace", "")
            with_text = template.get("with", "")
            if replace_pattern:
                return re.sub(
                    replace_pattern, with_text, region_text, flags=re.MULTILINE
                )
    except (json.JSONDecodeError, TypeError):
        pass

    # Try sed-style s/pattern/replace/flags
    sed_match = re.match(r"^s/(.+)/(.*)/([gimsuUxA]*)$", fix_strategy)
    if sed_match:
        pattern_str = sed_match.group(1)
        replacement_str = sed_match.group(2)
        flags_str = sed_match.group(3)
        flags = 0
        if "i" in flags_str:
            flags |= re.IGNORECASE
        if "m" in flags_str:
            flags |= re.MULTILINE
        if "s" in flags_str:
            flags |= re.DOTALL
        count = 0 if "g" in flags_str else 1
        return re.sub(
            pattern_str, replacement_str, region_text, count=count, flags=flags
        )

    # If fix_strategy is empty or just a description, we apply
    # match_pattern → the first capture group replacement semantics.
    # This falls through to the caller; the caller will use the first
    # match's group(0) as the basis.
    return None


def apply_fix(
    file_path: pathlib.Path,
    before: str,
    region: str,
    after: str,
    replacement: str,
) -> bool:
    """Write *before + replacement + after* atomically to *file_path*.

    Returns True on success, False on IO error.
    """
    new_content = before + replacement + after
    try:
        atomic_file_write(file_path, new_content)
        return True
    except OSError as exc:
        print(f"ERROR [IOError] Failed to write {file_path}: {exc}", file=sys.stderr)
        return False


def build_diff_summary(
    region: str, replacement: str, match_count: int, fix_strategy: str
) -> str:
    """Produce a compact diff summary string."""
    if replacement is None:
        return f"match_pattern matched {match_count} time(s); no replacement generated"
    if region == replacement:
        return "no change (region and replacement are identical)"
    removed = len(region) - len(replacement)
    if removed > 0:
        return f"replaced {len(region)}→{len(replacement)} chars ({removed} fewer)"
    elif removed < 0:
        return f"replaced {len(region)}→{len(replacement)} chars ({-removed} more)"
    else:
        return f"replaced {len(region)} chars (same length)"


def record_result(
    artifacts_dir: pathlib.Path,
    task_id: str,
    rule_id: str,
    file_rel: str,
    status: str,
    confidence: float,
    match_count: int,
    match_context: str,
    diff_summary: str,
    verification_hint: str,
    errors: List[str],
    warnings: List[str],
    line_start: int,
    line_end: int,
) -> pathlib.Path:
    """Write 06-fix-result-{task_id}.json and return its path."""
    result = {
        "task_id": task_id,
        "rule_id": rule_id,
        "file": file_rel,
        "status": status,
        "confidence": confidence,
        "match_count": match_count,
        "match_region": f"lines {line_start}-{line_end}",
        "match_context": match_context,
        "diff_summary": diff_summary,
        "verification_hint": verification_hint,
        "errors": errors,
        "warnings": warnings,
        "applied_at": iso_now(),
    }
    result_path = artifacts_dir / f"06-fix-result-{task_id}.json"
    write_json_atomic(result_path, result)
    return result_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply one rule fix to one file from a rule batch task.",
    )
    parser.add_argument(
        "--artifacts-dir",
        required=True,
        help="Path to the artifacts directory (e.g. migration-runs/sample/artifacts)",
    )
    parser.add_argument(
        "--rule-id",
        required=True,
        help="Rule identifier (e.g. BC-1.6-0001)",
    )
    parser.add_argument(
        "--task-id",
        required=True,
        help="Task identifier within the batch (e.g. BC-1.6-0001-0001)",
    )
    parser.add_argument(
        "--workspace-root",
        default=None,
        help="Workspace root directory (defaults to CWD). File paths are resolved relative to this.",
    )
    args = parser.parse_args()

    artifacts_dir = pathlib.Path(args.artifacts_dir)
    if not artifacts_dir.is_dir():
        print(
            f"ERROR [ARTIFACTS_DIR_MISSING] {artifacts_dir} is not a directory",
            file=sys.stderr,
        )
        return 2

    workspace_root = pathlib.Path(args.workspace_root or ".")
    if not workspace_root.is_dir():
        print(
            f"ERROR [WORKSPACE_MISSING] {workspace_root} is not a directory",
            file=sys.stderr,
        )
        return 2

    rule_id: str = args.rule_id
    task_id: str = args.task_id
    errors: List[str] = []
    warnings: List[str] = []

    # ---- PHASE 1: LOAD ----

    batch_path = artifacts_dir / f"05-rule-batch-{rule_id}.json"
    manifest_path = artifacts_dir / "01-breaking-changes-manifest.json"

    task, task_err = load_task(batch_path, task_id)
    if task_err:
        # Record failure even when task not found
        record_result(
            artifacts_dir,
            task_id,
            rule_id,
            file_rel="",
            status="FAILED",
            confidence=0.0,
            match_count=0,
            match_context="",
            diff_summary="",
            verification_hint="",
            errors=[task_err],
            warnings=[],
            line_start=0,
            line_end=0,
        )
        return exit_fail("LOAD_TASK_FAILED", task_err)

    assert task is not None

    file_rel = task.get("file", "")
    line_start = task.get("line_start", 0)
    line_end = task.get("line_end", 0)

    if not file_rel:
        record_result(
            artifacts_dir,
            task_id,
            rule_id,
            file_rel="",
            status="FAILED",
            confidence=0.0,
            match_count=0,
            match_context="",
            diff_summary="",
            verification_hint="",
            errors=["Task entry missing 'file' field"],
            warnings=[],
            line_start=line_start,
            line_end=line_end,
        )
        return exit_fail("LOAD_TASK_FAILED", "Task entry has no 'file' field")

    file_path = workspace_root / file_rel
    if not file_path.exists():
        record_result(
            artifacts_dir,
            task_id,
            rule_id,
            file_rel=file_rel,
            status="FAILED",
            confidence=0.0,
            match_count=0,
            match_context="",
            diff_summary="",
            verification_hint="",
            errors=[f"Target file not found: {file_path}"],
            warnings=[],
            line_start=line_start,
            line_end=line_end,
        )
        return exit_fail("FILE_NOT_FOUND", f"Target file not found: {file_path}")

    rule, rule_err = load_rule(manifest_path, rule_id)
    if rule_err:
        record_result(
            artifacts_dir,
            task_id,
            rule_id,
            file_rel=file_rel,
            status="FAILED",
            confidence=0.0,
            match_count=0,
            match_context="",
            diff_summary="",
            verification_hint="",
            errors=[rule_err],
            warnings=[],
            line_start=line_start,
            line_end=line_end,
        )
        return exit_fail("LOAD_RULE_FAILED", rule_err)

    assert rule is not None

    # ---- PHASE 2: MATCH ----

    try:
        raw_content = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        record_result(
            artifacts_dir,
            task_id,
            rule_id,
            file_rel=file_rel,
            status="FAILED",
            confidence=0.0,
            match_count=0,
            match_context="",
            diff_summary="",
            verification_hint=rule.get("verification_hint", ""),
            errors=[f"Failed to read file: {exc}"],
            warnings=[],
            line_start=line_start,
            line_end=line_end,
        )
        return exit_fail("FILE_READ_FAILED", str(exc))

    lines = raw_content.splitlines(keepends=True)

    if line_start < 1 or line_end < 1 or line_start > len(lines):
        record_result(
            artifacts_dir,
            task_id,
            rule_id,
            file_rel=file_rel,
            status="FAILED",
            confidence=0.0,
            match_count=0,
            match_context="",
            diff_summary="",
            verification_hint=rule.get("verification_hint", ""),
            errors=[
                f"Invalid line range {line_start}-{line_end} (file has {len(lines)} lines)"
            ],
            warnings=[],
            line_start=line_start,
            line_end=line_end,
        )
        return exit_fail(
            "INVALID_RANGE",
            f"Line range {line_start}-{line_end} out of bounds ({len(lines)} lines)",
        )

    before, region, after = extract_flagged_region(lines, line_start, line_end)

    # ---- PHASE 3: PLAN ----

    replacement, plan_err, match_count, match_context = plan_fix(
        rule, region, line_start, line_end
    )

    if plan_err:
        record_result(
            artifacts_dir,
            task_id,
            rule_id,
            file_rel=file_rel,
            status="FAILED",
            confidence=0.0,
            match_count=match_count,
            match_context=match_context,
            diff_summary="",
            verification_hint=rule.get("verification_hint", ""),
            errors=[plan_err],
            warnings=[],
            line_start=line_start,
            line_end=line_end,
        )
        return exit_fail("MATCH_FAILED", plan_err)

    # If fix_strategy did not resolve, fall back to using match_pattern
    # as a direct regex substitution on the region.
    if replacement is None:
        if match_count > 0:
            # Use the match_pattern itself as a direct substitution:
            # replace the matched text with nothing/empty.
            # This is a best-effort fallback; the caller should provide
            # a proper fix_strategy for production use.
            try:
                replacement = re.sub(
                    rule["match_pattern"], "", region, flags=re.MULTILINE
                )
            except re.error:
                replacement = region  # no change
            warnings.append(
                "fix_strategy did not resolve; applied match_pattern as direct "
                "substitution (this may not be correct — verify manually)"
            )
        else:
            replacement = region

    rule_confidence = float(rule.get("confidence", 0.7))
    final_confidence = compute_confidence(rule_confidence, match_count, match_context)

    # Check for diff spill
    diff_spill = False
    if replacement is not None:
        # Rough heuristic: if replacement adds or removes lines significantly,
        # check boundaries.
        reg_lines = region.splitlines(keepends=True)
        repl_lines = replacement.splitlines(keepends=True) if replacement else []
        diff_spill = abs(len(repl_lines) - len(reg_lines)) > 5

    needs_review = should_needs_review(
        final_confidence=final_confidence,
        match_count=match_count,
        fix_strategy=rule.get("fix_strategy", ""),
        rule_category=rule.get("category", ""),
        diff_spill=diff_spill,
        file_content=raw_content,
    )

    # ---- PHASE 4: APPLY ----

    status = "NEEDS_REVIEW" if needs_review else "FIXED"

    if replacement is not None and region != replacement:
        ok = apply_fix(file_path, before, region, after, replacement)
        if not ok:
            record_result(
                artifacts_dir,
                task_id,
                rule_id,
                file_rel=file_rel,
                status="FAILED",
                confidence=final_confidence,
                match_count=match_count,
                match_context=match_context,
                diff_summary="",
                verification_hint=rule.get("verification_hint", ""),
                errors=["Atomic file write failed"],
                warnings=warnings,
                line_start=line_start,
                line_end=line_end,
            )
            return exit_fail("WRITE_FAILED", "Atomic file write failed")
    else:
        if replacement is None:
            errors.append("No replacement generated; file unchanged")
            status = "FAILED"
        elif region == replacement:
            warnings.append("Region and replacement are identical; file unchanged")

    # ---- PHASE 5: RECORD ----

    diff_summary = build_diff_summary(
        region, replacement or "", match_count, rule.get("fix_strategy", "")
    )

    result_path = record_result(
        artifacts_dir,
        task_id,
        rule_id,
        file_rel=file_rel,
        status=status,
        confidence=final_confidence,
        match_count=match_count,
        match_context=match_context,
        diff_summary=diff_summary,
        verification_hint=rule.get("verification_hint", ""),
        errors=errors,
        warnings=warnings,
        line_start=line_start,
        line_end=line_end,
    )

    print(
        f"{status} | {task_id} | {file_rel} | confidence={final_confidence} | {diff_summary}"
    )
    print(f"Result written to {result_path}")

    return 0 if status in ("FIXED", "NEEDS_REVIEW") else 2


if __name__ == "__main__":
    raise SystemExit(main())
