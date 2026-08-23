import os
import pathlib

import pytest

_FIXTURE_ARTIFACTS = pathlib.Path("tests/fixtures/artifacts")
_FIXTURE_WORKSPACE = pathlib.Path("tests/fixtures/workspace")


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
def sample_artifacts_dir():
    """Live ``migration-runs/sample`` artifacts used by orchestrator
    integration tests (they deliberately exercise the real pipeline)."""
    return pathlib.Path("migration-runs/sample/artifacts")