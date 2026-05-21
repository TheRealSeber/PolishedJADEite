---
name: jade-atomic-rule-commit
description: >-
  Stages and commits all files touched by a single migration rule, using a strict
  conventional-commit message format. Logs the commit SHA to artifacts/09-rule-commit-log.json
  so the orchestrator can verify the rule was committed before moving to the next rule.
when_to_use: >-
  Invoked automatically by jade-migration-orchestrator after every rule passes verification.
  May also be used standalone when the user says "commit rule X", "atomic commit", or
  "commit this migration rule".
arguments: [rule_id, batch_artifact, short_description]
argument-hint: "[rule_id] [path/to/batch-artifact.json] \"short description\""
disable-model-invocation: true
allowed-tools: Bash(git *) Bash(python *) Read Write
env: {}
paths: "*.py" "*.sh" "*.json" "*.java"
---

# JADE Atomic Rule Commit

## Objective

Commit verified changes for **one rule** before the next rule starts. Every rule gets its own
commit with an exact, machine-readable format. The commit hash is logged to a JSON artifact
so the orchestrator can confirm the commit succeeded before advancing the rule queue.

## Required inputs

| Input | Source | Description |
|-------|--------|-------------|
| `rule_id` | orchestrator (from `05-rule-queue.json`) | e.g. `raw-types`, `enhanced-for` |
| `batch_artifact` | previous step (`08-rule-batch-{rule_id}.json`) | JSON listing files touched |
| `short_description` | rule definition | e.g. `add generic type parameters to raw collections` |
| `artifacts_path` | `00-run-config.json` → `artifacts_path` | Base path for artifact I/O |

## Outputs

| Artifact | Description |
|----------|-------------|
| `artifacts/09-rule-commit-log.json` | `{rule_id, commit_hash, message, timestamp, files[]}` |

## Commit policy

### Message format (strict)

```
fix(migration): resolved {rule_id} - {short_description}
```

The body is optional. If the rule touched > 5 files, the body lists affected packages:

```
Affected: package1, package2, ...
```

### Rules

1. **One commit per rule** — never squash multiple rules into one commit.
2. **Only stage files listed in the batch artifact** — never `git add -A` or `git add .`.
3. **Abort if working tree is dirty with unrelated changes** — refuse to commit if
   `git diff --name-only` shows files *not* in the batch artifact's file list.
4. **Commit hash log is the source of truth** — the orchestrator reads
   `09-rule-commit-log.json` to confirm the commit happened.
5. **Never amend** — each rule commit is immutable history.

### Safety gate

Before staging, run `git diff --name-only` and `git diff --cached --name-only`. If the union
of dirty + staged files exceeds the batch artifact's file list, abort with an error message
listing the unexpected files. The orchestrator treats this as `COMMIT_SAFETY_GATE_FAILED`.

## Workflow

1. Load batch artifact JSON.
2. Run `scripts/list_rule_files.py` to extract the flat file list.
3. Run the safety gate (compare dirty/staged files against allowed set).
4. Run `scripts/commit_rule.sh` with `rule_id`, the file list, and `short_description`.
5. Verify `artifacts/09-rule-commit-log.json` was written with a non-empty `commit_hash`.
6. Return 0 on success, non-zero on failure.

## Exit criteria

- Exactly one new commit exists on HEAD with the correct message format.
- `artifacts/09-rule-commit-log.json` is present and valid.
- Working tree is clean (all rule changes consumed by the commit).

## Failure modes

| Code | Meaning |
|------|---------|
| `BATCH_ARTIFACT_MISSING` | batch artifact file not found |
| `BATCH_ARTIFACT_INVALID` | batch artifact does not contain a `files` key (list or dict) |
| `COMMIT_SAFETY_GATE_FAILED` | dirty/staged files exist that are not in the batch artifact |
| `COMMIT_FAILED` | `git commit` returned non-zero |
| `COMMIT_LOG_MISSING` | commit succeeded but `09-rule-commit-log.json` was not written |
