import os
import pathlib

import pytest


@pytest.fixture
def artifacts_dir():
    path = os.environ.get(
        "JADE_TEST_ARTIFACTS_DIR",
        str(pathlib.Path("migration-runs/sample/artifacts")),
    )
    return pathlib.Path(path)


@pytest.fixture
def workspace_dir():
    path = os.environ.get(
        "JADE_TEST_WORKSPACE_DIR",
        str(pathlib.Path("migration-runs/sample/workspace")),
    )
    return pathlib.Path(path)
