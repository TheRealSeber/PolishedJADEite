# Consumer Onboarder Utility — Design Spec

**Date:** 2026-05-25
**Status:** Approved

## Purpose

Automate onboarding of external JADE projects into the consumer playground. Takes a ZIP archive, extracts Java sources, generates `test-config.json`.

## Components

| Component | Path |
|-----------|------|
| Skill definition | `.claude/skills/jade-utility-consumer-onboarder/SKILL.md` |
| Onboarder script | `.claude/skills/jade-utility-consumer-onboarder/scripts/onboard.py` |
| Runtime fix | `.claude/skills/jade-core-verification/scripts/runtime_verify.py` (glob fix) |

## onboard.py

**Args:** `--zip-file`, `--project-name`, `--agent-class` (optional)

**Flow:**
1. Extract ZIP to temp dir
2. Find Java source root (Maven: `src/main/java/`, plain: root)
3. Copy only `.java` files into `consumer-playground/<name>/`
4. Skip `.class`, test dirs, IDE dirs
5. Generate `test-config.json`

**test-config.json defaults:**

| Field | Default |
|-------|---------|
| docker_image | `${TARGET_DOCKER_IMAGE}` |
| classpath_deps | `["src/jade/lib/jade.jar", "src/jade/lib/commons-codec/commons-codec-1.3.jar"]` |
| boot_args | `["-agents", "<agent>"]` or placeholder |
| expected_stdout_markers | `["is ready"]` |
| timeout_seconds | 90 |
