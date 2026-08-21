# JADE Skill Suite (Product-First) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible, production-grade suite of migration Skills (prompts + helper scripts + artifact contracts) where JADE 1.5->1.6 is only the validation harness.

**Architecture:** The pipeline is file-based, evidence-first, and deterministic. All state is exchanged via `artifacts/` files, never large prompt payloads. Execution is strictly Rule-by-Rule Sequential Batching: one `rule_id` across all affected files, then verification, then atomic git commit, then next rule.

**Tech Stack:** Python 3, Bash, Git, Ant/Maven/Gradle, MCP web fetcher/Context7, JSON artifact contracts.

---

## Scope and non-negotiable constraints

- Product-first: deliverable is the Skill Suite, not a one-off migration.
- No repository-wide copy: copy only `src/`, build files, `lib/`, required runtime config; exclude `docs/`, `examples/` by default.
- File-based handoff only: agents receive artifact file paths, not embedded large JSON.
- Change Collector strict mode: no inferred version diffs without evidence.
- If source fetch fails (404/timeout/paywall): halt with `AWAITING_SOURCE_INPUT` and request user local source file.
- Tooling Scout runs on modern JDK (11/17+) and analyzes legacy workspace target.
- **No File Lock Manager skill.**
- **Rule-by-Rule Sequential Batching is mandatory.**
- Atomic commit per rule after verification gate passes.
- Verification uses Semantic Log Matching (state outcomes), not raw text diff.

---

## File structure and ownership

### Skill package root (new)
- Create: `.claude/skills/jade-core-orchestrator/SKILL.md`
- Create: `.claude/skills/jade-core-orchestrator/scripts/orchestrator.py`
- Create: `.claude/skills/jade-core-orchestrator/references/schemas.md`

- Create: `.claude/skills/jade-core-change-collector/SKILL.md`
- Create: `.claude/skills/jade-core-change-collector/scripts/collect_changes.py`
- Create: `.claude/skills/jade-core-change-collector/scripts/fetch_source.py`

- Create: `.claude/skills/jade-core-tooling-scout/SKILL.md`
- Create: `.claude/skills/jade-core-tooling-scout/scripts/tooling_scout.py`

- Create: `.claude/skills/jade-core-build-fixer/SKILL.md`
- Create: `.claude/skills/jade-core-build-fixer/scripts/build_audit.py`

- Create: `.claude/skills/jade-core-scanner/SKILL.md`
- Create: `.claude/skills/jade-core-scanner/scripts/scan_and_tag.py`

- Create: `.claude/skills/jade-core-batch-processor/SKILL.md`
- Create: `.claude/skills/jade-core-batch-processor/scripts/rule_batch_runner.py`

- Create: `.claude/skills/jade-core-rule-dispatcher/SKILL.md`
- Create: `.claude/skills/jade-core-rule-dispatcher/scripts/dispatcher.py`
- Create: `.claude/skills/jade-core-rule-dispatcher/recipe-registry.json`

- Create: `.claude/skills/java-migration-skill-registry/1.5-to-1.6/raw-types/SKILL.md`
- Create: `.claude/skills/java-migration-skill-registry/1.5-to-1.6/raw-types/scripts/apply.py`

- Create: `.claude/skills/java-migration-skill-registry/1.5-to-1.6/enhanced-for/SKILL.md`
- Create: `.claude/skills/java-migration-skill-registry/1.5-to-1.6/enhanced-for/scripts/apply.py`

- Create: `.claude/skills/jade-core-verification/SKILL.md`
- Create: `.claude/skills/jade-core-verification/scripts/semantic_verify.py`
- Create: `.claude/skills/jade-core-verification/scripts/normalize_trace.py`

- Create: `.claude/skills/jade-core-atomic-commit/SKILL.md`
- Create: `.claude/skills/jade-core-atomic-commit/scripts/commit_rule.sh`
- Create: `.claude/skills/jade-core-atomic-commit/scripts/list_rule_files.py`

- Create: `.claude/skills/jade-core-retry-router/SKILL.md`
- Create: `.claude/skills/jade-core-retry-router/scripts/retry_router.py`

- Create: `.claude/skills/jade-core-evaluator/SKILL.md`
- Create: `.claude/skills/jade-core-evaluator/scripts/evaluate_skills.py`

### Validation harness (new)
- Create: `migration-runs/.gitkeep`
- Create: `benchmarks/jade-playground/README.md`
- Create: `benchmarks/jade-playground/scenarios/*.md`
- Create: `benchmarks/jade-playground/baseline-config.json`

