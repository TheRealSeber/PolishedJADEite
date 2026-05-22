# Test Suite Expansion — 6 Post-State-Machine Gaps

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close 6 test gaps introduced by the state machine rewrite, retry router upgrade, and workspace isolation changes — ensuring every new state, artifact, and validation gate has test coverage.

**Architecture:** All tests use the sample artifacts harness under `migration-runs/sample/artifacts/`. No new test dependencies. Each gap is one task — independent, committable, 9-15 lines of test code.

**Tech Stack:** Python 3, pytest, JSON artifacts.

---

### Task 1: Add new state machine states (Gap A)

**Files:**
- Modify: `tests/test_artifact_contracts.py:18-37`

Add `RULE_RETRY` and `RULE_ESCALATE` to the valid state set in `test_run_state_has_required_keys`.

```python
def test_run_state_has_required_keys(artifacts_dir):
    ...
    assert state["state"] in {
        "INIT", "WORKSPACE_READY", "MANIFEST_READY", "TOOLING_SCOUT_READY",
        "BUILD_GATE_READY", "SCAN_READY", "RULE_BATCH_LOOP", "RULE_RETRY",
        "RULE_ESCALATE", "VERIFIED", "DONE", "FAILED",
        "AWAITING_SOURCE_INPUT",
    }
```

- [ ] Edit + run `python -m pytest tests/test_artifact_contracts.py::test_run_state_has_required_keys -v` → PASS
- [ ] Commit: `test: add RULE_RETRY and RULE_ESCALATE to valid orchestrator states`

### Task 2: Add new manifest fields (Gap B)

**Files:**
- Modify: `tests/test_artifact_contracts.py:40-54`

Add `fix_strategy`, `evidence_ref`, `evidence_hash`, `confidence`, `category` checks to `test_manifest_has_valid_rules`. Add `match_pattern` validation since the dispatcher relies on it.

```python
def test_manifest_has_valid_rules(artifacts_dir):
    ...
    for rule in rules:
        assert "id" in rule
        assert "name" in rule
        assert "severity" in rule
        assert "patterns" in rule
        assert "fix_strategy" in rule
        assert rule["fix_strategy"].startswith("recipe:")
        assert "evidence_ref" in rule
        assert "evidence_hash" in rule
        assert isinstance(rule.get("confidence", 0), (int, float))
        assert rule.get("confidence", 0) >= 0.7
        assert "match_pattern" in rule
        for pattern in rule["patterns"]:
            assert "pattern" in pattern
            assert "target_extensions" in pattern
```

- [ ] Edit + run `python -m pytest tests/test_artifact_contracts.py::test_manifest_has_valid_rules -v` → PASS
- [ ] Commit: `test: validate fix_strategy, evidence_ref, confidence in manifest schema test`

### Task 3: Test PROGRESS.md output (Gap C)

**Files:**
- Modify: `tests/test_orchestrator_integration.py` — add new test

The orchestrator writes `PROGRESS.md` on every state transition. Verify it exists, has header rows, and contains the run_id from config.

```python
def test_orchestrator_produces_progress_md(artifacts_dir):
    progress_path = artifacts_dir / "PROGRESS.md"
    if not progress_path.exists():
        pytest.skip(f"{progress_path} not found (orchestrator hasn't run yet)")

    content = progress_path.read_text(encoding="utf-8")
    assert "Migration Progress" in content
    assert "| Phase | Status |" in content
    assert len(content.splitlines()) >= 5, "PROGRESS.md should have header + at least 3 rows"
```

- [ ] Edit + run `python -m pytest tests/test_orchestrator_integration.py::test_orchestrator_produces_progress_md -v` → PASS
- [ ] Commit: `test: add PROGRESS.md output verification`

### Task 4: Test ACTION_REQUIRED.md output (Gap D)

**Files:**
- Create: `tests/test_retry_router.py`

A standalone test exercising the retry router's `write_action_required()` function directly (import it, pass a synthetic EscalationEntry, verify the file is written and contains expected sections).

