# Recipes — Java 1.7

Transform recipes for Java 7 target features. Invoked by
`jade-core-rule-dispatcher` via `recipe-registry.json` (mapped by `rule_id`).

| rule_id | Recipe | Effect |
|---------|--------|--------|
| `DIAMOND_OPERATOR` | `jade-recipe-1.7-diamond-operator` | Explicit generic type args → diamond `<>` |
| `STRINGS_IN_SWITCH` | `jade-recipe-1.7-strings-in-switch` | `.equals()` if-chains → `switch` on strings |

Each recipe dir contains `SKILL.md` (docs + agent-fallback) and
`scripts/apply.py` (deterministic transform, `--file` / `--line`).
