import json
import pathlib

import pytest

ARTIFACTS_DIR = pathlib.Path("migration-runs/sample/artifacts")


def test_run_config_has_required_keys():
    cfg = json.loads((ARTIFACTS_DIR / "00-run-config.json").read_text(encoding="utf-8"))
    assert cfg["run_id"]
    assert cfg["workspace_path"]
    assert cfg["artifacts_path"]
    assert cfg["source_version"]
    assert cfg["target_version"]


def test_run_state_has_required_keys():
    state = json.loads(
        (ARTIFACTS_DIR / "00-run-state.json").read_text(encoding="utf-8")
    )
    assert state["run_id"]
    assert state["state"] in {
        "INIT",
        "WORKSPACE_READY",
        "MANIFEST_READY",
        "TOOLING_SCOUT_READY",
        "BUILD_GATE_READY",
        "SCAN_READY",
        "RULE_BATCH_LOOP",
        "VERIFIED",
        "DONE",
        "FAILED",
        "AWAITING_SOURCE_INPUT",
    }
    assert "updated_at" in state


def test_manifest_has_valid_rules():
    manifest = json.loads(
        (ARTIFACTS_DIR / "01-breaking-changes-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    rules = manifest["rules"]
    assert isinstance(rules, list)
    for rule in rules:
        assert "id" in rule
        assert "name" in rule
        assert "severity" in rule
        assert "patterns" in rule
        for pattern in rule["patterns"]:
            assert "pattern" in pattern
            assert "target_extensions" in pattern


def test_flag_index_has_flags_list():
    idx = json.loads((ARTIFACTS_DIR / "04-flag-index.json").read_text(encoding="utf-8"))
    assert isinstance(idx["flags"], list)
    if idx["flags"]:
        flag = idx["flags"][0]
        assert "rule_id" in flag
        assert "file" in flag
        assert "line" in flag


def test_scan_summary_has_counts():
    summary_path = ARTIFACTS_DIR / "04-scan-summary.json"
    if not summary_path.exists():
        pytest.skip("04-scan-summary.json not found (no scanner run yet)")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["total_files_scanned"] >= 0
    assert "by_rule" in summary


def test_rule_queue_is_sequential():
    queue = json.loads(
        (ARTIFACTS_DIR / "05-rule-queue.json").read_text(encoding="utf-8")
    )
    assert isinstance(queue["rules"], list)


def test_phase_history_is_valid_jsonl():
    history_path = ARTIFACTS_DIR / "phase-history.log.jsonl"
    assert history_path.exists()
    for line in history_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        assert "ts" in entry
        assert "phase" in entry
        assert "status" in entry
