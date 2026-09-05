"""Tests for jade-recipe-1.7-strings-in-switch/scripts/apply.py.

Covers three defects fixed in the recipe:
  (a) a case body ending in return/throw must not get a trailing `break;`
      (javac rejects that as an unreachable statement)
  (b) the original if/else-if chain must be REPLACED by the generated
      switch, not kept alongside it
  (c) a flagged if-statement sitting inside a comment must be SKIPPED
      with zero file edits

The recipe imports shared/lib/java_source.py (classify_lines / is_live_code /
strip_comments_and_strings) — a module contract owned by a different,
parallel task. These tests never depend on that module's real
implementation: they inject a controllable fake into ``sys.modules`` via
``monkeypatch`` before loading apply.py, so the tests are exercising only
apply.py's own logic against the frozen contract.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = (
    ROOT
    / ".claude/skills/java-migration-skill-registry/1.7"
    / "jade-recipe-1.7-strings-in-switch/scripts/apply.py"
)

JAVAC = shutil.which("javac")


def _make_fake_java_source(live: bool):
    """Stub for the shared/lib/java_source.py contract.

    ``live`` controls what is_live_code() reports for every query — enough
    granularity for these tests, which each ask a single yes/no question
    about one flagged if-statement.
    """
    import types

    mod = types.ModuleType("java_source")

    def classify_lines(source: str) -> list[str]:
        n = len(source.splitlines())
        return ["code" if live else "comment"] * n

    def is_live_code(source: str, line_number: int) -> bool:
        return live

    def strip_comments_and_strings(source: str) -> str:
        return source

    mod.classify_lines = classify_lines
    mod.is_live_code = is_live_code
    mod.strip_comments_and_strings = strip_comments_and_strings
    return mod


def load_apply(monkeypatch: pytest.MonkeyPatch, *, live: bool = True):
    """Import apply.py fresh with a fake java_source pre-seeded into
    sys.modules — so the import succeeds regardless of whether the real
    shared/lib/java_source.py exists yet (it is written by a parallel task)."""
    monkeypatch.setitem(sys.modules, "java_source", _make_fake_java_source(live))
    spec = importlib.util.spec_from_file_location("strings_in_switch_apply", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def run_apply(monkeypatch, tmp_path, java_src: str, flag_line: int, *, live: bool = True):
    """Write *java_src* to Example.java under tmp_path, run apply.main()
    against it, and return (returncode, result_dict, new_file_text)."""
    module = load_apply(monkeypatch, live=live)
    fp = tmp_path / "Example.java"
    fp.write_text(java_src, encoding="utf-8")

    monkeypatch.setattr(
        sys, "argv", ["apply.py", "--file", str(fp), "--line", str(flag_line)]
    )
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = module.main()

    result = json.loads(buf.getvalue().strip())
    return rc, result, fp.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Fixtures — small Java sources exercising Pattern A (sequential if-return)
# and Pattern B (if-else-if-else)
# ---------------------------------------------------------------------------

# Pattern A: three branches, each a braced if-block ending in return/throw.
PATTERN_A_SRC = """public class Example {
    public String pick(String cmd) {
        if (cmd.equals("A")) {
// JADE-FLAG:STRINGS_IN_SWITCH
            return "Alpha";
        }
        if (cmd.equals("B")) {
// JADE-FLAG:STRINGS_IN_SWITCH
            return "Beta";
        }
        if (cmd.equals("C")) {
// JADE-FLAG:STRINGS_IN_SWITCH
            return "Gamma";
        }
        return "Unknown";
    }
}
"""
PATTERN_A_FLAG_LINE = 4  # the "// JADE-FLAG..." line after if(cmd.equals("A"))

# Pattern A with a throw in the first branch, return in the second.
PATTERN_A_THROW_SRC = """public class Example {
    public int parse(String code) {
        if (code.equals("X")) {
// JADE-FLAG:STRINGS_IN_SWITCH
            throw new IllegalArgumentException("X not supported");
        }
        if (code.equals("Y")) {
            return 2;
        }
        return 0;
    }
}
"""
PATTERN_A_THROW_FLAG_LINE = 4

# Pattern B: if/else-if/else, each branch just assigns (no return/throw) —
# these branches DO need a break; regression guard for defect (a).
PATTERN_B_SRC = """public class Example {
    public String pick(String cmd) {
        String result;
        if (cmd.equals("A")) {
// JADE-FLAG:STRINGS_IN_SWITCH
            result = "Alpha";
        }
        else if (cmd.equals("B")) {
            result = "Beta";
        }
        else {
            result = "Unknown";
        }
        return result;
    }
}
"""
PATTERN_B_FLAG_LINE = 5

# The if-chain sitting inside a /* ... */ comment block — defect (c).
COMMENTED_OUT_SRC = """public class Example {
    public String pick(String cmd) {
        /*
        if (cmd.equals("A")) {
// JADE-FLAG:STRINGS_IN_SWITCH
            return "Alpha";
        }
        if (cmd.equals("B")) {
            return "Beta";
        }
        */
        return "Unknown";
    }
}
"""
COMMENTED_OUT_FLAG_LINE = 5


# ---------------------------------------------------------------------------
# (a) no unreachable `break;` after return/throw
# ---------------------------------------------------------------------------


def test_case_ending_in_return_gets_no_trailing_break(monkeypatch, tmp_path):
    rc, result, new_src = run_apply(monkeypatch, tmp_path, PATTERN_A_SRC, PATTERN_A_FLAG_LINE)

    assert rc == 0
    assert result["status"] == "FIXED"
    # Every case must end its statement with no break directly following
    # a return — i.e. "return ...;" must never be immediately followed by
    # a "break;" line for the same case.
    lines = new_src.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("return ") and stripped.endswith(";"):
            # the next non-blank line must not be a bare `break;`
            nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
            assert nxt != "break;", f"unreachable break after: {line!r}"
    assert "break;" not in new_src


def test_case_ending_in_throw_gets_no_trailing_break(monkeypatch, tmp_path):
    rc, result, new_src = run_apply(
        monkeypatch, tmp_path, PATTERN_A_THROW_SRC, PATTERN_A_THROW_FLAG_LINE
    )

    assert rc == 0
    assert result["status"] == "FIXED"
    lines = new_src.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("throw ") and stripped.endswith(";"):
            nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
            assert nxt != "break;", f"unreachable break after: {line!r}"


def test_case_not_ending_in_return_still_gets_break(monkeypatch, tmp_path):
    """Regression guard: branches that do NOT end in return/throw must keep
    their break — the fix for (a) must not remove breaks that are needed."""
    rc, result, new_src = run_apply(monkeypatch, tmp_path, PATTERN_B_SRC, PATTERN_B_FLAG_LINE)

    assert rc == 0
    assert result["status"] == "FIXED"
    # Two non-default cases (A, B) each assign then need a break.
    assert new_src.count("break;") == 2


# ---------------------------------------------------------------------------
# (b) original if/else-if chain is replaced, not kept alongside the switch
# ---------------------------------------------------------------------------


def test_original_if_chain_is_removed_not_duplicated(monkeypatch, tmp_path):
    rc, result, new_src = run_apply(monkeypatch, tmp_path, PATTERN_A_SRC, PATTERN_A_FLAG_LINE)

    assert rc == 0
    assert result["status"] == "FIXED"
    assert new_src.count("switch (cmd)") == 1
    # None of the original if(...) branch lines may survive.
    assert 'if (cmd.equals("A"))' not in new_src
    assert 'if (cmd.equals("B"))' not in new_src
    assert 'if (cmd.equals("C"))' not in new_src
    # Each literal appears exactly once, as a case label.
    for literal in ("A", "B", "C"):
        assert new_src.count(f'"{literal}"') == 1
    # The flag markers are gone (they lived only in the removed range).
    assert "JADE-FLAG:STRINGS_IN_SWITCH" not in new_src
    # Unrelated trailing code survives untouched.
    assert 'return "Unknown";' in new_src


def test_if_else_chain_is_removed_not_duplicated(monkeypatch, tmp_path):
    rc, result, new_src = run_apply(monkeypatch, tmp_path, PATTERN_B_SRC, PATTERN_B_FLAG_LINE)

    assert rc == 0
    assert result["status"] == "FIXED"
    assert new_src.count("switch (cmd)") == 1
    assert "else if" not in new_src
    assert 'if (cmd.equals("A"))' not in new_src
    assert "default:" in new_src
    assert 'result = "Unknown";' in new_src
    assert "return result;" in new_src


# ---------------------------------------------------------------------------
# (c) flagged location inside a comment -> SKIPPED, zero edits
# ---------------------------------------------------------------------------


def test_commented_out_chain_is_skipped_with_zero_edits(monkeypatch, tmp_path):
    rc, result, new_src = run_apply(
        monkeypatch,
        tmp_path,
        COMMENTED_OUT_SRC,
        COMMENTED_OUT_FLAG_LINE,
        live=False,
    )

    assert rc == 0
    assert result["status"] == "SKIPPED"
    assert result["changes"] == 0
    assert any("comment" in w.lower() for w in result["warnings"])
    # Zero edits: file content is byte-for-byte identical to the input.
    assert new_src == COMMENTED_OUT_SRC


def test_live_code_is_not_affected_by_comment_guard(monkeypatch, tmp_path):
    """Sanity check that the (c) guard does not also block live code."""
    rc, result, new_src = run_apply(
        monkeypatch, tmp_path, PATTERN_A_SRC, PATTERN_A_FLAG_LINE, live=True
    )
    assert rc == 0
    assert result["status"] == "FIXED"
    assert "switch (cmd)" in new_src


# ---------------------------------------------------------------------------
# Compiles: the generated switch must be valid Java (no unreachable stmt)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(JAVAC is None, reason="javac not available on PATH")
@pytest.mark.parametrize(
    "src,flag_line",
    [
        (PATTERN_A_SRC, PATTERN_A_FLAG_LINE),
        (PATTERN_A_THROW_SRC, PATTERN_A_THROW_FLAG_LINE),
        (PATTERN_B_SRC, PATTERN_B_FLAG_LINE),
    ],
)
def test_generated_switch_compiles(monkeypatch, tmp_path, src, flag_line):
    rc, result, new_src = run_apply(monkeypatch, tmp_path, src, flag_line)
    assert rc == 0
    assert result["status"] == "FIXED"

    java_file = tmp_path / "Example.java"
    java_file.write_text(new_src, encoding="utf-8")

    proc = subprocess.run(
        [JAVAC, "-d", str(tmp_path), str(java_file)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"javac failed:\nstdout={proc.stdout}\nstderr={proc.stderr}\n"
        f"--- generated source ---\n{new_src}"
    )
    assert "unreachable statement" not in proc.stderr
