import importlib.util
import pathlib


SCRIPT_PATH = pathlib.Path(
    ".claude/skills/jade-core-tooling-scout/scripts/tooling_scout.py"
)


def _load_tooling_scout_module():
    spec = importlib.util.spec_from_file_location("tooling_scout", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_java_home_env_uses_process_environment(monkeypatch):
    tooling_scout = _load_tooling_scout_module()
    monkeypatch.setenv("PATH", "C:/Windows/System32")
    jdk_path = pathlib.Path("C:/Program Files/Java/jdk-25.0.2")

    env = tooling_scout.java_home_env(jdk_path)

    assert env["JAVA_HOME"] == str(jdk_path)
    assert env["PATH"].startswith(str(jdk_path / "bin"))
