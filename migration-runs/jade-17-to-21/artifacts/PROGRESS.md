# jade-17-to-21 — Migration Progress

**Source:** 17 → **Target:** 21
**Current state:** DONE
**Updated:** 2026-09-05T16:36:36Z

| Phase | Status | Details |
|-------|--------|---------|
| ✅ INIT | OK | Run initialized |
| ✅ WORKSPACE_READY | OK | Workspace ready: migration-runs/jade-17-to-21/workspace |
| 🔴 FAILED | ERROR | ARTIFACT_MISSING: Required for MANIFEST_READY: migration-runs/jade-17-to-21/artifacts/01-breaking-changes-manifest.json |
| 🔴 FAILED | ERROR | Run terminated: FAILED |
| ✅ INIT | OK | Run initialized |
| ✅ WORKSPACE_READY | OK | Workspace ready: migration-runs/jade-17-to-21/workspace |
| 🔴 FAILED | ERROR | ARTIFACT_MISSING: Required for KNOWLEDGE_GRAPH_READY: migration-runs/jade-17-to-21/artifacts/03.5-knowledge-graph.json |
| 🔴 FAILED | ERROR | Run terminated: FAILED |
| ✅ INIT | OK | Run initialized |
| ✅ WORKSPACE_READY | OK | Workspace ready: migration-runs/jade-17-to-21/workspace |
| ✅ RULE_BATCH_LOOP | OK | Paused for agent input — see AWAITING_AGENT.md |
| ✅ INIT | OK | Run initialized |
| ✅ WORKSPACE_READY | OK | Workspace ready: migration-runs/jade-17-to-21/workspace |
| ✅ RULE_BATCH_LOOP | OK | Processing rule JEP400_FILE_IO_DEFAULT_CHARSET |
| ✅ RULE_BATCH_LOOP | OK | Completed rule JEP400_FILE_IO_DEFAULT_CHARSET |
| ✅ RULE_BATCH_LOOP | OK | Processing rule THREADDEATH_DEPRECATED_FOR_REMOVAL |
| ✅ RULE_BATCH_LOOP | OK | Completed rule THREADDEATH_DEPRECATED_FOR_REMOVAL |
| ✅ RULE_BATCH_LOOP | OK | Processing rule FINALIZE_DEPRECATED_FOR_REMOVAL |
| 🔴 FAILED | ERROR | SHARD_LEDGER_INVALID: shard ledger keys ['FINALIZE_DEPRECATED_FOR_REMOVAL-body-local-001', 'FINALIZE_DEPRECATED_FOR_REMOVAL-signature-001'] do not match plan shard_ids ['FINALIZE_DEPRECATED_FOR_REMOVAL-signature-001'] |
| 🔴 FAILED | ERROR | Run terminated: FAILED |
| ✅ INIT | OK | Run initialized |
| ✅ WORKSPACE_READY | OK | Workspace ready: migration-runs/jade-17-to-21/workspace |
| ✅ RULE_BATCH_LOOP | OK | Processing rule FINALIZE_DEPRECATED_FOR_REMOVAL |
| ✅ RULE_BATCH_LOOP | OK | Completed rule FINALIZE_DEPRECATED_FOR_REMOVAL |
