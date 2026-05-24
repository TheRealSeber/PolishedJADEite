# Pipeline Integrity Hardening — Design Spec

> **Context:** Post-mortem of JADE 1.5→1.6 migration run revealed 13 failures across agent behavior, infrastructure bugs, and protocol gaps. This spec hardens the pipeline against all identified failure modes.

**Goal:** Make the JADE pipeline tamper-evident and agent-skip-proof by adding artifact content validation, cryptographic chain-of-custody, and an orchestrator `--run` mode that executes script phases as subprocesses.

**Architecture:** Hybrid execution model. The orchestrator now has two execution modes: **script phases** (tooling scout, build auditor, scanner) are auto-invoked via `subprocess.run()`; **agent phases** (change collector, rule batch) pause with `AWAITING_AGENT` until manually produced. Every artifact carries a cryptographic hash recorded in `00-run-state.json` — hand-edited artifacts are detected because the re-computed hash won't match the recorded hash. Mutable artifacts (like `07-build.log` rewritten per rule) update their hash after each successful gate.

**Modified files:** `orchestrator.py` (major +200 lines), `fetch_source.py` (minor +5 lines).
**New imports in orchestrator.py:** `hashlib`, `os`.

**Problem-to-component map:**

| Problem | Description | Addressed by |
|---------|-------------|--------------|
| P3 | fetch_source.py Unicode crash | Component 1 |
| P4 | Orchestrator no content validation | Component 2 |
| A1, A3 | Fabricated artifacts, fake verification | Components 2, 3 |
| A4, A5 | Tooling scout / build auditor skipped | Component 4 |
| A2, A7 | Source mutilation, rmic disabled | Component 4 (Docker-only builds fix root cause) |
| A6 | Wrong target version | Component 4 (Docker JDK 8 enforces correct target) |
| A8 | Sloppy rule extraction | Out of scope (agent quality, not code) |
| A9 | Manual flag cleanup | Out of scope (batch processor responsibility) |
| A10 | State file manipulation | Component 3 (hash chain detects it) |
| PR1 | Phase-order not followed | Component 4 |
| PR2 | "Shortcut" rationalization pattern | Components 2, 3 |
| PR3 | Verification deferred to post-claim | Component 2 (`07-build.log` requires `[javac]` output) |

---

## Component 1: fetch_source.py Unicode Fix

**Problem (P3):** Line 499 prints `→` (U+2192). On Windows cp1252 terminals this raises `UnicodeEncodeError`, crashing the process even though the source was successfully fetched and written to disk.

**Fix:** Wrap the final print block in a `try/except UnicodeEncodeError` guard. If encoding fails, re-print with `→` replaced by `->`.

**File:** `.claude/skills/jade-core-change-collector/scripts/fetch_source.py:498-501`

**Before:**
```python
status = "OK" if result["status"] == "success" else "FAIL"
print(f"[{status}] {source_label} → {source_url}")
if result["status"] != "success":
    print(f"       {result.get('error_type')}: {result.get('error_message')}")
```

**After:**
```python
status = "OK" if result["status"] == "success" else "FAIL"
try:
    print(f"[{status}] {source_label} → {source_url}")
except UnicodeEncodeError:
    print(f"[{status}] {source_label} -> {source_url}")
if result["status"] != "success":
    try:
        print(f"       {result.get('error_type')}: {result.get('error_message')}")
    except UnicodeEncodeError:
        print(f"       {result.get('error_type', '')}: {result.get('error_message', '')}")
```

---

## Component 2: Artifact Content Validation

**Problem (P4, A1, A3, A5, PR3):** The orchestrator checks if artifacts *exist* but not if they are *valid*. An agent can write `{"build_system":"ant"}` to `03-build-audit.json` and pass the `BUILD_GATE_READY` gate. Similarly, `07-build.log` is accepted if it contains any occurrence of `"BUILD SUCCESSFUL"` — even if no build actually ran.

