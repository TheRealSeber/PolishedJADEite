# AWAITING AGENT — RULE_BATCH_LOOP (agent recipe)
Rule: BUILD_DOCLINT_STRICT | blast_class: body-local | shards: 1

## Anti-bypass

**ANTI-BYPASS:** You are strictly forbidden from manually creating a batch
artifact and marking it `DONE` or `NOOP` if flags exist for that rule.
You must either (a) write a true registry recipe script to transform the flagged
code, or (b) use `defer_rules.py` to defer modernization flags and preserve
them as `// JADE-MODERNIZATION-DEFERRED` markers for future developers.
Failure to comply is a pipeline integrity violation. An agent-result envelope
reporting status `FIXED` with zero files is an additional integrity
violation — an empty envelope must never be recorded as FIXED.

## Shards

| shard_id | class | parallel_safe | editable_files | entry_points |
|----------|-------|----------------|----------------|--------------|
| BUILD_DOCLINT_STRICT-body-local-001 | body-local | True | 1 | 2 |

## Per-shard procedure

For each shard, run these seven steps in order:

1. Checkpoint the shard's editable files (git blob snapshot).
2. Dispatch one subagent for the shard: it may edit only that shard's
   `editable_files`; `read_only_context` is read-only. It writes a result
   envelope to `result_file`.
3. Verify the shard compiles (javac in Docker against the previous jar).
4. Gate the shard's edits against the knowledge graph for signature leaks
   outside the shard's editable set.
5. Record the subagent's result envelope into `06-fix-results-<rule_id>.json`.
6. If verify and gate both exited 0/1 and record exited 0: accept the shard
   (the checkpoint blob is dropped; the edit is kept).
7. Otherwise (verify/gate exited 2/3, or record exited 2/3/4): roll back the
   shard to its checkpointed state, with a `--reason` explaining why.

Shards with `parallel_safe: true` may be dispatched concurrently to
independent subagents; `parallel_safe: false` shards must be run
sequentially.

### BUILD_DOCLINT_STRICT-body-local-001

1. `python .claude/skills/jade-core-orchestrator/scripts/shard_checkpoint.py --artifacts-dir migration-runs/jade-1.7-to-1.8-v2/artifacts --rule-id BUILD_DOCLINT_STRICT --shard-id BUILD_DOCLINT_STRICT-body-local-001 --workspace migration-runs/jade-1.7-to-1.8-v2/workspace --create`
2. Dispatch the subagent for this shard.
3. `python .claude/skills/jade-core-verification/scripts/verify_shard.py --artifacts-dir migration-runs/jade-1.7-to-1.8-v2/artifacts --rule-id BUILD_DOCLINT_STRICT --shard-id BUILD_DOCLINT_STRICT-body-local-001`
4. `python .claude/skills/jade-core-verification/scripts/gate_signatures.py --artifacts-dir migration-runs/jade-1.7-to-1.8-v2/artifacts --rule-id BUILD_DOCLINT_STRICT --shard-id BUILD_DOCLINT_STRICT-body-local-001 --before-graph migration-runs/jade-1.7-to-1.8-v2/artifacts/03.5-knowledge-graph.json --after-graph migration-runs/jade-1.7-to-1.8-v2/artifacts/03.5-knowledge-graph-after-BUILD_DOCLINT_STRICT-body-local-001.json`
5. `python .claude/skills/jade-core-rule-dispatcher/scripts/dispatcher.py --artifacts-dir migration-runs/jade-1.7-to-1.8-v2/artifacts --rule-id BUILD_DOCLINT_STRICT --record-agent-result --shard-id BUILD_DOCLINT_STRICT-body-local-001 --result-file migration-runs/jade-1.7-to-1.8-v2/artifacts/06-agent-result-BUILD_DOCLINT_STRICT-BUILD_DOCLINT_STRICT-body-local-001.json`
6. `python .claude/skills/jade-core-orchestrator/scripts/shard_checkpoint.py --artifacts-dir migration-runs/jade-1.7-to-1.8-v2/artifacts --rule-id BUILD_DOCLINT_STRICT --shard-id BUILD_DOCLINT_STRICT-body-local-001 --workspace migration-runs/jade-1.7-to-1.8-v2/workspace --accept`
7. `python .claude/skills/jade-core-orchestrator/scripts/shard_checkpoint.py --artifacts-dir migration-runs/jade-1.7-to-1.8-v2/artifacts --rule-id BUILD_DOCLINT_STRICT --shard-id BUILD_DOCLINT_STRICT-body-local-001 --workspace migration-runs/jade-1.7-to-1.8-v2/workspace --rollback --reason "<why>"`

## Subagent contract

One subagent per shard. It may edit only files listed in that shard's
`editable_files`; `read_only_context` files may be read but never written.
It returns a result envelope (schema_version, rule_id, shard_id, status,
match_quality, diff_summary, files[], errors[], warnings[]) to the shard's
`result_file`.

## Resume

```
python .claude/skills/jade-core-orchestrator/scripts/orchestrator.py --config migration-runs/jade-1.7-to-1.8-v2/artifacts/00-run-config.json --run
```
