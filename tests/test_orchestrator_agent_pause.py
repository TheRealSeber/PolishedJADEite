"""Tests for the agent-mode RULE_BATCH_LOOP pause/gate in orchestrator.py.

A rule whose recipe-registry.json entry carries "mode": "agent" is gated
by agent_registry_entry / _process_agent_rule instead of the legacy
05-rule-batch-<rule_id>.json script path. These tests exercise that gate
directly (never through dispatcher.py or registry_modes.py — this stream
owns orchestrator.py only, and reads recipe-registry.json itself).
"""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / ".claude/skills/jade-core-orchestrator/scripts/orchestrator.py"


def load_orchestrator():
    spec = importlib.util.spec_from_file_location("orchestrator_agent_pause_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _shard(shard_id, editable_files, entry_points=None, rule_id="R", parallel_safe=True):
    return {
        "shard_id": shard_id,
        "rule_id": rule_id,
        "class": "body-local",
        "editable_files": editable_files,
        "read_only_context": ["src/jade/src/jade/Boot.java"],
        "entry_points": entry_points or [{"file": editable_files[0], "line": 10}],
        "invariants": ["EDITS_CONFINED_TO_EDITABLE_FILES"],
        "graph_artifact": "03.5-knowledge-graph.json",
        "parallel_safe": parallel_safe,
    }


def _write_shard_plan(artifacts, rule_id, shards, run_id="test-run"):
    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "rule_id": rule_id,
        "status": "OK",
        "blast_class": "body-local",
        "shard_count": len(shards),
        "shards": shards,
        "total_flags": 0,
        "total_flagged_files": 0,
        "warnings": [],
    }
    (artifacts / f"05-rule-shards-{rule_id}.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    return payload


def _write_ledger(artifacts, rule_id, shards_state, run_id="test-run"):
    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "rule_id": rule_id,
        "workspace_root": "workspace",
        "repo_root": "/repo",
        "shards": shards_state,
    }
    (artifacts / f"06-shard-checkpoints-{rule_id}.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    return payload


def _agent_registry(tmp_path, rule_id):
    path = tmp_path / "recipe-registry.json"
    path.write_text(
        json.dumps(
            {
                rule_id: {
                    "mode": "agent",
                    "skill": "jade-recipe-agent-x",
                    "skill_md": ".claude/skills/java-migration-skill-registry/shared/jade-recipe-agent-x/SKILL.md",
                    "description": "agent recipe under test",
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def _base_cfg(artifacts, workspace):
    return {
        "run_id": "test-run",
        "source_version": "1.7",
        "target_version": "1.8",
        "artifacts_path": str(artifacts),
        "workspace_path": str(workspace),
    }


def _base_state():
    return {
        "run_id": "test-run",
        "state": "RULE_BATCH_LOOP",
        "current_rule_id": None,
        "updated_at": "2026-08-29T00:00:00Z",
        "failure_reason": None,
    }


def test_agent_rule_without_shard_plan_returns_artifact_missing(tmp_path, monkeypatch):
    orch = load_orchestrator()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    workspace = tmp_path / "workspace"
    monkeypatch.setattr(orch, "RECIPE_REGISTRY_PATH", _agent_registry(tmp_path, "R1"))

    cfg = _base_cfg(artifacts, workspace)
    state = _base_state()
    rstatus = {}
    outcome = orch._process_agent_rule(
        cfg,
        artifacts,
        state,
        "R1",
        artifacts / "phase-history.log.jsonl",
        artifacts / "00-run-state.json",
        artifacts / "rule-status.json",
        rstatus,
    )
    assert outcome == "ARTIFACT_MISSING"
    assert rstatus["R1"]["status"] == "PENDING_AGENT"
    assert state["failure_reason"] == "MISSING_SHARD_PLAN"
    assert not (artifacts / "AWAITING_AGENT.md").exists()


def test_agent_rule_with_malformed_shards_field_returns_artifact_missing(tmp_path, monkeypatch):
    orch = load_orchestrator()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    workspace = tmp_path / "workspace"
    monkeypatch.setattr(orch, "RECIPE_REGISTRY_PATH", _agent_registry(tmp_path, "R1"))

    # A shard plan that is a JSON object but has "shards": null (or any
    # non-list) must degrade to the same fail-closed path as a missing
    # plan, not crash — nothing downstream may assume "shards" is a list.
    (artifacts / "05-rule-shards-R1.json").write_text(
        json.dumps({"schema_version": 1, "rule_id": "R1", "status": "OK", "shards": None}),
        encoding="utf-8",
    )

    cfg = _base_cfg(artifacts, workspace)
    state = _base_state()
    rstatus = {}
    outcome = orch._process_agent_rule(
        cfg,
        artifacts,
        state,
        "R1",
        artifacts / "phase-history.log.jsonl",
        artifacts / "00-run-state.json",
        artifacts / "rule-status.json",
        rstatus,
    )
    assert outcome == "ARTIFACT_MISSING"
    assert rstatus["R1"]["status"] == "PENDING_AGENT"
    assert not (artifacts / "AWAITING_AGENT.md").exists()


def test_agent_rule_with_plan_and_no_tasks_pauses_once_per_rule(tmp_path, monkeypatch):
    orch = load_orchestrator()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    workspace = tmp_path / "workspace"
    monkeypatch.setattr(orch, "RECIPE_REGISTRY_PATH", _agent_registry(tmp_path, "R1"))

    shards = [_shard(f"R1-body-local-{i:03d}", [f"F{i}.java"]) for i in range(6)]
    _write_shard_plan(artifacts, "R1", shards)

    calls = []
    original = orch._pause_for_agent

    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(orch, "_pause_for_agent", spy)

    cfg = _base_cfg(artifacts, workspace)
    state = _base_state()
    outcome = orch._process_agent_rule(
        cfg,
        artifacts,
        state,
        "R1",
        artifacts / "phase-history.log.jsonl",
        artifacts / "00-run-state.json",
        artifacts / "rule-status.json",
        {},
    )
    assert outcome == "AWAIT_AGENT"
    assert len(calls) == 1, "must pause exactly once per rule, not once per shard"
    assert (artifacts / "AWAITING_AGENT.md").exists()
    assert state["awaiting_rule_id"] == "R1"
    assert state["awaiting_shards"] == [s["shard_id"] for s in shards]


def test_awaiting_agent_md_lists_all_shards_and_all_six_commands(tmp_path, monkeypatch):
    orch = load_orchestrator()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    workspace = tmp_path / "workspace"
    monkeypatch.setattr(orch, "RECIPE_REGISTRY_PATH", _agent_registry(tmp_path, "R1"))

    shards = [_shard(f"R1-body-local-{i:03d}", [f"F{i}.java"]) for i in range(3)]
    plan = _write_shard_plan(artifacts, "R1", shards)

    cfg = _base_cfg(artifacts, workspace)
    state = _base_state()
    orch._process_agent_rule(
        cfg,
        artifacts,
        state,
        "R1",
        artifacts / "phase-history.log.jsonl",
        artifacts / "00-run-state.json",
        artifacts / "rule-status.json",
        {},
    )
    content = (artifacts / "AWAITING_AGENT.md").read_text(encoding="utf-8")

    for header in (
        "## Anti-bypass",
        "## Shards",
        "## Per-shard procedure",
        "## Subagent contract",
        "## Resume",
    ):
        assert header in content

    for shard in shards:
        sid = shard["shard_id"]
        assert sid in content
        assert f"shard_checkpoint.py --artifacts-dir {cfg['artifacts_path']} --rule-id R1 --shard-id {sid} --workspace {cfg['workspace_path']} --create" in content
        assert f"verify_shard.py --artifacts-dir {cfg['artifacts_path']} --rule-id R1 --shard-id {sid}" in content
        assert f"gate_signatures.py --artifacts-dir {cfg['artifacts_path']} --rule-id R1 --shard-id {sid}" in content
        assert f"dispatcher.py --artifacts-dir {cfg['artifacts_path']} --rule-id R1 --record-agent-result --shard-id {sid}" in content
        assert f"shard_checkpoint.py --artifacts-dir {cfg['artifacts_path']} --rule-id R1 --shard-id {sid} --workspace {cfg['workspace_path']} --accept" in content
        assert f"shard_checkpoint.py --artifacts-dir {cfg['artifacts_path']} --rule-id R1 --shard-id {sid} --workspace {cfg['workspace_path']} --rollback" in content


def test_awaiting_agent_md_contains_no_absolute_source_paths_outside_workspace(tmp_path, monkeypatch):
    orch = load_orchestrator()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    workspace = tmp_path / "workspace"
    monkeypatch.setattr(orch, "RECIPE_REGISTRY_PATH", _agent_registry(tmp_path, "R1"))

    distinctive_file = "src/jade/src/jade/core/Runtime.java"
    shards = [_shard("R1-body-local-001", [distinctive_file])]
    _write_shard_plan(artifacts, "R1", shards)

    cfg = _base_cfg(artifacts, workspace)
    state = _base_state()
    orch._process_agent_rule(
        cfg,
        artifacts,
        state,
        "R1",
        artifacts / "phase-history.log.jsonl",
        artifacts / "00-run-state.json",
        artifacts / "rule-status.json",
        {},
    )
    content = (artifacts / "AWAITING_AGENT.md").read_text(encoding="utf-8")
    assert distinctive_file not in content
    assert "Runtime.java" not in content
    assert "Boot.java" not in content  # read_only_context path also never leaks


def test_script_mode_rule_uses_unchanged_pause_text(tmp_path):
    orch = load_orchestrator()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    cfg = {
        "run_id": "test-run",
        "source_version": "1.7",
        "target_version": "1.8",
        "artifacts_path": str(artifacts),
        "workspace_path": str(tmp_path / "workspace"),
    }
    state = _base_state()
    outcome = orch._pause_for_agent("RULE_BATCH_LOOP", artifacts, state, cfg)
    assert outcome == "AWAIT_AGENT"

    golden = f"""# AWAITING AGENT — RULE_BATCH_LOOP

The pipeline has paused at the **rule batch processing** phase.

## What to do

**ANTI-BYPASS:** You are strictly forbidden from manually creating a batch
artifact and marking it `DONE` or `NOOP` if flags exist for that rule.
You must either (a) write a true registry recipe script to transform the flagged
code, or (b) use `defer_rules.py` to defer modernization flags and preserve
them as `// JADE-MODERNIZATION-DEFERRED` markers for future developers.
Failure to comply is a pipeline integrity violation.

1. Review `04-scan-summary.json` and group flagged rules by severity:
   - `HIGH`/`MEDIUM` → Breaking Changes (mandatory — must be transformed)
   - `LOW`/`INFO` → Modernization Opportunities (optional)
2. ASK THE USER in chat: "Which modernization rules should be applied vs deferred?"
   Present the flagged modernization rules with their counts. Wait for user's answer.
3. For rules the user defers, run:
   ```
   python .claude/skills/jade-core-batch-processor/scripts/defer_rules.py \\
     --workspace {cfg["workspace_path"]} \\
     --artifacts {cfg["artifacts_path"]} \\
     --rule-id <rule_id> --reason "<user-provided reason>"
   ```
4. Create `{cfg["artifacts_path"]}/05-rule-queue.json` with ONLY rules the user
   approved (all mandatory breaking changes + user-selected modernization rules)
5. For each rule:
   a. Create `{cfg["artifacts_path"]}/05-rule-batch-<rule_id>.json` with per-file tasks
   b. Dispatch recipe via rule-dispatcher
   c. Apply transforms to flagged source files
6. After all rules processed, produce `{cfg["artifacts_path"]}/07-build.log`
   by running the build in Docker via `build_audit.py`

## Resume

After rule batches and build verification are complete:
```
python .claude/skills/jade-core-orchestrator/scripts/orchestrator.py --config {cfg["artifacts_path"]}/00-run-config.json --run
```
"""
    actual = (artifacts / "AWAITING_AGENT.md").read_text(encoding="utf-8")
    assert actual == golden
    assert "awaiting_rule_id" not in state
    assert "awaiting_shards" not in state


def test_checkpointed_shard_yields_shard_rollback_pending(tmp_path, monkeypatch):
    orch = load_orchestrator()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    workspace = tmp_path / "workspace"
    monkeypatch.setattr(orch, "RECIPE_REGISTRY_PATH", _agent_registry(tmp_path, "R1"))

    shards = [_shard("R1-body-local-001", ["F0.java"]), _shard("R1-body-local-002", ["F1.java"])]
    _write_shard_plan(artifacts, "R1", shards)
    (artifacts / "05-agent-tasks-R1.json").write_text("{}", encoding="utf-8")
    _write_ledger(
        artifacts,
        "R1",
        {
            "R1-body-local-001": {
                "state": "CHECKPOINTED",
                "created_at": "t",
                "updated_at": "t",
                "rollback_reason": None,
                "files": [{"file": "F0.java", "existed": True, "blob": "a" * 40, "mode": 420}],
            },
            "R1-body-local-002": {
                "state": "ACCEPTED",
                "created_at": "t",
                "updated_at": "t",
                "rollback_reason": None,
                "files": [{"file": "F1.java"}],
            },
        },
    )

    cfg = _base_cfg(artifacts, workspace)
    state = _base_state()
    outcome = orch._process_agent_rule(
        cfg,
        artifacts,
        state,
        "R1",
        artifacts / "phase-history.log.jsonl",
        artifacts / "00-run-state.json",
        artifacts / "rule-status.json",
        {},
    )
    assert outcome == "SHARD_ROLLBACK_PENDING"
    assert (artifacts / "AWAITING_AGENT.md").exists()
    assert state["state"] == "AWAITING_AGENT"


def test_needs_review_shard_marked_accepted_is_surfaced_not_failed(tmp_path, monkeypatch):
    """NEEDS_REVIEW on an accepted shard proceeds and lands in REVIEW_REQUIRED.md.

    The recipe contract defines NEEDS_REVIEW as "the edit was applied, but a
    human should verify it" -- an outcome, not a failure. Failing the run on it
    pushed agents the wrong way: to get a green run they had to record FIXED for
    work they were unsure about, which is the fabricated status the pipeline
    exists to prevent. The review debt is now recorded instead of hidden.
    """
    orch = load_orchestrator()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    workspace = tmp_path / "workspace"
    monkeypatch.setattr(orch, "RECIPE_REGISTRY_PATH", _agent_registry(tmp_path, "R1"))

    shards = [_shard("R1-body-local-001", ["F0.java"])]
    _write_shard_plan(artifacts, "R1", shards)
    (artifacts / "05-agent-tasks-R1.json").write_text("{}", encoding="utf-8")
    _write_ledger(
        artifacts,
        "R1",
        {
            "R1-body-local-001": {
                "state": "ACCEPTED",
                "created_at": "t",
                "updated_at": "t",
                "rollback_reason": None,
                "files": [{"file": "F0.java"}],
            },
        },
    )
    (artifacts / "06-fix-results-R1.json").write_text(
        json.dumps(
            [
                {
                    "task_id": "R1-body-local-001-f000",
                    "rule_id": "R1",
                    "shard_id": "R1-body-local-001",
                    "status": "NEEDS_REVIEW",
                    "file": "F0.java",
                }
            ]
        ),
        encoding="utf-8",
    )

    cfg = _base_cfg(artifacts, workspace)
    state = _base_state()
    outcome = orch._process_agent_rule(
        cfg,
        artifacts,
        state,
        "R1",
        artifacts / "phase-history.log.jsonl",
        artifacts / "00-run-state.json",
        artifacts / "rule-status.json",
        {},
    )
    assert outcome != "ARTIFACT_TAMPERED"
    assert state.get("failure_reason") != "SHARD_NEEDS_REVIEW_ACCEPTED"

    ledger = artifacts / "REVIEW_REQUIRED.md"
    assert ledger.is_file(), "an accepted NEEDS_REVIEW shard must be recorded for review"
    body = ledger.read_text(encoding="utf-8")
    assert "R1" in body and "R1-body-local-001" in body


def test_all_shards_accepted_or_rolled_back_falls_through_to_build_verification(tmp_path, monkeypatch):
    orch = load_orchestrator()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    workspace = tmp_path / "workspace"
    monkeypatch.setattr(orch, "RECIPE_REGISTRY_PATH", _agent_registry(tmp_path, "R1"))

    shards = [_shard("R1-body-local-001", ["F0.java"]), _shard("R1-body-local-002", ["F1.java"])]
    _write_shard_plan(artifacts, "R1", shards)
    (artifacts / "05-agent-tasks-R1.json").write_text("{}", encoding="utf-8")
    _write_ledger(
        artifacts,
        "R1",
        {
            "R1-body-local-001": {
                "state": "ACCEPTED",
                "created_at": "t",
                "updated_at": "t",
                "rollback_reason": None,
                "files": [{"file": "F0.java"}],
            },
            "R1-body-local-002": {
                "state": "ROLLED_BACK",
                "created_at": "t",
                "updated_at": "t",
                "rollback_reason": "needs manual follow-up",
                "files": [{"file": "F1.java"}],
            },
        },
    )

    cfg = _base_cfg(artifacts, workspace)
    state = _base_state()
    outcome = orch._process_agent_rule(
        cfg,
        artifacts,
        state,
        "R1",
        artifacts / "phase-history.log.jsonl",
        artifacts / "00-run-state.json",
        artifacts / "rule-status.json",
        {},
    )
    assert outcome is None
    assert not (artifacts / "AWAITING_AGENT.md").exists()

    # Full process_rule_batch integration: with no 07-build.log yet, the
    # unchanged build-verification path takes over from here exactly as it
    # does for a script-mode rule.
    queue_path = artifacts / "05-rule-queue.json"
    queue_path.write_text(json.dumps({"run_id": "test-run", "rules": ["R1"]}), encoding="utf-8")
    outcome2 = orch.process_rule_batch(
        cfg,
        artifacts,
        state,
        artifacts / "phase-history.log.jsonl",
        artifacts / "00-run-state.json",
        artifacts / "rule-status.json",
    )
    assert outcome2 == "VERIFY_FAIL"
    rstatus = json.loads((artifacts / "rule-status.json").read_text())["rules"]
    assert rstatus["R1"]["status"] == "PENDING_VERIFY"
