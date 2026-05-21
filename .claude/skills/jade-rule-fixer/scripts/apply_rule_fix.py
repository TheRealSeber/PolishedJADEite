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


def apply_file_transform(
    file_path: pathlib.Path, edit_fn
) -> Tuple[str, int, List[str]]:
    """Load file, apply edit_fn(lines) -> lines, atomically write back.

    edit_fn receives List[str] and returns (changed_lines, changes_count, warnings).
    Returns (status, changes_made, warnings).
    """
    content = file_path.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    lines, changes, warnings = edit_fn(lines)
    if changes > 0:
        new_content = "".join(lines)
        atomic_file_write(file_path, new_content)
        return "FIXED", changes, warnings
    return "NOOP", 0, warnings


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


def infer_generic_type(lines: List[str], var_name: str) -> Optional[str]:
    """Infer type parameter for a raw collection variable.

    Scans lines for:
    1. .add(x) calls → type of x
    2. .put(k, v) calls → Map<K, V> semantic
    3. Cast expressions from .get() → the cast type

    Returns the inferred type string (e.g. 'String', 'Object', 'String,Object' for Map)
    or None if ambiguous.
    """
    add_types: List[str] = []
    get_cast_types: List[str] = []

    for line in lines:
        # .add(something)
        add_match = re.search(rf"\b{re.escape(var_name)}\.add\(\s*(.+?)\s*\)", line)
        if add_match:
            arg = add_match.group(1).strip()
            add_types.append(_resolve_arg_type(arg, lines))

        # .put(key, value)
        put_match = re.search(
            rf"\b{re.escape(var_name)}\.put\(\s*(.+?)\s*,\s*(.+?)\s*\)", line
        )
        if put_match:
            key_type = _resolve_arg_type(put_match.group(1).strip(), lines)
            val_type = _resolve_arg_type(put_match.group(2).strip(), lines)
            if key_type or val_type:
                return f"{key_type or 'Object'},{val_type or 'Object'}"

        # (Type) var.get(i) — cast from get
        cast_match = re.search(
            rf"\((\w+(?:<.*?>)?)\)\s*{re.escape(var_name)}\.get", line
        )
        if cast_match:
            get_cast_types.append(cast_match.group(1))

    # Merge inferences
    all_types = add_types + get_cast_types
    unique_types = list(dict.fromkeys(t for t in all_types if t and t != "null"))

    if not unique_types:
        return None  # ambiguous, use Object
    if len(unique_types) == 1:
        return unique_types[0]

    # Multiple types found — pick most specific common supertype
    if all(t == "String" for t in unique_types):
        return "String"
    return "Object"


def _resolve_arg_type(arg: str, lines: List[str]) -> str:
    """Resolve a simple argument expression to a Java type name.

    Heuristics:
    - "string literal" → String
    - variable name matching a known typed variable → try to find its declaration
    - null → None
    - new Xxx() → Xxx
    - method call → Object (can't infer)
    """
    arg = arg.strip().rstrip(";")

    if not arg or arg == "null":
        return "null"

    # String literal
    if arg.startswith('"') or arg.startswith("'"):
        return "String"

    # Numeric literal
    if re.match(r"^-?\d+(\.\d+)?[fFlLdD]?$", arg):
        return "Integer"

    # Boolean literal
    if arg in ("true", "false"):
        return "Boolean"

    # Constructor call: new Foo(...)
    new_match = re.match(r"new\s+(\w+)\s*\(", arg)
    if new_match:
        return new_match.group(1)

    # Single word = variable name. Try to find its declaration.
    if re.match(r"^\w+$", arg):
        for line in lines:
            decl = re.search(rf"\b(\w+(?:<.*?>)?)\s+{re.escape(arg)}\s*[=;]", line)
            if decl:
                return decl.group(1)
        return arg  # can't resolve, return as-is

    return "Object"


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


def _infer_collection_element_type(lines: List[str], coll_var: str) -> str:
    """Infer element type from collection declaration."""
    for line in lines:
        decl = re.search(rf"(\w+(?:<(\w+)>)?)\s+{re.escape(coll_var)}\s*=", line)
        if decl:
            inner = decl.group(2)
            if inner:
                return inner
            return "Object"
    return "Object"


