#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import shutil
import subprocess
import sys
from typing import Dict, List, Optional, Tuple

# ------------------------------------------------------------------
# Transition table — current state + outcome → next state
# ------------------------------------------------------------------
TRANSITIONS: Dict[str, Dict[str, str]] = {
    "INIT": {"OK": "WORKSPACE_READY"},
    "WORKSPACE_READY": {"OK": "MANIFEST_READY"},
    "MANIFEST_READY": {"OK": "TOOLING_SCOUT_READY", "ARTIFACT_MISSING": "FAILED"},
    "TOOLING_SCOUT_READY": {"OK": "BUILD_GATE_READY", "ARTIFACT_MISSING": "FAILED"},
    "BUILD_GATE_READY": {"OK": "SCAN_READY", "ARTIFACT_MISSING": "FAILED"},
    "SCAN_READY": {"OK": "RULE_BATCH_LOOP", "ARTIFACT_MISSING": "FAILED"},
    "RULE_BATCH_LOOP": {
        "NEXT_RULE": "RULE_BATCH_LOOP",
        "NO_MORE_RULES": "VERIFIED",
        "VERIFY_FAIL": "RULE_RETRY",
    },
    "RULE_RETRY": {"RETRY": "RULE_BATCH_LOOP", "ESCALATE": "RULE_ESCALATE"},
    "RULE_ESCALATE": {"OK": "RULE_BATCH_LOOP"},
    "VERIFIED": {"OK": "DONE"},
}

TERMINAL_STATES = {"DONE", "FAILED", "AWAITING_SOURCE_INPUT"}

# Artifacts required for each gate phase
REQUIRED_ARTIFACTS: Dict[str, List[str]] = {
    "MANIFEST_READY": ["01-breaking-changes-manifest.json"],
    "TOOLING_SCOUT_READY": ["02-tooling-scout-report.json"],
    "BUILD_GATE_READY": ["03-build-audit.json"],
    "SCAN_READY": ["04-flag-index.json"],
}

RETRY_SCRIPT = pathlib.Path(
    ".claude/skills/jade-core-retry-router/scripts/retry_router.py"
)
MAX_RETRIES = 3


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
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


# ------------------------------------------------------------------
# PROGRESS.md writer
# ------------------------------------------------------------------
def write_progress_md(artifacts: pathlib.Path, state: Dict, cfg: Dict) -> None:
    path = artifacts / "PROGRESS.md"
    lines = [
        f"# {cfg['run_id']} — Migration Progress",
        "",
        f"**Source:** {cfg['source_version']} → **Target:** {cfg['target_version']}",
        f"**Current state:** {state['state']}",
        f"**Updated:** {state['updated_at']}",
        "",
        "| Phase | Status | Details |",
        "|-------|--------|---------|",
    ]
    hist_path = artifacts / "phase-history.log.jsonl"
    if hist_path.exists():
        for raw in hist_path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                continue
            phase = entry.get("phase", "?")
            status = entry.get("status", "?")
            msg = entry.get("message", "")
            emoji = "✅" if status == "OK" else ("🔴" if status == "ERROR" else "🟡")
            lines.append(f"| {emoji} {phase} | {status} | {msg} |")
    try:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except (OSError, UnicodeEncodeError):
        pass


# ------------------------------------------------------------------
# Phase processors
# ------------------------------------------------------------------
def check_gate_artifacts(phase: str, artifacts: pathlib.Path, state: Dict) -> str:
    required = REQUIRED_ARTIFACTS.get(phase, [])
    for af in required:
        if not (artifacts / af).exists():
            fail(
                artifacts,
                state,
                "ARTIFACT_MISSING",
                f"Required for {phase}: {artifacts / af}",
            )
            return "ARTIFACT_MISSING"
    return "OK"


