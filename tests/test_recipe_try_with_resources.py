"""Tests for jade-recipe-1.7-try-with-resources/scripts/scan.py.

scan.py is a narrowing shortlist, not a transform: it flags file:line
candidates for try-with-resources conversion, and the SKILL.md hands the
actual decision to a subagent (mode: agent — see the SKILL.md's "What
scan.py cannot decide" section for why a regex alone tops out around 70%
precision here, and stays a shortlist rather than an apply.py).

These tests cover:
  - the narrowing logic itself (declared-Closeable-shaped-type + close()
    in the try's own finally/body) on small synthetic snippets
  - nested-try masking (a resource opened+closed entirely inside an inner
    try must not also be attributed to the outer try that contains it —
    this was a real bug caught while measuring precision on the corpus,
    see BootGUI.java:178 vs 208 in the SKILL.md's methodology)
  - comment/string-literal awareness, via the real shared/lib/java_source.py
    contract scan.py imports (a `try` keyword inside a /* */ comment or a
    string literal must never surface as a candidate)
  - the documented "name looks Closeable, isn't" gap (scan.py cannot and
    is not expected to resolve real type hierarchies — that's exactly why
    this recipe is agent mode, not script mode)
  - CLI behavior (--file, --workspace-root, --json-out atomic write, error
    handling)
  - a regression lock on the real corpus counts documented in SKILL.md, so
    a future edit to the narrowing pattern cannot silently drift without a
    test failing
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
RECIPE_DIR = (
    ROOT / ".claude/skills/java-migration-skill-registry/1.7/jade-recipe-1.7-try-with-resources"
)
SCRIPT = RECIPE_DIR / "scripts" / "scan.py"
WORKSPACE = ROOT / "migration-runs/jade-1.6-to-1.7/workspace/src/jade/src"


def load_module():
    spec = importlib.util.spec_from_file_location("twr_scan_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def scan():
    return load_module()


def _lines(candidates):
    return sorted(c["line"] for c in candidates)


# ---------------------------------------------------------------------------
# Core narrowing logic
# ---------------------------------------------------------------------------


def test_single_resource_closed_inline_no_finally(scan):
    source = (
        "void m() {\n"
        "  try {\n"
        "    FileOutputStream out = new FileOutputStream(f);\n"
        "    out.write(1);\n"
        "    out.close();\n"
        "  } catch (IOException e) {}\n"
        "}\n"
    )
    candidates = scan.find_candidates(source)
    assert _lines(candidates) == [2]
    assert candidates[0]["vars"] == ["out"]


def test_declare_before_try_close_in_finally_idiom(scan):
    source = (
        "void m() {\n"
        "  FileOutputStream fos = null;\n"
        "  try {\n"
        "    fos = new FileOutputStream(f);\n"
        "    fos.write(1);\n"
        "  } finally {\n"
        "    if (fos != null) { fos.close(); }\n"
        "  }\n"
        "}\n"
    )
    candidates = scan.find_candidates(source)
    assert _lines(candidates) == [3]
    assert candidates[0]["vars"] == ["fos"]


def test_multi_resource_dependent_order(scan):
    source = (
        "void m() {\n"
        "  try {\n"
        "    FileWriter f = new FileWriter(name);\n"
        "    BufferedWriter bw = new BufferedWriter(f);\n"
        "    bw.write(x);\n"
        "    bw.close();\n"
        "    f.close();\n"
        "  } catch (IOException e) {}\n"
        "}\n"
    )
    candidates = scan.find_candidates(source)
    assert len(candidates) == 1
    assert candidates[0]["vars"] == ["bw", "f"]


def test_no_candidate_when_no_close_call(scan):
    source = (
        "void m() {\n"
        "  try {\n"
        "    FileOutputStream out = new FileOutputStream(f);\n"
        "    out.write(1);\n"
        "  } catch (IOException e) {}\n"
        "}\n"
    )
    assert scan.find_candidates(source) == []


def test_no_candidate_when_declared_type_not_closeable_shaped(scan):
    source = (
        "void m() {\n"
        "  try {\n"
        "    StringBuilder sb = new StringBuilder();\n"
        "    sb.append(x);\n"
        "    sb.close();\n"  # not real Java, but exercises the type filter
        "  } catch (Exception e) {}\n"
        "}\n"
    )
    assert scan.find_candidates(source) == []


# ---------------------------------------------------------------------------
# Nested-try masking
# ---------------------------------------------------------------------------


def test_nested_try_resource_not_attributed_to_outer(scan):
    """Mirrors BootGUI.java:178 vs 208 — an outer try with no finally that
    contains a nested try opening+closing its own resource must not also
    get flagged for the nested try's variable."""
    source = (
        "void m() {\n"
        "  try {\n"
        "    doSomethingUnrelated();\n"
        "    try {\n"
        "      FileOutputStream out = new FileOutputStream(f);\n"
        "      out.write(1);\n"
        "      out.close();\n"
        "    } catch (IOException e1) {}\n"
        "  } catch (BootException be) {}\n"
        "}\n"
    )
    candidates = scan.find_candidates(source)
    assert _lines(candidates) == [4]
    assert candidates[0]["vars"] == ["out"]


