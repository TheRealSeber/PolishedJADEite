# Graph-Based State Machine & DX Upgrades — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the orchestrator from a linear for-loop to a conditional transition table with connected retry routing, live PROGRESS.md, and an escalation ledger (ACTION_REQUIRED.md). No new skills. No recipe generation.

**Architecture:** The orchestrator becomes a transition table — each state + outcome maps to a next state. The retry router is invoked by the orchestrator on verify failures. Escalated rules are skipped and continue to next rules. PROGRESS.md is written on every state transition. No skills renamed. No Skill 12.

**Tech Stack:** Python 3, JSON artifacts, Git.

---

## File Structure

### Files to modify

| File | Action | Lines |
|------|--------|-------|
| `.claude/skills/jade-core-orchestrator/scripts/orchestrator.py` | Major rewrite — transition table, PROGRESS.md, retry integration | ~350 |
| `.claude/skills/jade-core-retry-router/scripts/retry_router.py` | Add `ACTION_REQUIRED.md` writer, `ESCALATED_TO_LLM` termination | ~15 lines added |
| `.claude/skills/jade-core-orchestrator/SKILL.md` | Document transition model, PROGRESS.md output | ~20 lines changed |
| `.claude/skills/jade-core-retry-router/SKILL.md` | Document ACTION_REQUIRED.md output | ~10 lines changed |
| `AGENTS.md` | Update constraint #3 and add PROGRESS.md + ACTION_REQUIRED.md to artifacts | ~5 lines changed |
| `docs/architecture.md` | Update Phase 7 diagram to include retry → escalate → continue | ~15 lines changed |

### No new files created
- Reporting is baked into orchestrator (PROGRESS.md) and retry router (ACTION_REQUIRED.md).

---

## Task 1: Rewrite orchestrator.py as a proper state machine

**Files:**
- Modify: `.claude/skills/jade-core-orchestrator/scripts/orchestrator.py`

### Step 1: Define transitions table

```python
TRANSITIONS = {
    "INIT": {
        "OK": "WORKSPACE_READY",
    },
    "WORKSPACE_READY": {
        "OK": "MANIFEST_READY",
        "BASELINE_MISSING": "FAILED",
        "COPY_FAILED": "FAILED",
    },
    "MANIFEST_READY": {
        "OK": "TOOLING_SCOUT_READY",
        "ARTIFACT_MISSING": "FAILED",
    },
    "TOOLING_SCOUT_READY": {
        "OK": "BUILD_GATE_READY",
        "ARTIFACT_MISSING": "FAILED",
    },
    "BUILD_GATE_READY": {
        "OK": "SCAN_READY",
        "ARTIFACT_MISSING": "FAILED",
    },
    "SCAN_READY": {
        "OK": "RULE_BATCH_LOOP",
        "ARTIFACT_MISSING": "FAILED",
    },
    "RULE_BATCH_LOOP": {
        "NEXT_RULE": "RULE_BATCH_LOOP",   # loop: pick next rule from queue
        "NO_MORE_RULES": "VERIFIED",
        "VERIFY_FAIL": "RULE_RETRY",
    },
    "RULE_RETRY": {
        "RETRY": "RULE_BATCH_LOOP",         # re-apply the same rule and verify again
        "ESCALATE": "RULE_ESCALATE",
    },
    "RULE_ESCALATE": {
        "OK": "RULE_BATCH_LOOP",            # skip this rule, continue to next
    },
    "VERIFIED": {
        "OK": "DONE",
    },
    "FAILED": {},   # terminal
    "DONE": {},     # terminal
    "AWAITING_SOURCE_INPUT": {},  # terminal
}
```

### Step 2: Replace main() with state machine loop

```python
def main() -> int:
    # ... config parsing (unchanged) ...
    # ... INIT + WORKSPACE_READY (unchanged) ...

    state = load_or_init_state(artifacts, cfg)
    
    while state["state"] not in TERMINAL_STATES:
        current = state["state"]
        outcome = process_state(current, cfg, artifacts, state)
        
        next_state = TRANSITIONS.get(current, {}).get(outcome)
        if next_state is None:
            return fail(artifacts, state, "TRANSITION_ERROR",
                        f"No transition from {current} for outcome {outcome}")
        
        state["state"] = next_state
        state["updated_at"] = iso_now()
        write_json(state_path, state)
        write_progress_md(artifacts, state, cfg)
        append_jsonl(hist_path, {...})

    return 0 if state["state"] == "DONE" else 2
```

### Step 3: Implement process_state() — the core state handler

