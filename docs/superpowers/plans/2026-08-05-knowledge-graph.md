# jade-core-knowledge-graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a universal Java Knowledge Graph skill that parses any Java codebase with tree-sitter and produces a queryable dependency graph artifact consumed by downstream pipeline phases.

**Architecture:** 4-script skill (SKILL.md + build_graph.py + query_graph.py + schema.py + tree_sitter_java_queries.py). 4-stage build pipeline: SCAN → PARSE → RESOLVE → SERIALIZE. 5 edge types: imports, extends, implements, calls, type_refs. 5 query types: dependents, impact-chain, rule-scope, consumer-coverage, transform-order. File-based handoff via `03.5-knowledge-graph.json`.

**Tech Stack:** Python 3, tree-sitter + tree-sitter-java, stdlib json/pathlib/dataclasses, pytest

---

## File Map

| File | Responsibility |
|------|---------------|
| `.claude/skills/jade-core-knowledge-graph/SKILL.md` | Agent instructions for invoking the skill |
| `.claude/skills/jade-core-knowledge-graph/scripts/tree_sitter_java_queries.py` | tree-sitter query strings + AST extraction helpers |
| `.claude/skills/jade-core-knowledge-graph/scripts/schema.py` | Dataclasses, KnowledgeGraph class, query methods |
| `.claude/skills/jade-core-knowledge-graph/scripts/build_graph.py` | 4-stage main entry, CLI args, artifact output |
| `.claude/skills/jade-core-knowledge-graph/scripts/query_graph.py` | CLI query wrapper (5 query types) |
| `tests/fixtures/knowledge-graph/SampleA.java` | Fixture: class with imports, extends, method calls |
| `tests/fixtures/knowledge-graph/SampleB.java` | Fixture: class imported by SampleA |
| `tests/fixtures/knowledge-graph/SampleInterface.java` | Fixture: interface with method signatures |
| `tests/fixtures/knowledge-graph/WildcardConsumer.java` | Fixture: wildcard import consumer |
| `tests/test_knowledge_graph.py` | Test suite: unit + integration |

---

### Task 1: Install dependencies

**Files:**
- Modify: (none, pip install only)

- [ ] **Step 1: Install tree-sitter and tree-sitter-java**

```bash
pip install tree-sitter tree-sitter-java
```

- [ ] **Step 2: Verify imports work**

```bash
python -c "import tree_sitter; import tree_sitter_java; print('tree-sitter OK:', tree_sitter.__version__ if hasattr(tree_sitter, '__version__') else 'imported')"
```

Expected: prints "tree-sitter OK" without errors.

---

### Task 2: Create test fixtures (Java source files)

**Files:**
- Create: `tests/fixtures/knowledge-graph/SampleA.java`
- Create: `tests/fixtures/knowledge-graph/SampleB.java`
- Create: `tests/fixtures/knowledge-graph/SampleInterface.java`
- Create: `tests/fixtures/knowledge-graph/WildcardConsumer.java`

- [ ] **Step 1: Write SampleB.java (leaf dependency)**

```java
package tests.fixtures.knowledge_graph;

import java.io.Serializable;

public class SampleB implements Serializable {
    private String value;

    public SampleB(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }

    public int computeLength() {
        return value.length();
    }
}
```

Write to: `tests/fixtures/knowledge-graph/SampleB.java`

- [ ] **Step 2: Write SampleInterface.java (interface)**

```java
package tests.fixtures.knowledge_graph;

public interface SampleInterface {
    String process(String input);
    void reset();
}
```

Write to: `tests/fixtures/knowledge-graph/SampleInterface.java`

- [ ] **Step 3: Write SampleA.java (main fixture — extends SampleB, implements SampleInterface, calls methods)**

```java
package tests.fixtures.knowledge_graph;

import java.util.List;
import java.util.ArrayList;

public class SampleA extends SampleB implements SampleInterface {
    private List<String> items;

    public SampleA(String value) {
        super(value);
        this.items = new ArrayList<>();
    }

    @Override
    public String process(String input) {
        String baseValue = getValue();
        int length = computeLength();
        return baseValue + input + length;
    }

    @Override
    public void reset() {
        items.clear();
    }

    public void addItem(String item) {
        items.add(item);
    }
}
```

Write to: `tests/fixtures/knowledge-graph/SampleA.java`

- [ ] **Step 4: Write WildcardConsumer.java (wildcard import)**

```java
package tests.fixtures.knowledge_graph;

import tests.fixtures.knowledge_graph.*;

public class WildcardConsumer {
    private SampleA a;
    private SampleB b;

    public WildcardConsumer() {
        this.a = new SampleA("test");
        this.b = new SampleB("other");
    }

    public String getFromA() {
        return a.getValue();
    }

    public int getFromB() {
        return b.computeLength();
    }
}
```

Write to: `tests/fixtures/knowledge-graph/WildcardConsumer.java`

- [ ] **Step 5: Verify fixtures compile** (optional — checks fixture correctness)

```bash
javac tests/fixtures/knowledge-graph/*.java
```

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/knowledge-graph/
git commit -m "test: add Java fixtures for knowledge-graph skill"
```

---

### Task 3: Write tree_sitter_java_queries.py

**Files:**
- Create: `.claude/skills/jade-core-knowledge-graph/scripts/tree_sitter_java_queries.py`

- [ ] **Step 1: Create directory structure**

```bash
New-Item -ItemType Directory -Force -Path ".claude/skills/jade-core-knowledge-graph/scripts"
```

- [ ] **Step 2: Write tree_sitter_java_queries.py**

```python
"""tree-sitter-java query patterns and AST extraction helpers."""

import tree_sitter_java as tsjava
from tree_sitter import Language, Parser, Query


def get_java_language():
    return Language(tsjava.language())


def get_parser():
    parser = Parser()
    parser.set_language(get_java_language())
    return parser


# Query strings for extraction
CLASS_QUERY_STR = """
(class_declaration
  name: (identifier) @name
  superclass: (superclass (type_identifier) @superclass)?
  interfaces: (super_interfaces (type_list (type_identifier) @interface))?
) @class
"""

