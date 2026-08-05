"""Knowledge Graph schema: dataclasses, KnowledgeGraph class, query methods."""

import json
import os
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional


@dataclass
class Parameter:
    name: str
    type: str


@dataclass
class MethodInfo:
    name: str
    modifiers: List[str] = field(default_factory=list)
    return_type: str = ""
    parameters: List[Parameter] = field(default_factory=list)
    exceptions: List[str] = field(default_factory=list)
    annotations: List[str] = field(default_factory=list)
    line_start: int = 0
    line_end: int = 0


@dataclass
class FieldInfo:
    name: str
    type: str
    modifiers: List[str] = field(default_factory=list)
    annotations: List[str] = field(default_factory=list)


@dataclass
class ConstructorInfo:
    name: str
    modifiers: List[str] = field(default_factory=list)
    parameters: List[Parameter] = field(default_factory=list)
    exceptions: List[str] = field(default_factory=list)
    line_start: int = 0


@dataclass
class GraphNode:
    path: str
    package: str = ""
    class_name: str = ""
    kind: str = "class"
    modifiers: List[str] = field(default_factory=list)
    extends: str = ""
    implements: List[str] = field(default_factory=list)
    methods: List[MethodInfo] = field(default_factory=list)
    fields: List[FieldInfo] = field(default_factory=list)
    constructors: List[ConstructorInfo] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        if not d["extends"]:
            d.pop("extends")
        return d

    @staticmethod
    def from_dict(d: dict):
        methods = [MethodInfo(**m) for m in d.pop("methods", [])]
        fields = [FieldInfo(**f) for f in d.pop("fields", [])]
        constructors = [ConstructorInfo(**c) for c in d.pop("constructors", [])]
        return GraphNode(**d, methods=methods, fields=fields, constructors=constructors)


@dataclass
class ImportEdge:
    from_file: str
    to_file: str


@dataclass
class ExtendsEdge:
    from_file: str
    to_file: str


@dataclass
class ImplementsEdge:
    from_file: str
    to_file: str


@dataclass
class CallEdge:
    from_file: str
    from_method: str
    to_file: str
    to_method: str
    line: int = 0


@dataclass
class TypeRefEdge:
    from_file: str
    to_file: str
    field: str = ""
    type_name: str = ""


class KnowledgeGraph:
    """Container for nodes and typed edges with query methods."""

    def __init__(self):
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: Dict[str, list] = {
            "imports": [],
            "extends": [],
            "implements": [],
            "calls": [],
            "type_refs": [],
        }

    def add_node(self, node: GraphNode):
        self.nodes[node.path] = node

    def add_import_edge(self, from_file: str, to_file: str):
        self.edges["imports"].append(ImportEdge(from_file, to_file))

    def add_extends_edge(self, from_file: str, to_file: str):
        self.edges["extends"].append(ExtendsEdge(from_file, to_file))

    def add_implements_edge(self, from_file: str, to_file: str):
        self.edges["implements"].append(ImplementsEdge(from_file, to_file))

    def add_call_edge(self, from_file: str, from_method: str, to_file: str, to_method: str, line: int = 0):
        self.edges["calls"].append(CallEdge(from_file, from_method, to_file, to_method, line))

    def add_type_ref_edge(self, from_file: str, to_file: str, field: str = "", type_name: str = ""):
        self.edges["type_refs"].append(TypeRefEdge(from_file, to_file, field, type_name))

    def query_dependents(self, target: str) -> list:
        """All files that import or reference target."""
        dependents = set()
        for e in self.edges["imports"]:
            if e.to_file == target:
                dependents.add(e.from_file)
        for e in self.edges["type_refs"]:
            if e.to_file == target:
                dependents.add(e.from_file)
        for e in self.edges["calls"]:
            if e.to_file == target:
                dependents.add(e.from_file)
        return sorted(dependents)

    def query_call_sites(self, target: str, method_name: str) -> list:
        """All call sites for a specific method."""
        results = []
        for e in self.edges["calls"]:
            if e.to_file == target and e.to_method == method_name:
                results.append({"file": e.from_file, "line": e.line, "caller_method": e.from_method})
        return results

    def query_rule_scope(self, flagged_files: list) -> dict:
        """For a list of flagged files, compute direct + transitive scope."""
        direct = set(flagged_files)
        transitive = set()
        for ff in flagged_files:
            for dep in self.query_dependents(ff):
                transitive.add(dep)
        transitive -= direct
        return {"direct": len(direct), "transitive": len(transitive), "total": len(direct | transitive)}

    def query_consumer_coverage(self, files: list, consumer_file_map: dict) -> list:
        """Which consumer projects cover these files."""
        covered = set()
        for f in files:
            for consumer, consumer_files in consumer_file_map.items():
                if any(f.endswith(cf) or cf.endswith(f) for cf in consumer_files):
                    covered.add(consumer)
        return sorted(covered)

    def query_transform_order(self, rules: list, rule_files: dict) -> list:
        """Topologically sort rules. Placeholder: returns as-is for now."""
        return rules

    def to_dict(self) -> dict:
        nodes_dict = {}
        for path, node in self.nodes.items():
            nodes_dict[path] = node.to_dict()

        edges_dict = {}
        for etype, elist in self.edges.items():
            if etype == "imports":
                edges_dict[etype] = [{"from": e.from_file, "to": e.to_file} for e in elist]
            elif etype == "extends":
                edges_dict[etype] = [{"from": e.from_file, "to": e.to_file} for e in elist]
            elif etype == "implements":
                edges_dict[etype] = [{"from": e.from_file, "to": e.to_file} for e in elist]
            elif etype == "calls":
                edges_dict[etype] = [
                    {"from": e.from_file, "from_method": e.from_method,
                     "to": e.to_file, "to_method": e.to_method, "line": e.line}
                    for e in elist
                ]
            elif etype == "type_refs":
                edges_dict[etype] = [
                    {"from": e.from_file, "to": e.to_file,
                     "field": e.field, "type": e.type_name}
                    for e in elist
                ]

        return {"nodes": nodes_dict, "edges": edges_dict}

    @staticmethod
    def from_dict(d: dict):
        kg = KnowledgeGraph()
        for path, node_data in d.get("nodes", {}).items():
            kg.nodes[path] = GraphNode.from_dict(node_data)
        edges_data = d.get("edges", {})
        for e in edges_data.get("imports", []):
            kg.add_import_edge(e["from"], e["to"])
        for e in edges_data.get("extends", []):
            kg.add_extends_edge(e["from"], e["to"])
        for e in edges_data.get("implements", []):
            kg.add_implements_edge(e["from"], e["to"])
        for e in edges_data.get("calls", []):
            kg.add_call_edge(e["from"], e.get("from_method", ""), e["to"], e.get("to_method", ""), e.get("line", 0))
        for e in edges_data.get("type_refs", []):
            kg.add_type_ref_edge(e["from"], e["to"], e.get("field", ""), e.get("type", ""))
        return kg

    def save(self, filepath: str):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @staticmethod
    def load(filepath: str):
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return KnowledgeGraph.from_dict(data)

    def compute_stats(self) -> dict:
        return {
            "total_files": len(self.nodes),
            "total_edges": sum(len(v) for v in self.edges.values()),
            "edge_counts": {k: len(v) for k, v in self.edges.items()},
        }
