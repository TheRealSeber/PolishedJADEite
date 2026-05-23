# PolishedJADEite

**Autonomous AI-driven pipeline for migrating the JADE multi-agent framework from Java 1.5 to modern LTS versions — with a product-first skill suite that compounds across migrations.**

---

## What This Is

A **JADE Migration Skill Suite** — 11 agnostic core pipeline skills (`jade-core-*`) plus per-migration recipe skills (`jade-recipe-*`) that migrate legacy Java codebases through sequential version jumps. The JADE 1.5→1.6 migration is the validation harness; the skill suite is the product.

The pipeline operates as a file-based state machine where artifacts on disk are the sole source of truth. Skills communicate through a shared `artifacts/` directory — no agent ever passes raw source code or large JSON in its prompt context.

**Architecture:** `docs/architecture.md` — read before modifying the pipeline.  
**Agent directives:** `AGENTS.md` — the constitution in 52 lines.

---

## Architecture (30 seconds)

| Layer | Prefix | Contains | Example |
|-------|--------|----------|---------|
| **Core** | `jade-core-*` | Agnostic pipeline plumbing | orchestrator, scanner, dispatcher, verification |
| **Recipe** | `jade-recipe-*` | Version-specific transforms | `jade-recipe-1.5-to-1.6-<rule-id>` |

**The Dispatcher Pattern:** Core skills never contain transform logic. The `jade-core-rule-dispatcher` reads a rule from the manifest, looks up the matching recipe in `recipe-registry.json`, and invokes it as a subprocess. Adding a new migration means adding recipe skills — the core pipeline never changes.

**Rule-by-Rule Sequential Batching:** One `rule_id` is applied to ALL flagged files before verification and git commit. The next rule only starts after the previous rule passes verification. Component-by-component migration is forbidden — it breaks cross-package contracts.

---

## Pipeline Phases

```
0 (optional) → 1 → 2 → 3 → 4 → 5 → 6 → 7 (batch loop) → 8 → 9
```

| Phase | Skill | What happens |
|-------|-------|-------------|
| 0\* | `codebase-analysis` | Static analysis → `JadeDocumentation/` (optional) |
| 1 | `jade-core-orchestrator` | Reads config, initializes run state |
| 2 | `jade-core-orchestrator` | Verifies workspace + build file exist |
| 3 | `jade-core-change-collector` | Strict evidence-backed manifest of breaking changes |
| 4 | `jade-core-tooling-scout` | OpenRewrite/PMD/Checkstyle dry-run discovery |
| 5 | `jade-core-build-fixer` | Updates compiler flags, verifies build compiles |
| 6 | `jade-core-scanner` | Injects `// JADE-FLAG:` markers, writes flag index |
| 7 | batch loop | **Rule-by-Rule:** prepare → dispatch to recipe → verify → commit → next rule |
| 8 | `jade-core-orchestrator` | Confirms all rules passed |
| 9 | `jade-core-evaluator` | Scores all skills, writes matrix |

\*Phase 0 is optional — pipeline never requires `JadeDocumentation/`.

---

## The Rule Batch Loop (Phase 7) in detail

For each `rule_id` in the queue:

```
7.1 jade-core-batch-processor     → 05-rule-batch-{rule_id}.json (per-file tasks)
7.2 jade-core-rule-dispatcher     → dispatches each file to recipe script
       └─ recipe script            → applies transform, returns JSON status
7.3 jade-core-verification        → compiles, semantic trace diff
7.4 jade-core-retry-router        → (if failed) requeue or escalate
7.5 jade-core-atomic-commit       → git commit only batch files, log SHA
```

Every rule gets its own git commit. History is clean and revertible per rule.

---

## Five Pillars (Hard Constraints)

1. **File-based handoff** — agents pass artifact paths, never raw source or large JSON
2. **Rule-by-Rule Sequential Batching** — one rule applied to all files before next rule
3. **Strict source evidence** — change collector halts with `AWAITING_SOURCE_INPUT` rather than fabricate rules
4. **Semantic verification** — compares normalized agent lifecycle/ACL/DF events, not raw text logs
5. **Atomic per-rule commits** — safety gate rejects unrelated dirty files

Full details: `AGENTS.md` (52 lines) and `docs/architecture.md` (448 lines).

---

## Skill Inventory

### Core (11 skills)

