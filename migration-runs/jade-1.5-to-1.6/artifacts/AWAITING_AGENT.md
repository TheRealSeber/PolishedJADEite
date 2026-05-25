# AWAITING AGENT — RULE_BATCH_LOOP

The pipeline has paused at the **rule batch processing** phase.

## What to do

1. Review `04-scan-summary.json` and `04-flag-index.json` for flagged rules
2. Create `migration-runs/jade-1.5-to-1.6/artifacts/05-rule-queue.json` with rule IDs from flagged rules
3. For each rule:
   a. Create `migration-runs/jade-1.5-to-1.6/artifacts/05-rule-batch-<rule_id>.json` with per-file tasks
   b. Dispatch recipe via rule-dispatcher
   c. Apply transforms to flagged source files
4. After all rules processed, produce `migration-runs/jade-1.5-to-1.6/artifacts/07-build.log`
   by running the build in Docker via `build_audit.py`

## Resume

After rule batches and build verification are complete:
```
python .claude/skills/jade-core-orchestrator/scripts/orchestrator.py --config migration-runs/jade-1.5-to-1.6/artifacts/00-run-config.json --run
```
