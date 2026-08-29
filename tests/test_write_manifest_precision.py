"""Tests for the precision-gate extension of write_manifest.py.

Test 28 (compatibility) is the load-bearing one: absent --precision-report
and absent a precision_gate config block, output must be byte-identical
(module "generated_at" timestamp aside) to the pre-precision-gate script,
fetched straight from git so there is no risk of the golden fixture and the
implementation drifting together.
"""

import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).parents[1]
MANIFEST_SCRIPT = ROOT / ".claude/skills/jade-core-change-collector/scripts/write_manifest.py"


def _valid_rule(**overrides):
    r = {
        "id": "VALID",
        "name": "Valid Rule",
        "severity": "HIGH",
        "fix_strategy": "recipe:jade-recipe-dummy",
        "match_pattern": "class",
        "confidence": 0.95,
        "evidence_ref": "mock-sources::lines 1-5",
        "evidence_hash": "dd251f683048fa9e882155b9e5aeccad9a46605bde50cac26741a564a2833a35",
        "patterns": [
            {
                "type": "regex",
                "pattern": "class",
                "target_extensions": [".java"],
                "reason": "test",
                "confidence": "HIGH",
            }
        ],
    }
    r.update(overrides)
    return r


def _run(script, tmp_path, rules, extra_args=None):
    inp = tmp_path / "input.json"
    inp.write_text(json.dumps(rules), encoding="utf-8")
    cmd = [
        sys.executable,
        str(script),
        "--input",
        str(inp),
        "--artifacts-dir",
        str(tmp_path),
        "--run-id",
        "test",
        "--source-version",
        "1.5",
        "--target-version",
        "1.6",
    ]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(cmd, capture_output=True, text=True)


def _strip_generated_at(manifest_text: str) -> dict:
    data = json.loads(manifest_text)
    data.pop("generated_at", None)
    return data


