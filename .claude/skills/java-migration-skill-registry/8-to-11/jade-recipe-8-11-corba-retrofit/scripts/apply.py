#!/usr/bin/env python3
"""CORBA_REMOVAL retrofit recipe for Java 8 -> 11 (JEP 320).

Ensures the standalone GlassFish CORBA jars are present under lib/corba/ and
the Ant build.xml classpath references them, then clears JADE-FLAG:CORBA_REMOVAL
markers (one per invocation, in ascending flag-line order).

Output contract (single JSON line on stdout):
  {"status": "FIXED|SKIPPED|FAILED", "changes": N, "warnings": [...], "errors": [...], "diff_summary": "..."}
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

FLAG_MARKER = "JADE-FLAG:CORBA_REMOVAL"
OIMGAPI_JAR = "glassfish-corba-omgapi-4.2.2.jar"

BUILD_XML_PATH_BLOCK = """	<path id="compile.classpath">
		<fileset dir="${lib}/corba" includes="*.jar"/>
		<pathelement location="lib/commons-codec/commons-codec-1.3.jar"/>
	</path>
"""


def _ok(status, changes, warnings, errors, diff):
    return {
        "status": status,
        "changes": changes,
        "warnings": warnings,
        "errors": errors,
        "diff_summary": diff,
    }


def _find_jade_root(fp: pathlib.Path) -> pathlib.Path:
    """Walk up from the flagged file until a directory containing build.xml."""
    cur = fp.parent
    while True:
        if (cur / "build.xml").exists():
            return cur
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    return pathlib.Path()


def _retrofit_present(jade_root: pathlib.Path) -> bool:
    omgapi = jade_root / "lib" / "corba" / OIMGAPI_JAR
    return omgapi.is_file()


def _ensure_buildxml(jade_root: pathlib.Path) -> list:
    """Idempotently add the compile.classpath path element to build.xml.

    Returns list of applied-change descriptions (empty = already present).
    """
    build_xml = jade_root / "build.xml"
    if not build_xml.exists():
        return ["build.xml not found under jade root"]
    raw = build_xml.read_text(encoding="utf-8", errors="replace")
    if 'classpathref="compile.classpath"' in raw and "<path id=\"compile.classpath\"" in raw:
        return []

    changed = raw

    # Replace the explicit classpath attribute with the path reference.
    changed = changed.replace(
        'classpath="lib/commons-codec/commons-codec-1.3.jar"',
        'classpathref="compile.classpath"',
    )

    # Insert the path definition before the compile target.
    if '<path id="compile.classpath">' not in changed:
        marker = '<target name="jade"'
        if marker in changed:
            changed = changed.replace(marker, BUILD_XML_PATH_BLOCK + marker, 1)
        else:
            return ["<target name=\"jade\"> not found — cannot insert compile.classpath"]

    if changed != raw:
        tmp = build_xml.with_name(build_xml.name + ".tmp.recipe")
        tmp.write_text(changed, encoding="utf-8")
        tmp.replace(build_xml)
        return ["added lib/corba jars to compile.classpath in build.xml"]
    return []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--line", type=int, required=True)
    args = parser.parse_args()

    fp = pathlib.Path(args.file)
    if not fp.exists():
        print(json.dumps(_ok("FAILED", 0, [], [f"File not found: {args.file}"], "")))
        return 2

    jade_root = _find_jade_root(fp)
    if not jade_root.exists():
        print(json.dumps(_ok("FAILED", 0, [], ["Could not locate jade root (build.xml) above the flagged file"], "")))
        return 2

    # 1. Jars must already be vendored (resolved at the build gate via Maven).
    if not _retrofit_present(jade_root):
        print(json.dumps(_ok(
            "FAILED", 0, [],
            [f"lib/corba/{OIMGAPI_JAR} missing. Vendor the GlassFish CORBA 4.2.2 set under "
             f"{jade_root / 'lib' / 'corba'} (mvn dependency:copy-dependencies on "
             "org.glassfish.corba:glassfish-corba-orb:4.2.2) before re-running this recipe."],
            "",
        )))
        return 2

    # 2. Ensure build.xml references the retrofit (idempotent).
    applied = _ensure_buildxml(jade_root)
    if any("cannot insert" in a or "not found" in a for a in applied):
        print(json.dumps(_ok("FAILED", 0, [], applied, "")))
        return 2

    # 3. Remove the next outstanding CORBA flag marker (ascending order).
    lines = fp.read_text(encoding="utf-8", errors="replace").splitlines(True)
    target_idx = None
    for i, ln in enumerate(lines):
        if FLAG_MARKER in ln:
            target_idx = i
            break

    if target_idx is None:
        print(json.dumps(_ok(
            "SKIPPED", 0,
            ["No remaining JADE-FLAG:CORBA_REMOVAL marker"],
            [],
            "CORBA retrofit already applied; marker already cleared",
        )))
        return 0

    removed = lines.pop(target_idx)
    tmp = fp.with_name(fp.name + ".tmp.recipe")
    tmp.write_text("".join(lines), encoding="utf-8")
    tmp.replace(fp)

    diff = (
        f"{fp.name}:{target_idx + 1} cleared {FLAG_MARKER} (retrofit verified: "
        f"lib/corba jars + compile.classpath)"
    )
    print(json.dumps(_ok("FIXED", 1, applied, [], diff)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())