```python
def process_state(current: str, cfg: Dict, artifacts: pathlib.Path, state: Dict) -> str:
    """Process the current state and return an outcome key."""
    
    if current == "INIT":
        # Already done — config validated, state written, workspace copied
        return "OK"
    
    if current == "WORKSPACE_READY":
        # Already done — workspace isolated
        return "OK"
    
    if current in ("MANIFEST_READY", "TOOLING_SCOUT_READY", "BUILD_GATE_READY", "SCAN_READY"):
        # Check for required artifacts, return OK or ARTIFACT_MISSING
        required = REQUIRED_ARTIFACTS.get(current, [])
        for af in required:
            if not (artifacts / af).exists():
                return "ARTIFACT_MISSING"
        return "OK"
    
    if current == "RULE_BATCH_LOOP":
        return process_rule_batch(cfg, artifacts, state)
    
    if current == "RULE_RETRY":
        return process_retry(cfg, artifacts, state)
    
    if current == "RULE_ESCALATE":
        return process_escalate(artifacts, state)
    
    if current == "VERIFIED":
        return "OK"
    
    return "OK"
```

### Step 4: Implement process_rule_batch() — the core loop

Read `05-rule-queue.json`. Load `rule-status.json` (or init). Find the first rule NOT yet DONE or ESCALATED. Process it: log PREPARE, DISPATCH, VERIFY. On verify failure → return "VERIFY_FAIL". On rule DONE → advance to next rule. When no remaining rules → return "NO_MORE_RULES".

### Step 5: Implement process_retry() — invoke retry_router.py

```python
def process_retry(cfg: Dict, artifacts: pathlib.Path, state: Dict) -> str:
    import subprocess
    result = subprocess.run(
        [sys.executable,
         ".claude/skills/jade-core-retry-router/scripts/retry_router.py",
         "--artifacts", str(artifacts),
         "--max-retries", "3"],
        capture_output=True, text=True,
    )
    
    # Read the retry router's output
    final_status = read_json(artifacts / "08-final-status.json")
    
    current_rule = state.get("current_rule_id")
    rules_status = final_status.get("rules", {})
    rule_result = rules_status.get(current_rule, {})
    
    if rule_result.get("status") in ("ESCALATED", "ESCALATED_TO_LLM"):
        return "ESCALATE"
    if rule_result.get("status") == "REQUEUED":
        return "RETRY"
    
    return "RETRY"  # default: try again
```

### Step 6: Implement PROGRESS.md writer

```python
def write_progress_md(artifacts: pathlib.Path, state: Dict, cfg: Dict) -> None:
    """Write human-readable PROGRESS.md on every state transition."""
    path = artifacts / "PROGRESS.md"
    
    lines = [
        f"# {cfg['run_id']} — Migration Progress",
        "",
        f"**Source:** {cfg['source_version']} → **Target:** {cfg['target_version']}",
        f"**Updated:** {state['updated_at']}",
        "",
        "| Phase | Status | Details |",
        "|-------|--------|---------|",
    ]
    
    # Read phase history to build the table
    hist_path = artifacts / "phase-history.log.jsonl"
    if hist_path.exists():
        for raw in hist_path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            entry = json.loads(raw)
            phase = entry.get("phase", "?")
            status = entry.get("status", "?")
            msg = entry.get("message", "")
            emoji = "✅" if status == "OK" else ("🔴" if status == "ERROR" else "🟡")
            lines.append(f"| {emoji} {phase} | {status} | {msg} |")
    
    # Append current state
    lines.append(f"| ▶ {state['state']} | IN PROGRESS | |")
    
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
```

### Step 7: Verify orchestrator parses

```bash
python -c "import py_compile; py_compile.compile('.claude/skills/jade-core-orchestrator/scripts/orchestrator.py', doraise=True); print('Syntax OK')"
```

### Step 8: Run existing tests

```bash
python -m pytest tests/ -v
```
Expected: 9 passed, 2 skipped.

### Step 9: Commit

```bash
git add .claude/skills/jade-core-orchestrator/scripts/orchestrator.py
git commit -m "refactor(orchestrator): implement graph-based state machine with PROGRESS.md"
```

---

## Task 2: Add ACTION_REQUIRED.md to retry router

**Files:**
- Modify: `.claude/skills/jade-core-retry-router/scripts/retry_router.py`

### Step 1: Add write_action_required() function