@pytest.fixture(scope="module")
def golden_script(tmp_path_factory):
    """The write_manifest.py exactly as committed at HEAD, before this
    phase's precision-gate edits -- fetched from git, not hand-copied, so
    the golden reference can never silently drift from what was actually
    the prior behavior."""
    result = subprocess.run(
        ["git", "show", "HEAD:.claude/skills/jade-core-change-collector/scripts/write_manifest.py"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 0, result.stderr
    out_dir = tmp_path_factory.mktemp("golden")
    path = out_dir / "write_manifest_golden.py"
    path.write_text(result.stdout, encoding="utf-8")
    return path


# --- Test 28: compatibility ---------------------------------------------


def test_golden_compare_no_report_no_config(tmp_path, golden_script):
    rule = _valid_rule()

    old_dir = tmp_path / "old"
    new_dir = tmp_path / "new"
    old_dir.mkdir()
    new_dir.mkdir()

    old_result = _run(golden_script, old_dir, [rule])
    new_result = _run(MANIFEST_SCRIPT, new_dir, [rule])

    assert old_result.returncode == new_result.returncode == 0

    old_manifest = _strip_generated_at(
        (old_dir / "01-breaking-changes-manifest.json").read_text(encoding="utf-8")
    )
    new_manifest = _strip_generated_at(
        (new_dir / "01-breaking-changes-manifest.json").read_text(encoding="utf-8")
    )
    assert old_manifest == new_manifest
    assert "pattern_precision" not in new_manifest["rules"][0]
    assert "queue_eligible" not in new_manifest["rules"][0]


# --- Test 29: --precision-report injects fields -----------------------------


def _report_entry(**overrides):
    entry = {
        "status": "PASS",
        "queue_eligible": True,
        "pattern_precision": 0.95,
        "judged": 10,
        "true_positive": 10,
        "false_positive": 0,
        "undecidable": 0,
        "wilson_95": [0.7, 1.0],
        "effective_min_precision": 0.7,
        "pattern_revision": 1,
        "sample_artifact": "01.5-precision-sample-VALID.json",
        "sample_hash": "samplehash",
        "verdicts_artifact": "01.5-precision-verdicts-VALID.json",
        "verdicts_hash": "verdictshash",
        "false_positive_classes": {},
        "counterexamples": [],
        "population": {"total_hits": 10, "files_with_hits": 3},
    }
    entry.update(overrides)
    return entry


def _write_report(artifacts_dir, rules_map):
    (artifacts_dir / "01.5-precision-report.json").write_text(
        json.dumps({"schema_version": 1, "run_id": "test", "rules": rules_map}), encoding="utf-8"
    )


def test_precision_report_injects_pattern_precision_and_queue_eligible(tmp_path):
    _write_report(tmp_path, {"VALID": _report_entry()})
    result = _run(MANIFEST_SCRIPT, tmp_path, [_valid_rule()], extra_args=["--precision-report", str(tmp_path / "01.5-precision-report.json")])
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads((tmp_path / "01-breaking-changes-manifest.json").read_text(encoding="utf-8"))
    rule = manifest["rules"][0]
    assert rule["queue_eligible"] is True
    assert rule["pattern_precision"]["value"] == 0.95
    assert rule["pattern_precision"]["status"] == "PASS"
    assert rule["pattern_precision"]["report_artifact"] == "01.5-precision-report.json"


# --- Test 30/31: FORGED_PRECISION --------------------------------------------


def test_forged_precision_without_report_exits_2(tmp_path):
    rule = _valid_rule(pattern_precision={"value": 0.99}, queue_eligible=True)
    result = _run(MANIFEST_SCRIPT, tmp_path, [rule])
    assert result.returncode == 2
    combined = result.stdout + result.stderr
    assert "FORGED_PRECISION" in combined
    assert not (tmp_path / "01-breaking-changes-manifest.json").exists()


def test_forged_precision_contradicting_report_exits_2(tmp_path):
    _write_report(tmp_path, {"VALID": _report_entry(pattern_precision=0.95)})
    rule = _valid_rule(pattern_precision={"value": 0.01}, queue_eligible=False)
    result = _run(
        MANIFEST_SCRIPT,
        tmp_path,
        [rule],
        extra_args=["--precision-report", str(tmp_path / "01.5-precision-report.json")],
    )
    assert result.returncode == 2
    combined = result.stdout + result.stderr
    assert "FORGED_PRECISION" in combined
    assert not (tmp_path / "01-breaking-changes-manifest.json").exists()


# --- Test 32: --require-precision ---------------------------------------------


def test_require_precision_missing_rule_exits_2(tmp_path):
    _write_report(tmp_path, {"OTHER_RULE": _report_entry()})
    result = _run(
        MANIFEST_SCRIPT,
        tmp_path,
        [_valid_rule()],
        extra_args=[
            "--precision-report",
            str(tmp_path / "01.5-precision-report.json"),
            "--require-precision",
        ],
    )
    assert result.returncode == 2
    assert "PRECISION_COVERAGE_MISSING" in (result.stdout + result.stderr)


def test_require_precision_satisfied_passes(tmp_path):
    _write_report(tmp_path, {"VALID": _report_entry()})
    result = _run(
        MANIFEST_SCRIPT,
        tmp_path,
        [_valid_rule()],
        extra_args=[
            "--precision-report",
            str(tmp_path / "01.5-precision-report.json"),
            "--require-precision",
        ],
    )
    assert result.returncode == 0, result.stdout + result.stderr


# --- Test 33: manifest_evidence digest vs full -------------------------------


def test_manifest_evidence_digest_caps_at_five_no_context(tmp_path):
    cfg = {"run_id": "test", "artifacts_path": str(tmp_path), "precision_gate": {"enabled": True, "manifest_evidence": "digest"}}
    (tmp_path / "00-run-config.json").write_text(json.dumps(cfg), encoding="utf-8")
    counterexamples = [
        {"hit_id": f"h{i}", "file": "A.java", "line": i, "line_text": f"line {i}", "false_positive_class": "OTHER", "reason": "x"}
        for i in range(8)
    ]
    _write_report(tmp_path, {"VALID": _report_entry(counterexamples=counterexamples)})
    result = _run(
        MANIFEST_SCRIPT,
        tmp_path,
        [_valid_rule()],
        extra_args=["--precision-report", str(tmp_path / "01.5-precision-report.json")],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads((tmp_path / "01-breaking-changes-manifest.json").read_text(encoding="utf-8"))
    ces = manifest["rules"][0]["pattern_precision"]["counterexamples"]
    assert len(ces) <= 5
    for ce in ces:
        assert "context_before" not in ce
        assert "context_after" not in ce


def test_manifest_evidence_full_pastes_everything_with_context(tmp_path):
    cfg = {"run_id": "test", "artifacts_path": str(tmp_path), "precision_gate": {"enabled": True, "manifest_evidence": "full"}}
    (tmp_path / "00-run-config.json").write_text(json.dumps(cfg), encoding="utf-8")

    sample = {
        "hits": [
            {"hit_id": f"h{i}", "file": "A.java", "line": i, "line_text": f"line {i}", "context_before": ["b"], "context_after": ["a"]}
            for i in range(8)
        ]
    }
    (tmp_path / "01.5-precision-sample-VALID.json").write_text(json.dumps(sample), encoding="utf-8")
    verdicts = {"verdicts": [{"hit_id": f"h{i}", "verdict": "TRUE_POSITIVE", "reason": "ok"} for i in range(8)]}
    (tmp_path / "01.5-precision-verdicts-VALID.json").write_text(json.dumps(verdicts), encoding="utf-8")

    _write_report(
        tmp_path,
        {
            "VALID": _report_entry(
                counterexamples=[{"hit_id": "h0"}],  # deliberately sparse; full mode ignores this
                sample_artifact="01.5-precision-sample-VALID.json",
                verdicts_artifact="01.5-precision-verdicts-VALID.json",
            )
        },
    )
    result = _run(
        MANIFEST_SCRIPT,
        tmp_path,
        [_valid_rule()],
        extra_args=["--precision-report", str(tmp_path / "01.5-precision-report.json")],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads((tmp_path / "01-breaking-changes-manifest.json").read_text(encoding="utf-8"))
    ces = manifest["rules"][0]["pattern_precision"]["counterexamples"]
    assert len(ces) == 8
    assert all("context_before" in ce and "context_after" in ce for ce in ces)


# --- THRESHOLD_WEAKENED (write_manifest.py's half of test 22, see section 3:
# the CLI spec assigns min_pattern_precision enforcement to write_manifest.py,
# not the scorer -- score_pattern_precision.py's test 22 only covers a rule
# raising its own threshold above the policy floor being respected) ----------


def test_threshold_weakened_rejected(tmp_path):
    cfg = {
        "run_id": "test",
        "artifacts_path": str(tmp_path),
        "precision_gate": {"enabled": True, "min_precision": 0.7},
    }
    (tmp_path / "00-run-config.json").write_text(json.dumps(cfg), encoding="utf-8")

    rule = _valid_rule(min_pattern_precision=0.5)  # below the 0.7 run threshold
    result = _run(MANIFEST_SCRIPT, tmp_path, [rule])
    assert result.returncode == 2
    assert "THRESHOLD_WEAKENED" in (result.stdout + result.stderr)


def test_threshold_raised_above_floor_allowed(tmp_path):
    cfg = {
        "run_id": "test",
        "artifacts_path": str(tmp_path),
        "precision_gate": {"enabled": True, "min_precision": 0.7},
    }
    (tmp_path / "00-run-config.json").write_text(json.dumps(cfg), encoding="utf-8")

    rule = _valid_rule(min_pattern_precision=0.9)  # above the 0.7 run threshold
    result = _run(MANIFEST_SCRIPT, tmp_path, [rule])
    assert result.returncode == 0, result.stdout + result.stderr


# --- Test 34: STALE_PATTERN_REVISION -----------------------------------------


def test_stale_pattern_revision_rejected(tmp_path):
    cfg = {"run_id": "test", "artifacts_path": str(tmp_path), "precision_gate": {"enabled": True}}
    (tmp_path / "00-run-config.json").write_text(json.dumps(cfg), encoding="utf-8")

    old_rule = _valid_rule(pattern_revision=1)
    (tmp_path / "01-breaking-changes-manifest.json").write_text(
        json.dumps({"rules": [old_rule]}), encoding="utf-8"
    )

    changed_rule = _valid_rule(
        pattern_revision=1,
        patterns=[
            {
                "type": "regex",
                "pattern": "different-pattern",
                "target_extensions": [".java"],
                "reason": "test",
                "confidence": "HIGH",
            }
        ],
    )
    result = _run(MANIFEST_SCRIPT, tmp_path, [changed_rule])
    assert result.returncode == 2
    assert "STALE_PATTERN_REVISION" in (result.stdout + result.stderr)


def test_pattern_revision_bump_without_pattern_change_allowed(tmp_path):
    cfg = {"run_id": "test", "artifacts_path": str(tmp_path), "precision_gate": {"enabled": True}}
    (tmp_path / "00-run-config.json").write_text(json.dumps(cfg), encoding="utf-8")

    old_rule = _valid_rule(pattern_revision=1)
    (tmp_path / "01-breaking-changes-manifest.json").write_text(
        json.dumps({"rules": [old_rule]}), encoding="utf-8"
    )

    bumped_rule = _valid_rule(pattern_revision=2)  # same patterns, just a revision bump
    result = _run(MANIFEST_SCRIPT, tmp_path, [bumped_rule])
    assert result.returncode == 0, result.stdout + result.stderr


def test_pattern_change_with_revision_bump_allowed(tmp_path):
    cfg = {"run_id": "test", "artifacts_path": str(tmp_path), "precision_gate": {"enabled": True}}
    (tmp_path / "00-run-config.json").write_text(json.dumps(cfg), encoding="utf-8")

    old_rule = _valid_rule(pattern_revision=1)
    (tmp_path / "01-breaking-changes-manifest.json").write_text(
        json.dumps({"rules": [old_rule]}), encoding="utf-8"
    )

    changed_rule = _valid_rule(
        pattern_revision=2,
        patterns=[
            {
                "type": "regex",
                "pattern": "different-pattern",
                "target_extensions": [".java"],
                "reason": "test",
                "confidence": "HIGH",
            }
        ],
    )
    result = _run(MANIFEST_SCRIPT, tmp_path, [changed_rule])
    assert result.returncode == 0, result.stdout + result.stderr
