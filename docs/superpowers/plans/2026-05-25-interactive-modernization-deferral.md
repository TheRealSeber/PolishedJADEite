# Interactive Modernization Decision + Deferral Mechanism

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate breaking-change rules (mandatory transform) from modernization opportunities (user chooses apply vs defer), add a deferral script that rewrites `JADE-FLAG` to `JADE-MODERNIZATION-DEFERRED`, and add anti-bypass guardrails.

**Architecture:** Three coordinated changes: (1) New hard constraint #14 in AGENTS.md codifies the interactive decision rule, (2) `defer_rules.py` rewrites flagged comments in-place to preserve technical debt markers, (3) Orchestrator AWAITING_AGENT.md generation and SKILL.md include anti-bypass language.

**Tech Stack:** Python 3 (argparse, pathlib, re), bash, existing JADE pipeline conventions.

---

### File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `AGENTS.md:54` | Modify | Add constraint #14 after existing #13 |
| `.claude/skills/jade-core-batch-processor/scripts/defer_rules.py` | Create | Scan workspace, rewrite `JADE-FLAG:<id>` → `JADE-MODERNIZATION-DEFERRED:<id> <reason>`, write audit artifact |
| `.claude/skills/jade-core-orchestrator/scripts/orchestrator.py:454-477` | Modify | Inject anti-bypass guardrail into RULE_BATCH_LOOP AWAITING_AGENT.md text |
| `.claude/skills/jade-core-orchestrator/SKILL.md:80` | Modify | Add anti-bypass section before Rule batch policy |

---

### Task 1: AGENTS.md — Constraint #14

**Files:**
- Modify: `AGENTS.md:54-55`

- [ ] **Step 1: Read current Hard Constraints section**

```
read AGENTS.md offset=24 limit=32
```

Verify line 54 is constraint #13 ending, line 55 is blank, line 56 is `## Skill Inventory`.

- [ ] **Step 2: Insert constraint #14**

