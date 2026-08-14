# Skill Registry — Java 1.5 → 1.6

This bucket contains recipes for the Java 1.5 to 1.6 migration. Recipes are invoked
as subprocesses through `jade-core-rule-dispatcher/recipe-registry.json`; nested
`SKILL.md` files are documentation, not agent-discoverable skills.

## How it works

1. Run `scripts/register_recipe.py` with `--bucket 1.5-to-1.6`
2. Review the generated or copied `SKILL.md` and `scripts/apply.py`
3. Verify the registry entry and recipe subprocess before committing

## Registry structure (once populated)

```
1.5-to-1.6/
├── raw-types-generics/
│   ├── SKILL.md           ← auto-generated, versioned
│   ├── eval_cases.json    ← cases this skill is benchmarked against
│   └── v1/SKILL.md        ← previous versions
├── enhanced-for-loops/
│   └── ...
└── README.md              ← this file
```

## Current status

Existing recipes are maintained in this bucket; new recipes must use the canonical
registration helper.
