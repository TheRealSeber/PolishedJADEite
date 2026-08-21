"""Tests for runtime_verify.py graph-backed consumer map and impact ordering."""

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / ".claude/skills/jade-core-verification/scripts/runtime_verify.py"


def load_runtime_verify():
    spec = importlib.util.spec_from_file_location("runtime_verify_graph_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def graph_nodes():
    return {
        "core/AID.java": {
            "package": "jade.core",
            "class_name": "AID",
            "kind": "class",
        },
        "core/Agent.java": {
            "package": "jade.core",
            "class_name": "Agent",
            "kind": "class",
        },
        "lang/acl/ACLMessage.java": {
            "package": "jade.lang.acl",
            "class_name": "ACLMessage",
            "kind": "class",
        },
    }


def make_consumer(tmp_path, name, imports):
    project = tmp_path / name
    src = project / "src"
    src.mkdir(parents=True)
    lines = ["package consumer;"]
    for imp in imports:
        lines.append(f"import {imp};")
    lines.append("public class Main { public static void main(String[] a) {} }")
    (src / "Main.java").write_text("\n".join(lines), encoding="utf-8")
    cfg = project / "test-config.json"
    cfg.write_text(json.dumps({"name": name}), encoding="utf-8")
    return project


def test_collect_consumer_jade_fqns(tmp_path):
    rv = load_runtime_verify()
    project = make_consumer(
        tmp_path, "cons-a", ["jade.core.AID", "jade.core.Agent", "java.util.List"]
    )
    assert rv.collect_consumer_jade_fqns(project) == [
        "jade.core.AID",
        "jade.core.Agent",
    ]


def test_map_jade_fqns_to_node_paths():
    rv = load_runtime_verify()
    nodes = graph_nodes()
    paths = rv.map_jade_fqns_to_node_paths(["jade.core.AID", "jade.lang.acl.ACLMessage"], nodes)
    assert paths == ["core/AID.java", "lang/acl/ACLMessage.java"]


def test_build_consumer_map_deterministic(tmp_path):
    rv = load_runtime_verify()
    p1 = make_consumer(tmp_path, "cons-a", ["jade.core.AID"])
    p2 = make_consumer(tmp_path, "cons-b", ["java.util.List"])
    consumers = [(p1, {"name": "cons-a"}), (p2, {"name": "cons-b"})]
    nodes = graph_nodes()
    first = rv.build_consumer_map(consumers, nodes)
    second = rv.build_consumer_map(consumers, nodes)
    assert first == second
    assert first["cons-a"]["node_paths"] == ["core/AID.java"]
    assert first["cons-b"]["node_paths"] == []
    assert first["cons-b"]["jade_fqns"] == []


def test_order_consumers_impacted_first(tmp_path):
    rv = load_runtime_verify()
    p1 = make_consumer(tmp_path, "cons-a", ["jade.core.AID"])
    p2 = make_consumer(tmp_path, "cons-b", ["jade.core.Agent"])
    p3 = make_consumer(tmp_path, "cons-c", ["java.util.List"])
    consumers = [
        (p1, {"name": "cons-a"}),
        (p2, {"name": "cons-b"}),
        (p3, {"name": "cons-c"}),
    ]
    nodes = graph_nodes()
    consumer_map = rv.build_consumer_map(consumers, nodes)
    ordered, coverage = rv.order_consumers_by_impact(
        consumers, consumer_map, ["core/AID.java"], nodes
    )
    names = [c[1]["name"] for c in ordered]
    assert names == ["cons-a", "cons-b", "cons-c"]
    assert coverage["impacted_consumers"] == ["cons-a"]


def test_order_consumers_preserves_all_and_order_without_impact(tmp_path):
    rv = load_runtime_verify()
    p1 = make_consumer(tmp_path, "cons-a", ["jade.core.AID"])
    p2 = make_consumer(tmp_path, "cons-b", ["jade.core.Agent"])
    consumers = [(p1, {"name": "cons-a"}), (p2, {"name": "cons-b"})]
    nodes = graph_nodes()
    consumer_map = rv.build_consumer_map(consumers, nodes)
    ordered, coverage = rv.order_consumers_by_impact(consumers, consumer_map, [], nodes)
    assert len(ordered) == 2
    assert coverage == {}


def test_load_graph_nodes_missing_or_malformed(tmp_path):
    rv = load_runtime_verify()
    artifacts = tmp_path / "artifacts"
    assert rv.load_graph_nodes(artifacts) is None
    artifacts.mkdir()
    (artifacts / "03.5-knowledge-graph.json").write_text(
        "{not valid", encoding="utf-8"
    )
    assert rv.load_graph_nodes(artifacts) is None


def test_load_impacted_nodes(tmp_path):
    rv = load_runtime_verify()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "07-graph-diff.json").write_text(
        json.dumps({"changed_nodes": ["B.java"], "removed_nodes": ["A.java", 42]}),
        encoding="utf-8",
    )
    assert rv.load_impacted_nodes(artifacts) == ["A.java", "B.java"]