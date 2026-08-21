# JADE Migration Pipeline — Architecture Constitution

> **Version:** 1.1  
> **Last updated:** 2026-05-26  
> **Status:** ACTIVE — all agents and skills MUST comply with constraints herein.

---

## 1. Product-First Philosophy

The JADE Migration Pipeline exists to produce a **robust, reproducible suite of AI
Skills** capable of migrating legacy Java codebases across major version boundaries.
Migrating JADE from 1.5 to 1.6 is the **validation harness** — not the end goal.

Every Skill in this suite must operate in LLM-hostile environments (limited context
windows, nondeterministic outputs, no persistent memory between invocations). The
pipeline is therefore designed as a **file-based state machine** where artifacts on
disk are the sole source of truth — never prompt context.

The suite targets **operators like Speckit and Claude Code** where skills are invoked
as tool-calling agents with access to a filesystem, a shell, and git. No skill stores
state in memory. No skill assumes the agent remembers anything from a prior invocation.

---

## 2. The Five Pillars of LLM-Safe Architecture

### Pillar 1 — File-Based Handoff

**Agents never pass large JSON payloads in prompt context.**

Every skill reads its inputs from artifact files on disk and writes its outputs to
artifact files on disk. Skills communicate through a shared `artifacts/` directory.
The orchestrator never dumps `04-flag-index.json` (potentially thousands of entries)
into a subagent's prompt — it passes only the file path.

Skill invocations carry:
- File paths to required input artifacts (e.g., `--artifacts-dir artifacts/`)
- A single `--rule-id` or `--task-id` string
- A workspace root path

No raw source code, no raw JSON arrays, no large payloads cross the agent boundary.

**Workspace Isolation:**

The pipeline never mutates the baseline source code. The `00-run-config.json` has
two paths:
- `baseline_path` — the pristine, read-only master source (e.g., `JADE-4.6.0`)
- `workspace_path` — an isolated sandbox copy (e.g., `migration-runs/jade-1.5-to-1.6/workspace`)

At INIT, the orchestrator copies the entire baseline tree to the workspace via
`shutil.copytree`. This preserves the complete directory structure including `lib/`,
build files, and source — ensuring all relative paths in Ant/Maven/Gradle work
correctly. Every skill reads and writes exclusively under `workspace_path`. The
baseline directory is never touched by any phase.

**Artifact numbering convention:**

| Prefix | Phase | Produced by |
|--------|-------|-------------|
| `00-` | INIT | User (config), orchestrator (state) |
| `01-` | MANIFEST | Change collector |
| `02-` | TOOLING | Tooling scout |
| `03-` | BUILD | Build system fixer |
| `04-` | SCAN | Scanner |
| `05-` | BATCH | Batch processor |
| `06-` | FIX | Rule dispatcher (per task) |
| `07-` | VERIFY | Verification (build log, semantic diff, runtime verify) |
| `08-` | RETRY | Retry router |
| `09-` | COMMIT | Atomic commit |
| `10-` | EVAL | Skill matrix evaluator |

### Pillar 2 — Rule-by-Rule Sequential Batching

**We apply ONE rule to ALL files before touching the next rule.**

The temptation to migrate "component by component" (fix `jade.core`, then `jade.lang`,
then `jade.content`) is a trap. If we apply generics to `jade.core.Agent` but not to
`jade.lang.ServiceDescription`, cross-package contracts break immediately — the codebase
will not compile. Verification becomes impossible until the next batch, and the next
batch may depend on a contract that no longer exists.

**The Rule-by-Rule approach instead:**
1. Select one `rule_id` from the rule queue (e.g., `LOOP_MODERNIZATION`)
2. Apply that rule to **every flagged file** in the entire workspace
3. Verify the full build compiles and passes semantic checks
4. Atomic git commit for that rule
5. Select the next `rule_id` (`GENERICS_UPGRADE`)
6. Repeat

This guarantees that every intermediate state is compilable and verifiable. No broken
contracts. No race conditions between agents.

**Parallel execution is forbidden within a rule batch.** The orchestrator operates
as a transition-table state machine. Different rules are never processed concurrently.

On verification failure, the orchestrator routes through the retry router. If a
rule's retry budget is exhausted, it is escalated (marked `ESCALATED_TO_LLM` in
`rule-status.json`) and the pipeline continues to the next rule — never blocking
the entire run for one problematic rule. An `ACTION_REQUIRED.md` ledger details
every escalated file with failure reasons.

