---
name: jade-recipe-java1.5-raw-types
description: >-
  Java 1.5→1.6 recipe: adds generic type parameters to raw collection
  instantiations. Infers type from .add()/.put()/.get() calls. Removes
  safe casts. Invoked by jade-core-rule-dispatcher, never standalone.
when_to_use: >-
  Invoked automatically by jade-core-rule-dispatcher when rule_id is
  RAW_TYPES. Do not invoke independently.
arguments: [file_path, line]
argument-hint: null
---

# jade-recipe-java1.5-raw-types

## Objective

Transform raw Java collection instantiations to parameterized generics
for Java 1.5 → 1.6 migration. This recipe runs on ONE file at ONE flagged
line.

## Transform

- `new Vector()` → `new Vector<String>()` (type inferred from `.add()` calls)
- `new ArrayList()` → `new ArrayList<Object>()` (when type ambiguous)
- `new HashMap()` → `new HashMap<KeyType,ValueType>()` (from `.put()` calls)
- Safe casts removed: `(String) list.get(i)` → `list.get(i)`
- No diamond operator (`<>`) — target is Java 1.6

## Contract

```
python apply.py --file <path> --line <num>
```

Prints single JSON line to stdout. Exit 0 = success, 2 = failure.
