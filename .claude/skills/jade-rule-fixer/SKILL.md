---
name: jade-rule-fixer
description: >-
  Applies exactly one rule fix to exactly one file — the smallest atomic unit
  of the rule batch pipeline. Reads the matching rule from the breaking-changes
  manifest, extracts the target snippet, generates a patch, applies it
  atomically, and records the result. Emits NEEDS_REVIEW when confidence is low
  or the match is ambiguous. Never edits files outside the assigned task.
when_to_use: >-
  Use inside the RULE_BATCH_LOOP phase, dispatched once per task entry from
  the jade-rule-batch-processor output. Do not invoke independently.
arguments: [artifacts_dir, rule_id, task_id]
argument-hint: "<artifacts-dir> <rule-id> <task-id>"
allowed-tools: Bash(python *) Read Write Edit
---

# JADE Rule Fixer

## Objective

Apply **one rule fix to one file** — the atomic unit of work in the rule
batch pipeline. Each execution is stateless: it loads the rule, reads the
file, applies the fix, and records the result. No cross-file edits.

## Core Constraints

1. **One execution = one file + one rule_id.** Never touch other files.
2. May only edit the assigned file from the task entry.
3. Must emit `NEEDS_REVIEW` when confidence drops below threshold.
4. All writes use tmp-file + atomic replace.
5. Never fabricate a diff — the `fix_strategy` and `match_pattern` from
   the manifest are the sole source of truth.
6. Stop on first unrecoverable error; record `FAILED` with error detail.

## Required Input

| Artifact | Purpose |
|----------|---------|
| `artifacts/05-rule-batch-{rule_id}.json` | Task entry list; used to locate the specific task by `task_id` |
| `artifacts/01-breaking-changes-manifest.json` | Rule definitions (`match_pattern`, `fix_strategy`, `confidence`) |

## Produced Output

| Artifact | Purpose |
|----------|---------|
| `artifacts/06-fix-result-{task-id}.json` | Per-task fix record with status, confidence, diff summary, and any warnings |
| Modified workspace file | The source file with the fix applied atomically |

## Fixer Execution Model

```
LOAD  →  MATCH  →  PLAN  →  APPLY  →  RECORD
```

### Phase 1 — LOAD

1. Read `artifacts/05-rule-batch-{rule_id}.json`.
2. Find the task entry where `task_id == $task_id`.
3. If not found: write `FAILED` result, exit code 2.
4. Extract `file` (relative to workspace root), `line_start`, `line_end`,
   and `snippet` from the task entry.
5. Read `artifacts/01-breaking-changes-manifest.json` and locate the rule
   where `rule_id == $rule_id`.
6. If rule not found: write `FAILED` result, exit code 2.

### Phase 2 — MATCH

1. Read the target file (full content).
2. Extract the flagged region: lines `line_start` through `line_end`.
3. Apply `match_pattern` (regex) against the flagged region.
4. Count matches:
   - **0 matches** → `FAILED` (pattern does not match flagged region).
   - **1 match** → proceed to PLAN.
   - **> 1 match** → set `match_count`, lower confidence; proceed with
     first match, flag as potential `NEEDS_REVIEW`.

### Phase 3 — PLAN

1. Determine confidence:
   ```
   final_confidence = rule.confidence * match_quality_factor
   ```
   `match_quality_factor`:
   - `1.0` — single exact match, no ambiguity
   - `0.9` — single match but near-miss on edge case
   - `0.8` — multiple matches found, first match used
   - `0.6` — pattern matched but surrounding context ambiguous
2. If `final_confidence < 0.85`: status → `NEEDS_REVIEW`.
3. Generate replacement text from `fix_strategy`:
   - If `fix_strategy` is a structured template (`"replace": "{match}",
     "with": "{replacement}"`), perform the substitution.
   - If `fix_strategy` is a plain string instruction, resolve it
     against the matched text.
4. Compute a preview diff (before/after of the matched region).

### Phase 4 — APPLY

1. Write the modified file content to a tmp file (same directory,
   `.tmp.{task_id}` suffix).
2. Atomically rename tmp → target file.
3. If the filesystem does not support atomic rename across devices,
   fall back to write-then-move within the same directory.
4. On write failure: `FAILED` result with `IOError` detail.

### Phase 5 — RECORD

Write `artifacts/06-fix-result-{task-id}.json`:

```json
{
  "task_id": "BC-1.6-0001-0001",
  "rule_id": "BC-1.6-0001",
  "file": "JADE-4.6.0-java1.6/src/jade/core/SomeFile.java",
  "status": "FIXED|NEEDS_REVIEW|FAILED|SKIPPED",
  "confidence": 0.92,
  "match_count": 1,
  "match_region": "lines 67-80",
  "diff_summary": "Removed 1 cast, added generic parameter",
  "verification_hint": "from manifest",
  "errors": [],
  "warnings": [],
  "applied_at": "2026-05-21T12:00:00Z"
}
```

## NEEDS_REVIEW Conditions

A result MUST be `NEEDS_REVIEW` (not `FIXED`) when ANY of these hold:

| Condition | Trigger |
|-----------|---------|
| `final_confidence < 0.85` | Rule confidence already marginal or match ambiguous |
| `match_count > 1` | Multiple matches in flagged region — may have applied to wrong occurrence |
| `fix_strategy` contains `"manual"` or `"review"` keyword | Manifest signals human review needed |
| Diff touches lines outside `line_start`–`line_end` range | Fix spilled beyond flagged region |
| Rule category is `BEHAVIOR_CHANGE` | Semantic change, not syntactic — needs verification |
| File contains `MIGRATION-SKIP` marker | Previous migration already flagged this file as problematic |

`NEEDS_REVIEW` is NOT a failure — it means the fix was applied but a human
should verify it before the rule batch is committed.

## Halt Conditions

| Condition | Exit Code | Action |
|-----------|-----------|--------|
| Task entry not found in batch file | 2 | Record `FAILED`, exit |
| Rule not found in manifest | 2 | Record `FAILED`, exit |
| `match_pattern` yields 0 matches | 2 | Record `FAILED` with `match_failed`, exit |
| Target file does not exist | 2 | Record `FAILED` with `file_not_found`, exit |
| File write fails (disk full, permissions) | 2 | Record `FAILED` with `IOError`, exit |

## Script

Use `scripts/apply_rule_fix.py` with the required arguments:

```
python scripts/apply_rule_fix.py \
  --artifacts-dir migration-runs/sample/artifacts \
  --rule-id BC-1.6-0001 \
  --task-id BC-1.6-0001-0001
```
