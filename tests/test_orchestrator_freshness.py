"""Tests for orchestrator graph freshness recording and guarded rebuild."""

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / ".claude/skills/jade-core-orchestrator/scripts/orchestrator.py"


def load_orchestrator():
    spec = importlib.util.spec_from_file_location("orchestrator_freshness_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def graph_payload():
    """A structurally valid 03.5 graph artifact (non-empty nodes/edges/stats)."""
    return {
        "schema_version": 2,
        "content_hash": "abc123",
        "source": {"java_files": 1},
        "source_identity": {"workspace": "ws"},
        "diagnostics": {
            "parse_failures": [],
            "unresolved_types": [],
            "ambiguous_symbols": [],
        },
        "nodes": {"core/AID.java": {"package": "jade.core", "class_name": "AID"}},
        "edges": {"imports": [{"from": "A.java", "to": "B.java"}]},
        "stats": {"total_files": 1, "total_edges": 1, "edge_counts": {"imports": 1}},
    }


def test_record_graph_freshness(tmp_path):
    orch = load_orchestrator()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    assert orch.record_graph_freshness(artifacts) is None

    (artifacts / "03.5-knowledge-graph.json").write_text(
        json.dumps(graph_payload()), encoding="utf-8"
    )
    fresh = orch.record_graph_freshness(artifacts)
    assert fresh["schema_version"] == 2
    assert fresh["content_hash"] == "abc123"
    assert fresh["java_files"] == 1


def test_gate_records_graph_freshness_into_state(tmp_path):
    orch = load_orchestrator()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "03.5-knowledge-graph.json").write_text(
        json.dumps(graph_payload()), encoding="utf-8"
    )
    state = {}
    outcome = orch.check_gate_artifacts("KNOWLEDGE_GRAPH_READY", artifacts, state)
    assert outcome == "OK"
    assert state["graph"] is not None
    assert state["graph"]["java_files"] == 1


def test_gate_stores_none_when_graph_missing(tmp_path):
    orch = load_orchestrator()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    state = {}
    # Required artifact is absent -> gate fails before freshness recording.
    outcome = orch.check_gate_artifacts("KNOWLEDGE_GRAPH_READY", artifacts, state)
    assert outcome == "ARTIFACT_MISSING"
    assert "graph" not in state


def test_rebuild_disabled_by_default_returns_true(tmp_path):
    orch = load_orchestrator()
    assert orch.rebuild_knowledge_graph(tmp_path, tmp_path, {}) is True
    assert orch.rebuild_knowledge_graph(
        tmp_path, tmp_path, {"rebuild_graph_per_batch": False}
    ) is True


def test_rebuild_enabled_failure_is_advisory(tmp_path, monkeypatch):
    orch = load_orchestrator()
    cfg = {"rebuild_graph_per_batch": True, "workspace_path": "ws"}

    def _fail(*args, **kwargs):
        raise OSError("docker unavailable")

    monkeypatch.setattr(orch.subprocess, "run", _fail)
    assert orch.rebuild_knowledge_graph(tmp_path, tmp_path, cfg) is False


def test_rebuild_enabled_success_accepts_build_exit_codes(tmp_path, monkeypatch):
    orch = load_orchestrator()
    cfg = {"rebuild_graph_per_batch": True, "workspace_path": "ws"}

    class _Proc:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(orch.subprocess, "run", lambda *a, **k: _Proc())
    assert orch.rebuild_knowledge_graph(tmp_path, tmp_path, cfg) is True

    class _ProcFail:
        returncode = 2
        stderr = "boom"

    monkeypatch.setattr(orch.subprocess, "run", lambda *a, **k: _ProcFail())
    assert orch.rebuild_knowledge_graph(tmp_path, tmp_path, cfg) is False


