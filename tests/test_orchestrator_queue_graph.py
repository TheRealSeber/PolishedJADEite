import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / ".claude/skills/jade-core-orchestrator/scripts/orchestrator.py"


def load_orchestrator():
    spec = importlib.util.spec_from_file_location("orchestrator_queue_graph_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def write_graph(artifacts, edges):
    payload = {
        "schema_version": 2,
        "source": {"workspace_root": "ws"},
        "nodes": {
            "A.java": {"path": "A.java", "class_name": "A", "kind": "class"},
            "B.java": {"path": "B.java", "class_name": "B", "kind": "class"},
        },
        "edges": {
            "imports": [{"from": e[0], "to": e[1]} for e in edges],
            "extends": [],
            "implements": [],
            "calls": [],
            "type_refs": [],
        },
        "stats": {},
    }
    (artifacts / "03.5-knowledge-graph.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def write_flag_index(artifacts, flags):
    (artifacts / "04-flag-index.json").write_text(
        json.dumps({"flags": flags, "total_flags": len(flags)}), encoding="utf-8"
    )


def test_compute_metadata_preserves_rules_order(tmp_path):
    orch = load_orchestrator()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    rules = ["R1", "R2"]
    meta = orch.compute_queue_graph_metadata(artifacts, rules)
    assert rules == ["R1", "R2"]
    assert meta["status"] == "computed"
    assert meta["suggested_order"] == ["R1", "R2"]
    assert meta["direct_counts"] == {}
    assert meta["impact_counts"] == {}
    for key in (
        "status",
        "source_artifact",
        "suggested_order",
        "direct_counts",
        "impact_counts",
        "cycles",
        "ordering_reasons",
        "diagnostics",
    ):
        assert key in meta


def test_empty_rules_handled(tmp_path):
    orch = load_orchestrator()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    meta = orch.compute_queue_graph_metadata(artifacts, [])
    assert meta["status"] == "empty"
    assert meta["suggested_order"] == []
    assert meta["direct_counts"] == {}
    assert meta["cycles"] == []


def test_missing_graph_yields_graph_unavailable_diagnostic(tmp_path):
    orch = load_orchestrator()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    meta = orch.compute_queue_graph_metadata(artifacts, ["R1"])
    assert any(d.get("kind") == "graph_unavailable" for d in meta["diagnostics"])
    assert meta["suggested_order"] == ["R1"]


def test_attach_metadata_is_additive_and_preserves_queue(tmp_path):
    orch = load_orchestrator()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    queue_path = artifacts / "05-rule-queue.json"
    queue_path.write_text(
        json.dumps({"run_id": "r", "rules": ["R1", "R2"]}), encoding="utf-8"
    )
    updated = orch.attach_queue_graph_metadata(artifacts)
    assert updated["rules"] == ["R1", "R2"]
    assert "graph_metadata" in updated
    on_disk = json.loads(queue_path.read_text(encoding="utf-8"))
    assert on_disk["rules"] == ["R1", "R2"]
    assert on_disk["graph_metadata"]["suggested_order"] == ["R1", "R2"]


def test_attach_returns_none_without_queue(tmp_path):
    orch = load_orchestrator()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    assert orch.attach_queue_graph_metadata(artifacts) is None


def test_attach_returns_none_for_malformed_queue(tmp_path):
    orch = load_orchestrator()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "05-rule-queue.json").write_text(
        json.dumps(["not", "a", "dict"]), encoding="utf-8"
    )
    assert orch.attach_queue_graph_metadata(artifacts) is None


def test_process_rule_batch_malformed_queue_returns_missing(tmp_path):
    orch = load_orchestrator()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "05-rule-queue.json").write_text(
        json.dumps(["not", "a", "dict"]), encoding="utf-8"
    )
    cfg = {"run_id": "r"}
    outcome = orch.process_rule_batch(
        cfg,
        artifacts,
        {},
        artifacts / "phase-history.log.jsonl",
        artifacts / "00-run-state.json",
        artifacts / "rule-status.json",
    )
    assert outcome == "ARTIFACT_MISSING"


def test_approved_only_order_from_graph(tmp_path):
    orch = load_orchestrator()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    write_graph(artifacts, edges=[("A.java", "B.java")])
    write_flag_index(
        artifacts,
        [
            {"rule_id": "R1", "file": "A.java", "line": 1, "graph": {"impact_files": ["B.java"]}},
            {"rule_id": "R2", "file": "B.java", "line": 1, "graph": {"impact_files": []}},
        ],
    )
    meta = orch.compute_queue_graph_metadata(artifacts, ["R1", "R2"])
    assert set(meta["suggested_order"]) == {"R1", "R2"}
    assert meta["suggested_order"] == ["R2", "R1"]
    assert meta["direct_counts"] == {"R1": 1, "R2": 1}
    assert meta["impact_counts"] == {"R1": 1, "R2": 0}
    assert meta["cycles"] == []


def test_approved_only_excludes_non_queued_rules(tmp_path):
    orch = load_orchestrator()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    write_graph(artifacts, edges=[("A.java", "B.java")])
    write_flag_index(
        artifacts,
        [
            {"rule_id": "R1", "file": "A.java", "line": 1, "graph": {"impact_files": ["B.java"]}},
            {"rule_id": "R2", "file": "B.java", "line": 1, "graph": {"impact_files": []}},
        ],
    )
    meta = orch.compute_queue_graph_metadata(artifacts, ["R1"])
    assert meta["suggested_order"] == ["R1"]
    assert meta["direct_counts"] == {"R1": 1}