# Skill Registry — Java 1.5 → 1.6

This directory is populated by the **Skill-Creator agent** as it processes JADE modules.
Hand-authored skills live in `.claude/skills/` — this registry holds auto-generated improvements.

## How it works

1. Tester agent runs `mvn clean compile` on `JADE-4.6.0-java1.6/` and collects failure patterns
2. Skill-Creator reads failure patterns → generates or improves a skill here
3. Skill is benchmarked against `benchmarks/1.5-to-1.6/eval_cases.json`
4. If pass rate improves, skill is committed here with a version bump

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

Registry is empty — migration PoC is using hand-authored skills in `.claude/skills/`.
Skill-Creator agent populates this directory as failures are encountered.
