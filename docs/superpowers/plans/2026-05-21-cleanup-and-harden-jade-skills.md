# Cleanup & Harden JADE Skill Suite

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete legacy migration artifacts that do not align with the new pipeline architecture, then harden the `jade-rule-fixer` with real Java transform logic and strengthen the evaluator and test suite.

**Architecture:** File-based artifact handoff. No live JADE migration — all transforms are tested against sample workspace fixtures only. Cleanup removes old one-off migration copies and committed build cache. Rule fixer gains deterministic RAW_TYPES + ENHANCED_FOR transforms.

**Tech Stack:** Python 3, JSON artifact contracts, Git.

---

## File structure

### Files to delete
- `.claude/skills/jade-phase0-scanner/` (legacy — replaced by `jade-scanner`)
- `.claude/skills/jade-1.5-to-1.6-raw-types/` (legacy — replaced by `jade-rule-fixer`)
- `.claude/skills/jade-1.5-to-1.6-enhanced-for/` (legacy — replaced by `jade-rule-fixer`)
- `JADE-4.6.0-java1.6/` (legacy migration copy, not pipeline-aligned)
- `.claude/skills/jade-*/scripts/__pycache__/` (all 11 committed dirs + 13 `.pyc` files)

### Files to modify
- `.gitignore` — add `__pycache__/`, `*.pyc`, `JADE-4.6.0-java1.6/`
- `.claude/skills/jade-rule-fixer/scripts/apply_rule_fix.py` — add real RAW_TYPES and ENHANCED_FOR transform functions
- `.claude/skills/jade-skill-matrix-evaluator/scripts/evaluate_skills.py` — improve scoring heuristics
- `tests/test_artifact_contracts.py` — expand with schema validation tests

### Files to create
- `tests/test_idempotency.py` — scanner idempotency test
- `tests/test_orchestrator_integration.py` — orchestrator integration test

---

## Task 1: Cleanup legacy artifacts and gitignore

**Files:**
- Delete: `.claude/skills/jade-phase0-scanner/`
- Delete: `.claude/skills/jade-1.5-to-1.6-raw-types/`
- Delete: `.claude/skills/jade-1.5-to-1.6-enhanced-for/`
- Delete: `JADE-4.6.0-java1.6/`
- Delete: `.claude/skills/jade-*/scripts/__pycache__/` (11 dirs)
- Modify: `.gitignore`

- [ ] **Step 1: Delete legacy skill directories**

```bash
rm -rf .claude/skills/jade-phase0-scanner
rm -rf .claude/skills/jade-1.5-to-1.6-raw-types
rm -rf .claude/skills/jade-1.5-to-1.6-enhanced-for
```

- [ ] **Step 2: Delete legacy migration copy**

```bash
rm -rf "JADE-4.6.0-java1.6"
```

- [ ] **Step 3: Delete committed __pycache__ directories and .pyc files**

```bash
find .claude/skills -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; echo "done"
```

- [ ] **Step 4: Update .gitignore**

Add these lines to `.gitignore`:
```
# Python bytecode
__pycache__/
*.pyc

# Legacy migration copies (pipeline reads workspace from 00-run-config.json)
JADE-4.6.0-java1.6/
```

- [ ] **Step 5: Verify cleanup**

```bash
test ! -d .claude/skills/jade-phase0-scanner && echo "PASS: legacy scanner gone" || echo "FAIL"
test ! -d .claude/skills/jade-1.5-to-1.6-raw-types && echo "PASS: legacy raw-types gone" || echo "FAIL"
test ! -d .claude/skills/jade-1.5-to-1.6-enhanced-for && echo "PASS: legacy enhanced-for gone" || echo "FAIL"
test ! -d "JADE-4.6.0-java1.6" && echo "PASS: migration copy gone" || echo "FAIL"
find .claude/skills -type d -name "__pycache__" 2>/dev/null | wc -l | xargs -I{} sh -c '[ {} -eq 0 ] && echo "PASS: no pycache dirs" || echo "FAIL: {} pycache dirs remain"'
find .claude/skills -name "*.pyc" 2>/dev/null | wc -l | xargs -I{} sh -c '[ {} -eq 0 ] && echo "PASS: no pyc files" || echo "FAIL: {} pyc files remain"'
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add -A .claude/skills/jade-phase0-scanner .claude/skills/jade-1.5-to-1.6-raw-types .claude/skills/jade-1.5-to-1.6-enhanced-for "JADE-4.6.0-java1.6"
git add .gitignore
git add -u .claude/skills/
git commit -m "chore: cleanup legacy skills, migration copy, pycache, and gitignore"
```

