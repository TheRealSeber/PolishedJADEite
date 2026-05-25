# Consumer Playground Runtime Verification — Design Spec

**Date:** 2026-05-25
**Status:** Approved
**Context:** JADE migration pipeline — adding runtime verification beyond compile-only checks

---

## Problem

The pipeline currently verifies migration correctness via **compile-only** checks (BUILD SUCCESSFUL in `07-build.log`). There is no mechanism to:

- Start a JADE platform from the migrated workspace
- Launch agents that exercise interaction protocols
- Assert that consumers of JADE's APIs function correctly at runtime
- Feed runtime traces into the existing semantic verifier

Without runtime verification, a migration could produce bytecodes that compile but fail at boot or produce incorrect agent behavior.

---

## Solution Overview

Add a **Runtime Verification phase** (`RUNTIME_VERIFY`) to the orchestrator state machine, powered by a new `consumer-playground/` directory of independent test projects and a `runtime_verify.py` script.

### Pipeline integration

```
RULE_BATCH_LOOP → (NO_MORE_RULES) → VERIFIED → RUNTIME_VERIFY → DONE
                                          ↘ VERIFY_FAIL → FAILED
```

**Note:** `RUNTIME_VERIFY` fires once per pipeline run, after ALL rule batches are complete, not per-rule.

### Components

| Component | Location | Purpose |
|-----------|----------|---------|
| Consumer projects | `consumer-playground/*/` | Independent JADE-based test projects |
| test-config.json | Per consumer project | Docker image, boot args, expected output |
| runtime_verify.py | `.claude/skills/jade-core-verification/scripts/` | Compile → run → assert loop |
| Orchestrator integration | `orchestrator.py` | New state, transition, script phase, artifact validation |

---

## Consumer Playground Structure

### This plan implements

```
consumer-playground/
└── version-check/
    ├── VersionCheckAgent.java
    └── test-config.json
```

### Future (not in this plan)

```
consumer-playground/
└── basic-ping/                    # deferred: separate plan
    ├── PingAgent.java
    ├── PongAgent.java
    └── test-config.json
```

### test-config.json schema

