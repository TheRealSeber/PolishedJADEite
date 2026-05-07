# Deep Research: Referenced Works Analysis

*This document analyzes the methodology, results, failures, and transferable lessons from four foundational papers that inform the PolishedJADEite architecture.*

---

## 1. From Translation to Superset — "Rust-to-Python Migration at Scale"

**Paper:** Wang & Sengupta, arXiv:2604.11518 | **Venue:** ICML 2026 | **Codebase:** 648K LOC Rust → Python

### Methodology

The core contribution is treating **code migration as a translation task constrained to produce a superset** — the output Python must be functionally equivalent to the input Rust. They use SWE-bench Verified (a benchmark of real GitHub issues with ground-truth fixes) as the objective function, driving the entire pipeline.

The pipeline is a three-stage loop:

1. **Translate** — Generate Python from Rust using iterative LLM prompts, starting with a "naive translation" and refining it
2. **Test** — Run the SWE-bench test suite to get a pass/fail signal per benchmark instance
3. **Revise** — If tests fail, feed the failure back into the next iteration of the translator

The key insight is that a diff between the original Rust and translated Python reveals the *delta* — what language features were added, removed, or transformed. This delta is what they optimize on.

### What Worked

- **Benchmark-as-objective-function**: Using SWE-bench pass rate as the only optimization target gave them a clean, reproducible signal. No subjective quality scoring.
- **Iterative refinement loop**: One-shot translation failed consistently; iterating with failure feedback dramatically improved results. The paper shows a monotonic improvement curve as iterations increase.
- **Translation-to-superset framing**: Rather than trying to produce identical code, producing *equivalent* code (same behavior, different idioms) sidesteps the trap of over-relying on syntax-level mapping.
- **Language feature targeting**: They identified that certain Rust patterns (lifetimes, trait bounds, macros) map poorly to Python. By tracking which patterns caused failures, they directed the translator to handle them specially.

### What Failed / Limitations

- **Macro translation was the hardest failure mode**: Rust macros expand to code; Python has no direct equivalent. Every macro pattern required custom handling, and the failure rate there was never brought to zero.
- **Dependency graph complexity**: Rust's ownership model doesn't exist in Python. Translated code sometimes silently dropped thread-safety guarantees — not caught by SWE-bench because the tests don't exercise concurrent behavior.
- **15.9x code reduction is real but misleading**: The reduction comes partly from removing lifetime annotations and type hints that aren't mandatory in Python. The "same behavior" claim holds for runtime, but the code is not structurally equivalent.
- **Context window saturation**: For 648K LOC, they had to do module-level translation rather than whole-codebase. The boundaries between modules introduced edge cases that required human intervention to resolve.
- **SWE-bench coverage is narrow**: The benchmark tests *fixes* to issues, not general code behavior. Translated code that passes SWE-bench might still have semantic drift in parts of the codebase that no issue touched.

### Transferable Lessons for PolishedJADEite

1. **SWE-bench as benchmark template**: JADE's JUnit suite maps directly to SWE-bench — same idea of "does this code still do what it did before?" Use pass rate as the objective.
2. **Iterative translation loop is non-negotiable**: One-shot modernization (give the LLM all the code, ask it to modernize) will fail. The Refactorer must operate in a loop: draft → test → revise → test again.
3. **Track failure modes explicitly**: Just as they tracked which Rust patterns caused failures, the Tester agent should tag every failure with a pattern label (e.g., "enum-idiom", "diamond-operator"). This data feeds the Skill-Creator.
4. **Macro-equivalent patterns need special handling**: In Java 1.5→1.8, the equivalent problem is `assert` statements (compile-time vs runtime), enums as class replacements, and reflection-heavy code. These need dedicated skills, not generic modernization prompts.
5. **Module-level translation boundaries are dangerous**: JADE has ~50+ packages. Migrating one package at a time works, but cross-package dependencies (e.g., an enum in package A used as a type in package B) need a global dependency analysis pass first.

---

## 2. SWE-Adept — "Two-Agent Codebase Repair with Shared Working Memory"

**Paper:** He & Roy, arXiv:2603.01327 | **Venue:** ICLR 2026 | **Benchmark:** SWE-Bench Lite + Pro

### Methodology

