# jade-11-to-17 — Migration Progress

**Source:** 11 → **Target:** 17
**Current state:** DONE
**Updated:** 2026-09-05T11:37:37Z

| Phase | Status | Details |
|-------|--------|---------|
| ✅ INIT | OK | Run initialized |
| ✅ WORKSPACE_READY | OK | Workspace ready: migration-runs/jade-11-to-17/workspace |
| ✅ MANIFEST_READY | OK | Paused for agent input — see AWAITING_AGENT.md |
| 🔴 AWAITING_AGENT | ERROR | Run terminated: AWAITING_AGENT |
| ✅ INIT | OK | Run initialized |
| ✅ WORKSPACE_READY | OK | Workspace ready: migration-runs/jade-11-to-17/workspace |
| 🔴 FAILED | ERROR | Run terminated: FAILED |
| ✅ INIT | OK | Run initialized |
| ✅ WORKSPACE_READY | OK | Workspace ready: migration-runs/jade-11-to-17/workspace |
| ✅ RULE_BATCH_LOOP | OK | Paused for agent input — see AWAITING_AGENT.md |
| ✅ INIT | OK | Run initialized |
| ✅ WORKSPACE_READY | OK | Workspace ready: migration-runs/jade-11-to-17/workspace |
| 🔴 RULE_BATCH_LOOP | ERROR | COLLAPSED: 453 duplicate 'Processing rule RMIC_TOOL_REMOVED' entries between 2026-09-05T11:28:11Z and 2026-09-05T11:37:35Z. Cause: 07-build.log was stale (predated the RULE_BATCH_LOOP fixes, still showed the pre-fix rmic BUILD FAILED), so _validate_artifact rejected it every pass and RULE_RETRY -> RETRY -> RULE_BATCH_LOOP looped with no backoff. Interrupted manually, then resolved by rebuilding 07-build.log for real (docker run jade-ant:17 ant clean lib -q -> BUILD SUCCESSFUL) before resuming. See the background task flagged against orchestrator.py's RULE_RETRY path (no backoff/iteration cap when a script-mode gate artifact fails validation). |
| ✅ RULE_BATCH_LOOP | OK | Completed rule RMIC_TOOL_REMOVED |
| ✅ RULE_BATCH_LOOP | OK | Processing rule THREADGROUP_DESTROY_DEPRECATED_FOR_REMOVAL |
| ✅ RULE_BATCH_LOOP | OK | Completed rule THREADGROUP_DESTROY_DEPRECATED_FOR_REMOVAL |
| ✅ RULE_BATCH_LOOP | OK | Processing rule WRAPPER_CONSTRUCTOR_DEPRECATED_FOR_REMOVAL |
| ✅ RULE_BATCH_LOOP | OK | Completed rule WRAPPER_CONSTRUCTOR_DEPRECATED_FOR_REMOVAL |
| ✅ RULE_BATCH_LOOP | OK | Processing rule MULTICAST_SOCKET_GROUP_API_DEPRECATED |
| ✅ RULE_BATCH_LOOP | OK | Completed rule MULTICAST_SOCKET_GROUP_API_DEPRECATED |
| ✅ RULE_BATCH_LOOP | OK | Processing rule APPLET_API_DEPRECATED_FOR_REMOVAL |
| ✅ RULE_BATCH_LOOP | OK | Completed rule APPLET_API_DEPRECATED_FOR_REMOVAL |
| ✅ DONE | OK | Run terminated: DONE |