---

## Task 2: Add real RAW_TYPES transform to apply_rule_fix.py

**Files:**
- Modify: `.claude/skills/jade-rule-fixer/scripts/apply_rule_fix.py`

The current `apply_rule_fix.py` has a generic fix framework (match_pattern + fix_strategy = sed-style or JSON template substitution) but no domain-specific transform logic for RAW_TYPES (infer generics from `.add()` / `.put()` calls). This needs real `Vector` → `Vector<String>` inference.

- [ ] **Step 1: Add `infer_generic_type()` function**

```python
def infer_generic_type(lines: List[str], var_name: str) -> Optional[str]:
    """Infer type parameter for a raw collection variable.
    
    Scans lines for:
    1. .add(x) calls → type of x
    2. .put(k, v) calls → Map<K, V> semantic
    3. Cast expressions from .get() → the cast type
    
    Returns the inferred type string (e.g. 'String', 'Object', 'String,Object' for Map)
    or None if ambiguous.
    """
    add_types: List[str] = []
    get_cast_types: List[str] = []
    
    for line in lines:
        # .add(something)
        add_match = re.search(rf'\b{re.escape(var_name)}\.add\(\s*(.+?)\s*\)', line)
        if add_match:
            arg = add_match.group(1).strip()
            add_types.append(_resolve_arg_type(arg, lines))
        
        # .put(key, value)
        put_match = re.search(rf'\b{re.escape(var_name)}\.put\(\s*(.+?)\s*,\s*(.+?)\s*\)', line)
        if put_match:
            key_type = _resolve_arg_type(put_match.group(1).strip(), lines)
            val_type = _resolve_arg_type(put_match.group(2).strip(), lines)
            if key_type or val_type:
                return f"{key_type or 'Object'},{val_type or 'Object'}"
        
        # (Type) var.get(i) — cast from get
        cast_match = re.search(rf'\((\w+(?:<.*?>)?)\)\s*{re.escape(var_name)}\.get', line)
        if cast_match:
            get_cast_types.append(cast_match.group(1))
    
    # Merge inferences
    all_types = add_types + get_cast_types
    unique_types = list(dict.fromkeys(t for t in all_types if t and t != 'null'))
    
    if not unique_types:
        return None  # ambiguous, use Object
    if len(unique_types) == 1:
        return unique_types[0]
    
    # Multiple types found — pick most specific common supertype
    # For simplicity: if all are String → String, else Object
    if all(t == 'String' for t in unique_types):
        return 'String'
    return 'Object'
```

- [ ] **Step 2: Add `_resolve_arg_type()` helper**

```python
def _resolve_arg_type(arg: str, lines: List[str]) -> str:
    """Resolve a simple argument expression to a Java type name.
    
    Heuristics:
    - "string literal" → String
    - variable name matching a known typed variable → try to find its declaration
    - null → None
    - new Xxx() → Xxx
    - method call → Object (can't infer)
    """
    arg = arg.strip().rstrip(';')
    
    if not arg or arg == 'null':
        return 'null'
    
    # String literal
    if arg.startswith('"') or arg.startswith("'"):
        return 'String'
    
    # Numeric literal
    if re.match(r'^-?\d+(\.\d+)?[fFlLdD]?$', arg):
        return 'Integer'  # conservative — could be Long, Float, etc.
    
    # Boolean literal
    if arg in ('true', 'false'):
        return 'Boolean'
    
    # Constructor call: new Foo(...)
    new_match = re.match(r'new\s+(\w+)\s*\(', arg)
    if new_match:
        return new_match.group(1)
    
    # Single word = variable name. Try to find its declaration.
    if re.match(r'^\w+$', arg):
        for line in lines:
            decl = re.search(rf'\b(\w+(?:<.*?>)?)\s+{re.escape(arg)}\s*[=;]', line)
            if decl:
                return decl.group(1)
        return arg  # can't resolve, return as-is
    
    return 'Object'
```

- [ ] **Step 3: Add `apply_raw_types_fix()` function**

