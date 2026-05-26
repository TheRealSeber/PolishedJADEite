# Spec: Build Fixer — Scoped `<javac>` Attribute Fix

**Date:** 2026-05-25  
**Status:** Draft  
**Scope:** `.claude/skills/jade-core-build-fixer/scripts/build_audit.py`

## Problem

`apply_ant_fixes()` uses **unanchored global regex** to replace `source=` and `target=` attribute values anywhere in Ant `build.xml`. This corrupts attributes on non-`<javac>` elements:

### Bug manifestation (JADE 1.6→1.7 migration)

| Element | Attribute | Before | After (BUG) |
|---------|-----------|--------|--------------|
| `<javac>` | `source` | `1.5` | `1.7` ✓ |
| `<javac>` | `target` | `1.5` | `1.7` ✓ |
| `<javacc>` | `target` | `src/jade/lang/acl/ACLParser.jj` | `1.7` ✗ |
| `<javacc>` | `target` | `src/jade/content/lang/sl/SLParser.jj` | `1.7` ✗ |
| `<javacc>` | `target` | `src/jade/content/lang/sl/ExtendedSLParser.jj` | `1.7` ✗ |

The `<javacc target="...">` attribute specifies a **grammar file path**, not a Java version. Replacing it with `1.7` silently breaks javacc builds.

### Affected regex (line 511 and 525)

```python
# UNSAFE — matches ANY target/source attribute in entire XML file
r'(\bsource\s*=\s*["\'])([^"\']*?)(["\'])'
r'(\btarget\s*=\s*["\'])([^"\']*?)(["\'])'
```

## Design

### Change 1: Scope regex to `<javac>` elements

Anchor both patterns to only match inside `<javac>` opening tags:

```python
# OLD
r'(\bsource\s*=\s*["\'])([^"\']*?)(["\'])'

# NEW
r'(<javac\b[^>]*?\bsource\s*=\s*["\'])([^"\']*?)(["\'])'
```

Same for `target`. The `<javac\b[^>]*?` prefix:
- `\b` — word boundary, prevents matching `<javacc`
- `[^>]*?` — lazy match of any characters except `>`, keeps match inside the opening tag
- Ensures `source`/`target` matched are attributes of `<javac>` only

Replacement stays identical (`\g<1>{target_version}\g<3>`) since group 1 now captures the `<javac...source="` prefix.

### Change 2: Post-fix validation

Add `validate_ant_fixes(build_path, original_text, fixed_text) → List[str]` that:

1. Parses original and fixed XML with `xml.etree.ElementTree`
2. For every `<javac>` element: verifies `source`/`target` are present and match target version OR were already correct  
3. For every `<javacc>` element: verifies `target` attribute (if present) was **not** changed to equal the `target_version` value (e.g. `1.7`). Compares the original value from the pre-fix XML parse against the post-fix value.
4. For every `<antcall>` element: verifies `target` attribute was **not** changed to equal the `target_version` value
5. Returns list of warning strings (empty = clean)

Called after `apply_ant_fixes()` returns. Warnings are logged to stderr and recorded in the audit JSON under a new `fix_validation_warnings` field.

### Change 3: Hook validation into audit flow

After `apply_ant_fixes()` returns (line 883 in current code), call `validate_ant_fixes()`. If warnings exist:
- Print them to stderr
- Record them in `03-build-audit.json` as `fix_validation_warnings: [...]`
- Do NOT revert — the javac fixes are correct; only non-javac collisions are suspicious

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| `<javac source="1.5" target="1.5"/>` | Both updated to `1.7` ✓ |
| `<javac source="1.7"/>` (already correct) | Regex doesn't match (value already 1.7), no-op |
| `<javacc target="grammar.jj"/>` | Regex doesn't match (anchored to `<javac\b`), preserved ✓ |
| `<antcall target="build-jar"/>` | Regex doesn't match, preserved ✓ |
| `<property name="target" value="x"/>` | Regex matches `target=` in `<property>` but NOT anchored to `<javac` — NOT matched ✓ |
| No `<javac>` elements in XML | Regex returns 0 substitutions, no-op |
| build.xml uses single quotes (`source='1.5'`) | Regex handles both `"` and `'` via `["\']` |

## Non-Goals

- NOT fixing the Docker image registry (java-11 → maven image for Ant projects) — separate issue
- NOT adding `ant lib` jar-building to the build fixer — separate issue
- NOT reducing orchestrator AWAITING_AGENT pauses — separate issue

## Testing

### Unit fixtures
1. `build_javac_only.xml` — single `<javac source="1.5" target="1.5"/>` → verify both updated
2. `build_mixed_javac_javacc.xml` — `<javac>` + `<javacc target="grammar.jj"/>` → verify javacc target preserved
3. `build_with_antcall.xml` — `<antcall target="deploy"/>` → verify antcall target preserved

### Integration
Run against JADE-4.6.0 `src/jade/build.xml` with target 1.7. Verify:
- `<javac source="1.7" target="1.7"/>` — correct
- `<javacc target="src/jade/lang/acl/ACLParser.jj"/>` — preserved, NOT changed to `1.7`