### Plan/eval assets (new)
- Create: `evals/jade-skill-suite/evals.json`
- Create: `evals/jade-skill-suite/assertions.md`

---

## Task 1: Build artifact contracts first

**Files:**
- Create: `.claude/skills/jade-migration-orchestrator/references/schemas.md`
- Create: `benchmarks/jade-playground/baseline-config.json`

- [ ] **Step 1: Write failing schema validation test scaffold**

```python
# tests/test_artifact_contracts.py
import json

def test_run_config_has_required_keys():
    cfg = json.load(open('migration-runs/sample/artifacts/00-run-config.json'))
    assert 'run_id' in cfg and 'workspace_path' in cfg and 'artifacts_path' in cfg
```

- [ ] **Step 2: Add sample schema docs and sample artifact files**

Run: `python -m json.tool migration-runs/sample/artifacts/00-run-config.json > /dev/null`
Expected: no output, exit 0

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/jade-migration-orchestrator/references/schemas.md benchmarks/jade-playground/baseline-config.json migration-runs/sample/artifacts
git commit -m "feat(skills): add artifact contract schemas"
```

---

## Task 2: Generate `jade-migration-orchestrator` via Skill Creator

**Files:**
- Create: `.claude/skills/jade-migration-orchestrator/SKILL.md`
- Create: `.claude/skills/jade-migration-orchestrator/scripts/orchestrator.py`
- Create: `evals/jade-skill-suite/evals.json` (initial cases for orchestrator)

**In-plan Skill Creator command (copy/paste exactly):**

```text
Create a new production-grade skill named `jade-migration-orchestrator` for our JADE migration pipeline.

CONTEXT
- Product-first objective: we are building reusable Skills as the final product.
- Migration (JADE Java 1.5->1.6 etc.) is only a validation harness.
- Architecture must be strictly file-based handoff.

CRITICAL PIPELINE RULES TO ENFORCE
1) NO file-locking subsystem.
2) Rule-by-Rule Sequential Batching is mandatory:
   - Pick one rule_id
   - Apply fixes for that rule across all affected files
   - Run verification/build gate
   - Run atomic git commit for that rule
   - Only then proceed to next rule_id
3) No large JSON payloads in prompts. Agents pass only artifact file paths.
4) Strict source/evidence model is handled by other skills; this orchestrator consumes artifact paths and state.

YOUR TASK
Generate a complete skill package draft for `jade-migration-orchestrator` including:
1. SKILL.md (frontmatter + full instructions)
2. Embedded helper script `scripts/orchestrator.py`
3. Minimal schema examples for required artifacts under `references/`:
   - run-config schema
   - run-state schema
   - phase-result schema

SKILL BEHAVIOR REQUIREMENTS
The orchestrator must:
- Read `artifacts/00-run-config.json`
- Maintain `artifacts/00-run-state.json`
- Execute phases in order (path-based handoff only)
- Stop on gate failure and set deterministic state
- Support halt/resume states:
  - AWAITING_SOURCE_INPUT
  - BUILD_GATE_FAILED
  - VERIFICATION_FAILED
- Enforce Rule-by-Rule sequence by reading a precomputed rule queue artifact and iterating:
  - for each rule_id:
    - trigger rule batch processor (separate skill)
    - trigger verification
    - trigger atomic commit
    - persist per-rule status
- Never dispatch concurrent processing for different rules

REQUIRED PHASE MODEL
- INIT
- WORKSPACE_READY
- MANIFEST_READY
- TOOLING_SCOUT_READY
- BUILD_GATE_READY
- SCAN_READY
- RULE_BATCH_LOOP
- VERIFIED
- DONE / FAILED / AWAITING_SOURCE_INPUT

REQUIRED ARTIFACT PATH CONTRACTS
Input:
- artifacts/00-run-config.json
- artifacts/01-breaking-changes-manifest.json
- artifacts/02-tooling-scout-report.json (optional in early iterations)
- artifacts/03-build-audit.json
- artifacts/04-flag-index.json
- artifacts/05-rule-queue.json

Output/update:
- artifacts/00-run-state.json
- artifacts/phase-history.log.jsonl
- artifacts/rule-status.json
- artifacts/failure-summary.json (if failed)

REQUIRED scripts/orchestrator.py FUNCTIONALITY
- Validate existence of required artifact files per phase
- Persist state transitions atomically
- Append structured phase events to jsonl history
- Iterate rule queue sequentially (no parallel branch)
- Call external phase runners via command hooks (placeholder functions)
- Return non-zero exit code on hard failure
- Produce concise machine-readable fa