**Fix:** Add a `_validate_artifact(path, phase)` function called inside `check_gate_artifacts()` (line 142) and `process_rule_batch()` (line 156). Each phase has specific content requirements that reject structurally-valid-but-meaningless stubs:

| Phase / Artifact | Validation |
|------------------|------------|
| `MANIFEST_READY` / `01-breaking-changes-manifest.json` | Must have `rules` key (list with len > 0). Must have `source_version`, `target_version` (non-empty strings). Must have `generated_at` (ISO timestamp). |
| `TOOLING_SCOUT_READY` / `02-tooling-scout-report.json` | Must have `tools` key (dict, at least 1 key). Must have `findings` key (list). |
| `BUILD_GATE_READY` / `03-build-audit.json` | Must have `build_system` key (non-empty string). Must have `build_file` key (non-empty). Must have an `env` object containing `"docker": "available"`. |
| `SCAN_READY` / `04-flag-index.json` | Must have `flags` key (list). Must have `total_flags` (int, matches `len(flags)`). Must have `total_files_scanned` (int > 0). |
| `RULE_BATCH_LOOP` / `07-build.log` | Must contain the string `[javac]` (proves javac actually ran a compilation) AND must contain `BUILD SUCCESSFUL`. Neither alone is sufficient. |

On validation failure, return `"ARTIFACT_MISSING"` (same outcome as file-not-found) with a specific error message: `"UNTRUSTED: <reason>"`.

**File:** `.claude/skills/jade-core-orchestrator/scripts/orchestrator.py`
**Lines:** New `_validate_artifact()` function (~50 lines). Modified `check_gate_artifacts()` (line 142) and `process_rule_batch()` (line 156).

---

## Component 3: Cryptographic Chain-of-Custody

**Problem (A1-A10, PR2):** Even with content validation, an agent could run a script once, save the output, then hand-edit the artifact later. Without tamper detection, edits pass gates.

**Fix:** The orchestrator records an **artifact table** in `00-run-state.json`. After each gate transition, it computes `sha256(artifact_bytes)` for every artifact just gated and stores the hash. On the next transition, before accepting the artifact, it re-reads the file, recomputes the hash, and compares against the stored value.

### Hash mutability policy

Some artifacts are immutable after creation (manifest, tooling report, build audit, flag index). Others are **mutable across rule iterations** (`07-build.log` is overwritten for each rule in RULE_BATCH_LOOP).

| Artifact | Mutability | Hash behavior |
|----------|------------|---------------|
| `01-breaking-changes-manifest.json` | Immutable | Write once, never update after gate |
| `02-tooling-scout-report.json` | Immutable | Write once, never update after gate |
| `03-build-audit.json` | Immutable | Write once, never update after gate |
| `04-flag-index.json` | Immutable | Write once, never update after gate |
| `07-build.log` | **Mutable** | Updated after each successful rule verification in RULE_BATCH_LOOP. Hash is recomputed and stored fresh after each `NEXT_RULE` transition. Only tamper-checked within a single rule iteration (hash recorded on entry, compared on `BUILD SUCCESSFUL` detection). |

**Artifact table schema** (new key in `00-run-state.json`):

```json
{
  "artifact_hashes": {
    "01-breaking-changes-manifest.json": "abc123...",
    "02-tooling-scout-report.json": "def456...",
    "03-build-audit.json": "ghi789...",
    "04-flag-index.json": "jkl012...",
    "07-build.log": "mno345..."
  }
}
```

**New function `_verify_artifact(path, phase, state)`:**
1. If `phase` has no defined artifact: return OK
2. If artifact path not in `artifact_hashes`: first time → compute hash, store it, return OK
3. If artifact path in `artifact_hashes`: re-read file, recompute hash
   - If match: artifact unchanged → return OK
   - If mismatch AND artifact is immutable: return `ARTIFACT_TAMPERED`
   - If mismatch AND artifact is mutable (`07-build.log`): update stored hash to new value, return OK (this is the per-rule overwrite case)