```python
import pathlib, json
from .claude.skills.jade_core_retry_router.scripts.retry_router import (
    write_action_required, EscalationEntry, FixResult,
)

def test_write_action_required(tmp_path):
    escalated = [
        EscalationEntry(
            rule_id="TEST_RULE", total_attempts=3,
            final_failure="BUILD_ERROR: compilation failed",
            escalated_at="2026-01-01T00:00:00Z",
        )
    ]
    fix_results = [
        FixResult(
            rule_id="TEST_RULE", attempt=3, status="FAILED",
            files_modified=["src/Test.java"],
            error="javac: cannot find symbol\n  symbol: class Vector",
        )
    ]
    write_action_required(tmp_path, escalated, fix_results)

    path = tmp_path / "ACTION_REQUIRED.md"
    assert path.exists()
    content = path.read_text()
    assert "Action Required" in content
    assert "TEST_RULE" in content
    assert "compilation failed" in content
    assert "src/Test.java" in content
    assert "Suggested actions" in content
```

Since the retry_router module path contains dots that Python can't import, use subprocess instead:

```python
import subprocess, sys, json, pathlib

RETRY_SCRIPT = pathlib.Path(".claude/skills/jade-core-retry-router/scripts/retry_router.py")

def test_retry_router_writes_action_required(tmp_path):
    # Create fake fix results and build log to trigger an escalation
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    
    # Write a fix result with FAILED status
    (artifacts / "06-fix-result-TEST.json").write_text(json.dumps({
        "rule_id": "TEST_RULE", "attempt": 3, "status": "FAILED",
        "files_modified": ["src/Test.java"],
        "error": "javac: cannot find symbol: class Vector",
    }))
    
    # Write a build log with matching errors
    (artifacts / "07-build.log").write_text("src/Test.java:10: error: cannot find symbol: class Vector")
    
    result = subprocess.run(
        [sys.executable, str(RETRY_SCRIPT), "--artifacts", str(artifacts), "--max-retries", "3"],
        capture_output=True, text=True,
    )
    
    action_path = artifacts / "ACTION_REQUIRED.md"
    assert action_path.exists(), f"Retry router did not produce ACTION_REQUIRED.md\n{result.stdout}\n{result.stderr}"
    content = action_path.read_text()
    assert "TEST_RULE" in content
    assert "Suggested actions" in content
```

- [ ] Create `tests/test_retry_router.py` with the above
- [ ] Run `python -m pytest tests/test_retry_router.py -v` → 1 passed
- [ ] Run `python -m pytest tests/ -v` → verify no regressions
- [ ] Commit: `test: add ACTION_REQUIRED.md output verification for retry router`

### Task 5: Test transition table integrity (Gap E)

**Files:**
- Modify: `tests/test_orchestrator_integration.py` — add new test

Import the `TRANSITIONS` dict from `orchestrator.py` and verify every state has valid transitions, no dead-end states, and every `next_state` is a valid state.

```python
import importlib.util, sys

def test_transition_table_integrity():
    # Load TRANSITIONS from orchestrator.py without executing main()
    orch_path = pathlib.Path(".claude/skills/jade-core-orchestrator/scripts/orchestrator.py")
    spec = importlib.util.spec_from_file_location("orchestrator", orch_path)
    mod = importlib.util.module_from_spec(spec)
    # Can't import directly due to __future__ and side effects.
    # Use exec to get just the TRANSITIONS dict.
    source = orch_path.read_text(encoding="utf-8")
    ns = {}
    exec(compile(source, str(orch_path), "exec"), ns)
    transitions = ns["TRANSITIONS"]
    valid_states = ns.get("TERMINAL_STATES", set())

    assert isinstance(transitions, dict), "TRANSITIONS must be a dict"
    assert len(transitions) > 0

    for state, outcomes in transitions.items():
        for outcome, next_state in outcomes.items():
            assert next_state in transitions or next_state in valid_states, (
                f"State '{state}' → outcome '{outcome}' → '{next_state}' "
                f"is not a valid state in TRANSITIONS or TERMINAL_STATES"
            )
```

- [ ] Edit + run `python -m pytest tests/test_orchestrator_integration.py::test_transition_table_integrity -v` → PASS
- [ ] Commit: `test: add transition table integrity check`

