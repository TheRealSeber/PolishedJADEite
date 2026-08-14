# Knowledge Graph Pipeline Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the Java Knowledge Graph into migration analysis, batching, verification, consumer prioritization, and orchestrator freshness checks without allowing heuristic graph data to bypass existing safety gates.

**Architecture:** The graph remains a file-based artifact at `03.5-knowledge-graph.json`. Downstream phases consume explicit, backward-compatible advisory metadata. Direct scanner matches remain transform scope; graph-derived dependents are impact-only until separately approved. Graph quality work precedes consumers of the enriched query contract.

**Tech Stack:** Python 3, stdlib JSON/pathlib, tree-sitter-java, pytest, existing JADE artifact contracts.

---

## Worktree and Baseline

All commands below run in:

```text
C:\Users\jrsh4\ds\sem8\asa\PolishedJADEite\.worktrees\knowledge-graph-integration
```

Baseline evidence before implementation:

- `python -m pytest tests/test_knowledge_graph.py -q` -> `19 passed`.
- `python -m pytest tests/ -q` -> `60 passed, 5 skipped, 1 failed`.
- The known baseline failure is `test_transition_table_integrity`, caused by `AWAITING_AGENT -> RESUME` not being represented as a valid state.
- Do not modify unrelated dirty `migration-runs/sample/artifacts/*` files.

## File Map

| File | Responsibility in this plan |
|---|---|
| `.claude/skills/jade-core-knowledge-graph/scripts/schema.py` | Query traversal, diagnostics, provenance, deterministic serialization helpers |
| `.claude/skills/jade-core-knowledge-graph/scripts/build_graph.py` | Source identity, parse diagnostics, graph artifact generation |
| `.claude/skills/jade-core-knowledge-graph/scripts/tree_sitter_java_queries.py` | Package/type/call/type-reference extraction |
| `.claude/skills/jade-core-scanner/scripts/scan_and_tag.py` | Join flag entries with graph metadata without changing detection |
| `.claude/skills/jade-core-batch-processor/scripts/rule_batch_runner.py` | Add direct versus impact-only batch scope |
| `.claude/skills/jade-core-rule-dispatcher/scripts/dispatcher.py` | Persist graph context in fix results; recipes stay unchanged |
| `.claude/skills/jade-core-verification/scripts/semantic_verify.py` | Consume graph impact snapshots/diffs |
| `.claude/skills/jade-core-verification/scripts/runtime_verify.py` | Build consumer map and prioritize impacted consumers |
| `.claude/skills/jade-core-orchestrator/scripts/orchestrator.py` | Graph freshness and batch-boundary rebuild lifecycle |
| `tests/test_knowledge_graph.py` | Graph behavior and artifact contract tests |
| `tests/test_scanner_graph.py` | Scanner enrichment tests |
| `tests/test_batch_processor_graph.py` | Direct/impact-only batch tests |
| `tests/test_dispatcher_graph.py` | Graph context recording tests |
| `tests/test_verification_graph.py` | Graph snapshot/diff tests |
| `tests/test_runtime_verify_graph.py` | Consumer coverage prioritization tests |
| `tests/test_orchestrator_integration.py` | Graph lifecycle contract tests |

---

### Task 1: Harden Graph Contract and Queries

**Files:**
- Modify: `.claude/skills/jade-core-knowledge-graph/scripts/schema.py`
- Modify: `.claude/skills/jade-core-knowledge-graph/scripts/build_graph.py`
- Modify: `.claude/skills/jade-core-knowledge-graph/scripts/tree_sitter_java_queries.py`
- Modify: `tests/test_knowledge_graph.py`
- Add: `tests/fixtures/knowledge-graph/PackageMismatch.java`
- Add: `tests/fixtures/knowledge-graph/MultiHopA.java`
- Add: `tests/fixtures/knowledge-graph/MultiHopB.java`
- Add: `tests/fixtures/knowledge-graph/MultiHopC.java`

- [ ] **Step 1: Add failing tests for graph correctness gaps**

Add tests that assert:

```python
def test_rule_scope_reaches_multiple_hops():
    kg.add_import_edge("B.java", "A.java")
    kg.add_import_edge("C.java", "B.java")
    assert kg.query_rule_scope(["A.java"])["files"] == ["A.java", "B.java", "C.java"]

def test_dependents_include_inheritance_edges():
    kg.add_implements_edge("Impl.java", "Api.java")
    assert kg.query_dependents("Api.java") == ["Impl.java"]

def test_transform_order_reports_cycle():
    kg.add_import_edge("A.java", "B.java")
    kg.add_import_edge("B.java", "A.java")
    result = kg.query_transform_order_with_diagnostics(["ra", "rb"], {"ra": ["A.java"], "rb": ["B.java"]})
    assert result["cycles"]
```

Also test package declarations that differ from source directory names, wildcard import resolution, parse-error diagnostics, and deterministic sorted output.

- [ ] **Step 2: Run focused tests and confirm they fail**

Run:

```powershell
python -m pytest tests/test_knowledge_graph.py -q
```

Expected: the new tests fail against the current one-hop/path-based implementation.

- [ ] **Step 3: Implement versioned diagnostics and deterministic output**

Add artifact fields while preserving existing keys:

```json
{
  "schema_version": 2,
  "source": {"workspace_root": "...", "java_files": 973},
  "diagnostics": {
    "parse_failures": [],
    "unresolved_types": 0,
    "ambiguous_symbols": 0
  }
}
```

Sort file traversal, nodes, and edge lists. Detect `root.has_error` and record locations. Use atomic temporary-file replacement for graph output.

- [ ] **Step 4: Implement declaration-aware resolution and query traversal**

Use declared package/class names to build FQN maps. Resolve wildcard imports to package candidates and preserve resolution provenance. Add recursive graph traversal with a visited set. Return both counts and sorted file lists from `query_rule_scope`. Include `imports`, `extends`, `implements`, `calls`, and `type_refs` in `query_dependents`. Return cycle and ambiguity diagnostics from transform ordering while preserving the existing list-returning CLI output for compatibility.

- [ ] **Step 5: Run focused graph tests and baseline graph build**

Run:

```powershell
python -m pytest tests/test_knowledge_graph.py -q
python .claude/skills/jade-core-knowledge-graph/scripts/build_graph.py --workspace JADE-4.6.0/src/jade/src/jade --artifacts-dir $env:TEMP\opencode\kg-contract\artifacts
```

Expected: all graph tests pass, the artifact has 973 nodes, diagnostics are present, and output is deterministic across two builds.

- [ ] **Step 6: Commit**

```powershell
git add .claude/skills/jade-core-knowledge-graph tests/test_knowledge_graph.py tests/fixtures/knowledge-graph
git commit -m "feat: harden knowledge graph query contract"
```

Validation checkpoint: spec reviewer checks every schema/query requirement; quality reviewer checks resolution ambiguity, atomic writes, and backward compatibility. Any finding routes back to Task 1 Step 3.

### Task 2: Enrich Scanner Flags and Rule Batches

**Files:**
- Modify: `.claude/skills/jade-core-scanner/scripts/scan_and_tag.py`
- Modify: `.claude/skills/jade-core-batch-processor/scripts/rule_batch_runner.py`
- Modify: `.claude/skills/jade-core-batch-processor/SKILL.md`
- Add: `tests/test_scanner_graph.py`
- Add: `tests/test_batch_processor_graph.py`

- [ ] **Step 1: Add failing artifact tests**

Create a temporary graph with `A.java -> B.java`, run scanner/batch preparation, and assert:

```python
assert flag["graph"]["node_exists"] is True
assert "B.java" in flag["graph"]["impact_files"]
assert batch["files"][0]["transform_scope"] == "DIRECT"
assert batch["impact_only"][0]["file"] == "B.java"
```

Also assert missing/invalid graph data leaves original flags intact and records a warning.

- [ ] **Step 2: Implement graph loading as optional advisory input**

Load `03.5-knowledge-graph.json` from the same artifacts directory. Never fail scanner detection solely because the graph is missing or partial. Add `graph` metadata to existing flag entries and preserve all original fields.

