#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

# ------------------------------------------------------------------
# Transition table — current state + outcome → next state
# ------------------------------------------------------------------
TRANSITIONS: Dict[str, Dict[str, str]] = {
    "INIT": {"OK": "WORKSPACE_READY"},
    "WORKSPACE_READY": {"OK": "MANIFEST_READY"},
    "MANIFEST_READY": {
        "OK": "TOOLING_SCOUT_READY",
        "ARTIFACT_MISSING": "FAILED",
        "ARTIFACT_TAMPERED": "FAILED",
        "AWAIT_AGENT": "AWAITING_AGENT",
    },
    "TOOLING_SCOUT_READY": {
        "OK": "BUILD_GATE_READY",
        "ARTIFACT_MISSING": "FAILED",
        "ARTIFACT_TAMPERED": "FAILED",
        "SCRIPT_ERROR": "FAILED",
    },
    "BUILD_GATE_READY": {
        "OK": "KNOWLEDGE_GRAPH_READY",
        "ARTIFACT_MISSING": "FAILED",
        "ARTIFACT_TAMPERED": "FAILED",
        "SCRIPT_ERROR": "FAILED",
    },
    "KNOWLEDGE_GRAPH_READY": {
        "OK": "SCAN_READY",
        "DEPENDENCY_MISSING": "SCAN_READY",
        "ARTIFACT_MISSING": "FAILED",
        "ARTIFACT_TAMPERED": "FAILED",
        "SCRIPT_ERROR": "FAILED",
    },
    "SCAN_READY": {
        "OK": "RULE_BATCH_LOOP",
        "ARTIFACT_MISSING": "FAILED",
        "ARTIFACT_TAMPERED": "FAILED",
        "SCRIPT_ERROR": "FAILED",
    },
    "RULE_BATCH_LOOP": {
        "NEXT_RULE": "RULE_BATCH_LOOP",
        "NO_MORE_RULES": "VERIFIED",
        "VERIFY_FAIL": "RULE_RETRY",
        "ARTIFACT_MISSING": "FAILED",
        "ARTIFACT_TAMPERED": "FAILED",
        "AWAIT_AGENT": "AWAITING_AGENT",
    },
    "RULE_RETRY": {"RETRY": "RULE_BATCH_LOOP", "ESCALATE": "RULE_ESCALATE"},
    "RULE_ESCALATE": {"OK": "RULE_BATCH_LOOP"},
    "VERIFIED": {"OK": "RUNTIME_VERIFY"},
    "RUNTIME_VERIFY": {"OK": "DONE", "VERIFY_FAIL": "FAILED", "SCRIPT_ERROR": "FAILED"},
    "AWAITING_AGENT": {"OK": "RESUME"},
}

TERMINAL_STATES = {"DONE", "FAILED", "AWAITING_SOURCE_INPUT", "AWAITING_AGENT"}

# Artifacts required for each gate phase
REQUIRED_ARTIFACTS: Dict[str, List[str]] = {
    "MANIFEST_READY": ["01-breaking-changes-manifest.json"],
    "TOOLING_SCOUT_READY": ["02-tooling-scout-report.json"],
    "BUILD_GATE_READY": ["03-build-audit.json"],
    "KNOWLEDGE_GRAPH_READY": ["03.5-knowledge-graph.json"],
    "SCAN_READY": ["04-flag-index.json"],
    "RUNTIME_VERIFY": ["07-runtime-verify.json"],
}

ARTIFACT_CONTENT_RULES: Dict[str, Dict[str, Any]] = {
    "01-breaking-changes-manifest.json": {
        "json_keys_required": [
            "rules",
            "source_version",
            "target_version",
            "generated_at",
        ],
        "json_nonempty_list": ["rules"],
        "json_nonempty_str": ["source_version", "target_version"],
    },
    "02-tooling-scout-report.json": {
        "json_keys_required": ["tools", "findings"],
        "json_nonempty_dict": ["tools"],
    },
    "03-build-audit.json": {
        "json_keys_required": ["build_system", "build_file"],
        "json_nonempty_str": ["build_system", "build_file"],
        "json_contains": {
            "env": {
                "docker": "available",
            }
        },
    },
    "03.5-knowledge-graph.json": {
        "json_keys_required": ["nodes", "edges", "stats"],
        "json_nonempty_dict": ["nodes", "edges", "stats"],
    },
    "04-flag-index.json": {
        "json_keys_required": ["flags", "total_flags", "total_files_scanned"],
        "json_len_match": [("flags", "total_flags")],
    },
    "07-runtime-verify.json": {
        "json_keys_required": [
            "results",
            "overall_pass",
            "total_consumers",
            "passed",
            "failed",
        ],
        "json_len_match": [("results", "total_consumers")],
    },
}
"""Content validation rules for each phase artifact.
json_keys_required   — top-level keys must exist
json_nonempty_list   — key must be a list with len > 0
json_nonempty_str    — key must be a non-empty string
json_nonempty_dict   — key must be a dict with at least 1 entry
json_nonzero_int     — key must be an int > 0
json_contains        — nested key path must have expected value
json_len_match       — len(key[0]) must equal int(key[1])
"""

