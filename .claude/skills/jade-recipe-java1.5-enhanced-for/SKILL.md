---
name: jade-recipe-java1.5-enhanced-for
description: >-
  Java 1.5→1.6 recipe: converts safe indexed for-loops to enhanced-for
  loops. Marks unsafe loops with // MIGRATION-SKIP comments. Handles both
  collection (.get) and array ([]) access patterns. Invoked by
  jade-core-rule-dispatcher, never standalone.
when_to_use: >-
  Invoked automatically by jade-core-rule-dispatcher when rule_id is
  ENHANCED_FOR. Do not invoke independently.
arguments: [file_path, line]
argument-hint: null
---

# jade-recipe-java1.5-enhanced-for

## Objective

Convert safe indexed `for` loops to enhanced `for` for Java 1.5 → 1.6
migration. This recipe runs on ONE file at ONE flagged line.

## Transform

- `for (int i = 0; i < list.size(); i++)` → `for (String item : list)`
- `for (int i = 0; i < arr.length; i++)` → `for (String item : arr)`
- Array access `arr[i]` replaced with loop variable in body
- `.get(i)` calls replaced with loop variable in body

## Safety

Unsafe loops are left unchanged with a `// MIGRATION-SKIP: reason` comment:
- `.remove(i)`, `.set(i)`, `.add(i)` inside loop
- Index variable used after the loop body
- Index used for parallel collection iteration
- Backwards loop

## Contract

```
python apply.py --file <path> --line <num>
```

Prints single JSON line to stdout. Exit 0 = success, 2 = failure.
