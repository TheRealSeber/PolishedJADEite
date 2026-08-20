# jade-core-knowledge-graph — Design Specification

**Status:** Draft
**Date:** 2026-08-05
**Version:** 1.0

## 1. Purpose

A universal, codebase-agnostic Java source analyzer that builds a Knowledge Graph (KG) from `.java` files using `tree-sitter-java`. The KG artifact is consumed by downstream pipeline phases for impact analysis, semantic verification, rule ordering, consumer test selection, and registry recipe script auto-generation.

## 2. Pipeline Integration

### New Phase: 3.5 (between TOOLING_SCOUT and SCANNER)

```
Phase 3: TOOLING_SCOUT  →  02-tooling-scout-report.json
Phase 3.5: KG            →  03.5-knowledge-graph.json   [NEW]
Phase 4: SCANNER          →  04-flag-index.json, 04-scan-summary.json
```

The KG is built once per migration run (after tooling scout, before scanner) and consumed by downstream phases:
- **RULE_BATCH_LOOP**: `rule-scope` query for precise file lists
- **RULE_DISPATCH**: `impact-chain` query before transforming hub files
- **VERIFY**: `impact-chain` post-transform semantic check
- **RUNTIME_VERIFY**: `consumer-coverage` selective test execution
- **RULE_QUEUE**: `transform-order` auto-ordering of rules

## 3. Skill Structure

```
.claude/skills/jade-core-knowledge-graph/
├── SKILL.md
└── scripts/
    ├── build_graph.py              # Main entry: parse codebase → KG artifact
    ├── query_graph.py              # CLI query interface for downstream skills
    ├── schema.py                   # Graph node/edge type definitions, KnowledgeGraph class
    └── tree_sitter_java_queries.py # tree-sitter query patterns for extraction
```

### Invocation Contract

```
python .claude/skills/jade-core-knowledge-graph/scripts/build_graph.py \
  --workspace <path> --artifacts-dir <path>

python .claude/skills/jade-core-knowledge-graph/scripts/query_graph.py \
  --graph <path> --query <type> [--target <file>] [--rule-id <id>] [--files <list>]
```

Exit codes: `0`=success, `1`=partial (some files unparseable), `2`=failure, `3`=env-error.

## 4. Graph Schema

### Node (one per .java file)

```json
{
  "path": "core/AID.java",
  "package": "jade.core",
  "class_name": "AID",
  "kind": "class",
  "modifiers": ["public"],
  "extends": "java.lang.Object",
  "implements": ["java.io.Serializable"],
  "methods": [{
    "name": "equals", "modifiers": ["public"], "return_type": "boolean",
    "parameters": [{"name": "o", "type": "Object"}],
    "exceptions": [], "annotations": ["@Override"],
    "line_start": 142, "line_end": 168
  }],
  "fields": [{
    "name": "name", "type": "String",
    "modifiers": ["private", "transient"], "annotations": []
  }],
  "constructors": [{
    "parameters": [{"name": "name", "type": "String"}], "line_start": 95
  }]
}
```

### Edge Types (5 categories)

| Type | Meaning | Enables |
|------|---------|---------|
| `imports` | A imports class/package from B | Impact analysis, rule ordering |
| `extends` | A extends B | Inheritance-aware transforms |
| `implements` | A implements interface B | Contract change detection |
| `calls` | Method in A calls method in B | Call-site verification, consumer test selection |
| `type_refs` | A references type B (field, param, return, cast) | API change impact, type compatibility |

External types (`java.lang.*`, `java.util.*`) are recorded as edges but never recursed into.

### Edge Schema

```json
"edges": {
  "imports": [
    {"from": "core/Agent.java", "to": "core/AID.java"}
  ],
  "extends": [
    {"from": "core/Agent.java", "to": "java.lang.Object"}
  ],
  "implements": [
    {"from": "core/Agent.java", "to": "jade.core.Timer"}
  ],
  "calls": [
    {"from": "core/Agent.java", "from_method": "doDelete",
     "to": "core/AID.java", "to_method": "getName", "line": 245}
  ],
  "type_refs": [
    {"from": "core/Agent.java", "to": "lang/acl/ACLMessage.java",
     "field": "msgQueue", "type": "ACLMessage"}
  ]
}
```

## 5. Query Interface

### 5 Query Types