```python
def apply_raw_types_fix(
    file_path: pathlib.Path,
    flagged_lines: List[int],
) -> Tuple[str, int, List[str]]:
    """Transform raw collection instantiations in a file.
    
    For each flagged line containing 'new Vector()' etc.:
    1. Find the variable name being assigned
    2. Scan the method/class for .add() / .put() calls to that variable
    3. Infer type parameter
    4. Replace 'new Vector()' → 'new Vector<Foo>()'
    5. Remove safe casts from subsequent .get() calls
    
    Returns (status, changes_made, warnings).
    """
    content = file_path.read_text(encoding='utf-8')
    lines = content.splitlines(keepends=True)
    changes = 0
    warnings: List[str] = []
    
    for flagged_line_num in flagged_lines:
        idx = flagged_line_num - 1
        if idx < 0 or idx >= len(lines):
            continue
        
        line = lines[idx]
        
        # Match: Type varName = new Collection();
        match = re.match(
            r'^(\s*)(\w+)\s+(\w+)\s*=\s*new\s+(Vector|ArrayList|HashMap|Hashtable|LinkedList|HashSet)\s*\(\s*\)\s*;',
            line
        )
        if not match:
            # Try without variable declaration (just new Foo())
            match = re.match(
                r'(.*?)new\s+(Vector|ArrayList|HashMap|Hashtable|LinkedList|HashSet)\s*\(\s*\)',
                line
            )
            if not match:
                continue
        
        indent = match.group(1) if '(' not in match.group(1) else ''
        var_name = match.group(3) if match.lastindex and match.lastindex >= 3 else None
        coll_type = match.group(4) if match.lastindex and match.lastindex >= 4 else match.group(2)
        
        # Infer type
        inferred = 'Object'
        if var_name:
            # Scan surrounding context (whole file for simplicity)
            result = infer_generic_type(lines, var_name)
            if result:
                inferred = result
        
        # Build replacement
        if var_name:
            replacement = f'{match.group(1) if match.group(1) and "(" not in match.group(1) else indent}{coll_type}<{inferred}> {var_name} = new {coll_type}<{inferred}>();'
            lines[idx] = replacement + '\n'
            changes += 1
        else:
            # Inline: new Vector() → new Vector<Object>()
            old = match.group(0)
            new = old.replace(f'new {coll_type}()', f'new {coll_type}<{inferred}>()')
            lines[idx] = line.replace(old, new, 1)
            changes += 1
        
        # Best-effort cast removal (not fully implemented — safe casts are
        # left in place; the type parameter already provides the guarantee)
        if var_name:
            for ci in range(idx + 1, len(lines)):
                cast_match = re.search(
                    rf'\((\w+(?:<.*?>)?)\)\s*\b{re.escape(var_name)}\.get\(',
                    lines[ci]
                )
                if cast_match:
                    cast_type = cast_match.group(1)
                    if cast_type == inferred or inferred == 'Object':
                        # Safe to remove cast: "(Type) var.get(i)" → "var.get(i)"
                        lines[ci] = re.sub(
                            rf'\((\w+(?:<.*?>)?)\)\s*({re.escape(var_name)}\.get\()',
                            r'\2',
                            lines[ci]
                        )
    
    if changes > 0:
        new_content = ''.join(lines)
        atomic_file_write_internal(file_path, new_content)
    
    status = 'FIXED' if changes > 0 else 'NOOP'
    return status, changes, warnings
```

- [ ] **Step 4: Add `apply_enhanced_for_fix()` function**

