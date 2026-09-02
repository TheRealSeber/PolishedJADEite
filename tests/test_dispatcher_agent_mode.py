"""Tests for dispatcher.py agent mode: --emit-agent-tasks and --record-agent-result.

registry_modes.py is owned by a separate stream and is stubbed out here via
monkeypatch.setattr(module, "_registry_modes", FakeRegistryModes) rather than
relying on the real file existing on disk -- see dispatcher.py's
_load_registry_modes() docstring.
"""

import importlib.util
import json
import pathlib

import pytest


SCRIPT = pathlib.Path(__file__).parents[1] / ".claude/skills/jade-core-rule-dispatcher/scripts/dispatcher.py"
REPO_ROOT = pathlib.Path(__file__).parents[1]
REAL_SHARD_PLAN = (
    REPO_ROOT / "migration-runs/jade-1.7-to-1.8/artifacts/05-rule-shards-THREAD_STOP_DISABLED.json"
)
REAL_WORKSPACE = REPO_ROOT / "migration-runs/jade-1.7-to-1.8/workspace"


def load_module():
    spec = importlib.util.spec_from_file_location("dispatcher", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeRegistryModes:
    """Minimal stand-in for registry_modes.py's entry_mode()."""

    @staticmethod
    def entry_mode(entry):
        mode = entry.get("mode")
        if mode is None:
            return "script"
        if mode not in ("script", "agent"):
            raise ValueError(
                f"Recipe registry entry 'mode' must be one of ('script', 'agent'): {mode!r}"
            )
        return mode


def _agent_registry_entry(rule_id="RULE", skill="jade-recipe-agent-example"):
    return {
        rule_id: {
            "skill": skill,
            "skill_md": (
                f".claude/skills/java-migration-skill-registry/shared/{skill}/SKILL.md"
            ),
            "mode": "agent",
            "description": "agent-mode test recipe",
        }
    }


def _write_manifest(artifacts, rule_id="RULE", **extra):
    rule = {"id": rule_id, "fix_strategy": "recipe:agent", "verification_hint": "check manually"}
    rule.update(extra)
    (artifacts / "01-breaking-changes-manifest.json").write_text(
        json.dumps({"rules": [rule]}), encoding="utf-8"
    )


def _write_shard_plan(artifacts, rule_id="RULE", shards=None, status="OK", warnings=None):
    if shards is None:
        shards = [
            {
                "shard_id": f"{rule_id}-body-local-001",
                "rule_id": rule_id,
                "class": "body-local",
                "editable_files": ["Example1.java", "Example2.java"],
                "read_only_context": ["Other.java"],
                "entry_points": [
                    {"file": "Example1.java", "line": 10},
                    {"file": "Example2.java", "line": 5},
                ],
                "invariants": ["EDITS_CONFINED_TO_EDITABLE_FILES"],
                "graph_artifact": "artifacts/03.5-knowledge-graph.json",
                "parallel_safe": True,
            }
        ]
    payload = {
        "schema_version": 1,
        "run_id": "test-run",
        "rule_id": rule_id,
        "status": status,
        "blast_class": "body-local",
        "shard_count": len(shards),
        "shards": shards,
        "warnings": warnings or [],
    }
    path = artifacts / f"05-rule-shards-{rule_id}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _setup_common(tmp_path, monkeypatch, module, rule_id="RULE", **manifest_extra):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _write_manifest(artifacts, rule_id=rule_id, **manifest_extra)
    monkeypatch.setattr(module, "load_registry", lambda: _agent_registry_entry(rule_id))
    monkeypatch.setattr(module, "_registry_modes", FakeRegistryModes)
    return artifacts


# ---------------------------------------------------------------------------
# --emit-agent-tasks
# ---------------------------------------------------------------------------


def test_emit_agent_tasks_writes_contract_for_real_thread_stop_plan(tmp_path, monkeypatch):
    module = load_module()
    artifacts = _setup_common(tmp_path, monkeypatch, module, rule_id="THREAD_STOP_DISABLED")
    plan_text = REAL_SHARD_PLAN.read_text(encoding="utf-8")
    (artifacts / "05-rule-shards-THREAD_STOP_DISABLED.json").write_text(plan_text, encoding="utf-8")

    rc = module.main(
        [
            "--artifacts-dir", str(artifacts),
            "--rule-id", "THREAD_STOP_DISABLED",
            "--emit-agent-tasks",
            "--workspace-root", str(REAL_WORKSPACE),
        ]
    )

    assert rc == 0
    output = json.loads(
        (artifacts / "05-agent-tasks-THREAD_STOP_DISABLED.json").read_text(encoding="utf-8")
    )
    assert output["task_count"] == 6
    assert len(output["tasks"]) == 6
    shard_ids = [t["shard_id"] for t in output["tasks"]]
    assert shard_ids == sorted(shard_ids)
    assert output["mode"] == "agent"
    assert output["rule_id"] == "THREAD_STOP_DISABLED"
    for task in output["tasks"]:
        for key in (
            "checkpoint_command", "verify_command", "gate_command",
            "record_command", "accept_command", "rollback_command",
        ):
            assert task[key]


def test_emit_agent_tasks_contains_no_source_file_content(tmp_path, monkeypatch):
    module = load_module()
    artifacts = _setup_common(tmp_path, monkeypatch, module, rule_id="THREAD_STOP_DISABLED")
    plan_text = REAL_SHARD_PLAN.read_text(encoding="utf-8")
    plan = json.loads(plan_text)
    (artifacts / "05-rule-shards-THREAD_STOP_DISABLED.json").write_text(plan_text, encoding="utf-8")

    rc = module.main(
        [
            "--artifacts-dir", str(artifacts),
            "--rule-id", "THREAD_STOP_DISABLED",
            "--emit-agent-tasks",
            "--workspace-root", str(REAL_WORKSPACE),
        ]
    )
    assert rc == 0

    output_text = (artifacts / "05-agent-tasks-THREAD_STOP_DISABLED.json").read_text(
        encoding="utf-8"
    )

    editable_files = sorted(
        {f for shard in plan["shards"] for f in shard["editable_files"]}
    )
    assert editable_files, "fixture shard plan must have editable files"
    checked_any = False
    for rel in editable_files:
        source_path = REAL_WORKSPACE / rel
        for line in source_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped:
                checked_any = True
                assert stripped not in output_text
                break
    assert checked_any


def test_emit_agent_tasks_rejects_overlapping_shards(tmp_path, monkeypatch):
    module = load_module()
    shards = [
        {
            "shard_id": "RULE-body-local-001",
            "rule_id": "RULE",
            "class": "body-local",
            "editable_files": ["Shared.java"],
            "read_only_context": [],
            "entry_points": [{"file": "Shared.java", "line": 1}],
            "invariants": ["EDITS_CONFINED_TO_EDITABLE_FILES"],
            "graph_artifact": "artifacts/graph.json",
            "parallel_safe": True,
        },
        {
            "shard_id": "RULE-body-local-002",
            "rule_id": "RULE",
            "class": "body-local",
            "editable_files": ["Shared.java"],
            "read_only_context": [],
            "entry_points": [{"file": "Shared.java", "line": 2}],
            "invariants": ["EDITS_CONFINED_TO_EDITABLE_FILES"],
            "graph_artifact": "artifacts/graph.json",
            "parallel_safe": True,
        },
    ]
    artifacts = _setup_common(tmp_path, monkeypatch, module)
    _write_shard_plan(artifacts, shards=shards)

    rc = module.main(
        [
            "--artifacts-dir", str(artifacts),
            "--rule-id", "RULE",
            "--emit-agent-tasks",
            "--workspace-root", str(tmp_path),
        ]
    )

    assert rc == 3
    assert not (artifacts / "05-agent-tasks-RULE.json").exists()


@pytest.mark.parametrize("status", ["UNCLASSIFIED", "EMPTY"])
def test_emit_agent_tasks_rejects_plan_status_not_ok(tmp_path, monkeypatch, status):
    module = load_module()
    artifacts = _setup_common(tmp_path, monkeypatch, module)
    _write_shard_plan(artifacts, shards=[], status=status)

    rc = module.main(
        [
            "--artifacts-dir", str(artifacts),
            "--rule-id", "RULE",
            "--emit-agent-tasks",
            "--workspace-root", str(tmp_path),
        ]
    )

    assert rc == 3
    assert not (artifacts / "05-agent-tasks-RULE.json").exists()


def test_emit_agent_tasks_exit_1_with_warnings(tmp_path, monkeypatch):
    module = load_module()
    artifacts = _setup_common(tmp_path, monkeypatch, module)
    _write_shard_plan(artifacts, warnings=[{"kind": "informational", "message": "fyi"}])

    rc = module.main(
        [
            "--artifacts-dir", str(artifacts),
            "--rule-id", "RULE",
            "--emit-agent-tasks",
            "--workspace-root", str(tmp_path),
        ]
    )

    assert rc == 1
    output = json.loads((artifacts / "05-agent-tasks-RULE.json").read_text(encoding="utf-8"))
    assert output["warnings"] == [{"kind": "informational", "message": "fyi"}]


def test_emit_agent_tasks_is_atomic(tmp_path, monkeypatch):
    module = load_module()
    artifacts = _setup_common(tmp_path, monkeypatch, module)
    _write_shard_plan(artifacts)
    output_path = artifacts / "05-agent-tasks-RULE.json"
    assert not output_path.exists()

    def raising_replace(self, target):
        raise OSError("simulated atomic-rename failure")

    monkeypatch.setattr(pathlib.Path, "replace", raising_replace)

    rc = module.main(
        [
            "--artifacts-dir", str(artifacts),
            "--rule-id", "RULE",
            "--emit-agent-tasks",
            "--workspace-root", str(tmp_path),
        ]
    )

    assert rc == 3
    assert not output_path.exists()


# ---------------------------------------------------------------------------
# --record-agent-result
# ---------------------------------------------------------------------------


def _write_envelope(artifacts, name, **overrides):
    envelope = {
        "schema_version": 1,
        "rule_id": "RULE",
        "shard_id": "RULE-body-local-001",
        "status": "FIXED",
        "match_quality": "exact",
        "diff_summary": "did the thing",
        "files": [
            {
                "file": "Example1.java",
                "match_count": 1,
                "changes": 1,
                "touched_line_start": 10,
                "touched_line_end": 10,
                "migration_skip_marker": False,
                "diff_summary": "1 call site",
            },
            {
                "file": "Example2.java",
                "match_count": 1,
                "changes": 1,
                "touched_line_start": 5,
                "touched_line_end": 5,
                "migration_skip_marker": False,
                "diff_summary": "1 call site",
            },
        ],
        "errors": [],
        "warnings": [],
    }
    envelope.update(overrides)
    path = artifacts / name
    path.write_text(json.dumps(envelope), encoding="utf-8")
    return path


def test_record_agent_result_writes_same_schema_plus_mode_and_shard_id(tmp_path, monkeypatch):
    module = load_module()
    artifacts = _setup_common(tmp_path, monkeypatch, module, **{"confidence": 1.0})
    _write_shard_plan(artifacts)
    result_file = _write_envelope(artifacts, "06-agent-result.json")

    rc = module.main(
        [
            "--artifacts-dir", str(artifacts),
            "--rule-id", "RULE",
            "--record-agent-result",
            "--shard-id", "RULE-body-local-001",
            "--result-file", str(result_file),
        ]
    )
    assert rc == 0
    agent_records = json.loads((artifacts / "06-fix-results-RULE.json").read_text(encoding="utf-8"))
    agent_record = agent_records[0]

    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()
    module.record_result(
        baseline_dir, "T1", "RULE", "f.java", "FIXED", 1, "ctx", "diff", "hint",
        [], [], 1, 1, graph_context={"status": "unavailable", "diagnostics": []},
    )
    baseline_record = json.loads(
        (baseline_dir / "06-fix-results-RULE.json").read_text(encoding="utf-8")
    )[0]

    assert set(agent_record) - set(baseline_record) == {"mode", "shard_id"}
    assert set(baseline_record) - set(agent_record) == set()
    assert agent_record["mode"] == "agent"
    assert agent_record["shard_id"] == "RULE-body-local-001"


def test_record_agent_result_one_record_per_file(tmp_path, monkeypatch):
    module = load_module()
    artifacts = _setup_common(tmp_path, monkeypatch, module, **{"confidence": 1.0})
    _write_shard_plan(artifacts)
    result_file = _write_envelope(artifacts, "06-agent-result.json")

    rc = module.main(
        [
            "--artifacts-dir", str(artifacts),
            "--rule-id", "RULE",
            "--record-agent-result",
            "--shard-id", "RULE-body-local-001",
            "--result-file", str(result_file),
        ]
    )
    assert rc == 0
    records = json.loads((artifacts / "06-fix-results-RULE.json").read_text(encoding="utf-8"))
    assert len(records) == 2
    assert records[0]["task_id"] == "RULE-body-local-001-f000"
    assert records[1]["task_id"] == "RULE-body-local-001-f001"
    assert records[0]["file"] == "Example1.java"
    assert records[1]["file"] == "Example2.java"


def test_record_agent_result_empty_files_writes_single_record_with_empty_file(tmp_path, monkeypatch):
    module = load_module()
    artifacts = _setup_common(tmp_path, monkeypatch, module, **{"confidence": 1.0})
    _write_shard_plan(artifacts)
    result_file = _write_envelope(artifacts, "06-agent-result.json", status="SKIPPED", files=[])

    rc = module.main(
        [
            "--artifacts-dir", str(artifacts),
            "--rule-id", "RULE",
            "--record-agent-result",
            "--shard-id", "RULE-body-local-001",
            "--result-file", str(result_file),
        ]
    )
    assert rc == 0
    records = json.loads((artifacts / "06-fix-results-RULE.json").read_text(encoding="utf-8"))
    assert len(records) == 1
    record = records[0]
    assert record["task_id"] == "RULE-body-local-001"
    assert record["file"] == ""
    assert record["match_count"] == 0
    assert record["match_region"] == "lines 0-0"


def test_record_agent_result_rejects_file_outside_editable_files(tmp_path, monkeypatch):
    module = load_module()
    artifacts = _setup_common(tmp_path, monkeypatch, module, **{"confidence": 1.0})
    _write_shard_plan(artifacts)
    result_file = _write_envelope(
        artifacts, "06-agent-result.json",
        files=[
            {
                "file": "NotEditable.java",
                "match_count": 1,
                "changes": 1,
                "touched_line_start": 1,
                "touched_line_end": 1,
                "migration_skip_marker": False,
                "diff_summary": "sneaky",
            }
        ],
    )

    rc = module.main(
        [
            "--artifacts-dir", str(artifacts),
            "--rule-id", "RULE",
            "--record-agent-result",
            "--shard-id", "RULE-body-local-001",
            "--result-file", str(result_file),
        ]
    )
    assert rc == 3
    assert not (artifacts / "06-fix-results-RULE.json").exists()


def test_record_agent_result_rejects_shard_id_mismatch(tmp_path, monkeypatch):
    module = load_module()
    artifacts = _setup_common(tmp_path, monkeypatch, module, **{"confidence": 1.0})
    _write_shard_plan(artifacts)
    result_file = _write_envelope(artifacts, "06-agent-result.json", shard_id="WRONG-SHARD-ID")

    rc = module.main(
        [
            "--artifacts-dir", str(artifacts),
            "--rule-id", "RULE",
            "--record-agent-result",
            "--shard-id", "RULE-body-local-001",
            "--result-file", str(result_file),
        ]
    )
    assert rc == 3
    assert not (artifacts / "06-fix-results-RULE.json").exists()


# ---------------------------------------------------------------------------
# needs_review_reasons / compute_final_confidence (unit-level)
# ---------------------------------------------------------------------------

_NEUTRAL_RULE = {"fix_strategy": "recipe:auto-fix", "category": "SAFE_TRANSFORM"}
_NEUTRAL_FILE_ENTRY = {
    "file": "Example1.java",
    "match_count": 1,
    "touched_line_start": 10,
    "touched_line_end": 10,
    "migration_skip_marker": False,
}
_NEUTRAL_SHARD = {"entry_points": [{"file": "Example1.java", "line": 10}]}


def _needs_review_case(**overrides):
    rule = dict(_NEUTRAL_RULE)
    file_entry = dict(_NEUTRAL_FILE_ENTRY)
    shard = _NEUTRAL_SHARD
    final_confidence = 1.0
    for key, value in overrides.items():
        if key == "final_confidence":
            final_confidence = value
        elif key in rule:
            rule[key] = value
        else:
            file_entry[key] = value
    return rule, file_entry, final_confidence, shard


@pytest.mark.parametrize(
    "overrides, expected_reason",
    [
        ({"final_confidence": 0.5}, "low_final_confidence"),
        ({"match_count": 2}, "multiple_matches"),
        ({"fix_strategy": "recipe:needs manual review"}, "manual_review_keyword"),
        ({"touched_line_start": 1, "touched_line_end": 1}, "diff_outside_flagged_region"),
        ({"category": "BEHAVIOR_CHANGE"}, "behavior_change_category"),
        ({"migration_skip_marker": True}, "migration_skip_marker"),
    ],
)
def test_needs_review_six_conditions(overrides, expected_reason):
    module = load_module()
    rule, file_entry, final_confidence, shard = _needs_review_case(**overrides)
    reasons = module.needs_review_reasons(rule, file_entry, final_confidence, shard)
    assert reasons == [expected_reason]


def test_needs_review_reasons_sorted_and_deduplicated():
    module = load_module()
    rule, file_entry, _, shard = _needs_review_case(
        match_count=2, migration_skip_marker=True
    )
    reasons = module.needs_review_reasons(rule, file_entry, 0.1, shard)
    assert reasons == sorted(set(reasons))
    assert reasons == sorted(
        {"low_final_confidence", "multiple_matches", "migration_skip_marker"}
    )


@pytest.mark.parametrize(
    "rule_confidence, match_quality, expected",
    [
        (0.8, "exact", 0.8),
        (0.8, "multiple", 0.64),
        (0.9, "near_miss", 0.81),
        (None, "exact", 0.0),
    ],
)
def test_compute_final_confidence_formula(rule_confidence, match_quality, expected):
    module = load_module()
    final_confidence, _reasons = module.compute_final_confidence(rule_confidence, match_quality)
    assert final_confidence == expected


def test_fixed_is_promoted_to_needs_review_but_failed_is_not(tmp_path, monkeypatch):
    module = load_module()
    shard = {
        "shard_id": "RULE-body-local-001",
        "rule_id": "RULE",
        "editable_files": ["Example1.java"],
        "read_only_context": [],
        "entry_points": [{"file": "Example1.java", "line": 10}],
        "graph_artifact": "graph.json",
    }
    rule = {"fix_strategy": "recipe:auto-fix", "confidence": 0.5}  # triggers low_final_confidence
    file_entry = {
        "file": "Example1.java",
        "match_count": 1,
        "touched_line_start": 10,
        "touched_line_end": 10,
        "migration_skip_marker": False,
        "changes": 1,
        "diff_summary": "ok",
    }

    fixed_artifacts = tmp_path / "fixed"
    fixed_artifacts.mkdir()
    fixed_envelope = {
        "status": "FIXED", "match_quality": "exact", "diff_summary": "ok",
        "files": [file_entry], "errors": [], "warnings": [],
    }
    overall_status, _ = module.record_agent_result(
        fixed_artifacts, "RULE", shard, fixed_envelope, rule, recipe_skill="x"
    )
    assert overall_status == "NEEDS_REVIEW"

    failed_artifacts = tmp_path / "failed"
    failed_artifacts.mkdir()
    failed_envelope = {
        "status": "FAILED", "match_quality": "exact", "diff_summary": "ok",
        "files": [file_entry], "errors": ["boom"], "warnings": [],
    }
    overall_status, _ = module.record_agent_result(
        failed_artifacts, "RULE", shard, failed_envelope, rule, recipe_skill="x"
    )
    assert overall_status == "FAILED"


@pytest.mark.parametrize(
    "declared_status, expected_exit_code",
    [
        ("FIXED", 0),
        ("SKIPPED", 0),
        ("DEFERRED", 0),
        ("FAILED", 2),
        ("NEEDS_REVIEW", 4),
    ],
)
def test_record_agent_result_exit_codes(tmp_path, monkeypatch, declared_status, expected_exit_code):
    module = load_module()
    artifacts = _setup_common(tmp_path, monkeypatch, module, **{"confidence": 1.0})
    _write_shard_plan(artifacts)
    # Empty files: overall_status is taken directly from the declared status,
    # with no needs_review promotion in play -- isolates the exit-code table.
    result_file = _write_envelope(
        artifacts, "06-agent-result.json", status=declared_status, files=[]
    )

    rc = module.main(
        [
            "--artifacts-dir", str(artifacts),
            "--rule-id", "RULE",
            "--record-agent-result",
            "--shard-id", "RULE-body-local-001",
            "--result-file", str(result_file),
        ]
    )
    assert rc == expected_exit_code


# ---------------------------------------------------------------------------
# Mode-mismatch and CLI plumbing
# ---------------------------------------------------------------------------


def test_agent_subcommands_refuse_script_mode_entry(tmp_path, monkeypatch):
    module = load_module()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _write_manifest(artifacts)
    _write_shard_plan(artifacts)
    monkeypatch.setattr(
        module, "load_registry",
        lambda: {"RULE": {"skill": "recipe", "script": "unused", "description": "d"}},
    )
    monkeypatch.setattr(module, "_registry_modes", FakeRegistryModes)

    rc_emit = module.main(
        [
            "--artifacts-dir", str(artifacts),
            "--rule-id", "RULE",
            "--emit-agent-tasks",
            "--workspace-root", str(tmp_path),
        ]
    )
    assert rc_emit == 3
    assert not (artifacts / "05-agent-tasks-RULE.json").exists()

    result_file = _write_envelope(artifacts, "06-agent-result.json")
    rc_record = module.main(
        [
            "--artifacts-dir", str(artifacts),
            "--rule-id", "RULE",
            "--record-agent-result",
            "--shard-id", "RULE-body-local-001",
            "--result-file", str(result_file),
        ]
    )
    assert rc_record == 3
    assert not (artifacts / "06-fix-results-RULE.json").exists()


def test_emit_and_record_are_mutually_exclusive(tmp_path):
    module = load_module()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    with pytest.raises(SystemExit) as exc_info:
        module.main(
            [
                "--artifacts-dir", str(artifacts),
                "--rule-id", "RULE",
                "--emit-agent-tasks",
                "--record-agent-result",
            ]
        )
    assert exc_info.value.code == 2
