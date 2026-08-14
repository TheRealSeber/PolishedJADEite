import importlib.util
import json
import pathlib
import subprocess

import pytest


SCRIPT = pathlib.Path(__file__).parents[1] / ".claude/skills/jade-core-rule-dispatcher/scripts/dispatcher.py"


def load_module():
    spec = importlib.util.spec_from_file_location("dispatcher", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dispatch_recipe_resolves_registry_script_from_repo_root(tmp_path, monkeypatch):
    module = load_module()
    workspace_file = tmp_path / "Example.java"
    workspace_file.write_text("class Example {}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = module.dispatch_recipe(
        ".claude/skills/java-migration-skill-registry/shared/dummy/scripts/apply.py",
        str(workspace_file),
        1,
    )

    assert result["status"] == "FIXED"
    assert "// E2E TEST" in workspace_file.read_text(encoding="utf-8")


def test_dispatch_recipe_returns_failed_json_for_missing_script(tmp_path):
    module = load_module()
    workspace_file = tmp_path / "Example.java"
    workspace_file.write_text("class Example {}\n", encoding="utf-8")

    result = module.dispatch_recipe(
        ".claude/skills/java-migration-skill-registry/shared/missing/scripts/apply.py",
        str(workspace_file),
        1,
    )

    assert result == {
        "status": "FAILED",
        "changes": 0,
        "warnings": [],
        "errors": ["Recipe script not found: .claude/skills/java-migration-skill-registry/shared/missing/scripts/apply.py"],
        "diff_summary": "Recipe script not found: .claude/skills/java-migration-skill-registry/shared/missing/scripts/apply.py",
    }


def test_dispatch_recipe_accepts_canonical_registry_script(tmp_path):
    module = load_module()
    workspace_file = tmp_path / "Example.java"
    workspace_file.write_text("class Example {}\n", encoding="utf-8")
    result = module.dispatch_recipe(
        ".claude/skills/java-migration-skill-registry/shared/dummy/scripts/apply.py",
        str(workspace_file),
        1,
    )

    assert result["status"] == "FIXED"


def test_dispatch_recipe_rejects_script_outside_repo(tmp_path):
    module = load_module()
    result = module.dispatch_recipe(str(tmp_path / "apply.py"), str(tmp_path / "Example.java"), 1)
    assert result["status"] == "FAILED"
    assert "outside repository" in result["errors"][0]


def test_dispatch_recipe_rejects_symlink_outside_repo(tmp_path):
    module = load_module()
    link = tmp_path / "apply.py"
    outside = tmp_path.parent / "outside-apply.py"
    outside.write_text("", encoding="utf-8")
    try:
        link.symlink_to(outside)
    except OSError:
        return
    result = module.dispatch_recipe(str(link), str(tmp_path / "Example.java"), 1)
    assert result["status"] == "FAILED"
    assert "outside repository" in result["errors"][0]


def test_dispatch_recipe_handles_oserror(tmp_path, monkeypatch):
    module = load_module()
    script = ".claude/skills/java-migration-skill-registry/shared/dummy/scripts/apply.py"
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("spawn failed")))
    result = module.dispatch_recipe(str(script), str(tmp_path / "Example.java"), 1)
    assert result["status"] == "FAILED"
    assert "spawn failed" in result["errors"][0]


def test_dispatch_recipe_rejects_non_object_json(tmp_path, monkeypatch):
    module = load_module()
    script = ".claude/skills/java-migration-skill-registry/shared/dummy/scripts/apply.py"
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "[]", ""))
    result = module.dispatch_recipe(str(script), str(tmp_path / "Example.java"), 1)
    assert result["status"] == "FAILED"
    assert "non-object JSON" in result["errors"][0]


