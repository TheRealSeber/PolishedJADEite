"""Tests for the binding rule-execution order added to RULE_BATCH_LOOP.

compute_binding_rule_order permutes the approved rule list by
(blast_class rank, suggested_order index, original index) — body-local
before signature before unclassified, with suggested_order (from the
knowledge graph) as a binding second-order tie-break and the on-disk
queue order as the final, deterministic tie-break. See
effective_rule_order for how this is composed from artifacts on disk, and
process_rule_batch for the one call site that actually iterates in this
order — the on-disk 05-rule-queue.json ``rules`` list itself is never
reordered or rewritten by any of this.
"""

import importlib.util
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / ".claude/skills/jade-core-orchestrator/scripts/orchestrator.py"


def load_orchestrator():
    spec = importlib.util.spec_from_file_location("orchestrator_rule_order_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_binding_order_degenerate_equals_queue_order():
    orch = load_orchestrator()
    rules = ["R1", "R2", "R3"]
    result = orch.compute_binding_rule_order(rules, {}, list(rules))
    assert result == rules


def test_body_local_before_signature():
    orch = load_orchestrator()
    rules = ["R1", "R2"]
    blast_classes = {"R1": "signature", "R2": "body-local"}
    result = orch.compute_binding_rule_order(rules, blast_classes, rules)
    assert result == ["R2", "R1"]


def test_unclassified_goes_last():
    orch = load_orchestrator()
    rules = ["R2", "R1"]
    blast_classes = {"R1": "body-local"}
    result = orch.compute_binding_rule_order(rules, blast_classes, [])
    assert result == ["R1", "R2"]


def test_suggested_order_breaks_ties_within_same_blast_class():
    orch = load_orchestrator()
    rules = ["R1", "R2", "R3"]
    # All unclassified (same blast rank) — suggested_order alone decides.
    result = orch.compute_binding_rule_order(rules, {}, ["R3", "R1", "R2"])
    assert result == ["R3", "R1", "R2"]


def test_original_index_breaks_ties_when_rule_absent_from_suggested_order():
    orch = load_orchestrator()
    rules = ["R1", "R2", "R3"]
    # R2 is present in suggested_order (rank 0); R1 and R3 are both absent
    # (rank len(suggested_order)) and must fall back to their original
    # index in `rules` — R1 before R3.
    result = orch.compute_binding_rule_order(rules, {}, ["R2"])
    assert result == ["R2", "R1", "R3"]


def test_binding_order_is_a_permutation():
    orch = load_orchestrator()
    rules = ["R5", "R1", "R4", "R2", "R3"]
    blast_classes = {"R1": "signature", "R2": "body-local", "R4": "signature"}
    suggested_order = ["R4", "R3"]
    result = orch.compute_binding_rule_order(rules, blast_classes, suggested_order)
    assert len(result) == len(rules)
    assert Counter(result) == Counter(rules)
    # Original inputs are never mutated.
    assert rules == ["R5", "R1", "R4", "R2", "R3"]
    assert suggested_order == ["R4", "R3"]


def test_effective_rule_order_composes_manifest_and_graph_metadata(tmp_path):
    orch = load_orchestrator()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "01-breaking-changes-manifest.json").write_text(
        json.dumps(
            {
                "rules": [
                    {"id": "R1", "blast_class": "signature"},
                    {"id": "R2", "blast_class": "body-local"},
                ]
            }
        ),
        encoding="utf-8",
    )
    queue = {
        "run_id": "r",
        "rules": ["R1", "R2"],
        "graph_metadata": {"suggested_order": ["R1", "R2"]},
    }
    result = orch.effective_rule_order(artifacts, queue)
    assert result == ["R2", "R1"]
    # Queue dict itself is untouched.
    assert queue["rules"] == ["R1", "R2"]


def test_process_rule_batch_iterates_binding_order_but_leaves_queue_rules_on_disk_untouched(
    tmp_path,
):
    orch = load_orchestrator()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    # R_LATER is body-local (should run first); R_FIRST is unclassified
    # but listed first on disk (should run last).
    (artifacts / "01-breaking-changes-manifest.json").write_text(
        json.dumps(
            {
                "rules": [
                    {"id": "R_LATER", "blast_class": "body-local"},
                ]
            }
        ),
        encoding="utf-8",
    )
    queue_path = artifacts / "05-rule-queue.json"
    queue_path.write_text(
        json.dumps({"run_id": "r", "rules": ["R_FIRST", "R_LATER"]}),
        encoding="utf-8",
    )

    cfg = {"run_id": "r", "source_version": "1.7", "target_version": "1.8"}
    state = {}
    hist_path = artifacts / "phase-history.log.jsonl"
    state_path = artifacts / "00-run-state.json"
    rule_status_path = artifacts / "rule-status.json"

    outcome = orch.process_rule_batch(
        cfg, artifacts, state, hist_path, state_path, rule_status_path
    )
    # Neither rule has a 05-rule-batch-<id>.json, so the loop stops on the
    # first rule it visits with ARTIFACT_MISSING — which rule that is
    # reveals the binding iteration order.
    assert outcome == "ARTIFACT_MISSING"

    lines = [
        json.loads(line)
        for line in hist_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    processing_msgs = [e["message"] for e in lines if e["message"].startswith("Processing rule")]
    assert processing_msgs == ["Processing rule R_LATER"]

    on_disk = json.loads(queue_path.read_text(encoding="utf-8"))
    assert on_disk["rules"] == ["R_FIRST", "R_LATER"]