SWE-Adept decomposes the codebase repair problem into two specialized agents that share a **working memory store** (a structured context that persists across agent turns):

- **Localization Agent**: Given a bug report or issue description, it searches the codebase to identify the files and functions most likely to be involved. It writes its findings to the working memory.
- **Resolution Agent**: Reads from working memory, generates a fix for the localized code, and writes the fix back.

The working memory is indexed by *execution steps* — each agent's contribution is timestamped and indexed, so the Resolution Agent can look up exactly what the Localization Agent saw without re-running the search.

They use Git-based version control: each proposed fix is a Git branch, tests run against the branch, and the branch is merged or discarded based on results.

### What Worked

- **Agent specialization**: Localization and resolution require different skill sets (search-heavy vs. edit-heavy). Separate agents with separate prompts outperformed a single-agent approach by 4.7% on SWE-Bench Lite/Pro.
- **Shared working memory**: The explicit memory store prevented the Resolution Agent from "forgetting" what the Localization Agent found. Without it, the Resolution Agent often re-searched for the same information, wasting context window and introducing inconsistencies.
- **Git-based versioning**: Branch-per-fix made it trivial to roll back a bad fix. It also made the entire history of attempts auditable.
- **Structured memory indexing**: Indexing by execution steps (not just time) meant that memory entries were semantically meaningful — "step 5: identified `MessageTemplate.java` as the likely fault site" is more useful than "step 5: 14:32:07".

### What Failed / Limitations

- **Working memory grows unbounded**: In long-running sessions, the memory store accumulated thousands of entries. They never solved the eviction problem — eventually the Localization Agent's searches were lost in noise. They note this as "future work."
- **Localization accuracy bottlenecked everything**: If the Localization Agent picked the wrong file, the Resolution Agent could never fix the issue. Their localization accuracy was ~60%, which set a hard ceiling on end-to-end performance.
- **Single-issue-at-a-time**: The system processes one issue per branch. For JADE's simultaneous multi-package migration, this would require running dozens of SWE-Adept instances in parallel — which they never explored.
- **Shared memory is a single point of failure**: If the memory store corrupted or lost entries, both agents became inconsistent with each other. No fault-tolerance mechanism was described.

### Transferable Lessons for PolishedJADEite

1. **Two-agent specialization maps cleanly to our architecture**: Analyzer = Localization Agent, Refactorer = Resolution Agent. The working memory pattern should be implemented as a shared context store between agents.
2. **Git-based version control per migration**: Every version-jump attempt should be a branch. This lets us roll back to a known-good state if a migration breaks things, and maintains a full audit trail of what was tried.
3. **Memory eviction is a real problem**: For JADE's ~50 packages, a naive memory store will overflow. We need an explicit eviction strategy — probably LRU with importance weighting based on how recently a fact was used by an active agent.
4. **Localization must be high-accuracy or the whole pipeline suffers**: Before the Refactorer touches any code, the Analyzer's pattern detection must be reliable. The first skills we build should be diagnostic skills (what version idiom is this?) before we build transformation skills.

---

## 3. FullStack-Agent — "Multi-Agent Full-Stack Development with Back-Translation Self-Improvement"

**Paper:** Lu et al., arXiv:2602.03798 | **Venue:** ICML 2026 | **Codebase:** Generated full-stack websites (Next.js/NestJS)

### Methodology

FullStack-Agent has three tightly coupled components:

**FullStack-Dev** — A multi-agent development framework:
- Planning Agent (architect): designs the full-stack structure, outputs frontend/backend plans in JSON
- Backend Coding Agent: implements the backend from the plan
- Frontend Coding Agent: implements the frontend using the backend's API summary
- Two debugging tools (Frontend Debugging Tool, Backend Debugging Tool): dynamically generate test cases and localize errors

**FullStack-Learn** — An iterative self-improvement pipeline:

1. Crawl real GitHub website repositories
2. Information Gathering Agent reads the repo → produces a summary + quality score + plans
3. Trajectory Back-Translation Agent reproduces the repo in an empty template (i.e., it generates the agentic *trajectory* that would produce this repo from scratch)
4. Rule-based program cleans the trajectory (removes references to original repo)
5. Augmentation Planning Agent proposes 5 augmentations per repo (1 simplification, 1 extension, 3 application transitions)
6. Augmentation Implementing Agent applies them → synthetic repos
7. Iterative self-improvement: train model on round N data → use it to generate round N+1 data

