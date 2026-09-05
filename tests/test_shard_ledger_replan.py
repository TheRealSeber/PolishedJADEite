"""Re-planning a rule after a rollback must not deadlock the ledger check.

A rollback is the recovery path for a shard the gates rejected. Recovery
normally means re-planning the rule -- and re-planning renames the shards, so
the ledger keeps the superseded entry while the plan no longer has it. Demanding
exact set equality between the two made that path impossible.

What still has to hold: every shard in the plan is in the ledger, and every
ledger entry the plan does not know about is ROLLED_BACK. A CHECKPOINTED or
ACCEPTED entry outside the plan means live edits in a shard nobody is tracking.
"""

import importlib.util
import json
import pathlib

SCRIPT = (
    pathlib.Path(__file__).parent.parent
    / ".claude/skills/jade-core-orchestrator/scripts/orchestrator.py"
)
RULE = "FINALIZE_DEPRECATED_FOR_REMOVAL"


def load():
    spec = importlib.util.spec_from_file_location("orchestrator_ledger_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _write_ledger(tmp_path, shards):
    path = tmp_path / f"06-shard-checkpoints-{RULE}.json"
    path.write_text(
        json.dumps({"schema_version": 1, "rule_id": RULE, "shards": shards}),
        encoding="utf-8",
    )
    return path


PLAN = {"shards": [{"shard_id": f"{RULE}-signature-001"}]}


def _entry(state, **extra):
    entry = {"state": state, "files": {}}
    entry.update(extra)
    return entry


def test_plan_shard_present_and_no_strays_is_valid(tmp_path):
    orch = load()
    _write_ledger(tmp_path, {f"{RULE}-signature-001": _entry("ACCEPTED")})
    ok, reason = orch.validate_shard_ledger(tmp_path, RULE, PLAN)
    assert ok, reason


def test_superseded_rolled_back_shard_is_tolerated(tmp_path):
    orch = load()
    _write_ledger(
        tmp_path,
        {
            f"{RULE}-body-local-001": _entry(
                "ROLLED_BACK", rollback_reason="reclassified from body-local to signature"
            ),
            f"{RULE}-signature-001": _entry("ACCEPTED"),
        },
    )
    ok, reason = orch.validate_shard_ledger(tmp_path, RULE, PLAN)
    assert ok, reason


def test_stray_checkpointed_shard_is_still_rejected(tmp_path):
    orch = load()
    _write_ledger(
        tmp_path,
        {
            f"{RULE}-body-local-001": _entry("CHECKPOINTED"),
            f"{RULE}-signature-001": _entry("ACCEPTED"),
        },
    )
    ok, reason = orch.validate_shard_ledger(tmp_path, RULE, PLAN)
    assert not ok
    assert "body-local-001" in reason


def test_stray_accepted_shard_is_still_rejected(tmp_path):
    orch = load()
    _write_ledger(
        tmp_path,
        {
            f"{RULE}-body-local-001": _entry("ACCEPTED"),
            f"{RULE}-signature-001": _entry("ACCEPTED"),
        },
    )
    ok, reason = orch.validate_shard_ledger(tmp_path, RULE, PLAN)
    assert not ok
    assert "body-local-001" in reason


def test_plan_shard_missing_from_ledger_is_rejected(tmp_path):
    orch = load()
    _write_ledger(
        tmp_path,
        {
            f"{RULE}-body-local-001": _entry(
                "ROLLED_BACK", rollback_reason="reclassified"
            )
        },
    )
    ok, reason = orch.validate_shard_ledger(tmp_path, RULE, PLAN)
    assert not ok
    assert "missing plan shard_ids" in reason
