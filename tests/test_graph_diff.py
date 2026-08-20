"""Tests for jade-core-verification scripts/graph_diff.py."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / ".claude/skills/jade-core-verification/scripts/graph_diff.py"


def load_graph_diff():
    spec = importlib.util.spec_from_file_location("graph_diff_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def node(path, **kwargs):
    data = {
        "path": path,
        "class_name": path.rsplit("/", 1)[-1].replace(".java", ""),
        "kind": "class",
    }
    data.update(kwargs)
    return data


def graph(nodes, edges=None, source_identity=None, schema_version=2,
          content_hash="abc", diagnostics=None):
    edges = edges or {}
    return {
        "schema_version": schema_version,
        "source_identity": source_identity or {"workspace": "ws"},
        "content_hash": content_hash,
        "nodes": nodes,
        "edges": {
            "imports": edges.get("imports", []),
            "extends": edges.get("extends", []),
            "implements": edges.get("implements", []),
            "calls": edges.get("calls", []),
            "type_refs": edges.get("type_refs", []),
        },
        "diagnostics": diagnostics or {
            "parse_failures": [],
            "unresolved_types": [],
            "ambiguous_symbols": [],
            "other": [],
        },
    }


def run_cli(before_path, after_path, output_path):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--before", str(before_path),
         "--after", str(after_path), "--output", str(output_path)],
        capture_output=True, text=True,
    )


def test_report_schema_and_no_timestamps():
    gd = load_graph_diff()
    report = gd.compute_diff(graph({"A.java": node("A.java")}), graph({"A.java": node("A.java")}))
    assert set(report) == {
        "graph_diff_version", "before_identity", "after_identity",
        "added_nodes", "removed_nodes", "added_edges", "removed_edges",
        "changed_nodes", "impact_paths", "warnings",
    }
    assert report["graph_diff_version"] == 1
    assert "timestamp" not in report


def test_added_removed_nodes_and_edges_with_identity():
    gd = load_graph_diff()
    before = graph(
        {"A.java": node("A.java"), "B.java": node("B.java")},
        edges={"imports": [{"from": "A.java", "to": "B.java", "provenance": "direct"}]},
        source_identity={"workspace": "ws-before"},
    )
    after = graph(
        {"B.java": node("B.java"), "C.java": node("C.java")},
        edges={"imports": [{"from": "B.java", "to": "C.java", "provenance": "direct"}]},
        source_identity={"workspace": "ws-after"},
    )
    report = gd.compute_diff(before, after)

    assert report["before_identity"]["source_identity"] == {"workspace": "ws-before"}
    assert report["after_identity"]["source_identity"] == {"workspace": "ws-after"}
    assert report["added_nodes"] == ["C.java"]
    assert report["removed_nodes"] == ["A.java"]
    assert report["added_edges"] == [
        {"from": "B.java", "to": "C.java", "type": "imports"}
    ]
    assert report["removed_edges"] == [
        {"from": "A.java", "to": "B.java", "type": "imports"}
    ]
    assert report["changed_nodes"] == []


def test_identical_graphs_have_no_diff():
    gd = load_graph_diff()
    base = graph(
        {"A.java": node("A.java"), "B.java": node("B.java")},
        edges={"imports": [{"from": "A.java", "to": "B.java", "provenance": "direct"}]},
    )
    report = gd.compute_diff(base, json.loads(json.dumps(base)))
    assert report["added_nodes"] == []
    assert report["removed_nodes"] == []
    assert report["added_edges"] == []
    assert report["removed_edges"] == []
    assert report["changed_nodes"] == []
    assert report["warnings"] == []


def test_changed_node_signature_detection():
    gd = load_graph_diff()
    before = graph({"B.java": node("B.java", methods=[])})
    after = graph({"B.java": node("B.java", methods=[{"name": "foo", "return_type": "void"}])})
    report = gd.compute_diff(before, after)
    assert report["changed_nodes"] == ["B.java"]
    assert report["added_nodes"] == []
    assert report["removed_nodes"] == []


def test_line_numbers_do_not_count_as_changes():
    gd = load_graph_diff()
    before = graph({"B.java": node("B.java", methods=[{"name": "foo", "line_start": 1, "line_end": 5}])})
    after = graph({"B.java": node("B.java", methods=[{"name": "foo", "line_start": 10, "line_end": 20}])})
    report = gd.compute_diff(before, after)
    assert report["changed_nodes"] == []


def test_canonical_edge_tuple_comparison():
    gd = load_graph_diff()
    before = graph(
        {"A.java": node("A.java"), "B.java": node("B.java")},
        edges={"imports": [{"from": "A.java", "to": "B.java", "provenance": "direct"}]},
    )
    after = graph(
        {"A.java": node("A.java"), "B.java": node("B.java")},
        edges={
            "imports": [{"from": "A.java", "to": "B.java", "provenance": "wildcard"}],
            "calls": [{"from": "A.java", "to": "B.java", "from_method": "run", "to_method": "go", "line": 7}],
        },
    )
    report = gd.compute_diff(before, after)
    assert report["added_edges"] == [{"from": "A.java", "to": "B.java", "type": "calls"}]
    assert report["removed_edges"] == []
    assert report["changed_nodes"] == []


def test_impact_paths_for_changed_nodes():
    gd = load_graph_diff()
    before = graph(
        {"A.java": node("A.java"), "B.java": node("B.java")},
        edges={"imports": [{"from": "A.java", "to": "B.java", "provenance": "direct"}]},
    )
    after = graph(
        {
            "A.java": node("A.java"),
            "B.java": node("B.java", methods=[{"name": "foo", "return_type": "void"}]),
            "C.java": node("C.java"),
        },
        edges={
            "imports": [
                {"from": "A.java", "to": "B.java", "provenance": "direct"},
                {"from": "B.java", "to": "C.java", "provenance": "direct"},
            ],
        },
    )
    report = gd.compute_diff(before, after)
    assert report["changed_nodes"] == ["B.java"]
    assert report["impact_paths"] == [
        {"file": "A.java", "path": ["B.java", "A.java"], "reasons": ["imports"]}
    ]


def test_deterministic_report_across_repeated_runs():
    gd = load_graph_diff()
    before = graph(
        {"A.java": node("A.java"), "B.java": node("B.java")},
        edges={"imports": [{"from": "A.java", "to": "B.java", "provenance": "direct"}]},
    )
    after = graph(
        {"B.java": node("B.java", methods=[{"name": "foo"}]), "C.java": node("C.java")},
        edges={"imports": [{"from": "B.java", "to": "C.java", "provenance": "direct"}]},
    )
    first = gd.compute_diff(before, after)
    second = gd.compute_diff(before, after)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_diagnostics_are_warnings():
    gd = load_graph_diff()
    diag = {
        "parse_failures": [{"kind": "parse_error", "file": "A.java"}],
        "unresolved_types": [],
        "ambiguous_symbols": [],
        "other": [],
    }
    before = graph({"A.java": node("A.java")})
    after = graph({"A.java": node("A.java")}, diagnostics=diag)
    report = gd.compute_diff(before, after)
    assert any(w["kind"] == "graph_diagnostics" and w["side"] == "after" for w in report["warnings"])


def test_identity_mismatch_is_warning():
    gd = load_graph_diff()
    before = graph({"A.java": node("A.java")}, source_identity={"workspace": "ws-a"})
    after = graph({"A.java": node("A.java")}, source_identity={"workspace": "ws-b"})
    report = gd.compute_diff(before, after)
    assert any(w["kind"] == "identity_mismatch" for w in report["warnings"])


def test_cli_missing_file_exit_3(tmp_path):
    output = tmp_path / "report.json"
    result = run_cli(tmp_path / "missing-before.json", tmp_path / "missing-after.json", output)
    assert result.returncode == 3
    assert not output.exists()


def test_cli_malformed_json_exit_2(tmp_path):
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    before.write_text("{not valid json", encoding="utf-8")
    after.write_text(json.dumps(graph({"A.java": node("A.java")})), encoding="utf-8")
    result = run_cli(before, after, tmp_path / "report.json")
    assert result.returncode == 2


def test_cli_success_exit_0_writes_atomically(tmp_path):
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    before.write_text(json.dumps(graph({"A.java": node("A.java")})), encoding="utf-8")
    after.write_text(json.dumps(graph({"A.java": node("A.java")})), encoding="utf-8")
    output = tmp_path / "report.json"
    result = run_cli(before, after, output)
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["graph_diff_version"] == 1
    assert report["added_nodes"] == []
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".graph-diff-")]
    assert leftovers == []


def test_cli_warnings_exit_1(tmp_path):
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    before.write_text(json.dumps(graph({"A.java": node("A.java")}, source_identity={"workspace": "a"})), encoding="utf-8")
    after.write_text(json.dumps(graph({"A.java": node("A.java")}, source_identity={"workspace": "b"})), encoding="utf-8")
    output = tmp_path / "report.json"
    result = run_cli(before, after, output)
    assert result.returncode == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert any(w["kind"] == "identity_mismatch" for w in report["warnings"])


def test_cli_output_is_byte_deterministic(tmp_path):
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    before.write_text(json.dumps(graph({"A.java": node("A.java"), "B.java": node("B.java")})), encoding="utf-8")
    after.write_text(json.dumps(graph({"B.java": node("B.java"), "C.java": node("C.java")})), encoding="utf-8")
    out1 = tmp_path / "r1.json"
    out2 = tmp_path / "r2.json"
    assert run_cli(before, after, out1).returncode == 0
    assert run_cli(before, after, out2).returncode == 0
    assert out1.read_bytes() == out2.read_bytes()