# PolishedJADEite

**Autonomous AI-driven pipeline for migrating the JADE multi-agent framework from Java 1.5 to modern LTS versions — with a product-first skill suite that compounds across migrations.**

---

## What This Is

A **JADE Migration Skill Suite** — 11 agnostic core pipeline skills (`jade-core-*`) plus versioned recipes in the canonical Java migration registry. The JADE 1.5→1.6 migration is the validation harness; the skill suite is the product.

The pipeline operates as a file-based state machine where artifacts on disk are the sole source of truth. Skills communicate through a shared `artifacts/` directory — no agent ever passes raw source code or large JSON in its prompt context.

**Architecture:** `docs/architecture.md` — read before modifying the pipeline.  
**Agent directives:** `AGENTS.md` — the constitution in 106 lines.

---

## Architecture (30 seconds)

| Layer | Prefix | Contains | Example |
|-------|--------|----------|---------|
| **Core** | `jade-core-*` | Agnostic pipeline plumbing | orchestrator, scanner, dispatcher, verification |
| **Recipe** | `java-migration-skill-registry/<bucket>/` | Version-specific transforms | `1.5-to-1.6/arrays-copyof` |
| **Utility** | `jade-utility-*` | Pipeline support tooling | `jade-utility-consumer-onboarder` |

**The Dispatcher Pattern:** Core skills never contain transform logic. The `jade-core-rule-dispatcher` reads a rule from the manifest, looks up the matching recipe in `recipe-registry.json`, and invokes it as a subprocess. Adding a new migration means adding registry recipe scripts — the core pipeline never changes.

**Rule-by-Rule Sequential Batching:** One `rule_id` is applied to ALL flagged files before verification and git commit. The next rule only starts after the previous rule passes verification. Component-by-component migration is forbidden — it breaks cross-package contracts.

---

## Pipeline Phases

```
0 (optional) → 1 → 2 → 3 → 4 → 5 → 6 → 7 (batch loop) → 8 → RUNTIME_VERIFY → 9
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
| RUNTIME_VERIFY | `jade-core-verification` | Compiles & runs consumer projects in Docker |
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

Full details: `AGENTS.md` (106 lines) and `docs/architecture.md` (545 lines).

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
| `jade-core-rule-dispatcher` | Routes tasks to registry recipe scripts |
| `jade-core-verification` | Semantic trace normalization + outcome matching |
| `jade-core-atomic-commit` | Per-rule git commit with safety gate |
| `jade-core-retry-router` | Failure classification + bounded retry |
| `jade-core-evaluator` | Skill matrix scoring from run artifacts |

### Recipes (registry-managed)

Recipes are stored under `.claude/skills/java-migration-skill-registry/` in buckets
`1.5-to-1.6`, `1.7`, and `shared`, with directory names such as
`arrays-copyof` and `dummy`. Use `scripts/register_recipe.py` to scaffold and register a recipe. Each recipe is a
standalone CLI script invoked by the dispatcher: `python apply.py --file <path> --line <num>`.

---

## Repository Structure

```
PolishedJADEite/
├── AGENTS.md                         # 106-line agent constitution
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
│   └── java-migration-skill-registry/ # Canonical recipe registry + scaffold helper
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
├── config/
│   └── docker-images.json            # Centralized Docker image registry
├── consumer-playground/              # Runtime verification consumer projects
│   ├── hw-jade/                      # Hotel/flight booking multi-agent system
│   └── version-check/                # Minimal agent: echo version and exit
├── mock-sources/                     # Mock source documents for testing
├── tests/                            # pytest suite (41 passed, 5 skipped)
├── benchmarks/                       # Evaluation cases and benchmark scripts
├── evals/                            # Skill evaluation harness
└── report/                           # Project report
```

---

## Current State

- **Core pipeline complete** — all 11 `jade-core-*` skills built, agnostic, validated
- **1.6→1.7 migration completed** — 33 modernization changes (diamond operator, strings-in-switch)
- **1.5→1.6 migration** — rules collected, tooling scouted, flag injection in progress
- **Recipe skills exist** — `1.5-1.6-arrays-copyof`, `1.5-1.6-deque-retrofit`, `1.5-1.6-navigable-set-map`, `1.7-diamond-operator`, `1.7-strings-in-switch`, `noop`, `dummy`
- **Consumer Playground** — runtime verification against real JADE consumer projects (`hw-jade`, `version-check`)
- **Source governance enforced** — production mode restricts evidence to official allowlist only (Oracle/OpenJDK)
- **Source catalog** — structured JSON registry for 8 migration paths with per-path source lists
- **Dockerized build + runtime gates** — no host JDK or build tools required
- **LLM-as-Extractor change collector** — `write_manifest.py` enforces 12+ schema validations per rule
- **Core/Recipe split enforced** — dispatcher routes via `recipe-registry.json`
- **Phase 0 optional** — `JadeDocumentation/` enriches verification for dynamic trace scenarios
- **Test suite** — 41 passed, 5 skipped

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
