#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import shutil
import sys
from typing import Dict, List

PHASES = [
    "INIT",
    "WORKSPACE_READY",
    "MANIFEST_READY",
    "TOOLING_SCOUT_READY",
    "BUILD_GATE_READY",
    "SCAN_READY",
    "RULE_BATCH_LOOP",
    "VERIFIED",
]

TERMINAL_STATES = {"DONE", "FAILED", "AWAITING_SOURCE_INPUT"}


def iso_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def read_json(path: pathlib.Path) -> Dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: pathlib.Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    tmp.replace(path)


def append_jsonl(path: pathlib.Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=True) + "\n")


def fail(artifacts: pathlib.Path, state: Dict, code: str, message: str) -> int:
    state["state"] = "FAILED"
    state["updated_at"] = iso_now()
    state["failure_reason"] = code
    write_json(artifacts / "00-run-state.json", state)
    write_json(
        artifacts / "failure-summary.json",
        {"code": code, "message": message, "updated_at": state["updated_at"]},
    )
    append_jsonl(
        artifacts / "phase-history.log.jsonl",
        {
            "ts": iso_now(),
            "phase": state.get("state", "UNKNOWN"),
            "status": "ERROR",
            "message": f"{code}: {message}",
            "artifacts": ["failure-summary.json", "00-run-state.json"],
        },
    )
    print(f"ERROR [{code}] {message}", file=sys.stderr)
    return 2


def placeholder_runner(name: str) -> bool:
    # Hook point for future skill invocations
    _ = name
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="JADE migration orchestrator")
    parser.add_argument(
        "--config",
        default="migration-runs/sample/artifacts/00-run-config.json",
        help="Path to 00-run-config.json",
    )
    args = parser.parse_args()

    config_path = pathlib.Path(args.config)
    if not config_path.exists():
        print(
            f"ERROR [CONFIG_NOT_FOUND] Missing config: {config_path}", file=sys.stderr
        )
        return 2

    cfg = read_json(config_path)
    required = {
        "run_id",
        "baseline_path",
        "workspace_path",
        "artifacts_path",
        "source_version",
        "target_version",
    }
    missing = sorted(required - set(cfg.keys()))
    if missing:
        print(
            f"ERROR [CONFIG_INVALID] Missing keys: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 2

    artifacts = pathlib.Path(cfg["artifacts_path"])
    state_path = artifacts / "00-run-state.json"
    hist_path = artifacts / "phase-history.log.jsonl"

    state = {
        "run_id": cfg["run_id"],
        "state": "INIT",
        "current_rule_id": None,
        "updated_at": iso_now(),
        "failure_reason": None,
    }
    write_json(state_path, state)
    append_jsonl(
        hist_path,
        {
            "ts": iso_now(),
            "phase": "INIT",
            "status": "OK",
            "message": "Run initialized",
            "artifacts": ["00-run-state.json"],
        },
    )

    # ------------------------------------------------------------------
    # WORKSPACE_READY — isolate workspace (never mutate baseline)
    # ------------------------------------------------------------------
    baseline = pathlib.Path(cfg["baseline_path"])
    workspace = pathlib.Path(cfg["workspace_path"])

    if not baseline.exists():
        return fail(
            artifacts,
            state,
            "BASELINE_MISSING",
            f"Baseline path does not exist: {baseline}",
        )

    if not workspace.exists():
        try:
            shutil.copytree(baseline, workspace)
        except shutil.Error as exc:
            return fail(
                artifacts,
                state,
                "COPY_FAILED",
                f"Failed to copy {baseline} → {workspace}: {exc}",
            )

    state["state"] = "WORKSPACE_READY"
    state["updated_at"] = iso_now()
    write_json(state_path, state)
    append_jsonl(
        hist_path,
        {
            "ts": iso_now(),
            "phase": "WORKSPACE_READY",
            "status": "OK",
            "message": f"Workspace ready: {workspace}"
            + (" (fresh copy)" if not workspace.exists() else " (existing)"),
            "artifacts": ["00-run-state.json"],
        },
    )

    required_phase_inputs = {
        "MANIFEST_READY": [artifacts / "01-breaking-changes-manifest.json"],
        "BUILD_GATE_READY": [artifacts / "03-build-audit.json"],
        "SCAN_READY": [artifacts / "04-flag-index.json"],
        "RULE_BATCH_LOOP": [artifacts / "05-rule-queue.json"],
    }

    for phase in PHASES[1:]:
        for p in required_phase_inputs.get(phase, []):
            if not p.exists():
                return fail(
                    artifacts, state, "ARTIFACT_MISSING", f"Required for {phase}: {p}"
                )

        if phase == "RULE_BATCH_LOOP":
            queue = read_json(artifacts / "05-rule-queue.json")
            rules: List[str] = queue.get("rules", [])
            if not isinstance(rules, list):
                return fail(artifacts, state, "QUEUE_INVALID", "rules must be a list")

            rule_status = {}
            for rule_id in rules:
                state["current_rule_id"] = rule_id
                state["state"] = "RULE_BATCH_LOOP"
                state["updated_at"] = iso_now()
                write_json(state_path, state)

                ok = (
                    placeholder_runner(f"batch:{rule_id}")
                    and placeholder_runner(f"verify:{rule_id}")
                    and placeholder_runner(f"commit:{rule_id}")
                )
                if not ok:
                    return fail(
                        artifacts,
                        state,
                        "RULE_GATE_FAILED",
                        f"Rule pipeline failed for {rule_id}",
                    )

                rule_status[rule_id] = {"status": "DONE", "updated_at": iso_now()}
                append_jsonl(
                    hist_path,
                    {
                        "ts": iso_now(),
                        "phase": "RULE_BATCH_LOOP",
                        "status": "OK",
                        "message": f"Completed rule {rule_id}",
                        "artifacts": ["rule-status.json"],
                    },
                )

            write_json(
                artifacts / "rule-status.json",
                {"run_id": cfg["run_id"], "rules": rule_status},
            )
            continue

        if not placeholder_runner(phase):
            return fail(artifacts, state, "PHASE_FAILED", f"Phase failed: {phase}")

        state["state"] = phase
        state["updated_at"] = iso_now()
        write_json(state_path, state)
        append_jsonl(
            hist_path,
            {
                "ts": iso_now(),
                "phase": phase,
                "status": "OK",
                "message": f"Phase completed: {phase}",
                "artifacts": ["00-run-state.json"],
            },
        )

    state["state"] = "DONE"
    state["current_rule_id"] = None
    state["updated_at"] = iso_now()
    write_json(state_path, state)
    append_jsonl(
        hist_path,
        {
            "ts": iso_now(),
            "phase": "DONE",
            "status": "OK",
            "message": "Run complete",
            "artifacts": ["00-run-state.json", "rule-status.json"],
        },
    )
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