### Task 6: Test write_manifest.py rejects invalid rules (Gap F)

**Files:**
- Create: `tests/test_write_manifest.py`

Test that `write_manifest.py` correctly rejects rules with missing evidence, low confidence, missing `fix_strategy`.

```python
import json, pathlib, subprocess, sys

MANIFEST_SCRIPT = pathlib.Path(".claude/skills/jade-core-change-collector/scripts/write_manifest.py")

def write_input_and_run(tmp_path, rules):
    inp = tmp_path / "input.json"
    inp.write_text(json.dumps(rules))
    result = subprocess.run(
        [sys.executable, str(MANIFEST_SCRIPT),
         "--input", str(inp),
         "--artifacts-dir", str(tmp_path),
         "--run-id", "test", "--source-version", "1.5", "--target-version", "1.6"],
        capture_output=True, text=True,
    )
    return result

def test_rejects_missing_evidence(tmp_path):
    rules = [{"id": "R1", "name": "Test", "severity": "HIGH",
              "fix_strategy": "recipe:jade-recipe-dummy",
              "match_pattern": "class", "confidence": 0.95,
              "patterns": [{"type": "regex", "pattern": "class",
                             "target_extensions": [".java"], "reason": "test",
                             "confidence": "HIGH"}]}]
    result = write_input_and_run(tmp_path, rules)
    assert result.returncode == 2
    assert "evidence_ref" in result.stdout + result.stderr

def test_rejects_low_confidence(tmp_path):
    rules = [{"id": "R2", "name": "Test", "severity": "HIGH",
              "fix_strategy": "recipe:jade-recipe-dummy",
              "match_pattern": "class", "confidence": 0.5,
              "evidence_ref": "src::lines 1-5",
              "evidence_hash": "abc123",
              "patterns": [{"type": "regex", "pattern": "class",
                             "target_extensions": [".java"], "reason": "test",
                             "confidence": "HIGH"}]}]
    result = write_input_and_run(tmp_path, rules)
    assert result.returncode == 2
    assert "confidence" in (result.stdout + result.stderr).lower()

def test_accepts_valid_rule(tmp_path):
    rules = [{"id": "VALID", "name": "Valid Rule", "severity": "HIGH",
              "fix_strategy": "recipe:jade-recipe-dummy",
              "match_pattern": "class", "confidence": 0.95,
              "evidence_ref": "mock-sources::lines 1-5",
              "evidence_hash": "dd251f683048fa9e882155b9e5aeccad9a46605bde50cac26741a564a2833a35",
              "patterns": [{"type": "regex", "pattern": "class",
                             "target_extensions": [".java"], "reason": "test",
                             "confidence": "HIGH"}]}]
    result = write_input_and_run(tmp_path, rules)
    assert result.returncode == 0
    assert (tmp_path / "01-breaking-changes-manifest.json").exists()
```

- [ ] Create `tests/test_write_manifest.py` with the above
- [ ] Run `python -m pytest tests/test_write_manifest.py -v` → 3 passed
- [ ] Run `python -m pytest tests/ -v` → verify no regressions
- [ ] Commit: `test: add write_manifest.py validation rejection tests`

---

## Execution order

Tasks are independent (modify different files or different tests in same file). Run sequentially for clean commits: 1 → 2 → 3 → 4 → 5 → 6. Expected: **6 commits, 8 new tests, final suite ~17 passed.**

## DoD

- [ ] `test_run_state_has_required_keys` includes `RULE_RETRY`, `RULE_ESCALATE`
- [ ] `test_manifest_has_valid_rules` checks `fix_strategy`, `evidence_ref`, `confidence`
- [ ] Orchestrator integration has `test_orchestrator_produces_progress_md`
- [ ] New `tests/test_retry_router.py` with ACTION_REQUIRED.md test
- [ ] Orchestrator integration has `test_transition_table_integrity`
- [ ] New `tests/test_write_manifest.py` with 3 rejection tests
- [ ] Full suite: `python -m pytest tests/ -v` — 0 failures