INTERFACE_QUERY_STR = """
(interface_declaration
  name: (identifier) @name
  super_interfaces: (super_interfaces (type_list (type_identifier) @super_interface))?
) @iface
"""

ENUM_QUERY_STR = """
(enum_declaration
  name: (identifier) @name
  interfaces: (super_interfaces (type_list (type_identifier) @interface))?
) @enum
"""

ANNOTATION_QUERY_STR = """
(annotation_type_declaration
  name: (identifier) @name
) @annotation
"""

METHOD_QUERY_STR = """
(method_declaration
  (modifiers)? @modifiers
  type: (_) @return_type
  name: (identifier) @name
  parameters: (formal_parameters) @params
  throws: (throws (type_identifier) @exception)?
) @method
"""

FIELD_QUERY_STR = """
(field_declaration
  (modifiers)? @modifiers
  type: (_) @type
  declarator: (variable_declarator name: (identifier) @name)
) @field
"""

CONSTRUCTOR_QUERY_STR = """
(constructor_declaration
  (modifiers)? @modifiers
  name: (identifier) @name
  parameters: (formal_parameters) @params
  throws: (throws (type_identifier) @exception)?
) @constructor
"""

IMPORT_QUERY_STR = """
(import_declaration
  (scoped_identifier) @import
)
"""

CALL_QUERY_STR = """
(method_invocation
  object: (identifier)? @object
  name: (identifier) @method_name
) @call
"""

ANNOTATION_USAGE_QUERY_STR = """
(modifiers
  (marker_annotation
    name: (identifier) @annotation_name
  )
)
"""


def parse_file(parser, filepath):
    """Parse a single .java file and return the tree-sitter tree."""
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        source = f.read()
    return parser.parse(source.encode("utf-8"))


def extract_imports(tree, source_bytes):
    """Extract import strings from parsed tree."""
    query = get_java_language().query(IMPORT_QUERY_STR)
    captures = query.captures(tree.root_node)
    imports = []
    for node, name in captures:
        if name == "import":
            imports.append(source_bytes[node.start_byte:node.end_byte].decode("utf-8"))
    return imports


def extract_class_info(tree, source_bytes):
    """Extract class/interface/enum/annotation declarations."""
    results = []
    for query_str, kind in [
        (CLASS_QUERY_STR, "class"),
        (INTERFACE_QUERY_STR, "interface"),
        (ENUM_QUERY_STR, "enum"),
        (ANNOTATION_QUERY_STR, "annotation"),
    ]:
        query = get_java_language().query(query_str)
        captures = query.captures(tree.root_node)
        captures_by_node = {}
        for node, name in captures:
            node_id = node.parent.id if name in ("superclass", "interface", "super_interface") else node.id
            captures_by_node.setdefault(node_id, {})[name] = source_bytes[node.start_byte:node.end_byte].decode("utf-8")

        for node, name in captures:
            if name in ("class", "iface", "enum", "annotation"):
                info = {"kind": kind, "line_start": node.start_point[0] + 1, "line_end": node.end_point[0] + 1}
                for cap_name, val in captures_by_node.get(node.id, {}).items():
                    info[cap_name] = val
                results.append(info)
    return results


def extract_methods(tree, source_bytes):
    """Extract method declarations with signatures."""
    results = []
    query = get_java_language().query(METHOD_QUERY_STR)
    captures = query.captures(tree.root_node)

    methods = {}
    for node, name in captures:
        if name == "method":
            methods[node.id] = {
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "modifiers": [],
                "annotations": [],
                "parameters": [],
                "exceptions": [],
            }
        elif name == "modifiers":
            mod_text = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
            parent_id = node.parent.id
            if parent_id in methods:
                methods[parent_id]["modifiers"] = [m for m in mod_text.split() if m]
                methods[parent_id]["annotations"] = [m for m in mod_text.split() if m.startswith("@")]
        elif name == "return_type":
            parent_id = node.parent.id
            if parent_id in methods:
                methods[parent_id]["return_type"] = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
        elif name == "name":
            parent_id = node.parent.id
            if parent_id in methods:
                methods[parent_id]["name"] = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
        elif name == "params":
            parent_id = node.parent.id
            if parent_id in methods:
                params_text = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
                methods[parent_id]["parameters"] = _parse_parameters(params_text)
        elif name == "exception":
            parent_id = node.parent.id
            if parent_id in methods:
                methods[parent_id]["exceptions"].append(
                    source_bytes[node.start_byte:node.end_byte].decode("utf-8")
                )

    return [m for m in methods.values() if m.get("name")]


def extract_constructors(tree, source_bytes):
    """Extract constructor declarations."""
    results = []
    query = get_java_language().query(CONSTRUCTOR_QUERY_STR)
    captures = query.captures(tree.root_node)

    ctors = {}
    for node, name in captures:
        if name == "constructor":
            ctors[node.id] = {
                "line_start": node.start_point[0] + 1,
                "modifiers": [],
                "parameters": [],
                "exceptions": [],
            }
        elif name == "modifiers":
            mod_text = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
            parent_id = node.parent.id
            if parent_id in ctors:
                ctors[parent_id]["modifiers"] = [m for m in mod_text.split() if m]
        elif name == "name":
            parent_id = node.parent.id
            if parent_id in ctors:
                ctors[parent_id]["name"] = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
        elif name == "params":
            parent_id = node.parent.id
            if parent_id in ctors:
                params_text = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
                ctors[parent_id]["parameters"] = _parse_parameters(params_text)
        elif name == "exception":
            parent_id = node.parent.id
            if parent_id in ctors:
                ctors[parent_id]["exceptions"].append(
                    source_bytes[node.start_byte:node.end_byte].decode("utf-8")
                )

    return [c for c in ctors.values() if c.get("name")]


