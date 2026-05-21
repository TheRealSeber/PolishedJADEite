#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import sys
from typing import Dict, List

SKILL_IDS = [
    "jade-migration-orchestrator",
    "jade-change-collector-strict",
    "jade-tooling-scout",
    "jade-build-system-fixer",
    "jade-scanner",
    "jade-rule-batch-processor",
    "jade-rule-fixer",
    "jade-verification-semantic",
    "jade-atomic-rule-commit",
    "jade-retry-router",
]


def score_skill(skill_id: str, artifacts_dir: pathlib.Path) -> Dict:
    scores = {"contract_compliance": 0, "reproducibility": 0, "gate_pass_rate": 0, "artifact_completeness": 0, "failure_handling": 0}

    rule_status = artifacts_dir / "rule-status.json"
    if rule_status.exists():
        data = json.loads(rule_status.read_text(encoding="utf-8"))
        rules = data.get("rules", {})
        if rules:
            passed = sum(1 for r in rules.values() if r.get("status") == "DONE")
            scores["gate_pass_rate"] = int(100 * passed / len(rules))
            scores["reproducibility"] = 80 if passed == len(rules) else 40

    queue = artifacts_dir / "05-rule-queue.json"
    if queue.exists():
        scores["contract_compliance"] = 70
        q = json.loads(queue.read_text(encoding="utf-8"))
        if isinstance(q.get("rules"), list):
            scores["contract_compliance"] = 90

    run_config = artifacts_dir / "00-run-config.json"
    failure = artifacts_dir / "failure-summary.json"
    if run_config.exists():
        scores["artifact_completeness"] = 60
        scores["failure_handling"] = 50
    if failure.exists():
        scores["failure_handling"] = 85

    aggregate = int(sum(scores.values()) / len(scores))
    if aggregate >= 85:
        classification = "official"
    elif aggregate >= 60:
        classification = "candidate"
    else:
        classification = "experimental"

    return {"skill_id": skill_id, "scores": scores, "aggregate": aggregate, "classification": classification}


def main() -> int:
    artifacts = pathlib.Path("migration-runs/sample/artifacts")
    results: List[Dict] = []
    for sid in SKILL_IDS:
        results.append(score_skill(sid, artifacts))

    out = artifacts / "10-skill-matrix.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(results, indent=2), encoding="utf-8")
    tmp.replace(out)
    print(f"Skill matrix written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