**FullStack-Bench** — A three-tier evaluation benchmark:
- Frontend: GUI-agent judge + database log validation
- Backend: API testing via judge agent
- Database: schema snapshot validation

### What Worked

- **Back-translation for trajectory generation**: Instead of generating trajectories from scratch (which produces low-quality, out-of-distribution agent behavior), back-translation converts existing high-quality repos into trajectories. This produced much more realistic agent behavior than synthetic user-instruction → code generation.
- **Repository augmentation as data scaling**: Generating augmented repos (simplify, extend, port to similar app type) was 5x cheaper than finding new repos. The model trained on augmented data outperformed one trained only on original repos.
- **Debugging tools dramatically reduced iteration count**: Removing the Backend Debugging Tool increased average iterations from 74.9 to 115.5. The tool essentially did in 1 call what the agent used to do in ~40 shell commands.
- **Iterative self-improvement without stronger models**: The 30B model improved itself through two rounds of training without relying on a larger model for distillation. 9.7% improvement on frontend, 9.5% on backend, 2.8% on database.
- **Database interaction validation as a forcing function**: They appended a database log check after frontend tests — a frontend could only count as correct if the database logs showed real writes. This caught "fake correct" cases where the UI looked right but no data was stored.

### What Failed / Limitations

- **Backend accuracy is still the weakest tier** (77.8% vs 64.7% frontend, 77.9% database): Even with dedicated debugging tools and testing, the backend remains the hardest part. This suggests that for JADE, the backend (i.e., the core agent lifecycle logic, message passing, yellow pages) will be the most challenging thing to migrate correctly.
- **Error analysis reveals a dominant failure mode: "No Database Interaction"** (34.3% of backend errors): The backend would return fake responses that *looked* correct rather than actually querying the database. This is the analog of JADE code that compiles and passes tests but doesn't actually implement the contract correctly.
- **"Database Empty" is 46.7% of database errors**: This means the agent often forgot to initialize the database entirely. In JADE terms: the agent would register with the AMS but not actually set up its behaviors properly — it looks initialized but isn't.
- **Frontend Debugging Tool depends on GUI agents**: They used Qwen3-VL-235B-A22B-Instruct for GUI testing. For JADE, we don't have a visual GUI — our "GUI" is the JADE runtime's agent output and message logs. We need an equivalent "runtime behavior debugger" rather than a visual GUI tool.
- **Decontamination against the benchmark**: They had to filter training data for Jaccard similarity > 0.6 against the benchmark. This is a real problem for JADE: if our migration skills are trained on JADE code patterns, and our benchmark also uses JADE code, we risk data leakage. We need a clean split between skill-training data and evaluation data.

### Transferable Lessons for PolishedJADEite

1. **Back-translation is the Skill-Creator's core algorithm**: Instead of generating skills from scratch, the Skill-Creator should take *existing high-quality JADE code* (the reference implementation after migration) and back-translate it to show the agent *how to get there from the pre-migration version*. This is the trajectory: pre-migration state → skill application → post-migration state.
2. **Augmentation mirrors JADE module scaling**: JADE has multiple packages. Instead of finding new migration problems, we take one well-understood migration (e.g., `jade.core.messaging`) and apply augmentation strategies: simplify it, extend it to a similar module, port the pattern to a different package. This 5x's our effective skill training data.
3. **Debugging tools are force multipliers — build them first**: FullStack-Dev's Backend Debugging Tool cut iterations by 40%. For JADE, we need a **JADE Runtime Inspector** — a tool that can query the agent's in-memory state, check that behaviors are registered, that message handlers are wired, that the yellow pages query returns expected results. Without this, the Refactorer is flying blind.
4. **Three-tier testing (frontend/backend/database) maps to JADE tiers**: JADE has: (1) API-level — does the public interface compile and accept the right calls? (2) Runtime-level — does the agent actually boot, register, and respond to messages? (3) System-level — do multiple agents find each other via yellow pages, exchange messages correctly? We need all three tiers.
5. **Data contamination is a real risk**: Our skill training set (JADE package X migrated well) must not overlap with our benchmark set (JADE package Y used for evaluation). We need a formal split.

