"""The BUILD_GATE_READY gate must not accept a build that did not succeed.

Two independent holes let a failed build through, and both are covered here:

1. ``03-build-audit.json`` recorded ``build_exit_code`` but no gate rule ever
   read it, so an audit reporting its own failure validated fine.
2. ``build_audit.py`` returned exit 0 for ``NEEDS_MANUAL``, a status only
   reachable when the build failed, while printing "Build succeeded".

AGENTS.md #15: only BUILD SUCCESSFUL with exit 0 counts as build evidence.
"""

import importlib.util
import json
import pathlib
import sys

SCRIPT = (
    pathlib.Path(__file__).parent.parent
    / ".claude/skills/jade-core-orchestrator/scripts/orchestrator.py"
)
BUILD_AUDIT = (
    pathlib.Path(__file__).parent.parent
    / ".claude/skills/jade-core-build-fixer/scripts/build_audit.py"
)


def load_orchestrator():
    spec = importlib.util.spec_from_file_location("orchestrator_build_gate_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _audit(build_exit_code: int) -> dict:
    return {
        "run_id": "gate-test",
        "status": "OK",
        "build_system": "ant",
        "build_file": "src/jade/build.xml",
        "build_exit_code": build_exit_code,
        "env": {"docker": "available"},
    }


def _write(tmp_path: pathlib.Path, payload: dict) -> pathlib.Path:
    path = tmp_path / "03-build-audit.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_gate_accepts_a_successful_build(tmp_path):
    orch = load_orchestrator()
    ok, reason = orch._validate_artifact(_write(tmp_path, _audit(0)), "BUILD_GATE_READY")
    assert ok, reason


def test_gate_rejects_a_failed_build(tmp_path):
    orch = load_orchestrator()
    ok, reason = orch._validate_artifact(_write(tmp_path, _audit(1)), "BUILD_GATE_READY")
    assert not ok
    assert "build_exit_code" in reason


def test_gate_rejects_an_audit_with_no_build_exit_code(tmp_path):
    orch = load_orchestrator()
    payload = _audit(0)
    del payload["build_exit_code"]
    ok, reason = orch._validate_artifact(_write(tmp_path, payload), "BUILD_GATE_READY")
    assert not ok
    assert "build_exit_code" in reason


def test_json_equals_rule_is_wired_into_the_validator(tmp_path):
    orch = load_orchestrator()
    rules = orch.ARTIFACT_CONTENT_RULES["03-build-audit.json"]
    assert rules["json_equals"] == {"build_exit_code": 0}


def test_needs_manual_does_not_report_success():
    """NEEDS_MANUAL is unreachable on a successful build, so it must not exit 0."""
    source = BUILD_AUDIT.read_text(encoding="utf-8")
    # The branch's own comment explains the old "return 0", so read code only.
    code = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )
    branch = code.split('elif gate_status == "NEEDS_MANUAL":', 1)[1]
    branch = branch.split("else:", 1)[0]
    assert "return 0" not in branch
    assert "return 1" in branch
    assert "Build succeeded but manual fixes are pending" not in code


if __name__ == "__main__":
    sys.exit(0)
