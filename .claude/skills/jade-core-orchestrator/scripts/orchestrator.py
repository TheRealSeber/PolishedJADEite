#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
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
        "SHARD_ROLLBACK_PENDING": "AWAITING_AGENT",
    },
    "RULE_RETRY": {"RETRY": "RULE_BATCH_LOOP", "ESCALATE": "RULE_ESCALATE"},
    "RULE_ESCALATE": {"OK": "RULE_BATCH_LOOP"},
    "VERIFIED": {"OK": "RUNTIME_VERIFY"},
    "RUNTIME_VERIFY": {"OK": "DONE", "VERIFY_FAIL": "FAILED", "SCRIPT_ERROR": "FAILED"},
}

# AWAITING_AGENT is a terminal pause state. Entering it is table-driven
# (RULE_BATCH_LOOP --AWAIT_AGENT--> AWAITING_AGENT); resuming is handled by
# dedicated code that reads state.awaiting_phase and jumps straight to the
# target phase, bypassing the transition table.

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
        "json_keys_required": ["build_system", "build_file", "build_exit_code"],
        "json_nonempty_str": ["build_system", "build_file"],
        # AGENTS.md #15: only BUILD SUCCESSFUL with exit 0 counts as build
        # evidence. Without this the gate accepted an audit whose own recorded
        # build_exit_code was non-zero, and the run advanced on a failed build.
        "json_equals": {"build_exit_code": 0},
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
json_equals          — key must equal the expected value exactly
json_contains        — nested key path must have expected value
json_len_match       — len(key[0]) must equal int(key[1])
"""

BUILD_LOG_VALIDATION = {
    "require_substr": ["[javac]", "BUILD SUCCESSFUL"],
}
"""07-build.log must contain BOTH required substrings to pass."""

MUTABLE_ARTIFACTS = {"07-build.log", "03.5-knowledge-graph.json"}
"""Artifacts that may legitimately change across rule iterations.

- ``07-build.log``: rewritten per rule during verification.
- ``03.5-knowledge-graph.json``: rebuilt at batch boundaries when
  ``rebuild_graph_per_batch`` is enabled in the run config.

The knowledge graph is advisory by design, so tamper-evidence is not
enforced on it: any change is silently accepted and its hash refreshed.
Structural validity (non-empty nodes/edges/stats) is still enforced at the
KNOWLEDGE_GRAPH_READY gate.
"""

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
        "acceptable_exit_codes": (0, 1),
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
# Agent-mode rule dispatch (RULE_BATCH_LOOP agent recipes)
# ------------------------------------------------------------------
# A rule whose recipe-registry.json entry carries "mode": "agent" is not
# dispatched as a script subprocess. Instead the orchestrator pauses with
# AWAITING_AGENT.md describing the shard plan and the per-shard checkpoint
# / verify / gate / record / accept-or-rollback commands, and resumes only
# once every shard in that rule's checkpoint ledger reaches a terminal
# state (ACCEPTED or ROLLED_BACK). See agent_registry_entry,
# _process_agent_rule, and _agent_shard_instructions below.
#
# Binding rule-execution order ranks body-local blast_class rules ahead of
# signature blast_class rules, ahead of unclassified rules; suggested_order
# from the knowledge graph is a binding second-order tie-break within a
# blast_class band. See compute_binding_rule_order / effective_rule_order.
BLAST_CLASS_RANK: Dict[str, int] = {"body-local": 0, "signature": 1}
UNCLASSIFIED_BLAST_RANK = 2

SHARD_CHECKPOINT_SCRIPT = pathlib.Path(
    ".claude/skills/jade-core-orchestrator/scripts/shard_checkpoint.py"
)
DISPATCHER_SCRIPT = pathlib.Path(
    ".claude/skills/jade-core-rule-dispatcher/scripts/dispatcher.py"
)
VERIFY_SHARD_SCRIPT = pathlib.Path(
    ".claude/skills/jade-core-verification/scripts/verify_shard.py"
)
GATE_SIGNATURES_SCRIPT = pathlib.Path(
    ".claude/skills/jade-core-verification/scripts/gate_signatures.py"
)

RECIPE_REGISTRY_PATH = pathlib.Path(
    ".claude/skills/jade-core-rule-dispatcher/recipe-registry.json"
)
"""Recipe registry read directly (S3 never imports the S1/S2 modules).

