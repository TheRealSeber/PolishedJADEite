import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).parents[1]


def load_scanner():
    path = ROOT / ".claude/skills/jade-core-scanner/scripts/scan_and_tag.py"
    spec = importlib.util.spec_from_file_location("scanner_graph_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_inputs(tmp_path, graph=None):
    workspace = tmp_path / "workspace"
    artifacts = tmp_path / "artifacts"
    workspace.mkdir()
    artifacts.mkdir()
    (workspace / "A.java").write_text("class A {\n  void run() {}\n}\n", encoding="utf-8")
    (workspace / "B.java").write_text("class B { A value; }\n", encoding="utf-8")
    (artifacts / "01-breaking-changes-manifest.json").write_text(json.dumps({
        "rules": [{"id": "RULE", "patterns": [{"pattern": r"class A", "target_extensions": [".java"]}]}]
    }), encoding="utf-8")
    if graph is not None:
        (artifacts / "03.5-knowledge-graph.json").write_text(json.dumps(graph), encoding="utf-8")
    return workspace, artifacts


def run_scan(tmp_path, graph=None):
    scanner = load_scanner()
    workspace, artifacts = write_inputs(tmp_path, graph)
    assert scanner.main.__name__ == "main"
    import sys
    old = sys.argv
    try:
        sys.argv = ["scan", "--workspace", str(workspace), "--artifacts", str(artifacts)]
        assert scanner.main() == 0
    finally:
        sys.argv = old
    return json.loads((artifacts / "04-flag-index.json").read_text(encoding="utf-8"))


def graph_fixture():
    return {
        "source_identity": {"workspace": "fixture", "java_file_count": 2},
        "nodes": {
            "A.java": {"path": "A.java", "package": "", "class_name": "A", "methods": [{"name": "run", "line_start": 2, "line_end": 2}]},
            "B.java": {"path": "B.java", "package": "", "class_name": "B", "methods": []},
        },
        "edges": {"imports": [{"from": "B.java", "to": "A.java"}], "extends": [], "implements": [], "calls": [], "type_refs": []},
    }


def test_valid_graph_enriches_flags(tmp_path):
    index = run_scan(tmp_path, graph_fixture())
    flag = index["flags"][0]
    assert flag["graph"]["node_exists"] is True
    assert flag["graph"]["class"] == "A"
    assert flag["graph"]["direct_impact_files"] == ["B.java"]
    assert index["graph"]["source_identity"]["workspace"] == "fixture"


def test_missing_graph_preserves_flags_and_warns(tmp_path):
    index = run_scan(tmp_path)
    assert index["flags"]
    assert index["graph"]["status"] == "unavailable"
    assert index["flags"][0]["graph"]["diagnostics"][0]["kind"] == "graph_unavailable"


def test_malformed_graph_does_not_crash_scan(tmp_path):
    workspace, artifacts = write_inputs(tmp_path)
    (artifacts / "03.5-knowledge-graph.json").write_text("{bad", encoding="utf-8")
    scanner = load_scanner()
    import sys
    old = sys.argv
    try:
        sys.argv = ["scan", "--workspace", str(workspace), "--artifacts", str(artifacts)]
        assert scanner.main() == 0
    finally:
        sys.argv = old
    index = json.loads((artifacts / "04-flag-index.json").read_text(encoding="utf-8"))
    assert index["flags"]
    assert index["graph"]["diagnostics"][0]["kind"] == "graph_invalid"
