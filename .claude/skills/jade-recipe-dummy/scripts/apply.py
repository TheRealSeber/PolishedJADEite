#!/usr/bin/env python3
"""jade-recipe-dummy — E2E test recipe.

Appends // E2E TEST comment to the flagged line. Returns success.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="jade-recipe-dummy")
    parser.add_argument("--file", required=True)
    parser.add_argument("--line", required=True, type=int)
    args = parser.parse_args()

    file_path = pathlib.Path(args.file)
    if not file_path.exists():
        result = {
            "status": "FAILED",
            "changes": 0,
            "warnings": [],
            "errors": [f"File not found: {args.file}"],
            "diff_summary": "File not found",
        }
        print(json.dumps(result))
        return 2

    lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
    idx = args.line - 1
    if 0 <= idx < len(lines):
        lines[idx] = lines[idx].rstrip("\n") + " // E2E TEST\n"
        tmp = file_path.with_name(file_path.name + ".tmp.dummy")
        tmp.write_text("".join(lines), encoding="utf-8")
        tmp.replace(file_path)

    result = {
        "status": "FIXED",
        "changes": 1,
        "warnings": [],
        "errors": [],
        "diff_summary": f"Dummy test executed at line {args.line}",
    }
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
