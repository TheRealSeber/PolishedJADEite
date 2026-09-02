import importlib.util
import json
import pathlib
import subprocess
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


def test_register_recipe_scaffold_apply_emits_dispatcher_contract(tmp_path):
    module = load_module()
    registry = tmp_path / "recipe-registry.json"
    registry.write_text("{}\n", encoding="utf-8")
    module.register_recipe(
        registry_path=registry,
        registry_root=tmp_path / "registry",
        recipe_name="example",
        bucket="shared",
        rule_id="EXAMPLE_RULE",
        description="Example recipe",
    )
    source = tmp_path / "Example.java"
    source.write_text("class Example {}\n", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(tmp_path / "registry" / "shared" / "example" / "scripts" / "apply.py"),
            "--file",
            str(source),
            "--line",
            "1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload == {
        "status": "SKIPPED",
        "changes": 0,
        "warnings": [],
        "errors": [],
        "diff_summary": "No source changes required",
    }


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


def test_register_recipe_rejects_duplicate_rule_when_recipe_directory_is_missing(tmp_path):
    module = load_module()
    registry = tmp_path / "recipe-registry.json"
    registry.write_text(
        json.dumps(
            {
                "RULE": {
                    "skill": "existing",
                    "script": ".claude/skills/java-migration-skill-registry/shared/existing/scripts/apply.py",
                    "description": "Existing recipe",
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    registry_root = tmp_path / "registry"
    existing_script = registry_root / "shared" / "existing" / "scripts" / "apply.py"
    existing_script.parent.mkdir(parents=True)
    existing_script.write_text("", encoding="utf-8")

    with pytest.raises(FileExistsError, match="rule already registered: RULE"):
        module.register_recipe(
            registry_path=registry,
            registry_root=registry_root,
            recipe_name="new-recipe",
            bucket="shared",
            rule_id="RULE",
            description="New recipe",
        )

    assert not (registry_root / "shared" / "new-recipe").exists()


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


def test_register_recipe_force_replaces_recipe_and_registry(tmp_path):
    module = load_module()
    registry = tmp_path / "recipe-registry.json"
    registry.write_text("{}\n", encoding="utf-8")
    registry_root = tmp_path / "registry"
    args = dict(
        registry_path=registry,
        registry_root=registry_root,
        recipe_name="example",
        bucket="shared",
        rule_id="RULE",
        description="Original recipe",
    )

    assert module.register_recipe(**args) == "created"
    recipe_dir = registry_root / "shared" / "example"
    (recipe_dir / "SKILL.md").write_text("old skill\n", encoding="utf-8")

    args["description"] = "Updated recipe"
    assert module.register_recipe(**args, force=True) == "updated"
    assert (recipe_dir / "SKILL.md").read_text(encoding="utf-8").startswith("# example")
    assert json.loads(registry.read_text(encoding="utf-8"))["RULE"]["description"] == "Updated recipe"


def test_register_recipe_force_create_reports_created(tmp_path):
    module = load_module()
    registry = tmp_path / "recipe-registry.json"
    registry.write_text("{}\n", encoding="utf-8")

    assert module.register_recipe(
        registry_path=registry,
        registry_root=tmp_path / "registry",
        recipe_name="example",
        bucket="shared",
        rule_id="RULE",
        description="Recipe",
        force=True,
    ) == "created"


@pytest.mark.parametrize("target_kind", ["file", "symlink"])
def test_register_recipe_force_rejects_non_directory_target_without_mutation(tmp_path, target_kind):
    module = load_module()
    registry = tmp_path / "recipe-registry.json"
    registry.write_text("{}\n", encoding="utf-8")
    registry_root = tmp_path / "registry"
    target = registry_root / "shared" / "example"
    target.parent.mkdir(parents=True)
    if target_kind == "file":
        target.write_text("keep\n", encoding="utf-8")
    else:
        destination = tmp_path / "destination"
        destination.mkdir()
        try:
            target.symlink_to(destination, target_is_directory=True)
        except OSError:
            pytest.skip("symlinks are unavailable")
    before_registry = registry.read_bytes()

    expected = (
        "must be a directory" if target_kind == "file" else "must not be a symlink"
    )
    with pytest.raises(ValueError, match=expected):
        module.register_recipe(
            registry_path=registry,
            registry_root=registry_root,
            recipe_name="example",
            bucket="shared",
            rule_id="RULE",
            description="Recipe",
            force=True,
        )

    assert registry.read_bytes() == before_registry
    if target_kind == "symlink":
        assert target.is_symlink()
    else:
        assert target.read_text(encoding="utf-8") == "keep\n"


def test_register_recipe_source_dir_copies_recipe_files(tmp_path):
    module = load_module()
    registry = tmp_path / "recipe-registry.json"
    registry.write_text("{}\n", encoding="utf-8")
    source_dir = tmp_path / "source"
    (source_dir / "scripts").mkdir(parents=True)
    (source_dir / "SKILL.md").write_text("source skill\n", encoding="utf-8")
    (source_dir / "scripts" / "apply.py").write_text("source script\n", encoding="utf-8")

    module.register_recipe(
        registry_path=registry,
        registry_root=tmp_path / "registry",
        recipe_name="example",
        bucket="shared",
        rule_id="RULE",
        description="Recipe",
        source_dir=source_dir,
    )

    recipe_dir = tmp_path / "registry" / "shared" / "example"
    assert (recipe_dir / "SKILL.md").read_text(encoding="utf-8") == "source skill\n"
    assert (recipe_dir / "scripts" / "apply.py").read_text(encoding="utf-8") == "source script\n"


def test_register_recipe_rolls_back_recipe_when_registry_write_fails(tmp_path, monkeypatch):
    module = load_module()
    registry = tmp_path / "recipe-registry.json"
    registry.write_text("{}\n", encoding="utf-8")
    registry_root = tmp_path / "registry"
    args = dict(
        registry_path=registry,
        registry_root=registry_root,
        recipe_name="example",
        bucket="shared",
        rule_id="RULE",
        description="Original recipe",
    )
    module.register_recipe(**args)
    recipe_dir = registry_root / "shared" / "example"
    old_skill = "old skill\n"
    (recipe_dir / "SKILL.md").write_text(old_skill, encoding="utf-8")
    old_registry = registry.read_bytes()

    def fail_registry_write(path, payload):
        raise OSError("simulated registry failure")

    monkeypatch.setattr(module, "_write_json_atomic", fail_registry_write)
    updated_args = {**args, "description": "Updated recipe", "force": True}
    with pytest.raises(OSError, match="simulated registry failure"):
        module.register_recipe(**updated_args)

    assert (recipe_dir / "SKILL.md").read_text(encoding="utf-8") == old_skill
    assert registry.read_bytes() == old_registry


def test_recipe_registry_script_entries_resolve_to_files():
    module = load_module()
    registry_path = SCRIPT.parents[2] / "jade-core-rule-dispatcher" / "recipe-registry.json"
    registry_root = SCRIPT.parents[1]
    data = json.loads(registry_path.read_text(encoding="utf-8"))

    for rule_id, entry in data.items():
        if rule_id.startswith("_"):
            continue
        if entry.get("mode") == "agent":
            # Agent-mode entries (jade-core-rule-dispatcher's
            # --emit-agent-tasks / --record-agent-result) point at a
            # SKILL.md instead of a script -- see register_recipe.py's
            # _validate_agent_entry for the matching production check.
            assert isinstance(entry["skill_md"], str)
            relative_skill_md = pathlib.Path(entry["skill_md"])
            assert relative_skill_md.parts[:3] == (".claude", "skills", "java-migration-skill-registry")
            assert (SCRIPT.parents[4] / relative_skill_md).is_file(), rule_id
            continue
        assert isinstance(entry["script"], str)
        relative_script = pathlib.Path(entry["script"])
        assert relative_script.parts[:3] == (".claude", "skills", "java-migration-skill-registry")
        assert (SCRIPT.parents[4] / relative_script).is_file(), rule_id


def test_validate_registry_accepts_agent_mode_entry_with_valid_skill_md(tmp_path):
    module = load_module()
    registry_root = tmp_path / "registry"
    skill_md = registry_root / "shared" / "jade-recipe-agent-example" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text("# jade-recipe-agent-example\n", encoding="utf-8")

    # Must not raise: an entry with "mode": "agent" is validated through
    # skill_md rather than the script-mode "script" field.
    module._validate_registry(
        {
            "RULE": {
                "skill": "jade-recipe-agent-example",
                "skill_md": ".claude/skills/java-migration-skill-registry/shared/jade-recipe-agent-example/SKILL.md",
                "mode": "agent",
                "description": "agent-mode recipe",
            }
        },
        registry_root,
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"RULE": {"skill": "recipe", "mode": "agent", "description": "missing skill_md"}},
        {
            "RULE": {
                "skill": "recipe",
                "mode": "agent",
                "script": ".claude/skills/java-migration-skill-registry/shared/recipe/scripts/apply.py",
                "description": "script instead of skill_md",
            }
        },
        {
            "RULE": {
                "skill": "recipe",
                "mode": "agent",
                "skill_md": ".claude/skills/java-migration-skill-registry/shared/missing/SKILL.md",
                "description": "missing file",
            }
        },
        {
            "RULE": {
                "skill": "recipe",
                "mode": "agent",
                "skill_md": "unsafe/SKILL.md",
                "description": "unsafe path",
            }
        },
        {"RULE": {"skill": "recipe", "mode": "bogus", "script": "x", "description": "d"}},
    ],
)
def test_validate_registry_rejects_invalid_agent_mode_entries(tmp_path, payload):
    module = load_module()
    with pytest.raises(ValueError, match="invalid registry entry"):
        module._validate_registry(payload, tmp_path / "registry")


@pytest.mark.parametrize(
    "payload",
    [
        {"RULE": {"skill": "recipe", "description": "missing script"}},
        {"RULE": {"skill": "recipe", "script": "unsafe/apply.py", "description": "unsafe"}},
        {"RULE": {"skill": "recipe", "script": ".claude/skills/java-migration-skill-registry/shared/missing/apply.py", "description": "missing"}},
        {"RULE": {"skill": "recipe", "script": ".claude/skills/java-migration-skill-registry/shared/missing/scripts/apply.py", "description": "missing"}},
    ],
)
def test_register_recipe_rejects_invalid_existing_registry_entries(tmp_path, payload):
    module = load_module()
    registry = tmp_path / "recipe-registry.json"
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="invalid registry entry"):
        module.register_recipe(
            registry_path=registry,
            registry_root=tmp_path / "registry",
            recipe_name="example",
            bucket="shared",
            rule_id="NEW_RULE",
            description="Recipe",
        )


@pytest.mark.parametrize(
    "script",
    [
        ".claude/skills/java-migration-skill-registry/shared/recipe/apply.py",
        ".claude/skills/java-migration-skill-registry/shared/recipe/scripts/other.py",
        ".claude/skills/java-migration-skill-registry/shared/recipe/scripts/apply.py/extra",
        ".claude/skills/java-migration-skill-registry/shared/recipe/../other/scripts/apply.py",
        "./.claude/skills/java-migration-skill-registry/shared/recipe/scripts/apply.py",
        ".claude//skills/java-migration-skill-registry/shared/recipe/scripts/apply.py",
    ],
)
def test_register_recipe_rejects_noncanonical_script_paths(tmp_path, script):
    module = load_module()
    registry = tmp_path / "recipe-registry.json"
    registry.write_text(
        json.dumps({"RULE": {"skill": "recipe", "script": script, "description": "bad"}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid registry entry"):
        module.register_recipe(
            registry_path=registry,
            registry_root=tmp_path / "registry",
            recipe_name="new",
            bucket="shared",
            rule_id="NEW",
            description="Recipe",
        )


def test_register_recipe_rejects_script_symlink_outside_registry(tmp_path):
    module = load_module()
    registry_root = tmp_path / "registry"
    script = registry_root / "shared" / "recipe" / "scripts" / "apply.py"
    script.parent.mkdir(parents=True)
    outside = tmp_path / "outside.py"
    outside.write_text("", encoding="utf-8")
    try:
        script.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are unavailable")
    registry = tmp_path / "recipe-registry.json"
    registry.write_text(
        json.dumps({
            "RULE": {
                "skill": "recipe",
                "script": ".claude/skills/java-migration-skill-registry/shared/recipe/scripts/apply.py",
                "description": "bad",
            }
        }),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid registry entry"):
        module.register_recipe(
            registry_path=registry,
            registry_root=registry_root,
            recipe_name="new",
            bucket="shared",
            rule_id="NEW",
            description="Recipe",
        )


def test_register_recipe_rejects_script_symlink_inside_registry(tmp_path):
    module = load_module()
    registry_root = tmp_path / "registry"
    script = registry_root / "shared" / "recipe" / "scripts" / "apply.py"
    script.parent.mkdir(parents=True)
    target = registry_root / "shared" / "other.py"
    target.write_text("", encoding="utf-8")
    try:
        script.symlink_to(target)
    except OSError:
        pytest.skip("symlinks are unavailable")
    registry = tmp_path / "recipe-registry.json"
    registry.write_text(
        json.dumps({
            "RULE": {
                "skill": "recipe",
                "script": ".claude/skills/java-migration-skill-registry/shared/recipe/scripts/apply.py",
                "description": "bad",
            }
        }),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid registry entry"):
        module.register_recipe(
            registry_path=registry,
            registry_root=registry_root,
            recipe_name="new",
            bucket="shared",
            rule_id="NEW",
            description="Recipe",
        )


def test_register_recipe_rejects_symlink_recipe_dir_before_idempotent_return(tmp_path):
    module = load_module()
    registry = tmp_path / "recipe-registry.json"
    registry.write_text("{}\n", encoding="utf-8")
    registry_root = tmp_path / "registry"
    target = tmp_path / "target"
    (target / "scripts").mkdir(parents=True)
    (target / "SKILL.md").write_text("target\n", encoding="utf-8")
    (target / "scripts" / "apply.py").write_text("", encoding="utf-8")
    link = registry_root / "shared" / "recipe"
    link.parent.mkdir(parents=True)
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are unavailable")

    with pytest.raises(ValueError, match="must not be a symlink"):
        module.register_recipe(
            registry_path=registry,
            registry_root=registry_root,
            recipe_name="recipe",
            bucket="shared",
            rule_id="RULE",
            description="Recipe",
        )


def test_every_recipe_directory_has_one_registry_entry_with_canonical_script_layout():
    module = load_module()
    registry_path = SCRIPT.parents[2] / "jade-core-rule-dispatcher" / "recipe-registry.json"
    registry_root = SCRIPT.parents[1]
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    entries = [entry for rule_id, entry in data.items() if not rule_id.startswith("_")]

    for bucket in module.BUCKETS:
        bucket_dir = registry_root / bucket
        for recipe_dir in bucket_dir.iterdir():
            if not recipe_dir.is_dir():
                continue
            prefix = ".claude/skills/java-migration-skill-registry"
            expected_script = f"{prefix}/{bucket}/{recipe_dir.name}/scripts/apply.py"
            expected_skill_md = f"{prefix}/{bucket}/{recipe_dir.name}/SKILL.md"

            # An agent-mode recipe is a SKILL.md the dispatcher hands to a
            # subagent; it has no apply.py to run, so the canonical layout it
            # must satisfy is the skill_md one.
            agent_matches = [
                entry
                for entry in entries
                if entry.get("mode") == "agent" and entry.get("skill_md") == expected_skill_md
            ]
            if agent_matches:
                assert len(agent_matches) == 1, f"expected one registry entry for {recipe_dir}"
                assert (recipe_dir / "SKILL.md").is_file()
                assert not (recipe_dir / "scripts" / "apply.py").exists(), (
                    f"agent-mode recipe {recipe_dir} must not ship an apply.py"
                )
                continue

            matches = [entry for entry in entries if entry.get("script") == expected_script]
            assert len(matches) == 1, f"expected one registry entry for {recipe_dir}"
            assert (recipe_dir / "scripts" / "apply.py").is_file()
