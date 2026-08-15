"""Tests for jade-core-knowledge-graph skill."""

import json
import os
import shutil
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "skills", "jade-core-knowledge-graph", "scripts"))

from schema import KnowledgeGraph, GraphNode, MethodInfo, FieldInfo, Parameter
from tree_sitter_java_queries import (
    get_parser, parse_file, extract_class_info, extract_methods,
    extract_fields, extract_calls, extract_imports,
)
from build_graph import scan_workspace, parse_files, resolve_graph


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "knowledge-graph")


class TestSchema:
    def test_create_empty_kg(self):
        kg = KnowledgeGraph()
        assert kg.compute_stats()["total_files"] == 0
        assert kg.compute_stats()["total_edges"] == 0

    def test_add_node(self):
        kg = KnowledgeGraph()
        node = GraphNode(path="test/File.java", class_name="File", package="test", kind="class")
        kg.add_node(node)
        assert kg.compute_stats()["total_files"] == 1
        assert "test/File.java" in kg.nodes

    def test_add_edges(self):
        kg = KnowledgeGraph()
        kg.add_import_edge("a/A.java", "b/B.java")
        kg.add_extends_edge("a/A.java", "b/B.java")
        kg.add_implements_edge("a/A.java", "c/I.java")
        kg.add_call_edge("a/A.java", "run", "b/B.java", "execute", 42)
        kg.add_type_ref_edge("a/A.java", "b/B.java", field="b", type_name="B")
        stats = kg.compute_stats()
        assert stats["total_edges"] == 5
        assert stats["edge_counts"]["imports"] == 1
        assert stats["edge_counts"]["calls"] == 1

    def test_query_dependents(self):
        kg = KnowledgeGraph()
        kg.add_node(GraphNode(path="core/AID.java", class_name="AID"))
        kg.add_node(GraphNode(path="core/Agent.java", class_name="Agent"))
        kg.add_node(GraphNode(path="tools/Main.java", class_name="Main"))
        kg.add_import_edge("core/Agent.java", "core/AID.java")
        kg.add_import_edge("tools/Main.java", "core/AID.java")
        deps = kg.query_dependents("core/AID.java")
        assert sorted(deps) == ["core/Agent.java", "tools/Main.java"]

    def test_query_dependents_inheritance(self):
        kg = KnowledgeGraph()
        kg.add_extends_edge("child/Child.java", "base/Base.java")
        kg.add_implements_edge("impl/Impl.java", "base/Base.java")
        assert kg.query_dependents("base/Base.java") == ["child/Child.java", "impl/Impl.java"]

    def test_rule_scope_is_multi_hop_and_descriptive(self):
        kg = KnowledgeGraph()
        kg.add_import_edge("a/A.java", "b/B.java")
        kg.add_import_edge("b/B.java", "c/C.java")
        scope = kg.query_rule_scope(["c/C.java"])
        assert scope["direct"] == 1
        assert scope["transitive_files"] == ["a/A.java", "b/B.java"]
        assert scope["total"] == 3
        assert scope["files"] == ["a/A.java", "b/B.java", "c/C.java"]
        assert scope["paths"][0]["reasons"] == ["imports", "imports"]

    def test_rule_scope_uses_cached_reverse_adjacency_for_large_graph(self):
        kg = KnowledgeGraph()
        size = 1200
        for index in range(size):
            kg.add_import_edge(f"F{index:04d}.java", f"F{index + 1:04d}.java")

        scope = kg.query_rule_scope([f"F{size:04d}.java"])
        assert scope["files"] == [f"F{index:04d}.java" for index in range(size + 1)]
        assert len(kg._reverse_adjacency["imports"]) == size
        reverse_index = kg._reverse_adjacency
        assert kg.query_rule_scope([f"F{size:04d}.java"]) == scope
        assert kg._reverse_adjacency is reverse_index

    def test_transform_order_dependency(self):
        kg = KnowledgeGraph()
        kg.add_import_edge("a/FileA.java", "b/FileB.java")
        rules = ["ruleA", "ruleB"]
        rule_files = {"ruleA": ["a/FileA.java"], "ruleB": ["b/FileB.java"]}
        order = kg.query_transform_order(rules, rule_files)
        assert set(order) == set(rules)
        assert order.index("ruleB") < order.index("ruleA")

    def test_transform_order_independent_stable(self):
        kg = KnowledgeGraph()
        rules = ["ruleA", "ruleB", "ruleC"]
        rule_files = {
            "ruleA": ["a/FileA.java"],
            "ruleB": ["b/FileB.java"],
            "ruleC": ["c/FileC.java"],
        }
        order = kg.query_transform_order(rules, rule_files)
        assert order == rules

    def test_transform_order_cycle(self):
        kg = KnowledgeGraph()
        kg.add_import_edge("a/FileA.java", "b/FileB.java")
        kg.add_import_edge("b/FileB.java", "a/FileA.java")
        rules = ["ruleA", "ruleB"]
        rule_files = {"ruleA": ["a/FileA.java"], "ruleB": ["b/FileB.java"]}
        order = kg.query_transform_order(rules, rule_files)
        assert set(order) == set(rules)
        assert len(order) == 2
        result = kg.query_transform_order_result(rules, rule_files)
        assert any(d["kind"] == "cycle" for d in result["diagnostics"])
        assert kg.query_transform_order_with_diagnostics(rules, rule_files) == result

    def test_transform_order_empty_rule_files(self):
        kg = KnowledgeGraph()
        kg.add_import_edge("a/FileA.java", "b/FileB.java")
        rules = ["ruleA", "ruleB", "ruleC"]
        order = kg.query_transform_order(rules, {})
        assert set(order) == set(rules)
        assert order == rules

    def test_transform_order_rule_without_files(self):
        kg = KnowledgeGraph()
        kg.add_import_edge("a/FileA.java", "b/FileB.java")
        rules = ["ruleA", "ruleB", "ruleC"]
        rule_files = {"ruleA": ["a/FileA.java"], "ruleB": ["b/FileB.java"]}
        order = kg.query_transform_order(rules, rule_files)
        assert set(order) == set(rules)
        assert order.index("ruleB") < order.index("ruleA")

    def test_roundtrip_save_load(self):
        kg = KnowledgeGraph()
        node = GraphNode(
            path="test/A.java", class_name="A", package="test",
            methods=[MethodInfo(name="foo", return_type="void", line_start=10, line_end=15)],
            fields=[FieldInfo(name="x", type="int")],
        )
        kg.add_node(node)
        kg.add_import_edge("test/A.java", "test/B.java")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.json")
            kg.save(path)
            kg2 = KnowledgeGraph.load(path)
            assert kg2.compute_stats()["total_files"] == 1
            assert kg2.compute_stats()["total_edges"] == 1
            assert kg2.nodes["test/A.java"].class_name == "A"
            assert kg2.nodes["test/A.java"].methods[0].name == "foo"
            assert kg2.to_dict()["schema_version"] == 2
            assert "nodes" in kg2.to_dict() and "edges" in kg2.to_dict() and "stats" in kg2.to_dict()
            assert kg2.to_dict()["source"] == {}
            assert set(kg2.to_dict()["diagnostics"]) >= {"parse_failures", "unresolved_types", "ambiguous_symbols"}

    def test_content_hash_excludes_volatile_metadata(self):
        kg = KnowledgeGraph(source={"workspace_root": "workspace", "java_files": 0})
        first = kg.to_dict()
        second = kg.to_dict()
        assert first["content_hash"] == second["content_hash"]
        assert "generated_at" not in first


