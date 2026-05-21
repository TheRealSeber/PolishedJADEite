---
name: jade-core-orchestrator
description: >-
  Orchestrates JADE migration runs using strict file-based handoff and deterministic state transitions.
  Use whenever running a version migration pipeline that must process rules sequentially (rule-by-rule),
  persist artifacts to disk, and enforce phase gates before continuing.
---

# JADE Migration Orchestrator

## Objective
Run the migration pipeline as a deterministic state machine using artifact file paths only.

## Core constraints
- Never pass large JSON payloads in prompt context.
- Read/write artifacts under `artifacts/`.
- Process migration in strict Rule-by-Rule Sequential Batching.
- Do not dispatch different rules in parallel.
- Stop immediately on gate failure and persist failure reason.

## Required input
- `artifacts/00-run-config.json`

## Produced/updated artifacts
- `artifacts/00-run-state.json`
- `artifacts/phase-history.log.jsonl`
- `artifacts/rule-status.json`
- `artifacts/failure-summary.json` (on failure)

## Phase order
0. PHASE_0_DOCS (optional — skipped if `JadeDocumentation/` not present in workspace)
1. INIT
2. WORKSPACE_READY
3. MANIFEST_READY
4. TOOLING_SCOUT_READY
5. BUILD_GATE_READY
6. SCAN_READY
7. RULE_BATCH_LOOP
8. VERIFIED
9. DONE (or FAILED / AWAITING_SOURCE_INPUT)

### Phase 0 (Optional): Codebase Documentation
Before INIT, the orchestrator checks for `JadeDocumentation/` in the workspace root
(produced by the `codebase-analysis` skill). If present, it reads:
- `JadeDocumentation/migration/component-order.md` — advisory, not used for rule ordering
- `JadeDocumentation/behavior/workflows.md` — passed to the verification skill for dynamic trace scenarios

If `JadeDocumentation/` does not exist, Phase 0 is skipped silently. The pipeline
never requires documentation to proceed.

### Rule application policy (IMPORTANT)
All rules are applied **system-wide, not component-by-component**. Ordering rules
by component dependency (from `component-order.md`) would break cross-package
contracts (e.g., applying generics to Component A but not Component B causes
compilation failures). The pipeline strictly follows Rule-by-Rule Sequential
Batching — each rule is applied to ALL files before verification and commit.

## Rule batch policy
For each `rule_id` in queue:
1. Run rule batch processor for that rule.
2. Run verification gate.
3. Run atomic rule commit.
4. Persist status.
5. Move to next rule.

## Halt/resume states
- `AWAITING_SOURCE_INPUT`
- `BUILD_GATE_FAILED`
- `VERIFICATION_FAILED`

Use `scripts/orchestrator.py` to execute the above behavior.
