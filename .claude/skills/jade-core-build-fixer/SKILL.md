---
name: jade-core-build-fixer
description: >-
  Build prerequisite gate for JADE migration pipeline. Analyzes build files
  (build.xml/pom.xml/gradle), checks dependency/plugin compatibility for the
  target Java version, applies safe minimal build/dependency updates, and
  verifies the build. This is a GATE — no source-code migration may proceed
  until the build passes at the target version.
when_to_use: >-
  Use when the orchestrator enters BUILD_GATE_READY phase, when the user says
  "fix build system", "check build compatibility", "update build for java X",
  "prepare build for migration", or when 03-build-audit.json is missing/FAILED.
arguments: []
argument-hint: ""
disable-model-invocation: false
allowed-tools: Bash(docker *) Bash(python *) Read Write
env: {}
paths: "**/build.xml" "**/pom.xml" "**/build.gradle"
---

# JADE Build System Fixer — Build Prerequisite Gate

## Prerequisites
**Docker must be installed and running.** All builds execute in ephemeral
containers — no legacy JDK or build tools required on the host.

## Objective
Act as the **BUILD_GATE_READY** phase gate. Analyze the project's build system for
compatibility with the target Java version, apply safe minimal updates, and verify
the build passes. No source-code transformation may proceed until this gate is
satisfied.

## Gating Policy

```
BUILD FAILS → STOP → NO SOURCE MIGRATION
BUILD PASSES → PROCEED → NEXT GATE
```

This skill is the **prerequisite gate** before any source-level migration work.
If the build cannot be made to pass at the target version, the migration pipeline
halts with `BUILD_GATE_FAILED`.

---

## Required Input

| Artifact | Description |
|----------|-------------|
| `artifacts/00-run-config.json` | Run configuration with `source_version`, `target_version`, `workspace_path` |
| `config/docker-images.json` | Central Docker image registry (`java-8`, `java-11`, `java-17`) |
| Workspace build files | `build.xml`, `pom.xml`, or `build.gradle` in the workspace |

## Produced Output

| Artifact | Description |
|----------|-------------|
| `artifacts/03-build-audit.json` | Build system audit result (`status: OK` or `FAILED`) |
| `artifacts/03-build-fixes-plan.json` | List of fixes applied/needed |
| `artifacts/03-build-verify.log` | Raw build output (stdout + stderr) |

---

## Workflow

### Step 1: Run the audit script

```bash
python .claude/skills/jade-build-system-fixer/scripts/build_audit.py \
  --config "migration-runs/<run_id>/artifacts/00-run-config.json"
```

The script performs all detection, analysis, fix-proposal, fix-application, and
verification. It writes the three output artifacts directly.

### Step 2: Interpret results

Read `artifacts/03-build-audit.json`. If `status` is `OK`, the build gate passes.
If `status` is `FAILED`, read `artifacts/03-build-fixes-plan.json` and
`artifacts/03-build-verify.log` for the failure reason.

### Step 3: Gate decision

| audit status | action |
|-------------|--------|
| `OK` | Proceed to next migration phase (SCAN_READY / source transformations) |
| `FAILED` | Investigate failures; manual intervention may be required |
| `NEEDS_MANUAL` | Fixes were identified but could not be auto-applied; review fixes-plan |

---

## Build System Detection

The script auto-detects the build system:

| File | System | Compile command |
|------|--------|----------------|
| `build.xml` | Apache Ant | `ant <target>` (default `jade`) |
| `pom.xml` | Apache Maven | `mvn compile` |
| `build.gradle` / `build.gradle.kts` | Gradle | `gradle compileJava` |

### Ant-specific checks (JADE's build system)

| Check | Pattern |
|-------|---------|
| `source` / `target` attributes in `<javac>` | Must match `target_version` from config |
| `jdkversion` in `<javacc>` | Must be compatible with target JDK |
| Dependency JARs in classpath | Check compatibility with target version |
| Missing/outdated lib dirs | Flag missing required libraries |
| `build.properties` | Verify properties are valid for target |

### Maven-specific checks