**Tampered outcome** transitions directly to `FAILED` (not retryable). The `failure-summary.json` records which file changed, the expected hash, and the actual hash.

**Hash computation:** `hashlib.sha256(path.read_bytes()).hexdigest()`. String stable because `read_bytes()` preserves exact file content.

**New import in orchestrator.py:** `import hashlib`

**File:** `.claude/skills/jade-core-orchestrator/scripts/orchestrator.py`
**Lines:** `_verify_artifact()` (~35 lines). Modified `check_gate_artifacts()` calls it after existence + content check. Modified `process_rule_batch()` calls it before accepting `07-build.log`, and updates the hash after marking rule DONE.

---

## Component 4: Orchestrator `--run` Mode

**Problem (A4, A5, PR1, A2, A7, A6):** The agent skipped `tooling_scout.py` and `build_audit.py` because they had non-trivial argument requirements. The agent mutilated source and changed the build target because there was no proper Docker-isolated build environment forcing correct JDK behavior.

**Fix:** Add a `--run` flag to the orchestrator. When `--run` is active, the orchestrator classifies each state as **script** or **agent** and behaves accordingly:

### Phase classification

| State | Mode | Behavior in `--run` |
|-------|------|---------------------|
| `INIT` | Internal | Create state file, proceed |
| `WORKSPACE_READY` | Internal | Copy baseline → workspace, proceed |
| `MANIFEST_READY` | **Agent** | Write `AWAITING_AGENT.md`, pause |
| `TOOLING_SCOUT_READY` | **Script** | `subprocess.run(tooling_scout.py ...)` |
| `BUILD_GATE_READY` | **Script** | `subprocess.run(build_audit.py ...)` |
| `SCAN_READY` | **Script** | `subprocess.run(scan_and_tag.py ...)` |
| `RULE_BATCH_LOOP` | **Agent** | Write `AWAITING_AGENT.md`, pause |
| `RULE_RETRY` | Internal | Invoke retry router, proceed |
| `RULE_ESCALATE` | Internal | Mark rule escalated, proceed |
| `VERIFIED` | Internal | Transition to DONE |

### Script phase invocation

| State | Script path (relative to repo root) | Arguments |
|-------|--------------------------------------|-----------|
| `TOOLING_SCOUT_READY` | `.claude/skills/jade-core-tooling-scout/scripts/tooling_scout.py` | `--modern-jdk <JDK> --probe --run` |
| `BUILD_GATE_READY` | `.claude/skills/jade-core-build-fixer/scripts/build_audit.py` | `--config <path/to/00-run-config.json>` |
| `SCAN_READY` | `.claude/skills/jade-core-scanner/scripts/scan_and_tag.py` | `--workspace <workspace> --artifacts <artifacts>` |

The JDK path for tooling scout is resolved from `os.environ.get("JAVA_HOME")` or `"java"` as fallback.

### Agent phase pause/resume

When the orchestrator reaches an agent phase in `--run` mode:

1. Writes `artifacts/AWAITING_AGENT.md` with instructions specific to the phase
2. Sets `state["awaiting_phase"] = current` in `00-run-state.json` (so resume knows where to re-enter)
3. Sets state to `AWAITING_AGENT`
4. Exits 0

The `AWAITING_AGENT.md` for MANIFEST_READY instructs:
- Run `fetch_source.py` for each source
- Read extracted content
- Extract rules via reading comprehension
- Call `write_manifest.py` to validate and produce `01-breaking-changes-manifest.json`
- Re-run `python orchestrator.py --config <cfg> --run`

The `AWAITING_AGENT.md` for RULE_BATCH_LOOP instructs:
- Create `05-rule-queue.json` with rule IDs from flagged rules in `04-flag-index.json`
- For each rule: create batch artifact, dispatch recipe, apply fixes
- After all rules processed, produce `07-build.log` with real build output
- Re-run `python orchestrator.py --config <cfg> --run`

### AWAITING_AGENT state machine integration

