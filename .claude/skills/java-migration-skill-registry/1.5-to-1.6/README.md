# Skill Registry — Java 1.5 → 1.6

This bucket contains recipes for the Java 1.5 to 1.6 migration. Recipes are invoked
as subprocesses through `jade-core-rule-dispatcher/recipe-registry.json` (mapped by
`rule_id`); nested `SKILL.md` files are documentation, not agent-discoverable skills.

| rule_id | Recipe | Effect |
|---------|--------|--------|
| `ARRAYS_COPY_OF_UPGRADE` | `jade-recipe-1.5-1.6-arrays-copyof` | `System.arraycopy` → `Arrays.copyOf`/`copyOfRange` |
| `DEQUE_LINKEDLIST_RETROFIT` | `jade-recipe-1.5-1.6-deque-retrofit` | Informational — `LinkedList` already implements `Deque` |
| `NAVIGABLE_SET_MAP` | `jade-recipe-1.5-1.6-navigable-set-map` | Informational — `TreeSet`/`TreeMap` already implement `Navigable*` |

Each recipe dir contains `SKILL.md` (docs + agent-fallback) and
`scripts/apply.py` (deterministic transform, `--file` / `--line`). New recipes should
be scaffolded with the canonical registration helper:

1. Run `scripts/register_recipe.py` with `--bucket 1.5-to-1.6`
2. Review the generated or copied `SKILL.md` and `scripts/apply.py`
3. Verify the registry entry and recipe subprocess before committing

## Current status

Existing recipes are maintained in this bucket; new recipes must use the canonical
registration helper.
