---
name: java-migration-skill-registry
description: >-
  Registry of auto-generated migration skills produced by the Skill-Creator agent.
  Each subdirectory holds versioned skills for a specific version jump, benchmarked
  against eval_cases.json before acceptance. Not a command — background knowledge only.
user-invocable: false
disable-model-invocation: true
---

# Java Migration Skill Registry

Auto-generated skills live here, organized by version jump.
Hand-authored skills live in sibling directories under `.claude/skills/`.

## Structure

```
java-migration-skill-registry/
└── 1.5-to-1.6/
    ├── <skill-name>/
    │   ├── SKILL.md          ← generated, versioned
    │   ├── eval_cases.json   ← cases this skill is benchmarked against
    │   └── v1/SKILL.md       ← previous versions
    └── README.md
```

## How skills enter this registry

1. Tester agent collects failure patterns from `JADE-4.6.0-java1.6/`
2. Skill-Creator generates or improves a skill for the pattern
3. Skill is benchmarked against `benchmarks/1.5-to-1.6/eval_cases.json`
4. Pass rate must exceed the previous version's rate to be committed here

## Current status

Registry is empty — PoC uses hand-authored skills in `.claude/skills/`.
