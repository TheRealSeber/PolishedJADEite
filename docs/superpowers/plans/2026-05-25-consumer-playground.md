# Consumer Playground Runtime Verification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add runtime verification to the JADE migration pipeline — boot JADE in Docker, run a VersionCheckAgent, assert it prints expected output.

**Architecture:** Three new files (VersionCheckAgent.java, test-config.json, runtime_verify.py) + orchestrator modifications (new RUNTIME_VERIFY state). Phase fires once after all rule batches complete, before DONE.

**Tech Stack:** Java 1.6 target, Docker (frekele/ant:1.10.3-jdk8), Python 3, JSON artifacts

**Spec:** `docs/superpowers/specs/2026-05-25-consumer-playground-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `consumer-playground/version-check/VersionCheckAgent.java` | JADE agent that prints runtime info and exits |
| Create | `consumer-playground/version-check/test-config.json` | Consumer test config (Docker image, markers, deps) |
| Create | `.claude/skills/jade-core-verification/scripts/runtime_verify.py` | Compile → Docker run → assert loop |
| Modify | `.claude/skills/jade-core-orchestrator/scripts/orchestrator.py` | New state, transitions, script phase, artifact rules |
| Modify | `.claude/skills/jade-core-verification/SKILL.md` | Document runtime_verify.py usage |

Boundaries: `runtime_verify.py` only knows about `consumer-playground/` and the workspace. It has no pipeline logic. The orchestrator owns orchestrating it.

---

### Task 1: Create consumer-playground directory and VersionCheckAgent

**Files:**
- Create: `consumer-playground/version-check/VersionCheckAgent.java`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p consumer-playground/version-check
```

- [ ] **Step 2: Write VersionCheckAgent.java**

Write `consumer-playground/version-check/VersionCheckAgent.java`:

```java
import jade.core.Agent;
import jade.core.Runtime;

public class VersionCheckAgent extends Agent {
    protected void setup() {
        System.out.println("=== JADE Runtime Verification ===");
        System.out.println("JADE version: " + Runtime.instance().getVersion());
        System.out.println("java.version: " + System.getProperty("java.version"));
        System.out.println("java.vm.version: " + System.getProperty("java.vm.version"));
        System.out.println("RUNTIME_CHECK_PASSED");
        doDelete();
    }
}
```

Note: Uses `doDelete()` to cleanly deregister. We do NOT call `System.exit(0)` here because that would kill the JVM before JADE finishes writing shutdown logs. Instead, the Docker container will exit naturally when the main thread finishes.

---

### Task 2: Create test-config.json

**Files:**
- Create: `consumer-playground/version-check/test-config.json`

- [ ] **Step 1: Write test-config.json**

Write `consumer-playground/version-check/test-config.json`:

```json
{
  "name": "version-check",
  "description": "Verify JADE boots and reports Java runtime version",
  "docker_image": "frekele/ant:1.10.3-jdk8",
  "main_class": "jade.Boot",
  "boot_args": ["-container", "-agents", "check:VersionCheckAgent"],
  "expected_stdout_markers": ["JADE is ready", "RUNTIME_CHECK_PASSED"],
  "timeout_seconds": 90,
  "classpath_deps": [
    "src/jade/lib/jade.jar",
    "src/jade/lib/commons-codec/commons-codec-1.3.jar"
  ]
}
```

- [ ] **Step 2: Verify JSON is valid**

```bash
python -c "import json; json.load(open('consumer-playground/version-check/test-config.json')); print('OK')"
```

Expected: `OK`

---

### Task 3: Create runtime_verify.py

**Files:**
- Create: `.claude/skills/jade-core-verification/scripts/runtime_verify.py`

- [ ] **Step 1: Write runtime_verify.py**

Write `.claude/skills/jade-core-verification/scripts/runtime_verify.py` with the following structure:

```python
#!/usr/bin/env python3
"""Runtime verification for JADE migration consumer playground.

Discovers consumer projects in consumer-playground/, injects jade.jar,
compiles, runs in Docker, asserts expected output markers.

Output: artifacts/07-runtime-verify.json
Exit: 0 = all pass, 2 = failures, 3 = env error
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------
PLAYGROUND_DIR = pathlib.Path("consumer-playground")
TIMEOUT_BUFFER = 15  # extra seconds beyond test-config timeout for docker pull etc.


def iso_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def read_json(path: pathlib.Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: pathlib.Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    tmp.replace(path)


def discover_consumers() -> List[Tuple[pathlib.Path, Dict[str, Any]]]:
    """Find all consumer projects with valid test-config.json."""
    consumers: List[Tuple[pathlib.Path, Dict[str, Any]]] = []
    if not PLAYGROUND_DIR.exists():
        return consumers
    for candidate in sorted(PLAYGROUND_DIR.iterdir()):
        if not candidate.is_dir():
            continue
        config_path = candidate / "test-config.json"
        if not config_path.exists():
            continue
        try:
            cfg = read_json(config_path)
            consumers.append((candidate, cfg))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"WARNING: skipping {candidate.name}: invalid test-config.json ({exc})", file=sys.stderr)
    return consumers


def verify_deps(workspace: pathlib.Path, cfg: Dict[str, Any]) -> List[str]:
    """Check that all classpath_deps exist. Returns list of missing paths."""
    missing: List[str] = []
    for dep in cfg.get("classpath_deps", []):
        full = workspace / dep
        if not full.exists():
            missing.append(dep)
    return missing


def compile_consumer(
    project_dir: pathlib.Path,
    workspace: pathlib.Path,
    cfg: Dict[str, Any],
    build_dir: pathlib.Path,
) -> Tuple[bool, str]:
    """Compile consumer .java files against workspace jars. Returns (ok, output)."""
    java_files = sorted(project_dir.glob("*.java"))
    if not java_files:
        return False, "No .java files found in project directory"

    # Build classpath from workspace deps
    cp_parts: List[str] = []
    for dep in cfg.get("classpath_deps", []):
        full = workspace / dep
        cp_parts.append(str(full.resolve()))
    classpath = os.pathsep.join(cp_parts)

    javac = shutil.which("javac")
    if not javac:
        javac = "javac"  # hope it's on PATH

    cmd = [javac, "-cp", classpath, "-d", str(build_dir)]
    cmd.extend(str(f.resolve()) for f in java_files)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "JAVA_TOOL_OPTIONS": ""},
        )
        output = (proc.stdout + proc.stderr).strip()
        return proc.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Compilation timed out after 120s"
    except OSError as exc:
        return False, f"Failed to run javac: {exc}"


def run_in_docker(
    workspace: pathlib.Path,
    build_dir: pathlib.Path,
    cfg: Dict[str, Any],
) -> Tuple[int, str, str]:
    """Run consumer in Docker. Returns (exit_code, stdout, stderr)."""
    docker_image = cfg["docker_image"]
    main_class = cfg["main_class"]
    timeout = cfg.get("timeout_seconds", 60) + TIMEOUT_BUFFER

    # Build container classpath
    cp_parts: List[str] = ["/playground"]
    for dep in cfg.get("classpath_deps", []):
        # Map workspace-relative path to /ws/ prefix in container
        cp_parts.append(f"/ws/{dep}")
    classpath = ":".join(cp_parts)

    cmd = [
        "docker", "run", "--rm",
        "-v", f"{workspace.resolve()}:/ws",
        "-v", f"{build_dir.resolve()}:/playground",
        "-w", "/playground",
        docker_image,
        "java", "-cp", classpath, main_class,
    ]
    cmd.extend(cfg.get("boot_args", []))

    print(f"  $ {' '.join(cmd)}", file=sys.stderr)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "MSYS_NO_PATHCONV": "1"},
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Container timed out after {timeout}s"
    except OSError as exc:
        return -2, "", f"Failed to run docker: {exc}"


def test_consumer(
    project_dir: pathlib.Path,
    workspace: pathlib.Path,
    cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """Run one consumer test. Returns result dict."""
    name = cfg["name"]
    result: Dict[str, Any] = {
        "project": name,
        "status": "PENDING",
        "duration_seconds": 0.0,
        "jade_booted": False,
        "stdout_snippet": "",
        "error": None,
    }

    t0 = time.monotonic()

    print(f"\n=== Consumer: {name} ===")

    # Check deps
    missing = verify_deps(workspace, cfg)
    if missing:
        result["status"] = "FAIL"
        result["error"] = f"Missing dependencies: {', '.join(missing)}"
        result["duration_seconds"] = round(time.monotonic() - t0, 1)
        return result

    # Compile
    with tempfile.TemporaryDirectory(prefix=f"jade-rt-{name}-") as tmp:
        build_dir = pathlib.Path(tmp)
        ok, output = compile_consumer(project_dir, workspace, cfg, build_dir)
        if not ok:
            result["status"] = "FAIL"
            result["error"] = f"Compilation failed"
            result["stdout_snippet"] = output[:2000]
            result["duration_seconds"] = round(time.monotonic() - t0, 1)
            return result

        # Run in Docker
        rc, stdout, stderr = run_in_docker(workspace, build_dir, cfg)
        combined = stdout + "\n" + stderr

        result["duration_seconds"] = round(time.monotonic() - t0, 1)
        result["stdout_snippet"] = combined[:2000]

        # Check expected markers
        markers = cfg.get("expected_stdout_markers", [])
        missing_markers = [m for m in markers if m not in combined]

        if missing_markers:
            result["status"] = "FAIL"
            result["error"] = f"Missing expected markers: {missing_markers}"
        else:
            result["status"] = "PASS"
            result["jade_booted"] = "JADE is ready" in combined

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="JADE Runtime Verification")
    parser.add_argument("--workspace", required=True, help="Path to migrated workspace")
    parser.add_argument("--artifacts", required=True, help="Path to artifacts directory")
    parser.add_argument("--config", required=True, help="Path to 00-run-config.json")
    args = parser.parse_args()

    workspace = pathlib.Path(args.workspace)
    artifacts = pathlib.Path(args.artifacts)

    # Read run config
    try:
        run_cfg = read_json(pathlib.Path(args.config))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: cannot read config: {exc}", file=sys.stderr)
        return 3

    run_id = run_cfg.get("run_id", "unknown")

    # Verify env
    if shutil.which("docker") is None:
        print("ERROR: docker not found on PATH", file=sys.stderr)
        return 3
    # Check daemon is reachable
    try:
        subprocess.run(
            ["docker", "info"], capture_output=True, timeout=10, check=False
        )
    except (subprocess.TimeoutExpired, OSError):
        print("ERROR: docker daemon not running or unreachable", file=sys.stderr)
        return 3
    if shutil.which("java") is None and shutil.which("javac") is None:
        print("WARNING: javac not found on PATH, will rely on Docker for compilation", file=sys.stderr)

    # Discover consumers
    consumers = discover_consumers()
    if not consumers:
        result = {
            "run_id": run_id,
            "generated_at": iso_now(),
            "overall_pass": True,
            "total_consumers": 0,
            "passed": 0,
            "failed": 0,
            "results": [],
        }
        write_json(artifacts / "07-runtime-verify.json", result)
        print("No consumer projects found — pass")
        return 0

    # Test each consumer
    results: List[Dict[str, Any]] = []
    for project_dir, cfg in consumers:
        result = test_consumer(project_dir, workspace, cfg)
        results.append(result)
        status_icon = "PASS" if result["status"] == "PASS" else "FAIL"
        print(f"  [{status_icon}] {result['project']} ({result['duration_seconds']}s)")

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")

    output = {
        "run_id": run_id,
        "generated_at": iso_now(),
        "overall_pass": failed == 0,
        "total_consumers": len(results),
        "passed": passed,
        "failed": failed,
        "results": results,
    }
    write_json(artifacts / "07-runtime-verify.json", output)

    if failed > 0:
        print(f"\n{failed} consumer(s) FAILED", file=sys.stderr)
        return 2

    print(f"\nAll {passed} consumer(s) PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Verify script is valid Python**

```bash
python -c "import importlib; importlib.import_module('jade_core_verification.scripts.runtime_verify')" 2>&1 || python -m py_compile .claude/skills/jade-core-verification/scripts/runtime_verify.py
```

Expected: No syntax errors

---

### Task 4: Verify runtime_verify.py works standalone

**Files:**
- No files modified — verification only

- [ ] **Step 1: Run runtime_verify.py against the existing migrated workspace**

```bash
set JAVA_HOME=C:\Program Files\Java\jdk-17 && python .claude/skills/jade-core-verification/scripts/runtime_verify.py --workspace migration-runs/jade-1.5-to-1.6/workspace --artifacts migration-runs/jade-1.5-to-1.6/artifacts --config migration-runs/jade-1.5-to-1.6/artifacts/00-run-config.json
```

Expected: 
- Compiles VersionCheckAgent.java
- Docker container boots JADE
- stdout contains "JADE is ready" and "RUNTIME_CHECK_PASSED"
- Writes `07-runtime-verify.json` with status PASS

- [ ] **Step 2: Verify 07-runtime-verify.json**

```bash
python -c "import json; d=json.load(open('migration-runs/jade-1.5-to-1.6/artifacts/07-runtime-verify.json')); print(d['overall_pass'], d['total_consumers'], d['passed'], d['failed'])"
```

Expected: `True 1 1 0`

- [ ] **Step 3: Commit VersionCheckAgent and runtime_verify.py**

```bash
git add consumer-playground/ .claude/skills/jade-core-verification/scripts/runtime_verify.py migration-runs/jade-1.5-to-1.6/artifacts/07-runtime-verify.json
git commit -m "feat: add consumer playground runtime verification with VersionCheckAgent"
```

---

### Task 5: Modify orchestrator.py for RUNTIME_VERIFY phase

**Files:**
- Modify: `.claude/skills/jade-core-orchestrator/scripts/orchestrator.py`

- [ ] **Step 1: Add RUNTIME_VERIFY to TRANSITIONS**

Read the TRANSITIONS dict and add the new state. Current VERIFIED entry:
```python
"VERIFIED": {"OK": "DONE"},
```

Replace with:
```python
"VERIFIED": {"OK": "RUNTIME_VERIFY"},
"RUNTIME_VERIFY": {"OK": "DONE", "VERIFY_FAIL": "FAILED"},
```

- [ ] **Step 2: Add RUNTIME_VERIFY to REQUIRED_ARTIFACTS**

Add to the REQUIRED_ARTIFACTS dict:
```python
"RUNTIME_VERIFY": ["07-runtime-verify.json"],
```

- [ ] **Step 3: Add validation rules for 07-runtime-verify.json**

Add to ARTIFACT_CONTENT_RULES dict:
```python
"07-runtime-verify.json": {
    "json_keys_required": ["results", "overall_pass", "total_consumers", "passed", "failed"],
    "json_len_match": [("results", "total_consumers")],
},
```

- [ ] **Step 4: Add RUNTIME_VERIFY to SCRIPT_PHASES**

Add to the SCRIPT_PHASES dict:
```python
"RUNTIME_VERIFY": {
    "script": ".claude/skills/jade-core-verification/scripts/runtime_verify.py",
    "args": ["--workspace", "_WORKSPACE_", "--artifacts", "_ARTIFACTS_", "--config", "_CONFIG_"],
},
```

- [ ] **Step 5: Add handler in the state machine loop**

In the `while state["state"] not in TERMINAL_STATES` loop, add handling for RUNTIME_VERIFY. After the `elif current == "VERIFIED":` block (around line 913-915), add:

```python
elif current == "RUNTIME_VERIFY":
    if args.run and current in SCRIPT_PHASES:
        script_outcome = _run_script_phase(current, cfg)
        if script_outcome != "OK":
            outcome = script_outcome
        else:
            outcome = check_gate_artifacts(current, artifacts, state)
    else:
        outcome = check_gate_artifacts(current, artifacts, state)
    
    # Interpret the result: overall_pass=false means VERIFY_FAIL
    if outcome == "OK":
        rv_path = artifacts / "07-runtime-verify.json"
        try:
            rv = read_json(rv_path)
            if not rv.get("overall_pass", False):
                outcome = "VERIFY_FAIL"
        except (json.JSONDecodeError, OSError):
            outcome = "ARTIFACT_MISSING"
