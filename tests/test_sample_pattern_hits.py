"""Tests for sample_pattern_hits.py (precision gate, phase 1).

Population parity with the real scanner is the critical property here: the
sampler must see exactly the set of locations scan_and_tag.py would flag,
computed via the same collect_candidate_files/_comment_skip_prefixes logic
(imported by path, never re-implemented) so precision measured on the
sample generalizes to what the pipeline will actually inject.
"""

import hashlib
import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).parents[1]
SAMPLER = ROOT / ".claude/skills/jade-core-change-collector/scripts/sample_pattern_hits.py"
SCANNER = ROOT / ".claude/skills/jade-core-scanner/scripts/scan_and_tag.py"

CAST_PATTERN = r"\(\s*\w+\.\w+\s*\)"


def load_sampler():
    spec = importlib.util.spec_from_file_location("sample_pattern_hits_test", SAMPLER)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _rule(rule_id="R1", pattern=CAST_PATTERN, extra=None, target_extensions=None):
    rule = {
        "id": rule_id,
        "name": "Test rule",
        "description": "A test rule for the precision gate sampler.",
        "severity": "LOW",
        "fix_strategy": "recipe:x",
        "verification_hint": "n/a",
        "patterns": [
            {
                "type": "regex",
                "pattern": pattern,
                "target_extensions": target_extensions or [".java"],
                "reason": "test reason",
                "confidence": 0.8,
            }
        ],
    }
    if extra:
        rule.update(extra)
    return rule


def _setup(tmp_path, rule=None, files=None, precision_gate=None):
    artifacts = tmp_path / "artifacts"
    workspace = tmp_path / "workspace"
    artifacts.mkdir()
    workspace.mkdir()
    manifest = {"rules": [rule if rule is not None else _rule()]}
    (artifacts / "01-breaking-changes-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    cfg = {
        "run_id": "test-run",
        "artifacts_path": str(artifacts),
        "workspace_path": str(workspace),
    }
    if precision_gate is not None:
        cfg["precision_gate"] = precision_gate
    (artifacts / "00-run-config.json").write_text(json.dumps(cfg), encoding="utf-8")
    for rel, content in (files or {}).items():
        p = workspace / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return artifacts, workspace, cfg


def _run(artifacts, rule_id, extra_args=None, output=None):
    cmd = [
        sys.executable,
        str(SAMPLER),
        "--run-config",
        str(artifacts / "00-run-config.json"),
        "--rule-id",
        rule_id,
    ]
    if output is not None:
        cmd += ["--output", str(output)]
    if extra_args:
        cmd += extra_args
    return subprocess.run(cmd, capture_output=True, text=True)


BASIC_JAVA = """public class A {
    void m() {
        Object o = (Foo.Bar) x;
        // (Ignored.Comment) inside a comment line, must not match
        int y = 1;
        Object p = (Baz.Qux) y;
    }
}
"""


# --- Test 1: population parity with scan_and_tag.py -------------------------


def test_population_parity_with_scanner(tmp_path):
    rule = _rule("PARITY_RULE")
    artifacts, workspace, cfg = _setup(
        tmp_path,
        rule=rule,
        files={
            "src/A.java": BASIC_JAVA,
            "src/B.txt": "(Wrong.Ext) should not match, wrong extension\n",
            "target/Generated.java": "Object g = (Excluded.Dir) z;\n",
        },
    )
    output = artifacts / "sample.json"
    result = _run(artifacts, "PARITY_RULE", output=output)
    assert result.returncode == 1, result.stderr  # small population -> CENSUS
    sample = json.loads(output.read_text(encoding="utf-8"))
    sampler_locations = {(h["file"], h["line"]) for h in sample["hits"]}

    # Run the real scanner against an independent copy of the same workspace.
    scan_workspace = tmp_path / "scan_workspace"
    import shutil

    shutil.copytree(workspace, scan_workspace)
    scan_artifacts = tmp_path / "scan_artifacts"
    scan_artifacts.mkdir()
    (scan_artifacts / "01-breaking-changes-manifest.json").write_text(
        json.dumps({"rules": [rule]}), encoding="utf-8"
    )
    scan_result = subprocess.run(
        [
            sys.executable,
            str(SCANNER),
            "--workspace",
            str(scan_workspace),
            "--artifacts",
            str(scan_artifacts),
        ],
        capture_output=True,
        text=True,
    )
    assert scan_result.returncode == 0, scan_result.stderr
    flag_index = json.loads(
        (scan_artifacts / "04-flag-index.json").read_text(encoding="utf-8")
    )
    # The scanner records the line of the *injected comment* as it stands in
    # the FLAGGED file, one line after the match it belongs to. Injecting a
    # flag shifts every line below it, so those numbers cannot be compared to
    # the sampler's (which reads an unflagged copy) by subtracting a constant.
    # Compare on the invariant that actually matters at dispatch time: each
    # recorded line really is a flag line in the file on disk, and the line
    # directly above it is the matched source line.
    scanner_flags = [f for f in flag_index["flags"] if f["rule_id"] == "PARITY_RULE"]
    flagged_lines = (scan_workspace / "src" / "A.java").read_text(
        encoding="utf-8"
    ).splitlines()
    scanner_matched_text = set()
    for f in scanner_flags:
        assert "JADE-FLAG:PARITY_RULE" in flagged_lines[f["line"] - 1], (
            f"flag index line {f['line']} is not a flag line: "
            f"{flagged_lines[f['line'] - 1]!r}"
        )
        scanner_matched_text.add(flagged_lines[f["line"] - 2].strip())

    sampler_matched_text = {h["line_text"].strip() for h in sample["hits"]}
    assert sampler_matched_text == scanner_matched_text
    assert sampler_locations == {("src/A.java", 3), ("src/A.java", 6)}


