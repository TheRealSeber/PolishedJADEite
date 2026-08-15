import importlib.util
import json
import pathlib

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CONSUMER = REPO_ROOT / "consumer-playground" / "jrba"
CONFIG_PATH = CONSUMER / "test-config.json"


def _load_runtime_verify():
    path = REPO_ROOT / ".claude/skills/jade-core-verification/scripts/runtime_verify.py"
    spec = importlib.util.spec_from_file_location("runtime_verify_jrba_contract", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_jrba_contains_only_all_production_java_sources():
    sources = sorted((CONSUMER / "src/main/java").rglob("*.java"))

    assert len(sources) == 89
    assert all("/org/jrba/" in source.as_posix() for source in sources)
    assert (CONSUMER / "src/main/java/org/jrba/agentmodel/domain/AbstractAgent.java").is_file()


def test_jrba_maven_project_declares_workspace_compatible_dependencies():
    pom = (CONSUMER / "pom.xml").read_text(encoding="utf-8")

    assert "<maven.compiler.source>17</maven.compiler.source>" in pom
    assert "<maven.compiler.target>17</maven.compiler.target>" in pom
    assert "<maven.compiler.release>17</maven.compiler.release>" in pom
    assert "<artifactId>jade</artifactId>" in pom
    assert "<artifactId>easy-rules-core</artifactId>" in pom
    assert "<artifactId>mvel2</artifactId>" in pom
    assert "<groupId>com.tilab.jade</groupId>" in pom
    assert "<version>${jade.version}</version>" in pom
    assert "systemPath" not in pom


def test_jrba_config_uses_maven_verifier_contract():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    assert config["build_mode"] == "maven"
    assert config["maven_project_root"] == "."
    assert "Java 17 suffices" in config["description"]
    assert "record, pattern matching, switch expressions, Stream.toList, and List.of" in config["description"]
    assert config["docker_image"] == "${TARGET_DOCKER_IMAGE}"
    assert config["main_class"] == "jade.Boot"
    assert config["boot_args"] == ["-agents", "runner:org.jrba.consumer.JrbaIntegrationAgent"]
    assert config["source_level"] == 17
    assert config["runtime_java_version"] == 17
    assert config["jade_artifact"] == "jade.jar"
    assert config["expected_stdout_markers"] == [
        "JRBA_TEST_STARTED",
        "JRBA_BEHAVIOR_EXECUTED",
        "JRBA_TEST_PASSED",
    ]
    assert config["failure_stdout_markers"] == ["JRBA_TEST_FAILED"]
    assert config["timeout_seconds"] > 0


def test_jrba_consumer_has_no_binary_files():
    binaries = [
        path
        for path in CONSUMER.rglob("*")
        if path.is_file() and path.suffix.lower() in {".class", ".jar", ".war", ".zip"}
    ]

    assert binaries == []


def test_java_registry_rejects_unsupported_target_without_java_21_image():
    runtime_verify = _load_runtime_verify()
    registry = json.loads((REPO_ROOT / "config/docker-images.json").read_text())

    assert set(registry) == {"java-8", "java-11", "java-17"}
    assert runtime_verify.resolve_docker_image("17", registry) == registry["java-17"]
    with pytest.raises(ValueError, match="unsupported"):
        runtime_verify.resolve_docker_image("21", registry)
    for invalid_version in ("", "not-a-version"):
        with pytest.raises(ValueError, match="invalid or unsupported"):
            runtime_verify.resolve_docker_image(invalid_version, registry)


def test_jrba_agent_has_ordered_markers_and_one_exit_call():
    agent = (
        CONSUMER
        / "src/main/java/org/jrba/consumer/JrbaIntegrationAgent.java"
    ).read_text(encoding="utf-8")

    assert "extends AbstractAgent" in agent
    assert "super.setup()" in agent
    assert "prepareStartingBehaviours" in agent
    assert "ListenForControllerObjects" in agent
    assert "RulesController" in agent
    assert "setRulesController" in agent
    assert "getRulesController" in agent
    assert "SmokeRulesController" in agent
    assert "AgentBasicRule" in agent
    assert "super(null)" in agent
    assert "initializeRuleDescription" in agent
    assert "evaluateRule" in agent
    assert "executeRule" in agent
    assert "RuleSetRest" in agent
    assert "RuleSetFacts" in agent
    assert "RuleSet" in agent
    assert "rulesController.fire" in agent
    assert "JRBA_SMOKE_RULE" in agent
    assert "ruleExecuted" in agent
    assert "JRBA_BEHAVIOR_EXECUTED" in agent
    assert "doDelete()" in agent
    assert "takeDown()" in agent
    assert agent.index("JRBA_TEST_STARTED") < agent.index("JRBA_TEST_PASSED")
    assert agent.index("rulesController.fire") < agent.index("JRBA_BEHAVIOR_EXECUTED")
    assert agent.index("!smokeRule.ruleExecuted") < agent.index("JRBA_BEHAVIOR_EXECUTED")
    assert agent.index("JRBA_BEHAVIOR_EXECUTED") < agent.index("JRBA_TEST_PASSED")
    assert "JRBA_TEST_FAILED" in agent
    assert agent.count("System.exit(") == 1