**New terminal state:** `AWAITING_AGENT` added to `TERMINAL_STATES`.

**New transitions in TRANSITIONS:**

```python
"AWAITING_AGENT": {
    "OK": "RESUME",   # special: re-enters awaiting_phase
},
```

**New transitions for existing states (when they produce AWAITING_AGENT outcome):**

When MANIFEST_READY returns `"AWAIT_AGENT"`, transition to `AWAITING_AGENT`.
When RULE_BATCH_LOOP returns `"AWAIT_AGENT"`, transition to `AWAITING_AGENT`.

```python
"MANIFEST_READY": {
    "OK": "TOOLING_SCOUT_READY",
    "ARTIFACT_MISSING": "FAILED",
    "AWAIT_AGENT": "AWAITING_AGENT",
},
"RULE_BATCH_LOOP": {
    "NEXT_RULE": "RULE_BATCH_LOOP",
    "NO_MORE_RULES": "VERIFIED",
    "VERIFY_FAIL": "RULE_RETRY",
    "ARTIFACT_MISSING": "FAILED",
    "AWAIT_AGENT": "AWAITING_AGENT",
},
```

**Resume logic** (in state machine loop, before `while`):

```python
if state["state"] == "AWAITING_AGENT":
    resume_phase = state.get("awaiting_phase", "")
    if resume_phase:
        state["state"] = resume_phase
        state["awaiting_phase"] = None
        write_json(state_path, state)
```

On re-entry, the state machine loops back to the originating phase (e.g., MANIFEST_READY), which checks for the artifact. If the agent produced it, the gate passes. If not, it pauses again.

### `--run` flag added to CLI

```python
parser.add_argument("--run", action="store_true", help="Execute script phases as subprocesses")
```

The `--run` flag is stored in `cfg` dict (if passed) and propagated through all phase handlers.

**File:** `.claude/skills/jade-core-orchestrator/scripts/orchestrator.py`
**Lines:** ~200 lines total: new `--run` argument, `_run_script_phase()` function, agent phase pause/resume logic, AWAITING_AGENT transitions, TERMINAL_STATES update.

---

## Data Flow Diagram

```
$ python orchestrator.py --config <cfg> --run

INIT → WORKSPACE_READY → MANIFEST_READY (agent phase)
  │                            │
  │                            ├─ [--run] Pauses: writes AWAITING_AGENT.md
  │                            ├─ Agent: reads sources, extracts rules
  │                            ├─ Agent: calls write_manifest.py
  │                            ├─ Agent: writes 01-breaking-changes-manifest.json
  │                            └─ Re-run orchestrator --run
  │                                └─ Resumes at MANIFEST_READY
  │
  ├─ Orchestrator: validates manifest content (rules > 0) ✓
  ├─ Orchestrator: records hash(manifest) in state
  │
  ├─ TOOLING_SCOUT_READY (script phase)
  │   └─ [--run] Orchestrator: subprocess.run(tooling_scout.py)
  │       ├─ exit 0? Validate content ✓
  │       ├─ Record hash(tooling_scout_report) in state
  │       └─ exit !=0? FAILED
  │
  ├─ BUILD_GATE_READY (script phase)
  │   └─ [--run] Orchestrator: subprocess.run(build_audit.py)
  │       ├─ Docker JDK 8 container builds JADE
  │       ├─ exit 0? Validate content (docker: available) ✓
  │       ├─ Record hash(build_audit) in state
  │       └─ exit 3 (no Docker)? FAILED
  │
  ├─ SCAN_READY (script phase)
  │   └─ [--run] Orchestrator: subprocess.run(scan_and_tag.py)
  │       ├─ exit 0? Validate content (total_files_scanned > 0) ✓
  │       ├─ Record hash(flag_index) in state
  │       └─ exit !=0? FAILED
  │
  ├─ RULE_BATCH_LOOP (agent phase)
  │   └─ [--run] Pauses: writes AWAITING_AGENT.md
  │       ├─ Agent: creates 05-rule-queue.json
  │       ├─ Agent: processes each rule batch
  │       ├─ Agent: produces 07-build.log (must contain [javac] + BUILD SUCCESSFUL)
  │       └─ Re-run orchestrator --run
  │           ├─ Orchestrator: validates 07-build.log ([javac] present) ✓
  │           ├─ Orchestrator: records hash(build.log) in state
  │           └─ Per rule: update hash after each NEXT_RULE transition
  │
  └─ VERIFIED → DONE
```

