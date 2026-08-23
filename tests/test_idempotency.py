import json
import pathlib
import shutil
import subprocess
import sys

import pytest

SCAN_SCRIPT = pathlib.Path(".claude/skills/jade-core-scanner/scripts/scan_and_tag.py")
FIXTURE_ARTIFACTS = pathlib.Path("tests/fixtures/artifacts")
FIXTURE_WORKSPACE = pathlib.Path("tests/fixtures/workspace")


def test_scanner_second_run_no_new_flags(tmp_path):
    """A re-scan of an already-flagged workspace must produce zero new
    flags and count existing markers as idempotent skips."""
    if not FIXTURE_WORKSPACE.is_dir():
        pytest.skip(f"Workspace fixture not found: {FIXTURE_WORKSPACE}")
    idx_path = FIXTURE_ARTIFACTS / "04-flag-index.json"
    manifest = FIXTURE_ARTIFACTS / "01-breaking-changes-manifest.json"
    if not idx_path.exists() or not manifest.exists():
        pytest.skip("Fixture artifacts (flag-index / manifest) not found")

    workspace_copy = tmp_path / "workspace"
    shutil.copytree(str(FIXTURE_WORKSPACE), str(workspace_copy))

    artifacts_copy = tmp_path / "artifacts"
    artifacts_copy.mkdir()
    shutil.copy2(str(idx_path), str(artifacts_copy / "04-flag-index.json"))
    shutil.copy2(str(manifest), str(artifacts_copy / "01-breaking-changes-manifest.json"))

    existing = json.loads(idx_path.read_text(encoding="utf-8"))
    first_count = existing.get("total_flags", len(existing.get("flags", [])))
    assert first_count > 0

    result = subprocess.run(
        [
            sys.executable,
            str(SCAN_SCRIPT),
            "--workspace",
            str(workspace_copy),
            "--artifacts",
            str(artifacts_copy),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Scanner failed:\n{result.stderr}"

    summary_path = artifacts_copy / "04-scan-summary.json"
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