import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).parents[1]


def load_batch():
    path = ROOT / ".claude/skills/jade-core-batch-processor/scripts/rule_batch_runner.py"
    spec = importlib.util.spec_from_file_location("batch_graph_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_impact_only_is_sorted_and_excluded_from_tasks():
    batch = load_batch()
    index = {"flags": [
        {"rule_id": "RULE", "file": "A.java", "line": 1, "graph": {"paths": [
            {"file": "C.java", "path": ["A.java", "B.java", "C.java"], "reasons": ["imports", "calls"]},
            {"file": "B.java", "path": ["A.java", "B.java"], "reasons": ["imports"]},
        ]}},
    ]}
    tasks = batch.build_file_task_list("RULE", index)
    impact = batch.build_impact_only_list("RULE", index)
    assert [task["file"] for task in tasks] == ["A.java"]
    assert [item["file"] for item in impact] == ["B.java", "C.java"]
    assert impact[1]["reasons"] == ["calls", "imports"]
    assert impact[1]["paths"][0]["path"] == ["A.java", "B.java", "C.java"]


def test_batch_artifact_keeps_impact_only_additive(tmp_path):
    batch = load_batch()
    path = batch.write_batch_artifact(tmp_path, "RULE", [{"file": "A.java", "flags": [], "status": "PENDING", "updated_at": None}], [{"file": "B.java", "reasons": ["imports"], "paths": []}])
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["total_files"] == 1
    assert [item["file"] for item in payload["files"]] == ["A.java"]
    assert payload["impact_only"][0]["file"] == "B.java"


def test_cmd_prepare_real_path_separates_impact_and_dispatch_input(tmp_path, capsys):
    batch = load_batch()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    graph = {
        "source_identity": {"workspace": "fixture"},
        "nodes": {"A.java": {"path": "A.java", "class_name": "A"}, "B.java": {"path": "B.java", "class_name": "B"}},
        "edges": {"imports": [{"from": "B.java", "to": "A.java"}], "extends": [], "implements": [], "calls": [], "type_refs": []},
    }
    (artifacts / "03.5-knowledge-graph.json").write_text(json.dumps(graph), encoding="utf-8")
    (artifacts / "04-flag-index.json").write_text(json.dumps({"flags": [{
        "rule_id": "RULE", "file": "A.java", "line": 1, "confidence": "HIGH", "reason": "test"
    }]}), encoding="utf-8")
    (artifacts / "05-rule-queue.json").write_text(json.dumps({"rules": ["RULE"]}), encoding="utf-8")

    assert batch.cmd_prepare(artifacts, "RULE", "run-1") == 0
    payload = json.loads((artifacts / "05-rule-batch-RULE.json").read_text(encoding="utf-8"))
    assert [entry["file"] for entry in payload["files"]] == ["A.java"]
    assert [entry["file"] for entry in payload["impact_only"]] == ["B.java"]
    assert payload["files"][0]["transform_scope"] == "DIRECT"
    assert payload["impact_only"][0]["transform_scope"] == "IMPACT_ONLY"
    assert payload["total_files"] == 1
    assert payload["graph"]["source_artifact"] == "03.5-knowledge-graph.json"
    assert payload["impact_only"][0]["source_artifact"] == "03.5-knowledge-graph.json"
    assert payload["impact_only"][0]["source_identity"]["workspace"] == "fixture"
    assert batch.cmd_update(artifacts, "RULE", "run-1", "B.java", "DONE") == 2
    assert "FILE_NOT_IN_BATCH" in capsys.readouterr().err


def test_batch_missing_graph_warns_without_changing_direct_tasks(tmp_path, capsys):
    batch = load_batch()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "04-flag-index.json").write_text(json.dumps({"flags": [{"rule_id": "RULE", "file": "A.java", "line": 1}]}), encoding="utf-8")
    (artifacts / "05-rule-queue.json").write_text(json.dumps({"rules": ["RULE"]}), encoding="utf-8")
    assert batch.cmd_prepare(artifacts, "RULE", "run-1") == 0
    assert "graph_unavailable" in capsys.readouterr().err