@pytest.mark.parametrize("file_rel", ["../Example.java", "escape/../../Example.java"])
def test_main_rejects_workspace_traversal_without_dispatch(tmp_path, monkeypatch, file_rel):
    module = load_module()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "05-rule-batch-RULE.json").write_text(
        json.dumps({"files": [{"file": file_rel, "flags": [{"rule_id": "RULE", "line": 1}]}]}),
        encoding="utf-8",
    )
    (artifacts / "01-breaking-changes-manifest.json").write_text(
        json.dumps({"rules": [{"id": "RULE", "fix_strategy": "recipe:test"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "load_registry", lambda: {
        "RULE": {"skill": "recipe", "script": ".claude/skills/java-migration-skill-registry/shared/dummy/scripts/apply.py"}
    })
    monkeypatch.setattr(module, "dispatch_recipe", lambda *args: pytest.fail("recipe must not run"))

    assert module.main([
        "--artifacts-dir", str(artifacts), "--rule-id", "RULE",
        "--task-id", "RULE-0000", "--workspace-root", str(tmp_path / "workspace"),
    ]) == 2
    results = json.loads((artifacts / "06-fix-results-RULE.json").read_text(encoding="utf-8"))
    assert results[-1]["status"] == "FAILED"
    assert "outside workspace" in results[-1]["errors"][0]


def test_main_rejects_workspace_symlink_escape_without_dispatch(tmp_path, monkeypatch):
    module = load_module()
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
        json.dumps({"files": [{"file": "linked.java", "flags": [{"rule_id": "RULE", "line": 1}]}]}),
        encoding="utf-8",
    )
    (artifacts / "01-breaking-changes-manifest.json").write_text(
        json.dumps({"rules": [{"id": "RULE", "fix_strategy": "recipe:test"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "load_registry", lambda: {
        "RULE": {"skill": "recipe", "script": ".claude/skills/java-migration-skill-registry/shared/dummy/scripts/apply.py"}
    })
    monkeypatch.setattr(module, "dispatch_recipe", lambda *args: pytest.fail("recipe must not run"))

    assert module.main([
        "--artifacts-dir", str(artifacts), "--rule-id", "RULE",
        "--task-id", "RULE-0000", "--workspace-root", str(workspace),
    ]) == 2
    results = json.loads((artifacts / "06-fix-results-RULE.json").read_text(encoding="utf-8"))
    assert "outside workspace" in results[-1]["errors"][0]


def test_dispatch_recipe_rejects_noncanonical_script_without_running(tmp_path, monkeypatch):
    module = load_module()
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("recipe must not run"))
    result = module.dispatch_recipe(
        ".claude/skills/jade-core-rule-dispatcher/scripts/dispatcher.py",
        str(tmp_path / "Example.java"),
        1,
    )
    assert result["status"] == "FAILED"
    assert "canonical registry recipe script" in result["errors"][0]


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"status": "FIXED", "changes": "1", "warnings": [], "errors": [], "diff_summary": "ok"}, "changes"),
        ({"status": "FIXED", "changes": 1, "warnings": [1], "errors": [], "diff_summary": "ok"}, "warnings"),
        ({"status": "FIXED", "changes": 1, "warnings": [], "errors": [], "diff_summary": 1}, "diff_summary"),
    ],
)
def test_dispatch_recipe_rejects_malformed_result(tmp_path, monkeypatch, payload, message):
    module = load_module()
    script = ".claude/skills/java-migration-skill-registry/shared/dummy/scripts/apply.py"
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, json.dumps(payload), ""))
    result = module.dispatch_recipe(script, str(tmp_path / "Example.java"), 1)
    assert result["status"] == "FAILED"
    assert message in result["errors"][0]


def test_dispatch_recipe_rejects_unknown_status(tmp_path, monkeypatch):
    module = load_module()
    script = ".claude/skills/java-migration-skill-registry/shared/dummy/scripts/apply.py"
    payload = {"status": "MAGIC", "changes": 0, "warnings": [], "errors": [], "diff_summary": "ok"}
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, json.dumps(payload), ""))
    result = module.dispatch_recipe(script, str(tmp_path / "Example.java"), 1)
    assert result["status"] == "FAILED"
    assert "unknown status" in result["errors"][0]


def test_dispatch_recipe_accepts_valid_result(tmp_path, monkeypatch):
    module = load_module()
    script = ".claude/skills/java-migration-skill-registry/shared/dummy/scripts/apply.py"
    payload = {"status": "SKIPPED", "changes": 0, "warnings": ["informational"], "errors": [], "diff_summary": "ok"}
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, json.dumps(payload), ""))
    assert module.dispatch_recipe(script, str(tmp_path / "Example.java"), 1) == payload


def test_main_records_failure_for_malformed_registry(tmp_path, monkeypatch):
    module = load_module()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "05-rule-batch-RULE.json").write_text(
        json.dumps({"files": [{"file": "Example.java", "flags": [{"rule_id": "RULE", "line": 1}]}]}),
        encoding="utf-8",
    )
    (artifacts / "01-breaking-changes-manifest.json").write_text(
        json.dumps({"rules": [{"id": "RULE", "fix_strategy": "recipe:test"}]}),
        encoding="utf-8",
    )
    (tmp_path / "Example.java").write_text("class Example {}\n", encoding="utf-8")
    monkeypatch.setattr(module, "load_registry", lambda: [])

    assert module.main([
        "--artifacts-dir", str(artifacts), "--rule-id", "RULE",
        "--task-id", "RULE-0001", "--workspace-root", str(tmp_path),
    ]) == 2
    results = json.loads((artifacts / "06-fix-results-RULE.json").read_text(encoding="utf-8"))
    assert results[-1]["status"] == "FAILED"


def test_main_records_failure_for_entry_without_script(tmp_path, monkeypatch):
    module = load_module()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "05-rule-batch-RULE.json").write_text(
        json.dumps({"files": [{"file": "Example.java", "flags": [{"rule_id": "RULE", "line": 1}]}]}),
        encoding="utf-8",
    )
    (artifacts / "01-breaking-changes-manifest.json").write_text(
        json.dumps({"rules": [{"id": "RULE", "fix_strategy": "recipe:test"}]}),
        encoding="utf-8",
    )
    (tmp_path / "Example.java").write_text("class Example {}\n", encoding="utf-8")
    monkeypatch.setattr(module, "load_registry", lambda: {"RULE": {"skill": "recipe"}})

    assert module.main([
        "--artifacts-dir", str(artifacts), "--rule-id", "RULE",
        "--task-id", "RULE-0001", "--workspace-root", str(tmp_path),
    ]) == 2
    results = json.loads((artifacts / "06-fix-results-RULE.json").read_text(encoding="utf-8"))
    assert results[-1]["status"] == "FAILED"
