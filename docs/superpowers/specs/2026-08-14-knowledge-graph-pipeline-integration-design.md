# Knowledge Graph Pipeline Integration

**Status:** Approved design
**Date:** 2026-08-14

 ## Goal

 Turn the existing Java Knowledge Graph artifact into a pipeline-wide advisory and verification input while preserving the migration constitution: rule-by-rule batching, user-approved modernization rules, recipe/pipeline separation, mandatory build gates, and runtime consumer verification.

 ## Scope

 The integration covers six areas:

 1. Graph artifact quality and query contracts.
 2. Scanner impact metadata.
 3. Rule-batch and queue metadata.
 4. Dispatcher context and transform-order recommendations.
 5. Pre/post transformation verification.
 6. Consumer coverage and orchestrator freshness checks.

 Graph-derived data is advisory in the first implementation. It must not silently add transform files, remove mandatory rules, skip consumers, or bypass user approval and verification gates.

 ## Architecture

 ```text
 BUILD_GATE_READY
        |
        v
 KNOWLEDGE_GRAPH_READY -> 03.5-knowledge-graph.json
        |
        v
 SCAN_READY -> 04-flag-index.json + graph impact metadata
        |
        v
 RULE_QUEUE -> graph ordering/scope metadata, user approval remains authoritative
        |
        v
 RULE_BATCH -> direct transform files + impact-only verification files
        |
        v
 DISPATCH -> recipe receives no graph responsibility
        |
        v
 VERIFY -> graph impact snapshot and post-transform graph diff
        |
        v
 RUNTIME_VERIFY -> impacted consumers first, all consumers remain mandatory
 ```

 ## Component Contracts

 ### Graph artifact

 `03.5-knowledge-graph.json` remains the file-based handoff. It will include a versioned schema, deterministic graph content, source/workspace identity, and diagnostics for parse failures, unresolved symbols, and ambiguous resolutions. Existing `nodes`, `edges`, and `stats` keys remain available.

 Every derived result must identify its source graph artifact and, where practical, include the edge path or relation that caused the result.

 ### Scanner enrichment

 `04-flag-index.json` remains authoritative for detection. Graph data may add per-flag metadata such as node existence, enclosing declaration, direct dependents, impact scope, hub score, and graph diagnostics. A graph failure or low-confidence result must produce a warning, not erase a scanner flag.

 ### Batch and queue enrichment

 `05-rule-batch-{rule_id}.json` may distinguish:

 - direct files: eligible for the recipe transform;
 - impact-only files: eligible for verification and reporting only;
 - graph paths: relationships explaining the impact.

 `05-rule-queue.json` may include graph-derived ordering and risk metadata, but the approved rule set and sequential rule processing remain authoritative.

 ### Dispatcher

 The dispatcher may load graph context and persist it in fix-result metadata. Recipes remain version-specific subprocesses and do not read the graph or implement pipeline policy.

 ### Verification

 Verification consumes graph snapshots to report affected callers, inheritance dependents, type references, and pre/post edge changes. Graph evidence supplements, never replaces, Dockerized compilation, semantic gates, or runtime consumer tests.

 ### Runtime consumers

 A generated consumer-to-JADE-file map feeds coverage queries. Impacted consumers may run first for faster feedback. The final runtime gate still requires all configured consumers to pass.

 ### Orchestrator

 The orchestrator validates the graph artifact at Phase 3.5, records graph identity/freshness, and can rebuild it after a completed rule batch. Rebuilds happen at batch boundaries, not per file. Partial or unavailable graph data follows a conservative advisory fallback unless a required artifact is structurally invalid.

 ## Safety Rules

 - Never transform an impact-only file automatically.
 - Never reorder rules that the user deferred or did not approve.
 - Never use graph output to bypass build, semantic, retry, or runtime gates.
 - Treat unresolved, ambiguous, and parse-error diagnostics as explicit uncertainty.
 - Preserve backward-compatible artifact keys and existing command contracts where possible.
 - Keep all writes atomic and workspace-relative.

 ## Validation Strategy

 Each component is validated independently and then end-to-end:

 - unit tests for graph resolution, traversal, diagnostics, and ordering;
 - artifact contract tests for every enriched artifact;
 - fixture tests covering wildcard imports, inheritance, multi-hop impact, and ambiguous symbols;
 - baseline JADE graph build and metric checks;
 - idempotency and deterministic serialization checks;
 - end-to-end rule batch test proving direct versus impact-only separation;
 - consumer coverage test proving prioritization without weakening the all-consumer gate;
 - full test suite with the known unrelated `AWAITING_AGENT -> RESUME` baseline failure recorded separately;
 - fresh independent subagent validation of the complete worktree.

 ## Delivery Boundaries

 The work is divided into sequential integration batches:

 1. Graph contract and query correctness.
 2. Scanner and batch impact metadata.
 3. Queue, dispatcher, and rule-order advisory context.
 4. Verification snapshots and graph diffs.
 5. Consumer coverage and orchestrator freshness.
 6. Full integration validation.

 A batch is accepted only after its tests and a focused review pass. Failed validation routes back to the responsible subagent for correction before the next batch starts.
