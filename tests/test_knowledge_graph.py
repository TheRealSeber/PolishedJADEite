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
        assert scope["paths"][0]["reasons"] == ["imports", "imports"]

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
        assert len(nodes) == 4
        assert "SampleA.java" in nodes
        assert nodes["SampleA.java"]["kind"] == "class"
        assert nodes["SampleInterface.java"]["kind"] == "interface"

        edges = data["edges"]
        assert len(edges["extends"]) > 0
        assert len(edges["implements"]) > 0

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
        (tmp_path / "Broken.java").write_text("public class Broken { void x( {\n")
        parser, lang = get_parser()
        nodes, diagnostics = parse_files(scan_workspace(str(tmp_path)), parser, lang, return_diagnostics=True)
        kg = resolve_graph(nodes, diagnostics)
        assert kg.diagnostics
        assert any(d["kind"] == "parse_error" for d in kg.diagnostics["parse_failures"])
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