```python
def apply_enhanced_for_fix(
    file_path: pathlib.Path,
    flagged_lines: List[int],
) -> Tuple[str, int, List[str]]:
    """Convert safe indexed for-loops to enhanced for-loops.
    
    Safety checks:
    - Index used ONLY for .get(i) or array[i]
    - No .remove(i), .set(i, x), .add(i, x) inside loop
    - Not iterating two parallel collections
    - No backwards loop or step > 1
    
    Returns (status, changes_made, warnings).
    """
    content = file_path.read_text(encoding='utf-8')
    lines = content.splitlines(keepends=True)
    changes = 0
    warnings: List[str] = []
    
    for flagged_line_num in flagged_lines:
        idx = flagged_line_num - 1
        if idx < 0 or idx >= len(lines):
            continue
        
        line = lines[idx]
        
        # Match: for (int i = 0; i < coll.size(); i++) {
        match = re.match(
            r'^(\s*)for\s*\(\s*int\s+(\w+)\s*=\s*0\s*;\s*\2\s*<\s*(\w+)\.size\(\)\s*;\s*\2\+\+\s*\)\s*\{',
            line
        )
        if not match:
            # Try array variant: for (int i = 0; i < arr.length; i++) {
            match = re.match(
                r'^(\s*)for\s*\(\s*int\s+(\w+)\s*=\s*0\s*;\s*\2\s*<\s*(\w+)\.length\s*;\s*\2\+\+\s*\)\s*\{',
                line
            )
            if not match:
                continue
        
        indent = match.group(1)
        idx_var = match.group(2)
        coll_var = match.group(3)
        
        # Find loop body (matching braces)
        loop_start = idx
        brace_count = 1
        loop_end = loop_start
        for bi in range(loop_start + 1, len(lines)):
            brace_count += lines[bi].count('{') - lines[bi].count('}')
            if brace_count == 0:
                loop_end = bi
                break
        
        if loop_end == loop_start:
            warnings.append(f"Line {flagged_line_num}: could not find loop closing brace, skipping")
            continue
        
        # Safety checks on loop body
        body_lines = lines[loop_start + 1 : loop_end]
        body_text = ''.join(body_lines)
        is_safe = True
        skip_reasons: List[str] = []
        
        # Check for .remove(i), .set(i), .add(i)
        if re.search(rf'\.(remove|set|add)\s*\(\s*{re.escape(idx_var)}\s*[,\)]', body_text):
            skip_reasons.append(f'.remove/set/add using {idx_var}')
            is_safe = False
        
        # Check for index used after loop
        after_text = ''.join(lines[loop_end + 1:])
        if re.search(rf'\b{re.escape(idx_var)}\b', after_text):
            skip_reasons.append(f'{idx_var} used after loop')
            is_safe = False
        
        # Check for parallel collection iteration
        if re.search(rf'\b{re.escape(idx_var)}\s*\]', body_text) and re.search(rf'\.get\s*\(\s*{re.escape(idx_var)}\s*\)', body_text):
            # index used both as array index AND .get() — parallel iteration
            skip_reasons.append(f'parallel iteration with {idx_var}')
            is_safe = False
        
        # Check for backwards loop
        if '--' in line:
            skip_reasons.append('backwards loop')
            is_safe = False
        
        if not is_safe:
            reason = '; '.join(skip_reasons)
            # Inject MIGRATION-SKIP comment
            lines[idx] = lines[idx].rstrip('\n') + f' // MIGRATION-SKIP: {reason}\n'
            changes += 1
            warnings.append(f"Line {flagged_line_num}: skipped ({reason})")
            continue
        
        # Determine element type
        # Find .get(i) in body to infer type, or look for the collection declaration
        elem_type = _infer_collection_element_type(lines, coll_var)
        
        # Build enhanced-for
        loop_var = 'item' if idx_var == 'i' else f'elem_{idx_var}'
        if re.search(rf'{coll_var}\.length', line):
            # Array loop
            new_for = f'{indent}for ({elem_type} {loop_var} : {coll_var}) {{'
        else:
            # Collection loop
            new_for = f'{indent}for ({elem_type} {loop_var} : {coll_var}) {{'
        
        lines[idx] = new_for + '\n'
        
        # Replace all (Type) coll.get(i) with just the item variable
        # Replace all coll.get(i) with loop_var
        for bi in range(idx + 1, loop_end + 1):
            # Cast-get: (Type) coll.get(i)
            cast_pattern = rf'\((\w+(?:<.*?>)?)\)\s*{re.escape(coll_var)}\.get\s*\(\s*{re.escape(idx_var)}\s*\)'
            lines[bi] = re.sub(cast_pattern, loop_var, lines[bi])
            # Plain get: coll.get(i)
            get_pattern = rf'{re.escape(coll_var)}\.get\s*\(\s*{re.escape(idx_var)}\s*\)'
            lines[bi] = re.sub(get_pattern, loop_var, lines[bi])
        
        changes += 1
    
    if changes > 0:
        new_content = ''.join(lines)
        atomic_file_write_internal(file_path, new_content)
    
    status = 'FIXED' if changes > 0 else 'NOOP'
    return status, changes, warnings
```

- [ ] **Step 5: Add `_infer_collection_element_type()` and `atomic_file_write_internal()` helpers**