- [ ] **Step 3: Add direct versus impact-only batch scope**

Keep `build_file_task_list()` direct-only. Add a separate sorted `impact_only` collection with graph paths and source edge types. Do not add impact-only files to recipe tasks or file counts used for transform completion.

- [ ] **Step 4: Run focused tests and artifact contract checks**

```powershell
python -m pytest tests/test_scanner_graph.py tests/test_batch_processor_graph.py -q
python -m pytest tests/test_knowledge_graph.py -q
```

Expected: original scanner/batch tests and new advisory tests pass; direct task counts are unchanged.

- [ ] **Step 5: Commit**

```powershell
git add .claude/skills/jade-core-scanner .claude/skills/jade-core-batch-processor tests/test_scanner_graph.py tests/test_batch_processor_graph.py
git commit -m "feat: add graph impact metadata to scan batches"
```

Validation checkpoint: spec reviewer verifies no impact-only file reaches a recipe; quality reviewer checks missing-graph fallback and artifact compatibility.

### Task 3: Add Queue and Dispatcher Advisory Context

**Files:**
- Modify: `.claude/skills/jade-core-rule-dispatcher/scripts/dispatcher.py`
- Modify: `.claude/skills/jade-core-orchestrator/scripts/orchestrator.py`
- Modify: `.claude/skills/jade-core-batch-processor/scripts/rule_batch_runner.py`
- Add: `tests/test_dispatcher_graph.py`
- Modify: `tests/test_orchestrator_integration.py`

- [ ] **Step 1: Add failing tests for approved-rule ordering and fix metadata**

Test that graph order is calculated only from the existing user-approved `rules` list and that an impact context is persisted without changing recipe arguments:

```python
assert queued_rules == approved_rules
assert result["graph_context"]["source_artifact"] == "03.5-knowledge-graph.json"
assert recipe_command == [sys.executable, recipe, "--file", file, "--line", str(line)]
```

- [ ] **Step 2: Add optional queue metadata**

Keep `05-rule-queue.json["rules"]` backward-compatible. Add a separate `graph_metadata` map containing suggested order, direct/impact counts, cycles, and ordering reasons. Never insert deferred/unapproved rules.

- [ ] **Step 3: Persist dispatcher graph context**

Load graph context once per dispatcher invocation, record target node, impact files, and graph artifact identity in `06-fix-results-{RULE_ID}.json`. Do not pass graph flags to recipes.

- [ ] **Step 4: Run tests and commit**

```powershell
python -m pytest tests/test_dispatcher_graph.py tests/test_orchestrator_integration.py -q
```

Expected: recipe invocation arguments remain unchanged and graph context is additive.

```powershell
git add .claude/skills/jade-core-rule-dispatcher .claude/skills/jade-core-orchestrator .claude/skills/jade-core-batch-processor tests/test_dispatcher_graph.py tests/test_orchestrator_integration.py
git commit -m "feat: add advisory graph context to rule processing"
```

Validation checkpoint: reviewers confirm user approval and sequential batching remain authoritative.

### Task 4: Add Verification Snapshots and Graph Diff

**Files:**
- Modify: `.claude/skills/jade-core-verification/scripts/semantic_verify.py`
- Modify: `.claude/skills/jade-core-verification/SKILL.md`
- Add: `.claude/skills/jade-core-verification/scripts/graph_diff.py`
- Add: `tests/test_graph_diff.py`
- Add: `tests/test_verification_graph.py`

- [ ] **Step 1: Add failing graph-diff tests**

Given before/after graph JSON, assert the diff reports added/removed nodes and edges, changed direct dependents, and source graph identities. Assert malformed or partial graphs produce an explicit warning rather than a passing semantic result.

- [ ] **Step 2: Implement `graph_diff.py`**

Expose a CLI that accepts `--before`, `--after`, and `--output`, writes atomically, and emits:

```json
{
  "graph_diff_version": 1,
  "added_edges": [],
  "removed_edges": [],
  "changed_nodes": [],
  "impact_paths": [],
  "warnings": []
}
```