```json
{
  "name": "version-check",
  "description": "Verify JADE boots and reports Java runtime version",
  "docker_image": "frekele/ant:1.10.3-jdk8",
  "main_class": "jade.Boot",
  "boot_args": ["-container", "-agents", "check:VersionCheckAgent"],
  "expected_stdout_markers": ["JADE is ready", "RUNTIME_CHECK_PASSED"],
  "timeout_seconds": 60,
  "classpath_deps": [
    "src/jade/lib/jade.jar",
    "src/jade/lib/commons-codec/commons-codec-1.3.jar"
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Unique project identifier |
| `description` | string | Human-readable purpose |
| `docker_image` | string | Docker image for runtime execution |
| `main_class` | string | Entry point (typically `jade.Boot`) |
| `boot_args` | string[] | Arguments passed to main_class |
| `expected_stdout_markers` | string[] | Substrings that MUST appear in stdout |
| `timeout_seconds` | int | Max runtime before forced termination |
| `classpath_deps` | string[] | JAR paths relative to workspace root. Example: `src/jade/lib/jade.jar` resolves to `<workspace>/src/jade/lib/jade.jar` |

### Runtime Docker image

JDK 6 Docker images are unavailable on modern registries (deprecated, removed). We use `frekele/ant:1.10.3-jdk8` (JDK 8), which runs Java 6 bytecodes correctly. The `java.version` reported by VersionCheckAgent will be `1.8.x`. The test validates that JADE compiled with `-source 1.6 -target 1.6` produces bytecodes that boot and execute correctly. JVM backward compatibility ensures these same bytecodes would run on a genuine JDK 6.

---

## runtime_verify.py Design

### Inputs

| Argument | Purpose |
|----------|---------|
| `--workspace` | Path to migrated workspace (contains `lib/jade.jar`) |
| `--artifacts` | Artifacts directory for writing output |
| `--config` | Path to `00-run-config.json` |

### Algorithm

```
1. Verify workspace/lib/jade.jar exists
2. Scan consumer-playground/ for subdirectories containing test-config.json
3. If no consumers found → write pass result (total_consumers=0) → exit 0
4. For each consumer project:
   a. Parse test-config.json
   b. Verify required classpath_deps exist in workspace
   c. Create temp build directory
   d. Compile consumer .java files:
        javac -cp <workspace>/lib/jade.jar:<workspace>/lib/commons-codec/* \
              -d <temp> consumer/*.java
   e. If compilation fails → record FAIL, continue to next
   f. Run in Docker:
        docker run --rm \
          -v <workspace>:/ws \
          -v <temp>:/playground \
          <docker_image> \
          java -cp /ws/lib/jade.jar:/ws/lib/commons-codec/commons-codec-1.3.jar:/playground \
            <main_class> <boot_args>
   g. Capture stdout/stderr (container output)
   h. Check all expected_stdout_markers appear in stdout
   i. Record PASS or FAIL with evidence (stdout snippet on failure)
5. Write 07-runtime-verify.json
6. Exit 0 if overall_pass, exit 2 if any FAIL
```

### Output: `07-runtime-verify.json`

```json
{
  "run_id": "jade-1.5-to-1.6",
  "generated_at": "2026-05-25T12:00:00Z",
  "overall_pass": true,
  "total_consumers": 1,
  "passed": 1,
  "failed": 0,
  "results": [
    {
      "project": "version-check",
      "status": "PASS",
      "duration_seconds": 12.3,
      "jade_booted": true,
      "stdout_snippet": "JADE is ready\nRUNTIME_CHECK_PASSED: java.version=1.8.0_432"
    }
  ]
}
```

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | All consumers passed (or no consumers) |
| 2 | One or more consumers failed |
| 3 | Environment error (Docker missing, workspace missing) |

---

## Orchestrator Integration

### State machine changes

```python
TRANSITIONS = {
    ...
    "VERIFIED": {"OK": "RUNTIME_VERIFY"},
    "RUNTIME_VERIFY": {"OK": "DONE", "VERIFY_FAIL": "FAILED"},
    ...
}
```

### Script phase

```python
SCRIPT_PHASES = {
    ...
    "RUNTIME_VERIFY": {
        "script": ".claude/skills/jade-core-verification/scripts/runtime_verify.py",
        "args": ["--workspace", "_WORKSPACE_", "--artifacts", "_ARTIFACTS_", "--config", "_CONFIG_"],
    },
}
```

### Required artifact

```python
REQUIRED_ARTIFACTS = {
    ...
    "RUNTIME_VERIFY": ["07-runtime-verify.json"],
}
```

### Content validation

```python
ARTIFACT_CONTENT_RULES = {
    ...
    "07-runtime-verify.json": {
        "json_keys_required": ["results", "overall_pass", "total_consumers", "passed", "failed"],
        "json_len_match": [("results", "total_consumers")],
    },
}
```

### Empty playground behavior

If `consumer-playground/` contains no projects with `test-config.json`, `runtime_verify.py` writes:
```json
{"overall_pass": true, "total_consumers": 0, "passed": 0, "failed": 0, "results": []}
```
The orchestrator accepts this and transitions to DONE.

---

## Phase 1: VersionCheckAgent (Quick Win)

### Agent source

```java
import jade.core.Agent;

public class VersionCheckAgent extends Agent {
    protected void setup() {
        System.out.println("=== JADE Runtime Verification ===");
        System.out.println("JADE version: " + jade.core.Runtime.instance().getVersion());
        System.out.println("java.version: " + System.getProperty("java.version"));
        System.out.println("java.vm.version: " + System.getProperty("java.vm.version"));
        System.out.println("RUNTIME_CHECK_PASSED");
        doDelete();
        System.exit(0);
    }
}
```

### test-config.json

```json
{
  "name": "version-check",
  "description": "Verify JADE boots and reports Java runtime version",
  "docker_image": "frekele/ant:1.10.3-jdk8",
  "main_class": "jade.Boot",
  "boot_args": ["-container", "-agents", "check:VersionCheckAgent"],
  "expected_stdout_markers": ["JADE is ready", "RUNTIME_CHECK_PASSED"],
  "timeout_seconds": 60,
  "classpath_deps": ["src/jade/lib/jade.jar", "src/jade/lib/commons-codec/commons-codec-1.3.jar"]
}
```

### Expected output

```
JADE is ready
=== JADE Runtime Verification ===
JADE version: 4.6.0
java.version: 1.8.0_432
java.vm.version: 25.432-b01
RUNTIME_CHECK_PASSED
```

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Docker daemon not running | runtime_verify.py exits 3, orchestrator writes failure-summary, pipeline FAILED |
| jade.jar missing | runtime_verify.py exits 3 (workspace not built) |
| Consumer compilation fails | Record FAIL in results, continue to next consumer |
| Container exceeds timeout | Force-kill, record FAIL with timeout message |
| expected_stdout_markers not found | Record FAIL with stdout snippet showing what was actually printed |
| No consumer projects | Write pass (total_consumers=0), continue to DONE |

---

## Files to Create/Modify

| Action | File |
|--------|------|
| **Create** | `consumer-playground/version-check/VersionCheckAgent.java` |
| **Create** | `consumer-playground/version-check/test-config.json` |
| **Create** | `.claude/skills/jade-core-verification/scripts/runtime_verify.py` |
| **Modify** | `.claude/skills/jade-core-orchestrator/scripts/orchestrator.py` (TRANSITIONS, SCRIPT_PHASES, REQUIRED_ARTIFACTS, ARTIFACT_CONTENT_RULES, state handler) |
| **Modify** | `.claude/skills/jade-core-verification/SKILL.md` (document new script) |

---

## Acceptance Criteria

1. `runtime_verify.py` discovers consumer projects and loops over them
2. VersionCheckAgent compiles against workspace `jade.jar`
3. VersionCheckAgent boots JADE in Docker, prints runtime info, exits cleanly
4. `07-runtime-verify.json` records PASS for version-check with evidence
5. Orchestrator transitions RUNTIME_VERIFY → DONE on success
6. Empty `consumer-playground/` produces pass without halting
7. Any consumer failure produces VERIFY_FAIL → FAILED with actionable reports
