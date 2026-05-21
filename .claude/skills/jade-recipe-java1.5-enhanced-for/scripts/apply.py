#!/usr/bin/env python3
"""jade-recipe-java1.5-enhanced-for — convert safe indexed for-loops to enhanced-for.

CLI:
    python apply.py --file <path> --line <num>

Prints JSON result to stdout. Exit 0 = success, 2 = failure.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Dict, List

TMP_FILE_SUFFIX = ".tmp.recipe"


def atomic_file_write(file_path: pathlib.Path, content: str) -> None:
    tmp = file_path.with_name(file_path.name + TMP_FILE_SUFFIX)
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(file_path)


def _infer_collection_element_type(lines: List[str], coll_var: str) -> str:
    for line in lines:
        decl = re.search(rf"(\w+(?:<(\w+)>)?)\s+{re.escape(coll_var)}\s*=", line)
        if decl:
            inner = decl.group(2)
            if inner:
                return inner
            return "Object"
    return "Object"


def apply_enhanced_for(file_path: pathlib.Path, flagged_line: int) -> Dict:
    content = file_path.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    changes = 0
    warnings: List[str] = []

    idx = flagged_line - 1
    if idx < 0 or idx >= len(lines):
        return {
            "status": "FAILED",
            "changes": 0,
            "warnings": [],
            "errors": [f"Line {flagged_line} out of range"],
        }

    line = lines[idx]

    match = re.match(
        r"^(\s*)for\s*\(\s*int\s+(\w+)\s*=\s*0\s*;\s*\2\s*<\s*(\w+)\.size\(\)\s*;\s*\2\+\+\s*\)\s*\{",
        line,
    )
    if not match:
        match = re.match(
            r"^(\s*)for\s*\(\s*int\s+(\w+)\s*=\s*0\s*;\s*\2\s*<\s*(\w+)\.length\s*;\s*\2\+\+\s*\)\s*\{",
            line,
        )
        if not match:
            return {
                "status": "NOOP",
                "changes": 0,
                "warnings": ["No indexed for-loop found on flagged line"],
                "errors": [],
            }

    indent = match.group(1)
    idx_var = match.group(2)
    coll_var = match.group(3)

    loop_start = idx
    brace_count = 1
    loop_end = loop_start
    for bi in range(loop_start + 1, len(lines)):
        brace_count += lines[bi].count("{") - lines[bi].count("}")
        if brace_count == 0:
            loop_end = bi
            break

    if loop_end == loop_start:
        return {
            "status": "SKIPPED",
            "changes": 0,
            "warnings": [f"Could not find loop closing brace at line {flagged_line}"],
        }

    body_lines = lines[loop_start + 1 : loop_end]
    body_text = "".join(body_lines)
    is_safe = True
    skip_reasons: List[str] = []

    if re.search(rf"\.(remove|set|add)\s*\(\s*{re.escape(idx_var)}\s*[,\)]", body_text):
        skip_reasons.append(f".remove/set/add using {idx_var}")
        is_safe = False

    after_text = "".join(lines[loop_end + 1 :])
    if re.search(rf"\b{re.escape(idx_var)}\b", after_text):
        skip_reasons.append(f"{idx_var} used after loop")
        is_safe = False

    if re.search(rf"\b{re.escape(idx_var)}\s*\]", body_text) and re.search(
        rf"\.get\s*\(\s*{re.escape(idx_var)}\s*\)", body_text
    ):
        skip_reasons.append(f"parallel iteration with {idx_var}")
        is_safe = False

    if "--" in line:
        skip_reasons.append("backwards loop")
        is_safe = False

    if not is_safe:
        reason = "; ".join(skip_reasons)
        lines[idx] = lines[idx].rstrip("\n") + f" // MIGRATION-SKIP: {reason}\n"
        changes += 1
        new_content = "".join(lines)
        atomic_file_write(file_path, new_content)
        return {
            "status": "SKIPPED",
            "changes": changes,
            "warnings": [f"Line {flagged_line}: skipped ({reason})"],
            "errors": [],
            "diff_summary": f"MIGRATION-SKIP: {reason}",
        }

    elem_type = _infer_collection_element_type(lines, coll_var)
    loop_var = "item" if idx_var == "i" else f"elem_{idx_var}"
    new_for = f"{indent}for ({elem_type} {loop_var} : {coll_var}) {{"
    lines[idx] = new_for + "\n"

    for bi in range(idx + 1, loop_end + 1):
        array_pattern = rf"\b{re.escape(coll_var)}\s*\[\s*{re.escape(idx_var)}\s*\]"
        lines[bi] = re.sub(array_pattern, loop_var, lines[bi])
        cast_pattern = rf"\((\w+(?:<.*?>)?)\)\s*{re.escape(coll_var)}\.get\s*\(\s*{re.escape(idx_var)}\s*\)"
        lines[bi] = re.sub(cast_pattern, loop_var, lines[bi])
        get_pattern = rf"{re.escape(coll_var)}\.get\s*\(\s*{re.escape(idx_var)}\s*\)"
        lines[bi] = re.sub(get_pattern, loop_var, lines[bi])

    changes += 1
    new_content = "".join(lines)
    atomic_file_write(file_path, new_content)

    return {
        "status": "FIXED",
        "changes": changes,
        "warnings": [],
        "errors": [],
        "diff_summary": f"Converted for-loop to enhanced-for at line {flagged_line}",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="jade-recipe-java1.5-enhanced-for")
    parser.add_argument("--file", required=True, help="Target Java file")
    parser.add_argument(
        "--line", required=True, type=int, help="Flagged line number (1-based)"
    )
    args = parser.parse_args()

    file_path = pathlib.Path(args.file)
    if not file_path.exists():
        result = {
            "status": "FAILED",
            "changes": 0,
            "warnings": [],
            "errors": [f"File not found: {args.file}"],
        }
        print(json.dumps(result))
        return 2

    result = apply_enhanced_for(file_path, args.line)
    print(json.dumps(result))
    return 0 if result["status"] in ("FIXED", "SKIPPED", "NOOP") else 2


if __name__ == "__main__":
    raise SystemExit(main())