class TestTreeSitterQueries:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.parser, self.lang = get_parser()

    def _parse(self, filename):
        path = os.path.join(FIXTURES_DIR, filename)
        tree, src = parse_file(self.parser, path)
        return tree.root_node, src

    def test_extract_imports(self):
        root, src = self._parse("SampleA.java")
        imports = extract_imports(root, src, self.lang)
        assert len(imports) == 2
        assert "java.util.List" in imports
        assert "java.util.ArrayList" in imports

    def test_extract_class_info(self):
        root, src = self._parse("SampleA.java")
        classes = extract_class_info(root, src, self.lang)
        assert len(classes) >= 1
        main = classes[0]
        assert main["name"] == "SampleA"
        assert main["kind"] == "class"
        assert "SampleB" in main.get("superclass", "")

    def test_extract_methods(self):
        root, src = self._parse("SampleA.java")
        methods = extract_methods(root, src, self.lang)
        method_names = [m["name"] for m in methods]
        assert "process" in method_names
        assert "reset" in method_names

    def test_extract_fields(self):
        root, src = self._parse("SampleA.java")
        fields = extract_fields(root, src, self.lang)
        field_names = [f["name"] for f in fields]
        assert "items" in field_names

    def test_extract_calls(self):
        root, src = self._parse("SampleA.java")
        calls = extract_calls(root, src, self.lang)
        method_names = [c["method_name"] for c in calls]
        assert "getValue" in method_names
        assert "computeLength" in method_names

    def test_extract_method_type_references(self):
        root, src = self._parse("SampleA.java")
        methods = extract_methods(root, src, self.lang)
        process = next(m for m in methods if m["name"] == "process")
        assert process["return_type"] == "String"
        assert process["parameters"][0]["type"] == "String"

    def test_extract_interface(self):
        root, src = self._parse("SampleInterface.java")
        classes = extract_class_info(root, src, self.lang)
        assert len(classes) >= 1
        assert classes[0]["kind"] == "interface"
        assert classes[0]["name"] == "SampleInterface"

    def test_wildcard_imports(self):
        root, src = self._parse("WildcardConsumer.java")
        imports = extract_imports(root, src, self.lang)
        assert any("tests.fixtures.knowledge_graph" in imp for imp in imports)