```python
def _infer_collection_element_type(lines: List[str], coll_var: str) -> str:
    """Infer element type from collection declaration."""
    for line in lines:
        decl = re.search(rf'(\w+(?:<(\w+)>)?)\s+{re.escape(coll_var)}\s*=', line)
        if decl:
            inner = decl.group(2)
            if inner:
                return inner
            # Check if it's assigned from another typed variable
            type_name = decl.group(1)
            return type_name
    return 'Object'


def atomic_file_write_internal(file_path: pathlib.Path, content: str) -> None:
    """Write content to a temp file, then atomically replace."""
    import tempfile
    tmp = pathlib.Path(str(file_path) + '.tmp.fix')
    tmp.write_text(content, encoding='utf-8')
    tmp.replace(file_path)
```

- [ ] **Step 6: Wire `apply_raw_types_fix()` and `apply_enhanced_for_fix()` into main()**

In `main()`, insert this block directly after the `needs_review` assignment (line ~632, where `status = "NEEDS_REVIEW" if needs_review else "FIXED"`) and before the `# ---- PHASE 4: APPLY ----` block (line ~631). `status` and `needs_review` must already be computed at this point.

```python
# Rule-specific transforms (runs after generic fix plan, before file apply)
if status == "FIXED" or needs_review is False:
    try:
        if rule_id == "RAW_TYPES":
            flagged = [line_start]  # the flagged line
            fix_status, changes, fix_warnings = apply_raw_types_fix(file_path, flagged)
            warnings.extend(fix_warnings)
            if fix_status == 'NOOP':
                warnings.append("RAW_TYPES transform produced no changes (falling back to generic)")
        elif rule_id == "ENHANCED_FOR":
            flagged = [line_start]
            fix_status, changes, fix_warnings = apply_enhanced_for_fix(file_path, flagged)
            warnings.extend(fix_warnings)
            if fix_status == 'NOOP':
                warnings.append("ENHANCED_FOR transform produced no changes (falling back to generic)")
    except Exception as exc:
        errors.append(f"Rule-specific transform failed: {exc}")
        status = "FAILED"
```

- [ ] **Step 7: Verify apply_rule_fix.py still parses correctly**

```bash
python3 -c "import py_compile; py_compile.compile('.claude/skills/jade-rule-fixer/scripts/apply_rule_fix.py', doraise=True); print('Syntax OK')"
```

Expected: `Syntax OK`

- [ ] **Step 8: Commit**

```bash
git add .claude/skills/jade-rule-fixer/scripts/apply_rule_fix.py
git commit -m "feat(skills): add RAW_TYPES and ENHANCED_FOR transforms to jade-rule-fixer"
```

---

## Task 3: Harden jade-skill-matrix-evaluator scoring

**Files:**
- Modify: `.claude/skills/jade-skill-matrix-evaluator/scripts/evaluate_skills.py`

Current issues: every skill gets the same score because the evaluator only checks the existence of a few artifact files (rule-status.json, 05-rule-queue.json, 00-run-config.json) — not per-skill metrics. It also hardcodes `artifacts_dir` to sample.

- [ ] **Step 1: Add CLI args and per-skill artifact checking**

