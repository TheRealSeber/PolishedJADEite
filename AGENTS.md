# JADE Migration Pipeline

> **Stack:** `jade-core-*` (agnostic plumbing) + `jade-recipe-*` (version-specific transforms).
> **Handoff:** File-based artifacts under `artifacts/`. Skills communicate via disk, never prompt context.
> **Ordering:** Rule-by-Rule Sequential Batching — ONE rule applied to ALL files, then verify, then commit.
> **Full constitution:** `docs/architecture.md` — read it before creating core skills, modifying the dispatcher, or altering phase flow.

---

## Invocation Contract

```
python .claude/skills/<name>/scripts/<script>.py --artifacts-dir artifacts/ --rule-id <id>
```

Exit codes: `0`=success, `1`=attention-needed, `2`=failure, `3`=env-error.
All writes: tmp-file + atomic rename. Idempotent where feasible.

## Rule-by-Rule Sequential Batching

Apply ONE `rule_id` to ALL flagged files → verify compile + semantic gates → atomic git commit → next rule.
**Never** component-by-component (breaks cross-package contracts). **Never** parallel rules.

## Hard Constraints

1. **File paths only** — never pass raw source or large JSON in prompts.
2. **Never skip verification** — failed gate = halt, do not proceed.
3. **Sequential only** — no parallel rule execution. Orchestrator operates as a
   transition-table state machine. Verification failures route through retry router;
   retry exhaustion → escalation → skip rule → continue to next rule.
4. **Safety gate** — commit only files in batch artifact; unrelated dirty files = abort.
5. **Evidence required** — change collector halts with `AWAITING_SOURCE_INPUT` rather than fabricate.
6. **Separation** — Core skills contain zero version-specific logic. Recipe skills contain zero pipeline logic.
7. **One commit per rule** — never squash rule commits. SHA logged to `09-rule-commit-log.json`.
8. **Phase 0 optional** — `JadeDocumentation/` enriches verification but pipeline never requires it.
9. **Workspace isolation** — pipeline NEVER mutates baseline source. Orchestrator copies
   `baseline_path` → `workspace_path` at INIT. All skills operate on the copy only. `JADE-4.6.0/`
   is read-only and never modified.
10. **Never fake artifacts** — every `artifacts/` file must be produced by the Phase-appropriate
    script (Phase 4 tooling-scout → `02-tooling-scout-report.json`, Phase 5 build-fixer →
    `03-build-audit.json` + `03-build-verify.log`, Phase 7 verification → `07-build.log`).
    Manually writing a file that "looks like" a pipeline output to bypass a gate is forbidden.
11. **Never exclude existing source** — the workspace MUST be a faithful copy of the
    baseline (minus `doc/` and `examples/`).  Adding exclusion patterns to build files
    (e.g. `excludes="FIPA/**,jade/mtp/iiop/**"`) to force a successful compilation
    on an incompatible JDK is forbidden.  Build failures caused by JDK version
    mismatches must be solved via the Docker-isolated build environment, not source
    mutilation.
12. **Container agnosticism** — never hardcode JDK versions or Docker images in consumer
    test configs, recipes, or core scripts. Resolve container images from the central
    registry (`config/docker-images.json`) using run-config target version and dynamic placeholders.
13. **Java 11+ readiness** — every migration targeting Java 11 or newer MUST run dependency
    compatibility auditing for removed JDK modules/libraries (including CORBA/JAXB families)
    during BUILD_GATE_READY and report blockers/warnings in build audit artifacts.

## Skill Inventory

| Type | Count | Examples |
|------|-------|----------|
| Core (`jade-core-*`) | 11 | orchestrator, change-collector, scanner, batch-processor, rule-dispatcher, verification, atomic-commit, retry-router, evaluator, tooling-scout, build-fixer |
| Recipe (`jade-recipe-*`) | 0 (per-migration) | Generated dynamically by Skill Creator from manifest data. Registry starts empty. |
| Utility (`jade-utility-*`) | 1 | consumer-onboarder — ingests ZIP archives of JADE projects into the `consumer-playground/` for runtime testing |

## Consumer Playground & Runtime Verification

After migration compilation, a **RUNTIME_VERIFY** phase boots JADE in Docker against consumer projects
stored in `consumer-playground/`. Each consumer project contains JADE agent source files and a
`test-config.json` defining the Docker image, boot arguments, and expected stdout markers.
The `runtime_verify.py` script (in `jade-core-verification`) compiles each consumer against the
migrated workspace's `jade.jar`, runs it in an isolated Docker container, and validates:

1. **Expected markers** — all `expected_stdout_markers` must appear in output
2. **Reverse assertion** — failure patterns (`Exception`, `NullPointerException`, `SEVERE:`) cause immediate FAIL
3. **Timeout** — always treated as FAIL
4. **Graceful shutdown** — consumers must shut down JADE cleanly (see TestRunnerAgent pattern)

Consumer projects are managed via `jade-utility-consumer-onboarder`.

## Quick Phase Reference

```
0 (opt) → 1 → 2 → 3 → 4 → 5 → 6 → 7 (batch loop) → 8 → RUNTIME_VERIFY → DONE
```

Artifact prefixes: `00-run`, `01-manifest`, `02-tooling`, `03-build`, `04-flag`, `05-batch`, `06-fix`, `07-verify`, `08-retry`, `09-commit`, `10-eval`.