---

## 4. From Helpful to Trustworthy — "Multi-Agent Pair Programming with Iterative Validation"

**Paper:** Ayon, arXiv:2604.10300 | **Venue:** FSE 2026 (Doctoral Symposium) | **Status:** Proposed / In Progress

### Methodology (Planned)

This is a doctoral research proposal (not yet completed) that plans three studies:

1. **Translation study**: Informal problem statements → formal specifications → standards-aligned requirements
2. **Refinement study**: Tests + implementations refined using automated feedback (solver-backed counterexamples)
3. **Maintenance study**: Refactoring, API migrations, and documentation updates while preserving validated behavior

The key claim is that current LLM pair programming produces artifacts that are *plausible* but not *aligned with developer intent* — and that multi-agent workflows with explicit intent externalization can close this gap.

### What They Plan to Do (Assessment Based on Proposal)

- **Intent externalization**: The system will maintain a formal specification that tracks what the developer *intended*, not just what the code *does*. This is the key insight: current LLMs optimize for "does this code look right?" but not "does this code do what the developer wanted?"
- **Solver-backed counterexamples**: When a test passes but the behavior is suspect, a formal verifier generates counterexamples to stress-test the implementation.
- **Iterative validation loop**: The system doesn't just generate once — it cycles through: generate → formal spec check → counterexample attack → revise → repeat.

### What to Watch For (Critical Assessment)

- **This is a proposal, not a result**: There are no numbers yet. The 3-study plan is ambitious and may not fully materialize before the dissertation deadline.
- **Formal specification as a bottleneck**: Writing formal specs (TLA+, ACL2) for every JADE module would be as much work as migrating the code itself. For JADE's 50+ packages, this approach may not scale.
- **Counterexample generation is computationally expensive**: Solver-backed verification doesn't scale to large codebases. For JADE's 648K LOC equivalent scale, this would need to be restricted to critical sections.
- **The "plausible but wrong" problem is the core JADE risk**: JADE has complex concurrency semantics (multi-agent, asynchronous message passing). A migrated enum or lambda expression might *look* correct and pass JUnit, but subtly violate the original concurrency contract. This is exactly the "plausible but misaligned" problem the paper identifies.

### Transferable Lessons for PolishedJADEite

1. **Intent tracking is harder than behavior tracking**: We can test "does this code behave the same?" (JUnit) but not "did the developer intend this behavior?" For JADE, developer intent lives in the JADE paper, the Java 1.5 spec comments, and the existing test suite. We should capture intent as structured comments in the refactored code.
2. **Counterexample-based stress testing for concurrency**: JADE's multi-agent message passing is its most complex contract. After each migration, we should run *adversarial* multi-agent scenarios — agents sending messages at high frequency, unexpected shutdowns, yellow pages failures — to catch the "plausible but wrong" class of bugs.
3. **The FSE 2026 publication venue is significant**: FSE (ESEC/FSE) is a top-tier software engineering venue. If this paper delivers on its claims, it will be widely cited. The multi-agent intent externalization idea is worth tracking.

---

## Cross-Cutting Synthesis: What All Four Papers Agree On

### What Universally Worked

| Pattern | Evidence |
|---------|----------|
| **Multi-agent specialization** | SWE-Adept (2 agents), FullStack-Agent (3+ agents), all showed gains over single-agent |
| **Iterative loop with test feedback** | Translation-to-Superset (3-stage loop), FullStack-Agent (iterative self-improvement), all confirmed this as essential |
| **Debugging tools as force multipliers** | FullStack-Agent: removing Backend Debugging Tool +40% iteration overhead; SWE-Adept: shared working memory reduced redundant search |
| **Benchmark-driven optimization** | Translation-to-Superset used SWE-bench as objective; FullStack-Agent used FullStack-Bench; both proved that optimizing on a clean metric beats subjective evaluation |
| **Training on domain-specific trajectories** | FullStack-Agent's back-translation produced much better training data than synthetic generation; Translation-to-Superset's delta analysis only works because they had real migration pairs |

### What Universally Failed or Was Underestimated

