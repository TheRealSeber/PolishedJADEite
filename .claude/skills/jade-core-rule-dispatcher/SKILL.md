---
name: jade-core-rule-dispatcher
description: >-
  Routes rule tasks to recipe skills via recipe-registry.json. Handles
  LOAD/MATCH/RECORD workflow but delegates all transform logic to recipe
  subprocesses. Contains ZERO version-specific or rule-specific transform code.
  Accepts one task at a time from the rule batch.
when_to_use: >-
  Use inside the RULE_BATCH_LOOP phase, dispatched once per task entry from
  jade-core-batch-processor output. The orchestrator invokes this skill per-task.
arguments: [artifacts_dir, rule_id, task_id]
argument-hint: "<artifacts-dir> <rule-id> <task-id>"
allowed-tools: Bash(python *) Read Write
---

# JADE Core Rule Dispatcher

## Objective

Route a single rule task to the correct recipe skill. The dispatcher contains **zero
transform logic** — its only job is to load the task, find the matching recipe
in `recipe-registry.json`, invoke the recipe script as a subprocess, and record
the result.

## Core constraints

1. **Never modify source files directly** — only recipe scripts touch source.
2. **Never contain regex or AST transform logic** — all transforms live in recipes.
3. **One execution = one file + one rule_id.**
4. All artifact writes use tmp-file + atomic rename.

## Required input

- `artifacts/05-rule-batch-{rule_id}.json` — task entry list
- `artifacts/01-breaking-changes-manifest.json` — rule definitions
- `recipe-registry.json` (in dispatcher directory)

## Produced output

- `artifacts/06-fix-results-{rule_id}.json` — aggregate array of per-flag fix records

## Recipe invocation contract

The dispatcher invokes recipe scripts as:
```
python <recipe-script> --file <path> --line <num>
```

Recipe scripts MUST:
- Exit 0 on success, non-zero on failure
- Print a single JSON line to stdout: `{"status": "FIXED|FAILED|SKIPPED|DEFERRED", "changes": N, "warnings": [...], "errors": [...], "diff_summary": "..."}`
- Handle file I/O internally (read, transform, atomic write)

The dispatcher records each result with `task_id`, `rule_id`, `file`, `status`,
`match_count`, `match_region`, `match_context`, `diff_summary`,
`verification_hint`, `errors`, `warnings`, and `applied_at`.

## Fix strategy format

In `01-breaking-changes-manifest.json`, rules specify:
```json
"fix_strategy": "recipe:jade-recipe-java1.5-generics"
```

The dispatcher looks up `rule_id` in `recipe-registry.json` to resolve the
actual script path.

## Script

Use `scripts/dispatcher.py`:
```
python scripts/dispatcher.py \
  --artifacts-dir migration-runs/sample/artifacts \
  --rule-id RAW_TYPES \
  --task-id RAW_TYPES-0001
```
