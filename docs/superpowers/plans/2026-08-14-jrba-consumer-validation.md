# JRBA Consumer Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add JRBA as a Maven-backed runtime consumer and extend the verifier without breaking existing javac consumers.

**Architecture:** Keep JRBA isolated under `consumer-playground/jrba/`. Add an explicit Maven consumer path to `runtime_verify.py`, preserving the current javac path. The Maven path compiles the consumer against the migrated workspace JADE jar, stages the resulting classes and dependency jars for Docker, and validates the same output and failure-marker contract.

**Tech Stack:** Python 3, pytest, Maven, Java, JADE, Docker, JSON configuration.

---

### Task 1: Define and test Maven consumer configuration

**Files:**
- Modify: `.claude/skills/jade-core-verification/scripts/runtime_verify.py`
- Create: `tests/test_runtime_verify_maven_config.py`

- [ ] **Step 1: Write failing config tests**

Test that Maven mode accepts a project root inside the consumer, rejects a missing root, rejects path traversal outside the consumer, and retains javac defaults when `build_mode` is absent.

- [ ] **Step 2: Run the focused tests**

Run: `pytest tests/test_runtime_verify_maven_config.py -q`

Expected: FAIL because Maven mode and validation helpers do not exist.

- [ ] **Step 3: Implement minimal configuration helpers**

Add explicit validation for `build_mode`, `maven_project_root`, and artifact output paths. Keep all paths relative to the consumer or workspace roots and return actionable errors rather than silently falling back.

- [ ] **Step 4: Run focused and existing verifier tests**