# --- Test 2: determinism -----------------------------------------------------


def test_determinism_byte_identical(tmp_path):
    artifacts, workspace, cfg = _setup(tmp_path, files={"src/A.java": BASIC_JAVA})
    out1 = artifacts / "sample1.json"
    out2 = artifacts / "sample2.json"
    r1 = _run(artifacts, "R1", output=out1)
    r2 = _run(artifacts, "R1", output=out2)
    assert r1.returncode == r2.returncode  # both runs must classify identically
    assert out1.read_bytes() == out2.read_bytes()


# --- Test 3: nesting ----------------------------------------------------------


def test_nested_sample_prefix_property(tmp_path):
    files_content = "".join(f"Object o{i} = (F{i}.M{i}) x;\n" for i in range(20))
    artifacts, workspace, cfg = _setup(
        tmp_path,
        files={"src/Many.java": files_content},
        precision_gate={"enabled": True, "sample_size": 5},
    )
    out10 = artifacts / "sample10.json"
    out5 = artifacts / "sample5.json"
    r10 = _run(artifacts, "R1", extra_args=["--sample-size", "10"], output=out10)
    r5 = _run(artifacts, "R1", extra_args=["--sample-size", "5"], output=out5)
    assert r10.returncode == 0 and r5.returncode == 0
    sample10 = json.loads(out10.read_text(encoding="utf-8"))
    sample5 = json.loads(out5.read_text(encoding="utf-8"))
    assert sample10["status"] == "SAMPLED"
    assert sample5["status"] == "SAMPLED"
    assert len(sample10["hits"]) == 10
    assert len(sample5["hits"]) == 5
    assert sample10["hits"][:5] == sample5["hits"]


# --- Test 4: seed reacts to pattern/revision, not to workspace growth --------


def test_seed_reacts_to_pattern_not_to_new_files(tmp_path):
    sampler = load_sampler()
    seed_a = sampler.compute_seed("R1", 1, [CAST_PATTERN], "rule+pattern")
    seed_a_again = sampler.compute_seed("R1", 1, [CAST_PATTERN], "rule+pattern")
    assert seed_a == seed_a_again  # adding a workspace file never enters the seed

    seed_revision_bump = sampler.compute_seed("R1", 2, [CAST_PATTERN], "rule+pattern")
    assert seed_revision_bump != seed_a

    seed_pattern_change = sampler.compute_seed("R1", 1, [r"different"], "rule+pattern")
    assert seed_pattern_change != seed_a

    seed_rule_id_scope = sampler.compute_seed("R1", 99, ["ignored"], "rule_id")
    seed_rule_id_scope_again = sampler.compute_seed("R1", 1, ["also ignored"], "rule_id")
    assert seed_rule_id_scope == seed_rule_id_scope_again  # rule_id scope ignores pattern/revision


# --- Test 5: CENSUS -----------------------------------------------------------


def test_census_status_when_population_leq_sample_size(tmp_path):
    artifacts, workspace, cfg = _setup(tmp_path, files={"src/A.java": BASIC_JAVA})
    output = artifacts / "sample.json"
    result = _run(artifacts, "R1", output=output)
    assert result.returncode == 1  # CENSUS is an "attention" outcome
    sample = json.loads(output.read_text(encoding="utf-8"))
    assert sample["status"] == "CENSUS"
    assert sample["sample_size"] == sample["population"]["total_hits"] == 2
    assert len(sample["hits"]) == 2


# --- Test 6: NO_POPULATION ----------------------------------------------------


def test_no_population(tmp_path):
    artifacts, workspace, cfg = _setup(
        tmp_path, files={"src/A.java": "public class A { int x = 1; }\n"}
    )
    output = artifacts / "sample.json"
    result = _run(artifacts, "R1", output=output)
    assert result.returncode == 1
    sample = json.loads(output.read_text(encoding="utf-8"))
    assert sample["status"] == "NO_POPULATION"
    assert sample["hits"] == []
    assert sample["population"]["total_hits"] == 0