| Skill | Purpose |
|-------|---------|
| `jade-core-orchestrator` | State machine, phase sequencing |
| `jade-core-change-collector` | Evidence-backed manifest of breaking changes |
| `jade-core-tooling-scout` | Auto-fix discovery via OpenRewrite/PMD/Checkstyle |
| `jade-core-build-fixer` | Build system audit + compiler flag updates |
| `jade-core-scanner` | Regex flag injection + idempotent flag index |
| `jade-core-batch-processor` | Per-rule file task lists from flag index |
| `jade-core-rule-dispatcher` | Routes tasks to recipe skills via registry |
| `jade-core-verification` | Semantic trace normalization + outcome matching |
| `jade-core-atomic-commit` | Per-rule git commit with safety gate |
| `jade-core-retry-router` | Failure classification + bounded retry |
| `jade-core-evaluator` | Skill matrix scoring from run artifacts |

### Recipes (generated per-migration)

Recipe skills are produced dynamically by the Skill Creator from manifest data. The `recipe-registry.json` starts empty (`{}`) and is populated before Phase 7. Each recipe is a standalone CLI script invoked by the dispatcher: `python apply.py --file <path> --line <num>`.

---

## Repository Structure

```
PolishedJADEite/
├── AGENTS.md                         # 52-line agent constitution
├── README.md                         # This file
├── LICENSE                           # MIT
├── JADE-4.6.0/                       # Original JADE source — never modified
│   └── src/jade/
│       ├── build.xml                 # Ant build (source/target 1.5)
│       └── src/                      # Java source tree
├── .claude/skills/
│   ├── jade-core-orchestrator/       # Phase sequencing, state machine
│   ├── jade-core-change-collector/   # Evidence-backed manifest
│   ├── jade-core-tooling-scout/      # Tooling discovery
│   ├── jade-core-build-fixer/        # Build system gate
│   ├── jade-core-scanner/            # Idempotent source tagger
│   ├── jade-core-batch-processor/    # Per-rule task preparation
│   ├── jade-core-rule-dispatcher/    # Dispatcher + recipe-registry.json
│   ├── jade-core-verification/       # Semantic trace verification
│   ├── jade-core-atomic-commit/      # Per-rule git commit
│   ├── jade-core-retry-router/       # Failure retry/requeue
│   ├── jade-core-evaluator/          # Skill matrix scoring
│   ├── codebase-analysis/            # Static analysis (Phase 0)
│   ├── java-modernization/           # Generic Java modernization
│   └── java-migration-skill-registry/ # Auto-generated skill registry
├── docs/
│   ├── architecture.md               # Full pipeline constitution
│   ├── sources/
│   │   ├── migration-source-catalog.json   # Canonical source registry
│   │   ├── official-allowlist.json         # Allowed domains for evidence
│   │   ├── official-source-policy.md       # Source governance policy
│   │   ├── paths/                          # Per-migration source lists (JSON)
│   │   └── schema/                         # Catalog JSON Schema
│   └── superpowers/
│       ├── specs/                     # Design specifications
│       └── plans/                     # Implementation plans
├── JadeDocumentation/                 # Static analysis output (Phase 0, optional)
├── migration-runs/
│   ├── jade-1.5-to-1.6/               # Target migration run (clean start)
│   └── sample/                        # Harness artifacts for testing
├── tests/                            # pytest suite (29 passed, 5 skipped)
├── benchmarks/                       # Evaluation cases and benchmark scripts
├── evals/                            # Skill evaluation harness
└── report/                           # Project report
```

---

## Current State

- **Core pipeline complete** — all 11 `jade-core-*` skills built, agnostic, validated
- **Source governance enforced** — production mode restricts evidence to official allowlist only (Oracle/OpenJDK)
- **Source catalog** — structured JSON registry for 8 migration paths with per-path source lists
- **Dockerized build gates** — no host JDK or build tools required
- **LLM-as-Extractor change collector** — `write_manifest.py` enforces 12+ schema validations per rule
- **Core/Recipe split enforced** — dispatcher routes via `recipe-registry.json`
- **Phase 0 optional** — `JadeDocumentation/` enriches verification for dynamic trace scenarios
- **Test suite** — 29 passed, 5 skipped (ingestion policy, manifest gate, schema, idempotency, integration)
- **Deferred:** Recipe skills for 1.5→1.6 (generated from manifest by Skill Creator)
- **Deferred:** Full JADE 1.5→1.6 real migration execution

---

## Setup

```bash
# Required: Docker (all builds run in ephemeral containers — no host JDK needed)
docker info  # verify Docker is running

# Required: commons-codec (not included in JADE repo)
mkdir -p JADE-4.6.0/src/jade/lib/commons-codec
curl -L "https://repo1.maven.org/maven2/commons-codec/commons-codec/1.3/commons-codec-1.3.jar" \
  -o JADE-4.6.0/src/jade/lib/commons-codec/commons-codec-1.3.jar

# Run test suite
python -m pytest tests/ -v
```

---

## Team

- **Mateusz Jarosz**, Warsaw University of Technology
- **Sebastian Rydz**, Warsaw University of Technology

## License

MIT
