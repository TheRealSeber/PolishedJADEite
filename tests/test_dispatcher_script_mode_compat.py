"""Backward-compatibility tests for dispatcher.py script mode.

These tests exist to prove that adding agent mode to the dispatcher did not
change a single byte of script-mode behavior for a registry entry that has
no "mode" key. Nothing here is allowed to fail by "fixing" the test -- a
failure here means script-mode compatibility was broken and the
implementation, not the test, must change.
"""

import importlib.util
import json
import pathlib
import shutil

import pytest


SCRIPT = pathlib.Path(__file__).parents[1] / ".claude/skills/jade-core-rule-dispatcher/scripts/dispatcher.py"
FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures" / "compat"


def load_module():
    spec = importlib.util.spec_from_file_location("dispatcher", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_script_mode_fix_results_byte_identical_to_golden(tmp_path):
    module = load_module()
    artifacts = tmp_path / "artifacts"
    workspace = tmp_path / "workspace"
    shutil.copytree(FIXTURE_DIR / "artifacts", artifacts)
    shutil.copytree(FIXTURE_DIR / "workspace", workspace)

    for task_id in [
        "DUMMY_TEST_RULE-Example1",
        "DUMMY_TEST_RULE-Example2",
        "DUMMY_TEST_RULE-Example3",
    ]:
        rc = module.main(
            [
                "--artifacts-dir", str(artifacts),
                "--rule-id", "DUMMY_TEST_RULE",
                "--task-id", task_id,
                "--workspace-root", str(workspace),
            ]
        )
        assert rc == 0

    results = json.loads(
        (artifacts / "06-fix-results-DUMMY_TEST_RULE.json").read_text(encoding="utf-8")
    )
    for record in results:
        assert "mode" not in record
        assert "shard_id" not in record
        record["applied_at"] = "1970-01-01T00:00:00Z"

    golden = json.loads(
        (FIXTURE_DIR / "06-fix-results-DUMMY_TEST_RULE.golden.json").read_text(encoding="utf-8")
    )
    for record in golden:
        record["applied_at"] = "1970-01-01T00:00:00Z"

    actual_dump = json.dumps(results, indent=2, ensure_ascii=False, sort_keys=False)
    golden_dump = json.dumps(golden, indent=2, ensure_ascii=False, sort_keys=False)
    assert actual_dump == golden_dump


def _scenario_missing_task(tmp_path, monkeypatch, module):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "05-rule-batch-RULE.json").write_text(
        json.dumps({"files": [{"file": "Example.java", "flags": [
            {"rule_id": "RULE", "file": "Example.java", "line": 1}
        ]}]}),
        encoding="utf-8",
    )
    return [
        "--artifacts-dir", str(artifacts), "--rule-id", "RULE",
        "--task-id", "NO-SUCH-TASK", "--workspace-root", str(tmp_path),
    ]


def _scenario_malformed_registry(tmp_path, monkeypatch, module):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "05-rule-batch-RULE.json").write_text(
        json.dumps({"files": [{"file": "Example.java", "flags": [
            {"rule_id": "RULE", "file": "Example.java", "line": 1}
        ]}]}),
        encoding="utf-8",
    )
    (artifacts / "01-breaking-changes-manifest.json").write_text(
        json.dumps({"rules": [{"id": "RULE", "fix_strategy": "recipe:test"}]}),
        encoding="utf-8",
    )
    (tmp_path / "Example.java").write_text("class Example {}\n", encoding="utf-8")
    monkeypatch.setattr(module, "load_registry", lambda: [])
    return [
        "--artifacts-dir", str(artifacts), "--rule-id", "RULE",
        "--task-id", "RULE-Example", "--workspace-root", str(tmp_path),
    ]


def _scenario_entry_without_script(tmp_path, monkeypatch, module):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "05-rule-batch-RULE.json").write_text(
        json.dumps({"files": [{"file": "Example.java", "flags": [
            {"rule_id": "RULE", "file": "Example.java", "line": 1}
        ]}]}),
        encoding="utf-8",
    )
    (artifacts / "01-breaking-changes-manifest.json").write_text(
        json.dumps({"rules": [{"id": "RULE", "fix_strategy": "recipe:test"}]}),
        encoding="utf-8",
    )
    (tmp_path / "Example.java").write_text("class Example {}\n", encoding="utf-8")
    monkeypatch.setattr(module, "load_registry", lambda: {"RULE": {"skill": "recipe"}})
    return [
        "--artifacts-dir", str(artifacts), "--rule-id", "RULE",
        "--task-id", "RULE-Example", "--workspace-root", str(tmp_path),
    ]


