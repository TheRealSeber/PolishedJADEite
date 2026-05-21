import json
import pathlib
import subprocess
import sys

import pytest

SCAN_SCRIPT = pathlib.Path(".claude/skills/jade-scanner/scripts/scan_and_tag.py")
ARTIFACTS_DIR = pathlib.Path("migration-runs/sample/artifacts")
WORKSPACE = pathlib.Path("migration-runs/sample/workspace")


def _assert_workspace_exists():
    if not WORKSPACE.is_dir():
        pytest.skip(f"Workspace not found: {WORKSPACE}")


def _assert_flag_index_exists():
    idx_path = ARTIFACTS_DIR / "04-flag-index.json"
    if not idx_path.exists():
        pytest.skip("Run scanner first to produce 04-flag-index.json")


def test_scanner_second_run_no_new_flags():
    _assert_workspace_exists()
    _assert_flag_index_exists()

    idx_path = ARTIFACTS_DIR / "04-flag-index.json"
    existing = json.loads(idx_path.read_text(encoding="utf-8"))
    first_count = existing.get("total_flags", len(existing.get("flags", [])))

    result = subprocess.run(
        [
            sys.executable,
            str(SCAN_SCRIPT),
            "--workspace",
            str(WORKSPACE),
            "--artifacts",
            str(ARTIFACTS_DIR),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Scanner failed:\n{result.stderr}"

    summary_path = ARTIFACTS_DIR / "04-scan-summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["total_new_flags"] == 0, (
            f"Second scan produced {summary['total_new_flags']} new flags "
            f"(should be 0). First run had {first_count}."
        )
        assert summary["idempotent_skips"] >= first_count, (
            f"Expected at least {first_count} idempotent skips, "
            f"got {summary['idempotent_skips']}"
        )