def process_rule_batch(
    cfg: Dict,
    artifacts: pathlib.Path,
    state: Dict,
    hist_path: pathlib.Path,
    state_path: pathlib.Path,
    rule_status_path: pathlib.Path,
) -> str:
    queue_path = artifacts / "05-rule-queue.json"
    if not queue_path.exists():
        return fail(
            artifacts, state, "MISSING_RULE_QUEUE", "05-rule-queue.json not found"
        )

    queue = read_json(queue_path)
    rules: List[str] = queue.get("rules", [])
    if not isinstance(rules, list) or not rules:
        return "NO_MORE_RULES"

    rstatus = {}
    if rule_status_path.exists():
        try:
            rstatus = read_json(rule_status_path).get("rules", {})
        except (json.JSONDecodeError, OSError):
            pass

    for rule_id in rules:
        entry = rstatus.get(rule_id, {})

        if entry.get("status") in ("DONE", "ESCALATED"):
            continue

        state["current_rule_id"] = rule_id
        state["state"] = "RULE_BATCH_LOOP"
        state["updated_at"] = iso_now()
        write_json(state_path, state)

        append_jsonl(
            hist_path,
            {
                "ts": iso_now(),
                "phase": "RULE_BATCH_LOOP",
                "status": "OK",
                "message": f"Processing rule {rule_id}",
                "artifacts": ["05-rule-batch-status.json"],
            },
        )

        # Simulate: batch-prep, dispatch, verify
        batch_artifact = artifacts / f"05-rule-batch-{rule_id}.json"
        if not batch_artifact.exists():
            rstatus[rule_id] = {
                "status": "SKIPPED",
                "reason": "batch artifact missing",
                "updated_at": iso_now(),
            }
            state["failure_reason"] = (
                f"Batch missing for {rule_id}; manual run required"
            )
            write_json(rule_status_path, {"run_id": cfg["run_id"], "rules": rstatus})
            write_progress_md(artifacts, state, cfg)
            return "ARTIFACT_MISSING"

        verify_log = artifacts / "07-build.log"
        if not verify_log.exists():
            rstatus[rule_id] = {
                "status": "PENDING_VERIFY",
                "updated_at": iso_now(),
                "note": "07-build.log missing — run verification manually; if passed, mark as DONE here",
            }
            write_json(rule_status_path, {"run_id": cfg["run_id"], "rules": rstatus})
            write_progress_md(artifacts, state, cfg)
            return "VERIFY_FAIL"

        # Check build log for success
        try:
            vtext = verify_log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            vtext = ""
        if "BUILD SUCCESSFUL" in vtext or "BUILD SUCCESS" in vtext:
            rstatus[rule_id] = {"status": "DONE", "updated_at": iso_now()}
            write_json(rule_status_path, {"run_id": cfg["run_id"], "rules": rstatus})
            write_progress_md(artifacts, state, cfg)
            append_jsonl(
                hist_path,
                {
                    "ts": iso_now(),
                    "phase": "RULE_BATCH_LOOP",
                    "status": "OK",
                    "message": f"Completed rule {rule_id}",
                    "artifacts": ["rule-status.json", "07-build.log"],
                },
            )
            return "NEXT_RULE"

        return "VERIFY_FAIL"

    return "NO_MORE_RULES"


def process_retry(cfg: Dict, artifacts: pathlib.Path, state: Dict) -> str:
    if not RETRY_SCRIPT.exists():
        return fail(
            artifacts,
            state,
            "RETRY_SCRIPT_MISSING",
            f"Retry router script not found: {RETRY_SCRIPT}",
        )

    result = subprocess.run(
        [
            sys.executable,
            str(RETRY_SCRIPT),
            "--artifacts",
            str(artifacts),
            "--max-retries",
            str(MAX_RETRIES),
        ],
        capture_output=True,
        text=True,
    )
    print(result.stdout.strip() or f"retry-router exit={result.returncode}")

    final_path = artifacts / "08-final-status.json"
    if not final_path.exists():
        return "RETRY"

    try:
        final = read_json(final_path)
    except (json.JSONDecodeError, OSError):
        return "RETRY"

    current_rule = state.get("current_rule_id", "")
    rules_status = final.get("rules", {})
    rule_result = rules_status.get(current_rule, {})

    if rule_result.get("status") in ("ESCALATED", "ESCALATED_TO_LLM"):
        append_jsonl(
            artifacts / "phase-history.log.jsonl",
            {
                "ts": iso_now(),
                "phase": "RULE_RETRY",
                "status": "OK",
                "message": f"Rule {current_rule} escalated after {MAX_RETRIES} retries",
                "artifacts": ["08-escalations.json", "ACTION_REQUIRED.md"],
            },
        )
        return "ESCALATE"
    if rule_result.get("status") == "REQUEUED":
        return "RETRY"
    if final.get("status") == "ALL_CLEAR":
        return "RETRY"

    return "RETRY"


