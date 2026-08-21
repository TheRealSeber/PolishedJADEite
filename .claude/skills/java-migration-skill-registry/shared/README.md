# Recipes — Shared (version-agnostic)

Pipeline-infrastructure recipes that are not tied to any specific version jump.
Invoked by `jade-core-rule-dispatcher` via `recipe-registry.json`.

| rule_id | Recipe | Effect |
|---------|--------|--------|
| `fallback` | `jade-recipe-noop` | Marks rule `SKIPPED` when no specific recipe exists |
| `DUMMY_TEST_RULE` | `jade-recipe-dummy` | Appends `// E2E TEST` — validates the pipeline end-to-end |

Each recipe dir contains `SKILL.md` (docs + agent-fallback) and
`scripts/apply.py` (deterministic transform, `--file` / `--line`).