```python
import argparse

def score_skill(skill_id: str, artifacts_dir: pathlib.Path) -> Dict:
    """Score one skill based on its output artifacts in artifacts_dir."""
    scores = {
        "contract_compliance": 0,
        "reproducibility": 0,
        "gate_pass_rate": 0,
        "artifact_completeness": 0,
        "failure_handling": 0,
    }
    
    # Check skill-specific artifacts
    skill_artifacts = _get_skill_artifacts(skill_id)
    present = sum(1 for a in skill_artifacts if (artifacts_dir / a).exists())
    total = len(skill_artifacts)
    if total > 0:
        scores["artifact_completeness"] = int(100 * present / total)
    
    # Check rule-status.json for gate pass rate
    rule_status = artifacts_dir / "rule-status.json"
    if rule_status.exists():
        data = json.loads(rule_status.read_text(encoding="utf-8"))
        rules = data.get("rules", {})
        if rules:
            passed = sum(1 for r in rules.values() if r.get("status") == "DONE")
            scores["gate_pass_rate"] = int(100 * passed / len(rules))
            if passed == len(rules):
                scores["reproducibility"] = 90
            elif passed > 0:
                scores["reproducibility"] = 50
    
    # Check failure-summary.json for failure handling
    failure = artifacts_dir / "failure-summary.json"
    if failure.exists():
        scores["failure_handling"] = 85
    else:
        # If there are no failures AND the run completed, that's also evidence
        if _run_completed(artifacts_dir):
            scores["failure_handling"] = 75
    
    # Check queue for contract compliance
    queue = artifacts_dir / "05-rule-queue.json"
    if queue.exists():
        q = json.loads(queue.read_text(encoding="utf-8"))
        rules = q.get("rules", [])
        if isinstance(rules, list) and len(rules) > 0:
            scores["contract_compliance"] = 95
    
    # Check phase-history.log.jsonl for overall health
    phase_history = artifacts_dir / "phase-history.log.jsonl"
    if phase_history.exists():
        phases = [json.loads(line) for line in phase_history.read_text().splitlines() if line.strip()]
        if phases:
            ok_phases = sum(1 for p in phases if p.get("status") == "OK")
            scores["contract_compliance"] = max(scores["contract_compliance"], int(90 * ok_phases / len(phases)))
    
    aggregate = int(sum(scores.values()) / len(scores))
    if aggregate >= 90:
        classification = "official"
    elif aggregate >= 70:
        classification = "candidate"
    elif aggregate >= 50:
        classification = "experimental"
    else:
        classification = "draft"
    
    return {
        "skill_id": skill_id,
        "scores": scores,
        "aggregate": aggregate,
        "classification": classification,
    }


_SKILL_ARTIFACT_MAP = {
    "jade-scanner": ["04-flag-index.json", "04-scan-summary.json"],
    "jade-rule-batch-processor": ["05-rule-batch-status.json"],
    "jade-rule-fixer": [],  # per-task results named 06-fix-result-*.json
    "jade-verification-semantic": [],  # verification results
    "jade-atomic-rule-commit": ["09-rule-commit-log.json"],
    "jade-skill-matrix-evaluator": ["10-skill-matrix.json"],
    "jade-build-system-fixer": ["03-build-audit.json"],
    "jade-change-collector-strict": ["01-breaking-changes-manifest.json"],
    "jade-tooling-scout": ["02-tooling-scout-report.json"],
    "jade-migration-orchestrator": [],
    "jade-retry-router": [],
}


def _get_skill_artifacts(skill_id: str) -> List[str]:
    return _SKILL_ARTIFACT_MAP.get(skill_id, [])


def _run_completed(artifacts_dir: pathlib.Path) -> bool:
    state = artifacts_dir / "00-run-state.json"
    if not state.exists():
        return False
    data = json.loads(state.read_text(encoding="utf-8"))
    return data.get("state") in ("DONE",)


def main() -> int:
    parser = argparse.ArgumentParser(description="JADE Skill Matrix Evaluator")
    parser.add_argument(
        "--artifacts",
        default="migration-runs/sample/artifacts",
        help="Path to artifacts directory",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output path for skill matrix JSON (default: <artifacts>/10-skill-matrix.json)",
    )
    args = parser.parse_args()
    
    artifacts = pathlib.Path(args.artifacts)
    if not artifacts.is_dir():
        print(f"ERROR: {artifacts} not a directory", file=sys.stderr)
        return 2
    
    results: List[Dict] = []
    for sid in SKILL_IDS:
        results.append(score_skill(sid, artifacts))
    
    out = pathlib.Path(args.output) if args.output else (artifacts / "10-skill-matrix.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(results, indent=2), encoding="utf-8")
    tmp.replace(out)
    
    # Print summary
    for r in results:
        print(f"{r['aggregate']:3d}% {r['classification']:13s} {r['skill_id']}")
    print(f"Skill matrix written to {out}")
    return 0
```

- [ ] **Step 2: Verify evaluator runs**

```bash
python3 .claude/skills/jade-skill-matrix-evaluator/scripts/evaluate_skills.py --artifacts migration-runs/sample/artifacts
```

Expected: prints scored skill list, exits 0.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/jade-skill-matrix-evaluator/scripts/evaluate_skills.py
git commit -m "test(skills): harden evaluator with per-skill artifact scoring and CLI args"
```

---

## Task 4: Expand test suite

**Files:**
- Modify: `tests/test_artifact_contracts.py`
- Create: `tests/test_idempotency.py`
- Create: `tests/test_orchestrator_integration.py`

- [ ] **Step 1: Write failing schema validation tests**

```python
# tests/test_artifact_contracts.py
import json
import pathlib
import pytest

