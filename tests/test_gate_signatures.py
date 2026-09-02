"""Tests for jade-core-verification scripts/gate_signatures.py."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / ".claude/skills/jade-core-verification/scripts/gate_signatures.py"
REAL_GRAPH = ROOT / "migration-runs/jade-1.7-to-1.8/artifacts/03.5-knowledge-graph.json"

PLAN_SHARDS_SCRIPT = (
    ROOT / ".claude/skills/jade-core-knowledge-graph/scripts/plan_shards.py"
)
STRICTER_CAST_RULE_ID = "STRICTER_CAST_CHECKING"
STRICTER_CAST_ARTIFACTS_DIR = ROOT / "migration-runs/jade-1.5-to-1.6/artifacts"


def load_gate_signatures():
    spec = importlib.util.spec_from_file_location("gate_signatures_test", SCRIPT)
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


def write_shard_plan(artifacts_dir, rule_id, shard_id, editable_files, shard_class="signature"):
    path = artifacts_dir / f"05-rule-shards-{rule_id}.json"
    path.write_text(
        json.dumps(
            {
                "rule_id": rule_id,
                "shards": [
                    {
                        "shard_id": shard_id,
                        "class": shard_class,
                        "editable_files": editable_files,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def run_gate(tmp_path, rule_id, shard_id, before_graph, after_graph, **kwargs):
    artifacts_dir = kwargs.pop("artifacts_dir", tmp_path)
    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    before_path.write_text(json.dumps(before_graph), encoding="utf-8")
    after_path.write_text(json.dumps(after_graph), encoding="utf-8")

    cmd = [
        sys.executable, str(SCRIPT),
        "--artifacts-dir", str(artifacts_dir),
        "--rule-id", rule_id,
        "--shard-id", shard_id,
        "--before-graph", str(before_path),
        "--after-graph", str(after_path),
    ]
    if "shards_artifact" in kwargs:
        cmd += ["--shards-artifact", str(kwargs.pop("shards_artifact"))]
    output = kwargs.pop("output", None)
    if output is not None:
        cmd += ["--output", str(output)]
    assert not kwargs, f"unexpected kwargs: {kwargs}"
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result


def default_output_path(artifacts_dir, shard_id):
    return artifacts_dir / f"07-shard-signature-gate-{shard_id}.json"


def _three_node_calls_graph(a_extra=None):
    """A.java has B.java and C.java calling into it."""
    a_node = node("A.java", methods=([] if a_extra is None else a_extra))
    nodes = {
        "A.java": a_node,
        "B.java": node("B.java"),
        "C.java": node("C.java"),
    }
    edges = {
        "calls": [
            {"from": "B.java", "from_method": "run", "to": "A.java", "to_method": "go", "line": 1},
            {"from": "C.java", "from_method": "run", "to": "A.java", "to_method": "go", "line": 2},
        ]
    }
    return graph(nodes, edges=edges)


def test_graph_diff_module_is_imported_not_reimplemented():
    gs = load_gate_signatures()
    gd = gs._load_graph_diff()
    assert hasattr(gd, "compute_diff")
    assert hasattr(gd, "_reverse_adjacency")
    assert hasattr(gd, "GRAPH_DIFF_VERSION")
    source = SCRIPT.read_text(encoding="utf-8")
    assert "def compute_diff" not in source
    assert "def _node_signature" not in source


def test_graph_diff_report_schema_stays_thirteen_keys():
    gs = load_gate_signatures()
    gd = gs._load_graph_diff()
    report = gd.compute_diff(
        graph({"A.java": node("A.java")}), graph({"A.java": node("A.java")})
    )
    assert set(report) == {
        "graph_diff_version", "before_identity", "after_identity",
        "added_nodes", "removed_nodes", "added_edges", "removed_edges",
        "changed_nodes", "impact_paths", "impact_path_count",
        "impact_path_truncated", "impact_path_truncated_nodes", "warnings",
    }


def test_pass_when_all_dependents_are_inside_editable(tmp_path):
    before = _three_node_calls_graph()
    after = _three_node_calls_graph(a_extra=[{"name": "foo", "return_type": "void"}])
    write_shard_plan(tmp_path, "RULE", "shard-1", ["A.java", "B.java", "C.java"])
    result = run_gate(tmp_path, "RULE", "shard-1", before, after)
    assert result.returncode == 0, result.stderr
    report = json.loads(default_output_path(tmp_path, "shard-1").read_text(encoding="utf-8"))
    assert report["verdict"] == "PASS"
    assert report["leaked_nodes"] == []
    assert report["suggested_shard_expansion"] == []
    assert report["reason"] == "No signature change leaks outside the shard editable set"


def test_reject_when_dependent_lies_outside_editable(tmp_path):
    before = _three_node_calls_graph()
    after = _three_node_calls_graph(a_extra=[{"name": "foo", "return_type": "void"}])
    write_shard_plan(tmp_path, "RULE", "shard-1", ["A.java", "B.java"])
    result = run_gate(tmp_path, "RULE", "shard-1", before, after)
    assert result.returncode == 2
    output = default_output_path(tmp_path, "shard-1")
    assert output.exists()
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["verdict"] == "REJECT"
    assert len(report["leaked_nodes"]) == 1
    assert report["leaked_nodes"][0]["node"] == "A.java"
    assert report["leaked_nodes"][0]["dependents"] == ["C.java"]
    assert report["suggested_shard_expansion"] == ["C.java"]


def test_reject_reason_text_is_exact(tmp_path):
    before = _three_node_calls_graph()
    after = _three_node_calls_graph(a_extra=[{"name": "foo", "return_type": "void"}])
    write_shard_plan(tmp_path, "RULE", "shard-1", ["A.java", "B.java"])
    run_gate(tmp_path, "RULE", "shard-1", before, after)
    report = json.loads(
        default_output_path(tmp_path, "shard-1").read_text(encoding="utf-8")
    )
    assert report["reason"] == (
        "1 changed node(s) leak signature changes to 1 file(s) "
        "outside the shard editable set"
    )


def test_line_shift_alone_is_not_a_signature_change(tmp_path):
    before = graph(
        {"A.java": node("A.java", methods=[{"name": "foo", "line_start": 1, "line_end": 5}])}
    )
    after = graph(
        {"A.java": node("A.java", methods=[{"name": "foo", "line_start": 10, "line_end": 20}])}
    )
    write_shard_plan(tmp_path, "RULE", "shard-1", ["A.java"])
    result = run_gate(tmp_path, "RULE", "shard-1", before, after)
    report = json.loads(default_output_path(tmp_path, "shard-1").read_text(encoding="utf-8"))
    assert report["changed_nodes"] == []
    assert report["verdict"] == "PASS"
    assert result.returncode == 0


def test_added_method_is_a_signature_change(tmp_path):
    before = _three_node_calls_graph()
    after = _three_node_calls_graph(a_extra=[{"name": "foo", "return_type": "void"}])
    write_shard_plan(tmp_path, "RULE", "shard-1", ["A.java", "B.java"])
    run_gate(tmp_path, "RULE", "shard-1", before, after)
    report = json.loads(
        default_output_path(tmp_path, "shard-1").read_text(encoding="utf-8")
    )
    assert report["changed_nodes"] == ["A.java"]
    assert any(entry["node"] == "A.java" for entry in report["leaked_nodes"])


def test_removed_node_dependents_are_read_from_before_graph(tmp_path):
    calls_edge = {
        "calls": [
            {"from": "C.java", "from_method": "run", "to": "A.java", "to_method": "go", "line": 1},
        ]
    }
    before = graph(
        {
            "A.java": node("A.java"),
            "B.java": node("B.java"),
            "C.java": node("C.java"),
        },
        edges=calls_edge,
    )
    # Only A.java is removed; C.java (its dependent) is unchanged and still
    # present in after -- rev_after has no edges into A.java at all, so this
    # test only passes when rev_before (not rev_after) is used for removed
    # nodes.
    after = graph(
        {"B.java": node("B.java"), "C.java": node("C.java")},
        edges={"calls": []},
    )
    write_shard_plan(tmp_path, "RULE", "shard-1", ["B.java"])
    result = run_gate(tmp_path, "RULE", "shard-1", before, after)
    report = json.loads(default_output_path(tmp_path, "shard-1").read_text(encoding="utf-8"))
    assert result.returncode == 2
    assert report["removed_nodes"] == ["A.java"]
    entry = next(e for e in report["leaked_nodes"] if e["node"] == "A.java")
    assert entry["side"] == "before"
    assert entry["dependents"] == ["C.java"]


def test_changed_node_uses_after_side(tmp_path):
    before = _three_node_calls_graph()
    after = _three_node_calls_graph(a_extra=[{"name": "foo", "return_type": "void"}])
    write_shard_plan(tmp_path, "RULE", "shard-1", ["A.java", "B.java"])
    run_gate(tmp_path, "RULE", "shard-1", before, after)
    report = json.loads(
        default_output_path(tmp_path, "shard-1").read_text(encoding="utf-8")
    )
    entry = next(e for e in report["leaked_nodes"] if e["node"] == "A.java")
    assert entry["side"] == "after"


def test_self_loop_is_not_a_leak(tmp_path):
    before = graph(
        {"A.java": node("A.java")},
        edges={
            "calls": [
                {"from": "A.java", "from_method": "run", "to": "A.java", "to_method": "run", "line": 1},
            ]
        },
    )
    after = graph(
        {"A.java": node("A.java", methods=[{"name": "foo", "return_type": "void"}])},
        edges={
            "calls": [
                {"from": "A.java", "from_method": "run", "to": "A.java", "to_method": "run", "line": 1},
            ]
        },
    )
    write_shard_plan(tmp_path, "RULE", "shard-1", ["A.java"])
    result = run_gate(tmp_path, "RULE", "shard-1", before, after)
    report = json.loads(default_output_path(tmp_path, "shard-1").read_text(encoding="utf-8"))
    assert report["verdict"] == "PASS"
    assert result.returncode == 0


def test_out_of_scope_edit_is_rejected(tmp_path):
    before = graph({"D.java": node("D.java")})
    after = graph({"D.java": node("D.java", methods=[{"name": "foo", "return_type": "void"}])})
    write_shard_plan(tmp_path, "RULE", "shard-1", ["A.java"])
    result = run_gate(tmp_path, "RULE", "shard-1", before, after)
    report = json.loads(default_output_path(tmp_path, "shard-1").read_text(encoding="utf-8"))
    assert report["out_of_scope_changed_nodes"] == ["D.java"]
    assert report["verdict"] == "REJECT"
    assert "D.java" in report["suggested_shard_expansion"]
    assert result.returncode == 2


def test_edge_types_list_is_deduplicated_and_sorted(tmp_path):
    before = graph(
        {"A.java": node("A.java"), "C.java": node("C.java")},
        edges={
            "calls": [
                {"from": "C.java", "from_method": "m1", "to": "A.java", "to_method": "go", "line": 1},
                {"from": "C.java", "from_method": "m2", "to": "A.java", "to_method": "go", "line": 2},
                {"from": "C.java", "from_method": "m3", "to": "A.java", "to_method": "go", "line": 3},
            ],
            "type_refs": [
                {"from": "C.java", "to": "A.java", "field": "x", "type": "A"},
            ],
        },
    )
    after = graph(
        {
            "A.java": node("A.java", methods=[{"name": "foo", "return_type": "void"}]),
            "C.java": node("C.java"),
        },
        edges=before["edges"],
    )
    write_shard_plan(tmp_path, "RULE", "shard-1", ["A.java"])
    run_gate(tmp_path, "RULE", "shard-1", before, after)
    report = json.loads(
        default_output_path(tmp_path, "shard-1").read_text(encoding="utf-8")
    )
    entry = next(e for e in report["leaked_nodes"] if e["node"] == "A.java")
    assert entry["edge_types"] == ["calls", "type_refs"]


def test_suggested_expansion_excludes_editable_files(tmp_path):
    before = _three_node_calls_graph()
    after = _three_node_calls_graph(a_extra=[{"name": "foo", "return_type": "void"}])
    write_shard_plan(tmp_path, "RULE", "shard-1", ["A.java", "B.java"])
    run_gate(tmp_path, "RULE", "shard-1", before, after)
    report = json.loads(
        default_output_path(tmp_path, "shard-1").read_text(encoding="utf-8")
    )
    editable = {"A.java", "B.java"}
    assert not (set(report["suggested_shard_expansion"]) & editable)
    assert report["suggested_shard_expansion"] == sorted(report["suggested_shard_expansion"])


def test_graph_diff_warnings_propagate_and_exit_1(tmp_path):
    before = graph({"A.java": node("A.java")})
    after = graph(
        {"A.java": node("A.java")},
        diagnostics={
            "parse_failures": [{"kind": "parse_error", "file": "A.java"}],
            "unresolved_types": [],
            "ambiguous_symbols": [],
            "other": [],
        },
    )
    write_shard_plan(tmp_path, "RULE", "shard-1", ["A.java"])
    result = run_gate(tmp_path, "RULE", "shard-1", before, after)
    report = json.loads(default_output_path(tmp_path, "shard-1").read_text(encoding="utf-8"))
    assert report["verdict"] == "PASS"
    assert report["graph_diff_warnings"] != []
    assert result.returncode == 1
    assert "WARNING [GRAPH_DIFF]" in result.stderr


def test_identity_mismatch_does_not_flip_verdict(tmp_path):
    before = graph({"A.java": node("A.java")}, source_identity={"workspace": "ws-a"})
    after = graph({"A.java": node("A.java")}, source_identity={"workspace": "ws-b"})
    write_shard_plan(tmp_path, "RULE", "shard-1", ["A.java"])
    result = run_gate(tmp_path, "RULE", "shard-1", before, after)
    report = json.loads(default_output_path(tmp_path, "shard-1").read_text(encoding="utf-8"))
    assert result.returncode == 1
    assert report["verdict"] == "PASS"


def test_missing_graph_file_exit_3_no_artifact(tmp_path):
    write_shard_plan(tmp_path, "RULE", "shard-1", ["A.java"])
    after_path = tmp_path / "after.json"
    after_path.write_text(json.dumps(graph({"A.java": node("A.java")})), encoding="utf-8")
    cmd = [
        sys.executable, str(SCRIPT),
        "--artifacts-dir", str(tmp_path),
        "--rule-id", "RULE",
        "--shard-id", "shard-1",
        "--before-graph", str(tmp_path / "missing-before.json"),
        "--after-graph", str(after_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 3
    assert "ERROR [GRAPH_NOT_FOUND] before:" in result.stderr
    assert not default_output_path(tmp_path, "shard-1").exists()


def test_malformed_graph_exit_2(tmp_path):
    write_shard_plan(tmp_path, "RULE", "shard-1", ["A.java"])
    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    before_path.write_text(json.dumps({"schema_version": 2}), encoding="utf-8")
    after_path.write_text(json.dumps(graph({"A.java": node("A.java")})), encoding="utf-8")
    cmd = [
        sys.executable, str(SCRIPT),
        "--artifacts-dir", str(tmp_path),
        "--rule-id", "RULE",
        "--shard-id", "shard-1",
        "--before-graph", str(before_path),
        "--after-graph", str(after_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 2
    assert "ERROR [GRAPH_MALFORMED]" in result.stderr
    assert not default_output_path(tmp_path, "shard-1").exists()


def test_shard_not_found_exit_2(tmp_path):
    write_shard_plan(tmp_path, "RULE", "shard-1", ["A.java"])
    cmd = [
        sys.executable, str(SCRIPT),
        "--artifacts-dir", str(tmp_path),
        "--rule-id", "RULE",
        "--shard-id", "does-not-exist",
        "--before-graph", str(tmp_path / "nope-before.json"),
        "--after-graph", str(tmp_path / "nope-after.json"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 2
    assert "ERROR [SHARD_NOT_FOUND]" in result.stderr
    assert not default_output_path(tmp_path, "does-not-exist").exists()


def test_shard_id_with_path_separator_rejected_exit_2(tmp_path):
    cmd = [
        sys.executable, str(SCRIPT),
        "--artifacts-dir", str(tmp_path),
        "--rule-id", "RULE",
        "--shard-id", "../evil",
        "--before-graph", str(tmp_path / "nope-before.json"),
        "--after-graph", str(tmp_path / "nope-after.json"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 2
    assert "ERROR [INVALID_ID]" in result.stderr


def test_output_is_byte_deterministic_and_leaves_no_tmp_files(tmp_path):
    before = _three_node_calls_graph()
    after = _three_node_calls_graph(a_extra=[{"name": "foo", "return_type": "void"}])
    write_shard_plan(tmp_path, "RULE", "shard-1", ["A.java", "B.java"])
    out1 = tmp_path / "r1.json"
    out2 = tmp_path / "r2.json"
    result1 = run_gate(tmp_path, "RULE", "shard-1", before, after, output=out1)
    result2 = run_gate(tmp_path, "RULE", "shard-1", before, after, output=out2)
    assert result1.returncode == 2
    assert result2.returncode == 2
    assert out1.read_bytes() == out2.read_bytes()
    report = json.loads(out1.read_text(encoding="utf-8"))
    assert "generated_at" not in report
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".signature-gate-")]
    assert leftovers == []


def test_malformed_edges_do_not_crash(tmp_path):
    before = graph({"A.java": node("A.java")})
    after = graph(
        {"A.java": node("A.java"), "B.java": node("B.java")},
        edges={
            "calls": [
                5,
                None,
                {"from": 1, "to": "A.java"},
            ]
        },
    )
    write_shard_plan(tmp_path, "RULE", "shard-1", ["A.java", "B.java"])
    result = run_gate(tmp_path, "RULE", "shard-1", before, after)
    assert result.returncode in (0, 1, 2)
    assert "Traceback" not in result.stderr


def test_identical_graphs_on_real_shard_plan_pass(tmp_path):
    """Real integration path, not a fabricated shard.

    First runs plan_shards.py on the real STRICTER_CAST_CHECKING artifacts
    (1.5-to-1.6 manifest + flag index, 1.7-to-1.8 knowledge graph) to obtain
    a real shard plan -- the editable_files list comes from the actual
    blast_class grouping logic, not a hand-picked slice of graph node keys.
    That real shard-plan artifact is then fed straight into
    gate_signatures.py via --shards-artifact.

    Skips (with a clear reason) instead of falsely passing whenever the real
    plan comes back UNCLASSIFIED, EMPTY, or with zero shards -- there would
    then be nothing real left to gate.
    """
    for path in (STRICTER_CAST_ARTIFACTS_DIR, REAL_GRAPH):
        if not path.exists():
            pytest.skip(f"{path} not found")

    plan_path = tmp_path / f"05-rule-shards-{STRICTER_CAST_RULE_ID}.json"
    plan_cmd = [
        sys.executable, str(PLAN_SHARDS_SCRIPT),
        "--artifacts-dir", str(STRICTER_CAST_ARTIFACTS_DIR),
        "--rule-id", STRICTER_CAST_RULE_ID,
        "--graph-artifacts-dir", str(REAL_GRAPH.parent),
        "--output", str(plan_path),
    ]
    plan_result = subprocess.run(plan_cmd, capture_output=True, text=True)
    assert plan_result.returncode in (0, 1), (
        f"plan_shards.py failed unexpectedly (exit {plan_result.returncode}): "
        f"{plan_result.stderr}"
    )
    if not plan_path.exists():
        pytest.skip(
            f"plan_shards.py produced no shard-plan artifact for "
            f"{STRICTER_CAST_RULE_ID}: {plan_result.stderr}"
        )

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan.get("status") != "OK" or not plan.get("shards"):
        pytest.skip(
            f"real shard plan for {STRICTER_CAST_RULE_ID} is "
            f"{plan.get('status')!r} with {len(plan.get('shards', []))} shard(s); "
            f"nothing real to gate"
        )

    shard = plan["shards"][0]
    shard_id = shard["shard_id"]
    editable_files = shard.get("editable_files") or []
    if not editable_files:
        pytest.skip(f"real shard {shard_id!r} has an empty editable_files list")

    output_path = tmp_path / f"07-shard-signature-gate-{shard_id}.json"
    gate_cmd = [
        sys.executable, str(SCRIPT),
        "--artifacts-dir", str(tmp_path),
        "--rule-id", STRICTER_CAST_RULE_ID,
        "--shard-id", shard_id,
        "--before-graph", str(REAL_GRAPH),
        "--after-graph", str(REAL_GRAPH),
        "--shards-artifact", str(plan_path),
        "--output", str(output_path),
    ]
    result = subprocess.run(gate_cmd, capture_output=True, text=True)
    report = json.loads(output_path.read_text(encoding="utf-8"))

    assert report["changed_nodes"] == []
    assert report["removed_nodes"] == []
    assert report["verdict"] == "PASS"
    assert report["editable_file_count"] == len(editable_files)
    # The real graph carries its own parse/type diagnostics (unresolved
    # types, ambiguous symbols, ...), so gate_signatures reports PASS but
    # still exits 1 (attention needed) even though before == after.
    assert result.returncode == 1, result.stderr
