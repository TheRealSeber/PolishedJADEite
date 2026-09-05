#!/usr/bin/env python3
"""jade-recipe-1.7-strings-in-switch — convert .equals() if-chains to switch.

Given --file and --line, reads the Java file and inspects the flagged if-statement.
Handles two patterns:
  A) Sequential if-return:  if(var.equals("X")) return ...; if(var.equals("Y")) return ...;
  B) If-else-if-else:       if(var.equals("X")){...} else if(var.equals("Y")){...} else{...}

If convertible (2+ branches), rewrites to switch. Otherwise defers by rewriting
JADE-FLAG → JADE-MODERNIZATION-DEFERRED. Atomic write via tmp-file + rename.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Optional

# shared/lib/java_source.py holds the comment/string-literal aware source
# classifier (contract owned by jade-core: classify_lines / is_live_code /
# strip_comments_and_strings). Resolve it relative to this file so the
# recipe works regardless of the caller's cwd.
_SHARED_LIB_DIR = pathlib.Path(__file__).resolve().parents[3] / "shared" / "lib"
if str(_SHARED_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_LIB_DIR))

import java_source  # noqa: E402  (path set up above)

# Match start of branch:  if (variableName.equals("literalString"))
_IF_EQUALS_RE = re.compile(
    r"^\s*if\s*\(\s*(\w+)\.equals\s*\(\s*\"((?:[^\"\\]|\\.)*)\"\s*\)\s*\)(\s*\{?)\s*$"
)

# Match: else if (variableName.equals("literalString"))
_ELSE_IF_EQUALS_RE = re.compile(
    r"^\s*else\s+if\s*\(\s*(\w+)\.equals\s*\(\s*\"((?:[^\"\\]|\\.)*)\"\s*\)\s*\)(\s*\{?)\s*$"
)

_ELSE_RE = re.compile(r"^\s*else\s*(\{?)\s*$")

_FLAG_RE = re.compile(r"//\s*JADE-FLAG:STRINGS_IN_SWITCH.*")

_JADE_COMMENT = "// JADE-FLAG:STRINGS_IN_SWITCH"
_DEFER_PREFIX = "// JADE-MODERNIZATION-DEFERRED:STRINGS_IN_SWITCH"
_DEFER_MSG = "(complex chain -- manual review recommended)"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _find_block_end(lines: list[str], start: int, has_brace: bool) -> int:
    """Return one-past-end index of a statement body starting at *start*.
    If *has_brace*, scans for matching close-brace. Otherwise scans for semicolon."""
    if has_brace:
        depth = 1
        i = start + 1
        while i < len(lines) and depth > 0:
            s = lines[i].rstrip("\n")
            depth += s.count("{") - s.count("}")
            i += 1
        return i
    else:
        i = start + 1
        while i < len(lines) and ";" not in lines[i]:
            i += 1
        return i + 1  # past the semicolon line


def _skip_ws_flags(lines: list[str], i: int) -> int:
    """Advance *i* past blank lines and JADE-FLAG lines."""
    while i < len(lines):
        s = lines[i].strip()
        if s == "" or _FLAG_RE.match(s):
            i += 1
            continue
        break
    return i


def _indent_of(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def _defer_flag(lines: list[str], flag_idx: int) -> list[str]:
    """Rewrite the JADE-FLAG at *flag_idx* to JADE-MODERNIZATION-DEFERRED."""
    lines[flag_idx] = lines[flag_idx].replace(_JADE_COMMENT, _DEFER_PREFIX, 1)
    if _DEFER_MSG not in lines[flag_idx]:
        lines[flag_idx] = lines[flag_idx].rstrip("\n") + f" {_DEFER_MSG}\n"
    return lines


# ---------------------------------------------------------------------------
# Chain scanning — Pattern A: sequential if-return
# ---------------------------------------------------------------------------
def _scan_sequential_if_return(
    lines: list[str], start_idx: int
) -> Optional[tuple[list[tuple[str, int]], int]]:
    """Try sequential if-return: if(v.equals("X")) return ...; if(v.equals("Y")) return ...

    Returns (branches [(literal, line_idx)], end_idx) or None."""
    branches: list[tuple[str, int]] = []
    var_name: Optional[str] = None
    i = start_idx

    while i < len(lines):
        s = lines[i].rstrip("\n")
        m = _IF_EQUALS_RE.match(s)
        if not m:
            break
        vn = m.group(1)
        if var_name is None:
            var_name = vn
        elif vn != var_name:
            break
        literal = m.group(2)
        has_brace = m.group(3).strip() == "{"

        # Check next non-flag line for a return/throw/break statement
        ni = _skip_ws_flags(lines, i + 1)
        if ni >= len(lines):
            break
        nxt = lines[ni].strip()
        if not (
            nxt.startswith("return ")
            or nxt.startswith("throw ")
            or nxt.startswith("break")
        ):
            # Body might be braced — scan for return inside
            if has_brace:
                body_end = _find_block_end(lines, i, True)
                body_lines = lines[i + 1 : body_end]
                body_text = "".join(body_lines)
                if "return" in body_text or "throw" in body_text:
                    branches.append((literal, i))
                    i = _skip_ws_flags(lines, body_end)
                    continue
            break

        branches.append((literal, i))

        if has_brace:
            i = _find_block_end(lines, i, True)
            i = _skip_ws_flags(lines, i)
        else:
            # Simple inline if; skip past the body line (return/throw/break) and flags
            body_start = _skip_ws_flags(lines, i + 1)
            # body_start is the return/throw/break line — advance past it
            i = _skip_ws_flags(lines, body_start + 1)

    if len(branches) < 2:
        return None
    return branches, i


# ---------------------------------------------------------------------------
# Chain scanning — Pattern B: if-else-if-else
# ---------------------------------------------------------------------------
def _scan_if_else_chain(
    lines: list[str], start_idx: int
) -> tuple[list[tuple[str, int]], Optional[int], Optional[int]]:
    """Try if-else-if-else chain starting at *start_idx*.
    Returns (branches [(literal, line_idx)], else_line_idx|None, end_idx|None)."""
    branches: list[tuple[str, int]] = []
    else_idx: Optional[int] = None

    m = _IF_EQUALS_RE.match(lines[start_idx].rstrip("\n"))
    if not m:
        return branches, None, None
    var_name = m.group(1)
    has_brace = m.group(3).strip() == "{"
    branches.append((m.group(2), start_idx))

    # Skip over first branch body
    i = _find_block_end(lines, start_idx, has_brace)
    i = _skip_ws_flags(lines, i)

    while i < len(lines):
        s = lines[i].rstrip("\n")
        em = _ELSE_IF_EQUALS_RE.match(s)
        if em and em.group(1) == var_name:
            branches.append((em.group(2), i))
            has_brace_e = em.group(3).strip() == "{"
            i = _find_block_end(lines, i, has_brace_e)
            i = _skip_ws_flags(lines, i)
            continue
        em = _ELSE_RE.match(s)
        if em:
            else_idx = i
            i = _find_block_end(lines, i, em.group(1) == "{")
            i = _skip_ws_flags(lines, i)
            break
        break

    if len(branches) < 2:
        return [], None, None
    return branches, else_idx, i


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="jade-recipe-1.7-strings-in-switch")
    parser.add_argument("--file", required=True)
    parser.add_argument("--line", required=True, type=int)
    args = parser.parse_args()

    fp = pathlib.Path(args.file)
    if not fp.exists():
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "changes": 0,
                    "warnings": [],
                    "errors": [f"File not found: {args.file}"],
                    "diff_summary": "File not found",
                }
            )
        )
        return 2

    lines = fp.read_text(encoding="utf-8").splitlines(keepends=True)
    flag_idx = args.line - 1

    if not (0 <= flag_idx < len(lines)):
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "changes": 0,
                    "warnings": [],
                    "errors": ["Line out of range"],
                    "diff_summary": "Line out of range",
                }
            )
        )
        return 2

    # Idempotency: already resolved?
    # Search nearby lines (±10) for the flag comment since scanner may
    # report match-line rather than flag-injection line
    flag_found = False
    actual_flag_idx = flag_idx
    for offset in range(-10, 11):
        ci = flag_idx + offset
        if 0 <= ci < len(lines):
            if _JADE_COMMENT in lines[ci]:
                flag_found = True
                actual_flag_idx = ci
                break
    if not flag_found:
        # Check if any nearby line has MODERNIZATION-DEFERRED
        deferred_found = False
        for offset in range(-10, 11):
            ci = flag_idx + offset
            if 0 <= ci < len(lines):
                if "JADE-MODERNIZATION-DEFERRED:STRINGS_IN_SWITCH" in lines[ci]:
                    deferred_found = True
                    break
        if deferred_found:
            print(
                json.dumps(
                    {
                        "status": "SKIPPED",
                        "changes": 0,
                        "warnings": ["Already deferred"],
                        "errors": [],
                        "diff_summary": "Previously deferred — no action",
                    }
                )
            )
        else:
            print(
                json.dumps(
                    {
                        "status": "SKIPPED",
                        "changes": 0,
                        "warnings": ["Flag already resolved or not found nearby"],
                        "errors": [],
                        "diff_summary": "Previously resolved",
                    }
                )
            )
        return 0
    # Update flag_idx to actual flag line
    flag_idx = actual_flag_idx

    # Find the associated if-statement (the flag is on the line after the matched code)
    # Walk backward past flags and blanks to find it
    candidate = flag_idx - 1
    while candidate >= 0:
        s = lines[candidate].strip()
        if s == "":
            candidate -= 1
            continue
        if _FLAG_RE.match(s):
            candidate -= 1
            continue
        if _IF_EQUALS_RE.match(lines[candidate].rstrip("\n")):
            break
        # Not part of an if-chain start pattern
        candidate = None
        break

    if candidate is None or candidate < 0:
        _defer_flag(lines, flag_idx)
        content = "".join(lines)
        tmp = fp.with_name(fp.name + ".tmp.switchdef")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(fp)
        print(
            json.dumps(
                {
                    "status": "SKIPPED",
                    "changes": 0,
                    "warnings": ["Cannot locate associated if-statement"],
                    "errors": [],
                    "diff_summary": "Deferred — cannot find if-statement for this flag",
                }
            )
        )
        return 0

    # Extract variable name from the if-statement
    if_m = _IF_EQUALS_RE.match(lines[candidate].rstrip("\n"))
    if not if_m:
        _defer_flag(lines, flag_idx)
        content = "".join(lines)
        tmp = fp.with_name(fp.name + ".tmp.switchdef")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(fp)
        print(
            json.dumps(
                {
                    "status": "SKIPPED",
                    "changes": 0,
                    "warnings": ["Unexpected if format"],
                    "errors": [],
                    "diff_summary": "Deferred — if-statement does not match expected pattern",
                }
            )
        )
        return 0

    var_name = if_m.group(1)

    # Defect (c) guard: the flagged if-statement may sit inside a comment
    # (e.g. dead/commented-out code) rather than live source. Check BEFORE
    # any pattern matching or file mutation — a comment match makes zero edits.
    source_text = "".join(lines)
    if not java_source.is_live_code(source_text, candidate + 1):
        print(
            json.dumps(
                {
                    "status": "SKIPPED",
                    "changes": 0,
                    "warnings": [
                        "Flagged if-statement is not live code (inside a comment) — no edits made"
                    ],
                    "errors": [],
                    "diff_summary": "SKIPPED — flagged location is inside a comment, zero edits",
                }
            )
        )
        return 0

    # Try Pattern A: sequential if-return
    result_a = _scan_sequential_if_return(lines, candidate)
    if result_a is not None:
        branches, end_idx = result_a
        # Build switch
        new_content = _build_switch(lines, candidate, end_idx, var_name, branches, None)
        tmp = fp.with_name(fp.name + ".tmp.switch")
        tmp.write_text(new_content, encoding="utf-8")
        tmp.replace(fp)
        literals = [b[0] for b in branches]
        print(
            json.dumps(
                {
                    "status": "FIXED",
                    "changes": 1,
                    "warnings": [],
                    "errors": [],
                    "diff_summary": f"sequential-if→switch({var_name}): {len(branches)} cases ({', '.join(literals)})",
                }
            )
        )
        return 0

    # Try Pattern B: if-else-if-else
    branches_b, else_idx, end_idx_b = _scan_if_else_chain(lines, candidate)
    if len(branches_b) >= 2:
        new_content = _build_switch(
            lines, candidate, end_idx_b or candidate + 1, var_name, branches_b, else_idx
        )
        tmp = fp.with_name(fp.name + ".tmp.switch")
        tmp.write_text(new_content, encoding="utf-8")
        tmp.replace(fp)
        literals = [b[0] for b in branches_b]
        print(
            json.dumps(
                {
                    "status": "FIXED",
                    "changes": 1,
                    "warnings": [],
                    "errors": [],
                    "diff_summary": f"if-else-if→switch({var_name}): {len(branches_b)} cases ({', '.join(literals)})",
                }
            )
        )
        return 0

    # Neither pattern matched — defer
    _defer_flag(lines, flag_idx)
    content = "".join(lines)
    tmp = fp.with_name(fp.name + ".tmp.switchdef")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(fp)
    print(
        json.dumps(
            {
                "status": "SKIPPED",
                "changes": 0,
                "warnings": ["No convertible chain detected"],
                "errors": [],
                "diff_summary": "Deferred — single branch, no convertible chain",
            }
        )
    )
    return 0


_RETURN_OR_THROW_RE = re.compile(r"^(return\b|throw\b)")


def _ends_with_return_or_throw(body_lines: list[str]) -> bool:
    """True when the last non-blank statement in *body_lines* is a
    return/throw. A trailing break after such a statement is unreachable
    code (javac: "unreachable statement"), so callers must omit it."""
    for raw in reversed(body_lines):
        s = raw.strip()
        if s == "":
            continue
        return bool(_RETURN_OR_THROW_RE.match(s))
    return False


def _strip_flag_lines(body_lines: list[str]) -> list[str]:
    """Drop any embedded JADE-FLAG:STRINGS_IN_SWITCH line from a captured
    branch body — those markers belong to the chain being replaced (defect
    b), not to the generated switch case."""
    return [bl for bl in body_lines if not _FLAG_RE.match(bl.strip())]


def _build_switch(
    lines: list[str],
    start_idx: int,
    end_idx: int,
    var_name: str,
    branches: list[tuple[str, int]],
    else_idx: Optional[int],
) -> str:
    """Build switch statement from branches and replace the original chain range.
    *branches* = [(literal_str, if_line_idx), ...]"""
    base_indent = _indent_of(lines[start_idx])

    switch_lines = [f"{base_indent}switch ({var_name}) {{\n"]

    for literal, line_idx in branches:
        switch_lines.append(f'{base_indent}case "{literal}":\n')
        # Extract the body
        if_line = lines[line_idx].rstrip("\n")
        has_brace = if_line.rstrip().endswith("{")
        if has_brace:
            # Braced body — extract content between braces
            body = []
            bi = line_idx + 1
            depth = 1
            while bi < len(lines) and depth > 0:
                s = lines[bi].rstrip("\n")
                depth += s.count("{") - s.count("}")
                if depth > 0:
                    body.append(lines[bi])
                bi += 1
            body = _strip_flag_lines(body)
            for bl in body:
                switch_lines.append(f"{base_indent}    {bl.lstrip()}")
        else:
            # Simple inline — body is on next lines until semicolon
            body = []
            bi = line_idx + 1
            while bi < len(lines) and ";" not in lines[bi]:
                if _FLAG_RE.match(lines[bi].strip()):
                    bi += 1
                    continue
                body.append(lines[bi])
                bi += 1
            if bi < len(lines):
                body.append(lines[bi])  # the semicolon line
            for bl in body:
                switch_lines.append(f"{base_indent}    {bl.lstrip()}")
        # Defect (a): a case body that already ends in return/throw must not
        # get a trailing break — javac rejects it as an unreachable statement.
        if not _ends_with_return_or_throw(body):
            switch_lines.append(f"{base_indent}    break;\n")

    if else_idx is not None:
        switch_lines.append(f"{base_indent}default:\n")
        else_line = lines[else_idx].rstrip("\n")
        has_brace = else_line.rstrip().endswith("{")
        if has_brace:
            bi = else_idx + 1
            depth = 1
            body = []
            while bi < len(lines) and depth > 0:
                s = lines[bi].rstrip("\n")
                depth += s.count("{") - s.count("}")
                if depth > 0:
                    body.append(lines[bi])
                bi += 1
            body = _strip_flag_lines(body)
            for bl in body:
                switch_lines.append(f"{base_indent}    {bl.lstrip()}")
        else:
            bi = else_idx + 1
            body = []
            while bi < len(lines) and ";" not in lines[bi]:
                if _FLAG_RE.match(lines[bi].strip()):
                    bi += 1
                    continue
                body.append(lines[bi])
                bi += 1
            if bi < len(lines):
                body.append(lines[bi])
            for bl in body:
                switch_lines.append(f"{base_indent}    {bl.lstrip()}")

    switch_lines.append(f"{base_indent}}}\n")

    # Defect (b): the original if/else-if chain occupies lines[start_idx:end_idx]
    # (JADE-FLAG comments included) and must be REPLACED by switch_lines, not
    # kept alongside it — so that range is dropped entirely from the output.
    before = lines[:start_idx]
    after = lines[end_idx:]

    return "".join(before + switch_lines + after)


if __name__ == "__main__":
    raise SystemExit(main())
