# PolishedJADEite

**Autonomous agentic pipeline for migrating the JADE multi-agent framework from Java 1.5 to a modern LTS version — with self-improving skills that compound across version jumps.**

JADE (Java Agent Development Framework) is a legacy multi-agent system last updated for Java 1.5 (2004). PolishedJADEite is a research project from Warsaw University of Technology that runs a fully autonomous migration pipeline — no human-in-the-loop at execution time.

The system doesn't just migrate code. It **builds its own migration tooling** — generating, benchmarking, and improving skills from each migration failure, so subsequent modules migrate faster.

---

## The Problem

- JADE is stuck on **Java 1.5** (2004) — no generics, no enums as classes, no lambda expressions, no stream API
- Standard LLM chats fail at complex migrations because of **context loss** and **lack of execution tools**
- Human experts are a bottleneck — every module requires the same pattern of analysis, refactoring, testing
- Legacy migration isn't a one-shot task — as JADE evolves upstream, the migration must stay in sync

## The Solution

An **agentic pipeline** where Claude Code skills coordinate the migration, and a **skill-creation loop** lets the system build its own migration tooling:

```
Phase 0: Scan    → jade-phase0-scanner detects idiom patterns and severity
Phase 1: Migrate → jade-1.5-to-1.6-raw-types adds generics file-by-file
Phase 2: Migrate → jade-1.5-to-1.6-enhanced-for converts safe for-loops
Phase 3: Verify  → benchmarks/run-benchmark.sh measures delta
Phase 4: Learn   → failures feed the skill-creator (auto-generated skills)
```

**Skills** are the core innovation. Instead of human-written migration guides, the system generates its own skills from failures:

1. Migration runs → finds a failure pattern
2. Skill-Creator analyzes the failure → generates a skill that handles this pattern
3. Skill is benchmarked, versioned, and registered
4. Next module uses the improved skill instead of repeating the failure

Over time, skills **compound** — the 1.8→11 jump requires far fewer interventions than 1.5→1.6 because the system already learned from earlier iterations.

---

## Migration Strategy

### Stepping-Stone Jumps

Rather than jumping directly to Java 21, the pipeline uses incremental version checkpoints:

```
1.5 → 1.6 → 1.7 → 1.8 LTS → 11 LTS → 17 LTS → 21 LTS
```

Each jump produces a new versioned directory (`JADE-4.6.0-java1.6/`, `JADE-4.6.0-java1.7/`, etc.). The original `JADE-4.6.0/` is **never modified**.

1.6 and 1.7 can be collapsed into a single pass in practice (1.6 adds nothing syntactically, 1.7 adds only diamond operator + try-with-resources + multi-catch). The 1.8→11 jump is always its own phase — CORBA/IIOP removal, module system.

### JDK Requirements Per Jump

| Jump | JDK needed | Notes |
|------|-----------|-------|
| 1.5→1.6, 1.6→1.7 | JDK 8 | Only JDK that still supports `source/target 1.5` and `1.6` |
| 1.7→1.8 | JDK 8 | |
| 1.8→11 | JDK 11 | CORBA/IIOP removed — `FIPA/` and `jade/mtp/iiop/` must be excluded or replaced |
| 11→17, 17→21 | JDK 17 / 21 | |

JDK 8 is installed at `/usr/lib/jvm/java-8-openjdk`. All ant compile commands use `JAVA_HOME=/usr/lib/jvm/java-8-openjdk` explicitly.

---

## Skill Architecture

Skills live under `.claude/skills/` and follow the Claude Code skill format (`SKILL.md` with frontmatter). The pipeline uses three types:

**Hand-authored migration skills** — reviewed, stable, used directly:

| Skill | Purpose | When to use |
|-------|---------|-------------|
| `jade-phase0-scanner` | Scans source for Java 1.5 idiom patterns, outputs flag report | Always first |
| `jade-1.5-to-1.6-raw-types` | Adds generic type parameters to raw collections | After scanner confirms RAW_INST_FILES > 0 |
| `jade-1.5-to-1.6-enhanced-for` | Converts safe indexed for-loops to enhanced-for | After raw-types |
| `java-modernization` | Generic Java 8+ modernization (lambdas, streams) | Later jumps |
| `codebase-analysis` | Deep static analysis | Exploration |

