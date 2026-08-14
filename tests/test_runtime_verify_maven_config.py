import importlib.util
import json
import pathlib


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNTIME_VERIFY_PATH = (
    REPO_ROOT / ".claude/skills/jade-core-verification/scripts/runtime_verify.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "runtime_verify_maven_config_test", RUNTIME_VERIFY_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_maven_config_accepts_project_root_inside_consumer(tmp_path):
    mod = _load_module()
    consumer = tmp_path / "consumer"
    (consumer / "jrba").mkdir(parents=True)

    normalized, errors = mod.validate_consumer_config(
        consumer,
        {"build_mode": "maven", "maven_project_root": "jrba"},
        tmp_path / "workspace",
    )

    assert errors == []
    assert normalized["build_mode"] == "maven"
    assert normalized["maven_project_root"] == "jrba"


def test_maven_config_rejects_missing_project_root(tmp_path):
    mod = _load_module()
    consumer = tmp_path / "consumer"
    consumer.mkdir()

    _, errors = mod.validate_consumer_config(
        consumer,
        {"build_mode": "maven"},
        tmp_path / "workspace",
    )

    assert any("maven_project_root" in error for error in errors)


def test_maven_config_rejects_project_root_outside_consumer(tmp_path):
    mod = _load_module()
    consumer = tmp_path / "consumer"
    consumer.mkdir()

    _, errors = mod.validate_consumer_config(
        consumer,
        {"build_mode": "maven", "maven_project_root": "../outside"},
        tmp_path / "workspace",
    )

    assert any("inside the consumer" in error for error in errors)


def test_config_defaults_to_backward_compatible_javac_mode(tmp_path):
    mod = _load_module()
    consumer = tmp_path / "consumer"
    consumer.mkdir()

    normalized, errors = mod.validate_consumer_config(
        consumer,
        {"name": "legacy"},
        tmp_path / "workspace",
    )

    assert errors == []
    assert normalized["build_mode"] == "javac"
    assert "maven_project_root" not in normalized


def test_config_rejects_non_string_build_mode(tmp_path):
    mod = _load_module()
    consumer = tmp_path / "consumer"
    consumer.mkdir()

    _, errors = mod.validate_consumer_config(
        consumer,
        {"build_mode": []},
        tmp_path / "workspace",
    )

    assert any("build_mode" in error for error in errors)


def test_config_rejects_null_classpath_deps(tmp_path):
    mod = _load_module()
    consumer = tmp_path / "consumer"
    consumer.mkdir()

    _, errors = mod.validate_consumer_config(
        consumer,
        {"classpath_deps": None},
        tmp_path / "workspace",
    )

    assert any("classpath_deps" in error for error in errors)


def test_config_rejects_string_classpath_deps(tmp_path):
    mod = _load_module()
    consumer = tmp_path / "consumer"
    consumer.mkdir()

    _, errors = mod.validate_consumer_config(
        consumer,
        {"classpath_deps": "jade.jar"},
        tmp_path / "workspace",
    )

    assert any("classpath_deps" in error for error in errors)


def test_config_rejects_unsafe_dependency_and_artifact_paths(tmp_path):
    mod = _load_module()
    consumer = tmp_path / "consumer"
    consumer.mkdir()

    _, errors = mod.validate_consumer_config(
        consumer,
        {
            "classpath_deps": ["../outside.jar"],
            "artifact_output_dir": "../outside-output",
        },
        tmp_path / "workspace",
    )

    assert any("classpath_deps" in error for error in errors)
    assert any("artifact_output_dir" in error for error in errors)


def test_discovery_records_invalid_top_level_config_values(tmp_path):
    mod = _load_module()
    mod.PLAYGROUND_DIR = tmp_path / "consumer-playground"

    for name, config in {
        "null": None,
        "list": [],
        "string": "invalid",
    }.items():
        project_dir = mod.PLAYGROUND_DIR / name
        project_dir.mkdir(parents=True)
        (project_dir / "test-config.json").write_text(
            json.dumps(config), encoding="utf-8"
        )

    discovered = mod.discover_consumers()

    assert len(discovered) == 3
    for project_dir, cfg in discovered:
        assert cfg["name"] == project_dir.name
        assert "invalid test-config.json" in cfg["_config_error"]
        result = mod.test_consumer(project_dir, tmp_path / "workspace", cfg)
        assert result["status"] == "FAIL"
        assert "Invalid consumer configuration" in result["error"]