BUILD_LOG_VALIDATION = {
    "require_substr": ["[javac]", "BUILD SUCCESSFUL"],
}
"""07-build.log must contain BOTH required substrings to pass."""

MUTABLE_ARTIFACTS = {"07-build.log"}
"""Artifacts that may legitimately change across rule iterations.
For these, hash is updated after each successful verification instead
of being treated as tamper-evident immutable records."""

SCRIPT_PHASES: Dict[str, Dict[str, Any]] = {
    "TOOLING_SCOUT_READY": {
        "script": ".claude/skills/jade-core-tooling-scout/scripts/tooling_scout.py",
        "args": ["--modern-jdk", "_JAVA_HOME_", "--config", "_CONFIG_", "--all"],
    },
    "BUILD_GATE_READY": {
        "script": ".claude/skills/jade-core-build-fixer/scripts/build_audit.py",
        "args": ["--config", "_CONFIG_"],
    },
    "KNOWLEDGE_GRAPH_READY": {
        "script": ".claude/skills/jade-core-knowledge-graph/scripts/build_graph.py",
        "args": ["--workspace", "_WORKSPACE_", "--artifacts-dir", "_ARTIFACTS_"],
    },
    "SCAN_READY": {
        "script": ".claude/skills/jade-core-scanner/scripts/scan_and_tag.py",
        "args": ["--workspace", "_WORKSPACE_", "--artifacts", "_ARTIFACTS_"],
    },
    "RUNTIME_VERIFY": {
        "script": ".claude/skills/jade-core-verification/scripts/runtime_verify.py",
        "args": [
            "--workspace",
            "_WORKSPACE_",
            "--artifacts",
            "_ARTIFACTS_",
            "--config",
            "_CONFIG_",
        ],
    },
}
"""Script phases that the orchestrator can auto-invoke in --run mode.
Placeholders (_JAVA_HOME_, _CONFIG_, _WORKSPACE_, _ARTIFACTS_) are
resolved at call time."""

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


def _validate_artifact(path: pathlib.Path, phase: str) -> Tuple[bool, str]:
    """Validate artifact content against rules for *phase*.

    Returns (ok, reason).  If ok is False, reason explains why.
    """
    # JSON artifacts
    rules = ARTIFACT_CONTENT_RULES.get(path.name)
    if rules:
        try:
            data = read_json(path)
        except (json.JSONDecodeError, OSError) as exc:
            return False, f"invalid JSON: {exc}"
        for key in rules.get("json_keys_required", []):
            if key not in data:
                return False, f"missing required key: {key}"
        for key in rules.get("json_nonempty_list", []):
            val = data.get(key)
            if not isinstance(val, list) or len(val) == 0:
                return False, f"key '{key}' must be a non-empty list"
        for key in rules.get("json_nonempty_str", []):
            val = data.get(key)
            if not isinstance(val, str) or not val.strip():
                return False, f"key '{key}' must be a non-empty string"
        for key in rules.get("json_nonempty_dict", []):
            val = data.get(key)
            if not isinstance(val, dict) or len(val) == 0:
                return False, f"key '{key}' must be a non-empty dict"
        for key in rules.get("json_nonzero_int", []):
            val = data.get(key)
            if not isinstance(val, (int, float)) or val <= 0:
                return False, f"key '{key}' must be > 0"
        for list_key, count_key in rules.get("json_len_match", []):
            lst = data.get(list_key)
            cnt = data.get(count_key)
            if not isinstance(lst, list) or not isinstance(cnt, int) or len(lst) != cnt:
                return (
                    False,
                    f"len({list_key})={len(lst) if isinstance(lst, list) else '?'} != {count_key}={cnt}",
                )
        for top_key, expected in rules.get("json_contains", {}).items():
            actual = data.get(top_key, {})
            if not isinstance(actual, dict):
                return False, f"key '{top_key}' must be a dict"
            for sub_key, sub_val in expected.items():
                if actual.get(sub_key) != sub_val:
                    return (
                        False,
                        f"expected {top_key}.{sub_key}='{sub_val}', got '{actual.get(sub_key)}'",
                    )
        return True, ""

    # Text artifacts (07-build.log)
    if path.name == "07-build.log":
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return False, f"cannot read: {exc}"
        for substr in BUILD_LOG_VALIDATION.get("require_substr", []):
            if substr not in text:
                return False, f"build log missing required marker: '{substr}'"
        return True, ""

    # Unrecognised artifact — pass (future-proofing)
    return True, ""