def apply_raw_types_fix(
    file_path: pathlib.Path,
    flagged_lines: List[int],
) -> Tuple[str, int, List[str]]:
    """Transform raw collection instantiations in a file.

    For each flagged line containing 'new Vector()' etc.:
    1. Find the variable name being assigned
    2. Scan the method/class for .add() / .put() calls to that variable
    3. Infer type parameter
    4. Replace 'new Vector()' → 'new Vector<Foo>()'
    5. Remove safe casts from subsequent .get() calls

    Returns (status, changes_made, warnings).
    """

    def _raw_types_editor(lines: List[str]) -> Tuple[List[str], int, List[str]]:
        changes = 0
        warnings: List[str] = []

        for flagged_line_num in flagged_lines:
            idx = flagged_line_num - 1
            if idx < 0 or idx >= len(lines):
                continue

            line = lines[idx]

            # Match: Type varName = new Collection();
            match = re.match(
                r"^(\s*)(\w+)\s+(\w+)\s*=\s*new\s+(Vector|ArrayList|HashMap|Hashtable|LinkedList|HashSet)\s*\(\s*\)\s*;",
                line,
            )
            if not match:
                # Try without variable declaration (just new Foo())
                match = re.match(
                    r"(.*?)new\s+(Vector|ArrayList|HashMap|Hashtable|LinkedList|HashSet)\s*\(\s*\)",
                    line,
                )
                if not match:
                    continue

            indent = match.group(1) if "(" not in match.group(1) else ""
            var_name = (
                match.group(3) if match.lastindex and match.lastindex >= 3 else None
            )
            coll_type = (
                match.group(4)
                if match.lastindex and match.lastindex >= 4
                else match.group(2)
            )

            # Infer type
            inferred = "Object"
            if var_name:
                result = infer_generic_type(lines, var_name)
                if result:
                    inferred = result

            # Build replacement
            if var_name:
                replacement = f"{indent}{coll_type}<{inferred}> {var_name} = new {coll_type}<{inferred}>();"
                lines[idx] = replacement + "\n"
                changes += 1
            else:
                # Inline: new Vector() → new Vector<Object>()
                old = match.group(0)
                new = old.replace(
                    f"new {coll_type}()", f"new {coll_type}<{inferred}>()"
                )
                lines[idx] = line.replace(old, new, 1)
                changes += 1

            # Best-effort cast removal for .get() calls
            if var_name:
                for ci in range(idx + 1, len(lines)):
                    cast_match = re.search(
                        rf"\((\w+(?:<.*?>)?)\)\s*\b{re.escape(var_name)}\.get\(",
                        lines[ci],
                    )
                    if cast_match:
                        cast_type = cast_match.group(1)
                        if cast_type == inferred or inferred == "Object":
                            # Safe to remove cast: "(Type) var.get(i)" → "var.get(i)"
                            lines[ci] = re.sub(
                                rf"\((\w+(?:<.*?>)?)\)\s*({re.escape(var_name)}\.get\()",
                                r"\2",
                                lines[ci],
                            )

        return lines, changes, warnings

    return apply_file_transform(file_path, _raw_types_editor)


