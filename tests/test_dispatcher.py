import importlib.util
import json
import pathlib


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DISPATCHER_PATH = (
    REPO_ROOT / ".claude/skills/jade-core-rule-dispatcher/scripts/dispatcher.py"
)


def _load_dispatcher():
    spec = importlib.util.spec_from_file_location("dispatcher_test", DISPATCHER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_validate_flag_line_rejects_missing_string_zero_and_negative_lines():
    dispatcher = _load_dispatcher()

    for flag in ({}, {"line": "4"}, {"line": 0}, {"line": -1}):
        valid, error = dispatcher.validate_flag_line(flag)
        assert not valid
        assert error


def test_validate_flag_line_accepts_positive_integer_line():
    dispatcher = _load_dispatcher()

    assert dispatcher.validate_flag_line({"line": 4}) == (True, "")


def test_main_records_failed_malformed_flag_without_dispatching(tmp_path, monkeypatch):
    dispatcher = _load_dispatcher()
    artifacts = tmp_path / "artifacts"
    workspace = tmp_path / "workspace"
    artifacts.mkdir()
    workspace.mkdir()
    (workspace / "Example.java").write_text("class Example {}\n", encoding="utf-8")

    (artifacts / "05-rule-batch-RULE.json").write_text(
        json.dumps(
            {
                "files": [
                    {
                        "file": "Example.java",
                        "status": "PENDING",
                        "flags": [{"rule_id": "RULE"}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (artifacts / "01-breaking-changes-manifest.json").write_text(
        json.dumps(
            {"rules": [{"id": "RULE", "fix_strategy": "recipe:test"}]}
        ),
        encoding="utf-8",
    )

    def fail_if_dispatched(*args):
        raise AssertionError("malformed flag was dispatched")

    monkeypatch.setattr(dispatcher, "dispatch_recipe", fail_if_dispatched)
    monkeypatch.setattr(
        "sys.argv",
        [
            "dispatcher.py",
            "--artifacts-dir",
            str(artifacts),
            "--rule-id",
            "RULE",
            "--task-id",
            "RULE-0000",
            "--workspace-root",
            str(workspace),
        ],
    )

    assert dispatcher.main() == 2
    results = json.loads(
        (artifacts / "06-fix-results-RULE.json").read_text(encoding="utf-8")
    )
    assert results[0]["status"] == "FAILED"
    assert "line" in results[0]["errors"][0]