| Failure Mode | Evidence | JADE Equivalent |
|-------------|----------|----------------|
| **Silent semantic drift** | FullStack-Agent: fake backend responses (34.3%); Translation-to-Superset: dropped thread-safety guarantees | JADE code that compiles, passes JUnit, but doesn't actually implement the agent contract correctly |
| **Context window saturation** | Translation-to-Superset: had to segment 648K LOC into module-level chunks | JADE's ~50 packages mean we must migrate module by module, but cross-package enum dependencies create edge cases |
| **One-shot generation** | Every paper tried and failed at one-shot; all moved to iterative loops | Our Refactorer must never attempt one-shot modernization of a JADE package |
| **Benchmark contamination** | FullStack-Agent had to filter training data against benchmark | Our skill training data and evaluation data must be formally separated |
| **Unbounded memory growth** | SWE-Adept's working memory accumulated without eviction | The Orchestrator's shared context needs explicit eviction |

### The Four Most Critical Transferable Lessons for PolishedJADEite

**1. Debugging tools are not optional — they are the bottleneck.**
FullStack-Agent showed that a well-designed debugging tool cuts agent iterations by 40%. We need to build a **JADE Runtime Inspector** before we build any migration skills. Without it, the Refactorer can't verify that an agent actually boots, registers, and participates in message exchanges correctly.

**2. The Skill-Creator must use back-translation, not generation-from-scratch.**
FullStack-Agent proved that converting existing high-quality code into training trajectories (back-translation) produces far better skills than asking an LLM to invent a migration skill from first principles. For JADE: take a successfully migrated module, back-translate it to show the skill that would have produced that migration from the pre-migration state.

**3. Three-tier testing (API / Runtime / System) is necessary.**
FullStack-Agent's three test tiers (frontend/backend/database) caught failures that single-tier testing missed. JADE needs: (1) API compilation + interface contract tests, (2) single-agent runtime tests (does it boot, register, respond), (3) multi-agent system tests (do agents find each other, exchange messages, handle failures).

**4. Skills must be versioned and benchmarked, not just written.**
Translation-to-Superset showed that skills improve monotonically when measured against a benchmark. A skill that achieves 80% pass rate on eval cases is worse than one that achieves 95% — and this is only discoverable if we actually run the eval. Every skill in the registry needs an associated `eval_cases.json` and a pass rate threshold for acceptance.

---

## Benchmark Suitability Assessment

| Benchmark Approach | Paper | JADE Applicability | Notes |
|-------------------|-------|-------------------|-------|
| SWE-bench Verified | Translation-to-Superset | ✅ High | JUnit pass rate maps directly. JADE's test suite IS our SWE-bench. |
| Git-based version control | SWE-Adept | ✅ High | Branch-per-migration enables rollback. Should be our default workflow. |
| FullStack-Bench (3-tier) | FullStack-Agent | ✅ High | Maps to API / Runtime / System tiers. Must implement all three. |
| Solver-backed counterexamples | Helpful-to-Trustworthy | ⚠️ Medium | Computational cost is high. Apply only to critical JADE contracts. |
| Formal specification tracking | Helpful-to-Trustworthy | ⚠️ Low | Too expensive for 50+ packages. Restrict to core `jade.core` package only. |

---

## Research Gaps (What No Paper Addresses)

These are open problems that PolishedJADEite must solve without a template:

1. **How to migrate cross-package type dependencies**: All four papers work on single-package or single-repository code. JADE's enums in `jade.lang` used as types in `jade.core.messaging` require a global dependency analysis that no paper addresses.
2. **How to handle framework-specific idioms that don't map cleanly**: Rust lifetimes → Python has no equivalent. Java 1.5 `assert` statements → Java 8+ `if (!x) throw` requires semantic knowledge of the original intent (was the assert checking a precondition? An invariant?).
3. **How to verify semantic preservation when the test suite is itself version-dependent**: JADE's tests were written for Java 1.5. Some tests may fail not because the code is wrong, but because the test itself uses a deprecated Java 1.5 API. Which failures are regressions and which are test-level issues?
4. **How to handle concurrent multi-agent behavior in a single-agent test harness**: JADE's core value is its multi-agent runtime. Testing it requires starting multiple agents, facilitating message exchange, and verifying timeout/lifecycle behavior. None of the four papers address multi-agent test harness design.