```

- [ ] **Step 6: Verify orchestrator.py is valid Python**

```bash
python -m py_compile .claude/skills/jade-core-orchestrator/scripts/orchestrator.py
```

Expected: No syntax errors

- [ ] **Step 7: Commit orchestrator changes**

```bash
git add .claude/skills/jade-core-orchestrator/scripts/orchestrator.py
git commit -m "feat: add RUNTIME_VERIFY phase to orchestrator for consumer playground"
```

---

### Task 6: Run the full pipeline end-to-end

**Files:**
- No files modified — verification only

- [ ] **Step 1: Reset pipeline state and run full migration + runtime verify**

```bash
del /f /q migration-runs\jade-1.5-to-1.6\artifacts\00-run-state.json 2>nul & del /f /q migration-runs\jade-1.5-to-1.6\artifacts\failure-summary.json 2>nul & del /f /q migration-runs\jade-1.5-to-1.6\artifacts\07-runtime-verify.json 2>nul
set JAVA_HOME=C:\Program Files\Java\jdk-17 && python .claude/skills/jade-core-orchestrator/scripts/orchestrator.py --config migration-runs/jade-1.5-to-1.6/artifacts/00-run-config.json --run
```

Expected: Pipeline completes with state DONE, and the RUNTIME_VERIFY phase:
- Compiles and runs VersionCheckAgent in Docker
- Reports PASS
- Writes `07-runtime-verify.json` with `overall_pass: true`

- [ ] **Step 2: Verify pipeline output**

```bash
python -c "import json; d=json.load(open('migration-runs/jade-1.5-to-1.6/artifacts/00-run-state.json')); print('State:', d['state'])"
python -c "import json; d=json.load(open('migration-runs/jade-1.5-to-1.6/artifacts/07-runtime-verify.json')); print('Runtime:', d['overall_pass'])"
```

Expected:
```
State: DONE
Runtime: True
```

- [ ] **Step 3: Show the runtime proof — VersionCheckAgent Docker output**

Run the VersionCheckAgent directly to see the raw Docker container output:

```bash
python -c "
import json
d = json.load(open('migration-runs/jade-1.5-to-1.6/artifacts/07-runtime-verify.json'))
for r in d['results']:
    print(f'--- {r[\"project\"]} ---')
    print(r['stdout_snippet'])
