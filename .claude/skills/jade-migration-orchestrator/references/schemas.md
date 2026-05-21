# JADE Migration Orchestrator Artifact Schemas

## run-config (`artifacts/00-run-config.json`)

```json
{
  "run_id": "string",
  "workspace_path": "string",
  "artifacts_path": "string",
  "source_version": "string",
  "target_version": "string"
}
```

Required keys:
- `run_id`
- `workspace_path`
- `artifacts_path`
- `source_version`
- `target_version`

## run-state (`artifacts/00-run-state.json`)

```json
{
  "run_id": "string",
  "state": "INIT|WORKSPACE_READY|MANIFEST_READY|TOOLING_SCOUT_READY|BUILD_GATE_READY|SCAN_READY|RULE_BATCH_LOOP|VERIFIED|DONE|FAILED|AWAITING_SOURCE_INPUT",
  "current_rule_id": "string|null",
  "updated_at": "ISO-8601 string",
  "failure_reason": "string|null"
}
```

## phase-result (`artifacts/phase-history.log.jsonl`)

Each line is a JSON object:

```json
{
  "ts": "ISO-8601 string",
  "phase": "string",
  "status": "OK|ERROR|SKIPPED",
  "message": "string",
  "artifacts": ["string"]
}
```