After line 54 (end of constraint #13), insert two newlines then constraint #14 text.

```markdown
14. **Interactive Modernization Decision** — At `RULE_BATCH_LOOP`, the Agent MUST
    read `04-scan-summary.json` and group flagged rules by severity. `HIGH`/`MEDIUM`
    rules are Breaking Changes (mandatory — must be transformed via a registry recipe script).
    `LOW`/`INFO` rules are Modernization Opportunities (optional). The Agent
    MUST ask the user in-chat: "Which modernization rules should be applied vs
    deferred?" before generating `05-rule-queue.json`. Only user-acknowledged
    rules may enter the rule queue. Rules the user chooses to defer MUST be
    processed via `defer_rules.py` so flags persist as
    `// JADE-MODERNIZATION-DEFERRED:<rule_id>` markers for future developers.
```

- [ ] **Step 3: Verify file integrity**

```bash
python -c "
lines = open('AGENTS.md').readlines()
idx = [i for i, l in enumerate(lines) if 'Interactive Modernization Decision' in l]
print(f'Found at line {idx[0]+1}')
# Verify numbering: constraint 13 is still before, Skill Inventory after
assert '13.' in lines[idx[0]-4] or '13.' in lines[idx[0]-3]
assert 'Skill Inventory' in lines[idx[0]+8] or 'Skill Inventory' in lines[idx[0]+9]
print('Structure OK')
"
```

- [ ] **Step 4: Commit**

```bash
git add AGENTS.md
git commit -m "feat: add constraint #14 - Interactive Modernization Decision"
```

---

### Task 2: Create `defer_rules.py`

**Files:**
- Create: `.claude/skills/jade-core-batch-processor/scripts/defer_rules.py`

- [ ] **Step 1: Write the script**

The script follows `rule_batch_runner.py` conventions. Key design:

1. **Argparse:** `--workspace`, `--artifacts`, `--rule-id`, `--reason` (required)
2. **Comment syntax per file extension** — same table as `scan_and_tag.py`
3. **Per-file processing:** read lines, find `JADE-FLAG:<rule_id>`, rewrite line to `JADE-MODERNIZATION-DEFERRED:<rule_id> <reason>`, atomic write via tmp + replace
4. **Exit codes:** 0 = success (even 0 flags found — idempotent), 2 = error
5. **Artifact:** writes `05-deferred-<rule_id>.json` to `--artifacts`

```python
#!/usr/bin/env python3
"""JADE Rule Deferral — rewrite JADE-FLAG markers to deferred status.

When a user chooses NOT to apply a modernization rule, this script rewrites
``// JADE-FLAG:<rule_id>`` → ``// JADE-MODERNIZATION-DEFERRED:<rule_id> <reason>``
in the workspace source files.  The rewritten markers are permanently visible
as technical-debt indicators but are ignored by subsequent scanner runs.

Usage:
    python defer_rules.py --workspace migration-runs/X/workspace \\
                          --artifacts migration-runs/X/artifacts \\
                          --rule-id STRINGS_IN_SWITCH \\
                          --reason "Not applicable to JADE codebase"
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from typing import Any, Dict, List, Tuple

# ---------------------------------------------------------------------------
# Comment syntax map (mirrors scan_and_tag.py)
# ---------------------------------------------------------------------------
_COMMENT_SYNTAX: Dict[str, Tuple[str, str]] = {
    ".java": ("//", ""),
    ".properties": ("#", ""),
    ".xml": ("<!--", "-->"),
    ".gradle": ("//", ""),
    ".kt": ("//", ""),
    ".scala": ("//", ""),
    ".groovy": ("//", ""),
}

_DEFAULT_COMMENT: Tuple[str, str] = ("//", "")


def _comment_syntax(ext: str) -> Tuple[str, str]:
    return _COMMENT_SYNTAX.get(ext.lower(), _DEFAULT_COMMENT)


# ---------------------------------------------------------------------------
# Flag detection
# ---------------------------------------------------------------------------
def _is_flag_line(line: str, rule_id: str, ext: str) -> bool:
    """Check if *line* is a JADE-FLAG comment for *rule_id*."""
    prefix, suffix = _comment_syntax(ext)
    flag_start = f"{prefix} JADE-FLAG:{rule_id} ".lstrip()
    alt_start = f"{prefix}JADE-FLAG:{rule_id} ".lstrip()
    stripped = line.strip()
    return stripped.startswith(flag_start) or stripped.startswith(alt_start)


def _rewrite_flag_line(line: str, rule_id: str, reason: str, ext: str) -> str:
    """Replace JADE-FLAG with JADE-MODERNIZATION-DEFERRED in *line*."""
    prefix, suffix = _comment_syntax(ext)
    indent = line[: len(line) - len(line.lstrip())]
    return f"{indent}{prefix}JADE-MODERNIZATION-DEFERRED:{rule_id} {reason}{suffix}\n"


# ---------------------------------------------------------------------------
# Helpers (mirrors rule_batch_runner.py conventions)
# ---------------------------------------------------------------------------
def iso_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def read_json(path: pathlib.Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: pathlib.Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------
def defer_rule(
    workspace: pathlib.Path,
    artifacts: pathlib.Path,
    rule_id: str,
    reason: str,
) -> Tuple[int, List[str]]:
    """Rewrite all JADE-FLAG markers for *rule_id* to deferred markers.

    Returns (exit_code, list_of_modified_files).
    """
    modified: List[str] = []
    flags_rewritten: int = 0

    for fp in workspace.rglob("*.java"):
        try:
            lines = fp.read_text(encoding="utf-8", errors="replace").splitlines(
                keepends=True
            )
        except OSError as exc:
            print(f"WARN [FILE_READ] {fp}: {exc}", file=sys.stderr)
            continue

        ext = fp.suffix.lower()
        rewritten = False
        new_lines: List[str] = []

        for line in lines:
            if _is_flag_line(line, rule_id, ext):
                new_lines.append(_rewrite_flag_line(line, rule_id, reason, ext))
                flags_rewritten += 1
                rewritten = True
            else:
                new_lines.append(line)

        if rewritten:
            tmp = fp.with_name(fp.name + ".defertmp")
            with tmp.open("w", encoding="utf-8") as fh:
                fh.writelines(new_lines)
            tmp.replace(fp)
            modified.append(str(fp.relative_to(workspace)))

    return 0 if flags_rewritten >= 0 else 2, modified


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Defer JADE modernization flags — rewrite to JADE-MODERNIZATION-DEFERRED"
    )
    parser.add_argument(
        "--workspace", required=True, help="Path to workspace root"
    )
    parser.add_argument(
        "--artifacts", required=True, help="Path to artifacts directory"
    )
    parser.add_argument("--rule-id", required=True, help="Rule ID to defer")
    parser.add_argument(
        "--reason", required=True, help="Reason for deferral (preserved in comment)"
    )
    args = parser.parse_args()

    workspace = pathlib.Path(args.workspace)
    artifacts = pathlib.Path(args.artifacts)

    if not workspace.exists():
        print(f"ERROR [WORKSPACE_MISSING] {workspace}", file=sys.stderr)
        return 2

    if not artifacts.exists():
        print(f"ERROR [ARTIFACTS_MISSING] {artifacts}", file=sys.stderr)
        return 2

    reason = args.reason.strip()
    if not reason:
        print("ERROR [REASON_EMPTY] --reason must be non-empty", file=sys.stderr)
        return 2

    print(f"Deferring rule {args.rule_id}: {reason}")

    exit_code, modified = defer_rule(workspace, artifacts, args.rule_id, reason)

    now = iso_now()
    deferred_artifact = {
        "rule_id": args.rule_id,
        "reason": reason,
        "files_modified": len(modified),
        "flags_rewritten": -1,  # updated below from flag count
        "files": modified,
        "deferred_at": now,
    }

    # Count total flags from the existing batch artifact for accuracy
    batch_path = artifacts / f"05-rule-batch-{args.rule_id}.json"
    if batch_path.exists():
        try:
            batch = read_json(batch_path)
            deferred_artifact["flags_rewritten"] = batch.get("total_files", len(modified))
        except (json.JSONDecodeError, OSError):
            deferred_artifact["flags_rewritten"] = len(modified)
    else:
        deferred_artifact["flags_rewritten"] = len(modified)

    deferred_path = artifacts / f"05-deferred-{args.rule_id}.json"
    write_json(deferred_path, deferred_artifact)

    print(
        f"Deferred {len(modified)} file(s) for rule {args.rule_id} → {deferred_path}"
    )

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Verify script runs (help text)**

```bash
python .claude/skills/jade-core-batch-processor/scripts/defer_rules.py --help
```

Expected: standard argparse help output showing `--workspace`, `--artifacts`, `--rule-id`, `--reason`.

- [ ] **Step 3: Test on existing workspace (dry-run style)**

Since `jade-1.6-to-1.7` workspace already exists, test deferring one LOW rule:

```bash
python .claude/skills/jade-core-batch-processor/scripts/defer_rules.py \
  --workspace migration-runs/jade-1.6-to-1.7/workspace \
  --artifacts migration-runs/jade-1.6-to-1.7/artifacts \
  --rule-id STRINGS_IN_SWITCH \
  --reason "Not applicable - JADE uses enums not strings for dispatch"
```

Expected: reports count of modified files, creates `05-deferred-STRINGS_IN_SWITCH.json`.

- [ ] **Step 4: Verify deferred comments look correct**

```bash
python -c "
import pathlib
import json

artifacts = pathlib.Path('migration-runs/jade-1.6-to-1.7/artifacts')
deferred = json.loads((artifacts / '05-deferred-STRINGS_IN_SWITCH.json').read_text())
# Check first modified file
fp = pathlib.Path('migration-runs/jade-1.6-to-1.7/workspace') / deferred['files'][0]
content = fp.read_text()
assert 'JADE-MODERNIZATION-DEFERRED:STRINGS_IN_SWITCH' in content
assert 'JADE-FLAG:STRINGS_IN_SWITCH' not in content
print(f'Verified: {deferred[\"files\"][0]} — deferred marker present, flag absent')
"
```

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/jade-core-batch-processor/scripts/defer_rules.py
git commit -m "feat: add defer_rules.py for modernization flag deferral"
```

---

### Task 3: Anti-Bypass Guardrail

**Files:**
- Modify: `.claude/skills/jade-core-orchestrator/scripts/orchestrator.py:455-468`
- Modify: `.claude/skills/jade-core-orchestrator/SKILL.md:80`

- [ ] **Step 1: Inject guardrail into orchestrator.py**

In `orchestrator.py`, find the RULE_BATCH_LOOP `AWAITING_AGENT.md` template (line 454-477). Add the guardrail paragraph between "## What to do" and the numbered list (after line 461).

Old (lines 460-462):
```python
            ## What to do

1. Review `04-scan-summary.json` and `04-flag-index.json` for flagged rules
```

New:
```python
            ## What to do

**ANTI-BYPASS:** You are strictly forbidden from manually creating a batch
artifact and marking it `DONE` or `NOOP` if flags exist for that rule.
You must either (a) write a true registry recipe script to transform the flagged
code, or (b) use `defer_rules.py` to defer modernization flags and preserve
them as `// JADE-MODERNIZATION-DEFERRED` markers for future developers.
Failure to comply is a pipeline integrity violation.

1. Review `04-scan-summary.json` and `04-flag-index.json` for flagged rules
```

- [ ] **Step 2: Add to Step 1 instructions — mandatory user interaction**

Modify step 1 and add step 2 in the numbered list to include severity grouping and user interaction:

Old (lines 462-463):
```python
1. Review `04-scan-summary.json` and `04-flag-index.json` for flagged rules
2. Create `{cfg["artifacts_path"]}/05-rule-queue.json` with rule IDs from flagged rules
```

New:
```python
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
```

- [ ] **Step 3: Inject guardrail into orchestrator SKILL.md**

In `.claude/skills/jade-core-orchestrator/SKILL.md`, after the "Rule application policy" section (line 79), insert a new section:

```markdown
### Anti-Bypass Guard (IMPORTANT)

At `RULE_BATCH_LOOP`, the Agent MUST NOT manually create a batch artifact
and mark it `DONE` or `NOOP` if flagged files exist for that rule.
Acceptable resolution paths:
1. **Transform** — Write a registry recipe script (`jade-recipe-*`) that actually applies
   the change, then dispatch it via the rule dispatcher.
2. **Defer** — Use `defer_rules.py` to rewrite `// JADE-FLAG:<rule_id>` to
   `// JADE-MODERNIZATION-DEFERRED:<rule_id> <reason>`. This preserves the
   marker as technical debt while removing it from the active pipeline.

Artifact-based bypasses (manually writing a JSON file to skip a rule) are
prohibited and constitute a pipeline integrity violation.
```

- [ ] **Step 4: Verify orchestrator.py changes compile**

```bash
python -c "import py_compile; py_compile.compile('.claude/skills/jade-core-orchestrator/scripts/orchestrator.py', doraise=True); print('Compile OK')"
```

- [ ] **Step 5: Run orchestrator with changes to verify no breakage**

The orchestrator state machine and text generation should still work:

```bash
# Just do a no-run check to validate the module loads and config parsing works
python -c "
from pathlib import Path
import sys
sys.path.insert(0, '.claude/skills/jade-core-orchestrator/scripts')
# Verify the f-string in _pause_for_agent still compiles
import orchestrator
print('Module loaded OK')
"
```

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/jade-core-orchestrator/scripts/orchestrator.py \
        .claude/skills/jade-core-orchestrator/SKILL.md
git commit -m "feat: add anti-bypass guardrail to orchestrator"
```

---