### Pillar 3 — Strict Source Evidence (Anti-Hallucination)

**The Change Collector cannot invent rules.**

The change collector uses **LLM reading comprehension, not regex** to extract rules
from source documents. The agent reads clean text from `artifacts/01-source-content-*.txt`
(fetched and HTML-stripped by `fetch_source.py`). It extracts rules by understanding
the text, NOT by matching patterns — eliminating the fragility of regex extraction.

Every extracted rule is validated by `write_manifest.py` before being accepted.
The validator enforces 12 schema checks:

Every entry in `01-breaking-changes-manifest.json` MUST cite a specific source with:
- `evidence_ref` — source label, section anchor, and line range (from text the agent read)
- `evidence_hash` — SHA-256 of the source text (from `01-source-index.json`)
- `confidence` — never below 0.7

`write_manifest.py` additionally validates:
- `fix_strategy` starts with `"recipe:"`
- `match_pattern` compiles as valid regex
- No duplicate `rule_id` values
- `severity` and `category` are valid enum values
- Every rule has at least one pattern

**Hard constraints:**
- Confidence `1.0` is reserved for official Oracle/OpenJDK release notes or JEP documents
- Community sources (Stack Overflow, blog posts) cap at `0.85`
- When two sources disagree, the higher-quality source wins; the conflict is recorded
- If ALL sources fail (404, timeout, paywall), the collector sets `AWAITING_SOURCE_INPUT`
  and halts — it NEVER proceeds with LLM-priors
- A `match_pattern` or `fix_strategy` may not be fabricated; ambiguous changes go into
  `rejected_candidates`, not promoted to rules
- **The agent writes extracted rules to a temp file; `write_manifest.py` validates and
  atomically writes the manifest. The agent never directly writes the manifest.**

This prevents the most common failure mode in LLM-assisted migration: an agent
confidently applying a "known" Java 1.5→1.6 change that was never actually a
breaking change.

### Pillar 4 — Semantic Verification

**Text-diffing logs fails in concurrent, nondeterministic systems.**

JADE is a distributed agent platform. Logs contain:
- Timestamps (will differ between runs)
- Thread IDs (scheduling is nondeterministic)
- Platform addresses (`@192.168.1.5:1099/JADE`)
- Agent container names

A raw `diff baseline.log migrated.log` will always show differences even when the
system is behaviorally identical.

**Instead, we verify semantic state outcomes:**

| Layer | What we compare | Example |
|-------|----------------|---------|
| Lifecycle | Agent birth/death/migration events | `AGENT_STARTED buyer`, `AGENT_TERMINATED seller` |
| ACL Protocol | Message exchanges by performative and conversation-id | `ACL_SEND buyer→seller CFP [conv-42]` |
| DF/AMS | Service registration and discovery outcomes | `DF_REGISTER seller EnglishAuctionService` |

The normalizer strips timestamps, thread IDs, hex nonces, memory addresses, and
platform addresses before comparison. The tolerance config allows relaxing strict
ordering for genuinely nondeterministic event sequences.

**Phase 0 enrichment (optional):** If `JadeDocumentation/behavior/workflows.md`
exists (produced by `codebase-analysis`), the verification skill dynamically
generates required event sequences from documented business workflows. A workflow
documenting "ContractNet protocol (initiate → propose → accept → confirm)" becomes
a required assertion that all four event types appear in the migrated trace with
matching conversation IDs.

### Pillar 5 — Atomic Commits

**One git commit per verified rule. Never squash across rules.**

After a rule passes verification, `jade-core-atomic-commit`:
1. Stages **only** files listed in the batch artifact (never `git add -A`)
2. Runs a safety gate: if any dirty/staged files are NOT in the batch artifact, abort
3. Commits with strict format: `fix(migration): resolved {rule_id} - {short_description}`
4. Logs the commit SHA to `artifacts/09-rule-commit-log.json`

The orchestrator confirms the commit log exists before advancing to the next rule.
This ensures:
- **Clean history** — `git bisect` can pinpoint which rule introduced a regression
- **Revertibility** — `git revert <commit>` undoes one rule without touching others
- **Auditability** — every rule's impact is isolated to one commit

---

## 3. Core vs. Recipe (Plugin) Taxonomy