**Auto-generated skills** (Skill-Creator output) live under:
```
.claude/skills/java-migration-skill-registry/1.5-to-1.6/
```
These are created from migration failures and benchmarked before being registered.

---

## Workflow

Each version jump follows the same six-step loop. `X` is the source version, `Y` is the target.

---

### Step 1 — SCAN

```
/jade-phase0-scanner JADE-X/src/jade/src
```

Runs grep-based idiom detection across the source tree. Produces a structured flag report:

```
FLAG                        COUNT    SEVERITY
---------------------------------------------
RAW_INST_FILES              <N>      HIGH / MEDIUM / LOW / NONE
RAW_DECL_LINES              <N>      ...
CAST_GET_LINES              <N>      ...
LEAP_ITER_FILES             <N>      INFO (never modify)
MIXED_ITER_FILES            <N>      WARN if > 0
FOR_SIZE_LOOPS              <N>      ...
FOR_LENGTH_LOOPS            <N>      ...
JVMDI_JVMPI_REFS            <N>      BLOCKER if > 0

=== Recommended Skills ===
1. jade-X-to-Y-<skill-name>   (invoke as: /jade-X-to-Y-<skill-name> JADE-X/src/jade/src)
```

Any `BLOCKER` flag must be resolved before proceeding. `INFO` flags (LEAP types) inform which files to skip — they are never touched.

---

### Step 2 — PLAN

Claude proposes the skill execution order based on the flag report and explains the dependency between skills (e.g. generics must precede enhanced-for because element types need to be known). You approve or adjust before any file is touched.

Example plan output:

```
Plan for 1.5 → 1.6:
  1. jade-1.5-to-1.6-raw-types     — RAW_INST_FILES=239, HIGH severity
  2. jade-1.5-to-1.6-enhanced-for  — FOR_SIZE_LOOPS=159, depends on (1)
  Reason: generics must be in place before enhanced-for so element types are known.
  Estimated files touched: ~280
```

---

### Step 3 — COPY

The first skill run creates the migration directory:

```bash
cp -r JADE-X/ JADE-X-javaY/
```

`JADE-X/` becomes a frozen baseline from this point. All edits target `JADE-X-javaY/` only. The Ant build in the copy has its `source`/`target` bumped from `X` to `Y`.

---

### Step 4 — APPLY

Skills run in the approved order on `JADE-X-javaY/src/jade/src`:

```
/jade-X-to-Y-raw-types     JADE-X-javaY/src/jade/src
/jade-X-to-Y-enhanced-for  JADE-X-javaY/src/jade/src
```

Each skill verifies compilation after every file it edits. If a file fails to compile, the skill fixes the error before moving on — it never leaves the tree in a broken state.

Unsafe patterns are never silently skipped — they receive a `// MIGRATION-SKIP: <reason>` comment so they are visible and auditable.

---

### Step 5 — VERIFY

```bash
./benchmarks/run-benchmark.sh JADE-X-javaY/
```

Reports:
- Unchecked warning delta (`BEFORE → AFTER`)
- Raw instantiation files remaining
- For-loop candidates remaining
- Compile result (`BUILD SUCCESSFUL` required)

A jump is considered complete when `BUILD SUCCESSFUL` and all delta counts have moved in the right direction. Runtime regression testing (JUnit) is a planned addition — currently the verification gate is compile-only.

---

### Step 6 — CAPTURE

Any failure pattern that required manual intervention during Step 4 is captured and fed back into the skill registry:

1. Failure pattern is extracted from compiler output
2. A skill is written (manually now, auto-generated later) in `.claude/skills/java-migration-skill-registry/X-to-Y/`
3. New skill is benchmarked against `benchmarks/X-to-Y/eval_cases.json`
4. Committed to the registry only if pass rate improves over the previous version

**Current state:** the registry scaffold and eval harness exist. Automated Skill-Creator generation is planned but not yet implemented — patterns are captured manually and converted into skills by hand.

This is the **compounding mechanism** — each jump produces better skills for the next one. By the time the system reaches 1.8→11, the registry already contains proven patterns from the earlier jumps.

---

## Key Constraints

### JADE LEAP Types — Never Modify

JADE's `jade.util.leap.*` package provides MIDP/J2ME-compatible collection types that mirror `java.util.*` but do not extend it. **These must never be parameterised or replaced with `java.util.*` equivalents.**

