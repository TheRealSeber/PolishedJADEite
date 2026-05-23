import json
import pathlib
import subprocess
import sys

RETRY_SCRIPT = pathlib.Path(
    ".claude/skills/jade-core-retry-router/scripts/retry_router.py"
)


def test_retry_router_writes_action_required(tmp_path):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    (artifacts / "06-fix-result-TEST.json").write_text(
        json.dumps(
            {
                "rule_id": "TEST_RULE",
                "attempt": 3,
                "status": "FAILED",
                "files_modified": ["src/Test.java"],
                "error": "javac: cannot find symbol: class Vector",
            }
        )
    )

    (artifacts / "07-build.log").write_text(
        "src/Test.java:10: error: cannot find symbol: class Vector\n"
    )

    result = subprocess.run(
        [
            sys.executable,
            str(RETRY_SCRIPT),
            "--artifacts",
            str(artifacts),
            "--max-retries",
            "3",
        ],
        capture_output=True,
        text=True,
    )

    action_path = artifacts / "ACTION_REQUIRED.md"
    assert action_path.exists(), (
        f"Retry router did not produce ACTION_REQUIRED.md\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    content = action_path.read_text(encoding="utf-8")
    assert "TEST_RULE" in content
    assert "Action Required" in content
    assert "Suggested actions" in content
