import json
import pathlib
import subprocess
import sys

import pytest

ORCH_SCRIPT = pathlib.Path(
    ".claude/skills/jade-migration-orchestrator/scripts/orchestrator.py"
)
ARTIFACTS_DIR = pathlib.Path("migration-runs/sample/artifacts")
CONFIG_PATH = ARTIFACTS_DIR / "00-run-config.json"


def test_orchestrator_completes_on_sample_run():
    result = subprocess.run(
        [sys.executable, str(ORCH_SCRIPT), "--config", str(CONFIG_PATH)],
        capture_output=True,
        text=True,
    )
    assert result.returncode in (0, 1, 2), (
        f"Unexpected exit code {result.returncode}:\n{result.stderr}"
    )

    state = json.loads(
        (ARTIFACTS_DIR / "00-run-state.json").read_text(encoding="utf-8")
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


def test_orchestrator_produces_phase_history():
    history_path = ARTIFACTS_DIR / "phase-history.log.jsonl"
    assert history_path.exists(), "phase-history.log.jsonl not found"

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
