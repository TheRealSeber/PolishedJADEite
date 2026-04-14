# PolishedJADEite

**Autonomous agentic pipeline for migrating the JADE multi-agent framework from Java 1.5 to a modern LTS version — with self-improving skills that compound across version jumps.**

JADE (Java Agent Development Framework) is a legacy multi-agent system last updated for Java 1.5 (2004). PolishedJADEite is a research project from Warsaw University of Technology that runs a fully autonomous migration pipeline on Hermes Agent — no human-in-the-loop at execution time.

The system doesn't just migrate code. It **builds its own migration tooling** — generating, benchmarking, and improving skills from each migration failure, so subsequent modules migrate faster.

---

## The Problem

- JADE is stuck on **Java 1.5** (2004) — no generics, no enums as classes, no lambda expressions, no stream API
- Standard LLM chats fail at complex migrations because of **context loss** and **lack of execution tools**
- Human experts are a bottleneck — every module requires the same pattern of analysis, refactoring, testing
- Legacy migration isn't a one-shot task — as JADE evolves upstream, the migration must stay in sync

## The Solution

An **agentic pipeline** where an orchestrator (Hermes Agent) coordinates specialized sub-agents, and a **skill-creation loop** lets the system build its own migration tooling:

```
Hermes Orchestrator
│
├── Analyzer agent      → detects: "this is a 1.5→1.6 enum idiom"
├── Refactorer agent   → applies modernization using skills
├── Tester agent       → runs JUnit, parses failures
├── Skill-Creator agent → reads failures → generates or improves skills
└── Archivist agent    → maintains skill registry + version history
```

**Skills** are the core innovation. Instead of human-written migration guides, the system generates its own skills from failures:

1. Tester runs tests → finds a failure pattern
2. Skill-Creator analyzes the failure → generates a skill that handles this pattern
3. Skill is benchmarked, versioned, and registered
4. Next module uses the improved skill instead of repeating the failure

Over time, skills **compound** — the 1.8→11 jump requires far fewer interventions than 1.5→1.6 because the system already learned from earlier iterations.

---

## Architecture

### Agentic Pipeline

The pipeline executes iterative version jumps (`1.5 → 1.6 → 1.7 → 1.8 LTS → newer LTS`):

```
For each version jump V → V+1:

  Contextualize   → Feed the agent generated migration context
  Instruct        → Agent uses skills on specific JADE modules
  Execute & Iter  → Draft refactors, apply changes, run tests
  Knowledge Cap   → Summarize hurdles into improved skills
```

This is a **closed learning loop** — the system gets better at migration over time, not just better at individual files.

### Meta-Circular Skill Ecosystem

Skills live in a versioned registry. A skill is a prompt template + optional scripts + evaluation harness:

```
skill-registry/
├── 1.5-to-1.6/
│   ├── enum-modernization/     # handles Java 1.5 enum idioms
│   │   ├── SKILL.md
│   │   ├── scripts/
│   │   │   └── detect_enum_patterns.py
│   │   └── evals/
│   │       └── eval_cases.json
│   └── assert-statements/      # handles assert→throw patterns
│       └── ...
├── 1.6-to-1.7/
│   └── diamond-operator/       # handles <> type inference
│       └── ...
├── 1.7-to-1.8/
│   ├── lambda-rewriter/        # inner classes → lambdas
│   └── stream-api-advisor/     # loop→stream transformations
│       └── ...
└── 1.8-to-11/
    └── ...
```

Skills are created by the **Skill-Creator agent** — they are not human-written. The Skill-Creator:

1. Reads failed test outputs from the Tester agent
2. Identifies the pattern that caused the failure
3. Proposes a new skill (or improvement to an existing one)
4. Runs benchmarks to verify the skill works
5. If the skill improves pass rate, it is committed to the registry

### Sub-Agent Responsibilities

| Agent | Role | Skills it uses |
|-------|------|---------------|
| **Analyzer** | Scans JADE module for Java version patterns | `java-version-detector`, `dependency-scanner` |
| **Refactorer** | Applies modernization transformations | `enum-modernizer`, `lambda-rewriter`, `stream-advisor` |
| **Tester** | Runs JUnit, parses failures, feeds back to Skill-Creator | `test-runner`, `failure-classifier` |
| **Skill-Creator** | Generates and improves migration skills | `skill-creator` (meta — creates other skills) |
| **Archivist** | Maintains skill registry, version history, benchmarks | `skill-registry-manager` |

---

## Key Principles

### 1. Benchmark-Driven Iteration

Migration quality is measured by **benchmark pass rate**, not gut feeling. Each skill is evaluated against a suite of test cases extracted from real JADE code patterns. A skill only improves if it increases pass rate on held-out cases.

### 2. Skills Compounding

Early version jumps (1.5→1.6) teach the system about JADE's patterns. Later jumps (1.8→11) inherit those lessons. The result is **superlinear acceleration** — each module takes less time than the last because the skills already exist.

### 3. No Human-in-the-Loop at Execution

The orchestrator decides what to migrate next, which skills to generate, when to branch and revert. Humans set goals and review outcomes — but the execution loop runs autonomously.

### 4. Semantic Preservation

JUnit catches **regressions** (behavior that used to work and broke). But semantic drift — behavior that technically passes tests but subtly changed — requires **contract testing** and **property-based verification**. The system tracks both.

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
| [SWE-Adept](https://arxiv.org/abs/2603.01327) (He & Roy, 2026) | Two-agent codebase analysis with shared working memory and Git-based version control. Localization agent + resolution agent pattern maps to Analyzer + Refactorer. |
| [FullStack-Agent](https://arxiv.org/abs/2602.03798) (Lu et al., 2026) | Multi-agent framework with self-improvement via back-translation. The FullStack-Learn self-improvement loop is the template for our Skill-Creator agent. |
| [From Helpful to Trustworthy](https://arxiv.org/abs/2604.10300) (Ayon, 2026) | Multi-agent pair programming with iterative validation. Accepted at FSE 2026. |

---

## Repository Structure

```
PolishedJADEite/
├── README.md                   # This file
├── LICENSE                     # MIT
├── jade/                       # JADE source (cloned/forked separately)
│   └── ...
├── skill-registry/             # Autogenerated skill ecosystem
│   ├── 1.5-to-1.6/
│   ├── 1.6-to-1.7/
│   └── ...
├── benchmarks/                 # Evaluation harnesses per version jump
│   └── 1.5-to-1.6/
│       └── eval_cases.json
├── hermes-config/              # Hermes Agent configuration for this project
│   └── ...
└── .gitignore
```

---

## Team

- **Mateusz Jarosz**, Warsaw University of Technology
- **Sebastian Rydz**, Warsaw University of Technology

---

## License

MIT
