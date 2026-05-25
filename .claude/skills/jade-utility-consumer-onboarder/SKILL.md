---
name: jade-utility-consumer-onboarder
description: >-
  Onboards external JADE projects into the consumer playground. Extracts a ZIP
  archive of a JADE project, copies Java sources into consumer-playground/<name>/,
  and generates a test-config.json for runtime verification.
when_to_use: >-
  Use when the user says "onboard a project", "ingest zip", "add consumer project",
  "import JADE project into playground", or provides a ZIP file to integrate.
arguments: [zip-file, project-name, agent-class]
argument-hint: "hw-jade.zip my-project MyAgentClass"
allowed-tools: Bash(python *) Read Write Glob
paths: "**/*.zip" "consumer-playground/**"
disable-model-invocation: true
---

# JADE Utility — Consumer Onboarder

## Objective

Automate onboarding of external JADE projects into the consumer playground.
Takes a ZIP archive, extracts Java sources (preserving package structure),
and generates a boilerplate `test-config.json`.

## Usage

```
python .claude/skills/jade-utility-consumer-onboarder/scripts/onboard.py \
  --zip-file <path-to-zip> \
  --project-name <project-directory-name> \
  [--agent-class <agent-name:fully.qualified.Class>]
```

## What it does

1. Extracts the ZIP to a temporary directory
2. Detects the Java source root (Maven: `src/main/java/`, Gradle: `src/main/java/`, plain: root)
3. Copies only `.java` files into `consumer-playground/<project-name>/`, preserving package subdirectories
4. Skips `.class` files, test directories, IDE configs (`.idea/`, `.mvn/`, `target/`)
5. Generates a `test-config.json` with:
   - `docker_image`: `"${TARGET_DOCKER_IMAGE}"` (dynamic placeholder)
   - `classpath_deps`: standard JADE workspace jars
   - `boot_args`: agent class if provided, otherwise `["-agents", "REPLACE_ME:YourAgentClass"]`
   - `expected_stdout_markers`: `["is ready"]`
   - `timeout_seconds`: 90

## Post-onboarding

After running the script, manually refine `test-config.json`:
1. Set the correct `boot_args` agent class
2. Add project-specific `expected_stdout_markers` from the agent's `System.out.println` output
3. Run `runtime_verify.py` to confirm the project compiles and boots against the migrated JADE workspace

## TestRunnerAgent Pattern

JADE's `jade.Boot -agents` passes **zero arguments** to agents. If a consumer project's agents need constructor arguments (like `CustomerAgent` needing a `TripRequest`), they will crash with `NullPointerException` or `ArrayIndexOutOfBoundsException`.

**Solution:** Create a `TestRunnerAgent.java` in the consumer project directory that:
- Extends `jade.core.Agent`
- Requires no constructor arguments
- Creates mock data programmatically (same objects the project's `Main.java` would create)
- Starts the target agent(s) via `getContainerController().createNewAgent()`
- Waits for agent behaviours to complete
- Prints a unique success marker (e.g., `HW_JADE_PASSED`) or failure marker (e.g., `HW_JADE_FAILED`)
- Calls `System.exit(0)` for **graceful shutdown**

Update `boot_args` to start `TestRunnerAgent` instead of the original agent:
```json
"boot_args": ["-agents", "runner:pw.agents.TestRunnerAgent"],
"expected_stdout_markers": ["HW_JADE_PASSED"]
```

## Verification Hardening

`runtime_verify.py` performs **reverse assertion** — it scans output for failure patterns regardless of whether expected markers are present. If any of these appear, the test is **FAIL**:

| Pattern | Meaning |
|---------|---------|
| `NullPointerException` | Agent crashed with NPE |
| `ArrayIndexOutOfBoundsException` | Missing arguments |
| `Exception` | Any unhandled exception |
| `SEVERE:` | JADE internal error |
| Container timed out | Docker hung (always FAIL) |

## Graceful Shutdown

Consumer projects must shut down the JADE platform cleanly. Without it, the Docker container hangs until timeout. `TestRunnerAgent` handles this by calling `System.exit(0)` after test completion. For agents that naturally complete (like VersionCheckAgent), a threaded `System.exit(0)` after a delay suffices.