# --- Test 7: exclusions -------------------------------------------------------


def test_excludes_comments_dirs_and_wrong_extensions(tmp_path):
    artifacts, workspace, cfg = _setup(
        tmp_path,
        files={
            "src/A.java": BASIC_JAVA,
            "src/B.txt": "(Wrong.Ext) should not match\n",
            "build/Ignored.java": "Object g = (Excluded.Dir) z;\n",
            "target/Ignored2.java": "Object g = (Excluded.Dir) z;\n",
        },
    )
    output = artifacts / "sample.json"
    result = _run(artifacts, "R1", output=output)
    assert result.returncode == 1  # CENSUS with only 2 hits from A.java
    sample = json.loads(output.read_text(encoding="utf-8"))
    files_hit = {h["file"] for h in sample["hits"]}
    assert files_hit == {"src/A.java"}
    assert sample["population"]["total_hits"] == 2


# --- Test 8: context at file boundaries --------------------------------------


def test_context_clipped_at_file_boundaries(tmp_path):
    content = "Object o = (F0.M0) x;\nline2\nline3\nline4\nObject p = (F1.M1) y;\n"
    artifacts, workspace, cfg = _setup(tmp_path, files={"src/A.java": content})
    output = artifacts / "sample.json"
    result = _run(artifacts, "R1", output=output)
    assert result.returncode == 1
    sample = json.loads(output.read_text(encoding="utf-8"))
    by_line = {h["line"]: h for h in sample["hits"]}
    first_hit = by_line[1]
    assert first_hit["context_before"] == []
    assert len(first_hit["context_after"]) == 3
    last_hit = by_line[5]
    assert last_hit["context_after"] == []
    assert len(last_hit["context_before"]) == 3


# --- Test 9: --sample-size below run-config floor -----------------------------


def test_sample_size_below_floor_rejected(tmp_path):
    artifacts, workspace, cfg = _setup(
        tmp_path,
        files={"src/A.java": BASIC_JAVA},
        precision_gate={"enabled": True, "sample_size": 30},
    )
    result = _run(artifacts, "R1", extra_args=["--sample-size", "5"])
    assert result.returncode == 2
    assert "SAMPLE_SIZE_BELOW_FLOOR" in result.stderr


# --- Test 10: line truncation --------------------------------------------------


def test_long_line_is_truncated(tmp_path):
    long_line = "Object o = (Foo.Bar) x; " + ("z" * 500) + "\n"
    artifacts, workspace, cfg = _setup(tmp_path, files={"src/A.java": long_line})
    output = artifacts / "sample.json"
    result = _run(artifacts, "R1", output=output)
    sample = json.loads(output.read_text(encoding="utf-8"))
    hit = sample["hits"][0]
    assert hit["line_truncated"] is True
    assert len(hit["line_text"]) == 400


# --- Test 11: structural errors ------------------------------------------------


def test_rule_not_in_manifest_exits_2(tmp_path):
    artifacts, workspace, cfg = _setup(tmp_path, files={"src/A.java": BASIC_JAVA})
    result = _run(artifacts, "DOES_NOT_EXIST")
    assert result.returncode == 2
    assert "RULE_NOT_IN_MANIFEST" in result.stderr


def test_non_compiling_regex_exits_2(tmp_path):
    rule = _rule("BAD_REGEX", pattern="(unclosed")
    artifacts, workspace, cfg = _setup(tmp_path, rule=rule, files={"src/A.java": BASIC_JAVA})
    result = _run(artifacts, "BAD_REGEX")
    assert result.returncode == 2
    assert "PATTERN_COMPILE_ERROR" in result.stderr


def test_invalid_rule_id_exits_2(tmp_path):
    artifacts, workspace, cfg = _setup(tmp_path, files={"src/A.java": BASIC_JAVA})
    result = _run(artifacts, "bad rule id!")
    assert result.returncode == 2
    assert "INVALID_RULE_ID" in result.stderr


# --- Test 12: atomicity and dry-run --------------------------------------------


def test_atomic_write_leaves_no_tmp_file(tmp_path):
    artifacts, workspace, cfg = _setup(tmp_path, files={"src/A.java": BASIC_JAVA})
    output = artifacts / "sample.json"
    result = _run(artifacts, "R1", output=output)
    assert result.returncode in (0, 1)
    assert output.exists()
    leftovers = list(artifacts.glob("*.tmp")) + list(artifacts.glob(".sample-pattern-hits-*"))
    assert leftovers == []


def test_dry_run_creates_no_artifact(tmp_path):
    artifacts, workspace, cfg = _setup(tmp_path, files={"src/A.java": BASIC_JAVA})
    output = artifacts / "sample.json"
    result = _run(artifacts, "R1", extra_args=["--dry-run"], output=output)
    assert result.returncode in (0, 1)
    assert not output.exists()
