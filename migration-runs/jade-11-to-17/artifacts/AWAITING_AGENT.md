# AWAITING AGENT — MANIFEST_READY

The pipeline has paused at the **change collector** phase.

## What to do

1. Identify Java 11 → 17 breaking-change sources
2. Fetch each source:
   ```
   python .claude/skills/jade-core-change-collector/scripts/fetch_source.py \
     --run-config migration-runs/jade-11-to-17/artifacts/00-run-config.json \
     --source-url "<URL>" --source-label "<label>"
   ```
3. Read the extracted content from `migration-runs/jade-11-to-17/artifacts/01-source-content-*.txt`
4. Extract rules via reading comprehension — every rule MUST come from the source text
5. Save rules to `migration-runs/jade-11-to-17/artifacts/01-extracted-rules.tmp.json`
6. Validate and write manifest:
   ```
   python .claude/skills/jade-core-change-collector/scripts/write_manifest.py \
     --input migration-runs/jade-11-to-17/artifacts/01-extracted-rules.tmp.json \
     --artifacts-dir migration-runs/jade-11-to-17/artifacts \
     --run-id jade-11-to-17 \
     --source-version 11 \
     --target-version 17
   ```

## Resume

After producing `01-breaking-changes-manifest.json`:
```
python .claude/skills/jade-core-orchestrator/scripts/orchestrator.py --config migration-runs/jade-11-to-17/artifacts/00-run-config.json --run
```
