import importlib.util
import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).parents[1]


def load_scanner():
    path = ROOT / ".claude/skills/jade-core-scanner/scripts/scan_and_tag.py"
    spec = importlib.util.spec_from_file_location("scanner_graph_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_missing_graph_node_warns_and_preserves_flag(tmp_path, capsys):
    workspace = tmp_path / "workspace"
    artifacts = tmp_path / "artifacts"
    workspace.mkdir()
    artifacts.mkdir()
    (workspace / "A.java").write_text("class A {}\n", encoding="utf-8")
    (artifacts / "01-breaking-changes-manifest.json").write_text(
        json.dumps({"rules": [{"id": "RULE", "patterns": [{"pattern": "class A"}]}]}),
        encoding="utf-8",
    )
    (artifacts / "03.5-knowledge-graph.json").write_text(
        json.dumps({"nodes": {}, "edges": {}}), encoding="utf-8"
    )

    scanner = load_scanner()
    old_argv = sys.argv
    try:
        sys.argv = ["scan", "--workspace", str(workspace), "--artifacts", str(artifacts)]
        assert scanner.main() == 0
    finally:
        sys.argv = old_argv

    index = json.loads((artifacts / "04-flag-index.json").read_text(encoding="utf-8"))
    assert index["flags"]
    assert any(d["kind"] == "graph_node_missing" for d in index["flags"][0]["graph"]["diagnostics"])
    assert "graph_node_missing" in capsys.readouterr().err


def test_graph_diagnostic_buckets_are_visible_and_flags_continue(tmp_path, capsys):
    scanner = load_scanner()
    graph = {
        "nodes": {"A.java": {"class_name": "A", "methods": []}},
        "edges": {},
        "diagnostics": {
            "parse_failures": [{"file": "Broken.java", "message": "bad syntax"}],
            "unresolved_types": [{"name": "Missing"}],
            "ambiguous_symbols": [{"name": "Thing"}],
            "other": [{"message": "advisory"}],
        },
    }
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "03.5-knowledge-graph.json").write_text(json.dumps(graph), encoding="utf-8")
    flags = [{"rule_id": "RULE", "file": "A.java", "line": 1}]

    metadata = scanner.enrich_flags_with_graph(flags, artifacts)
    stderr = capsys.readouterr().err
    for bucket in ("parse_failures", "unresolved_types", "ambiguous_symbols", "other"):
        assert bucket in stderr
        assert metadata["artifact_diagnostics"]["counts"][bucket] == 1
    assert flags[0]["graph"]["node_exists"] is True


def test_scan_artifacts_are_byte_deterministic(tmp_path):
    scanner = load_scanner()
    workspace = tmp_path / "workspace"
    artifacts = tmp_path / "artifacts"
    workspace.mkdir()
    artifacts.mkdir()
    (workspace / "A.java").write_text("class A {}\n", encoding="utf-8")
    (artifacts / "01-breaking-changes-manifest.json").write_text(
        json.dumps({"rules": [{"id": "RULE", "patterns": [{"pattern": "class A"}]}]}),
        encoding="utf-8",
    )
    scan_workspace = tmp_path / "scan-workspace"
    shutil.copytree(workspace, scan_workspace)
    old_argv = sys.argv
    try:
        sys.argv = ["scan", "--workspace", str(scan_workspace), "--artifacts", str(artifacts)]
        assert scanner.main() == 0
        first = ((artifacts / "04-flag-index.json").read_bytes(),
                 (artifacts / "04-scan-summary.json").read_bytes())
        shutil.rmtree(scan_workspace)
        shutil.copytree(workspace, scan_workspace)
        sys.argv = ["scan", "--workspace", str(scan_workspace), "--artifacts", str(artifacts)]
        assert scanner.main() == 0
        second = ((artifacts / "04-flag-index.json").read_bytes(),
                  (artifacts / "04-scan-summary.json").read_bytes())
    finally:
        sys.argv = old_argv
    assert first == second