```python
def write_action_required(artifacts: pathlib.Path, escalated: List[EscalationEntry],
                          fix_results: List[FixResult]) -> None:
    """Write a human-readable escalation ledger."""
    path = artifacts / "ACTION_REQUIRED.md"
    
    lines = [
        "# Action Required — Escalated Items",
        "",
        f"**Generated:** {iso_now()}",
        f"**Escalated rules:** {len(escalated)}",
        "",
        "The following items could not be fixed automatically after the maximum",
        "retry budget. Manual intervention is required.",
        "",
        "---",
        "",
    ]
    
    for entry in escalated:
        lines.append(f"## Rule: `{entry.rule_id}`")
        lines.append(f"- **Attempts:** {entry.total_attempts}")
        lines.append(f"- **Final failure:** {entry.final_failure}")
        lines.append(f"- **Escalated at:** {entry.escalated_at}")
        
        # Find matching fix results for per-file detail
        for fr in fix_results:
            if fr.rule_id == entry.rule_id:
                lines.append(f"\n### Files")
                for fname in sorted(set(fr.files_modified)):
                    lines.append(f"- `{fname}`")
                if fr.error:
                    lines.append(f"\n### Error")
                    lines.append(f"```\n{fr.error}\n```")
        lines.append("")
        lines.append("---")
        lines.append("")
    
    lines.append("## Suggested actions")
    lines.append("1. Review the error messages above for each escalated rule.")
    lines.append("2. Manually fix the affected files, or adjust the recipe's transform logic.")
    lines.append("3. Clear the entry from `08-escalations.json`.")
    lines.append("4. Re-run the orchestrator to re-attempt the rule.")
    lines.append("")
    
    path.write_text("\n".join(lines), encoding="utf-8")
```

### Step 2: Call write_action_required() in main() when escalations exist

```python
    # After writing 08-escalations.json:
    if escalated:
        write_action_required(artifacts, escalated, fix_results)
        print(f"ACTION_REQUIRED: {escalated_count} rule(s) escalated — see ACTION_REQUIRED.md")
```

### Step 3: Verify retry router parses

```bash
python -c "import py_compile; py_compile.compile('.claude/skills/jade-core-retry-router/scripts/retry_router.py', doraise=True); print('Syntax OK')"
```

### Step 4: Commit

```bash
git add .claude/skills/jade-core-retry-router/scripts/retry_router.py
git commit -m "feat(retry-router): add ACTION_REQUIRED.md escalation ledger"
```

---

## Task 3: Update documentation

**Files:**
- Modify: `.claude/skills/jade-core-orchestrator/SKILL.md`
- Modify: `.claude/skills/jade-core-retry-router/SKILL.md`
- Modify: `AGENTS.md`
- Modify: `docs/architecture.md`

### Step 1: Update orchestrator SKILL.md

```markdown
## State machine

The orchestrator is a directed graph. Each state + outcome maps to a next state:

| State | Outcome | Next |
|-------|---------|------|
| RULE_BATCH_LOOP | NEXT_RULE | RULE_BATCH_LOOP (pick next rule) |
| RULE_BATCH_LOOP | NO_MORE_RULES | VERIFIED |
| RULE_BATCH_LOOP | VERIFY_FAIL | RULE_RETRY |
| RULE_RETRY | RETRY | RULE_BATCH_LOOP (re-apply same rule) |
| RULE_RETRY | ESCALATE | RULE_ESCALATE (skip rule, continue) |
| RULE_ESCALATE | OK | RULE_BATCH_LOOP (advance to next rule) |

Terminal states: DONE, FAILED, AWAITING_SOURCE_INPUT

## Produced artifacts (new)

- `artifacts/PROGRESS.md` — human-readable progress table, updated on every transition
```

### Step 2: Update retry router SKILL.md

```markdown
## Produced artifacts (new)

- `artifacts/ACTION_REQUIRED.md` — human-readable escalation ledger. Written when one
  or more rules are escalated after retry exhaustion. Contains per-rule failure
  reasons, affected files, and suggested remediation steps.
```

### Step 3: Update AGENTS.md

Add to hard constraint #3: "Orchestrator operates as a transition-table state machine — verification failures route through retry router; retry exhaustion → ESCALATED_TO_LLM → skip rule → continue."

Add `PROGRESS.md` and `ACTION_REQUIRED.md` to the artifact prefixes table (or add a note line).

### Step 4: Update architecture.md

In the Phase 7 description, add the retry → escalate → continue flow after the verification step. Show the conditional routing.

### Step 5: Run tests

```bash
python -m pytest tests/ -v
```
Expected: 9 passed, 2 skipped.

### Step 6: Commit

```bash
git add .claude/skills/jade-core-orchestrator/SKILL.md .claude/skills/jade-core-retry-router/SKILL.md AGENTS.md docs/architecture.md
git commit -m "docs: update docs for graph routing, PROGRESS.md, and ACTION_REQUIRED.md"
```

---

## Execution order

Tasks must run sequentially: 1 → 2 → 3. Each task ends with a commit. 3 commits total.

## DoD

- [ ] `orchestrator.py` uses a `TRANSITIONS` dict instead of `for phase in PHASES`
- [ ] `process_state()` dispatches per phase; `process_rule_batch()` iterates rules
- [ ] `process_retry()` invokes `retry_router.py` as subprocess and reads its output
- [ ] `process_escalate()` skips the escalated rule and advances to the next
- [ ] `write_progress_md()` writes `PROGRESS.md` on every state transition
- [ ] `retry_router.py` writes `ACTION_REQUIRED.md` when rules are escalated
- [ ] All documentation updated
- [ ] `python -m pytest tests/ -v` → 9 passed, 2 skipped