def _scenario_workspace_traversal(tmp_path, monkeypatch, module):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    file_rel = "../Example.java"
    (artifacts / "05-rule-batch-RULE.json").write_text(
        json.dumps({"files": [{"file": file_rel, "flags": [
            {"rule_id": "RULE", "file": file_rel, "line": 1}
        ]}]}),
        encoding="utf-8",
    )
    (artifacts / "01-breaking-changes-manifest.json").write_text(
        json.dumps({"rules": [{"id": "RULE", "fix_strategy": "recipe:test"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        module, "load_registry",
        lambda: {"RULE": {"skill": "recipe", "script": "unused"}},
    )
    monkeypatch.setattr(module, "dispatch_recipe", lambda *a: pytest.fail("recipe must not run"))
    return [
        "--artifacts-dir", str(artifacts), "--rule-id", "RULE",
        "--task-id", "RULE-0000", "--workspace-root", str(tmp_path / "workspace"),
    ]


def _scenario_symlink_escape(tmp_path, monkeypatch, module):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "Example.java").write_text("class Example {}\n", encoding="utf-8")
    try:
        (workspace / "linked.java").symlink_to(outside / "Example.java")
    except OSError:
        pytest.skip("symlinks are unavailable")
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "05-rule-batch-RULE.json").write_text(
        json.dumps({"files": [{"file": "linked.java", "flags": [
            {"rule_id": "RULE", "file": "linked.java", "line": 1}
        ]}]}),
        encoding="utf-8",
    )
    (artifacts / "01-breaking-changes-manifest.json").write_text(
        json.dumps({"rules": [{"id": "RULE", "fix_strategy": "recipe:test"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        module, "load_registry",
        lambda: {"RULE": {"skill": "recipe", "script": "unused"}},
    )
    monkeypatch.setattr(module, "dispatch_recipe", lambda *a: pytest.fail("recipe must not run"))
    return [
        "--artifacts-dir", str(artifacts), "--rule-id", "RULE",
        "--task-id", "RULE-0000", "--workspace-root", str(workspace),
    ]


def _scenario_invalid_flag(tmp_path, monkeypatch, module):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "05-rule-batch-RULE.json").write_text(
        json.dumps({"files": [{"file": "Example.java", "flags": [
            {"rule_id": "RULE", "file": "Example.java", "line": 0}
        ]}]}),
        encoding="utf-8",
    )
    (artifacts / "01-breaking-changes-manifest.json").write_text(
        json.dumps({"rules": [{"id": "RULE", "fix_strategy": "recipe:test"}]}),
        encoding="utf-8",
    )
    (tmp_path / "Example.java").write_text("class Example {}\n", encoding="utf-8")
    monkeypatch.setattr(module, "load_registry", lambda: {"RULE": {"script": "unused"}})
    monkeypatch.setattr(module, "dispatch_recipe", lambda *a: pytest.fail("recipe must not run"))
    return [
        "--artifacts-dir", str(artifacts), "--rule-id", "RULE",
        "--task-id", "RULE-Example", "--workspace-root", str(tmp_path),
    ]


def _scenario_file_mismatch(tmp_path, monkeypatch, module):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "05-rule-batch-RULE.json").write_text(
        json.dumps({"files": [{"file": "Example.java", "flags": [
            {"rule_id": "RULE", "file": "Other.java", "line": 1}
        ]}]}),
        encoding="utf-8",
    )
    (artifacts / "01-breaking-changes-manifest.json").write_text(
        json.dumps({"rules": [{"id": "RULE", "fix_strategy": "recipe:test"}]}),
        encoding="utf-8",
    )
    (tmp_path / "Example.java").write_text("class Example {}\n", encoding="utf-8")
    monkeypatch.setattr(module, "load_registry", lambda: {"RULE": {"script": "unused"}})
    monkeypatch.setattr(module, "dispatch_recipe", lambda *a: pytest.fail("recipe must not run"))
    return [
        "--artifacts-dir", str(artifacts), "--rule-id", "RULE",
        "--task-id", "RULE-Other", "--workspace-root", str(tmp_path),
    ]


def _scenario_rule_not_found(tmp_path, monkeypatch, module):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "05-rule-batch-RULE.json").write_text(
        json.dumps({"files": [{"file": "Example.java", "flags": [
            {"rule_id": "RULE", "file": "Example.java", "line": 1}
        ]}]}),
        encoding="utf-8",
    )
    (artifacts / "01-breaking-changes-manifest.json").write_text(
        json.dumps({"rules": []}),
        encoding="utf-8",
    )
    (tmp_path / "Example.java").write_text("class Example {}\n", encoding="utf-8")
    return [
        "--artifacts-dir", str(artifacts), "--rule-id", "RULE",
        "--task-id", "RULE-Example", "--workspace-root", str(tmp_path),
    ]


SCENARIOS = {
    "missing_task": (_scenario_missing_task, 2),
    "malformed_registry": (_scenario_malformed_registry, 2),
    "entry_without_script": (_scenario_entry_without_script, 2),
    "workspace_traversal": (_scenario_workspace_traversal, 2),
    "symlink_escape": (_scenario_symlink_escape, 2),
    "invalid_flag": (_scenario_invalid_flag, 2),
    "file_mismatch": (_scenario_file_mismatch, 2),
    "rule_not_found": (_scenario_rule_not_found, 2),
}


@pytest.mark.parametrize("scenario_name", sorted(SCENARIOS))
def test_script_mode_exit_codes_unchanged(tmp_path, monkeypatch, scenario_name):
    module = load_module()
    builder, expected_exit_code = SCENARIOS[scenario_name]
    argv = builder(tmp_path, monkeypatch, module)
    assert module.main(argv) == expected_exit_code


def test_registry_entry_without_mode_takes_script_path(tmp_path, monkeypatch):
    module = load_module()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "05-rule-batch-RULE.json").write_text(
        json.dumps({"files": [{"file": "Example.java", "flags": [
            {"rule_id": "RULE", "file": "Example.java", "line": 1}
        ]}]}),
        encoding="utf-8",
    )
    (artifacts / "01-breaking-changes-manifest.json").write_text(
        json.dumps({"rules": [{"id": "RULE", "fix_strategy": "recipe:test"}]}),
        encoding="utf-8",
    )
    (tmp_path / "Example.java").write_text("class Example {}\n", encoding="utf-8")
    monkeypatch.setattr(
        module, "load_registry",
        lambda: {"RULE": {"skill": "recipe", "script": "sentinel-script-path"}},
    )
    calls = []

    def fake_resolve_script_path(script_path):
        calls.append(script_path)
        raise ValueError("stop before spawning a subprocess")

    monkeypatch.setattr(module, "resolve_script_path", fake_resolve_script_path)

    module.main(
        [
            "--artifacts-dir", str(artifacts), "--rule-id", "RULE",
            "--task-id", "RULE-Example", "--workspace-root", str(tmp_path),
        ]
    )

    assert calls == ["sentinel-script-path"]


def test_agent_entry_refused_in_script_dispatch_without_running(tmp_path, monkeypatch):
    module = load_module()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "05-rule-batch-RULE.json").write_text(
        json.dumps({"files": [{"file": "Example.java", "flags": [
            {"rule_id": "RULE", "file": "Example.java", "line": 1}
        ]}]}),
        encoding="utf-8",
    )
    (artifacts / "01-breaking-changes-manifest.json").write_text(
        json.dumps({"rules": [{"id": "RULE", "fix_strategy": "recipe:test"}]}),
        encoding="utf-8",
    )
    (tmp_path / "Example.java").write_text("class Example {}\n", encoding="utf-8")
    monkeypatch.setattr(
        module, "load_registry",
        lambda: {
            "RULE": {
                "skill": "jade-recipe-agent-example",
                "skill_md": (
                    ".claude/skills/java-migration-skill-registry/shared/"
                    "jade-recipe-agent-example/SKILL.md"
                ),
                "mode": "agent",
            }
        },
    )

    class FakeRegistryModes:
        @staticmethod
        def entry_mode(entry):
            mode = entry.get("mode")
            return "script" if mode is None else mode

    monkeypatch.setattr(module, "_registry_modes", FakeRegistryModes)
    monkeypatch.setattr(module, "dispatch_recipe", lambda *a: pytest.fail("recipe must not run"))

    rc = module.main(
        [
            "--artifacts-dir", str(artifacts), "--rule-id", "RULE",
            "--task-id", "RULE-Example", "--workspace-root", str(tmp_path),
        ]
    )

    assert rc == 2
    results = json.loads((artifacts / "06-fix-results-RULE.json").read_text(encoding="utf-8"))
    assert results[-1]["status"] == "FAILED"
    assert "script dispatch refused" in results[-1]["errors"][0]
