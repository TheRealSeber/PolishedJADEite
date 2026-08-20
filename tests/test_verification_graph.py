"""Integration tests: semantic_verify.py records graph-diff evidence additively."""

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / ".claude/skills/jade-core-verification/scripts/semantic_verify.py"


BASELINE_EVENTS = [
    {"message": "Agent rma is born", "sender": "rma"},
    {"message": "Agent ping is born", "sender": "ping"},
    {"message": "Agent ping sends ACL(INFORM) to rma", "sender": "ping"},
]


def node(path, **kwargs):
    data = {
        "path": path,
        "class_name": path.rsplit("/", 1)[-1].replace(".java", ""),
        "kind": "class",
    }
    data.update(kwargs)
    return data


def graph(nodes, edges=None, source_identity=None):
    edges = edges or {}
    return {
        "schema_version": 2,
        "source_identity": source_identity or {"workspace": "ws"},
        "content_hash": "abc",
        "nodes": nodes,
        "edges": {
            "imports": edges.get("imports", []),
            "extends": edges.get("extends", []),
            "implements": edges.get("implements", []),
            "calls": edges.get("calls", []),
            "type_refs": edges.get("type_refs", []),
        },
        "diagnostics": {
            "parse_failures": [],
            "unresolved_types": [],
            "ambiguous_symbols": [],
            "other": [],
        },
    }


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def run_semantic(tmp_path, baseline_events, migrated_events, before_graph=None,
                 after_graph=None, graph_after_missing=False, graph_after_malformed=False):
    artifacts = tmp_path / "artifacts"
    baseline = tmp_path / "baseline.json"
    migrated = tmp_path / "migrated.json"
    tolerance = tmp_path / "tolerance.json"
    write_json(baseline, {"events": baseline_events})
    write_json(migrated, {"events": migrated_events})
    tolerance.write_text("{}", encoding="utf-8")

    cmd = [
        sys.executable, str(SCRIPT),
        "--baseline", str(baseline),
        "--migrated", str(migrated),
        "--tolerance", str(tolerance),
        "--artifacts-dir", str(artifacts),
    ]

    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    if before_graph is not None:
        write_json(before, before_graph)
        cmd += ["--graph-before", str(before)]
    add_after = after_graph is not None or graph_after_missing or graph_after_malformed
    if add_after:
        if graph_after_missing:
            after = tmp_path / "does-not-exist.json"
        elif graph_after_malformed:
            after.write_text("{not valid json", encoding="utf-8")
        else:
            write_json(after, after_graph)
        cmd += ["--graph-after", str(after)]

    return subprocess.run(cmd, capture_output=True, text=True), artifacts


def test_graph_diff_recorded_additively_on_pass(tmp_path):
    before_graph = graph(
        {"A.java": node("A.java"), "B.java": node("B.java")},
        edges={"imports": [{"from": "A.java", "to": "B.java", "provenance": "direct"}]},
    )
    after_graph = graph(
        {"A.java": node("A.java"), "B.java": node("B.java"), "C.java": node("C.java")},
        edges={
            "imports": [
                {"from": "A.java", "to": "B.java", "provenance": "direct"},
                {"from": "B.java", "to": "C.java", "provenance": "direct"},
            ],
        },
    )
    result, artifacts = run_semantic(
        tmp_path, BASELINE_EVENTS, BASELINE_EVENTS, before_graph, after_graph
    )
    assert result.returncode == 0, result.stderr

    diff = json.loads((artifacts / "07-graph-diff.json").read_text(encoding="utf-8"))
    assert diff["status"] == "computed"
    assert diff["added_nodes"] == ["C.java"]
    assert diff["added_edges"] == [{"from": "B.java", "to": "C.java", "type": "imports"}]

    semantic = json.loads((artifacts / "07-semantic-diff.json").read_text(encoding="utf-8"))
    assert semantic["overall_pass"] is True
    assert semantic["graph_evidence"]["status"] == "computed"
    assert semantic["graph_evidence"]["changed_nodes"] == 0
    assert semantic["graph_evidence"]["warnings"] == []

    metrics = json.loads((artifacts / "07-metrics.json").read_text(encoding="utf-8"))
    assert metrics["graph_diff"]["status"] == "computed"
    assert metrics["overall_pass"] is True