def test_sibling_nested_tries_each_own_their_own_resource(scan):
    source = (
        "void m() {\n"
        "  try {\n"
        "    try {\n"
        "      FileOutputStream a = new FileOutputStream(f1);\n"
        "      a.close();\n"
        "    } catch (IOException e) {}\n"
        "    try {\n"
        "      FileOutputStream b = new FileOutputStream(f2);\n"
        "      b.close();\n"
        "    } catch (IOException e) {}\n"
        "  } catch (Exception e) {}\n"
        "}\n"
    )
    candidates = scan.find_candidates(source)
    assert _lines(candidates) == [3, 7]
    assert candidates[0]["vars"] == ["a"]
    assert candidates[1]["vars"] == ["b"]


# ---------------------------------------------------------------------------
# Comment / string-literal awareness (via shared/lib/java_source.py contract)
# ---------------------------------------------------------------------------


def test_ignores_try_inside_block_comment(scan):
    source = (
        "void m() {\n"
        "  /*\n"
        "  try {\n"
        "    FileOutputStream out = new FileOutputStream(f);\n"
        "    out.close();\n"
        "  } catch (IOException e) {}\n"
        "  */\n"
        "}\n"
    )
    assert scan.find_candidates(source) == []


def test_ignores_try_inside_line_comment(scan):
    source = (
        "void m() {\n"
        "  // try { FileOutputStream out = new FileOutputStream(f); out.close(); }\n"
        "}\n"
    )
    assert scan.find_candidates(source) == []


def test_ignores_close_call_text_inside_string_literal(scan):
    source = (
        "void m() {\n"
        "  try {\n"
        "    FileOutputStream out = new FileOutputStream(f);\n"
        '    String note = "out.close();";\n'  # decoy in a string literal
        "  } catch (IOException e) {}\n"
        "}\n"
    )
    assert scan.find_candidates(source) == []


# ---------------------------------------------------------------------------
# Documented gap: a name that looks Closeable, but the type isn't
# ---------------------------------------------------------------------------


def test_flags_a_custom_connection_type_scan_cannot_verify(scan):
    """scan.py has no way to know whether `Connection` here resolves to a
    type that really implements Closeable/AutoCloseable — this IS the gap
    documented in SKILL.md ("What scan.py cannot decide") that keeps this
    recipe mode: agent instead of a script that would silently emit
    non-compiling try-with-resources for jade.imtp.leap.JICP.Connection
    (an abstract class with a `close()` method but no Closeable/
    AutoCloseable in its hierarchy — verified directly against
    Connection.java in this same corpus).

    Both the outer try (which owns `c`'s finally) and the inner
    try-catch-solely-around-close() get flagged here — the same double
    hit the real corpus produces at HTTPFEDispatcher.java:457,462 for this
    exact shape. Neither is a real candidate; scan.py has no way to know
    that without resolving Connection's type hierarchy."""
    source = (
        "void m() {\n"
        "  Connection c = getConnection(ta);\n"
        "  try {\n"
        "    return deliver(pkt, c);\n"
        "  } finally {\n"
        "    try { c.close(); } catch (Exception e) {}\n"
        "  }\n"
        "}\n"
    )
    candidates = scan.find_candidates(source)
    assert _lines(candidates) == [3, 6]
    assert candidates[0]["vars"] == ["c"]
    assert candidates[1]["vars"] == ["c"]


