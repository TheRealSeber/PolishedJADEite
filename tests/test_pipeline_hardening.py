import importlib.util
import pathlib


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
BUILD_AUDIT_PATH = (
    REPO_ROOT / ".claude/skills/jade-core-build-fixer/scripts/build_audit.py"
)
RUNTIME_VERIFY_PATH = (
    REPO_ROOT / ".claude/skills/jade-core-verification/scripts/runtime_verify.py"
)


def _load_module(module_path: pathlib.Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_build_audit_resolves_registry_image_for_target_java():
    mod = _load_module(BUILD_AUDIT_PATH, "build_audit_hardening_test")
    registry = {
        "java-8": "frekele/ant:1.10.3-jdk8",
        "java-11": "maven:3.8-eclipse-temurin-11",
        "java-17": "eclipse-temurin:17-jre",
        "java-21": "maven:3.9-eclipse-temurin-21",
    }

    assert mod.resolve_docker_image("1.6", registry) == "frekele/ant:1.10.3-jdk8"
    assert mod.resolve_docker_image("11", registry) == "maven:3.8-eclipse-temurin-11"
    assert mod.resolve_docker_image("17", registry) == "eclipse-temurin:17-jre"
    assert mod.resolve_docker_image("21", registry) == "maven:3.9-eclipse-temurin-21"


def test_build_audit_flags_java11_removed_dependencies_as_blocker():
    mod = _load_module(BUILD_AUDIT_PATH, "build_audit_dependency_test")
    deps = [
        {
            "groupId": "javax.xml.bind",
            "artifactId": "jaxb-api",
            "version": "2.2.11",
        },
        {
            "groupId": "com.sun.corba",
            "artifactId": "corba-api",
            "version": "1.0",
        },
    ]

    report = mod.audit_dependencies("maven", deps, "11")

    assert report["risk_level"] == "BLOCKER"
    assert report["blockers"]
    assert any(
        x["dependency"] == "javax.xml.bind:jaxb-api:2.2.11" for x in report["blockers"]
    )
    assert any(
        x["dependency"] == "com.sun.corba:corba-api:1.0" for x in report["blockers"]
    )


def test_build_audit_produces_upgrade_candidates_for_old_deps():
    mod = _load_module(BUILD_AUDIT_PATH, "build_audit_upgrade_test")
    deps = [
        {
            "groupId": "javax.xml.bind",
            "artifactId": "jaxb-api",
            "version": "2.2.11",
        }
    ]

    report = mod.audit_dependencies("maven", deps, "11")
    candidates = report["upgrade_candidates"]

    assert candidates
    assert candidates[0]["dependency"] == "javax.xml.bind:jaxb-api:2.2.11"
    assert candidates[0]["recommended_version"]


def test_runtime_verify_resolves_placeholder_from_registry_and_target():
    mod = _load_module(RUNTIME_VERIFY_PATH, "runtime_verify_hardening_test")
    registry = {
        "java-8": "frekele/ant:1.10.3-jdk8",
        "java-11": "maven:3.8-eclipse-temurin-11",
        "java-17": "eclipse-temurin:17-jre",
        "java-21": "maven:3.9-eclipse-temurin-21",
    }
    consumer_cfg = {"docker_image": "${TARGET_DOCKER_IMAGE}"}
    run_cfg = {"target_version": "17"}

    resolved = mod.resolve_consumer_docker_image(consumer_cfg, run_cfg, registry)
    assert resolved == "eclipse-temurin:17-jre"

    run_cfg["target_version"] = "21"
    assert mod.resolve_consumer_docker_image(consumer_cfg, run_cfg, registry) == (
        "maven:3.9-eclipse-temurin-21"
    )
