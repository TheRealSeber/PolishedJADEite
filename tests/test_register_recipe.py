import importlib.util
import json
import pathlib
import sys

import pytest


SCRIPT = pathlib.Path(__file__).parents[1] / ".claude/skills/java-migration-skill-registry/scripts/register_recipe.py"


def load_module():
    spec = importlib.util.spec_from_file_location("register_recipe", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_register_recipe_scaffolds_and_updates_registry(tmp_path):
    module = load_module()
    registry = tmp_path / "recipe-registry.json"
    registry.write_text("{}\n", encoding="utf-8")

    result = module.register_recipe(
        registry_path=registry,
        registry_root=tmp_path / "registry",
        recipe_name="example",
        bucket="shared",
        rule_id="EXAMPLE_RULE",
        description="Example recipe",
    )

    recipe_dir = tmp_path / "registry" / "shared" / "example"
    assert result == "created"
    assert (recipe_dir / "SKILL.md").is_file()
    assert (recipe_dir / "scripts" / "apply.py").is_file()
    data = json.loads(registry.read_text(encoding="utf-8"))
    assert data["EXAMPLE_RULE"]["skill"] == "example"
    assert data["EXAMPLE_RULE"]["script"] == ".claude/skills/java-migration-skill-registry/shared/example/scripts/apply.py"


@pytest.mark.parametrize(
    "recipe_name,bucket",
    [("../escape", "shared"), ("safe", "../escape"), ("safe/name", "shared")],
)
def test_register_recipe_rejects_traversal(tmp_path, recipe_name, bucket):
    module = load_module()
    registry = tmp_path / "recipe-registry.json"
    registry.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError):
        module.register_recipe(
            registry_path=registry,
            registry_root=tmp_path / "registry",
            recipe_name=recipe_name,
            bucket=bucket,
            rule_id="RULE",
            description="Recipe",
        )


def test_register_recipe_rejects_existing_recipe_without_force(tmp_path):
    module = load_module()
    registry = tmp_path / "recipe-registry.json"
    registry.write_text("{}\n", encoding="utf-8")
    registry_root = tmp_path / "registry"
    module.register_recipe(
        registry_path=registry,
        registry_root=registry_root,
        recipe_name="example",
        bucket="shared",
        rule_id="RULE",
        description="Recipe",
    )

    with pytest.raises(FileExistsError):
        module.register_recipe(
            registry_path=registry,
            registry_root=registry_root,
            recipe_name="example",
            bucket="shared",
            rule_id="RULE2",
            description="Recipe",
        )


def test_register_recipe_is_idempotent(tmp_path):
    module = load_module()
    registry = tmp_path / "recipe-registry.json"
    registry.write_text("{}\n", encoding="utf-8")
    args = dict(
        registry_path=registry,
        registry_root=tmp_path / "registry",
        recipe_name="example",
        bucket="shared",
        rule_id="RULE",
        description="Recipe",
    )

    assert module.register_recipe(**args) == "created"
    before = registry.read_bytes()
    assert module.register_recipe(**args) == "unchanged"
    assert registry.read_bytes() == before