Run: `pytest tests/test_runtime_verify_maven_config.py tests/test_artifact_contracts.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the isolated contract change**

Run: `git add .claude/skills/jade-core-verification/scripts/runtime_verify.py tests/test_runtime_verify_maven_config.py && git commit -m "feat: add Maven consumer config contract"`

### Task 2: Implement Maven consumer build and Docker classpath staging

**Files:**
- Modify: `.claude/skills/jade-core-verification/scripts/runtime_verify.py`
- Modify: `tests/test_runtime_verify_maven_config.py`

- [ ] **Step 1: Add failing build-command tests**

Use a fake Maven executable and temporary project to assert the command receives the selected workspace JADE artifact, writes output to a per-consumer build directory, and returns a failure when Maven exits nonzero.

- [ ] **Step 2: Run the tests and confirm failure**

Run: `pytest tests/test_runtime_verify_maven_config.py -q`

Expected: FAIL before Maven build execution exists.

- [ ] **Step 3: Implement Maven build mode**

Add a separate `build_maven_consumer` path. It must run Maven non-interactively, use a temporary local repository, avoid network assumptions where possible, copy compiled output and resolved runtime dependencies into the consumer build directory, and return structured build output. Do not alter the javac path.

- [ ] **Step 4: Add runtime classpath construction**

Build the Docker classpath from the compiled consumer output, workspace dependencies, and resolved Maven runtime jars. Preserve `${TARGET_DOCKER_IMAGE}` resolution through `config/docker-images.json`.

- [ ] **Step 5: Run focused tests**

Run: `pytest tests/test_runtime_verify_maven_config.py -q`

Expected: PASS.

- [ ] **Step 6: Commit the Maven build path**

Run: `git add .claude/skills/jade-core-verification/scripts/runtime_verify.py tests/test_runtime_verify_maven_config.py && git commit -m "feat: support Maven consumer builds"`

### Task 3: Add JRBA consumer source and deterministic integration agent

**Files:**
- Create: `consumer-playground/jrba/pom.xml`
- Create: `consumer-playground/jrba/test-config.json`
- Create: `consumer-playground/jrba/src/main/java/org/jrba/consumer/JRBAIntegrationAgent.java`
- Create: `consumer-playground/jrba/src/main/java/org/jrba/consumer/JRBAConsumerMain.java` if Maven packaging requires a launcher
- Create: `tests/test_jrba_consumer_contract.py`

- [ ] **Step 1: Copy JRBA production sources from the supplied archive**

Copy only `jrba-master/src/main/java` into the consumer project, preserving package paths. Do not copy `src/test`, compiled files, or local binary `lib/jade.jar`.

- [ ] **Step 2: Add the Maven project descriptor**

Declare JRBA's production dependencies from its source `pom.xml`, replace the local JADE binary with the workspace JADE dependency supplied by the verifier, and keep the Java source level explicit. The descriptor must not contain credentials or publishing configuration.

- [ ] **Step 3: Add a deterministic integration agent**

Create a no-argument JADE agent that exercises one JRBA behaviour, prints `JRBA_TEST_STARTED`, prints `JRBA_TEST_PASSED` only after the behaviour completes, prints `JRBA_TEST_FAILED` on failure, and calls `System.exit(0)` or `System.exit(1)` exactly once.

- [ ] **Step 4: Add consumer configuration**

Configure Maven mode, `${TARGET_DOCKER_IMAGE}`, `jade.Boot`, the integration agent, `JRBA_TEST_PASSED`, and a bounded timeout. Do not hardcode a Docker image.

- [ ] **Step 5: Add static contract tests**

Assert that the config uses Maven mode and the dynamic image placeholder, the agent has a no-argument setup path, success and failure markers exist, and no binary dependency is tracked.

- [ ] **Step 6: Commit the JRBA consumer**

Run: `git add consumer-playground/jrba tests/test_jrba_consumer_contract.py && git commit -m "test: add JRBA consumer validation"`

### Task 4: Integrate runtime discovery and artifact reporting

**Files:**
- Modify: `.claude/skills/jade-core-verification/scripts/runtime_verify.py`
- Modify: `tests/test_runtime_verify_maven_config.py`

- [ ] **Step 1: Add a discovery test**

Assert that a valid Maven consumer is discovered alongside existing javac consumers and that its build result is included in the runtime verification artifact.

- [ ] **Step 2: Implement mode dispatch**

Dispatch per consumer configuration, keep project names and statuses in the existing artifact schema, and include build command/output sufficient to diagnose failures without embedding source payloads.

- [ ] **Step 3: Preserve failure semantics**

Apply expected-marker checks, reverse assertion patterns, timeout handling, and graceful-shutdown requirements equally to Maven and javac consumers.

- [ ] **Step 4: Run the complete Python test suite**

Run: `pytest -q`

Expected: PASS for all repository tests.

- [ ] **Step 5: Commit integration changes**

Run: `git add .claude/skills/jade-core-verification/scripts/runtime_verify.py tests/test_runtime_verify_maven_config.py && git commit -m "feat: integrate Maven consumers into runtime verification"`

### Task 5: Execute real JRBA gates

**Files:**
- No source changes unless a preceding gate reports a concrete failure.
- Generated evidence: runtime verifier artifact under the configured artifacts directory.

- [ ] **Step 1: Run static consumer validation**

Run: `python .claude/skills/jade-core-verification/scripts/runtime_verify.py --help` and the focused contract tests.

Expected: the CLI loads and tests pass.

- [ ] **Step 2: Run the Dockerized runtime verifier in the isolated worktree**

Run: `python .claude/skills/jade-core-verification/scripts/runtime_verify.py --workspace migration-runs/sample/workspace --artifacts migration-runs/sample/artifacts --config migration-runs/sample/artifacts/00-run-config.json`

Use the corresponding real migration run paths when validating a non-sample migration. Do not fabricate `07-runtime-verify.json` or replace a failed result.

- [ ] **Step 3: If the gate fails, dispatch one fix agent for the reported root cause**

The fix agent may modify only files implicated by the failure, then the same focused test and runtime gate must be rerun. Stop after retry exhaustion and report the blocker.

- [ ] **Step 4: Confirm existing consumers remain covered**

The final runtime artifact must show PASS for the existing consumers and JRBA. A partial result is not completion.

### Task 6: Fresh subagent review and final verification

**Files:**
- Review only; no changes unless findings are confirmed.

- [ ] **Step 1: Dispatch a fresh reviewer with no implementation context**

Review the complete worktree diff against the design, focusing on path traversal, dependency reproducibility, hardcoded images, source omissions, failure handling, and unrelated changes.

- [ ] **Step 2: Resolve confirmed findings through a new focused fix loop**

For every confirmed finding, make the smallest correction, rerun the affected tests, and rerun the full suite or runtime gate as appropriate.

- [ ] **Step 3: Perform final evidence check**

Run: `git status --short`, `git diff --check`, `pytest -q`, and `python .claude/skills/jade-core-verification/scripts/runtime_verify.py --workspace migration-runs/sample/workspace --artifacts migration-runs/sample/artifacts --config migration-runs/sample/artifacts/00-run-config.json`. Report exact pass/fail evidence before claiming completion.
