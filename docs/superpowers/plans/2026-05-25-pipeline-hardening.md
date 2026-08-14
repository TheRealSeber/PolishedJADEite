# JADE Pipeline Hardening — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 6 pipeline bugs discovered during the jade-1.5-to-1.6 migration run to prevent them in future migrations.

**Architecture:** Each fix targets a specific pipeline component (orchestrator, scanner, change-collector, build-fixer, rule-dispatcher). All fixes are localized — no cross-cutting refactoring. Each fix adds a guard clause or a new transition entry. No new files are created beyond what already exists (`jade-recipe-noop` recipe).

**Tech Stack:** Python 3, existing orchestrator/scanner/collector/build-fixer/dispatcher scripts.

---

### Task 1: Fix orchestrator RUNTIME_VERIFY missing SCRIPT_ERROR transition

**Files:**
- Modify: `.claude/skills/jade-core-orchestrator/scripts/orchestrator.py:56`

- [ ] **Step 1: Add SCRIPT_ERROR transition**

Replace line 56:
```python
"RUNTIME_VERIFY": {"OK": "DONE", "VERIFY_FAIL": "FAILED"},
```
with:
```python
"RUNTIME_VERIFY": {"OK": "DONE", "VERIFY_FAIL": "FAILED", "SCRIPT_ERROR": "FAILED"},
```

- [ ] **Step 2: Verify syntax**

Run: `python -c "import ast; ast.parse(open('.claude/skills/jade-core-orchestrator/scripts/orchestrator.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Verify the TRANSITIONS table includes all states**

Run: `python -c "
exec(open('.claude/skills/jade-core-orchestrator/scripts/orchestrator.py').read())
print('RUNTIME_VERIFY transitions:', TRANSITIONS.get('RUNTIME_VERIFY'))
"`
Expected: shows `{'OK': 'DONE', 'VERIFY_FAIL': 'FAILED', 'SCRIPT_ERROR': 'FAILED'}`

---

### Task 2: Guard script phases from re-triggering in --run mode

**Files:**
- Modify: `.claude/skills/jade-core-orchestrator/scripts/orchestrator.py:908-909`

- [ ] **Step 1: Wrap script invocation with artifact existence check**

Replace lines 908-909:
```python
            if args.run and current in SCRIPT_PHASES:
                script_outcome = _run_script_phase(current, cfg)
```
with:
```python
            af = REQUIRED_ARTIFACTS.get(current, [])
            artifact_missing = not all((artifacts / a).exists() for a in af)
            if args.run and current in SCRIPT_PHASES and artifact_missing:
                script_outcome = _run_script_phase(current, cfg)
```

- [ ] **Step 2: Verify syntax**

Run: `python -c "import ast; ast.parse(open('.claude/skills/jade-core-orchestrator/scripts/orchestrator.py').read()); print('OK')"`
Expected: `OK`

---

### Task 3: Guard scanner against empty regex patterns

**Files:**
- Modify: `.claude/skills/jade-core-scanner/scripts/scan_and_tag.py:117-122`

- [ ] **Step 1: Add empty-pattern skip in PatternDef.__init__**

Replace lines 117-122:
```python
    def __init__(self, raw: Dict[str, Any]) -> None:
        self.type: str = raw.get("type", "regex")
        if self.type != "regex":
            raise ValueError(f"Unsupported pattern type: {self.type}")
        self.pattern_str: str = raw["pattern"]
        self.compiled: re.Pattern = re.compile(raw["pattern"])
```
with:
```python
    def __init__(self, raw: Dict[str, Any]) -> None:
        self.type: str = raw.get("type", "regex")
        if self.type != "regex":
            raise ValueError(f"Unsupported pattern type: {self.type}")
        self.pattern_str: str = raw["pattern"]
        if not self.pattern_str.strip():
            raise ValueError("Empty pattern string — skipping rule (would match every line)")
        self.compiled: re.Pattern = re.compile(raw["pattern"])
```

- [ ] **Step 2: Verify syntax**