def test_real_corpus_connection_type_is_not_closeable():
    """Ground truth for the test above: jade.imtp.leap.JICP.Connection
    really does not implement Closeable/AutoCloseable."""
    connection_java = (
        WORKSPACE / "jade/imtp/leap/JICP/Connection.java"
    ).read_text(encoding="utf-8")
    assert "abstract void close()" in connection_java or "void close()" in connection_java
    assert "Closeable" not in connection_java


# ---------------------------------------------------------------------------
# CLI behavior
# ---------------------------------------------------------------------------


def test_cli_file_mode_prints_json_candidates(tmp_path):
    java_file = tmp_path / "Example.java"
    java_file.write_text(
        "void m() {\n"
        "  try {\n"
        "    FileOutputStream out = new FileOutputStream(f);\n"
        "    out.close();\n"
        "  } catch (IOException e) {}\n"
        "}\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--file", str(java_file)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload == [{"line": 2, "vars": ["out"]}]


def test_cli_file_mode_missing_file_errors(tmp_path):
    missing = tmp_path / "DoesNotExist.java"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--file", str(missing)],
        capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert "not found" in json.loads(result.stdout)["error"].lower()


def test_cli_workspace_root_not_a_directory_errors(tmp_path):
    not_a_dir = tmp_path / "nope.txt"
    not_a_dir.write_text("x", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--workspace-root", str(not_a_dir)],
        capture_output=True, text=True,
    )
    assert result.returncode == 2


def test_cli_workspace_root_and_file_are_mutually_exclusive(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--file", "a.java", "--workspace-root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0


def test_cli_json_out_is_atomic(tmp_path):
    java_dir = tmp_path / "ws"
    java_dir.mkdir()
    (java_dir / "A.java").write_text(
        "void m() {\n"
        "  try {\n"
        "    FileOutputStream out = new FileOutputStream(f);\n"
        "    out.close();\n"
        "  } catch (IOException e) {}\n"
        "}\n",
        encoding="utf-8",
    )
    out_path = tmp_path / "result.json"
    result = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--workspace-root", str(java_dir),
            "--json-out", str(out_path),
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert out_path.exists()
    assert not out_path.with_name(out_path.name + ".tmp").exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["files_scanned"] == 1
    assert payload["narrow_hit_count"] == 1
    assert payload["narrow_hits"][0]["file"] == "A.java"


# ---------------------------------------------------------------------------
# Regression lock on the real corpus (SKILL.md's measured precision numbers)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not WORKSPACE.is_dir(), reason="jade-1.6-to-1.7 workspace fixture not present")
def test_corpus_scan_matches_documented_measurement(scan):
    """Locks in the exact numbers SKILL.md's precision table reports. If
    this fails after a change to the narrowing pattern, SKILL.md's
    precision section (and its manually-verified true/false breakdown)
    needs to be re-measured and rewritten, not just the assertion bumped."""
    result = scan._scan_workspace(WORKSPACE)
    assert result["files_scanned"] == 1015
    assert result["raw_try_hits"] == 1880
    assert result["narrow_hit_count"] == 47


@pytest.mark.skipif(not WORKSPACE.is_dir(), reason="jade-1.6-to-1.7 workspace fixture not present")
def test_corpus_scan_finds_bootgui_true_candidates_only_at_the_close_sites(scan):
    """BootGUI.java has an outer try with no finally (line 178) that
    contains a nested try which opens+closes a FileOutputStream (line 208);
    a third similar site is fully self-contained (line 296). Only the
    inner close-sites should surface — this is the exact real-corpus case
    the nested-try masking fix (see measure history in SKILL.md) exists
    for."""
    text = (WORKSPACE / "jade/BootGUI.java").read_text(encoding="utf-8")
    candidates = scan.find_candidates(text)
    lines = _lines(candidates)
    assert 208 in lines
    assert 296 in lines
    assert 178 not in lines


@pytest.mark.skipif(not WORKSPACE.is_dir(), reason="jade-1.6-to-1.7 workspace fixture not present")
def test_corpus_scan_finds_dfdbkb_statement_candidates(scan):
    """java.sql.Statement implements AutoCloseable as of Java 7 — the exact
    JDK change this migration is targeting. DFDBKB.java's tableExists()
    manages a Statement with the classic declare-above/close-in-finally
    idiom across three methods."""
    text = (WORKSPACE / "jade/domain/DFDBKB.java").read_text(encoding="utf-8")
    candidates = scan.find_candidates(text)
    lines = _lines(candidates)
    for expected in (382, 415, 455):
        assert expected in lines
