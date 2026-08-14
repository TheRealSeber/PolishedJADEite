"""Knowledge Graph schema: dataclasses, KnowledgeGraph class, query methods."""

import json
import os
import tempfile
import hashlib
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
        d = dict(d)
        methods = [MethodInfo(**m) for m in d.pop("methods", [])]
        fields = [FieldInfo(**f) for f in d.pop("fields", [])]
        constructors = [ConstructorInfo(**c) for c in d.pop("constructors", [])]
        return GraphNode(**d, methods=methods, fields=fields, constructors=constructors)


@dataclass
class ImportEdge:
    from_file: str
    to_file: str
    provenance: str = "direct"


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

    def __init__(self, source_identity=None, diagnostics=None, source=None):
        self.schema_version = 2
        self.source_identity = source_identity or {}
        self.source = source or {}
        self.diagnostics = {"parse_failures": [], "unresolved_types": [],
                            "ambiguous_symbols": [], "other": []}
        for diagnostic in diagnostics or []:
            self.add_diagnostic(diagnostic)
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

    def add_import_edge(self, from_file: str, to_file: str, provenance: str = "direct"):
        self.edges["imports"].append(ImportEdge(from_file, to_file, provenance))

    def add_extends_edge(self, from_file: str, to_file: str):
        self.edges["extends"].append(ExtendsEdge(from_file, to_file))

    def add_implements_edge(self, from_file: str, to_file: str):
        self.edges["implements"].append(ImplementsEdge(from_file, to_file))

    def add_call_edge(self, from_file: str, from_method: str, to_file: str, to_method: str, line: int = 0):
        self.edges["calls"].append(CallEdge(from_file, from_method, to_file, to_method, line))

    def add_type_ref_edge(self, from_file: str, to_file: str, field: str = "", type_name: str = ""):
        self.edges["type_refs"].append(TypeRefEdge(from_file, to_file, field, type_name))

    def add_diagnostic(self, diagnostic):
        """Normalize legacy diagnostic records into the stable artifact shape."""
        if not isinstance(diagnostic, dict):
            self.diagnostics["other"].append({"message": str(diagnostic)})
            return
        kind = diagnostic.get("kind", "")
        if kind in ("parse_error", "parse_failure"):
            bucket = "parse_failures"
        elif kind in ("unresolved_import", "unresolved_type"):
            bucket = "unresolved_types"
        elif kind in ("ambiguous_import", "ambiguous_symbol", "ambiguous_declaration"):
            bucket = "ambiguous_symbols"
        else:
            bucket = "other"
        self.diagnostics[bucket].append(dict(diagnostic))

    def query_dependents(self, target: str) -> list:
        """All files that import or reference target, in stable order."""
        dependents = set()
        for etype in ("imports", "extends", "implements", "calls", "type_refs"):
            for e in self.edges[etype]:
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
        """Compute the complete reverse dependency closure with paths."""
        direct = set(flagged_files)
        visited = set(direct)
        queue = [(f, [f], []) for f in sorted(direct)]
        paths = []
        while queue:
            target, path, reasons = queue.pop(0)
            for etype in ("imports", "extends", "implements", "calls", "type_refs"):
                edges = sorted(self.edges[etype], key=lambda e: (e.from_file, e.to_file))
                for edge in edges:
                    if edge.to_file != target or edge.from_file in visited:
                        continue
                    visited.add(edge.from_file)
                    next_path = path + [edge.from_file]
                    next_reasons = reasons + [etype]
                    queue.append((edge.from_file, next_path, next_reasons))
                    paths.append({"file": edge.from_file, "path": next_path, "reasons": next_reasons})
        transitive = visited - direct
        return {
            "direct": len(direct), "transitive": len(transitive), "total": len(visited),
            "direct_files": sorted(direct), "transitive_files": sorted(transitive),
            "files": sorted(visited),
            "paths": sorted(paths, key=lambda p: p["file"]),
        }

    def query_consumer_coverage(self, files: list, consumer_file_map: dict) -> list:
        """Which consumer projects cover these files."""
        covered = set()
        for f in files:
            for consumer, consumer_files in consumer_file_map.items():
                if any(f.endswith(cf) or cf.endswith(f) for cf in consumer_files):
                    covered.add(consumer)
        return sorted(covered)

    def query_transform_order(self, rules: list, rule_files: dict) -> list:
        """Topologically sort rules so dependent transforms run first."""
        return self.query_transform_order_result(rules, rule_files)["order"]

    def query_transform_order_result(self, rules: list, rule_files: dict) -> dict:
        """Return transform order plus ownership and cycle diagnostics."""
        if not rules:
            return {"order": [], "diagnostics": []}

        file_to_rule = {}
        ownership_conflicts = {}
        diagnostics = []
        for rule in rules:
            for f in sorted(set(rule_files.get(rule, []) or [])):
                if f in file_to_rule and file_to_rule[f] != rule:
                    prior = file_to_rule[f]
                    rules_for_file = ownership_conflicts.setdefault(f, set())
                    if prior is not None:
                        rules_for_file.add(prior)
                    rules_for_file.add(rule)
                    file_to_rule[f] = None
                elif f not in file_to_rule:
                    file_to_rule[f] = rule

        for f, owners in ownership_conflicts.items():
            diagnostics.append({"kind": "ambiguous_file_ownership", "file": f,
                                "rules": sorted(owners)})

        deps = {rule: set() for rule in rules}
        depended_by = {rule: set() for rule in rules}
        for etype in ("imports", "extends", "implements", "calls", "type_refs"):
            for e in self.edges.get(etype, []):
                from_rule = file_to_rule.get(e.from_file)
                to_rule = file_to_rule.get(e.to_file)
                if from_rule and to_rule and from_rule != to_rule:
                    deps[from_rule].add(to_rule)
                    depended_by[to_rule].add(from_rule)

        indegree = {rule: len(deps[rule]) for rule in rules}
        ready = [rule for rule in rules if indegree[rule] == 0]
        result = []

        while ready:
            rule = ready.pop(0)
            result.append(rule)
            for nxt in sorted(depended_by[rule], key=rules.index):
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    ready.append(nxt)
                    ready.sort(key=rules.index)

        seen = set(result)
        remaining = [rule for rule in rules if rule not in seen]
        if remaining:
            diagnostics.append({"kind": "cycle", "rules": remaining})
        result.extend(remaining)
        return {"order": result, "diagnostics": diagnostics}

    def query_transform_order_with_diagnostics(self, rules: list, rule_files: dict) -> dict:
        """Compatibility alias for callers using the explicit diagnostics name."""
        return self.query_transform_order_result(rules, rule_files)

    def to_dict(self) -> dict:
        nodes_dict = {path: self.nodes[path].to_dict() for path in sorted(self.nodes)}

        edges_dict = {}
        for etype, elist in self.edges.items():
            if etype == "imports":
                edges_dict[etype] = [{"from": e.from_file, "to": e.to_file, "provenance": e.provenance}
                                     for e in sorted(elist, key=lambda x: (x.from_file, x.to_file, x.provenance))]
            elif etype == "extends":
                edges_dict[etype] = [{"from": e.from_file, "to": e.to_file}
                                     for e in sorted(elist, key=lambda x: (x.from_file, x.to_file))]
            elif etype == "implements":
                edges_dict[etype] = [{"from": e.from_file, "to": e.to_file}
                                     for e in sorted(elist, key=lambda x: (x.from_file, x.to_file))]
            elif etype == "calls":
                edges_dict[etype] = [
                    {"from": e.from_file, "from_method": e.from_method,
                     "to": e.to_file, "to_method": e.to_method, "line": e.line}
                     for e in sorted(elist, key=lambda x: (x.from_file, x.to_file, x.from_method, x.to_method, x.line))
                ]
            elif etype == "type_refs":
                edges_dict[etype] = [
                    {"from": e.from_file, "to": e.to_file,
                     "field": e.field, "type": e.type_name}
                     for e in sorted(elist, key=lambda x: (x.from_file, x.to_file, x.field, x.type_name))
                ]

        source = dict(self.source)
        if "workspace_root" not in source and "workspace" in source:
            source["workspace_root"] = source["workspace"]
        if "java_files" not in source and "java_file_count" in source:
            source["java_files"] = source["java_file_count"]
        diagnostics = {bucket: sorted(values, key=lambda d: json.dumps(d, sort_keys=True))
                       for bucket, values in self.diagnostics.items()}
        result = {"schema_version": self.schema_version, "source": source,
                "source_identity": self.source_identity, "diagnostics": diagnostics,
                "nodes": nodes_dict, "edges": edges_dict, "stats": self.compute_stats()}
        canonical = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        result["content_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return result

    @staticmethod
    def from_dict(d: dict):
        raw_diagnostics = d.get("diagnostics", {})
        if isinstance(raw_diagnostics, dict):
            legacy_diagnostics = [item for values in raw_diagnostics.values() for item in values]
        else:
            legacy_diagnostics = raw_diagnostics
        kg = KnowledgeGraph(d.get("source_identity", {}), legacy_diagnostics, d.get("source", {}))
        kg.schema_version = d.get("schema_version", 1)
        for path, node_data in d.get("nodes", {}).items():
            kg.nodes[path] = GraphNode.from_dict(node_data)
        edges_data = d.get("edges", {})
        for e in edges_data.get("imports", []):
            kg.add_import_edge(e["from"], e["to"], e.get("provenance", "direct"))
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
        directory = os.path.dirname(os.path.abspath(filepath))
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".kg-", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, filepath)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

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