def test_graph_evidence_never_converts_failure_to_pass(tmp_path):
    before_graph = graph({"A.java": node("A.java")})
    after_graph = graph({"A.java": node("A.java")})
    migrated_events = BASELINE_EVENTS[1:]
    result, artifacts = run_semantic(
        tmp_path, BASELINE_EVENTS, migrated_events, before_graph, after_graph
    )
    assert result.returncode == 2

    semantic = json.loads((artifacts / "07-semantic-diff.json").read_text(encoding="utf-8"))
    assert semantic["overall_pass"] is False
    assert semantic["graph_evidence"]["status"] == "computed"

    diff = json.loads((artifacts / "07-graph-diff.json").read_text(encoding="utf-8"))
    assert diff["status"] == "computed"
    assert (artifacts / "failure-summary.json").exists()


def test_missing_graph_file_records_warning_gate_unchanged(tmp_path):
    before_graph = graph({"A.java": node("A.java")})
    result, artifacts = run_semantic(
        tmp_path, BASELINE_EVENTS, BASELINE_EVENTS,
        before_graph=before_graph, after_graph=None, graph_after_missing=True,
    )
    assert result.returncode == 0, result.stderr

    diff = json.loads((artifacts / "07-graph-diff.json").read_text(encoding="utf-8"))
    assert diff["status"] == "skipped"
    assert any(w["kind"] == "graph_file_not_found" for w in diff["warnings"])

    semantic = json.loads((artifacts / "07-semantic-diff.json").read_text(encoding="utf-8"))
    assert semantic["overall_pass"] is True
    assert semantic["graph_evidence"]["status"] == "skipped"
    assert any(w["kind"] == "graph_file_not_found" for w in semantic["graph_evidence"]["warnings"])


def test_malformed_graph_warns_and_does_not_pass_failing_gate(tmp_path):
    before_graph = graph({"A.java": node("A.java")})
    migrated_events = BASELINE_EVENTS[1:]
    result, artifacts = run_semantic(
        tmp_path, BASELINE_EVENTS, migrated_events,
        before_graph=before_graph, after_graph=None, graph_after_malformed=True,
    )
    assert result.returncode == 2

    diff = json.loads((artifacts / "07-graph-diff.json").read_text(encoding="utf-8"))
    assert diff["status"] == "malformed"
    assert any(w["kind"] == "graph_parse_error" for w in diff["warnings"])

    semantic = json.loads((artifacts / "07-semantic-diff.json").read_text(encoding="utf-8"))
    assert semantic["overall_pass"] is False
    assert semantic["graph_evidence"]["status"] == "malformed"


def test_no_graph_args_preserves_existing_output(tmp_path):
    result, artifacts = run_semantic(tmp_path, BASELINE_EVENTS, BASELINE_EVENTS)
    assert result.returncode == 0, result.stderr
    assert not (artifacts / "07-graph-diff.json").exists()

    semantic = json.loads((artifacts / "07-semantic-diff.json").read_text(encoding="utf-8"))
    assert "graph_evidence" not in semantic
    assert semantic["overall_pass"] is True

    metrics = json.loads((artifacts / "07-metrics.json").read_text(encoding="utf-8"))
    assert "graph_diff" not in metrics


def test_semantic_failure_without_graph_still_fails(tmp_path):
    migrated_events = BASELINE_EVENTS[1:]
    result, artifacts = run_semantic(tmp_path, BASELINE_EVENTS, migrated_events)
    assert result.returncode == 2
    assert not (artifacts / "07-graph-diff.json").exists()
    assert (artifacts / "failure-summary.json").exists()