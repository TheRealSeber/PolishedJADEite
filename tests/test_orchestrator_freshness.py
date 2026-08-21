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