| Query | Args | Returns | Use Case |
|-------|------|---------|----------|
| `dependents` | `--target <file>` | List of files that import/reference target | Impact analysis |
| `impact-chain` | `--target <file> --method <name>` | List of `{file, line, callee}` | Pre-transform call site listing |
| `rule-scope` | `--rule-id <id>` | `{direct, transitive, total}` | Batch processor file list |
| `consumer-coverage` | `--files <list>` | List of consumer project names | Selective test execution |
| `transform-order` | `--rules <list>` | Topologically sorted rule list | Rule queue ordering |

### Python API

```python
from schema import KnowledgeGraph
kg = KnowledgeGraph.load("artifacts/03.5-knowledge-graph.json")
aids_dependents = kg.query_dependents("core/AID.java")
call_sites = kg.query_call_sites("core/Agent.java", "doDelete")
scope = kg.query_rule_scope("LAMBDA_CONVERSION")
```

## 6. Build Process

### 4-Stage Pipeline

1. **SCAN** (stdlib): Walk workspace, collect all `.java` paths, map packages. ~0.5s.
2. **PARSE** (tree-sitter): For each file, parse AST, extract class/method/field declarations. ~5s.
3. **RESOLVE** (in-memory): Resolve import→file mappings, link type references, find call targets, connect extends/implements edges. ~1.5s.
4. **SERIALIZE** (json): Compact edges into arrays, compute stats, write `03.5-knowledge-graph.json`, validate schema. ~1s.

### Performance Budget

| Metric | Target |
|--------|--------|
| Runtime (973 files) | <10s |
| Peak memory | <100MB |
| Artifact size | <5MB |
| Parse failure rate | <1% (unparseable files logged as warnings) |

## 7. Parser Technology

**tree-sitter-java** via `pip install tree-sitter tree-sitter-java`.

Chosen over alternatives:
- **javalang**: Unmaintained, no Java 8+ support
- **javaparser (Java)**: Requires JVM subprocess, heavier integration
- **regex-only**: Insufficient accuracy for method bodies and nested structures

### tree-sitter Query Patterns

```
Class:  (class_declaration name: (identifier) @name superclass:? interfaces:?) @class
Method: (method_declaration modifiers:? type: (_) @ret name: (identifier) @name 
         parameters: (formal_parameters) @params throws:?) @method
Call:   (method_invocation object:? @obj name: (identifier) @method_name) @call
Field:  (field_declaration type: (_) @type declarator: (variable_declarator 
         name: (identifier) @name)) @field
Import: (import_declaration (scoped_identifier) @import)
```

## 8. Artifacts

### Produced

| File | Content |
|------|---------|
| `03.5-knowledge-graph.json` | Full KG: nodes, edges, stats |

### Consumed

| File | Phase | How |
|------|-------|-----|
| `workspace/` | Build | Source `.java` files to parse |

## 9. Separation from Existing Skills

This is a **core skill** — contains zero version-specific or rule-specific logic. It operates purely on the workspace source tree regardless of Java version or migration rules.

- Build is idempotent: re-running with same workspace produces identical output
- Query is stateless and read-only
- All paths are workspace-relative (matching convention)
- External dependencies (`java.*`, `javax.*`) are tracked but not resolved into the graph

## 10. Constraints & Edge Cases

1. **Files with parse errors**: Logged as warnings, file still gets a node with partial data (imports via regex fallback). Graph connectivity is preserved.
2. **Wildcard imports (`import jade.core.*`)**: Resolved by adding edges to ALL files in the package. Over-approximation is intentional — better false positive edges than missing dependencies.
3. **Overloaded method names**: Call resolution matches by method name only (not full signature). Conservative — may produce false positive call edges, but never misses real ones.
4. **Anonymous inner classes**: Extracted as synthetic nodes attached to parent file, not separate nodes.
5. **Generics**: Erased for type references. `List<Agent>` → type_ref to `Agent`. `List` itself is treated as external if `java.util.*`.
6. **Cross-package cycles**: Handled naturally — graph is directed, cycles don't break queries.

## 11. Testing Strategy

- **Unit**: Parse sample `.java` files from `tests/fixtures/` (covering all 5 edge types)
- **Integration**: Full build on JADE baseline, verify node count = 973, edge count in expected range
- **Schema**: Validate artifact against JSON Schema
- **Query**: Assert `dependents(core/AID.java)` returns 191 files

## 12. SKILL.md Requirements

The SKILL.md must describe:
- When to invoke (Phase 3.5 between tooling-scout and scanner)
- Invocation contract (same format as all core skills)
- Query guide for downstream skills
- Edge case handling (parse failures, wildcard imports)
- Artifact handoff: what it writes, where other skills read it
