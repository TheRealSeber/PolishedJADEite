# Recipes — Java 1.7 → 1.8

Transform recipes for the Java 1.7 → 1.8 migration. Invoked by
`jade-core-rule-dispatcher` via `recipe-registry.json` (mapped by `rule_id`).

| rule_id | Recipe | Effect |
|---------|--------|--------|
| `LAMBDA_CONVERSION` | `jade-recipe-1.7-1.8-lambda-conversion` | Anonymous SAM inner classes → lambdas |
| `THREAD_STOP_DISABLED` | `jade-recipe-1.7-1.8-thread-stop-removal` | Inspect `.stop()` calls; defer real `Thread.stop()` |

Each recipe dir contains `SKILL.md` (docs + agent-fallback) and
`scripts/apply.py` (deterministic transform, `--file` / `--line`).