Relative to the process cwd, matching every other script/artifact path
constant in this module (RETRY_SCRIPT, SCRIPT_PHASES, ...) — never derived
from ``__file__`` here, since ``test_transition_table_integrity`` execs
this module's source with a bare namespace that has no ``__file__``.
"""

SHARD_LEDGER_STATES = ("CHECKPOINTED", "ACCEPTED", "ROLLED_BACK")


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
        for key, expected in rules.get("json_equals", {}).items():
            if data.get(key) != expected:
                return False, f"key '{key}' must equal {expected!r}, got {data.get(key)!r}"
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

    if proc.returncode in entry.get("acceptable_exit_codes", (0,)):
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


def _shard_commands(
    rule_id: str, shard_id: str, artifacts_path: str, workspace_path: str
) -> Dict[str, str]:
    """Build the six per-shard command strings for AWAITING_AGENT.md.

    These mirror the frozen CLI contract of dispatcher.py's agent mode and
    shard_checkpoint.py exactly (paths only — no source file content, no
    subprocess is ever invoked here).
    """
    a = artifacts_path
    r = rule_id
    s = shard_id
    w = workspace_path
    result_file = f"{a}/06-agent-result-{r}-{s}.json"
    after_graph = f"{a}/03.5-knowledge-graph-after-{s}.json"
    return {
        "checkpoint": (
            f"python {SHARD_CHECKPOINT_SCRIPT} --artifacts-dir {a} --rule-id {r} "
            f"--shard-id {s} --workspace {w} --create"
        ),
        "verify": (
            f"python {VERIFY_SHARD_SCRIPT} --artifacts-dir {a} --rule-id {r} "
            f"--shard-id {s}"
        ),
        "gate": (
            f"python {GATE_SIGNATURES_SCRIPT} --artifacts-dir {a} --rule-id {r} "
            f"--shard-id {s} --before-graph {a}/03.5-knowledge-graph.json "
            f"--after-graph {after_graph}"
        ),
        "record": (
            f"python {DISPATCHER_SCRIPT} --artifacts-dir {a} --rule-id {r} "
            f"--record-agent-result --shard-id {s} --result-file {result_file}"
        ),
        "accept": (
            f"python {SHARD_CHECKPOINT_SCRIPT} --artifacts-dir {a} --rule-id {r} "
            f"--shard-id {s} --workspace {w} --accept"
        ),
        "rollback": (
            f"python {SHARD_CHECKPOINT_SCRIPT} --artifacts-dir {a} --rule-id {r} "
            f'--shard-id {s} --workspace {w} --rollback --reason "<why>"'
        ),
    }


def _agent_shard_instructions(
    rule_id: str,
    shard_plan: Dict[str, Any],
    cfg: Dict,
    artifacts: pathlib.Path,
) -> str:
    """Build AWAITING_AGENT.md content for an agent-recipe RULE_BATCH_LOOP pause.

    Never includes source file paths (only counts) — see 'Shards' table below.
    Command strings are built directly from cfg + shard ids, mirroring the
    frozen dispatcher/shard_checkpoint CLI contracts; this module never
    imports or invokes those scripts.
    """
    artifacts_path = str(cfg.get("artifacts_path", artifacts))
    workspace_path = str(cfg.get("workspace_path", "workspace"))
    blast_class = shard_plan.get("blast_class") or "UNCLASSIFIED"
    shards = [s for s in shard_plan.get("shards", []) if isinstance(s, dict)]

    lines: List[str] = [
        "# AWAITING AGENT — RULE_BATCH_LOOP (agent recipe)",
        f"Rule: {rule_id} | blast_class: {blast_class} | shards: {len(shards)}",
        "",
        "## Anti-bypass",
        "",
        "**ANTI-BYPASS:** You are strictly forbidden from manually creating a batch",
        "artifact and marking it `DONE` or `NOOP` if flags exist for that rule.",
        "You must either (a) write a true registry recipe script to transform the flagged",
        "code, or (b) use `defer_rules.py` to defer modernization flags and preserve",
        "them as `// JADE-MODERNIZATION-DEFERRED` markers for future developers.",
        "Failure to comply is a pipeline integrity violation. An agent-result envelope",
        "reporting status `FIXED` with zero files is an additional integrity",
        "violation — an empty envelope must never be recorded as FIXED.",
        "",
        "## Shards",
        "",
        "| shard_id | class | parallel_safe | editable_files | entry_points |",
        "|----------|-------|----------------|----------------|--------------|",
    ]
    for shard in shards:
        sid = shard.get("shard_id", "")
        cls = shard.get("class", "")
        parallel_safe = shard.get("parallel_safe", False)
        n_editable = len(shard.get("editable_files") or [])
        n_entry = len(shard.get("entry_points") or [])
        lines.append(f"| {sid} | {cls} | {parallel_safe} | {n_editable} | {n_entry} |")

    lines += [
        "",
        "## Per-shard procedure",
        "",
        "For each shard, run these seven steps in order:",
        "",
        "1. Checkpoint the shard's editable files (git blob snapshot).",
        "2. Dispatch one subagent for the shard: it may edit only that shard's",
        "   `editable_files`; `read_only_context` is read-only. It writes a result",
        "   envelope to `result_file`.",
        "3. Verify the shard compiles (javac in Docker against the previous jar).",
        "4. Gate the shard's edits against the knowledge graph for signature leaks",
        "   outside the shard's editable set.",
        "5. Record the subagent's result envelope into `06-fix-results-<rule_id>.json`.",
        "6. If verify and gate both exited 0/1 and record exited 0: accept the shard",
        "   (the checkpoint blob is dropped; the edit is kept).",
        "7. Otherwise (verify/gate exited 2/3, or record exited 2/3/4): roll back the",
        "   shard to its checkpointed state, with a `--reason` explaining why.",
        "",
        "Shards with `parallel_safe: true` may be dispatched concurrently to",
        "independent subagents; `parallel_safe: false` shards must be run",
        "sequentially.",
        "",
    ]
    for shard in shards:
        sid = shard.get("shard_id", "")
        cmds = _shard_commands(rule_id, sid, artifacts_path, workspace_path)
        lines += [
            f"### {sid}",
            "",
            f"1. `{cmds['checkpoint']}`",
            "2. Dispatch the subagent for this shard.",
            f"3. `{cmds['verify']}`",
            f"4. `{cmds['gate']}`",
            f"5. `{cmds['record']}`",
            f"6. `{cmds['accept']}`",
            f"7. `{cmds['rollback']}`",
            "",
        ]

    lines += [
        "## Subagent contract",
        "",
        "One subagent per shard. It may edit only files listed in that shard's",
        "`editable_files`; `read_only_context` files may be read but never written.",
        "It returns a result envelope (schema_version, rule_id, shard_id, status,",
        "match_quality, diff_summary, files[], errors[], warnings[]) to the shard's",
        "`result_file`.",
        "",
        "## Resume",
        "",
        "```",
        f"python .claude/skills/jade-core-orchestrator/scripts/orchestrator.py --config {artifacts_path}/00-run-config.json --run",
        "```",
        "",
    ]
    return "\n".join(lines)



def _write_review_ledger(
    artifacts: pathlib.Path, rule_id: str, records: List[Dict[str, Any]]
) -> None:
    """Record accepted-but-unreviewed shards to REVIEW_REQUIRED.md.

    These edits are in the workspace and compile; what they lack is a human
    judgement the recipe declined to make on its own -- a security policy call,
    a behavioural tradeoff, a semantic equivalence it could not prove.
    """
    path = artifacts / "REVIEW_REQUIRED.md"
    existing = path.read_text(encoding="utf-8") if path.exists() else "# REVIEW REQUIRED\n"
    lines = [f"\n## {rule_id}\n"]
    for record in records:
        summary = str(record.get("diff_summary") or "").strip()
        lines.append(
            f"- `{record.get('shard_id')}` {record.get('file')} -- {summary}\n"
        )
    tmp = path.with_suffix(".md.tmp")
    tmp.write_text(existing + "".join(lines), encoding="utf-8")
    tmp.replace(path)


def _pause_for_agent(
    phase: str,
    artifacts: pathlib.Path,
    state: Dict,
    cfg: Dict,
    rule_id: Optional[str] = None,
    shard_plan: Optional[Dict[str, Any]] = None,
) -> str:
    """Pause pipeline for an agent reasoning phase.  Writes AWAITING_AGENT.md."""
    md = artifacts / "AWAITING_AGENT.md"
    workspace = cfg.get("workspace_path", "workspace")
    if phase == "RULE_BATCH_LOOP" and rule_id is not None and shard_plan is not None:
        md.write_text(
            _agent_shard_instructions(rule_id, shard_plan, cfg, artifacts),
            encoding="utf-8",
        )
    elif phase == "MANIFEST_READY":
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
    if rule_id is not None and shard_plan is not None:
        state["awaiting_rule_id"] = rule_id
        state["awaiting_shards"] = [
            s.get("shard_id") for s in shard_plan.get("shards", []) if isinstance(s, dict)
        ]
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
    if phase == "KNOWLEDGE_GRAPH_READY":
        state["graph"] = record_graph_freshness(artifacts)
    return "OK"


def _load_knowledge_graph(artifacts: pathlib.Path) -> Optional[Any]:
    """Load a KnowledgeGraph object from the 03.5 artifact.

    Returns None when the schema module or graph artifact is unavailable
    or unreadable — the caller treats this as advisory-only.
    """
    schema_path = (
        pathlib.Path(__file__).parents[2]
        / "jade-core-knowledge-graph"
        / "scripts"
        / "schema.py"
    )
    if not schema_path.exists():
        return None
    spec = importlib.util.spec_from_file_location("jade_kg_schema", schema_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        return None
    graph_path = artifacts / "03.5-knowledge-graph.json"
    if not graph_path.exists():
        return None
    try:
        return module.KnowledgeGraph.load(str(graph_path))
    except Exception:
        return None


def record_graph_freshness(artifacts: pathlib.Path) -> Optional[Dict[str, Any]]:
    """Record the 03.5 graph artifact's identity/freshness for run state.

    Returns None when the artifact is missing or unreadable; the caller
    stores that value (None) directly under ``state["graph"]``.
    """
    graph_path = artifacts / "03.5-knowledge-graph.json"
    if not graph_path.exists():
        return None
    try:
        data = read_json(graph_path)
    except (json.JSONDecodeError, OSError):
        return None
    source = data.get("source")
    source = source if isinstance(source, dict) else {}
    return {
        "schema_version": data.get("schema_version"),
        "content_hash": data.get("content_hash"),
        "java_files": source.get("java_files"),
        "source_identity": data.get("source_identity"),
        "diagnostics": data.get("diagnostics"),
    }


def rebuild_knowledge_graph(
    workspace: pathlib.Path,
    artifacts: pathlib.Path,
    cfg: Dict[str, Any],
) -> bool:
    """Rebuild ``03.5-knowledge-graph.json`` at a batch boundary.

    Advisory and opt-in: only runs when ``cfg.rebuild_graph_per_batch`` is
    truthy. A failed rebuild logs a warning and leaves the previous graph in
    place (stale graph is safer than a missing one). Returns True when a
    rebuild was not requested or succeeded.
    """
    if not cfg.get("rebuild_graph_per_batch", False):
        return True
    script = (
        pathlib.Path(__file__).parents[2]
        / "jade-core-knowledge-graph"
        / "scripts"
        / "build_graph.py"
    )
    if not script.exists():
        print(f"WARNING [GRAPH_REBUILD_FAILED] missing script: {script}", file=sys.stderr)
        return False
    cmd = [
        sys.executable,
        str(script),
        "--workspace",
        str(workspace),
        "--artifacts-dir",
        str(artifacts),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"WARNING [GRAPH_REBUILD_FAILED] {exc}", file=sys.stderr)
        return False
    if proc.returncode not in (0, 1):
        print(
            f"WARNING [GRAPH_REBUILD_FAILED] exit {proc.returncode}: "
            f"{proc.stderr.strip()[:500]}",
            file=sys.stderr,
        )
        return False
    return True


def compute_queue_graph_metadata(
    artifacts: pathlib.Path, rules: List[str]
) -> Dict[str, Any]:
    """Compute additive graph metadata for the approved rule queue.

    Only ever derived from the *approved* ``rules`` list — it never inserts
    or reorders them on disk. ``suggested_order`` is a BINDING second-order
    key for execution order (see ``compute_binding_rule_order``); the
    on-disk ``rules`` list itself is still never reordered or extended.
    """
    meta: Dict[str, Any] = {
        "status": "empty" if not rules else "computed",
        "source_artifact": "03.5-knowledge-graph.json",
        "suggested_order": list(rules),
        "direct_counts": {},
        "impact_counts": {},
        "cycles": [],
        "ordering_reasons": [],
        "diagnostics": [],
    }
    if not rules:
        return meta

    rule_files: Dict[str, List[str]] = {}
    flag_index_path = artifacts / "04-flag-index.json"
    if flag_index_path.exists():
        try:
            fi = read_json(flag_index_path)
        except (json.JSONDecodeError, OSError):
            fi = {}
        if not isinstance(fi, dict):
            fi = {}
        flags = fi.get("flags", []) if isinstance(fi.get("flags", []), list) else []
        try:
            for rule in rules:
                files = sorted(
                    {
                        f.get("file")
                        for f in flags
                        if isinstance(f, dict)
                        and f.get("rule_id") == rule
                        and f.get("file")
                    }
                )
                rule_files[rule] = files
                meta["direct_counts"][rule] = len(files)
                impacted: set = set()
                for f in flags:
                    if isinstance(f, dict) and f.get("rule_id") == rule:
                        gf = f.get("graph")
                        if isinstance(gf, dict) and isinstance(gf.get("impact_files"), list):
                            impacted.update(i for i in gf["impact_files"] if isinstance(i, str))
                meta["impact_counts"][rule] = len(impacted)
        except Exception as exc:
            meta["diagnostics"].append(
                {"kind": "flag_index_error", "message": str(exc)}
            )
            return meta

    kg = _load_knowledge_graph(artifacts)
    if kg is None:
        meta["diagnostics"].append({"kind": "graph_unavailable"})
        return meta

    try:
        result = kg.query_transform_order_with_diagnostics(rules, rule_files)
    except Exception as exc:
        meta["diagnostics"].append(
            {"kind": "transform_order_error", "message": str(exc)}
        )
        return meta

    meta["suggested_order"] = list(result.get("order", rules))
    for d in result.get("diagnostics", []):
        if d.get("kind") == "cycle":
            meta["cycles"].append(d.get("rules", []))
        meta["diagnostics"].append(d)
    meta["ordering_reasons"] = [
        {"rule": rule, "reason": "binding dependency order — dependent transforms first"}
        for rule in meta["suggested_order"]
    ]
    return meta


def attach_queue_graph_metadata(artifacts: pathlib.Path) -> Optional[Dict[str, Any]]:
    """Additively attach ``graph_metadata`` to 05-rule-queue.json.

    Returns the updated queue, or None if the queue is absent/unreadable.
    ``rules`` on disk is never reordered or extended here — only
    user-approved rules are ever present and remain exactly as produced by
    the agent. Binding execution order (which may differ from this on-disk
    list) is computed separately by ``effective_rule_order`` at iteration
    time in ``process_rule_batch``.
    """
    queue_path = artifacts / "05-rule-queue.json"
    if not queue_path.exists():
        return None
    try:
        queue = read_json(queue_path)
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(queue, dict):
        return None
    rules = queue.get("rules", [])
    if not isinstance(rules, list):
        return None
    queue["graph_metadata"] = compute_queue_graph_metadata(artifacts, rules)
    write_json(queue_path, queue)
    return queue


def load_rule_blast_classes(artifacts: pathlib.Path) -> Dict[str, str]:
    """Read ``blast_class`` per rule from the breaking-changes manifest.

    Only rules whose ``blast_class`` is exactly ``"body-local"`` or
    ``"signature"`` are included. Any failure (missing file, malformed
    JSON, missing field) degrades silently to an empty/partial dict —
    this is advisory input to ``compute_binding_rule_order``, never a gate.
    """
    manifest_path = artifacts / "01-breaking-changes-manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        data = read_json(manifest_path)
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    rules = data.get("rules")
    if not isinstance(rules, list):
        return {}
    result: Dict[str, str] = {}
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        rule_id = rule.get("id")
        blast_class = rule.get("blast_class")
        if isinstance(rule_id, str) and blast_class in BLAST_CLASS_RANK:
            result[rule_id] = blast_class
    return result


def compute_binding_rule_order(
    rules: List[str],
    blast_classes: Dict[str, str],
    suggested_order: List[str],
) -> List[str]:
    """Deterministically permute ``rules`` into binding execution order.

    Sort key (ascending): (1) blast_class rank — body-local before
    signature before unclassified; (2) index in ``suggested_order`` (a rule
    absent from it sorts after every rule present in it) — this is the
    binding second-order key; (3) index in ``rules`` — a final tie-break
    that also makes the function degenerate to the original queue order
    whenever no rule carries a classified blast_class and
    ``suggested_order`` mirrors ``rules``. Never mutates either input;
    returns a permutation (same length, same multiset of rule ids).
    """
    suggested_index = {rule: i for i, rule in enumerate(suggested_order)}
    original_index = {rule: i for i, rule in enumerate(rules)}

    def sort_key(rule_id: str) -> Tuple[int, int, int]:
        blast_rank = BLAST_CLASS_RANK.get(
            blast_classes.get(rule_id), UNCLASSIFIED_BLAST_RANK
        )
        suggested_rank = suggested_index.get(rule_id, len(suggested_order))
        original_rank = original_index.get(rule_id, len(rules))
        return (blast_rank, suggested_rank, original_rank)

    return sorted(rules, key=sort_key)


def effective_rule_order(artifacts: pathlib.Path, queue: Dict[str, Any]) -> List[str]:
    """Compose the binding rule-execution order for one RULE_BATCH_LOOP pass.

    Combines ``queue["rules"]`` (the on-disk approved list, never mutated),
    ``load_rule_blast_classes`` (from the manifest), and
    ``queue["graph_metadata"]["suggested_order"]`` (from the knowledge
    graph). See ``compute_binding_rule_order`` for the sort key.
    """
    rules = queue.get("rules", [])
    if not isinstance(rules, list):
        return []
    blast_classes = load_rule_blast_classes(artifacts)
    graph_metadata = queue.get("graph_metadata")
    suggested_order = (
        graph_metadata.get("suggested_order") if isinstance(graph_metadata, dict) else None
    )
    if not isinstance(suggested_order, list):
        suggested_order = []
    return compute_binding_rule_order(rules, blast_classes, suggested_order)


# ------------------------------------------------------------------
# Agent-mode rule gate
# ------------------------------------------------------------------
def agent_registry_entry(rule_id: str) -> Optional[Dict[str, Any]]:
    """Return this rule's recipe-registry.json entry iff mode == "agent".

    Reads the registry directly (no import of dispatcher.py or
    registry_modes.py — S3 never depends on S1/S2). Any read/parse failure,
    a non-dict registry, or a missing/non-agent entry all degrade to
    ``None`` — the caller then falls back to today's script-mode path.
    """
    try:
        registry = read_json(RECIPE_REGISTRY_PATH)
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(registry, dict):
        return None
    entry = registry.get(rule_id)
    if not isinstance(entry, dict):
        return None
    if entry.get("mode") != "agent":
        return None
    return entry


def validate_shard_ledger(
    artifacts: pathlib.Path, rule_id: str, plan: Dict[str, Any]
) -> Tuple[bool, str]:
    """Structurally validate ``06-shard-checkpoints-<rule_id>.json``.

    Checks only well-formedness: root dict, schema_version == 1, rule_id
    match, the ledger's shard-id keys exactly equal the plan's shard ids,
    every state is one of SHARD_LEDGER_STATES, and every ROLLED_BACK entry
    carries a non-empty rollback_reason. A ledger with a CHECKPOINTED
    shard is still structurally valid (True) — whether that represents
    "rollback pending" is a separate, caller-side check.
    """
    ledger_path = artifacts / f"06-shard-checkpoints-{rule_id}.json"
    try:
        ledger = read_json(ledger_path)
    except (json.JSONDecodeError, OSError) as exc:
        return False, f"cannot read shard ledger: {exc}"
    if not isinstance(ledger, dict):
        return False, "shard ledger must be a JSON object"
    if ledger.get("schema_version") != 1:
        return False, (
            f"shard ledger schema_version must be 1, got {ledger.get('schema_version')!r}"
        )
    if ledger.get("rule_id") != rule_id:
        return False, (
            f"shard ledger rule_id mismatch: expected {rule_id!r}, "
            f"got {ledger.get('rule_id')!r}"
        )
    shards_ledger = ledger.get("shards")
    if not isinstance(shards_ledger, dict):
        return False, "shard ledger 'shards' must be a JSON object"
    plan_shard_ids = {
        s.get("shard_id")
        for s in plan.get("shards", [])
        if isinstance(s, dict) and isinstance(s.get("shard_id"), str)
    }
    ledger_shard_ids = set(shards_ledger.keys())
    missing_from_ledger = plan_shard_ids - ledger_shard_ids
    if missing_from_ledger:
        return False, (
            f"shard ledger is missing plan shard_ids {sorted(missing_from_ledger)}"
        )
    # A ledger entry with no shard in the current plan is only legitimate when
    # it was ROLLED_BACK: that is the shape left behind when a rule is
    # re-planned after a rollback -- the classification changed, the planner
    # produced different shard ids, and the superseded shard's edits are gone
    # from the workspace. Demanding exact set equality made rollback a dead end,
    # since the recovery it exists for always renames the shards. Anything else
    # outside the plan (CHECKPOINTED or ACCEPTED) is still a hard failure: those
    # states mean edits are live in a shard the plan does not know about.
    stale = sorted(ledger_shard_ids - plan_shard_ids)
    not_rolled_back = [
        shard_id
        for shard_id in stale
        if not isinstance(shards_ledger.get(shard_id), dict)
        or shards_ledger[shard_id].get("state") != "ROLLED_BACK"
    ]
    if not_rolled_back:
        return False, (
            f"shard ledger keys {not_rolled_back} are absent from the plan "
            f"{sorted(plan_shard_ids)} and are not ROLLED_BACK"
        )
    for shard_id, info in shards_ledger.items():
        if not isinstance(info, dict):
            return False, f"shard ledger entry {shard_id!r} must be a JSON object"
        state_val = info.get("state")
        if state_val not in SHARD_LEDGER_STATES:
            return False, f"shard {shard_id!r} has invalid state {state_val!r}"
        if state_val == "ROLLED_BACK":
            reason = info.get("rollback_reason")
            if not isinstance(reason, str) or not reason.strip():
                return False, (
                    f"shard {shard_id!r} is ROLLED_BACK but rollback_reason is empty"
                )
    return True, ""


def _fix_result_records(artifacts: pathlib.Path, rule_id: str) -> List[Dict[str, Any]]:
    """Read ``06-fix-results-<rule_id>.json`` records, tolerating either the
    list-of-records shape written by dispatcher.py or a wrapped dict."""
    path = artifacts / f"06-fix-results-{rule_id}.json"
    if not path.exists():
        return []
    try:
        payload = read_json(path)
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        records = payload.get("results", [])
    else:
        records = []
    return [r for r in records if isinstance(r, dict)] if isinstance(records, list) else []


def _process_agent_rule(
    cfg: Dict,
    artifacts: pathlib.Path,
    state: Dict,
    rule_id: str,
    hist_path: pathlib.Path,
    state_path: pathlib.Path,
    rule_status_path: pathlib.Path,
    rstatus: Dict[str, Any],
) -> Optional[str]:
    """Gate one agent-mode rule (recipe-registry.json entry mode == "agent").

    Returns an outcome string when the caller (``process_rule_batch``)
    should return immediately, or ``None`` when this rule's shard ledger
    shows every shard ACCEPTED/ROLLED_BACK and control should fall through
    to today's unchanged build-verification path.
    """
    shard_plan_path = artifacts / f"05-rule-shards-{rule_id}.json"

    def _missing_plan() -> str:
        state["failure_reason"] = "MISSING_SHARD_PLAN"
        state["updated_at"] = iso_now()
        write_json(state_path, state)
        rstatus[rule_id] = {
            "status": "PENDING_AGENT",
            "reason": "shard plan missing or unreadable",
            "updated_at": iso_now(),
        }
        write_json(rule_status_path, {"run_id": cfg["run_id"], "rules": rstatus})
        write_progress_md(artifacts, state, cfg)
        return "ARTIFACT_MISSING"

    if not shard_plan_path.exists():
        return _missing_plan()
    try:
        plan = read_json(shard_plan_path)
    except (json.JSONDecodeError, OSError):
        return _missing_plan()
    if not isinstance(plan, dict) or not isinstance(plan.get("shards"), list):
        return _missing_plan()

    agent_tasks_path = artifacts / f"05-agent-tasks-{rule_id}.json"
    ledger_path = artifacts / f"06-shard-checkpoints-{rule_id}.json"
    if not agent_tasks_path.exists() or not ledger_path.exists():
        _pause_for_agent("RULE_BATCH_LOOP", artifacts, state, cfg, rule_id, plan)
        return "AWAIT_AGENT"

    ledger_ok, ledger_reason = validate_shard_ledger(artifacts, rule_id, plan)
    if not ledger_ok:
        fail(artifacts, state, "SHARD_LEDGER_INVALID", ledger_reason)
        return "ARTIFACT_TAMPERED"

    ledger = read_json(ledger_path)
    shard_states: Dict[str, Any] = {
        sid: info.get("state")
        for sid, info in ledger.get("shards", {}).items()
        if isinstance(info, dict)
    }
    if any(s == "CHECKPOINTED" for s in shard_states.values()):
        _pause_for_agent("RULE_BATCH_LOOP", artifacts, state, cfg, rule_id, plan)
        return "SHARD_ROLLBACK_PENDING"

    accepted_shard_ids = {sid for sid, s in shard_states.items() if s == "ACCEPTED"}
    if accepted_shard_ids:
        # NEEDS_REVIEW is not a failure. The recipe contract defines it as "the
        # edit was applied, but a human should verify it before the rule batch
        # is trusted" -- an accepted shard carrying that status is the intended
        # outcome, not a tampered artifact. Failing the run here forced the
        # opposite behaviour: an agent wanting a green run had to record FIXED
        # for work it was not sure about, which is the fabricated status the
        # pipeline exists to prevent. Surface it in the review ledger instead.
        pending_review = [
            record
            for record in _fix_result_records(artifacts, rule_id)
            if record.get("shard_id") in accepted_shard_ids
            and record.get("status") == "NEEDS_REVIEW"
        ]
        if pending_review:
            _write_review_ledger(artifacts, rule_id, pending_review)

    # Every shard is ACCEPTED or ROLLED_BACK (SHARD_LEDGER_STATES has no
    # other member once CHECKPOINTED is ruled out above) — fall through to
    # the unchanged build-verification path.
    return None


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

    if cfg.get("rebuild_graph_per_batch", False):
        workspace = pathlib.Path(str(cfg.get("workspace_path", "workspace")))
        if rebuild_knowledge_graph(workspace, artifacts, cfg):
            state["graph"] = record_graph_freshness(artifacts)

    attach_queue_graph_metadata(artifacts)
    queue = read_json(queue_path)
    if not isinstance(queue, dict):
        return "ARTIFACT_MISSING"
    rules: List[str] = queue.get("rules", [])
    if not isinstance(rules, list) or not rules:
        return "NO_MORE_RULES"

    rstatus = {}
    if rule_status_path.exists():
        try:
            rstatus = read_json(rule_status_path).get("rules", {})
        except (json.JSONDecodeError, OSError):
            pass

    for rule_id in effective_rule_order(artifacts, queue):
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

        agent_entry = agent_registry_entry(rule_id)
        if agent_entry is not None:
            agent_outcome = _process_agent_rule(
                cfg,
                artifacts,
                state,
                rule_id,
                hist_path,
                state_path,
                rule_status_path,
                rstatus,
            )
            if agent_outcome is not None:
                return agent_outcome
            # agent_outcome is None: every shard for this rule is ACCEPTED or
            # ROLLED_BACK in its checkpoint ledger — fall through to the same
            # build-verification path script-mode rules use below (agent-mode
            # rules have no 05-rule-batch-<rule_id>.json, so that legacy check
            # is skipped for them; nothing below it changes).
        else:
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
            state["awaiting_rule_id"] = None
            state["awaiting_shards"] = None
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
        elif current in REQUIRED_ARTIFACTS and current != "RUNTIME_VERIFY":
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
                            {
                                "run_id": state.get("run_id", ""),
                                "rules": [],
                                "graph_metadata": compute_queue_graph_metadata(
                                    artifacts, []
                                ),
                            },
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