def _compute_hash(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_artifact(path: pathlib.Path, phase: str, state: Dict) -> str:
    """Verify artifact integrity via hash chain.

    Returns "OK", "ARTIFACT_TAMPERED", or "OK" (first-time store).
    Mutable artifacts (07-build.log) update their hash silently on change.
    Immutable artifacts reject any hash change.
    """
    hashes = state.setdefault("artifact_hashes", {})
    name = path.name
    if not path.exists():
        return "ARTIFACT_MISSING"

    current = _compute_hash(path)
    if name not in hashes:
        hashes[name] = current
        return "OK"

    stored = hashes[name]
    if current == stored:
        return "OK"

    if name in MUTABLE_ARTIFACTS:
        hashes[name] = current
        return "OK"

    return "ARTIFACT_TAMPERED"


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
def _run_script_phase(phase: str, cfg: Dict) -> str:
    """Invoke the script for *phase* as a subprocess.  Returns outcome."""
    entry = SCRIPT_PHASES.get(phase)
    if not entry:
        return "OK"

    script = pathlib.Path(entry["script"])
    if not script.exists():
        print(f"ERROR [SCRIPT_MISSING] {script}", file=sys.stderr)
        return "ARTIFACT_MISSING"

    args: List[str] = []
    for a in list(entry["args"]):
        a = str(a)
        if a == "_JAVA_HOME_":
            args.append(os.environ.get("JAVA_HOME", "java"))
        elif a == "_CONFIG_":
            args.append(str(pathlib.Path(cfg["artifacts_path"]) / "00-run-config.json"))
        elif a == "_WORKSPACE_":
            args.append(str(cfg["workspace_path"]))
        elif a == "_ARTIFACTS_":
            args.append(str(cfg["artifacts_path"]))
        else:
            args.append(a)

    proc = subprocess.run(
        [sys.executable, str(script)] + args,
        capture_output=True,
        text=True,
        timeout=600,
    )
    print(proc.stdout.strip() or f"(script produced no stdout)")
    if proc.stderr:
        print(proc.stderr.strip(), file=sys.stderr)

    if proc.returncode == 0:
        return "OK"
    if proc.returncode < 0:
        print(
            f"ERROR [SCRIPT_SIGNALED] {script.name} killed by signal {-proc.returncode}",
            file=sys.stderr,
        )
        return "SCRIPT_ERROR"
    if proc.returncode == 3:
        print(
            f"ERROR [DOCKER_MISSING] {script.name} exited 3 (environment error)",
            file=sys.stderr,
        )
        return "SCRIPT_ERROR"
    print(
        f"ERROR [SCRIPT_ERROR] {script.name} exited {proc.returncode}",
        file=sys.stderr,
    )
    return "SCRIPT_ERROR"


def _pause_for_agent(
    phase: str, artifacts: pathlib.Path, state: Dict, cfg: Dict
) -> str:
    """Pause pipeline for an agent reasoning phase.  Writes AWAITING_AGENT.md."""
    md = artifacts / "AWAITING_AGENT.md"
    workspace = cfg.get("workspace_path", "workspace")
    if phase == "MANIFEST_READY":
        md.write_text(
            f"""# AWAITING AGENT — {phase}

The pipeline has paused at the **change collector** phase.

## What to do

1. Identify Java {cfg["source_version"]} → {cfg["target_version"]} breaking-change sources
2. Fetch each source:
   ```
   python .claude/skills/jade-core-change-collector/scripts/fetch_source.py \\
     --run-config {cfg["artifacts_path"]}/00-run-config.json \\
     --source-url "<URL>" --source-label "<label>"
   ```
3. Read the extracted content from `{cfg["artifacts_path"]}/01-source-content-*.txt`
4. Extract rules via reading comprehension — every rule MUST come from the source text
5. Save rules to `{cfg["artifacts_path"]}/01-extracted-rules.tmp.json`
6. Validate and write manifest:
   ```
   python .claude/skills/jade-core-change-collector/scripts/write_manifest.py \\
     --input {cfg["artifacts_path"]}/01-extracted-rules.tmp.json \\
     --artifacts-dir {cfg["artifacts_path"]} \\
     --run-id {cfg["run_id"]} \\
     --source-version {cfg["source_version"]} \\
     --target-version {cfg["target_version"]}
   ```

## Resume

After producing `01-breaking-changes-manifest.json`:
```
python .claude/skills/jade-core-orchestrator/scripts/orchestrator.py --config {cfg["artifacts_path"]}/00-run-config.json --run
```
""",
            encoding="utf-8",
        )
    elif phase == "RULE_BATCH_LOOP":
        md.write_text(
            f"""# AWAITING AGENT — {phase}

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
""",
            encoding="utf-8",
        )

    state["awaiting_phase"] = phase
    state["state"] = "AWAITING_AGENT"
    state["updated_at"] = iso_now()
    write_json(artifacts / "00-run-state.json", state)
    append_jsonl(
        artifacts / "phase-history.log.jsonl",
        {
            "ts": iso_now(),
            "phase": phase,
            "status": "OK",
            "message": f"Paused for agent input — see AWAITING_AGENT.md",
            "artifacts": ["AWAITING_AGENT.md"],
        },
    )
    print(f"AWAITING AGENT for {phase} — see {md}")
    print(f"Re-run with --run to continue from {phase}")
    return "AWAIT_AGENT"


def check_gate_artifacts(phase: str, artifacts: pathlib.Path, state: Dict) -> str:
    required = REQUIRED_ARTIFACTS.get(phase, [])
    for af in required:
        fp = artifacts / af
        if not fp.exists():
            fail(
                artifacts,
                state,
                "ARTIFACT_MISSING",
                f"Required for {phase}: {fp}",
            )
            return "ARTIFACT_MISSING"
        ok, reason = _validate_artifact(fp, phase)
        if not ok:
            fail(
                artifacts,
                state,
                "UNTRUSTED",
                f"Artifact {af} failed content validation: {reason}",
            )
            return "ARTIFACT_MISSING"
        integrity = _verify_artifact(fp, phase, state)
        if integrity == "ARTIFACT_TAMPERED":
            current = _compute_hash(fp)
            stored = state.get("artifact_hashes", {}).get(af, "none")
            fail(
                artifacts,
                state,
                "ARTIFACT_TAMPERED",
                f"Artifact {af} was modified after gate approval (stored={stored[:12]}..., current={current[:12]}...)",
            )
            return "ARTIFACT_TAMPERED"
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
        state["failure_reason"] = "MISSING_RULE_QUEUE"
        state["updated_at"] = iso_now()
        write_json(state_path, state)
        write_json(
            artifacts / "failure-summary.json",
            {
                "code": "MISSING_RULE_QUEUE",
                "message": "05-rule-queue.json not found",
                "updated_at": state["updated_at"],
            },
        )
        append_jsonl(
            hist_path,
            {
                "ts": iso_now(),
                "phase": "RULE_BATCH_LOOP",
                "status": "ERROR",
                "message": "MISSING_RULE_QUEUE: 05-rule-queue.json not found",
                "artifacts": ["failure-summary.json"],
            },
        )
        print(
            "ERROR [MISSING_RULE_QUEUE] 05-rule-queue.json not found", file=sys.stderr
        )
        return "ARTIFACT_MISSING"

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

        ok, reason = _validate_artifact(verify_log, "RULE_BATCH_LOOP")
        if not ok:
            state["failure_reason"] = f"Build log validation failed: {reason}"
            write_json(state_path, state)
            rstatus[rule_id] = {
                "status": "PENDING_VERIFY",
                "updated_at": iso_now(),
                "note": f"07-build.log failed validation: {reason}",
            }
            write_json(rule_status_path, {"run_id": cfg["run_id"], "rules": rstatus})
            write_progress_md(artifacts, state, cfg)
            return "VERIFY_FAIL"

        integrity = _verify_artifact(verify_log, "RULE_BATCH_LOOP", state)
        if integrity == "ARTIFACT_TAMPERED":
            state["failure_reason"] = (
                f"Build log tampered (hash mismatch) for rule {rule_id}"
            )
            write_json(state_path, state)
            return "ARTIFACT_TAMPERED"

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
    parser.add_argument(
        "--run",
        action="store_true",
        help="Execute script phases as subprocesses (auto-invoke tooling scout, builder, scanner)",
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
    # Resume from AWAITING_AGENT if applicable
    if state.get("state") == "AWAITING_AGENT":
        resume_phase = state.get("awaiting_phase", "")
        if resume_phase:
            state["state"] = resume_phase
            state["awaiting_phase"] = None
            write_json(state_path, state)
            append_jsonl(
                hist_path,
                {
                    "ts": iso_now(),
                    "phase": resume_phase,
                    "status": "OK",
                    "message": f"Resumed from AWAITING_AGENT",
                    "artifacts": ["00-run-state.json"],
                },
            )
            print(f"Resumed from AWAITING_AGENT → {resume_phase}")
        else:
            fail(
                artifacts,
                state,
                "RESUME_ERROR",
                "AWAITING_AGENT state has no awaiting_phase to resume to",
            )
            write_progress_md(artifacts, state, cfg)
            return 2

    while state["state"] not in TERMINAL_STATES:
        current = state["state"]
        outcome: str = "OK"

        if current in ("INIT", "WORKSPACE_READY"):
            outcome = "OK"
        elif current in REQUIRED_ARTIFACTS:
            af = REQUIRED_ARTIFACTS.get(current, [])
            artifact_missing = not all((artifacts / a).exists() for a in af)
            if args.run and current in SCRIPT_PHASES and artifact_missing:
                script_outcome = _run_script_phase(current, cfg)
                if script_outcome != "OK":
                    outcome = script_outcome
                else:
                    outcome = check_gate_artifacts(current, artifacts, state)
            # In --run mode, pause at agent phases if no artifact
            elif args.run and current not in SCRIPT_PHASES:
                af = REQUIRED_ARTIFACTS.get(current, [])
                missing = not all((artifacts / a).exists() for a in af)
                if missing:
                    outcome = _pause_for_agent(current, artifacts, state, cfg)
                else:
                    outcome = check_gate_artifacts(current, artifacts, state)
            else:
                outcome = check_gate_artifacts(current, artifacts, state)
        elif current == "RULE_BATCH_LOOP":
            if args.run and not (artifacts / "05-rule-queue.json").exists():
                # Auto-create empty queue when scanner found no flags
                flag_index = artifacts / "04-flag-index.json"
                if flag_index.exists():
                    fi = read_json(flag_index)
                    if fi.get("total_flags", 0) == 0:
                        write_json(
                            artifacts / "05-rule-queue.json",
                            {"run_id": state.get("run_id", ""), "rules": []},
                        )
                        # Fall through to process_rule_batch → NO_MORE_RULES →
                        outcome = process_rule_batch(
                            cfg,
                            artifacts,
                            state,
                            hist_path,
                            state_path,
                            rule_status_path,
                        )
                    else:
                        outcome = _pause_for_agent(current, artifacts, state, cfg)
                        break
                else:
                    outcome = _pause_for_agent(current, artifacts, state, cfg)
                    break
            else:
                outcome = process_rule_batch(
                    cfg, artifacts, state, hist_path, state_path, rule_status_path
                )
        elif current == "RULE_RETRY":
            outcome = process_retry(cfg, artifacts, state)
        elif current == "RULE_ESCALATE":
            outcome = process_escalate(artifacts, state)
        elif current == "VERIFIED":
            outcome = "OK"
        elif current == "RUNTIME_VERIFY":
            if args.run and current in SCRIPT_PHASES:
                outcome = _run_script_phase(current, cfg)
                if outcome == "OK":
                    outcome = check_gate_artifacts(current, artifacts, state)
                    if outcome == "OK":
                        rv_path = artifacts / "07-runtime-verify.json"
                        try:
                            rv = read_json(rv_path)
                            if not rv.get("overall_pass", False):
                                outcome = "VERIFY_FAIL"
                        except (json.JSONDecodeError, OSError):
                            outcome = "ARTIFACT_MISSING"
            else:
                outcome = check_gate_artifacts(current, artifacts, state)
                if outcome == "OK":
                    rv_path = artifacts / "07-runtime-verify.json"
                    try:
                        rv = read_json(rv_path)
                        if not rv.get("overall_pass", False):
                            outcome = "VERIFY_FAIL"
                    except (json.JSONDecodeError, OSError):
                        outcome = "ARTIFACT_MISSING"
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
