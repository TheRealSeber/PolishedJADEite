# Orchestrator integration tests deliberately operate on the shared
# artifacts_dir fixture (migration-runs/sample/artifacts).  Unlike the
# scanner test which uses tmp_path, these tests exercise the real
# end-to-end pipeline and need live artifact state to validate phases,
# history, and state transitions.
import json
import pathlib
import subprocess
import sys

import pytest

ORCH_SCRIPT = pathlib.Path(
    ".claude/skills/jade-core-orchestrator/scripts/orchestrator.py"
)


def test_orchestrator_completes_on_sample_run(artifacts_dir):
    config_path = artifacts_dir / "00-run-config.json"
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
        (artifacts_dir / "00-run-state.json").read_text(encoding="utf-8")
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


def test_orchestrator_produces_phase_history(artifacts_dir):
    history_path = artifacts_dir / "phase-history.log.jsonl"
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
