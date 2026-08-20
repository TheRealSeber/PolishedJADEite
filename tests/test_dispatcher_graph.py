import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / ".claude/skills/jade-core-rule-dispatcher/scripts/dispatcher.py"

RULE_ID = "DUMMY_TEST_RULE"
FILE_REL = "TestFile.java"


def load_dispatcher():
    spec = importlib.util.spec_from_file_location("dispatcher_graph_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def make_artifacts(tmp_path, flags):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "01-breaking-changes-manifest.json").write_text(
        json.dumps(
            {
                "rules": [
                    {
                        "id": RULE_ID,
                        "fix_strategy": "recipe:dummy",
                        "verification_hint": "hint",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (artifacts / f"05-rule-batch-{RULE_ID}.json").write_text(
        json.dumps(
            {
                "rule_id": RULE_ID,
                "files": [{"file": FILE_REL, "flags": flags, "status": "PENDING"}],
                "impact_only": [],
            }
        ),
        encoding="utf-8",
    )
    return artifacts


def run_cli(tmp_path, module, flags, monkeypatch, recipe_result=None):
    artifacts = make_artifacts(tmp_path, flags)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / FILE_REL).write_text("class TestFile {}\n", encoding="utf-8")

    captured = {}

    def fake_dispatch(script_path, file_path, line):
        captured["script_path"] = script_path
        captured["file_path"] = file_path
        captured["line"] = line
        return recipe_result or {
            "status": "FIXED",
            "changes": 1,
            "warnings": [],
            "errors": [],
            "diff_summary": "1 change(s)",
        }

    monkeypatch.setattr(module, "dispatch_recipe", fake_dispatch)

    old_argv = sys.argv
    try:
        sys.argv = [
            "dispatcher",
            "--artifacts-dir",
            str(artifacts),
            "--rule-id",
            RULE_ID,
            "--task-id",
            f"{RULE_ID}-TestFile",
            "--workspace-root",
            str(workspace),
        ]
        rc = module.main()
    finally:
        sys.argv = old_argv

    results = json.loads(
        (artifacts / f"06-fix-results-{RULE_ID}.json").read_text(encoding="utf-8")
    )
    return rc, results, captured


def test_graph_context_recorded_without_changing_recipe_args(tmp_path, monkeypatch):
    dispatcher = load_dispatcher()
    flags = [
        {
            "rule_id": RULE_ID,
            "file": FILE_REL,
            "line": 5,
            "graph": {
                "status": "available",
                "source_artifact": "03.5-knowledge-graph.json",
                "declaration": {"path": FILE_REL, "class_name": "TestFile"},
                "impact_files": ["B.java", "C.java"],
                "diagnostics": [],
            },
        }
    ]
    rc, results, captured = run_cli(tmp_path, dispatcher, flags, monkeypatch)
    assert rc == 0
    assert captured["script_path"].endswith("apply.py")
    assert captured["file_path"].endswith(FILE_REL)
    assert captured["line"] == 5
    r = results[0]
    assert r["status"] == "FIXED"
    assert r["graph_context"]["status"] == "available"
    assert r["graph_context"]["target_node"]["class_name"] == "TestFile"
    assert r["graph_context"]["impact_files"] == ["B.java", "C.java"]
    assert r["graph_context"]["source_artifact"] == "03.5-knowledge-graph.json"


def test_missing_graph_context_marks_unavailable(tmp_path, monkeypatch):
    dispatcher = load_dispatcher()
    flags = [{"rule_id": RULE_ID, "file": FILE_REL, "line": 5}]
    rc, results, captured = run_cli(tmp_path, dispatcher, flags, monkeypatch)
    assert rc == 0
    r = results[0]
    assert r["graph_context"]["status"] == "unavailable"
    assert any(
        d.get("kind") == "graph_unavailable" for d in r["graph_context"]["diagnostics"]
    )


def test_malformed_graph_warns_and_preserves_behavior(tmp_path, monkeypatch):
    dispatcher = load_dispatcher()
    flags = [{"rule_id": RULE_ID, "file": FILE_REL, "line": 5, "graph": ["not", "a", "dict"]}]
    rc, results, captured = run_cli(tmp_path, dispatcher, flags, monkeypatch)
    assert rc == 0
    r = results[0]
    assert r["status"] == "FIXED"
    assert r["graph_context"]["status"] == "unavailable"
    assert any(
        d.get("kind") == "graph_malformed" for d in r["graph_context"]["diagnostics"]
    )
    assert any(d.get("kind") == "graph_malformed" for d in r["warnings"])


def test_malformed_impact_files_normalized_to_empty_list(tmp_path, monkeypatch):
    dispatcher = load_dispatcher()
    flags = [
        {
            "rule_id": RULE_ID,
            "file": FILE_REL,
            "line": 5,
            "graph": {"status": "available", "impact_files": "not-a-list"},
        }
    ]
    rc, results, captured = run_cli(tmp_path, dispatcher, flags, monkeypatch)
    assert rc == 0
    assert results[0]["graph_context"]["impact_files"] == []


def test_malformed_diagnostics_normalized_to_empty_list(tmp_path, monkeypatch):
    dispatcher = load_dispatcher()
    flags = [
        {
            "rule_id": RULE_ID,
            "file": FILE_REL,
            "line": 5,
            "graph": {"status": "unavailable", "diagnostics": "boom-msg"},
        }
    ]
    rc, results, captured = run_cli(tmp_path, dispatcher, flags, monkeypatch)
    assert rc == 0
    r = results[0]
    assert r["status"] == "FIXED"
    assert r["graph_context"]["diagnostics"] == []
    assert r["warnings"] == []


def test_record_result_backward_compatible_without_graph_context(tmp_path):
    dispatcher = load_dispatcher()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    path = dispatcher.record_result(
        artifacts, "task-1", "RULE", "F.java", "FIXED", 1, "ctx", "diff", "hint", [], [], 1, 1
    )
    results = json.loads(path.read_text(encoding="utf-8"))
    assert len(results) == 1
    assert results[0]["status"] == "FIXED"
    assert "graph_context" not in results[0]

    path = dispatcher.record_result(
        artifacts,
        "task-2",
        "RULE",
        "F.java",
        "FIXED",
        1,
        "ctx",
        "diff",
        "hint",
        [],
        [],
        1,
        1,
        {"status": "available", "impact_files": []},
    )
    results = json.loads(path.read_text(encoding="utf-8"))
    assert len(results) == 2
    assert results[1]["graph_context"]["status"] == "available"