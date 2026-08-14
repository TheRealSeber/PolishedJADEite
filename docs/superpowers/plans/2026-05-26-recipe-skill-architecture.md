# Registry Recipe Architecture

## Canonical Layout

Registry recipe implementations are stored below one of these buckets:

```text
.claude/skills/java-migration-skill-registry/
├── 1.5-to-1.6/<recipe>/
├── 1.7/<recipe>/
├── 1.7-to-1.8/<recipe>/
└── shared/<recipe>/
```

Each registry recipe contains `SKILL.md` and `scripts/apply.py`. The dispatcher invokes only
the script path recorded in `.claude/skills/jade-core-rule-dispatcher/recipe-registry.json`;
nested `SKILL.md` files document the transform and are not dispatcher entry points.

## Creating A Recipe

Use the deterministic helper instead of writing a recipe under `.claude/skills/`:

```text
python .claude/skills/java-migration-skill-registry/scripts/register_recipe.py \
  --recipe-name example --bucket 1.7 --rule-id EXAMPLE_RULE \
  --description "Apply the example transform"
```

The helper creates minimal files or copies them from `--source-dir`, rejects unsafe
path segments and duplicates without `--force`, validates registry entries, safe
canonical script paths, and script existence,
and atomically replaces the registry JSON. A second identical invocation is a
successful no-op.

## Verification

Before committing a recipe change:

1. Run `python -m pytest tests/test_register_recipe.py -q`.
2. Parse `recipe-registry.json` as JSON.
3. Verify every registry `script` path exists.
4. Invoke the affected `apply.py` with `--file` and `--line` and inspect its JSON.
5. Keep recipe changes in the registry bucket matching the migration version.