def apply_enhanced_for_fix(
    file_path: pathlib.Path,
    flagged_lines: List[int],
) -> Tuple[str, int, List[str]]:
    """Convert safe indexed for-loops to enhanced for-loops.

    Safety checks:
    - Index used ONLY for .get(i) or array[i]
    - No .remove(i), .set(i, x), .add(i, x) inside loop
    - Not iterating two parallel collections
    - No backwards loop or step > 1

    Returns (status, changes_made, warnings).
    """

    def _enhanced_for_editor(lines: List[str]) -> Tuple[List[str], int, List[str]]:
        changes = 0
        warnings: List[str] = []

        for flagged_line_num in flagged_lines:
            idx = flagged_line_num - 1
            if idx < 0 or idx >= len(lines):
                continue

            line = lines[idx]

            # Match: for (int i = 0; i < coll.size(); i++) {
            match = re.match(
                r"^(\s*)for\s*\(\s*int\s+(\w+)\s*=\s*0\s*;\s*\2\s*<\s*(\w+)\.size\(\)\s*;\s*\2\+\+\s*\)\s*\{",
                line,
            )
            if not match:
                # Try array variant: for (int i = 0; i < arr.length; i++) {
                match = re.match(
                    r"^(\s*)for\s*\(\s*int\s+(\w+)\s*=\s*0\s*;\s*\2\s*<\s*(\w+)\.length\s*;\s*\2\+\+\s*\)\s*\{",
                    line,
                )
                if not match:
                    continue

            indent = match.group(1)
            idx_var = match.group(2)
            coll_var = match.group(3)

            # Find loop body (matching braces)
            loop_start = idx
            brace_count = 1
            loop_end = loop_start
            for bi in range(loop_start + 1, len(lines)):
                brace_count += lines[bi].count("{") - lines[bi].count("}")
                if brace_count == 0:
                    loop_end = bi
                    break

            if loop_end == loop_start:
                warnings.append(
                    f"Line {flagged_line_num}: could not find loop closing brace, skipping"
                )
                continue

            # Safety checks on loop body
            body_lines = lines[loop_start + 1 : loop_end]
            body_text = "".join(body_lines)
            is_safe = True
            skip_reasons: List[str] = []

            # Check for .remove(i), .set(i), .add(i)
            if re.search(
                rf"\.(remove|set|add)\s*\(\s*{re.escape(idx_var)}\s*[,\)]", body_text
            ):
                skip_reasons.append(f".remove/set/add using {idx_var}")
                is_safe = False

            # Check for index used after loop
            after_text = "".join(lines[loop_end + 1 :])
            if re.search(rf"\b{re.escape(idx_var)}\b", after_text):
                skip_reasons.append(f"{idx_var} used after loop")
                is_safe = False

            # Check for parallel collection iteration
            if re.search(rf"\b{re.escape(idx_var)}\s*\]", body_text) and re.search(
                rf"\.get\s*\(\s*{re.escape(idx_var)}\s*\)", body_text
            ):
                skip_reasons.append(f"parallel iteration with {idx_var}")
                is_safe = False

            # Check for backwards loop
            if "--" in line:
                skip_reasons.append("backwards loop")
                is_safe = False

            if not is_safe:
                reason = "; ".join(skip_reasons)
                lines[idx] = lines[idx].rstrip("\n") + f" // MIGRATION-SKIP: {reason}\n"
                changes += 1
                warnings.append(f"Line {flagged_line_num}: skipped ({reason})")
                continue

            # Determine element type
            elem_type = _infer_collection_element_type(lines, coll_var)

            # Build enhanced-for
            loop_var = "item" if idx_var == "i" else f"elem_{idx_var}"
            new_for = f"{indent}for ({elem_type} {loop_var} : {coll_var}) {{"
            lines[idx] = new_for + "\n"

            # Replace arr[idx], (Type) coll.get(idx), and coll.get(idx) with loop_var
            for bi in range(idx + 1, loop_end + 1):
                # Replace arr[idx] with loop_var (array element access)
                array_pattern = (
                    rf"\b{re.escape(coll_var)}\s*\[\s*{re.escape(idx_var)}\s*\]"
                )
                lines[bi] = re.sub(array_pattern, loop_var, lines[bi])
                # Replace cast-get: (Type) coll.get(idx)
                cast_pattern = rf"\((\w+(?:<.*?>)?)\)\s*{re.escape(coll_var)}\.get\s*\(\s*{re.escape(idx_var)}\s*\)"
                lines[bi] = re.sub(cast_pattern, loop_var, lines[bi])
                # Replace plain get: coll.get(idx)
                get_pattern = (
                    rf"{re.escape(coll_var)}\.get\s*\(\s*{re.escape(idx_var)}\s*\)"
                )
                lines[bi] = re.sub(get_pattern, loop_var, lines[bi])

            changes += 1

        return lines, changes, warnings

    return apply_file_transform(file_path, _enhanced_for_editor)


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

    # Rule-specific transforms (runs after generic fix plan, before file apply)
    transform_applied = False
    if status == "FIXED":
        try:
            if rule_id == "RAW_TYPES":
                flagged = [line_start]
                fix_status, changes, fix_warnings = apply_raw_types_fix(
                    file_path, flagged
                )
                warnings.extend(fix_warnings)
                if fix_status == "FIXED":
                    transform_applied = True
                else:
                    warnings.append(
                        "RAW_TYPES transform produced no changes (falling back to generic)"
                    )
            elif rule_id == "ENHANCED_FOR":
                flagged = [line_start]
                fix_status, changes, fix_warnings = apply_enhanced_for_fix(
                    file_path, flagged
                )
                warnings.extend(fix_warnings)
                if fix_status == "FIXED":
                    transform_applied = True
                else:
                    warnings.append(
                        "ENHANCED_FOR transform produced no changes (falling back to generic)"
                    )
        except Exception as exc:
            errors.append(f"Rule-specific transform failed: {exc}")
            status = "FAILED"

    # When a rule-specific transform already wrote the file, skip generic apply
    if transform_applied and replacement is not None:
        replacement = region  # no-op the generic apply

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