def extract_fields(tree, source_bytes):
    """Extract field declarations with types."""
    results = []
    query = get_java_language().query(FIELD_QUERY_STR)
    captures = query.captures(tree.root_node)

    fields = {}
    for node, name in captures:
        if name == "field":
            fields[node.id] = {"modifiers": [], "annotations": []}
        elif name == "type":
            parent_id = node.parent.id
            if parent_id in fields:
                fields[parent_id]["type"] = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
        elif name == "name":
            parent_id = node.parent.id
            if parent_id in fields:
                fields[parent_id]["name"] = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
        elif name == "modifiers":
            parent_id = node.parent.id
            if parent_id in fields:
                mod_text = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
                fields[parent_id]["modifiers"] = [m for m in mod_text.split() if m]
                fields[parent_id]["annotations"] = [m for m in mod_text.split() if m.startswith("@")]

    return [f for f in fields.values() if f.get("name") and f.get("type")]


def extract_calls(tree, source_bytes):
    """Extract method invocation call sites."""
    results = []
    query = get_java_language().query(CALL_QUERY_STR)
    captures = query.captures(tree.root_node)

    for node, name in captures:
        if name == "call":
            obj = None
            method_name = None
            for child in node.children:
                if child.type == "identifier":
                    if method_name is None:
                        obj = source_bytes[child.start_byte:child.end_byte].decode("utf-8")
                    else:
                        method_name = source_bytes[child.start_byte:child.end_byte].decode("utf-8")
            if method_name is None and obj is not None:
                method_name = obj
                obj = None
            if method_name:
                results.append({
                    "object": obj,
                    "method_name": method_name,
                    "line": node.start_point[0] + 1,
                })
    return results


def _parse_parameters(params_text):
    """Parse (Type name, Type name) into list of {name, type} dicts."""
    inner = params_text.strip("()").strip()
    if not inner:
        return []
    params = []
    for param in inner.split(","):
        param = param.strip()
        if not param:
            continue
        parts = param.rsplit(None, 1)
        if len(parts) == 2:
            params.append({"type": parts[0], "name": parts[1]})
        elif len(parts) == 1:
            params.append({"type": parts[0], "name": ""})
    return params
```

Write to: `.claude/skills/jade-core-knowledge-graph/scripts/tree_sitter_java_queries.py`

- [ ] **Step 3: Quick smoke test — parse SampleA.java**

```bash
python -c "
from tree_sitter_java_queries import get_parser, parse_file, extract_class_info, extract_methods, extract_fields, extract_calls, extract_imports
parser = get_parser()
tree = parse_file(parser, 'tests/fixtures/knowledge-graph/SampleA.java')
src = open('tests/fixtures/knowledge-graph/SampleA.java', 'rb').read()
print('Classes:', extract_class_info(tree, src))
print('Methods:', extract_methods(tree, src))
print('Fields:', extract_fields(tree, src))
print('Calls:', extract_calls(tree, src))
print('Imports:', extract_imports(tree, src))
"
```

Expected: prints extracted data from SampleA without errors.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/jade-core-knowledge-graph/scripts/tree_sitter_java_queries.py
git commit -m "feat: add tree-sitter Java query helpers for KG extraction"
```

---

### Task 4: Write schema.py (KnowledgeGraph class)

**Files:**
- Create: `.claude/skills/jade-core-knowledge-graph/scripts/schema.py`

- [ ] **Step 1: Write schema.py**

```python
"""Knowledge Graph schema: dataclasses, KnowledgeGraph class, query methods."""

import json
import os
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Set
from collections import defaultdict


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
    def from_dict(d: dict) -> "GraphNode":
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

    def query_dependents(self, target: str) -> List[str]:
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

    def query_call_sites(self, target: str, method_name: str) -> List[dict]:
        """All call sites for a specific method."""
        results = []
        for e in self.edges["calls"]:
            if e.to_file == target and e.to_method == method_name:
                results.append({"file": e.from_file, "line": e.line, "caller_method": e.from_method})
        return results

    def query_rule_scope(self, flagged_files: List[str]) -> dict:
        """For a list of flagged files, compute direct + transitive scope."""
        direct = set(flagged_files)
        transitive = set()
        for ff in flagged_files:
            for dep in self.query_dependents(ff):
                transitive.add(dep)
        transitive -= direct
        return {"direct": len(direct), "transitive": len(transitive), "total": len(direct | transitive)}

    def query_consumer_coverage(self, files: List[str], consumer_file_map: Dict[str, List[str]]) -> List[str]:
        """Which consumer projects cover these files."""
        covered = set()
        for f in files:
            for consumer, consumer_files in consumer_file_map.items():
                if any(f.endswith(cf) or cf.endswith(f) for cf in consumer_files):
                    covered.add(consumer)
        return sorted(covered)

    def query_transform_order(self, rules: List[str], rule_files: Dict[str, List[str]]) -> List[str]:
        """Topologically sort rules so dependent transforms run first."""
        return rules  # Placeholder: full topological sort deferred to integration

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
    def from_dict(d: dict) -> "KnowledgeGraph":
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
    def load(filepath: str) -> "KnowledgeGraph":
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return KnowledgeGraph.from_dict(data)

    def compute_stats(self) -> dict:
        return {
            "total_files": len(self.nodes),
            "total_edges": sum(len(v) for v in self.edges.values()),
            "edge_counts": {k: len(v) for k, v in self.edges.items()},
        }
```

Write to: `.claude/skills/jade-core-knowledge-graph/scripts/schema.py`

- [ ] **Step 2: Verify schema.py loads**

```bash
python -c "from schema import KnowledgeGraph; kg = KnowledgeGraph(); print('KG created:', kg.compute_stats())"
```

Expected: `KG created: {'total_files': 0, 'total_edges': 0, 'edge_counts': {...}}`

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/jade-core-knowledge-graph/scripts/schema.py
git commit -m "feat: add KnowledgeGraph schema with dataclasses and query methods"
```

---

### Task 5: Write build_graph.py (4-stage pipeline)

**Files:**
- Create: `.claude/skills/jade-core-knowledge-graph/scripts/build_graph.py`

- [ ] **Step 1: Write build_graph.py**

```python
#!/usr/bin/env python3
"""build_graph.py — Build Knowledge Graph from Java workspace.

4-stage pipeline:
  1. SCAN: Walk workspace, collect .java paths
  2. PARSE: tree-sitter AST per file, extract declarations
  3. RESOLVE: Cross-reference imports, calls, type refs into edges
  4. SERIALIZE: Write 03.5-knowledge-graph.json

Exit codes: 0=success, 1=partial, 2=failure, 3=env-error
"""

