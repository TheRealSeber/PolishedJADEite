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
