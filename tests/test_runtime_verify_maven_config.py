import importlib.util
import json
import pathlib
import sys


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


def test_maven_config_rejects_unsafe_artifact_and_runtime_paths(tmp_path):
    mod = _load_module()
    consumer = tmp_path / "consumer"
    (consumer / "maven").mkdir(parents=True)

    _, errors = mod.validate_consumer_config(
        consumer,
        {
            "build_mode": "maven",
            "maven_project_root": "maven",
            "jade_artifact": "../outside.jar",
            "maven_runtime_lib_dir": "../outside-libs",
        },
        tmp_path / "workspace",
    )

    assert any("jade_artifact" in error for error in errors)
    assert any("maven_runtime_lib_dir" in error for error in errors)


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


def test_discovery_keeps_malformed_config_as_failed_consumer(tmp_path):
    mod = _load_module()
    mod.PLAYGROUND_DIR = tmp_path / "consumer-playground"

    malformed = mod.PLAYGROUND_DIR / "malformed"
    malformed.mkdir(parents=True)
    (malformed / "test-config.json").write_text('{"name":', encoding="utf-8")

    valid = mod.PLAYGROUND_DIR / "valid"
    valid.mkdir(parents=True)
    valid_config = {"name": "valid", "classpath_deps": []}
    (valid / "test-config.json").write_text(
        json.dumps(valid_config), encoding="utf-8"
    )

    discovered = mod.discover_consumers()
    discovered_by_name = {project.name: cfg for project, cfg in discovered}

    assert set(discovered_by_name) == {"malformed", "valid"}
    assert discovered_by_name["valid"] == valid_config
    assert "invalid test-config.json" in discovered_by_name["malformed"]["_config_error"]

    result = mod.test_consumer(
        malformed, tmp_path / "workspace", discovered_by_name["malformed"]
    )
    assert result["status"] == "FAIL"
    assert "Invalid consumer configuration" in result["error"]


def test_discovery_records_invalid_utf8_as_failed_consumer(tmp_path):
    mod = _load_module()
    mod.PLAYGROUND_DIR = tmp_path / "consumer-playground"

    invalid = mod.PLAYGROUND_DIR / "invalid-utf8"
    invalid.mkdir(parents=True)
    (invalid / "test-config.json").write_bytes(b'{"name": "\xff')

    valid = mod.PLAYGROUND_DIR / "valid"
    valid.mkdir(parents=True)
    valid_config = {"name": "valid", "classpath_deps": []}
    (valid / "test-config.json").write_text(
        json.dumps(valid_config), encoding="utf-8"
    )

    discovered = mod.discover_consumers()
    discovered_by_name = {project.name: cfg for project, cfg in discovered}

    assert set(discovered_by_name) == {"invalid-utf8", "valid"}
    assert discovered_by_name["valid"] == valid_config
    assert "invalid test-config.json" in discovered_by_name["invalid-utf8"][
        "_config_error"
    ]

    result = mod.test_consumer(
        invalid, tmp_path / "workspace", discovered_by_name["invalid-utf8"]
    )
    assert result["status"] == "FAIL"
    assert "Invalid consumer configuration" in result["error"]


def _write_fake_maven(path, *, exit_code=0, args_path=None):
    args_target = str(args_path or pathlib.Path("maven-args.txt"))
    path.write_text(
        "import pathlib, sys\n"
        f"args = pathlib.Path({args_target!r})\n"
        "args.write_text('\\n'.join(sys.argv[1:]), encoding='utf-8')\n"
        "if " + str(exit_code) + " == 0:\n"
        "    pathlib.Path('target/classes').mkdir(parents=True, exist_ok=True)\n"
        "    pathlib.Path('target/classes/Consumer.class').write_bytes(b'class')\n"
        "    pathlib.Path('target/dependency').mkdir(parents=True, exist_ok=True)\n"
        "    pathlib.Path('target/dependency/runtime.jar').write_bytes(b'jar')\n"
        "print('fake maven output', file=sys.stderr)\n"
        "sys.exit(" + str(exit_code) + ")\n",
        encoding="utf-8",
    )