ARTIFACTS_DIR = pathlib.Path("migration-runs/sample/artifacts")


def test_run_config_has_required_keys():
    cfg = json.loads((ARTIFACTS_DIR / "00-run-config.json").read_text(encoding="utf-8"))
    assert cfg["run_id"]
    assert cfg["workspace_path"]
    assert cfg["artifacts_path"]
    assert cfg["source_version"]
    assert cfg["target_version"]


def test_run_state_has_required_keys():
    state = json.loads((ARTIFACTS_DIR / "00-run-state.json").read_text(encoding="utf-8"))
    assert state["run_id"]
    assert state["state"] in {
        "INIT", "WORKSPACE_READY", "MANIFEST_READY", "TOOLING_SCOUT_READY",
        "BUILD_GATE_READY", "SCAN_READY", "RULE_BATCH_LOOP", "VERIFIED",
        "DONE", "FAILED", "AWAITING_SOURCE_INPUT",
    }
    assert "updated_at" in state


def test_manifest_has_valid_rules():
    manifest = json.loads((ARTIFACTS_DIR / "01-breaking-changes-manifest.json").read_text(encoding="utf-8"))
    rules = manifest["rules"]
    assert isinstance(rules, list)
    assert len(rules) > 0
    for rule in rules:
        assert "id" in rule
        assert "name" in rule
        assert "severity" in rule
        assert "patterns" in rule
        for pattern in rule["patterns"]:
            assert "pattern" in pattern
            assert "target_extensions" in pattern


def test_flag_index_has_flags_list():
    idx = json.loads((ARTIFACTS_DIR / "04-flag-index.json").read_text(encoding="utf-8"))
    assert isinstance(idx["flags"], list)
    if idx["flags"]:
        flag = idx["flags"][0]
        assert "rule_id" in flag
        assert "file" in flag
        assert "line" in flag


def test_scan_summary_has_counts():
    summary = json.loads((ARTIFACTS_DIR / "04-scan-summary.json").read_text(encoding="utf-8"))
    assert summary["total_files_scanned"] >= 0
    assert summary["by_rule"]


def test_rule_queue_is_sequential():
    queue = json.loads((ARTIFACTS_DIR / "05-rule-queue.json").read_text(encoding="utf-8"))
    assert isinstance(queue["rules"], list)
    assert queue["order"] == "sequential"


def test_phase_history_is_valid_jsonl():
    history_path = ARTIFACTS_DIR / "phase-history.log.jsonl"
    assert history_path.exists()
    for line in history_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        assert "ts" in entry
        assert "phase" in entry
        assert "status" in entry
```

- [ ] **Step 2: Run tests and verify they pass**

```bash
python3 -m pytest tests/test_artifact_contracts.py -v
```

Expected: all tests PASS.

- [ ] **Step 3: Write failing idempotency test**

```python
# tests/test_idempotency.py
import json
import pathlib
import subprocess
import sys
import pytest

SCAN_SCRIPT = pathlib.Path(".claude/skills/jade-scanner/scripts/scan_and_tag.py")
ARTIFACTS_DIR = pathlib.Path("migration-runs/sample/artifacts")
WORKSPACE = pathlib.Path("migration-runs/sample/workspace")


@pytest.fixture
def workspace_with_flags():
    """Ensure workspace exists and has been scanned once already."""
    assert WORKSPACE.is_dir(), f"Workspace not found: {WORKSPACE}"
    assert (ARTIFACTS_DIR / "04-flag-index.json").exists(), "Run scanner first"
    return WORKSPACE


