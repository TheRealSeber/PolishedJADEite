import json
import os
import pathlib
import shutil

import pytest

_FIXTURE_ARTIFACTS = pathlib.Path("tests/fixtures/artifacts")
_FIXTURE_WORKSPACE = pathlib.Path("tests/fixtures/workspace")
_SAMPLE_RUN_DIR = pathlib.Path("migration-runs/sample")


@pytest.fixture
def artifacts_dir():
    """Artifact directory used by contract/idempotency tests.

    Uses the committed fixture artifacts under ``tests/fixtures/artifacts``
    (deterministic, no pipeline run required). Overridable via
    ``JADE_TEST_ARTIFACTS_DIR`` to point at a real migration run.
    """
    path = os.environ.get("JADE_TEST_ARTIFACTS_DIR", str(_FIXTURE_ARTIFACTS))
    return pathlib.Path(path)


@pytest.fixture
def workspace_dir():
    path = os.environ.get(
        "JADE_TEST_WORKSPACE_DIR",
        str(pathlib.Path("tests/fixtures/workspace")),
    )
    return pathlib.Path(path)


@pytest.fixture
def sample_artifacts_dir(tmp_path):
    """Isolated copy of the ``migration-runs/sample`` run used by
    orchestrator integration tests (they deliberately exercise the real
    pipeline end-to-end).

    The orchestrator writes run-state/history/progress artifacts next to
    the config it is given, so this fixture copies the whole run
    directory into ``tmp_path`` and rewrites the copied config's path
    fields (``baseline_path``/``workspace_path``/``artifacts_path``) to
    point at that copy. This preserves the real pipeline behavior under
    test while never mutating the tracked files under
    ``migration-runs/sample/`` in the repo working tree.
    """
    run_copy = tmp_path / "sample-run"
    shutil.copytree(_SAMPLE_RUN_DIR, run_copy)

    config_path = run_copy / "artifacts" / "00-run-config.json"
    if config_path.exists():
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
        for key in ("baseline_path", "workspace_path", "artifacts_path"):
            if key in cfg:
                relative = pathlib.Path(cfg[key]).relative_to(_SAMPLE_RUN_DIR)
                cfg[key] = str((run_copy / relative).resolve())
        config_path.write_text(
            json.dumps(cfg, indent=2) + "\n", encoding="utf-8"
        )

    return run_copy / "artifacts"