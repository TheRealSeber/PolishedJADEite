#!/usr/bin/env python3
"""THREAD_STOP_DISABLED — inspect .stop() calls for actual Thread.stop() usage."""

import argparse
import json
import pathlib
import re
import sys

FLAG_MARKER = "JADE-FLAG:THREAD_STOP_DISABLED"
DEFERRED_MARKER = "JADE-MODERNIZATION-DEFERRED:THREAD_STOP_DISABLED"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--line", type=int, required=True)
    args = parser.parse_args()

    fp = pathlib.Path(args.file)
    if not fp.exists():
        result = {
            "status": "FAILED",
            "changes": 0,
            "warnings": [],
            "errors": [f"File not found: {args.file}"],
            "diff_summary": "",
        }
        print(json.dumps(result))
        return 2

    lines = fp.read_text(encoding="utf-8", errors="replace").splitlines(True)

    if args.line < 1 or args.line > len(lines):
        result = {
            "status": "FAILED",
            "changes": 0,
            "warnings": [],
            "errors": [f"Line {args.line} out of range (file has {len(lines)} lines)"],
            "diff_summary": "",
        }
        print(json.dumps(result))
        return 2

    line_idx = args.line - 1

    # Scan for flag marker
    found_flag = False
    flag_comment_line = line_idx
    actual_code_line = -1
    for i in range(line_idx, min(line_idx + 5, len(lines))):
        li = lines[i]
        if FLAG_MARKER in li or DEFERRED_MARKER in li:
            found_flag = True
            flag_comment_line = i
            continue
        stripped = li.strip()
        if found_flag and stripped and not stripped.startswith("//"):
            actual_code_line = i
            break

    if not found_flag:
        result = {
            "status": "SKIPPED",
            "changes": 0,
            "warnings": ["No JADE-FLAG marker found near line"],
            "errors": [],
            "diff_summary": "Already processed or flag missing",
        }
        print(json.dumps(result))
        return 0

    if actual_code_line < 0:
        result = {
            "status": "SKIPPED",
            "changes": 0,
            "warnings": ["Flag without associated code line"],
            "errors": [],
            "diff_summary": "Flag without code — likely already transformed",
        }
        print(json.dumps(result))
        return 0

    code = lines[actual_code_line].strip()
    is_thread_stop = bool(
        re.match(r"(?:Thread\s*\.\s*stop|\w*(?:[Tt]hread)\w*\s*\.\s*stop)\s*\(", code)
    )
    has_stop_call = ".stop(" in code

    if is_thread_stop:
        old_lines = "".join(lines)
        comment = f"// JADE-MODERNIZATION-DEFERRED:THREAD_STOP_DISABLED Thread.stop() was disabled in Java 8 — manual review required\n"
        lines[flag_comment_line] = comment
        new_lines = "".join(lines)
        diff = f"Line {args.line}: Thread.stop() flagged for manual review (call disabled in Java 8)"
        tmp = fp.with_name(fp.name + ".tmp.recipe")
        tmp.write_text(new_lines, encoding="utf-8")
        tmp.replace(fp)
        result = {
            "status": "FIXED",
            "changes": 1,
            "warnings": ["Thread.stop() found — manual review needed for replacement"],
            "errors": [],
            "diff_summary": diff,
        }
        print(json.dumps(result))
        return 0

    if has_stop_call:
        old_lines = "".join(lines)
        comment = f"// JADE-MODERNIZATION-DEFERRED:THREAD_STOP_DISABLED Custom .stop() call — not Thread.stop(); no change needed\n"
        lines[flag_comment_line] = comment
        new_lines = "".join(lines)
        diff = f"Line {args.line}: .stop() call is not Thread.stop(Throwable) — informational only"
        tmp = fp.with_name(fp.name + ".tmp.recipe")
        tmp.write_text(new_lines, encoding="utf-8")
        tmp.replace(fp)
        result = {
            "status": "FIXED",
            "changes": 1,
            "warnings": [],
            "errors": [],
            "diff_summary": diff,
        }
        print(json.dumps(result))
        return 0

    result = {
        "status": "SKIPPED",
        "changes": 0,
        "warnings": ["No .stop() call found in associated code line"],
        "errors": [],
        "diff_summary": "No actionable code found",
    }
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