def process_escalate(artifacts: pathlib.Path, state: Dict) -> str:
    rule_id = state.get("current_rule_id", "unknown")
    rule_status_path = artifacts / "rule-status.json"
    if rule_status_path.exists():
        try:
            rstatus = read_json(rule_status_path)
        except (json.JSONDecodeError, OSError):
            rstatus = {"rules": {}}
    else:
        rstatus = {"rules": {}}
    rstatus.setdefault("rules", {})[rule_id] = {
        "status": "ESCALATED",
        "updated_at": iso_now(),
    }
    write_json(rule_status_path, rstatus)
    append_jsonl(
        artifacts / "phase-history.log.jsonl",
        {
            "ts": iso_now(),
            "phase": "RULE_ESCALATE",
            "status": "OK",
            "message": f"Rule {rule_id} skipped (escalated)",
            "artifacts": ["rule-status.json"],
        },
    )
    return "OK"


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
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
    required_keys = {
        "run_id",
        "baseline_path",
        "workspace_path",
        "artifacts_path",
        "source_version",
        "target_version",
    }
    missing = sorted(required_keys - set(cfg.keys()))
    if missing:
        print(
            f"ERROR [CONFIG_INVALID] Missing keys: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 2

    artifacts = pathlib.Path(cfg["artifacts_path"])
    state_path = artifacts / "00-run-state.json"
    hist_path = artifacts / "phase-history.log.jsonl"
    rule_status_path = artifacts / "rule-status.json"

    # INIT — initialize or load state
    if state_path.exists():
        try:
            state = read_json(state_path)
        except (json.JSONDecodeError, OSError):
            state = {}
    else:
        state = {}

    if not state or state.get("state") in TERMINAL_STATES or state.get("state") is None:
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

    # WORKSPACE_READY — isolate (once per run)
    baseline = pathlib.Path(cfg["baseline_path"])
    workspace = pathlib.Path(cfg["workspace_path"])
    if not workspace.exists():
        if not baseline.exists():
            outcome = fail(
                artifacts, state, "BASELINE_MISSING", f"Baseline not found: {baseline}"
            )
            write_progress_md(artifacts, state, cfg)
            return 2 if outcome == "FAILED" else 0
        try:
            shutil.copytree(
                baseline, workspace, ignore=shutil.ignore_patterns("doc", "examples")
            )
        except shutil.Error as exc:
            outcome = fail(
                artifacts,
                state,
                "COPY_FAILED",
                f"Failed to copy {baseline} → {workspace}: {exc}",
            )
            write_progress_md(artifacts, state, cfg)
            return 2 if outcome == "FAILED" else 0

    if state.get("state") in ("INIT", "FAILED") or (
        state.get("state") == "WORKSPACE_READY" and not hist_path.exists()
    ):
        state["state"] = "WORKSPACE_READY"
        state["updated_at"] = iso_now()
        write_json(state_path, state)
        append_jsonl(
            hist_path,
            {
                "ts": iso_now(),
                "phase": "WORKSPACE_READY",
                "status": "OK",
                "message": f"Workspace ready: {workspace}",
                "artifacts": ["00-run-state.json"],
            },
        )
        write_progress_md(artifacts, state, cfg)

    # State machine loop
    while state["state"] not in TERMINAL_STATES:
        current = state["state"]
        outcome: str = "OK"

        if current in ("INIT", "WORKSPACE_READY"):
            outcome = "OK"
        elif current in REQUIRED_ARTIFACTS:
            outcome = check_gate_artifacts(current, artifacts, state)
        elif current == "RULE_BATCH_LOOP":
            outcome = process_rule_batch(
                cfg, artifacts, state, hist_path, state_path, rule_status_path
            )
        elif current == "RULE_RETRY":
            outcome = process_retry(cfg, artifacts, state)
        elif current == "RULE_ESCALATE":
            outcome = process_escalate(artifacts, state)
        elif current == "VERIFIED":
            outcome = "OK"
        else:
            outcome = fail(
                artifacts, state, "UNKNOWN_STATE", f"No handler for state: {current}"
            )

        transitions = TRANSITIONS.get(current, {})
        next_state = transitions.get(outcome)
        if next_state is None:
            return fail(
                artifacts,
                state,
                "TRANSITION_ERROR",
                f"No transition from {current} for outcome {outcome}",
            )

        state["state"] = next_state
        state["updated_at"] = iso_now()
        write_json(state_path, state)
        write_progress_md(artifacts, state, cfg)

        if next_state in TERMINAL_STATES:
            append_jsonl(
                hist_path,
                {
                    "ts": iso_now(),
                    "phase": next_state,
                    "status": "OK" if next_state == "DONE" else "ERROR",
                    "message": f"Run terminated: {next_state}",
                    "artifacts": ["00-run-state.json", "PROGRESS.md"],
                },
            )
            break

    print(state["state"])
    return 0 if state["state"] == "DONE" else (2 if state["state"] == "FAILED" else 0)


if __name__ == "__main__":
    raise SystemExit(main())
