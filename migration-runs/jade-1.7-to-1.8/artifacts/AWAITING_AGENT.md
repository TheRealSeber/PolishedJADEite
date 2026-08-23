# AWAITING AGENT — RULE_BATCH_LOOP

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
   python .claude/skills/jade-core-batch-processor/scripts/defer_rules.py \
     --workspace migration-runs/jade-1.7-to-1.8/workspace \
     --artifacts migration-runs/jade-1.7-to-1.8/artifacts \
     --rule-id <rule_id> --reason "<user-provided reason>"
   ```
4. Create `migration-runs/jade-1.7-to-1.8/artifacts/05-rule-queue.json` with ONLY rules the user
   approved (all mandatory breaking changes + user-selected modernization rules)
5. For each rule:
   a. Create `migration-runs/jade-1.7-to-1.8/artifacts/05-rule-batch-<rule_id>.json` with per-file tasks
   b. Dispatch recipe via rule-dispatcher
   c. Apply transforms to flagged source files
6. After all rules processed, produce `migration-runs/jade-1.7-to-1.8/artifacts/07-build.log`
   by running the build in Docker via `build_audit.py`

## Resume

After rule batches and build verification are complete:
```
python .claude/skills/jade-core-orchestrator/scripts/orchestrator.py --config migration-runs/jade-1.7-to-1.8/artifacts/00-run-config.json --run
```
