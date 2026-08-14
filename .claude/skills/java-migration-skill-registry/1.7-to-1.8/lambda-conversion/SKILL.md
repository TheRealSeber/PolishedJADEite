---
name: jade-recipe-1.7-1.8-lambda-conversion
description: >-
  Converts anonymous SAM inner classes to Java 8 lambda expressions.
  Supports Runnable, Callable, ActionListener, Comparable, ItemListener,
  ChangeListener, and Thread/TimerTask extensions. Non-convertible
  patterns (multi-method interfaces, complex nesting) are deferred
  via JADE-MODERNIZATION-DEFERRED markers. Invoked by jade-core-rule-dispatcher.
arguments: [--file, --line]
---

# jade-recipe-1.7-1.8-lambda-conversion

Converts anonymous single-abstract-method (SAM) inner classes to Java 8 lambda
expressions. Handles:

- `new Runnable() { public void run() { ... } }`   -> `() -> { ... }`
- `new Thread() { public void run() { ... } }`     -> `new Thread(() -> { ... })`
- `new ActionListener() { public void actionPerformed(ActionEvent e) { ... } }`
                                                    -> `(ActionEvent e) -> { ... }`
- `new Callable<V>() { public V call() { ... } }`  -> `() -> { ... }`
- `new Comparable<T>() { public int compareTo(T o) { ... } }`
                                                    -> `(T o) -> { ... }`
- `new TimerTask() { public void run() { ... } }` -> `() -> { ... }`

Non-convertible patterns (multi-method interfaces like FocusListener, KeyListener,
MouseListener, WindowListener) are left as-is. Anonymous classes extending concrete
classes by name are deferred for manual review.

## Invocation

```
python .claude/skills/java-migration-skill-registry/1.7-to-1.8/lambda-conversion/scripts/apply.py --file <path> --line <N>
```

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success (FIXED or SKIPPED) |
| 2 | Failure (file not found, line out of range) |
| 3 | Environment error |

## Output

One JSON line to stdout:
```json
{"status": "FIXED|SKIPPED|FAILED", "changes": N, "warnings": [], "errors": [], "diff_summary": "..."}
```

## Transform behavior

1. Scans flagged line and surrounding lines for anonymous class pattern (`new ClassName() {`)
2. Identifies the interface/class name and checks against known SAM types
3. Extracts the method body using brace-matching
4. If convertible: generates lambda expression, writes via atomic rename
5. If not convertible: rewrites flag to `// JADE-MODERNIZATION-DEFERRED:LAMBDA_CONVERSION`
6. Removes the original `// JADE-FLAG:LAMBDA_CONVERSION` marker on success