- [ ] **Step 3: Integrate snapshots into verification**

Write graph impact evidence beside existing verification artifacts. Graph evidence can expand diagnostics and verification scope but cannot convert failed build/runtime gates into success.

- [ ] **Step 4: Run tests and commit**

```powershell
python -m pytest tests/test_graph_diff.py tests/test_verification_graph.py -q
git add .claude/skills/jade-core-verification tests/test_graph_diff.py tests/test_verification_graph.py
git commit -m "feat: add graph-backed verification evidence"
```

Validation checkpoint: quality reviewer checks that graph warnings never suppress semantic or runtime failures.

### Task 5: Consumer Coverage and Orchestrator Freshness

**Files:**
- Modify: `.claude/skills/jade-core-verification/scripts/runtime_verify.py`
- Modify: `.claude/skills/jade-core-orchestrator/scripts/orchestrator.py`
- Add: `tests/test_runtime_verify_graph.py`
- Modify: `tests/test_orchestrator_integration.py`

- [ ] **Step 1: Add failing consumer prioritization tests**

Create a fixture consumer map and assert impacted consumers are ordered first, while the runtime result still contains every configured consumer and `overall_pass` remains dependent on all results.

- [ ] **Step 2: Implement deterministic consumer map generation**

Scan consumer Java sources, normalize workspace-relative paths, and write an artifact-backed map. Use exact normalized path/package matches before conservative suffix matching. Record unmatched consumers.

- [ ] **Step 3: Integrate graph freshness**

Record graph schema version, source file count, and a source-content hash in run state. At batch boundaries, rebuild the graph into a new artifact atomically and update its identity. A missing graph follows the configured advisory fallback; a malformed graph fails the artifact gate.

- [ ] **Step 4: Run tests and commit**

```powershell
python -m pytest tests/test_runtime_verify_graph.py tests/test_orchestrator_integration.py -q
git add .claude/skills/jade-core-verification .claude/skills/jade-core-orchestrator tests/test_runtime_verify_graph.py tests/test_orchestrator_integration.py
git commit -m "feat: prioritize impacted consumers and track graph freshness"
```

Validation checkpoint: reviewer verifies all consumers remain mandatory and no hardcoded Docker image or JDK version is added.

### Task 6: End-to-End Validation

**Files:**
- Modify only if required by validation findings: relevant tests and artifact documentation.

- [ ] **Step 1: Run focused suites**

```powershell
python -m pytest tests/test_knowledge_graph.py tests/test_scanner_graph.py tests/test_batch_processor_graph.py tests/test_dispatcher_graph.py tests/test_graph_diff.py tests/test_verification_graph.py tests/test_runtime_verify_graph.py -q
```

- [ ] **Step 2: Run idempotency checks**

Build the graph twice from the four Java fixtures and from the JADE baseline. Compare `nodes`, `edges`, `stats`, diagnostics, and content hashes; ignore only volatile timestamps and run IDs.

- [ ] **Step 3: Run an end-to-end advisory batch fixture**

Prove that one direct flagged file produces one transform task, dependent files appear as `impact_only`, dispatcher recipe arguments are unchanged, graph diff is written, and impacted consumers are ordered first without excluding any consumer.

- [ ] **Step 4: Run the full suite**

```powershell
python -m pytest tests/ -q
```

Expected: no new failures. The known baseline `AWAITING_AGENT -> RESUME` failure must either remain unchanged and be reported, or be fixed in a separately scoped commit with its own tests.

- [ ] **Step 5: Fresh subagent validation**

Dispatch an independent read-only verifier with the worktree path and this checklist:

1. Inspect all commits and changed files.
2. Run focused and full tests.
3. Validate artifact backward compatibility and direct/impact-only separation.
4. Run baseline JADE graph build and consumer fixture.
5. Check no unrelated worktree changes were committed.

The verifier must return `READY` only with command evidence; otherwise route the failing task back to its implementer/reviewer loop.

- [ ] **Step 6: Final status**

```powershell
git status --short
git log --oneline --max-count=10
```

Do not merge or commit unrelated dirty files from `migration-runs/sample/artifacts`.
