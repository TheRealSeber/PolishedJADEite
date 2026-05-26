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
- `artifacts/PROGRESS.md` — human-readable progress table, updated on every state transition

## State machine

The orchestrator is a directed graph. Each state + outcome maps to a next state.
The `TRANSITIONS` dict drives all routing:

| State | Outcome | Next state |
|-------|---------|------------|
| INIT | OK | WORKSPACE_READY |
| WORKSPACE_READY | OK | MANIFEST_READY |
| MANIFEST_READY | OK / ARTIFACT_MISSING | TOOLING_SCOUT_READY / FAILED |
| BUILD_GATE_READY | OK / ARTIFACT_MISSING | SCAN_READY / FAILED |
| SCAN_READY | OK / ARTIFACT_MISSING | RULE_BATCH_LOOP / FAILED |
| RULE_BATCH_LOOP | NEXT_RULE / NO_MORE_RULES / VERIFY_FAIL | RULE_BATCH_LOOP / VERIFIED / RULE_RETRY |
| RULE_RETRY | RETRY / ESCALATE | RULE_BATCH_LOOP / RULE_ESCALATE |
| RULE_ESCALATE | OK | RULE_BATCH_LOOP |

Terminal states: DONE, FAILED, AWAITING_SOURCE_INPUT.

On `VERIFY_FAIL`, the orchestrator invokes `retry_router.py` as a subprocess.
On `ESCALATE`, the rule is marked `ESCALATED` and skipped; the loop advances
to the next rule.

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

### Anti-Bypass Guard (IMPORTANT)

At `RULE_BATCH_LOOP`, the Agent MUST NOT manually create a batch artifact
and mark it `DONE` or `NOOP` if flagged files exist for that rule.
Acceptable resolution paths:
1. **Transform** — Write a Recipe Skill (`jade-recipe-*`) that actually applies
   the change, then dispatch it via the rule dispatcher.
2. **Defer** — Use `defer_rules.py` to rewrite `// JADE-FLAG:<rule_id>` to
   `// JADE-MODERNIZATION-DEFERRED:<rule_id> <reason>`. This preserves the
   marker as technical debt while removing it from the active pipeline.

Artifact-based bypasses (manually writing a JSON file to skip a rule) are
prohibited and constitute a pipeline integrity violation.

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