def test_script_phase_accepts_build_graph_partial_exit_code(tmp_path, monkeypatch):
    """build_graph.py exits 1 (partial/no-results) on parse diagnostics;
    the graph artifact is still written, so the gate must accept it."""
    orch = load_orchestrator()
    cfg = {
        "artifacts_path": str(tmp_path / "artifacts"),
        "workspace_path": str(tmp_path / "workspace"),
    }
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "workspace").mkdir()

    class _ProcPartial:
        returncode = 1
        stdout = "graph written"
        stderr = ""

    monkeypatch.setattr(orch.subprocess, "run", lambda *a, **k: _ProcPartial())
    outcome = orch._run_script_phase("KNOWLEDGE_GRAPH_READY", cfg)
    assert outcome == "OK"

    class _ProcFail:
        returncode = 2
        stdout = ""
        stderr = "boom"

    monkeypatch.setattr(orch.subprocess, "run", lambda *a, **k: _ProcFail())
    outcome = orch._run_script_phase("KNOWLEDGE_GRAPH_READY", cfg)
    assert outcome == "SCRIPT_ERROR"


def _write_runtime_verify(artifacts: Path, overall_pass: bool) -> None:
    payload = {
        "results": [{"project": "p", "status": "PASS" if overall_pass else "FAIL"}],
        "overall_pass": overall_pass,
        "total_consumers": 1,
        "passed": 1 if overall_pass else 0,
        "failed": 0 if overall_pass else 1,
    }
    (artifacts / "07-runtime-verify.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _run_orchestrator_in_state(tmp_path, state_name, cfg_extra=None):
    orch = load_orchestrator()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    cfg = {
        "run_id": "test",
        "baseline_path": str(tmp_path / "baseline"),
        "workspace_path": str(tmp_path / "workspace"),
        "artifacts_path": str(artifacts),
        "source_version": "1.5",
        "target_version": "1.6",
    }
    if cfg_extra:
        cfg.update(cfg_extra)
    (tmp_path / "baseline").mkdir()
    (tmp_path / "workspace").mkdir()
    (artifacts / "00-run-config.json").write_text(
        json.dumps(cfg), encoding="utf-8"
    )
    state = {
        "run_id": "test",
        "state": state_name,
        "current_rule_id": None,
        "updated_at": "2026-08-21T00:00:00Z",
        "failure_reason": None,
    }
    (artifacts / "00-run-state.json").write_text(
        json.dumps(state), encoding="utf-8"
    )
    return orch, cfg


def test_runtime_verify_failures_are_not_reported_as_done(tmp_path):
    """RUNTIME_VERIFY must route through the dedicated handler that checks
    overall_pass. A failing runtime verify must terminate FAILED, never DONE."""
    orch, cfg = _run_orchestrator_in_state(tmp_path, "RUNTIME_VERIFY")
    artifacts = tmp_path / "artifacts"
    _write_runtime_verify(artifacts, overall_pass=False)

    old_argv = sys.argv
    try:
        sys.argv = [
            "orch",
            "--config",
            str(artifacts / "00-run-config.json"),
        ]
        orch.main()
    finally:
        sys.argv = old_argv

    final = json.loads((artifacts / "00-run-state.json").read_text(encoding="utf-8"))
    assert final["state"] == "FAILED", (
        f"Expected FAILED for overall_pass=False, got {final['state']}"
    )


def test_runtime_verify_success_reaches_done(tmp_path):
    orch, cfg = _run_orchestrator_in_state(tmp_path, "RUNTIME_VERIFY")
    artifacts = tmp_path / "artifacts"
    _write_runtime_verify(artifacts, overall_pass=True)

    old_argv = sys.argv
    try:
        sys.argv = [
            "orch",
            "--config",
            str(artifacts / "00-run-config.json"),
        ]
        orch.main()
    finally:
        sys.argv = old_argv

    final = json.loads((artifacts / "00-run-state.json").read_text(encoding="utf-8"))
    assert final["state"] == "DONE", (
        f"Expected DONE for overall_pass=True, got {final['state']}"
    )