### Core Skills (`jade-core-*`)

Core skills are **100% agnostic to the migration version**. They contain zero
Java-version-specific logic, zero regex patterns for specific rules, and zero
knowledge of what any specific rule ID means. They are the pipeline's
plumbing.

| # | Skill | Responsibility |
|---|-------|---------------|
| 1 | `jade-core-orchestrator` | State machine, phase sequencing, rule queue iteration |
| 2 | `jade-core-change-collector` | Strict evidence-backed manifest generation |
| 3 | `jade-core-tooling-scout` | OpenRewrite/PMD/Checkstyle dry-run discovery |
| 4 | `jade-core-build-fixer` | Build system audit + Dockerized compilation |
| 5 | `jade-core-scanner` | Regex tag injection + idempotent flag index |
| 6 | `jade-core-batch-processor` | Per-rule file task list from flag index |
| 7 | `jade-core-rule-dispatcher` | Routes tasks to registry recipes via `recipe-registry.json` |
| 8 | `jade-core-verification` | Semantic trace normalization + outcome matching |
| 9 | `jade-core-atomic-commit` | Per-rule git commit with safety gate |
| 10 | `jade-core-retry-router` | Failure classification + bounded retry/requeue |
| 11 | `jade-core-evaluator` | Skill matrix scoring from run artifacts |

### Utility Skills (`jade-utility-*`)

Utility skills support the pipeline but are not part of the core state machine.

| # | Skill | Responsibility |
|---|-------|---------------|
| 1 | `jade-utility-consumer-onboarder` | ZIP extraction + test-config.json generation for consumer playground |

### Recipe Scripts (`jade-recipe-*`)

Recipes are **version-specific transform scripts** (plus docs) generated dynamically
per-migration. They contain pure Java editing logic — no artifact I/O, no JSON
parsing, no understanding of the pipeline. They are invoked as subprocesses by
the dispatcher.

> **Recipes are not agent skills.** They live under
> `.claude/skills/java-migration-skill-registry/<version-jump>/<recipe>/` — two levels
> below `.claude/skills/`, so they fall outside OpenCode's `skills/*/SKILL.md`
> discovery pattern and never enter the agent skill inventory. Each recipe keeps a
> `SKILL.md` purely as human/agent-fallback documentation; the dispatcher only ever
> reads the `script` path from `recipe-registry.json` and runs `apply.py`.

A recipe:
- Accepts `--file <path> --line <num>` via CLI
- Reads the target file, applies its transform, writes atomically
- Prints a single JSON line to stdout: `{"status": "FIXED|FAILED|SKIPPED|DEFERRED", "changes": N, "warnings": [], "errors": [], "diff_summary": "..."}`
- Exits 0 on success, non-zero on failure

Examples (for a hypothetical 1.5→1.6 migration):
- `jade-recipe-1.5-1.6-generics` — registry recipe script that infers generics from `.add()`/`.put()` calls
- `jade-recipe-1.5-1.6-loops` — registry recipe script that converts safe indexed loops to for-each

### The Dispatcher Pattern

```
Rule ID "EXAMPLE_RULE" arrives at jade-core-rule-dispatcher
    │
    ├─► LOAD task from 05-rule-batch-EXAMPLE_RULE.json
    ├─► LOAD rule from 01-breaking-changes-manifest.json
│       fix_strategy = "recipe:jade-recipe-1.5-1.6-example-rule"
├─► LOOKUP recipe-registry.json:
│       "EXAMPLE_RULE" → ".claude/skills/java-migration-skill-registry/1.5-to-1.6/jade-recipe-1.5-1.6-example-rule/scripts/apply.py"
    ├─► DISPATCH subprocess:
    │       python apply.py --file workspace/src/Example.java --line 42
    ├─► CAPTURE recipe stdout → {"status": "FIXED", ...}
    └─► RECORD → 06-fix-result-EXAMPLE_RULE-0001.json
```

The dispatcher contains **zero transform logic**. It never compiles a regex against
Java source. Adding a new migration (e.g., Java 8→11) means adding new recipe scripts
under the registry and updating `recipe-registry.json` — the core pipeline never changes.

### Recipe Registry

`jade-core-rule-dispatcher/recipe-registry.json` maps `rule_id` to a registry recipe script:

```json
{
  "EXAMPLE_RULE": {
    "skill": "jade-recipe-1.5-1.6-example",
    "script": ".claude/skills/java-migration-skill-registry/1.5-to-1.6/jade-recipe-1.5-1.6-example/scripts/apply.py",
    "description": "Apply a migration transform"
  }
}
```

Recipes are created and registered by
`.claude/skills/java-migration-skill-registry/scripts/register_recipe.py`. The helper
creates recipe files, validates safe path segments, and atomically updates the
registry. The registry is populated before the RULE_BATCH_LOOP phase.

### Consumer Playground & Runtime Verification

After all rules pass verification, a **RUNTIME_VERIFY** phase boots the migrated
JADE in Docker against consumer projects from `consumer-playground/`.

```
RULE_BATCH_LOOP → VERIFIED → RUNTIME_VERIFY → DONE
                              ↘ VERIFY_FAIL → FAILED
```

Each consumer project contains:
- JADE agent `.java` source files (preserved in package structure)
- `test-config.json` — Docker image, boot args, expected stdout markers, classpath deps

The `runtime_verify.py` script (in `jade-core-verification`) performs:
1. Discovers consumer projects from `consumer-playground/`
2. Compiles each against the migrated workspace's `jade.jar`
3. Runs in an isolated Docker container
4. **Reverse assertion** — scans output for `Exception`/`NullPointerException`/`SEVERE:` patterns
5. Validates all `expected_stdout_markers` are present
6. Treats container timeout as FAIL
7. Expects graceful shutdown (via `TestRunnerAgent` pattern or `System.exit(0)`)

The `jade-utility-consumer-onboarder` skill automates ingestion of new consumer
projects from ZIP archives, generating the directory structure and boilerplate
`test-config.json`.

**TestRunnerAgent pattern:** When consumer agents require constructor arguments
(which `jade.Boot -agents` cannot pass), create a `TestRunnerAgent.java` that
programmatically creates mock data and starts agents via `getContainerController()`.
This agent also handles graceful shutdown via `System.exit(0)`. See
`consumer-playground/hw-jade/TestRunnerAgent.java` for a reference implementation.

---

## 4. Pipeline Phase Flow