def _write_fake_maven_sequence(path, invocations_path):
    path.write_text(
        "import pathlib, sys\n"
        f"log = pathlib.Path({str(invocations_path)!r})\n"
        "with log.open('a', encoding='utf-8') as stream:\n"
        "    stream.write('\\n'.join(sys.argv[1:]) + '\\n---\\n')\n"
        "if 'package' in sys.argv:\n"
        "    pathlib.Path('target/classes').mkdir(parents=True, exist_ok=True)\n"
        "    pathlib.Path('target/classes/Consumer.class').write_bytes(b'class')\n"
        "    pathlib.Path('target/dependency').mkdir(parents=True, exist_ok=True)\n"
        "    pathlib.Path('target/dependency/runtime.jar').write_bytes(b'jar')\n",
        encoding="utf-8",
    )


def test_maven_runtime_lib_dir_cannot_escape_build_dir(tmp_path):
    mod = _load_module()
    consumer = tmp_path / "consumer"
    (consumer / "maven").mkdir(parents=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "jade.jar").write_bytes(b"jade")

    ok, output = mod.build_maven_consumer(
        consumer,
        workspace,
        {
            "maven_project_root": "maven",
            "classpath_deps": ["jade.jar"],
            "maven_runtime_lib_dir": "../escape",
        },
        tmp_path / "build",
    )

    assert not ok
    assert "maven_runtime_lib_dir" in output


def test_explicit_jade_artifact_is_present_in_runtime_classpath():
    mod = _load_module()

    classpath = mod.consumer_classpath(
        {
            "build_mode": "maven",
            "jade_artifact": "artifacts/jade.jar",
            "classpath_deps": [],
        }
    )

    assert "/ws/artifacts/jade.jar" in classpath


def test_maven_does_not_stage_stale_target_files(tmp_path):
    mod = _load_module()
    consumer = tmp_path / "consumer"
    project = consumer / "maven"
    (project / "target/classes").mkdir(parents=True)
    (project / "target/classes/Stale.class").write_bytes(b"stale")
    (project / "target/dependency").mkdir(parents=True)
    (project / "target/dependency/stale.jar").write_bytes(b"stale")
    (project / "pom.xml").write_text("<project/>", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "jade.jar").write_bytes(b"jade")
    fake_maven = tmp_path / "mvn.py"
    _write_fake_maven(fake_maven, args_path=project / "maven-args.txt")
    build_dir = tmp_path / "build"

    ok, output = mod.build_maven_consumer(
        consumer,
        workspace,
        {
            "maven_project_root": "maven",
            "classpath_deps": ["jade.jar"],
            "maven_executable": [sys.executable, str(fake_maven)],
        },
        build_dir,
    )

    assert ok, output
    assert not (build_dir / "Stale.class").exists()
    assert not (build_dir / "lib" / "stale.jar").exists()
    assert (project / "target/classes/Stale.class").exists()
    assert (project / "target/dependency/stale.jar").exists()


def test_nonzero_docker_exit_fails_even_when_markers_exist(tmp_path, monkeypatch):
    mod = _load_module()
    project = tmp_path / "consumer"
    project.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    cfg = {
        "name": "consumer",
        "classpath_deps": [],
        "expected_stdout_markers": ["PASS"],
    }
    monkeypatch.setattr(mod, "compile_consumer", lambda *args: (True, ""))
    monkeypatch.setattr(
        mod, "run_in_docker", lambda *args: (1, "PASS", "")
    )

    result = mod.test_consumer(project, workspace, cfg)

    assert result["status"] == "FAIL"
    assert "exited with code" in result["error"]


