#!/usr/bin/env python3
"""jade-recipe-1.7-diamond-operator — convert explicit generic constructors to diamond operator.

Given --file and --line, reads the Java file, finds the flagged constructor call
(e.g. new HashMap<String,String>()), replaces type arguments with diamond <> on
the same line, and removes the // JADE-FLAG:DIAMOND_OPERATOR comment below it.
Atomic write via tmp-file + rename.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

# Match a generic constructor invocation: new ClassName<types>()  (types may contain commas, <>, etc.)
_DIAMOND_RE = re.compile(r"\bnew\s+(\w+)\s*<([A-Za-z0-9_$<>\s,?.]+)>\s*\(")


def _replace_diamond(line: str) -> tuple[str, int]:
    """Replace first generic constructor on *line* with diamond. Returns (new_line, count)."""

    def _replacer(m: re.Match) -> str:
        cls_name = m.group(1)
        return f"new {cls_name}<>("

    new_line, n = _DIAMOND_RE.subn(_replacer, line, count=1)
    return new_line, n


def main() -> int:
    parser = argparse.ArgumentParser(description="jade-recipe-1.7-diamond-operator")
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
    line_idx = args.line - 1

    if not (0 <= line_idx < len(lines)):
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "changes": 0,
                    "warnings": [],
                    "errors": ["Line out of range"],
                    "diff_summary": f"Line {args.line} out of range (1..{len(lines)})",
                }
            )
        )
        return 2

    # The flagged line may be the JADE-FLAG comment — scan nearby lines for the pattern
    candidate_idxs = [line_idx]
    for offset in (-2, -1, 1, 2):
        ci = line_idx + offset
        if 0 <= ci < len(lines):
            candidate_idxs.append(ci)

    best_idx = line_idx
    best_line = lines[line_idx]
    for ci in candidate_idxs:
        tl = lines[ci]
        # Must have "new " and "<" but NOT already using diamond (<> should have content between < and >)
        if "new " in tl and "<" in tl and "<>" not in tl:
            best_idx = ci
            best_line = tl
            break

    target_line = best_line
    line_idx = best_idx

    if "new " not in target_line or "<" not in target_line:
        print(
            json.dumps(
                {
                    "status": "SKIPPED",
                    "changes": 0,
                    "warnings": ["No diamond-operator candidate on this line"],
                    "errors": [],
                    "diff_summary": "No generic constructor call on target line",
                }
            )
        )
        return 0

    # Skip diamond inside this(...) or super(...) calls — Java 7 type inference
    # cannot resolve the target type in constructor delegation contexts.
    stripped_line = target_line.strip()
    if re.search(r"\b(?:this|super)\s*\(", stripped_line):
        print(
            json.dumps(
                {
                    "status": "SKIPPED",
                    "changes": 0,
                    "warnings": [
                        "Constructor delegation context (this/super) — type inference ambiguous in Java 7"
                    ],
                    "errors": [],
                    "diff_summary": "Skipped: diamond in this()/super() call is ambiguous in Java 7",
                }
            )
        )
        return 0

    original = target_line.rstrip("\n")
    new_line, changes = _replace_diamond(target_line)

    if changes == 0:
        print(
            json.dumps(
                {
                    "status": "SKIPPED",
                    "changes": 0,
                    "warnings": ["Pattern not matched on this line"],
                    "errors": [],
                    "diff_summary": "No diamond operator replacement possible",
                }
            )
        )
        return 0

    lines[line_idx] = new_line

    # Remove the JADE-FLAG:DIAMOND_OPERATOR comment from adjacent lines
    # The flag may be on the same line, the next line, or the previous line
    for check_offset in (0, 1, -1):
        ci = line_idx + check_offset
        if 0 <= ci < len(lines) and "JADE-FLAG:DIAMOND_OPERATOR" in lines[ci]:
            cl = lines[ci]
            fi = cl.find("// JADE-FLAG:DIAMOND_OPERATOR")
            if fi >= 0:
                before = cl[:fi].rstrip()
                if before:
                    lines[ci] = before + "\n"
                else:
                    lines[ci] = ""

    # Atomic write
    content = "".join(lines)
    tmp = fp.with_name(fp.name + ".tmp.diamond")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(fp)

    short_orig = original.strip()[:70]
    short_new = new_line.strip()[:70]
    print(
        json.dumps(
            {
                "status": "FIXED",
                "changes": changes,
                "warnings": [],
                "errors": [],
                "diff_summary": f"Line {args.line}: {short_orig} -> {short_new}",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