| Check | Pattern |
|-------|---------|
| `maven.compiler.source` / `maven.compiler.target` | Must match target version |
| `maven-compiler-plugin` version | Must be compatible with target JDK |
| Dependency versions | Check for removed/deprecated APIs |

### Gradle-specific checks

| Check | Pattern |
|-------|---------|
| `sourceCompatibility` / `targetCompatibility` | Must match target version |
| Gradle wrapper version | Must support target JDK |
| Plugin versions | Must be compatible |

## Dependency Compatibility (Java 11+ Readiness)

For target versions `11` and above, the build auditor MUST run a dependency compatibility scan
before finalizing gate status.

Required behavior:

1. Parse declared dependencies from `pom.xml` (and Ant/Gradle dependency declarations where present)
2. Detect known Java 11+ removals (minimum baseline):
   - CORBA (`com.sun.corba:*`, `org.omg:*`)
   - JAXB APIs below Java 11 compatible levels (e.g., `javax.xml.bind:jaxb-api < 2.3`)
3. Emit findings to `03-build-audit.json` and `03-build-fixes-plan.json` with explicit severity (`BLOCKER`/`WARNING`)
4. Include actionable replacement or upgrade guidance in fixes-plan (`recommended_version`, migration notes)

This scan is a proactive dependency-hell defense. It does not auto-upgrade dependencies silently.

## Docker Infrastructure

All Docker images used by this skill MUST be resolved from `config/docker-images.json`.
Hardcoded image strings are forbidden in skill scripts.

Resolution policy:

1. Load registry keys: `java-8`, `java-11`, `java-17`
2. Map `target_version` from run config to the proper registry key
3. Record the resolved image in `03-build-audit.json` for traceability

If the registry file is missing or malformed, the skill fails with configuration error; it must not fallback to hardcoded defaults.

---

## Fix Categories

### SAFE (auto-applied)

These fixes are applied automatically — they are deterministic and reversible:

1. **Compiler source/target flags** — update `source="1.X"` / `target="1.X"` to target version
2. **Javacc jdkversion** — update to match target if too low
3. **Missing compile-target property** — add `maven.compiler.target` if only `source` exists

### NEEDS_REVIEW (proposed, not auto-applied)

These require human judgment:

1. **Dependency version bumps** — any library JAR version change
2. **Plugin version upgrades** — Maven plugins, Gradle plugins
3. **Removed API dependencies** — libraries whose entire API was removed in target JDK
4. **Build property changes** — non-standard properties that may affect behavior

### BLOCKED (cannot fix)

These require source-level changes (which happen after this gate):

1. `javax.*` → `jakarta.*` migration
2. Removed language features used in source
3. Deprecated API replacements

---

## Example: JADE 1.5 → 1.6 Ant fix

**Before** (`build.xml`):
```xml
<javac ... source="1.5" target="1.5" ... />
```

**After** (auto-applied):
```xml
<javac ... source="1.6" target="1.6" ... />
```

This is the minimal safe fix for the JADE 1.5→1.6 migration.

---

## Constraints

1. Never modify source files — this is a **build-only** gate
2. Never delete files — only update build configuration properties
3. Minimum viable change — only change what is necessary for build to pass
4. All fixes must be recorded in `03-build-fixes-plan.json`
5. Raw build output must be captured in `03-build-verify.log` verbatim
6. The script must exit 0 for OK/FIXED, non-zero for FAILED
7. The script must be idempotent — running twice produces same artifacts

---

## Exit Criteria

| Criterion | Indicator |
|-----------|-----------|
| Build system detected | Recorded in audit artifact |
| All compatibility checks run | Listed in fixes-plan |
| Safe fixes applied | Recorded in fixes-plan with `applied: true` |
| Build verified at target | Build output captured in verify log |
| Gate decision made | `status` field in audit artifact is definitive |

---

## Failure Recovery

If `status: FAILED`:
1. Read `03-build-verify.log` for the exact error
2. Read `03-build-fixes-plan.json` for attempted fixes
3. For `NEEDS_REVIEW` items — apply manually, re-run script
4. For `BLOCKED` items — these need source migration to proceed, which means the
   current gate cannot be satisfied until upstream prerequisites are met