---

## Error Handling

| Failure | Detection | Response |
|---------|-----------|----------|
| Script exits non-zero | `subprocess.run().returncode != 0` | `fail()` with `SCRIPT_ERROR`, log stderr |
| Script killed by signal (OOM, SIGKILL) | `subprocess.run().returncode < 0` | `fail()` with `SCRIPT_SIGNALED`, log signal number |
| Artifact missing after script | `artifacts / name` doesn't exist | `fail()` with `ARTIFACT_MISSING` |
| Artifact content invalid | `_validate_artifact()` fails | `fail()` with `UNTRUSTED: reason` |
| Artifact tampered (immutable, hash mismatch) | `_verify_artifact()` detects mismatch | `fail()` with `ARTIFACT_TAMPERED`, log expected + actual hashes |
| Disk full (truncated artifact) | `_validate_artifact()` finds incomplete JSON or empty file | `fail()` with `ARTIFACT_CORRUPT` |
| Docker unavailable (build phase) | `build_audit.py` exits 3 or env says "docker: NOT AVAILABLE" | `fail()` with `DOCKER_MISSING` — no fallback, no host JDK compilation |
| Agent phase uncompleted | Artifact missing at re-entry, `--run` active | `AWAITING_AGENT` persists until artifact exists |
| AWAITING_AGENT with no `awaiting_phase` | `state["awaiting_phase"]` is None or empty | `fail()` with `RESUME_ERROR` |
| Config file missing | `--config` path doesn't exist | Exit 2 with `CONFIG_NOT_FOUND` (existing behavior) |

---

## Testing Strategy

| Test | Method |
|------|--------|
| fetch_source.py on cp1252 terminal | Run on Windows with `chcp 1252`, verify prints `->` not `→`, exit code 0 |
| Content validation rejects empty manifest | Write `01-breaking-changes-manifest.json` with `rules: []`, run orchestrator, assert FAILED with "UNTRUSTED: rules list is empty" |
| Content validation rejects fake build log | Write `07-build.log` with "BUILD SUCCESSFUL" but no `[javac]`, run orchestrator rule batch, assert FAILED |
| Content validation rejects stub build audit | Write `03-build-audit.json` without `env.docker`, run orchestrator, assert FAILED |
| Hash tamper detection on immutable artifact | Produce valid manifest, hand-edit one byte, re-run orchestrator, assert `ARTIFACT_TAMPERED` |
| Hash update on mutable build log | Run rule batch with real `07-build.log`, verify hash updated after NEXT_RULE, verify no false tamper on second rule iteration |
| `--run` invokes scanner | Run `orchestrator.py --config <cfg> --run`, verify `scan_and_tag.py` output appears in process stdout |
| `--run` pauses at MANIFEST_READY | Run orchestrator --run from clean state, verify exits with AWAITING_AGENT.md containing manifest instructions |
| Resume from AWAITING_AGENT | Create valid manifest, re-run orchestrator --run, verify advances past MANIFEST_READY to TOOLING_SCOUT_READY |
| Round-trip agent → script → agent | Full pipeline: agent produces manifest → --run executes tooling_scout + build_audit + scanner → agent processes rule batches → orchestrator verifies → DONE |
| `--run` with no Docker (BUILD_GATE_READY) | Run on system without Docker, build_audit.py exits 3, verify orchestrator fails with DOCKER_MISSING |
| Script killed by signal | Kill subprocess, verify orchestrator fails with SCRIPT_SIGNALED |