def test_maven_build_stages_classes_and_runtime_jars(tmp_path, monkeypatch):
    mod = _load_module()
    consumer = tmp_path / "consumer"
    project = consumer / "maven"
    project.mkdir(parents=True)
    (project / "pom.xml").write_text("<project/>", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    jade = workspace / "jade.jar"
    jade.write_bytes(b"jade")
    fake_maven = tmp_path / "mvn.py"
    _write_fake_maven(fake_maven, args_path=project / "maven-args.txt")
    build_dir = tmp_path / "build"
    monkeypatch.setattr(mod.shutil, "which", lambda name: sys.executable if name == "mvn" else None)

    ok, output = mod.build_maven_consumer(
        consumer,
        workspace,
        {
            "maven_project_root": "maven",
            "classpath_deps": ["jade.jar"],
            "maven_executable": [sys.executable, str(fake_maven)],
        },
        build_dir,
    )

    assert ok, output
    assert (build_dir / "Consumer.class").read_bytes() == b"class"
    assert (build_dir / "lib" / "runtime.jar").read_bytes() == b"jar"
    args = (project / "maven-args.txt").read_text(encoding="utf-8")
    assert "-B" in args
    assert "-ntp" in args
    assert "-Dmaven.repo.local=" in args
    assert f"-Djade.artifact={jade.resolve()}" not in args
    assert "dependency:copy-dependencies" in args


def test_maven_build_installs_workspace_jade_before_package(tmp_path):
    mod = _load_module()
    consumer = tmp_path / "consumer"
    project = consumer / "maven"
    project.mkdir(parents=True)
    (project / "pom.xml").write_text("<project/>", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    jade = workspace / "jade.jar"
    jade.write_bytes(b"jade")
    fake_maven = tmp_path / "mvn.py"
    invocations = tmp_path / "maven-invocations.txt"
    _write_fake_maven_sequence(fake_maven, invocations)

    ok, output = mod.build_maven_consumer(
        consumer,
        workspace,
        {
            "maven_project_root": "maven",
            "classpath_deps": ["jade.jar"],
            "maven_executable": [sys.executable, str(fake_maven)],
        },
        tmp_path / "build",
    )

    assert ok, output
    invocations_text = invocations.read_text(encoding="utf-8")
    install, package = invocations_text.split("---\n")[:2]
    assert "maven-install-plugin:3.1.2:install-file" in install
    assert f"-Dfile={jade.resolve()}" in install
    assert "-DgroupId=com.tilab.jade" in install
    assert "-DartifactId=jade" in install
    assert "-Dversion=4.6" in install
    assert "package" in package
    assert "-Dmaven.repo.local=" in package
    assert "-Djade.artifact=" not in package


def test_failure_stdout_markers_fail_even_when_expected_markers_and_rc_pass(
    tmp_path, monkeypatch
):
    mod = _load_module()
    project = tmp_path / "consumer"
    project.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    cfg = {
        "name": "consumer",
        "classpath_deps": [],
        "expected_stdout_markers": ["PASS"],
        "failure_stdout_markers": ["FAIL"],
    }
    monkeypatch.setattr(mod, "compile_consumer", lambda *args: (True, ""))
    monkeypatch.setattr(mod, "run_in_docker", lambda *args: (0, "PASS FAIL", ""))

    result = mod.test_consumer(project, workspace, cfg)

    assert result["status"] == "FAIL"
    assert "Configured failure markers" in result["error"]


def test_singular_failure_stdout_marker_remains_supported(tmp_path, monkeypatch):
    mod = _load_module()
    project = tmp_path / "consumer"
    project.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    cfg = {
        "name": "consumer",
        "classpath_deps": [],
        "expected_stdout_markers": ["PASS"],
        "failure_stdout_marker": "FAIL",
    }
    monkeypatch.setattr(mod, "compile_consumer", lambda *args: (True, ""))
    monkeypatch.setattr(mod, "run_in_docker", lambda *args: (0, "PASS FAIL", ""))

    result = mod.test_consumer(project, workspace, cfg)

    assert result["status"] == "FAIL"
    assert "Configured failure markers" in result["error"]


def test_maven_build_returns_actionable_failure(tmp_path, monkeypatch):
    mod = _load_module()
    consumer = tmp_path / "consumer"
    project = consumer / "maven"
    project.mkdir(parents=True)
    (project / "pom.xml").write_text("<project/>", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "jade.jar").write_bytes(b"jade")
    fake_maven = tmp_path / "mvn.py"
    _write_fake_maven(fake_maven, exit_code=7)
    monkeypatch.setattr(mod.shutil, "which", lambda name: sys.executable if name == "mvn" else None)

    ok, output = mod.build_maven_consumer(
        consumer,
        workspace,
        {
            "maven_project_root": "maven",
            "classpath_deps": ["jade.jar"],
            "maven_executable": [sys.executable, str(fake_maven)],
        },
        tmp_path / "build",
    )

    assert not ok
    assert "Maven JADE artifact install failed (exit 7)" in output
    assert "fake maven output" in output


def test_maven_runtime_classpath_includes_staged_dependency_dir(tmp_path):
    mod = _load_module()
    cfg = {
        "build_mode": "maven",
        "classpath_deps": ["lib/jade.jar"],
        "maven_runtime_lib_dir": "lib",
    }

    assert mod.consumer_classpath(cfg) == ["/playground", "/ws/lib/jade.jar", "/playground/lib/*"]
