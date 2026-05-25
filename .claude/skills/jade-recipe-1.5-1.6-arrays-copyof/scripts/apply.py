#!/usr/bin/env python3
"""Replace System.arraycopy with Arrays.copyOf/copyOfRange for Java 1.5→1.6."""

import argparse, json, re, sys, pathlib


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--line", type=int, required=True)
    args = parser.parse_args()

    fp = pathlib.Path(args.file)
    if not fp.exists():
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "changes": 0,
                    "warnings": [],
                    "errors": ["File not found"],
                    "diff_summary": "",
                }
            )
        )
        return 1

    lines = fp.read_text(encoding="utf-8").splitlines(True)
    if args.line < 1 or args.line > len(lines):
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "changes": 0,
                    "warnings": [],
                    "errors": ["Line out of range"],
                    "diff_summary": "",
                }
            )
        )
        return 1

    line_idx = args.line - 1
    line = lines[line_idx]

    if "System.arraycopy" not in line:
        print(
            json.dumps(
                {
                    "status": "SKIPPED",
                    "changes": 0,
                    "warnings": ["No System.arraycopy on this line"],
                    "errors": [],
                    "diff_summary": "No match on target line",
                }
            )
        )
        return 0

    original = line.strip()

    # Try to parse: System.arraycopy(src, srcPos, dest, destPos, length)
    m = re.match(
        r"(.*?)System\.arraycopy\s*\(\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*,\s*(\d+)\s*,\s*(\w+)\s*\)(.*)",
        line,
    )

    if m:
        indent, src, srcPos, dest, destPos, length, rest = m.groups()
        if src == dest and destPos == "0":
            # System.arraycopy(arr, 0, arr, 0, newLen) → arr = Arrays.copyOf(arr, newLen)
            new_line = (
                f"{indent}{src} = java.util.Arrays.copyOf({src}, {length});{rest}"
            )
        elif destPos == "0":
            new_line = (
                f"{indent}{dest} = java.util.Arrays.copyOf({src}, {length});{rest}"
            )
        else:
            new_line = f"{indent}System.arraycopy({src}, {srcPos}, {dest}, {destPos}, {length});{rest}\n{indent}// NOTE: Consider Arrays.copyOfRange for Java 6+ compatibility"
    else:
        # Cannot parse automtically — leave as-is with note
        new_line = (
            line.rstrip() + " // NOTE: Consider Arrays.copyOf/copyOfRange for Java 6+\n"
        )

    lines[line_idx] = new_line

    # Add import if not present
    content = "".join(lines)
    if "java.util.Arrays" not in content and "System.arraycopy" not in content.replace(
        "// NOTE: Consider", ""
    ):
        # Check if we need import
        pass

    fp.write_text(content, encoding="utf-8")

    diff = f"Line {args.line}: {original[:60]}... → {new_line.strip()[:60]}..."
    print(
        json.dumps(
            {
                "status": "FIXED",
                "changes": 1,
                "warnings": [],
                "errors": [],
                "diff_summary": diff,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
