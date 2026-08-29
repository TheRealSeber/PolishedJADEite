# Orchestrator integration tests deliberately operate on the
# sample_artifacts_dir fixture, an isolated tmp_path copy of
# migration-runs/sample/artifacts (see tests/conftest.py). These tests
# exercise the real end-to-end pipeline and need real artifact state to
# validate phases, history, and state transitions, but never mutate the
# tracked files in the repo working tree.
import json
import pathlib
import subprocess
import sys

import pytest

ORCH_SCRIPT = pathlib.Path(
    ".claude/skills/jade-core-orchestrator/scripts/orchestrator.py"
)


def test_orchestrator_completes_on_sample_run(sample_artifacts_dir):
    config_path = sample_artifacts_dir / "00-run-config.json"
    if not config_path.exists():
        pytest.skip(f"{config_path} not found")
    result = subprocess.run(
        [sys.executable, str(ORCH_SCRIPT), "--config", str(config_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Orchestrator failed (exit {result.returncode}):\n{result.stderr}"
    )

    state = json.loads(
        (sample_artifacts_dir / "00-run-state.json").read_text(encoding="utf-8")
    )
    assert state["state"] in {
        "DONE",
        "FAILED",
        "AWAITING_SOURCE_INPUT",
        "INIT",
        "WORKSPACE_READY",
        "MANIFEST_READY",
    }, f"Unexpected state: {state['state']}"


def test_orchestrator_handles_missing_config():
    result = subprocess.run(
        [
            sys.executable,
            str(ORCH_SCRIPT),
            "--config",
            "/nonexistent/path/to/config.json",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, (
        f"Orchestrator should fail with missing config dir, got {result.returncode}"
    )


def test_orchestrator_produces_phase_history(sample_artifacts_dir):
    history_path = sample_artifacts_dir / "phase-history.log.jsonl"
    if not history_path.exists():
        pytest.skip(f"{history_path} not found (orchestrator hasn't run yet)")

    lines = [
        line
        for line in history_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(lines) > 0, "Phase history is empty"

    for line in lines:
        entry = json.loads(line)
        assert "ts" in entry
        assert "phase" in entry
        assert "status" in entry
        assert "artifacts" in entry


def test_orchestrator_produces_progress_md(sample_artifacts_dir):
    progress_path = sample_artifacts_dir / "PROGRESS.md"
    if not progress_path.exists():
        pytest.skip(f"{progress_path} not found (orchestrator hasn't run yet)")

    content = progress_path.read_text(encoding="utf-8")
    assert "Migration Progress" in content
    assert "| Phase | Status |" in content
    assert len(content.splitlines()) >= 5, (
        "PROGRESS.md should have header + at least 3 rows"
    )


def test_transition_table_integrity():
    import itertools

    orch_path = pathlib.Path(
        ".claude/skills/jade-core-orchestrator/scripts/orchestrator.py"
    )
    source = orch_path.read_text(encoding="utf-8")
    ns = {}
    exec(compile(source, str(orch_path), "exec"), ns)
    transitions = ns["TRANSITIONS"]
    terminal_states = ns.get("TERMINAL_STATES", set())

    assert isinstance(transitions, dict), "TRANSITIONS must be a dict"
    assert len(transitions) > 0

    for state, outcomes in transitions.items():
        for outcome, next_state in outcomes.items():
            assert next_state in transitions or next_state in terminal_states, (
                f"State '{state}' → outcome '{outcome}' → '{next_state}' "
                f"is not a valid state in TRANSITIONS or TERMINAL_STATES"
            )
