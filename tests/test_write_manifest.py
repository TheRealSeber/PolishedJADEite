import json
import pathlib
import subprocess
import sys

MANIFEST_SCRIPT = pathlib.Path(
    ".claude/skills/jade-core-change-collector/scripts/write_manifest.py"
)


def _run(tmp_path, rules, extra_args=None):
    inp = tmp_path / "input.json"
    inp.write_text(json.dumps(rules), encoding="utf-8")
    cmd = [
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
    ]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(cmd, capture_output=True, text=True)


EVIDENCE_HASH = "dd251f683048fa9e882155b9e5aeccad9a46605bde50cac26741a564a2833a35"
OTHER_HASH = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _write_source_index(tmp_path, sources):
    idx_path = tmp_path / "01-source-index.json"
    idx_path.write_text(json.dumps({"sources": sources}), encoding="utf-8")


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


# --- Evidence policy tests ---


def test_rejects_rule_with_evidence_label_not_in_source_index(tmp_path):
    _write_source_index(
        tmp_path,
        [
            {
                "source_label": "other-source",
                "content_hash": EVIDENCE_HASH,
                "is_official": True,
                "fetch_status": "success",
            }
        ],
    )
    result = _run(tmp_path, [_valid_rule()])
    assert result.returncode == 2
    combined = result.stdout + result.stderr
    assert "source_label" in combined or "not found" in combined


def test_rejects_non_official_evidence_in_production(tmp_path):
    _write_source_index(
        tmp_path,
        [
            {
                "source_label": "mock-sources",
                "content_hash": EVIDENCE_HASH,
                "is_official": False,
                "fetch_status": "success",
            }
        ],
    )
    result = _run(tmp_path, [_valid_rule()])
    assert result.returncode == 2
    combined = (result.stdout + result.stderr).lower()
    assert "non-official" in combined or "not official" in combined


def test_rejects_evidence_hash_mismatch(tmp_path):
    _write_source_index(
        tmp_path,
        [
            {
                "source_label": "mock-sources",
                "content_hash": OTHER_HASH,
                "is_official": True,
                "fetch_status": "success",
            }
        ],
    )
    result = _run(tmp_path, [_valid_rule()])
    assert result.returncode == 2
    combined = (result.stdout + result.stderr).lower()
    assert "hash" in combined


def test_rejects_malformed_evidence_ref_in_production(tmp_path):
    _write_source_index(
        tmp_path,
        [
            {
                "source_label": "mock-sources",
                "content_hash": EVIDENCE_HASH,
                "is_official": True,
                "fetch_status": "success",
            }
        ],
    )
    rule = _valid_rule(evidence_ref="malformed-ref-without-separator")
    result = _run(tmp_path, [rule])
    assert result.returncode == 2
    combined = result.stdout + result.stderr
    assert "malformed" in combined or "::" in combined


def test_allows_legacy_evidence_ref_in_development_with_warning(tmp_path):
    _write_source_index(
        tmp_path,
        [
            {
                "source_label": "mock-sources",
                "content_hash": EVIDENCE_HASH,
                "is_official": True,
                "fetch_status": "success",
            }
        ],
    )
    rule = _valid_rule(evidence_ref="malformed-ref-without-separator")
    result = _run(tmp_path, [rule], extra_args=["--source-policy-mode", "development"])
    assert result.returncode == 0
    combined = (result.stdout + result.stderr).lower()
    assert "warning" in combined or "legacy" in combined


def test_accepts_valid_rule_with_matching_official_source_index(tmp_path):
    _write_source_index(
        tmp_path,
        [
            {
                "source_label": "mock-sources",
                "content_hash": EVIDENCE_HASH,
                "is_official": True,
                "fetch_status": "success",
            }
        ],
    )
    result = _run(tmp_path, [_valid_rule()])
    assert result.returncode == 0
    assert (tmp_path / "01-breaking-changes-manifest.json").exists()
