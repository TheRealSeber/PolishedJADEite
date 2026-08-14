---
name: java-migration-skill-registry
description: >-
  Canonical registry for version-specific JADE migration recipes. Recipes are nested
  below migration buckets and are invoked only through recipe-registry.json. Not a
  command — background knowledge only.
user-invocable: false
disable-model-invocation: true
---

# Java Migration Skill Registry

Recipes live here, organized by version jump. Nested recipes are not agent skills;
the dispatcher invokes their `scripts/apply.py` entry point.

## Structure

```
java-migration-skill-registry/
├── 1.5-to-1.6/
├── 1.7/
├── 1.7-to-1.8/
├── shared/
└── scripts/register_recipe.py
```

## Registering a recipe

Use the deterministic scaffold and registry updater:

```text
python .claude/skills/java-migration-skill-registry/scripts/register_recipe.py \
  --recipe-name jade-recipe-example --bucket 1.7 --rule-id EXAMPLE_RULE \
  --description "Apply the example transform"
```

The helper validates safe path segments, refuses duplicates unless `--force` is
given, creates `SKILL.md` and `scripts/apply.py`, and atomically updates the
dispatcher registry. Use `--source-dir` to copy an existing recipe's two files.

## Current status

The registry contains the migrated hand-authored recipes and remains the source of
truth for dispatcher script paths.