import argparse
import os
import re
import sys
import time

from schema import (
    KnowledgeGraph, GraphNode, MethodInfo, FieldInfo,
    ConstructorInfo, Parameter,
)
from tree_sitter_java_queries import (
    get_parser, parse_file, extract_class_info, extract_methods,
    extract_fields, extract_constructors, extract_calls, extract_imports,
)


def scan_workspace(workspace_path: str) -> list:
    """Stage 1: Walk workspace, collect all .java file paths (relative to workspace)."""
    java_files = []
    for root, dirs, files in os.walk(workspace_path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.endswith(".java"):
                full = os.path.join(root, f)
                rel = os.path.relpath(full, workspace_path).replace("\\", "/")
                java_files.append((full, rel))
    return java_files


def parse_files(java_files: list, parser) -> dict:
    """Stage 2: Parse each file with tree-sitter, extract declarations."""
    nodes = {}
    parse_errors = []
    for full, rel in java_files:
        try:
            tree = parse_file(parser, full)
            with open(full, "rb") as f:
                src = f.read()

            class_infos = extract_class_info(tree, src)
            methods_raw = extract_methods(tree, src)
            fields_raw = extract_fields(tree, src)
            ctors_raw = extract_constructors(tree, src)
            calls_raw = extract_calls(tree, src)
            imports = extract_imports(tree, src)

            if not class_infos:
                parse_errors.append((rel, "no class/interface found"))
                continue

            main = class_infos[0]
            node = GraphNode(
                path=rel,
                package=_extract_package(rel),
                class_name=main.get("name", ""),
                kind=main.get("kind", "class"),
                modifiers=_extract_modifiers_from_info(main),
                extends=main.get("superclass", ""),
                implements=_filter_empty([main.get("interface", ""), main.get("super_interface", "")]),
                methods=[_build_method_info(m) for m in methods_raw],
                fields=[_build_field_info(f) for f in fields_raw],
                constructors=[_build_constructor_info(c) for c in ctors_raw],
                imports=imports,
            )
            nodes[rel] = {"node": node, "calls": calls_raw, "imports": imports,
                          "fields": fields_raw, "implements": node.implements,
                          "extends": node.extends}

        except Exception as e:
            parse_errors.append((rel, str(e)))
            nodes[rel] = {"node": _create_partial_node(rel), "calls": [], "imports": [],
                          "fields": [], "implements": [], "extends": ""}

    for rel, err in parse_errors:
        print(f"WARNING: parse issue in {rel}: {err}", file=sys.stderr)

    return nodes


def resolve_graph(nodes: dict) -> KnowledgeGraph:
    """Stage 3: Cross-reference to build edges."""
    kg = KnowledgeGraph()

    # Build import resolution maps
    rel_to_fqn = {}
    fqn_to_rel = {}
    pkg_to_rels = {}
    for rel, data in nodes.items():
        node = data["node"]
        fqn = f"jade.{rel.replace('/', '.').replace('.java', '')}" if "jade/" in rel else rel.replace("/", ".").replace(".java", "")
        rel_to_fqn[rel] = fqn
        fqn_to_rel[fqn] = rel
        pkg = node.package
        pkg_to_rels.setdefault(pkg, set()).add(rel)
        kg.add_node(node)

    # Resolve imports -> edges
    for rel, data in nodes.items():
        node = data["node"]
        for imp in node.imports:
            target_rel = _resolve_import(imp, fqn_to_rel, pkg_to_rels)
            if target_rel and target_rel != rel and target_rel in nodes:
                kg.add_import_edge(rel, target_rel)

    # Resolve extends -> edges
    for rel, data in nodes.items():
        for ext in ([data["extends"]] if isinstance(data["extends"], str) and data["extends"] else []):
            if isinstance(ext, str) and ext:
                target_rel = _resolve_type(ext, nodes, rel, fqn_to_rel, pkg_to_rels)
                if target_rel and target_rel in nodes:
                    kg.add_extends_edge(rel, target_rel)

    # Resolve implements -> edges
    for rel, data in nodes.items():
        for imp_iface in data.get("implements", []):
            if isinstance(imp_iface, str) and imp_iface:
                target_rel = _resolve_type(imp_iface, nodes, rel, fqn_to_rel, pkg_to_rels)
                if target_rel and target_rel in nodes:
                    kg.add_implements_edge(rel, target_rel)

    # Resolve type_refs from fields
    for rel, data in nodes.items():
        for fd in data.get("fields", []):
            if isinstance(fd, dict):
                ftype = fd.get("type", "")
                target_rel = _resolve_type(ftype, nodes, rel, fqn_to_rel, pkg_to_rels)
                if target_rel and target_rel in nodes:
                    kg.add_type_ref_edge(rel, target_rel, field=fd.get("name", ""), type_name=ftype)

    # Resolve calls -> edges
    for rel, data in nodes.items():
        node = data["node"]
        for call in data.get("calls", []):
            if not isinstance(call, dict):
                continue
            obj = call.get("object")
            mname = call.get("method_name")
            if not mname:
                continue
            target_rel = None
            if obj:
                target_rel = _resolve_type(obj, nodes, rel, fqn_to_rel, pkg_to_rels)
            else:
                for method in node.methods:
                    if method.name == mname:
                        target_rel = rel
                        break
            if target_rel and target_rel in nodes:
                kg.add_call_edge(rel, "", target_rel, mname, call.get("line", 0))

    return kg


def serialize_graph(kg: KnowledgeGraph, artifacts_dir: str, run_id: str):
    """Stage 4: Write 03.5-knowledge-graph.json."""
    os.makedirs(artifacts_dir, exist_ok=True)
    output_path = os.path.join(artifacts_dir, "03.5-knowledge-graph.json")

    stats = kg.compute_stats()
    output = {
        "run_id": run_id,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "stats": stats,
        **kg.to_dict(),
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Knowledge graph written: {output_path}")
    print(f"Stats: {stats}")


# --- Helpers ---

def _extract_package(rel: str) -> str:
    parts = rel.split("/")
    if len(parts) > 1:
        return ".".join(parts[:-1])
    return ""


def _extract_modifiers_from_info(info: dict) -> list:
    mods = info.get("modifiers", [])
    if isinstance(mods, str):
        return [m for m in mods.split() if m]
    return mods or []


def _filter_empty(items: list) -> list:
    return [i for i in items if i and isinstance(i, str)]


def _build_method_info(m: dict) -> MethodInfo:
    if not isinstance(m, dict):
        return MethodInfo(name="")
    params = [Parameter(**p) if isinstance(p, dict) else Parameter(name=str(p), type="") for p in m.get("parameters", [])]
    return MethodInfo(
        name=m.get("name", ""),
        modifiers=m.get("modifiers", []),
        return_type=m.get("return_type", ""),
        parameters=params,
        exceptions=m.get("exceptions", []),
        annotations=m.get("annotations", []),
        line_start=m.get("line_start", 0),
        line_end=m.get("line_end", 0),
    )


def _build_field_info(f: dict) -> FieldInfo:
    if not isinstance(f, dict):
        return FieldInfo(name="", type="")
    return FieldInfo(
        name=f.get("name", ""),
        type=f.get("type", ""),
        modifiers=f.get("modifiers", []),
        annotations=f.get("annotations", []),
    )


def _build_constructor_info(c: dict) -> ConstructorInfo:
    if not isinstance(c, dict):
        return ConstructorInfo(name="")
    params = [Parameter(**p) if isinstance(p, dict) else Parameter(name=str(p), type="") for p in c.get("parameters", [])]
    return ConstructorInfo(
        name=c.get("name", ""),
        modifiers=c.get("modifiers", []),
        parameters=params,
        exceptions=c.get("exceptions", []),
        line_start=c.get("line_start", 0),
    )


def _create_partial_node(rel: str) -> GraphNode:
    return GraphNode(
        path=rel,
        package=_extract_package(rel),
        class_name=os.path.basename(rel).replace(".java", ""),
    )


def _resolve_import(imp: str, fqn_to_rel: dict, pkg_to_rels: dict) -> str:
    """Resolve an import string to a relative file path."""
    # Wildcard import
    if imp.endswith(".*"):
        pkg = imp[:-2]
        return None  # Wildcards resolved by caller differently
    # Direct import
    if imp in fqn_to_rel:
        return fqn_to_rel[imp]
    # Try matching by short name
    short = imp.split(".")[-1]
    for fqn, rel in fqn_to_rel.items():
        if fqn.endswith(imp) or fqn.endswith("." + short):
            return rel
    return None


def _resolve_type(type_name: str, nodes: dict, from_rel: str, fqn_to_rel: dict, pkg_to_rels: dict) -> str:
    """Resolve a type name (from field, parameter, etc.) to a file path."""
    if not type_name:
        return None
    # Try FQN
    if type_name in fqn_to_rel:
        return fqn_to_rel[type_name]
    # Try same package
    from_pkg = _extract_package(from_rel)
    candidate_fqn = f"{from_pkg}.{type_name}"
    if candidate_fqn in fqn_to_rel:
        return fqn_to_rel[candidate_fqn]
    # Try short name match
    for fqn, rel in fqn_to_rel.items():
        if fqn.endswith("." + type_name) or fqn.endswith(type_name):
            return rel
    return None


def main():
    import json
    parser = argparse.ArgumentParser(description="Build Java Knowledge Graph")
    parser.add_argument("--workspace", required=True, help="Path to workspace root")
    parser.add_argument("--artifacts-dir", required=True, help="Path to artifacts directory")
    args = parser.parse_args()

    if not os.path.isdir(args.workspace):
        print(f"FATAL: workspace not found: {args.workspace}", file=sys.stderr)
        sys.exit(3)

    try:
        ts_parser = get_parser()
    except Exception as e:
        print(f"FATAL: tree-sitter init failed: {e}", file=sys.stderr)
        sys.exit(3)

    run_id = os.path.basename(os.path.dirname(args.artifacts_dir)) or "unknown"

    t0 = time.time()

    print(f"Stage 1/4: SCAN — walking workspace: {args.workspace}")
    java_files = scan_workspace(args.workspace)
    print(f"  Found {len(java_files)} .java files")

    print("Stage 2/4: PARSE — tree-sitter AST extraction")
    nodes = parse_files(java_files, ts_parser)
    print(f"  Parsed {len(nodes)} files")

    print("Stage 3/4: RESOLVE — cross-referencing edges")
    kg = resolve_graph(nodes)
    stats = kg.compute_stats()
    print(f"  Nodes: {stats['total_files']}, Edges: {stats['total_edges']}")

    print("Stage 4/4: SERIALIZE — writing artifact")
    serialize_graph(kg, args.artifacts_dir, run_id)

    elapsed = time.time() - t0
    print(f"Done in {elapsed:.1f}s")

    has_errors = stats["total_files"] < len(java_files)
    sys.exit(1 if has_errors else 0)


if __name__ == "__main__":
    main()
```

Write to: `.claude/skills/jade-core-knowledge-graph/scripts/build_graph.py`

- [ ] **Step 2: Test build_graph.py on fixtures**

```bash
python .claude/skills/jade-core-knowledge-graph/scripts/build_graph.py --workspace tests/fixtures/knowledge-graph --artifacts-dir tests/fixtures/knowledge-graph/artifacts
```

Expected: prints "Knowledge graph written" with 4 nodes and valid edge counts.

- [ ] **Step 3: Verify output JSON**

```bash
python -c "
import json
with open('tests/fixtures/knowledge-graph/artifacts/03.5-knowledge-graph.json') as f:
    d = json.load(f)
print('Nodes:', list(d['nodes'].keys()))
print('Edges import count:', len(d['edges']['imports']))
print('Edges calls count:', len(d['edges']['calls']))
"
```

Expected: 4 nodes, >0 import edges, >0 call edges.

- [ ] **Step 4: Clean up test artifacts**

```bash
Remove-Item -Recurse -Force tests/fixtures/knowledge-graph/artifacts
```

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/jade-core-knowledge-graph/scripts/build_graph.py
git commit -m "feat: add build_graph.py 4-stage Knowledge Graph builder"
```

---

### Task 6: Write query_graph.py (CLI wrapper)

**Files:**
- Create: `.claude/skills/jade-core-knowledge-graph/scripts/query_graph.py`

- [ ] **Step 1: Write query_graph.py**

```python
#!/usr/bin/env python3
"""query_graph.py — CLI query interface for Knowledge Graph artifacts.

Usage:
  python query_graph.py --graph <path> --query <type> [--target <file>] [--method <name>]

Query types: dependents, impact-chain, rule-scope, consumer-coverage, transform-order

Exit codes: 0=success, 1=no results/not found, 2=failure, 3=env-error
"""

import argparse
import json
import os
import sys

from schema import KnowledgeGraph


def cmd_dependents(kg: KnowledgeGraph, args):
    if not args.target:
        print("ERROR: --target required for dependents query", file=sys.stderr)
        sys.exit(2)
    results = kg.query_dependents(args.target)
    print(json.dumps(results, indent=2))
    sys.exit(0 if results else 1)


def cmd_impact_chain(kg: KnowledgeGraph, args):
    if not args.target:
        print("ERROR: --target required for impact-chain query", file=sys.stderr)
        sys.exit(2)
    results = kg.query_call_sites(args.target, args.method or "")
    print(json.dumps(results, indent=2))
    sys.exit(0 if results else 1)


def cmd_rule_scope(kg: KnowledgeGraph, args):
    flagged = args.files or []
    if not flagged:
        print("ERROR: --files required for rule-scope query", file=sys.stderr)
        sys.exit(2)
    results = kg.query_rule_scope(flagged)
    print(json.dumps(results, indent=2))
    sys.exit(0)


def cmd_consumer_coverage(kg: KnowledgeGraph, args):
    files = args.files or []
    if not files:
        print("ERROR: --files required for consumer-coverage query", file=sys.stderr)
        sys.exit(2)
    consumer_map = {}
    if args.consumer_map:
        with open(args.consumer_map, "r") as f:
            consumer_map = json.load(f)
    results = kg.query_consumer_coverage(files, consumer_map)
    print(json.dumps(results, indent=2))
    sys.exit(0)


def cmd_transform_order(kg: KnowledgeGraph, args):
    rules = args.rules or []
    if not rules:
        print("ERROR: --rules required for transform-order query", file=sys.stderr)
        sys.exit(2)
    rule_files = {}
    if args.rule_files_map:
        with open(args.rule_files_map, "r") as f:
            rule_files = json.load(f)
    results = kg.query_transform_order(rules, rule_files)
    print(json.dumps(results, indent=2))
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Query a Knowledge Graph artifact")
    parser.add_argument("--graph", required=True, help="Path to 03.5-knowledge-graph.json")
    parser.add_argument("--query", required=True,
                        choices=["dependents", "impact-chain", "rule-scope", "consumer-coverage", "transform-order"],
                        help="Query type")
    parser.add_argument("--target", help="Target file path (for dependents, impact-chain)")
    parser.add_argument("--method", help="Method name (for impact-chain)")
    parser.add_argument("--files", nargs="*", help="List of files (for rule-scope, consumer-coverage)")
    parser.add_argument("--rules", nargs="*", help="List of rule IDs (for transform-order)")
    parser.add_argument("--consumer-map", help="Path to consumer file map JSON")
    parser.add_argument("--rule-files-map", help="Path to rule-to-files map JSON")

    args = parser.parse_args()

    if not os.path.isfile(args.graph):
        print(f"ERROR: graph file not found: {args.graph}", file=sys.stderr)
        sys.exit(3)

    try:
        kg = KnowledgeGraph.load(args.graph)
    except Exception as e:
        print(f"ERROR: failed to load graph: {e}", file=sys.stderr)
        sys.exit(2)

    handlers = {
        "dependents": cmd_dependents,
        "impact-chain": cmd_impact_chain,
        "rule-scope": cmd_rule_scope,
        "consumer-coverage": cmd_consumer_coverage,
        "transform-order": cmd_transform_order,
    }
    handlers[args.query](kg, args)


if __name__ == "__main__":
    main()
```

Write to: `.claude/skills/jade-core-knowledge-graph/scripts/query_graph.py`

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/jade-core-knowledge-graph/scripts/query_graph.py
git commit -m "feat: add query_graph.py CLI for Knowledge Graph queries"
```

---

### Task 7: Write SKILL.md

**Files:**
- Create: `.claude/skills/jade-core-knowledge-graph/SKILL.md`

- [ ] **Step 1: Write SKILL.md**

```markdown
# jade-core-knowledge-graph

Universal Java source analyzer that builds a Knowledge Graph from `.java` files using tree-sitter-java. Produces `03.5-knowledge-graph.json` consumed by downstream pipeline phases for impact analysis, semantic verification, rule ordering, and consumer test selection.

## Invocation Contract

```
python .claude/skills/jade-core-knowledge-graph/scripts/build_graph.py --workspace <path> --artifacts-dir <path>
python .claude/skills/jade-core-knowledge-graph/scripts/query_graph.py --graph <path> --query <type> [args...]
```

Exit codes: `0`=success, `1`=partial/no-results, `2`=failure, `3`=env-error.

## Pipeline Phase

**Phase 3.5** — runs after TOOLING_SCOUT (Phase 3), before SCANNER (Phase 4). Build graph once per migration run.

## Graph Schema

- **Nodes**: One per `.java` file with class_name, package, kind, modifiers, extends, implements, methods (with full signatures), fields, constructors
- **Edges**: 5 types — `imports`, `extends`, `implements`, `calls`, `type_refs`
- External types (`java.*`, `javax.*`) recorded as edges but never recursed into

## Query Types

| Query | Args | Returns |
|-------|------|---------|
| `dependents` | `--target <file>` | Files importing/referencing target |
| `impact-chain` | `--target <file> --method <name>` | Call sites for a method |
| `rule-scope` | `--files <list>` | `{direct, transitive, total}` |
| `consumer-coverage` | `--files <list> --consumer-map <path>` | Consumer project names |
| `transform-order` | `--rules <list> --rule-files-map <path>` | Topologically sorted rules |

## Python API

```python
from schema import KnowledgeGraph
kg = KnowledgeGraph.load("artifacts/03.5-knowledge-graph.json")
deps = kg.query_dependents("core/AID.java")
calls = kg.query_call_sites("core/Agent.java", "doDelete")
```

## Edge Cases

1. **Parse errors**: File gets partial node (imports via regex fallback). Logged as warning.
2. **Wildcard imports**: Resolved to ALL files in the package (over-approximation).
3. **Overloaded methods**: Call resolution by method name only (conservative).
4. **Anonymous inner classes**: Attached to parent file, not separate nodes.
5. **Generics**: Erased. `List<Agent>` → type_ref to `Agent`.
6. **Cycles**: Graph is directed, cycles don't break queries.

## Artifact

Writes: `03.5-knowledge-graph.json` to artifacts directory.
Format: `{run_id, generated_at, stats, nodes: {path: {node}}, edges: {type: [edge]}}`.
```

Write to: `.claude/skills/jade-core-knowledge-graph/SKILL.md`

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/jade-core-knowledge-graph/SKILL.md
git commit -m "docs: add SKILL.md for jade-core-knowledge-graph"
```

---

### Task 8: Write test suite

**Files:**
- Create: `tests/test_knowledge_graph.py`

- [ ] **Step 1: Write test_knowledge_graph.py**

```python
"""Tests for jade-core-knowledge-graph skill."""

import json
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "skills", "jade-core-knowledge-graph", "scripts"))

from schema import KnowledgeGraph, GraphNode, MethodInfo, FieldInfo, Parameter
from tree_sitter_java_queries import (
    get_parser, parse_file, extract_class_info, extract_methods,
    extract_fields, extract_calls, extract_imports,
)


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


class TestTreeSitterQueries:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.parser = get_parser()

    def _parse(self, filename):
        path = os.path.join(FIXTURES_DIR, filename)
        tree = parse_file(self.parser, path)
        with open(path, "rb") as f:
            src = f.read()
        return tree, src

    def test_extract_imports(self):
        tree, src = self._parse("SampleA.java")
        imports = extract_imports(tree, src)
        assert len(imports) == 2
        assert "java.util.List" in imports
        assert "java.util.ArrayList" in imports

    def test_extract_class_info(self):
        tree, src = self._parse("SampleA.java")
        classes = extract_class_info(tree, src)
        assert len(classes) >= 1
        main = classes[0]
        assert main["name"] == "SampleA"
        assert main["kind"] == "class"
        assert "SampleB" in main.get("superclass", "")

    def test_extract_methods(self):
        tree, src = self._parse("SampleA.java")
        methods = extract_methods(tree, src)
        method_names = [m["name"] for m in methods]
        assert "process" in method_names
        assert "reset" in method_names
        assert "addItem" in method_names

    def test_extract_fields(self):
        tree, src = self._parse("SampleA.java")
        fields = extract_fields(tree, src)
        field_names = [f["name"] for f in fields]
        assert "items" in field_names

    def test_extract_calls(self):
        tree, src = self._parse("SampleA.java")
        calls = extract_calls(tree, src)
        method_names = [c["method_name"] for c in calls]
        assert "getValue" in method_names
        assert "computeLength" in method_names

    def test_extract_interface(self):
        tree, src = self._parse("SampleInterface.java")
        classes = extract_class_info(tree, src)
        assert len(classes) >= 1
        assert classes[0]["kind"] == "interface"
        assert classes[0]["name"] == "SampleInterface"

    def test_wildcard_imports(self):
        tree, src = self._parse("WildcardConsumer.java")
        imports = extract_imports(tree, src)
        assert any("tests.fixtures.knowledge_graph.*" in imp for imp in imports)


class TestBuildGraph:
    def test_build_on_fixtures(self):
        import subprocess
        result = subprocess.run(
            [
                sys.executable,
                ".claude/skills/jade-core-knowledge-graph/scripts/build_graph.py",
                "--workspace", FIXTURES_DIR,
                "--artifacts-dir", os.path.join(FIXTURES_DIR, "artifacts"),
            ],
            capture_output=True, text=True,
        )
        assert result.returncode in (0, 1)

        artifact = os.path.join(FIXTURES_DIR, "artifacts", "03.5-knowledge-graph.json")
        assert os.path.isfile(artifact)

        with open(artifact) as f:
            data = json.load(f)

        nodes = data["nodes"]
        assert len(nodes) == 4
        assert "SampleA.java" in nodes
        assert nodes["SampleA.java"]["kind"] == "class"
        assert nodes["SampleInterface.java"]["kind"] == "interface"

        edges = data["edges"]
        assert len(edges["imports"]) > 0
        assert len(edges["calls"]) > 0
        assert len(edges["implements"]) > 0

        import shutil
        art_path = os.path.join(FIXTURES_DIR, "artifacts")
        if os.path.isdir(art_path):
            shutil.rmtree(art_path)


class TestQueryGraph:
    def test_dependents_query(self):
        import subprocess
        subprocess.run(
            [
                sys.executable,
                ".claude/skills/jade-core-knowledge-graph/scripts/build_graph.py",
                "--workspace", FIXTURES_DIR,
                "--artifacts-dir", os.path.join(FIXTURES_DIR, "artifacts"),
            ],
            capture_output=True, text=True,
        )

        result = subprocess.run(
            [
                sys.executable,
                ".claude/skills/jade-core-knowledge-graph/scripts/query_graph.py",
                "--graph", os.path.join(FIXTURES_DIR, "artifacts", "03.5-knowledge-graph.json"),
                "--query", "dependents",
                "--target", "SampleB.java",
            ],
            capture_output=True, text=True,
        )
        output = result.stdout.strip()
        assert "SampleA.java" in output or "WildcardConsumer.java" in output

        import shutil
        art_path = os.path.join(FIXTURES_DIR, "artifacts")
        if os.path.isdir(art_path):
            shutil.rmtree(art_path)
```

Write to: `tests/test_knowledge_graph.py`

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_knowledge_graph.py -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_knowledge_graph.py
git commit -m "test: add test suite for knowledge-graph skill"
```

---

### Task 9: Full integration test on JADE baseline

**Files:**
- (none modified, test only)

- [ ] **Step 1: Run build_graph on JADE baseline**

```bash
python .claude/skills/jade-core-knowledge-graph/scripts/build_graph.py --workspace JADE-4.6.0/src/jade/src/jade --artifacts-dir artifacts
```

Expected: "Knowledge graph written: artifacts/03.5-knowledge-graph.json", 973 nodes.

- [ ] **Step 2: Verify key metrics**

```bash
python -c "
import json
with open('artifacts/03.5-knowledge-graph.json') as f:
    d = json.load(f)
print('Nodes:', d['stats']['total_files'])
print('Edges:', d['stats']['total_edges'])
print('Edge types:', d['stats']['edge_counts'])
# Verify known hub fan-in
import_count = sum(1 for e in d['edges']['imports'] if e['to'] == 'core/AID.java')
print('AID.java import fan-in:', import_count)
"
```

Expected: ~973 nodes, ~3000+ import edges, AID.java fan-in ~191.

- [ ] **Step 3: Query dependents**

```bash
python .claude/skills/jade-core-knowledge-graph/scripts/query_graph.py --graph artifacts/03.5-knowledge-graph.json --query dependents --target core/AID.java
```

Expected: JSON list with ~191 file paths.

- [ ] **Step 4: Clean up test artifact**

```bash
Remove-Item artifacts/03.5-knowledge-graph.json
```

- [ ] **Step 5: Commit (if needed)**

No new files — integration test is verification-only.

---

### Task 10: Register skill in pipeline

**Files:**
- Modify: `.claude/skills/jade-core-orchestrator/scripts/orchestrator.py`

- [ ] **Step 1: Add KNOWLEDGE_GRAPH_READY to TRANSITIONS table (~line 18-44)**

Insert `KNOWLEDGE_GRAPH_READY` between `BUILD_GATE_READY` and `SCAN_READY`. Change `BUILD_GATE_READY`'s OK transition from `SCAN_READY` to `KNOWLEDGE_GRAPH_READY`.

In `orchestrator.py:33-38`, replace:

```python
    "BUILD_GATE_READY": {
        "OK": "SCAN_READY",
        "ARTIFACT_MISSING": "FAILED",
        "ARTIFACT_TAMPERED": "FAILED",
        "SCRIPT_ERROR": "FAILED",
    },
```

with:

```python
    "BUILD_GATE_READY": {
        "OK": "KNOWLEDGE_GRAPH_READY",
        "ARTIFACT_MISSING": "FAILED",
        "ARTIFACT_TAMPERED": "FAILED",
        "SCRIPT_ERROR": "FAILED",
    },
    "KNOWLEDGE_GRAPH_READY": {
        "OK": "SCAN_READY",
        "DEPENDENCY_MISSING": "SCAN_READY",
        "ARTIFACT_MISSING": "FAILED",
        "ARTIFACT_TAMPERED": "FAILED",
        "SCRIPT_ERROR": "FAILED",
    },
```

Note: `DEPENDENCY_MISSING` (exit code 3, tree-sitter not installed) gracefully degrades to SCAN_READY — KG is optional, pipeline continues without it.

- [ ] **Step 2: Add required artifact for KG phase (~line 63-69)**

In the `REQUIRED_ARTIFACTS` dict, add after line 66:

```python
    "KNOWLEDGE_GRAPH_READY": ["03.5-knowledge-graph.json"],
```

- [ ] **Step 3: Add artifact content rules for 03.5-knowledge-graph.json (~line 71+)**

In `ARTIFACT_CONTENT_RULES`, add:

```python
    "03.5-knowledge-graph.json": {
        "json_keys_required": ["nodes", "edges", "stats"],
        "json_nonempty_dict": ["nodes", "edges", "stats"],
    },
```

- [ ] **Step 4: Add SCRIPT_PHASES entry for KNOWLEDGE_GRAPH_READY (~line 130-154)**

After the `BUILD_GATE_READY` block in `SCRIPT_PHASES`, insert:

```python
    "KNOWLEDGE_GRAPH_READY": {
        "script": ".claude/skills/jade-core-knowledge-graph/scripts/build_graph.py",
        "args": ["--workspace", "_WORKSPACE_", "--artifacts-dir", "_ARTIFACTS_"],
    },
```

- [ ] **Step 5: Verify transitions compile**

```bash
python -c "import importlib; importlib.import_module('orchestrator')" --workdir .claude/skills/jade-core-orchestrator/scripts
```

Expected: no SyntaxError or ImportError.

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/jade-core-orchestrator/scripts/orchestrator.py
git commit -m "feat: add Phase 3.5 KNOWLEDGE_GRAPH to orchestrator state machine"
```

---

### Task 11: Final verification

**Files:**
- (none modified, verification only)

- [ ] **Step 1: Run all tests**

```bash
pytest tests/ -v --tb=short
```

Expected: all tests pass, including new knowledge-graph tests.

- [ ] **Step 2: Run full build on JADE again to confirm idempotency**

```bash
python .claude/skills/jade-core-knowledge-graph/scripts/build_graph.py --workspace JADE-4.6.0/src/jade/src/jade --artifacts-dir artifacts
python .claude/skills/jade-core-knowledge-graph/scripts/build_graph.py --workspace JADE-4.6.0/src/jade/src/jade --artifacts-dir artifacts
```

Expected: second run produces identical output (idempotent).

- [ ] **Step 3: Clean up**

```bash
Remove-Item artifacts/03.5-knowledge-graph.json
```

- [ ] **Step 4: Commit (if any cleanup was needed)**

No commit needed if no changes.