"
```

- [ ] **Step 4: Verify empty playground behavior (no consumers = pass)**

Temporarily rename consumer-playground and verify the script handles empty playground gracefully:

```bash
ren consumer-playground consumer-playground.bak && set JAVA_HOME=C:\Program Files\Java\jdk-17 && python .claude/skills/jade-core-verification/scripts/runtime_verify.py --workspace migration-runs/jade-1.5-to-1.6/workspace --artifacts migration-runs/jade-1.5-to-1.6/artifacts --config migration-runs/jade-1.5-to-1.6/artifacts/00-run-config.json & ren consumer-playground.bak consumer-playground
```

Expected: "No consumer projects found — pass", exit 0

- [ ] **Step 5: Final commit**

```bash
git add .
git commit -m "feat: complete consumer playground runtime verification pipeline"
```

---

### Task 7: Update jade-core-verification SKILL.md

**Files:**
- Modify: `.claude/skills/jade-core-verification/SKILL.md`

- [ ] **Step 1: Add runtime_verify.py documentation to SKILL.md**

Read the existing `.claude/skills/jade-core-verification/SKILL.md`. Below the existing "Scripts" or "Tools" section (or at the end if none exists), add a new section:

```markdown
## runtime_verify.py — Consumer Playground Runtime Tests

**Purpose:** Compiles consumer projects from `consumer-playground/`, injects migrated `jade.jar`, runs each in Docker, and asserts expected output markers.

**Invocation:**
```
python .claude/skills/jade-core-verification/scripts/runtime_verify.py \
  --workspace <migrated_workspace> \
  --artifacts <artifacts_dir> \
  --config <00-run-config.json>
```

**Consumer projects:** Stored in `consumer-playground/<name>/` with:
- `*.java` — JADE agent source files
- `test-config.json` — docker image, boot args, expected markers, classpath deps

**Output:** `artifacts/07-runtime-verify.json` — per-consumer PASS/FAIL with stdout evidence.

**Exit codes:** 0 = all pass, 2 = failures, 3 = env error
```

- [ ] **Step 2: Commit SKILL.md update**

```bash
git add .claude/skills/jade-core-verification/SKILL.md
git commit -m "docs: add runtime_verify.py to verification skill documentation"
```