class TestBuildGraph:
    def test_build_on_fixtures(self):
        import subprocess
        art_dir = os.path.join(FIXTURES_DIR, "artifacts")
        result = subprocess.run(
            [
                sys.executable,
                ".claude/skills/jade-core-knowledge-graph/scripts/build_graph.py",
                "--workspace", FIXTURES_DIR,
                "--artifacts-dir", art_dir,
            ],
            capture_output=True, text=True,
        )
        assert result.returncode in (0, 1)

        artifact = os.path.join(art_dir, "03.5-knowledge-graph.json")
        assert os.path.isfile(artifact)

        with open(artifact) as f:
            data = json.load(f)

        nodes = data["nodes"]
        assert len(nodes) == 8
        assert "SampleA.java" in nodes
        assert nodes["SampleA.java"]["kind"] == "class"
        assert nodes["SampleInterface.java"]["kind"] == "interface"
        assert nodes["PackageMismatch.java"]["package"] == "declared.package"

        edges = data["edges"]
        assert len(edges["extends"]) > 0
        assert len(edges["implements"]) > 0
        assert len(edges["calls"]) > 0
        assert any(edge["from_method"] == "process" for edge in edges["calls"])
        assert any(edge["from"] == "WildcardConsumer.java" and edge["to"] == "SampleA.java"
                   for edge in edges["calls"])

        if os.path.isdir(art_dir):
            shutil.rmtree(art_dir)

    def test_declaration_identity_and_wildcard_provenance(self, tmp_path):
        source = tmp_path / "wrong" / "Consumer.java"
        source.parent.mkdir()
        source.write_text(
            "package actual.pkg;\nimport actual.pkg.*;\npublic class Consumer { private Target target; }\n"
        )
        (tmp_path / "Target.java").write_text("package actual.pkg; public class Target {}\n")
        parser, lang = get_parser()
        files = scan_workspace(str(tmp_path))
        nodes, diagnostics = parse_files(files, parser, lang, return_diagnostics=True)
        kg = resolve_graph(nodes, diagnostics)
        assert kg.nodes["wrong/Consumer.java"].package == "actual.pkg"
        assert {e.to_file for e in kg.edges["imports"]} == {"Target.java"}
        assert kg.edges["imports"][0].provenance == "wildcard"

    def test_parse_diagnostics_are_partial(self, tmp_path):
        (tmp_path / "Broken.java").write_text("public class Broken {\n    void x( {\n")
        parser, lang = get_parser()
        nodes, diagnostics = parse_files(scan_workspace(str(tmp_path)), parser, lang, return_diagnostics=True)
        kg = resolve_graph(nodes, diagnostics)
        assert kg.diagnostics
        failures = [d for d in kg.diagnostics["parse_failures"] if d["kind"] == "parse_error"]
        assert failures
        assert all(isinstance(d["line"], int) and d["line"] >= 1 for d in failures)
        assert all(isinstance(d["column"], int) and d["column"] >= 1 for d in failures)
        artifact_dir = tmp_path / "artifacts"
        result = __import__("subprocess").run(
            [sys.executable, ".claude/skills/jade-core-knowledge-graph/scripts/build_graph.py",
             "--workspace", str(tmp_path), "--artifacts-dir", str(artifact_dir)],
            capture_output=True, text=True,
        )
        assert result.returncode == 1

    def test_source_and_structured_diagnostics_contract(self, tmp_path):
        (tmp_path / "Consumer.java").write_text(
            "package p; import p.Missing; public class Consumer { private Missing value; }\n"
        )
        parser, lang = get_parser()
        nodes, diagnostics = parse_files(scan_workspace(str(tmp_path)), parser, lang, return_diagnostics=True)
        kg = resolve_graph(nodes, diagnostics)
        kg.source = {"workspace": str(tmp_path), "java_file_count": 1}
        data = kg.to_dict()
        assert data["source"]["java_file_count"] == 1
        assert data["source"]["workspace_root"] == str(tmp_path)
        assert data["source"]["java_files"] == 1
        assert isinstance(data["diagnostics"], dict)
        assert any(item["kind"] == "unresolved_import" for item in data["diagnostics"]["unresolved_types"])

    def test_duplicate_declarations_are_ambiguous_without_crashing(self, tmp_path):
        (tmp_path / "One.java").write_text("package p; public class Same {}\n")
        (tmp_path / "Two.java").write_text("package p; public class Same {}\n")
        (tmp_path / "Three.java").write_text("package p; public class Same {}\n")
        (tmp_path / "Use.java").write_text("package q; import p.Same; public class Use { Same same; }\n")
        parser, lang = get_parser()
        nodes, diagnostics = parse_files(scan_workspace(str(tmp_path)), parser, lang, return_diagnostics=True)
        kg = resolve_graph(nodes, diagnostics)
        ambiguous = kg.to_dict()["diagnostics"]["ambiguous_symbols"]
        assert any(item["symbol"] == "p.Same" for item in ambiguous)
        assert not kg.edges["imports"]

        assert any(item["symbol"] == "Same" for item in ambiguous)

    def test_wildcard_duplicate_name_is_ambiguous(self, tmp_path):
        (tmp_path / "One.java").write_text("package p; public class Same {}\n")
        (tmp_path / "Two.java").write_text("package p; public class Same {}\n")
        (tmp_path / "Use.java").write_text("package q; import p.*; public class Use {}\n")
        parser, lang = get_parser()
        nodes, diagnostics = parse_files(scan_workspace(str(tmp_path)), parser, lang, return_diagnostics=True)
        kg = resolve_graph(nodes, diagnostics)
        assert any(item["symbol"] == "p.Same" for item in kg.to_dict()["diagnostics"]["ambiguous_symbols"])
        assert not kg.edges["imports"]

    def test_wildcard_import_collision_across_packages_is_ambiguous(self, tmp_path):
        (tmp_path / "P.java").write_text("package p; public class Same {}\n")
        (tmp_path / "Q.java").write_text("package q; public class Same {}\n")
        (tmp_path / "Use.java").write_text(
            "package use; import p.*; import q.*; public class Use { Same same; }\n"
        )
        parser, lang = get_parser()
        nodes, diagnostics = parse_files(scan_workspace(str(tmp_path)), parser, lang, return_diagnostics=True)
        kg = resolve_graph(nodes, diagnostics)
        ambiguous = kg.to_dict()["diagnostics"]["ambiguous_symbols"]
        assert any(item["symbol"] == "Same" and
                   set(item["candidates"]) == {"P.java", "Q.java"} for item in ambiguous)
        assert not kg.edges["imports"]
        assert not kg.edges["type_refs"]

    def test_fixture_package_declaration_resolves_independently_of_path(self):
        parser, lang = get_parser()
        nodes, _ = parse_files(scan_workspace(FIXTURES_DIR), parser, lang, return_diagnostics=True)
        assert nodes["PackageMismatch.java"]["node"].package == "declared.package"

    def test_fixture_multi_hop_scope_uses_resolved_type_edges(self):
        parser, lang = get_parser()
        nodes, diagnostics = parse_files(scan_workspace(FIXTURES_DIR), parser, lang, return_diagnostics=True)
        kg = resolve_graph(nodes, diagnostics)
        scope = kg.query_rule_scope(["MultiHopC.java"])
        assert scope["files"] == ["MultiHopA.java", "MultiHopB.java", "MultiHopC.java"]
        assert scope["transitive_files"] == ["MultiHopA.java", "MultiHopB.java"]

    def test_method_parameter_and_return_type_edges(self, tmp_path):
        (tmp_path / "Target.java").write_text("package p; public class Target {}\n")
        (tmp_path / "Consumer.java").write_text(
            "package q; import p.Target; public class Consumer { Target convert(Target input) { return input; } }\n"
        )
        parser, lang = get_parser()
        nodes, diagnostics = parse_files(scan_workspace(str(tmp_path)), parser, lang, return_diagnostics=True)
        kg = resolve_graph(nodes, diagnostics)
        refs = [edge for edge in kg.edges["type_refs"] if edge.to_file == "Target.java"]
        assert {edge.type_name for edge in refs} == {"Target"}
        assert {edge.field for edge in refs} >= {"method:convert:return", "method:convert:parameter:input"}

    def test_explicit_import_wins_over_same_name_from_other_package(self, tmp_path):
        (tmp_path / "P.java").write_text("package p; public class Target { String get() { return \"p\"; } }\n")
        (tmp_path / "Q.java").write_text("package q; public class Target { String get() { return \"q\"; } }\n")
        (tmp_path / "Consumer.java").write_text(
            "package consumer; import p.Target; "
            "public class Consumer { Target field; "
            "Target convert(Target input) { input.get(); return input; } }\n"
        )
        parser, lang = get_parser()
        nodes, diagnostics = parse_files(scan_workspace(str(tmp_path)), parser, lang, return_diagnostics=True)
        kg = resolve_graph(nodes, diagnostics)

        type_refs = [edge for edge in kg.edges["type_refs"] if edge.from_file == "Consumer.java"]
        assert type_refs
        assert {edge.to_file for edge in type_refs} == {"P.java"}
        assert any(edge.to_file == "P.java" and edge.to_method == "get"
                   for edge in kg.edges["calls"])
        assert not any(item.get("file") == "Consumer.java" and item.get("symbol") == "Target"
                       for item in kg.to_dict()["diagnostics"]["ambiguous_symbols"])

    def test_earlier_file_field_receiver_resolves_to_target(self, tmp_path):
        (tmp_path / "Consumer.java").write_text(
            "package q; import p.Target; public class Consumer { Target target; void run() { target.get(); } }\n"
        )
        (tmp_path / "Target.java").write_text("package p; public class Target { String get() { return \"x\"; } }\n")
        parser, lang = get_parser()
        nodes, diagnostics = parse_files(scan_workspace(str(tmp_path)), parser, lang, return_diagnostics=True)
        kg = resolve_graph(nodes, diagnostics)
        assert any(edge.from_file == "Consumer.java" and edge.to_file == "Target.java"
                   and edge.to_method == "get" for edge in kg.edges["calls"])

    def test_receiver_types_are_scoped_to_the_calling_method(self, tmp_path):
        (tmp_path / "P.java").write_text("package p; public class P { void get() {} }\n")
        (tmp_path / "Q.java").write_text("package q; public class Q { void get() {} }\n")
        (tmp_path / "Consumer.java").write_text(
            "package consumer; import p.P; import q.Q; public class Consumer {"
            " void one() { P p; p.get(); } void two() { Q p; p.get(); } }\n"
        )
        parser, lang = get_parser()
        nodes, diagnostics = parse_files(scan_workspace(str(tmp_path)), parser, lang, return_diagnostics=True)
        kg = resolve_graph(nodes, diagnostics)
        calls = [edge for edge in kg.edges["calls"] if edge.from_file == "Consumer.java"]
        assert {(edge.from_method, edge.to_file, edge.to_method) for edge in calls} == {
            ("one", "P.java", "get"), ("two", "Q.java", "get")
        }

    def test_unresolved_receiver_call_is_structured_diagnostic(self, tmp_path):
        (tmp_path / "Consumer.java").write_text(
            "public class Consumer { void run() { Missing receiver; receiver.get(); } }\n"
        )
        parser, lang = get_parser()
        nodes, diagnostics = parse_files(scan_workspace(str(tmp_path)), parser, lang, return_diagnostics=True)
        kg = resolve_graph(nodes, diagnostics)
        unresolved = [item for item in kg.to_dict()["diagnostics"]["other"]
                      if item.get("kind") == "unresolved_receiver_call"]
        assert unresolved == [{"kind": "unresolved_receiver_call", "file": "Consumer.java",
                              "line": 1, "receiver": "receiver", "method": "get",
                              "caller_method": "run"}]

    def test_transform_order_reports_three_way_ownership_ambiguity(self):
        kg = KnowledgeGraph()
        result = kg.query_transform_order_result(
            ["a", "b", "c"], {"a": ["Shared.java"], "b": ["Shared.java"], "c": ["Shared.java"]}
        )
        assert result["order"] == ["a", "b", "c"]
        assert result["diagnostics"][0]["kind"] == "ambiguous_file_ownership"

    def test_serialized_order_is_deterministic(self):
        kg = KnowledgeGraph()
        kg.add_node(GraphNode(path="z/Z.java", class_name="Z"))
        kg.add_node(GraphNode(path="a/A.java", class_name="A"))
        kg.add_import_edge("z/Z.java", "a/A.java")
        assert list(kg.to_dict()["nodes"]) == ["a/A.java", "z/Z.java"]
        assert kg.to_dict()["edges"]["imports"][0]["from"] == "z/Z.java"


class TestQueryGraph:
    def test_dependents_query(self):
        import subprocess
        art_dir = os.path.join(FIXTURES_DIR, "artifacts")
        subprocess.run(
            [
                sys.executable,
                ".claude/skills/jade-core-knowledge-graph/scripts/build_graph.py",
                "--workspace", FIXTURES_DIR,
                "--artifacts-dir", art_dir,
            ],
            capture_output=True, text=True,
        )

        result = subprocess.run(
            [
                sys.executable,
                ".claude/skills/jade-core-knowledge-graph/scripts/query_graph.py",
                "--graph", os.path.join(art_dir, "03.5-knowledge-graph.json"),
                "--query", "dependents",
                "--target", "SampleB.java",
            ],
            capture_output=True, text=True,
        )
        output = result.stdout.strip()
        assert "WildcardConsumer.java" in output

        if os.path.isdir(art_dir):
            shutil.rmtree(art_dir)