```
┌──────────────────────────────────────────────────────────────────────┐
│                     JADE Migration Pipeline                           │
│                     jade-core-orchestrator                            │
└──────────────────────────────────────────────────────────────────────┘

PHASE 0 (optional)           PHASE 1                 PHASE 2
┌─────────────────┐         ┌──────────┐           ┌────────────────┐
│ codebase-analysis│         │  INIT    │           │ WORKSPACE_READY│
│                  │         │          │           │                │
│ Produces:        │         │ Reads:   │           │ Checks:        │
│ JadeDocumentation│ ──►     │ 00-run-  │ ──►       │ workspace path │
│ ├─ behavior/     │         │ config   │           │ build file     │
│ ├─ migration/    │         │          │           │ exists         │
│ └─ reference/    │         │ Writes:  │           │                │
└─────────────────┘         │ 00-run-  │           └───────┬────────┘
  (skipped if absent)       │ state    │                   │
                            └────┬─────┘                   │
                                 │                          │
                    PHASE 3      │         PHASE 4          │
              ┌─────────────────┴──────────────────────────┐│
              │              MANIFEST_READY          │      │
              │                                      │      │
              │ jade-core-change-collector           │      │
              │                                      │      │
              │ Reads: 00-run-config                 │      │
              │        user source list              │      │
              │                                      │      │
              │ Writes: 01-source-index              │      │
              │         01-breaking-changes-manifest  │      │
              │         01-evidence-map              │      │
              │                                      │      │
              │ Gate: ALL sources fail →             │      │
              │       AWAITING_SOURCE_INPUT halt     │      │
              └────────────────┬─────────────────────┘      │
                               │                            │
                    PHASE 4    │                            │
              ┌────────────────┴────────────────────────────┘
              │          TOOLING_SCOUT_READY
              │
              │ jade-core-tooling-scout
              │
              │ Reads: 00-run-config
              │        01-breaking-changes-manifest
              │
              │ Writes: 02-tooling-scout-report
              │         02-linter-findings
              │         Merges into 01-manifest
              │
              │ (never fails — tools absent = OK)
              └────────────────┬─────────────────────┐
                               │                     │
                    PHASE 5    │                     │
              ┌────────────────┴──────────┐          │
              │      BUILD_GATE_READY     │          │
              │                           │          │
              │ jade-core-build-fixer     │          │
              │                           │          │
              │ Reads: 00-run-config      │          │
              │        build.xml/pom.xml  │          │
              │                           │          │
              │ Writes: 03-build-audit    │          │
              │         03-fixes-plan     │          │
              │         03-build-verify   │          │
              │                           │          │
              │ Gate: FAILED → halt       │          │
              │       OK → SCAN_READY     │          │
              └────────────────┬──────────┘          │
                               │                     │
                    PHASE 6    │                     │
              ┌────────────────┴─────────────────────┘
              │              SCAN_READY
              │
              │ jade-core-scanner
              │
              │ Reads: 01-breaking-changes-manifest
              │        workspace/**/*.java
              │
              │ Writes: 04-flag-index
              │         04-scan-summary
              │         Injects // JADE-FLAG: in source
              │
              │ Idempotent: re-run → 0 new flags
              └────────────────┬─────────────────────┐
                               │                     │
                               │     ╔═══════════════╧═══════════════╗
                               │     ║     RULE_BATCH_LOOP (core)     ║
                               │     ║                               ║
                               │     ║  For each rule_id in queue:   ║
                               │     ║                               ║
                               │     ║  ┌─────────────────────────┐  ║
                    PHASE 7 ───╫──► ║  │ 7.1 BATCH PREPARE       │  ║
                               │     ║  │ jade-core-batch-        │  ║
                               │     ║  │ processor               │  ║
                               │     ║  │                         │  ║
                               │     ║  │ → 05-rule-batch-{id}   │  ║
                               │     ║  └───────────┬─────────────┘  ║
                               │     ║              │                ║
                               │     ║  ┌───────────┴─────────────┐  ║
                               │     ║  │ 7.2 FILE-BY-FILE FIX    │  ║
                               │     ║  │ jade-core-rule-         │  ║
                               │     ║  │ dispatcher              │  ║
                               │     ║  │       │                 │  ║
                                │     ║  │       └─► registry recipe │  ║
                               │     ║  │                         │  ║
                               │     ║  │ → 06-fix-result-{id}   │  ║
                               │     ║  └───────────┬─────────────┘  ║
                               │     ║              │                ║
                               │     ║  ┌───────────┴─────────────┐  ║
                               │     ║  │ 7.3 VERIFY              │  ║
                               │     ║  │ jade-core-verification  │  ║
                               │     ║  │                         │  ║
                               │     ║  │ → 07-build.log          │  ║
                               │     ║  │ → 07-semantic-diff      │  ║
                               │     ║  └──────┬──────────┬───────┘  ║
                               │     ║         │          │          ║
                               │     ║    PASS │     FAIL │          ║
                               │     ║         │          │          ║
                               │     ║  ┌──────┴──┐ ┌─────┴──────┐  ║
                               │     ║  │ 7.5     │ │ 7.4 RETRY  │  ║
                               │     ║  │ COMMIT  │ │ jade-core- │  ║
                               │     ║  │         │ │ retry-     │  ║
                               │     ║  │ → 09-   │ │ router     │  ║
                               │     ║  │ commit- │ │            │  ║
                               │     ║  │ log     │ │ → requeue  │  ║
                               │     ║  │         │ │ or escalate│  ║
                               │     ║  └────┬────┘ └────────────┘  ║
                               │     ║       │                      ║
                               │     ║       └─► advance to         ║
                               │     ║           next rule_id       ║
                               │     ╚═══════════════════════════════╝
                               │                     │
                               │     All rules DONE   │
                               │                     │
                     PHASE 8    │                     │
               ┌────────────────┴─────────────────────┘
               │              VERIFIED
               │
               │ jade-core-orchestrator
               │
               │ Confirms: all rule-status = DONE
               │           all commits logged
               └────────────────┬─────────────────────┐
                                │                     │
                     PHASE 8b   │                     │
               ┌────────────────┴──────────┐          │
               │      RUNTIME_VERIFY       │          │
               │                           │          │
               │ jade-core-verification    │          │
               │ (runtime_verify.py)       │          │
               │                           │          │
               │ Tests consumer projects   │          │
               │ in consumer-playground/   │          │
               │                           │          │
               │ Writes: 07-runtime-       │          │
               │         verify.json       │          │
               │                           │          │
               │ Gate: VERIFY_FAIL → halt  │          │
               │       OK → DONE           │          │
               └────────────────┬──────────┘          │
                                │                     │
                     PHASE 9    │                     │
               ┌────────────────┴─────────────────────┘
                 │              DONE
                │
                │ jade-core-evaluator
                │
                │ Reads: all artifacts
                │
                │ Writes: 10-skill-matrix
                │
                │ Scores all core skills
                │ on completeness,
                │ reproducibility,
                │ gate pass rate
                └───────────────────────────┐
                                                     │
      ┌──────────────────────────────────────────────┘
      │
      │   HALT STATES (reachable from any phase)
      │
      ├── AWAITING_SOURCE_INPUT   — no evidence sources survived
      ├── BUILD_GATE_FAILED       — build cannot compile at target version
      ├── VERIFICATION_FAILED     — semantic outcomes diverge
      └── COMMIT_SAFETY_GATE_FAILED — unrelated dirty files in working tree
```

