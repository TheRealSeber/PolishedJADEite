#!/usr/bin/env python3
from __future__ import annotations

import argparse
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

_SKILL_ARTIFACT_MAP = {
    "jade-scanner": ["04-flag-index.json", "04-scan-summary.json"],
    "jade-rule-batch-processor": ["05-rule-batch-status.json"],
    "jade-rule-fixer": [],
    "jade-verification-semantic": [],
    "jade-atomic-rule-commit": ["09-rule-commit-log.json"],
    "jade-skill-matrix-evaluator": ["10-skill-matrix.json"],
    "jade-build-system-fixer": ["03-build-audit.json"],
    "jade-change-collector-strict": ["01-breaking-changes-manifest.json"],
    "jade-tooling-scout": ["02-tooling-scout-report.json"],
    "jade-migration-orchestrator": [],
    "jade-retry-router": [],
}


def _get_skill_artifacts(skill_id: str) -> List[str]:
    return _SKILL_ARTIFACT_MAP.get(skill_id, [])


def _run_completed(artifacts_dir: pathlib.Path) -> bool:
    state = artifacts_dir / "00-run-state.json"
    if not state.exists():
        return False
    data = json.loads(state.read_text(encoding="utf-8"))
    return data.get("state") in ("DONE",)


def score_skill(skill_id: str, artifacts_dir: pathlib.Path) -> Dict:
    scores = {
        "contract_compliance": 0,
        "reproducibility": 0,
        "gate_pass_rate": 0,
        "artifact_completeness": 0,
        "failure_handling": 0,
    }

    # Check skill-specific artifacts
    skill_artifacts = _get_skill_artifacts(skill_id)
    if skill_artifacts:
        present = sum(1 for a in skill_artifacts if (artifacts_dir / a).exists())
        scores["artifact_completeness"] = int(100 * present / len(skill_artifacts))
    else:
        scores["artifact_completeness"] = 50

    # Check rule-status.json for gate pass rate
    rule_status = artifacts_dir / "rule-status.json"
    if rule_status.exists():
        data = json.loads(rule_status.read_text(encoding="utf-8"))
        rules = data.get("rules", {})
        if rules:
            passed = sum(1 for r in rules.values() if r.get("status") == "DONE")
            scores["gate_pass_rate"] = int(100 * passed / len(rules))
            if passed == len(rules):
                scores["reproducibility"] = 90
            elif passed > 0:
                scores["reproducibility"] = 50

    # Check failure-summary.json for failure handling
    failure = artifacts_dir / "failure-summary.json"
    if failure.exists():
        scores["failure_handling"] = 85
    else:
        if _run_completed(artifacts_dir):
            scores["failure_handling"] = 75

    # Check queue for contract compliance
    queue = artifacts_dir / "05-rule-queue.json"
    if queue.exists():
        q = json.loads(queue.read_text(encoding="utf-8"))
        rules_list = q.get("rules", [])
        if isinstance(rules_list, list) and len(rules_list) > 0:
            scores["contract_compliance"] = 95

    # Check phase-history.log.jsonl for overall health
    phase_history = artifacts_dir / "phase-history.log.jsonl"
    if phase_history.exists():
        phases = []
        for line in phase_history.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    phases.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        if phases:
            ok_phases = sum(1 for p in phases if p.get("status") == "OK")
            scores["contract_compliance"] = max(
                scores["contract_compliance"], int(90 * ok_phases / len(phases))
            )

    aggregate = int(sum(scores.values()) / len(scores))
    if aggregate >= 90:
        classification = "official"
    elif aggregate >= 70:
        classification = "candidate"
    elif aggregate >= 50:
        classification = "experimental"
    else:
        classification = "draft"

    return {
        "skill_id": skill_id,
        "scores": scores,
        "aggregate": aggregate,
        "classification": classification,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="JADE Skill Matrix Evaluator")
    parser.add_argument(
        "--artifacts",
        default="migration-runs/sample/artifacts",
        help="Path to artifacts directory",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output path for skill matrix JSON (default: <artifacts>/10-skill-matrix.json)",
    )
    args = parser.parse_args()

    artifacts = pathlib.Path(args.artifacts)
    if not artifacts.is_dir():
        print(f"ERROR: {artifacts} not a directory", file=sys.stderr)
        return 2

    results: List[Dict] = []
    for sid in SKILL_IDS:
        results.append(score_skill(sid, artifacts))

    out = (
        pathlib.Path(args.output)
        if args.output
        else (artifacts / "10-skill-matrix.json")
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(results, indent=2), encoding="utf-8")
    tmp.replace(out)

    for r in results:
        print(f"{r['aggregate']:3d}% {r['classification']:13s} {r['skill_id']}")
    print(f"Skill matrix written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
