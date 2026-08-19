import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / ".claude/skills/jade-core-batch-processor/scripts/rule_batch_runner.py"


def load_batch():
    spec = importlib.util.spec_from_file_location("batch_graph_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def inputs(tmp_path, flags):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "04-flag-index.json").write_text(json.dumps({"flags": flags}), encoding="utf-8")
    (artifacts / "05-rule-queue.json").write_text(json.dumps({"rules": ["RULE"]}), encoding="utf-8")
    return artifacts


def test_impact_files_only_input_uses_canonical_files_and_reasons(tmp_path):
    batch = load_batch()
    flags = [{
        "rule_id": "RULE", "file": "A.java", "line": 1,
        "graph": {
            "impact_files": ["B.java", "C.java"],
            "direct_impact_files": ["B.java"],
            "transitive_impact_files": ["C.java"],
            "paths": [{"file": "C.java", "path": ["A.java", "B.java", "C.java"], "reasons": ["calls"]}],
        },
    }]
    impact = batch.build_impact_only_list("RULE", {"flags": flags})
    assert [item["file"] for item in impact] == ["B.java", "C.java"]
    assert impact[1]["reasons"] == ["calls"]
    assert impact[1]["paths"][0]["path"] == ["A.java", "B.java", "C.java"]


def test_missing_canonical_impact_files_does_not_reconstruct_scope(tmp_path, capsys):
    batch = load_batch()
    flags = [{
        "rule_id": "RULE", "file": "A.java", "line": 1,
        "graph": {
            "direct_impact_files": ["B.java"],
            "transitive_impact_files": ["C.java"],
            "paths": [{"file": "C.java", "path": ["A.java", "C.java"], "reasons": ["calls"]}],
        },
    }]
    assert batch.build_impact_only_list("RULE", {"flags": flags}) == []
    assert "impact_files" in capsys.readouterr().err


def test_prepare_is_byte_deterministic(tmp_path):
    batch = load_batch()
    artifacts = inputs(tmp_path, [{"rule_id": "RULE", "file": "A.java", "line": 1}])
    assert batch.cmd_prepare(artifacts, "RULE", "run-1") == 0
    first = (artifacts / "05-rule-batch-RULE.json").read_bytes(), (artifacts / "05-rule-batch-status.json").read_bytes()
    assert batch.cmd_prepare(artifacts, "RULE", "run-1") == 0
    second = (artifacts / "05-rule-batch-RULE.json").read_bytes(), (artifacts / "05-rule-batch-status.json").read_bytes()
    assert first == second


def test_prepare_cli_supports_artifacts_dir_and_existing_artifacts_alias(tmp_path):
    artifacts = inputs(tmp_path, [{"rule_id": "RULE", "file": "A.java", "line": 1}])
    for option in ("--artifacts-dir", "--artifacts"):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), option, str(artifacts), "prepare", "--rule-id", "RULE", "--run-id", "run-1"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