---

## 5. Invocation Contract

Every skill in the suite adheres to a common invocation contract:

```
python .claude/skills/<skill-name>/scripts/<script>.py \
  --artifacts-dir artifacts/ \
  --rule-id <rule_id>           # (where applicable)
  --task-id <task_id>           # (where applicable)
```

**Exit codes:**
- `0` — success (fix applied, gate passed, phase completed)
- `1` — informational (run complete but attention needed)
- `2` — failure (invalid input, missing artifact, unrecoverable error)
- `3` — environment failure (missing Docker, missing JDK, tool not found)

**Build gates use Docker:** The `jade-core-build-fixer` and `jade-core-verification`
skills compile code in ephemeral Docker containers (`frekele/ant:1.10.3-jdk8`).
No host JDK or Ant installation is required.

**Atomic writes:** All artifact writes use tmp-file + atomic rename. No partial files
on disk. If the process is killed mid-write, the artifact either doesn't exist or is
complete — never truncated.

**Idempotency:** Where feasible, skills are idempotent. The scanner can be re-run
and produces zero new flags. The build fixer produces the same plan on re-run.

---

## 6. Hard Constraints (Non-Negotiable)

1. **Never pass raw source code or large JSON arrays in an agent prompt.** Pass file
   paths only.
2. **Never skip a verification gate.** If verification fails, halt — do not proceed
   to the next rule.
3. **Never apply rules in parallel.** Rule-by-Rule Sequential Batching is mandatory.
4. **Never commit without the safety gate.** Unrelated dirty files block the commit.
5. **Never fabricate evidence.** The change collector halts rather than guess.
6. **Never mix Core and Recipe logic.** Core skills contain zero version-specific
   transforms. Recipe skills contain zero pipeline logic.
7. **Never squash rule commits.** One commit per verified rule.
8. **Never assume `JadeDocumentation/` exists.** Phase 0 is optional.
9. **Never mutate baseline source.** The orchestrator copies `baseline_path` →
   `workspace_path` at INIT. All skills operate on the copy. `JADE-4.6.0/` is
   read-only.
10. **Never fake artifacts.** Every `artifacts/` file must be produced by the
    Phase-appropriate script. Manually writing a file that "looks like" a pipeline
    output to bypass a gate is forbidden.
11. **Never exclude existing source.** The workspace MUST be a faithful copy of the
    baseline. Adding exclusion patterns to build files to force compilation on an
    incompatible JDK is forbidden.
12. **Container agnosticism.** Never hardcode JDK versions or Docker images in consumer
    test configs, recipes, or core scripts. Resolve container images from the central
    registry (`config/docker-images.json`).
13. **Java 11+ readiness.** Every migration targeting Java 11 or newer MUST run
    dependency compatibility auditing for removed JDK modules/libraries (including
    CORBA/JAXB families) during BUILD_GATE_READY.
14. **Interactive modernization decision.** At `RULE_BATCH_LOOP`, the Agent MUST
    ask the user which modernization rules to apply vs defer. Deferred rules persist
    as `// JADE-MODERNIZATION-DEFERRED:<rule_id>` markers.
15. **Zero-trust verification.** Building successfully in Docker (exit code 0,
    `BUILD SUCCESSFUL` in log) and `PASS` in all runtime consumer tests are the ONLY
    acceptable proof of correctness. Evidence before assertions, always.