```
jade.util.leap.Iterator   jade.util.leap.List       jade.util.leap.ArrayList
jade.util.leap.Map        jade.util.leap.HashMap     jade.util.leap.Set
jade.util.leap.HashSet    jade.util.leap.LinkedList
```

Detection: `grep -n "jade\.util\.leap" <file.java>`

### No Diamond Operator in 1.6

Target is Java 1.6 — diamond operator (`<>`) requires Java 1.7. Use explicit type parameters: `new ArrayList<String>()` not `new ArrayList<>()`.

### Unsafe For-Loop Patterns

Loops that modify the collection by index (`list.remove(i)`, `list.set(i, x)`), iterate two parallel collections, or use LEAP types must not be converted. They get a `// MIGRATION-SKIP: <reason>` comment instead.

---

## KPIs

| Metric | Definition | Target |
|--------|------------|--------|
| **Regression Rate** | Core functionalities broken after migration | 0 |
| **Prompt Reduction** | Decrease in human interventions per version jump | Monotonically decreasing |
| **Skill Coverage** | % of failure patterns handled by registered skills | 100% after bootstrap |
| **Migration Velocity** | Time to migrate one module | Decreasing per skill generation |

---

## Related Work

| Paper | Relevance |
|-------|-----------|
| [From Translation to Superset](https://arxiv.org/abs/2604.11518) (Wang & Sengupta, 2026) | Benchmark-driven migration of a production Rust codebase (648K LOC) to Python using SWE-bench as objective function. Direct methodological inspiration. |
| [SWE-Adept](https://arxiv.org/abs/2603.01327) (He & Roy, 2026) | Two-agent codebase analysis with shared working memory and Git-based version control. Localization agent + resolution agent pattern maps to scanner + refactorer. |
| [FullStack-Agent](https://arxiv.org/abs/2602.03798) (Lu et al., 2026) | Multi-agent framework with self-improvement via back-translation. The FullStack-Learn self-improvement loop is the template for the Skill-Creator. |
| [From Helpful to Trustworthy](https://arxiv.org/abs/2604.10300) (Ayon, 2026) | Multi-agent pair programming with iterative validation. Accepted at FSE 2026. |

---

## Repository Structure

```
PolishedJADEite/
├── README.md
├── LICENSE                              # MIT
├── JADE-4.6.0/                          # Original JADE source — never modified
│   └── src/jade/
│       ├── build.xml                    # Ant build (source/target 1.5)
│       ├── build.properties
│       └── src/                         # Java source tree
├── JADE-4.6.0-java1.6/                  # 1.5→1.6 migrated copy (created by skills)
├── .claude/skills/
│   ├── jade-phase0-scanner/             # Scan module for idiom flags (run first)
│   ├── jade-1.5-to-1.6-raw-types/      # Add generics to raw collections
│   │   └── references/
│   │       └── jade-leap-types.md       # JADE LEAP type catalogue
│   ├── jade-1.5-to-1.6-enhanced-for/   # Convert indexed for-loops to enhanced-for
│   ├── java-migration-skill-registry/   # Auto-generated skills (Skill-Creator output)
│   │   └── 1.5-to-1.6/
│   ├── java-modernization/              # Generic Java 8+ modernization
│   └── codebase-analysis/              # Deep static analysis
├── benchmarks/
│   ├── run-benchmark.sh                 # Compare original vs migrated
│   └── 1.5-to-1.6/
│       └── eval_cases.json             # Before/after cases from real JADE code
└── deep-research-referenced-works.md   # Extended notes on related work
```

---

## Setup

```bash
# Required: JDK 8 for 1.5/1.6 compilation
sudo pacman -S jdk8-openjdk apache-ant

# Required: commons-codec (not included in JADE repo)
mkdir -p JADE-4.6.0/src/jade/lib/commons-codec
curl -L "https://repo1.maven.org/maven2/commons-codec/commons-codec/1.3/commons-codec-1.3.jar" \
  -o JADE-4.6.0/src/jade/lib/commons-codec/commons-codec-1.3.jar

# Verify baseline compiles
cd JADE-4.6.0/src/jade && JAVA_HOME=/usr/lib/jvm/java-8-openjdk ant jade 2>&1 | tail -3
```

---

## Team

- **Mateusz Jarosz**, Warsaw University of Technology
- **Sebastian Rydz**, Warsaw University of Technology

---

## License

MIT