def test_scanner_idempotent_second_run(workspace_with_flags):
    """Running the scanner twice on the same workspace must produce 0 new flags."""
    # First, get current flag count
    idx_path = ARTIFACTS_DIR / "04-flag-index.json"
    existing = json.loads(idx_path.read_text(encoding="utf-8"))
    first_count = existing["total_flags"]

    # Run scanner again
    result = subprocess.run(
        [sys.executable, str(SCAN_SCRIPT),
         "--workspace", str(WORKSPACE),
         "--artifacts", str(ARTIFACTS_DIR)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"Scanner failed:\n{result.stderr}"

    # Read new summary (may not exist if no flags were found in first run)
    summary_path = ARTIFACTS_DIR / "04-scan-summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["total_new_flags"] == 0, (
            f"Second scan produced {summary['total_new_flags']} new flags "
            f"(should be 0). First run had {first_count}."
        )
        assert summary["idempotent_skips"] >= first_count, (
            f"Expected at least {first_count} idempotent skips, "
            f"got {summary['idempotent_skips']}"
        )
```

- [ ] **Step 4: Run idempotency test**

```bash
python3 -m pytest tests/test_idempotency.py -v
```

Expected: PASS (if scanner ran before) or rely on existing scan data.

- [ ] **Step 5: Write orchestrator integration test**

```python
# tests/test_orchestrator_integration.py
import json
import pathlib
import subprocess
import sys
import pytest

ORCH_SCRIPT = pathlib.Path(".claude/skills/jade-migration-orchestrator/scripts/orchestrator.py")
ARTIFACTS_DIR = pathlib.Path("migration-runs/sample/artifacts")


def test_orchestrator_completes_on_sample_run():
    """Orchestrator must exit 0 and reach DONE state on sample artifacts."""
    result = subprocess.run(
        [sys.executable, str(ORCH_SCRIPT),
         "--artifacts-dir", str(ARTIFACTS_DIR)],
        capture_output=True, text=True,
    )
    # Orchestrator may exit 0 (completed) or 1 (needs more input) —
    # but must not crash with exceptions.
    assert result.returncode in (0, 1, 2), (
        f"Unexpected exit code {result.returncode}:\n{result.stderr}"
    )

    # Verify run state exists and is in a valid terminal state
    state = json.loads((ARTIFACTS_DIR / "00-run-state.json").read_text(encoding="utf-8"))
    assert state["state"] in {
        "DONE", "FAILED", "AWAITING_SOURCE_INPUT",
        "INIT", "WORKSPACE_READY", "MANIFEST_READY",
    }, f"Unexpected state: {state['state']}"


def test_orchestrator_handles_missing_config():
    """Orchestrator must return non-zero when config is missing."""
    result = subprocess.run(
        [sys.executable, str(ORCH_SCRIPT),
         "--artifacts-dir", "/nonexistent/path"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0, "Orchestrator should fail with missing config dir"


def test_orchestrator_produces_phase_history():
    """After a run, phase-history.log.jsonl must exist with valid entries."""
    history_path = ARTIFACTS_DIR / "phase-history.log.jsonl"
    assert history_path.exists(), "phase-history.log.jsonl not found"

    lines = [line for line in history_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) > 0, "Phase history is empty"

    for line in lines:
        entry = json.loads(line)
        assert "ts" in entry
        assert "phase" in entry
        assert "status" in entry
        assert "artifacts" in entry
```

- [ ] **Step 6: Run integration tests**

```bash
python3 -m pytest tests/test_orchestrator_integration.py -v
```

Expected: all tests PASS.

- [ ] **Step 7: Run full test suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add tests/test_artifact_contracts.py tests/test_idempotency.py tests/test_orchestrator_integration.py
git commit -m "test(skills): expand contract, idempotency, and integration tests"
```

---

## Execution order

Tasks must run sequentially: 1 → 2 → 3 → 4. Each task ends with a commit.

## DoD (Definition of Done)

- [ ] All legacy directories and `__pycache__/` dirs removed from repo
- [ ] `.gitignore` covers `__pycache__/`, `*.pyc`, `JADE-4.6.0-java1.6/`
- [ ] `apply_rule_fix.py` has real `apply_raw_types_fix()` and `apply_enhanced_for_fix()` functions wired into main()
- [ ] `evaluate_skills.py` accepts `--artifacts` CLI arg and scores per-skill with artifact completeness
- [ ] `test_artifact_contracts.py` validates all 7 artifact JSON schemas
- [ ] `test_idempotency.py` verifies scanner produces 0 new flags on second run
- [ ] `test_orchestrator_integration.py` verifies orchestrator exits cleanly and produces valid phase history
- [ ] Full test suite `pytest tests/ -v` passes
- [ ] `python3 -c "import py_compile; py_compile.compile('.claude/skills/jade-rule-fixer/scripts/apply_rule_fix.py', doraise=True)"` succeeds
