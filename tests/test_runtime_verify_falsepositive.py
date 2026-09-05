"""Regression coverage for the runtime_verify.py false-positive on
restaurant-recommendation (migration-runs/jade-8-to-11/artifacts/07-runtime-verify.json
reported status=PASS for a run whose own TestRunnerAgent had printed
RESTAURANT_TEST_FAILED).

Each test below isolates one candidate cause named in the diagnosis brief and
asserts the concrete, current behavior of runtime_verify.py:

- confirmed defect: an unconfigured "..._FAILED" marker in the combined
  output was silently ignored whenever every expected_stdout_marker also
  matched -- fixed by GENERIC_FAILURE_MARKER_RE in runtime_verify.py.
- everything else on the candidate list (empty marker list, empty stdout,
  timeout, a container that never started, an ignored exit code) is proven
  to already FAIL with an explicit reason -- these are not bugs, and the
  tests here exist to pin that down as a regression guard rather than as a
  fix.
"""

import importlib.util
import json
import pathlib
import sys

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNTIME_VERIFY_PATH = (
    REPO_ROOT / ".claude/skills/jade-core-verification/scripts/runtime_verify.py"
)
RESTAURANT_CONFIG_PATH = (
    REPO_ROOT / "consumer-playground/restaurant-recommendation/test-config.json"
)
RESTAURANT_ARTIFACT_PATH = (
    REPO_ROOT / "migration-runs/jade-8-to-11/artifacts/07-runtime-verify.json"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "runtime_verify_falsepositive_test", RUNTIME_VERIFY_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _base_cfg(**overrides):
    cfg = {
        "name": "synthetic-consumer",
        "main_class": "jade.Boot",
        "boot_args": [],
        "timeout_seconds": 30,
        "expected_stdout_markers": ["MARKER_ONE", "MARKER_TWO"],
    }
    cfg.update(overrides)
    return cfg


def _run(mod, tmp_path, monkeypatch, cfg, *, rc, stdout, stderr=""):
    project_dir = tmp_path / "consumer"
    project_dir.mkdir(exist_ok=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    monkeypatch.setattr(mod, "compile_consumer", lambda *a, **k: (True, ""))
    monkeypatch.setattr(mod, "run_in_docker", lambda *a, **k: (rc, stdout, stderr))
    return mod.test_consumer(project_dir, workspace, cfg, registry=None)


# ---------------------------------------------------------------------------
# The confirmed defect: an unconfigured "..._FAILED" marker was ignored.
# ---------------------------------------------------------------------------


def test_reproduces_the_actual_restaurant_recommendation_false_positive(
    tmp_path, monkeypatch
):
    """Feed the *real* recorded stdout from the false-positive run back
    through test_consumer with the *real* test-config.json markers.

    Before the fix this combination reported PASS (as the committed
    artifact shows); the fix must make it FAIL with an explicit reason.
    """
    mod = _load_module()
    real_cfg = json.loads(RESTAURANT_CONFIG_PATH.read_text(encoding="utf-8"))
    real_artifact = json.loads(RESTAURANT_ARTIFACT_PATH.read_text(encoding="utf-8"))
    recorded = next(
        r
        for r in real_artifact["results"]
        if r["project"] == "restaurant-recommendation"
    )
    # Sanity-check the fixture itself matches what we diagnosed, so this
    # test fails loudly (not silently) if the source artifact ever changes.
    assert recorded["status"] == "PASS"
    assert "RESTAURANT_TEST_FAILED" in recorded["stdout_snippet"]
    assert "RESTAURANT_TEST_PASSED" in recorded["stdout_snippet"]

    # classpath_deps points at real jars we don't need to stage here --
    # compile_consumer is monkeypatched out, so drop it to keep the test
    # hermetic.
    cfg = dict(real_cfg)
    cfg.pop("classpath_deps", None)

    result = _run(
        mod,
        tmp_path,
        monkeypatch,
        cfg,
        rc=0,
        stdout=recorded["stdout_snippet"],
    )

    assert result["status"] == "FAIL"
    assert "RESTAURANT_TEST_FAILED" in result["error"]


def test_generic_failed_marker_overrides_an_also_present_success_marker(
    tmp_path, monkeypatch
):
    """Minimal, config-independent reproduction of the same shape of bug:
    every expected_stdout_marker is present, but so is an unconfigured
    "..._FAILED" marker -- this must now FAIL, not PASS.
    """
    mod = _load_module()
    cfg = _base_cfg(expected_stdout_markers=["APP_TEST_PASSED"])

    result = _run(
        mod,
        tmp_path,
        monkeypatch,
        cfg,
        rc=0,
        stdout="APP_TEST_PASSED\nAPP_TEST_FAILED\n",
    )

    assert result["status"] == "FAIL"
    assert "APP_TEST_FAILED" in result["error"]


def test_configured_failure_marker_still_wins_over_generic_check(tmp_path, monkeypatch):
    """failure_stdout_markers (the jrba-style opt-in) must keep taking the
    more specific "Configured failure markers" branch, not the new generic
    one -- no behavior change for consumers that already declare it.
    """
    mod = _load_module()
    cfg = _base_cfg(
        expected_stdout_markers=["JRBA_TEST_PASSED"],
        failure_stdout_markers=["JRBA_TEST_FAILED"],
    )

    result = _run(
        mod,
        tmp_path,
        monkeypatch,
        cfg,
        rc=0,
        stdout="JRBA_TEST_PASSED\nJRBA_TEST_FAILED\n",
    )

    assert result["status"] == "FAIL"
    assert result["error"].startswith("Configured failure markers detected")


def test_generic_check_does_not_flag_a_clean_passing_run(tmp_path, monkeypatch):
    """Regression guard: a run with no "..._FAILED"-shaped token anywhere
    must still PASS -- the new check must not over-trigger on ordinary
    consumers such as hw-jade's free-text success markers.
    """
    mod = _load_module()
    cfg = _base_cfg(
        expected_stdout_markers=[
            "Customer initialized for request Warsaw -> Tokyo",
            "SUCCESS: Booking completed",
        ]
    )

    result = _run(
        mod,
        tmp_path,
        monkeypatch,
        cfg,
        rc=0,
        stdout="Customer initialized for request Warsaw -> Tokyo\nSUCCESS: Booking completed\n",
    )

    assert result["status"] == "PASS"


def test_generic_check_ignores_a_marker_that_is_itself_expected(tmp_path, monkeypatch):
    """A consumer whose own success marker happens to contain "_FAILED"
    (double-negative naming) must not be punished by the generic scan."""
    mod = _load_module()
    cfg = _base_cfg(expected_stdout_markers=["ZERO_ORDERS_FAILED_VALIDATION_OK"])

    result = _run(
        mod,
        tmp_path,
        monkeypatch,
        cfg,
        rc=0,
        stdout="ZERO_ORDERS_FAILED_VALIDATION_OK\n",
    )

    assert result["status"] == "PASS"


# ---------------------------------------------------------------------------
# The rest of the diagnosis checklist: already correct. Pinned as regression
# guards, not fixes.
# ---------------------------------------------------------------------------


def test_missing_expected_markers_is_a_config_error_not_a_pass(tmp_path):
    """"brak markerow traktowany jako sukces" -- omitting
    expected_stdout_markers must fail config validation, never be treated
    as an automatic pass."""
    mod = _load_module()
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    cfg = _base_cfg()
    del cfg["expected_stdout_markers"]

    result = mod.test_consumer(consumer, workspace, cfg, registry=None)

    assert result["status"] == "FAIL"
    assert "expected_stdout_markers is required" in result["error"]


def test_empty_expected_markers_list_is_a_config_error_not_a_pass(tmp_path):
    mod = _load_module()
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    cfg = _base_cfg(expected_stdout_markers=[])

    result = mod.test_consumer(consumer, workspace, cfg, registry=None)

    assert result["status"] == "FAIL"
    assert "expected_stdout_markers" in result["error"]


def test_empty_stdout_is_a_fail_not_a_pass(tmp_path, monkeypatch):
    """"pusty stdout" -- an empty combined output can never satisfy a
    non-empty expected_stdout_markers list, so it must FAIL."""
    mod = _load_module()
    cfg = _base_cfg()

    result = _run(mod, tmp_path, monkeypatch, cfg, rc=0, stdout="", stderr="")

    assert result["status"] == "FAIL"
    assert "Missing expected markers" in result["error"]


def test_timeout_is_always_a_fail_even_if_markers_already_printed(
    tmp_path, monkeypatch
):
    """"timeout" -- run_in_docker signals a timeout with rc == -1; this
    must FAIL even when the partial output already contains every expected
    marker (the process was still killed before it could exit cleanly)."""
    mod = _load_module()
    cfg = _base_cfg()

    result = _run(
        mod,
        tmp_path,
        monkeypatch,
        cfg,
        rc=-1,
        stdout="MARKER_ONE\nMARKER_TWO\n",
        stderr="Container timed out after 45s",
    )

    assert result["status"] == "FAIL"
    assert result["error"] == "Container timed out"


def test_container_that_never_started_is_a_fail(tmp_path, monkeypatch):
    """"kontener ktory nie wystartowal" -- docker itself failing to launch
    the container (e.g. bad image reference) surfaces as a non-zero,
    non-timeout return code with no stdout; this must FAIL with the exit
    code in the reason, not be treated as a vacuous pass."""
    mod = _load_module()
    cfg = _base_cfg()

    result = _run(
        mod,
        tmp_path,
        monkeypatch,
        cfg,
        rc=125,
        stdout="",
        stderr="docker: Error response from daemon: No such image.",
    )

    assert result["status"] == "FAIL"
    assert "125" in result["error"]


def test_nonzero_exit_code_is_not_ignored_even_with_all_markers_present(
    tmp_path, monkeypatch
):
    """"exit code ignorowany" -- a non-zero exit code must FAIL even when
    every expected marker is present in the output; marker matching must
    never override a failing exit code."""
    mod = _load_module()
    cfg = _base_cfg()

    result = _run(
        mod,
        tmp_path,
        monkeypatch,
        cfg,
        rc=1,
        stdout="MARKER_ONE\nMARKER_TWO\n",
        stderr="",
    )

    assert result["status"] == "FAIL"
    assert result["error"] == "Container exited with code 1"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
