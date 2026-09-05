#!/usr/bin/env python3
"""jade-recipe-1.7-try-with-resources — narrow candidate scanner.

The manifest's raw rule pattern for TRY_WITH_RESOURCES is ``\\btry\\s*\\{`` —
it matches every try block in the codebase (1832 flags on the full JADE
tree, 0.6% of them real candidates). This module is NOT a replacement rule
pattern and does not decide anything on its own. It narrows that firehose
down to try blocks where:

  1. a variable is declared with a type this module recognizes as
     Closeable/AutoCloseable-shaped (java.io streams/readers/writers,
     java.sql Statement/ResultSet/Connection, java.net Socket family,
     etc — see CLOSEABLE_TYPE_HINTS), AND
  2. that same variable has a ``.close()`` call in the try's own finally
     block, or (no finally present) inline in the try's own body.

That is it. It is a SHORTLIST, not a verdict — see "What this scanner
cannot decide" in SKILL.md for exactly why a name/pattern match is not
proof the resource is safe to convert (the flagged type might not really
implement Closeable at all — see jade.imtp.leap.JICP.Connection in this
same codebase, which has a close() method but does not implement
java.io.Closeable or java.lang.AutoCloseable), and read the "When NOT to
transform" section before acting on any hit this script produces.

Measured on migration-runs/jade-1.6-to-1.7/workspace/src/jade/src (1015
.java files): 42 narrow hits vs 1880 raw ``\\btry\\s*\\{`` hits. Manual
read of all 42: 32 genuine try-with-resources candidates, 10 not (a
resource used/declared outside this try's own scope, a conditionally
closed resource that escapes the try in another branch, or a Connection
type that only duck-types close() without implementing the marker
interface) — precision ~76%, see SKILL.md for the file:line breakdown.

Usage:
  scan.py --file path/to/Some.java              # candidates in one file
  scan.py --workspace-root DIR [--json-out OUT] # candidates across a tree
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
from typing import Optional

# shared/lib/java_source.py holds the comment/string-literal aware source
# classifier (contract: classify_lines / is_live_code /
# strip_comments_and_strings). Resolve it relative to this file so the
# recipe works regardless of the caller's cwd — same convention as the
# other 1.7 recipes in this registry.
_SHARED_LIB_DIR = pathlib.Path(__file__).resolve().parents[3] / "shared" / "lib"
if str(_SHARED_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_LIB_DIR))

import java_source  # noqa: E402  (path set up above)


# Type NAME SUFFIXES this scanner treats as "looks Closeable" — a
# narrowing hint only, never proof (see module docstring and SKILL.md).
# Matched as a suffix (e.g. "FileOutputStream", "ObjectInputStream" both
# match "OutputStream"/"InputStream") so the common concrete JDK stream
# and reader/writer subclasses are covered without enumerating every one
# of them by name. This is deliberately still a narrow whitelist, not
# "anything ending in Stream", because a codebase like JADE has plenty of
# home-grown classes with unrelated names that happen to share a suffix.
CLOSEABLE_TYPE_SUFFIXES = (
    "InputStream", "OutputStream", "Reader", "Writer",
    "Socket", "ServerSocket", "DatagramSocket",
    "Connection", "Statement", "ResultSet", "Scanner",
    "RandomAccessFile", "ZipFile", "JarFile",
    "Channel", "FileLock",
    "Closeable", "AutoCloseable",
)

_DECL_RE = re.compile(
    r"\b(?:\w+\.)*\w*(?:" + "|".join(CLOSEABLE_TYPE_SUFFIXES) + r")\b"
    r"(?:\s*<[^>]*>)?\s+(\w+)\s*="
)
_CLOSE_RE = re.compile(r"\b(\w+)\s*\.\s*close\s*\(\s*\)")
_TRY_RE = re.compile(r"\btry\b\s*\{")

# How far back (in characters of comment/string-stripped source) to look
# for a resource declaration that precedes its try statement — covers the
# pre-Java-7 "declare above as null, assign in try, close in finally" idiom.
_PRECEDING_WINDOW = 2000


def _find_matching_brace(s: str, open_idx: int) -> int:
    depth = 0
    i = open_idx
    n = len(s)
    while i < n:
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _skip_ws(s: str, i: int) -> int:
    n = len(s)
    while i < n and s[i] in " \t\n\r":
        i += 1
    return i


def _construct_end(s: str, close_brace: int) -> tuple[int, str]:
    """Walk a try block's closing '}' past any catch(...) {...} blocks and
    an optional finally {...}. Returns (end_index_exclusive, finally_body)."""
    i = _skip_ws(s, close_brace + 1)
    while s[i:i + 5] == "catch":
        paren_start = s.find("(", i)
        if paren_start == -1:
            break
        depth = 0
        j = paren_start
        while j < len(s):
            if s[j] == "(":
                depth += 1
            elif s[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        brace_start = s.find("{", j)
        if brace_start == -1:
            break
        brace_end = _find_matching_brace(s, brace_start)
        if brace_end == -1:
            break
        i = _skip_ws(s, brace_end + 1)

    finally_body = ""
    end = i
    if s[i:i + 7] == "finally":
        brace_start = s.find("{", i + 7)
        if brace_start != -1:
            brace_end = _find_matching_brace(s, brace_start)
            if brace_end != -1:
                finally_body = s[brace_start + 1:brace_end]
                end = brace_end + 1
    return end, finally_body


def _mask_span(text: str, base_offset: int, span_start: int, span_end: int) -> str:
    a = max(0, span_start - base_offset)
    b = min(len(text), span_end - base_offset)
    if a >= b:
        return text
    return text[:a] + (" " * (b - a)) + text[b:]


def find_candidates(source: str) -> list[dict]:
    """Return narrow try-with-resources candidates in *source*.

    Each result is ``{"line": int, "vars": [str, ...]}`` — the 1-indexed
    line of the ``try`` keyword, and the resource variable name(s) this
    scanner found declared-with-a-Closeable-shaped-type AND closed within
    this try's own scope. A nested try's own resources are masked out of
    the outer try's search region first, so a resource opened and closed
    entirely inside an inner try is attributed only to that inner try, not
    also to every try that contains it.
    """
    stripped = java_source.strip_comments_and_strings(source)

    constructs = []  # (try_kw_start, open_brace, close_brace, construct_end_idx)
    for m in _TRY_RE.finditer(stripped):
        try_kw_start = m.start()
        open_brace = m.end() - 1
        close_brace = _find_matching_brace(stripped, open_brace)
        if close_brace == -1:
            continue
        end_idx, _ = _construct_end(stripped, close_brace)
        constructs.append((try_kw_start, open_brace, close_brace, end_idx))

    results = []
    for (try_kw_start, open_brace, close_brace, _end_idx) in constructs:
        try_body = stripped[open_brace + 1:close_brace]
        _, finally_body = _construct_end(stripped, close_brace)

        # Mask out any OTHER construct nested strictly inside this try_body —
        # its own declarations/close() calls belong to it, not to this try.
        masked_try_body = try_body
        for (o2_kw, o2, _c2, e2) in constructs:
            if o2 == open_brace:
                continue
            if o2 > open_brace and e2 <= close_brace:
                masked_try_body = _mask_span(masked_try_body, open_brace + 1, o2_kw, e2)

        combined_close_scope = finally_body if finally_body else masked_try_body
        closed_vars = set(_CLOSE_RE.findall(combined_close_scope))
        if not closed_vars:
            continue

        declared: dict[str, bool] = {}
        for dm in _DECL_RE.finditer(masked_try_body):
            declared[dm.group(1)] = True
        line_start_of_try = stripped.rfind("\n", 0, try_kw_start) + 1
        preceding_start = max(0, line_start_of_try - _PRECEDING_WINDOW)
        preceding_text = stripped[preceding_start:line_start_of_try]
        for dm in _DECL_RE.finditer(preceding_text):
            declared[dm.group(1)] = True

        candidate_vars = closed_vars & set(declared.keys())
        if candidate_vars:
            line_no = stripped.count("\n", 0, try_kw_start) + 1
            results.append({"line": line_no, "vars": sorted(candidate_vars)})
    return results


def _iter_java_files(root: pathlib.Path):
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            if fn.endswith(".java"):
                yield pathlib.Path(dirpath) / fn


def _scan_workspace(root: pathlib.Path) -> dict:
    files_scanned = 0
    raw_try_hits = 0
    narrow_hits = []
    for path in _iter_java_files(root):
        files_scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        raw_try_hits += len(re.findall(r"\btry\s*\{", text))
        for cand in find_candidates(text):
            narrow_hits.append({
                "file": str(path.relative_to(root)),
                "line": cand["line"],
                "vars": cand["vars"],
            })
    return {
        "files_scanned": files_scanned,
        "raw_try_hits": raw_try_hits,
        "narrow_hits": narrow_hits,
        "narrow_hit_count": len(narrow_hits),
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", help="scan a single .java file, print JSON candidates")
    group.add_argument("--workspace-root", help="scan every .java file under this directory")
    parser.add_argument("--json-out", help="write the workspace scan result here (atomic)")
    args = parser.parse_args(argv)

    if args.file:
        fp = pathlib.Path(args.file)
        if not fp.exists():
            print(json.dumps({"error": f"File not found: {args.file}"}))
            return 2
        text = fp.read_text(encoding="utf-8", errors="replace")
        print(json.dumps(find_candidates(text), indent=2))
        return 0

    root = pathlib.Path(args.workspace_root)
    if not root.is_dir():
        print(json.dumps({"error": f"Not a directory: {args.workspace_root}"}))
        return 2
    result = _scan_workspace(root)
    if args.json_out:
        out_path = pathlib.Path(args.json_out)
        tmp = out_path.with_name(out_path.name + ".tmp")
        tmp.write_text(json.dumps(result, indent=2), encoding="utf-8")
        tmp.replace(out_path)
    else:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
