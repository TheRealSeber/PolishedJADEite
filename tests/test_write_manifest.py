import json
import pathlib
import subprocess
import sys

MANIFEST_SCRIPT = pathlib.Path(
    ".claude/skills/jade-core-change-collector/scripts/write_manifest.py"
)


def _run(tmp_path, rules):
    inp = tmp_path / "input.json"
    inp.write_text(json.dumps(rules), encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(MANIFEST_SCRIPT),
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
        ],
        capture_output=True,
        text=True,
    )


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


def test_rejects_missing_evidence(tmp_path):
    rule = _valid_rule()
    del rule["evidence_ref"]
    result = _run(tmp_path, [rule])
    assert result.returncode == 2
    combined = result.stdout + result.stderr
    assert "evidence_ref" in combined


def test_rejects_low_confidence(tmp_path):
    rule = _valid_rule(confidence=0.4)
    result = _run(tmp_path, [rule])
    assert result.returncode == 2
    combined = (result.stdout + result.stderr).lower()
    assert "confidence" in combined


def test_rejects_missing_fix_strategy(tmp_path):
    rule = _valid_rule(fix_strategy="")
    result = _run(tmp_path, [rule])
    assert result.returncode == 2
    combined = result.stdout + result.stderr
    assert "fix_strategy" in combined


def test_accepts_valid_rule(tmp_path):
    result = _run(tmp_path, [_valid_rule()])
    assert result.returncode == 0
    assert (tmp_path / "01-breaking-changes-manifest.json").exists()
