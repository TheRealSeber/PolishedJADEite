import json

import pytest


def test_run_config_has_required_keys(artifacts_dir):
    path = artifacts_dir / "00-run-config.json"
    if not path.exists():
        pytest.skip(f"{path} not found")
    cfg = json.loads(path.read_text(encoding="utf-8"))
    assert cfg["run_id"]
    assert cfg["workspace_path"]
    assert cfg["artifacts_path"]
    assert cfg["source_version"]
    assert cfg["target_version"]


def test_run_state_has_required_keys(artifacts_dir):
    path = artifacts_dir / "00-run-state.json"
    if not path.exists():
        pytest.skip(f"{path} not found")
    state = json.loads(path.read_text(encoding="utf-8"))
    assert state["run_id"]
    assert state["state"] in {
        "INIT",
        "WORKSPACE_READY",
        "MANIFEST_READY",
        "TOOLING_SCOUT_READY",
        "BUILD_GATE_READY",
        "SCAN_READY",
        "RULE_BATCH_LOOP",
        "RULE_RETRY",
        "RULE_ESCALATE",
        "VERIFIED",
        "DONE",
        "FAILED",
        "AWAITING_SOURCE_INPUT",
    }
    assert "updated_at" in state


def test_manifest_has_valid_rules(artifacts_dir):
    path = artifacts_dir / "01-breaking-changes-manifest.json"
    if not path.exists():
        pytest.skip(f"{path} not found")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    rules = manifest["rules"]
    assert isinstance(rules, list)
    for rule in rules:
        assert "id" in rule
        assert "name" in rule
        assert "severity" in rule
        assert "patterns" in rule
        assert "fix_strategy" in rule
        assert rule["fix_strategy"].startswith("recipe:")
        assert "evidence_ref" in rule
        assert "evidence_hash" in rule
        assert isinstance(rule.get("confidence", 0), (int, float))
        assert rule.get("confidence", 0) >= 0.7
        assert "match_pattern" in rule
        for pattern in rule["patterns"]:
            assert "pattern" in pattern
            assert "target_extensions" in pattern


def test_flag_index_has_flags_list(artifacts_dir):
    path = artifacts_dir / "04-flag-index.json"
    if not path.exists():
        pytest.skip(f"{path} not found")
    idx = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(idx["flags"], list)
    if idx["flags"]:
        flag = idx["flags"][0]
        assert "rule_id" in flag
        assert "file" in flag
        assert "line" in flag


def test_scan_summary_has_counts(artifacts_dir):
    path = artifacts_dir / "04-scan-summary.json"
    if not path.exists():
        pytest.skip(f"{path} not found")
    summary = json.loads(path.read_text(encoding="utf-8"))
    assert summary["total_files_scanned"] >= 0
    assert "by_rule" in summary


def test_rule_queue_is_sequential(artifacts_dir):
    path = artifacts_dir / "05-rule-queue.json"
    if not path.exists():
        pytest.skip(f"{path} not found")
    queue = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(queue["rules"], list)


def test_phase_history_is_valid_jsonl(artifacts_dir):
    path = artifacts_dir / "phase-history.log.jsonl"
    if not path.exists():
        pytest.skip(f"{path} not found")
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        assert "ts" in entry
        assert "phase" in entry
        assert "status" in entry