Run: `python -c "import ast; ast.parse(open('.claude/skills/jade-core-scanner/scripts/scan_and_tag.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Verify empty pattern is rejected**

Run: `python -c "
from .claude.skills.jade_core_scanner.scripts.scan_and_tag import PatternDef" 2>&1 || python -c "
import sys, pathlib
sys.path.insert(0, '.')
import importlib.util
spec = importlib.util.spec_from_file_location('st', '.claude/skills/jade-core-scanner/scripts/scan_and_tag.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
try:
    p = m.PatternDef({'type': 'regex', 'pattern': '', 'target_extensions': ['.java']})
    print('BUG: empty pattern not rejected')
except ValueError as e:
    print('OK: empty pattern rejected:', e)
"`
Expected: `OK: empty pattern rejected: Empty pattern string...`

---

### Task 4: Reject empty patterns in manifest validation (write_manifest.py)

**Files:**
- Modify: `.claude/skills/jade-core-change-collector/scripts/write_manifest.py:64-74`

- [ ] **Step 1: Add empty-pattern check in validate_pattern()**

Replace lines 64-74:
```python
def validate_pattern(pattern: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(pattern.get("pattern"), str):
        errors.append("pattern.pattern must be a string")
    if not isinstance(pattern.get("target_extensions"), list):
        errors.append("pattern.target_extensions must be a list")
    if not isinstance(pattern.get("reason"), str):
        errors.append("pattern.reason must be a string")
    if pattern.get("type") not in ("regex", None):
        errors.append(f"pattern.type must be 'regex', got: {pattern.get('type')}")
    return errors
```
with:
```python
def validate_pattern(pattern: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(pattern.get("pattern"), str):
        errors.append("pattern.pattern must be a string")
    elif pattern.get("pattern", "").strip() == "":
        errors.append("pattern.pattern must not be empty (would match every line)")
    if not isinstance(pattern.get("target_extensions"), list):
        errors.append("pattern.target_extensions must be a list")
    if not isinstance(pattern.get("reason"), str):
        errors.append("pattern.reason must be a string")
    if pattern.get("type") not in ("regex", None):
        errors.append(f"pattern.type must be 'regex', got: {pattern.get('type')}")
    return errors
```

- [ ] **Step 2: Verify syntax**

Run: `python -c "import ast; ast.parse(open('.claude/skills/jade-core-change-collector/scripts/write_manifest.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Verify empty pattern is rejected by manifest validator**

Run: `python -c "
import json, tempfile, pathlib, sys
sys.path.insert(0, '.')
import importlib.util
spec = importlib.util.spec_from_file_location('wm', '.claude/skills/jade-core-change-collector/scripts/write_manifest.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
errors = m.validate_pattern({'type': 'regex', 'pattern': '', 'target_extensions': ['.java'], 'reason': 'test'})
assert errors, f'Expected errors for empty pattern, got none'
print('OK: empty pattern rejected:', errors)
"`
Expected: `OK: empty pattern rejected: ['pattern.pattern must not be empty...']`

---

### Task 5: Build auditor — config-driven build target + log naming

**Files:**
- Modify: `.claude/skills/jade-core-build-fixer/scripts/build_audit.py:654-661` (run_ant_build)
- Modify: `.claude/skills/jade-core-build-fixer/scripts/build_audit.py:984` (log output path)
- Modify: `.claude/skills/jade-core-orchestrator/references/schemas.md:5-13` (run-config schema)

- [ ] **Step 1: Make ant target configurable from run-config**

Replace lines 654-661:
```python
def run_ant_build(
    build_path: pathlib.Path, docker_image: str, default_target: str = "jade"
) -> Tuple[int, str]:
    return _docker_run(
        docker_image,
        build_path.parent,
        ["ant", default_target, "-q"],
    )
```
with:
```python
def run_ant_build(
    build_path: pathlib.Path, docker_image: str, default_target: str = "jade"
) -> Tuple[int, str]:
    return _docker_run(
        docker_image,
        build_path.parent,
        ["ant", default_target, "-q"],
    )


def run_ant_build_target(
    build_path: pathlib.Path, docker_image: str, target: str
) -> Tuple[int, str]:
    return _docker_run(
        docker_image,
        build_path.parent,
        ["ant", target, "-q"],
    )
```

- [ ] **Step 2: Write build output to 07-build.log (orchestrator's expected name)**

Replace line 984:
```python
    write_text(artifacts / "03-build-verify.log", build_output)
```
with:
```python
    write_text(artifacts / "03-build-verify.log", build_output)
    write_text(artifacts / "07-build.log", build_output)
```

- [ ] **Step 3: Update schemas.md to document optional build_target field**

Add `"build_target": "jade"` as optional field in schemas.md run-config section.

- [ ] **Step 4: Verify syntax**

Run: `python -c "import ast; ast.parse(open('.claude/skills/jade-core-build-fixer/scripts/build_audit.py').read()); print('OK')"`
Expected: `OK`

---

### Task 6: Recipe registry fallback + dispatcher fallback

**Files:**
- Modify: `.claude/skills/jade-core-rule-dispatcher/recipe-registry.json` (add fallback)
- Modify: `.claude/skills/jade-core-rule-dispatcher/scripts/dispatcher.py:310-327` (fallback lookup)

- [ ] **Step 1: Add fallback entry to recipe registry**

Add `"fallback"` entry to recipe-registry.json:
```json
"fallback": {
    "skill": "jade-recipe-noop",
    "script": ".claude/skills/java-migration-skill-registry/shared/jade-recipe-noop/scripts/apply.py",
    "description": "Fallback NOOP — marks rule as SKIPPED when no specific recipe exists"
}
```

The key MUST be `"fallback"` (lowercase) with underscores if multi-word — matches the JSON key convention in the existing file.

- [ ] **Step 2: Update dispatcher to fall back to fallback recipe**

Replace lines 310-327:
```python
    recipe_entry = registry.get(args.rule_id)
    if recipe_entry is None:
        record_result(
            artifacts_dir,
            args.task_id,
            args.rule_id,
            file_rel,
            "FAILED",
            0,
            "",
            "",
            "",
            [f"No recipe registered for rule_id: {args.rule_id}"],
            [],
            0,
            0,
        )
        return 2
```
with:
```python
    recipe_entry = registry.get(args.rule_id)
    if recipe_entry is None:
        recipe_entry = registry.get("fallback")
    if recipe_entry is None:
        record_result(
            artifacts_dir,
            args.task_id,
            args.rule_id,
            file_rel,
            "FAILED",
            0,
            "",
            "",
            "",
            [f"No recipe registered for rule_id: {args.rule_id} and no fallback available"],
            [],
            0,
            0,
        )
        return 2
```

- [ ] **Step 3: Verify syntax**

Run: `python -c "import ast; ast.parse(open('.claude/skills/jade-core-rule-dispatcher/scripts/dispatcher.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 4: Verify fallback resolves**

Run: `python -c "
import json
registry = json.load(open('.claude/skills/jade-core-rule-dispatcher/recipe-registry.json'))
assert 'fallback' in registry, 'fallback entry missing'
print('OK: fallback resolves to', registry['fallback']['skill'])
"`
Expected: `OK: fallback resolves to jade-recipe-noop`

---

### Task 7: Run lint and type checks

**Files:** None (verify-only)

- [ ] **Step 1: Run Python syntax check on all modified files**

```bash
python -m py_compile .claude/skills/jade-core-orchestrator/scripts/orchestrator.py && \
python -m py_compile .claude/skills/jade-core-scanner/scripts/scan_and_tag.py && \
python -m py_compile .claude/skills/jade-core-change-collector/scripts/write_manifest.py && \
python -m py_compile .claude/skills/jade-core-build-fixer/scripts/build_audit.py && \
python -m py_compile .claude/skills/jade-core-rule-dispatcher/scripts/dispatcher.py && \
echo "All files compile OK"
```
Expected: `All files compile OK`

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/jade-core-orchestrator/scripts/orchestrator.py
git add .claude/skills/jade-core-scanner/scripts/scan_and_tag.py
git add .claude/skills/jade-core-change-collector/scripts/write_manifest.py
git add .claude/skills/jade-core-build-fixer/scripts/build_audit.py
git add .claude/skills/jade-core-rule-dispatcher/scripts/dispatcher.py
git add .claude/skills/jade-core-rule-dispatcher/recipe-registry.json
git add .claude/skills/jade-core-orchestrator/references/schemas.md
git commit -m "fix: harden pipeline against 6 bugs found in 1.5→1.6 migration"
```
