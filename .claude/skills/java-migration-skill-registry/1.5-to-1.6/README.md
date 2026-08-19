# Recipes — Java 1.5 → 1.6

Transform recipes for the Java 1.5 → 1.6 migration. Invoked by
`jade-core-rule-dispatcher` via `recipe-registry.json` (mapped by `rule_id`).

| rule_id | Recipe | Effect |
|---------|--------|--------|
| `ARRAYS_COPY_OF_UPGRADE` | `jade-recipe-1.5-1.6-arrays-copyof` | `System.arraycopy` → `Arrays.copyOf`/`copyOfRange` |
| `DEQUE_LINKEDLIST_RETROFIT` | `jade-recipe-1.5-1.6-deque-retrofit` | Informational — `LinkedList` already implements `Deque` |
| `NAVIGABLE_SET_MAP` | `jade-recipe-1.5-1.6-navigable-set-map` | Informational — `TreeSet`/`TreeMap` already implement `Navigable*` |

Each recipe dir contains `SKILL.md` (docs + agent-fallback) and
`scripts/apply.py` (deterministic transform, `--file` / `--line`).
