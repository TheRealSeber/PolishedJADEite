import importlib.util
import json
import pathlib


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
    }


def test_dispatch_recipe_preserves_absolute_script_paths(tmp_path):
    module = load_module()
    workspace_file = tmp_path / "Example.java"
    workspace_file.write_text("class Example {}\n", encoding="utf-8")
    script = SCRIPT.parents[2] / "java-migration-skill-registry/shared/dummy/scripts/apply.py"

    result = module.dispatch_recipe(str(script), str(workspace_file), 1)

    assert result["status"] == "FIXED"
