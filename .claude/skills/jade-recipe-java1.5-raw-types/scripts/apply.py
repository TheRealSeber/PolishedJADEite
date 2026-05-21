#!/usr/bin/env python3
"""jade-recipe-java1.5-raw-types — add generic type parameters to raw collections.

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
from typing import Dict, List, Optional, Tuple

TMP_FILE_SUFFIX = ".tmp.recipe"


def atomic_file_write(file_path: pathlib.Path, content: str) -> None:
    tmp = file_path.with_name(file_path.name + TMP_FILE_SUFFIX)
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(file_path)


def infer_generic_type(lines: List[str], var_name: str) -> Optional[str]:
    add_types: List[str] = []
    get_cast_types: List[str] = []
    for line in lines:
        add_match = re.search(rf"\b{re.escape(var_name)}\.add\(\s*(.+?)\s*\)", line)
        if add_match:
            arg = add_match.group(1).strip()
            add_types.append(_resolve_arg_type(arg, lines))
        put_match = re.search(
            rf"\b{re.escape(var_name)}\.put\(\s*(.+?)\s*,\s*(.+?)\s*\)", line
        )
        if put_match:
            key_type = _resolve_arg_type(put_match.group(1).strip(), lines)
            val_type = _resolve_arg_type(put_match.group(2).strip(), lines)
            if key_type or val_type:
                return f"{key_type or 'Object'},{val_type or 'Object'}"
        cast_match = re.search(
            rf"\((\w+(?:<.*?>)?)\)\s*{re.escape(var_name)}\.get", line
        )
        if cast_match:
            get_cast_types.append(cast_match.group(1))
    all_types = add_types + get_cast_types
    unique_types = list(dict.fromkeys(t for t in all_types if t and t != "null"))
    if not unique_types:
        return None
    if len(unique_types) == 1:
        return unique_types[0]
    if all(t == "String" for t in unique_types):
        return "String"
    return "Object"


def _resolve_arg_type(arg: str, lines: List[str]) -> str:
    arg = arg.strip().rstrip(";")
    if not arg or arg == "null":
        return "null"
    if arg.startswith('"') or arg.startswith("'"):
        return "String"
    if re.match(r"^-?\d+(\.\d+)?[fFlLdD]?$", arg):
        return "Integer"
    if arg in ("true", "false"):
        return "Boolean"
    new_match = re.match(r"new\s+(\w+)\s*\(", arg)
    if new_match:
        return new_match.group(1)
    if re.match(r"^\w+$", arg):
        for line in lines:
            decl = re.search(rf"\b(\w+(?:<.*?>)?)\s+{re.escape(arg)}\s*[=;]", line)
            if decl:
                return decl.group(1)
        return arg
    return "Object"


def apply_raw_types(file_path: pathlib.Path, flagged_line: int) -> Dict:
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
        r"^(\s*)(\w+)\s+(\w+)\s*=\s*new\s+(Vector|ArrayList|HashMap|Hashtable|LinkedList|HashSet)\s*\(\s*\)\s*;",
        line,
    )
    if not match:
        match = re.match(
            r"(.*?)new\s+(Vector|ArrayList|HashMap|Hashtable|LinkedList|HashSet)\s*\(\s*\)",
            line,
        )
        if not match:
            return {
                "status": "NOOP",
                "changes": 0,
                "warnings": ["No raw collection found on flagged line"],
                "errors": [],
            }

    indent = match.group(1) if "(" not in match.group(1) else ""
    var_name = match.group(3) if match.lastindex and match.lastindex >= 3 else None
    coll_type = (
        match.group(4) if match.lastindex and match.lastindex >= 4 else match.group(2)
    )

    inferred = "Object"
    if var_name:
        result = infer_generic_type(lines, var_name)
        if result:
            inferred = result

    if var_name:
        replacement = f"{indent}{coll_type}<{inferred}> {var_name} = new {coll_type}<{inferred}>();"
        lines[idx] = replacement + "\n"
        changes += 1
    else:
        old = match.group(0)
        new = old.replace(f"new {coll_type}()", f"new {coll_type}<{inferred}>()")
        lines[idx] = line.replace(old, new, 1)
        changes += 1

    if var_name:
        for ci in range(idx + 1, len(lines)):
            cast_match = re.search(
                rf"\((\w+(?:<.*?>)?)\)\s*\b{re.escape(var_name)}\.get\(", lines[ci]
            )
            if cast_match:
                cast_type = cast_match.group(1)
                if cast_type == inferred or inferred == "Object":
                    lines[ci] = re.sub(
                        rf"\((\w+(?:<.*?>)?)\)\s*({re.escape(var_name)}\.get\()",
                        r"\2",
                        lines[ci],
                    )

    if changes > 0:
        new_content = "".join(lines)
        atomic_file_write(file_path, new_content)
        return {
            "status": "FIXED",
            "changes": changes,
            "warnings": warnings,
            "errors": [],
            "diff_summary": f"Applied generics ({coll_type}<{inferred}>) at line {flagged_line}",
        }

    return {"status": "NOOP", "changes": 0, "warnings": warnings, "errors": []}


def main() -> int:
    parser = argparse.ArgumentParser(description="jade-recipe-java1.5-raw-types")
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

    result = apply_raw_types(file_path, args.line)
    print(json.dumps(result))
    return 0 if result["status"] in ("FIXED", "NOOP") else 2


if __name__ == "__main__":
    raise SystemExit(main())
