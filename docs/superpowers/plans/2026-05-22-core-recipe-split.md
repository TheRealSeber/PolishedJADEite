# jade-core / jade-recipe Architecture Split

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple generic pipeline logic from version-specific transforms using a Core/Recipe split + Dispatcher pattern. Core skills stay agnostic across migrations; recipe skills contain only per-rule transform logic.

**Architecture:** Prefix convention: `jade-core-*` for agnostic pipeline, `jade-recipe-*` for version-specific transforms. A `jade-core-rule-dispatcher` routes `rule_id` → recipe skill via a registry JSON. Recipes are pure transforms invoked by the dispatcher — they never touch artifact I/O.

**Tech Stack:** Python 3, Bash, Git.

---

## File Structure

### Files to create
- `.claude/skills/jade-core-rule-dispatcher/SKILL.md`
- `.claude/skills/jade-core-rule-dispatcher/scripts/dispatcher.py`
- `.claude/skills/jade-core-rule-dispatcher/recipe-registry.json`
- `.claude/skills/java-migration-skill-registry/1.5-to-1.6/jade-recipe-java1.5-raw-types/SKILL.md`
- `.claude/skills/java-migration-skill-registry/1.5-to-1.6/jade-recipe-java1.5-raw-types/scripts/apply.py`
- `.claude/skills/java-migration-skill-registry/1.5-to-1.6/jade-recipe-java1.5-enhanced-for/SKILL.md`
- `.claude/skills/java-migration-skill-registry/1.5-to-1.6/jade-recipe-java1.5-enhanced-for/scripts/apply.py`

### Files to rename (10 `git mv`s)
- `jade-migration-orchestrator` → `jade-core-orchestrator`
- `jade-change-collector-strict` → `jade-core-change-collector`
- `jade-tooling-scout` → `jade-core-tooling-scout`
- `jade-build-system-fixer` → `jade-core-build-fixer`
- `jade-scanner` → `jade-core-scanner`
- `jade-rule-batch-processor` → `jade-core-batch-processor`
- `jade-verification-semantic` → `jade-core-verification`
- `jade-atomic-rule-commit` → `jade-core-atomic-commit`
- `jade-retry-router` → `jade-core-retry-router`
- `jade-skill-matrix-evaluator` → `jade-core-evaluator`

### Files to delete
- `.claude/skills/jade-rule-fixer/` (replaced by dispatcher + recipes)

### Files to modify
- `docs/superpowers/plans/2026-05-21-cleanup-and-harden-jade-skills.md` — update skill path references
- `docs/superpowers/plans/2026-05-21-jade-skill-suite-product-first.md` — update skill path references
- `tests/test_idempotency.py` — update script paths
- `tests/test_orchestrator_integration.py` — update script paths
- `migration-runs/jade-1.5-to-1.6/artifacts/01-breaking-changes-manifest.json` — update `fix_strategy` to `"recipe:jade-recipe-java1.5-raw-types"` format

---

## Task 1: Rename 10 core skills to `jade-core-*`

**Files:** 10 `git mv` operations, no content changes.

- [ ] **Step 1: git mv all 10 skill directories**

```bash
git mv .claude/skills/jade-migration-orchestrator .claude/skills/jade-core-orchestrator
git mv .claude/skills/jade-change-collector-strict .claude/skills/jade-core-change-collector
git mv .claude/skills/jade-tooling-scout .claude/skills/jade-core-tooling-scout
git mv .claude/skills/jade-build-system-fixer .claude/skills/jade-core-build-fixer
git mv .claude/skills/jade-scanner .claude/skills/jade-core-scanner
git mv .claude/skills/jade-rule-batch-processor .claude/skills/jade-core-batch-processor
git mv .claude/skills/jade-verification-semantic .claude/skills/jade-core-verification
git mv .claude/skills/jade-atomic-rule-commit .claude/skills/jade-core-atomic-commit
git mv .claude/skills/jade-retry-router .claude/skills/jade-core-retry-router
git mv .claude/skills/jade-skill-matrix-evaluator .claude/skills/jade-core-evaluator
```

- [ ] **Step 2: Verify renaming**

```bash
test ! -d .claude/skills/jade-migration-orchestrator && test -d .claude/skills/jade-core-orchestrator && echo "PASS" || echo "FAIL"
```

- [ ] **Step 3: Commit**

```bash
git commit -m "refactor(skills): rename 10 core skills to jade-core-* prefix"
```

---

## Task 2: Create `jade-core-rule-dispatcher` (new)

**Files:**
- Create: `.claude/skills/jade-core-rule-dispatcher/SKILL.md`
- Create: `.claude/skills/jade-core-rule-dispatcher/scripts/dispatcher.py`
- Create: `.claude/skills/jade-core-rule-dispatcher/recipe-registry.json`

The dispatcher handles the generic LOAD → MATCH → PLAN → RECORD workflow. It contains zero transform logic. When a rule-specific transform is needed, it looks up `rule_id` in `recipe-registry.json`, finds the recipe skill script, and invokes it as a subprocess, capturing stdout as the result.

### recipe-registry.json

```json
{
  "RAW_TYPES": {
    "skill": "jade-recipe-java1.5-raw-types",
    "script": ".claude/skills/java-migration-skill-registry/1.5-to-1.6/jade-recipe-java1.5-raw-types/scripts/apply.py",
    "description": "Add generic type parameters to raw collections"
  },
  "ENHANCED_FOR": {
    "skill": "jade-recipe-java1.5-enhanced-for",
    "script": ".claude/skills/java-migration-skill-registry/1.5-to-1.6/jade-recipe-java1.5-enhanced-for/scripts/apply.py",
    "description": "Convert safe indexed for-loops to enhanced-for"
  }
}
```

### dispatcher.py

Extract the generic workflow from `apply_rule_fix.py` (LOAD task, MATCH rule, RECORD result) — strip out all `apply_raw_types_fix` and `apply_enhanced_for_fix` logic. Add recipe dispatch: when the manifest's `fix_strategy` starts with `"recipe:"`, invoke the recipe script as a subprocess.

### SKILL.md

Frontmatter:
```yaml
name: jade-core-rule-dispatcher
description: Routes rule tasks to recipe skills. Handles LOAD/MATCH/RECORD but delegates transforms to recipe scripts via recipe-registry.json.
```

- [ ] **Step 1: Create recipe-registry.json**
- [ ] **Step 2: Create dispatcher.py** (extract generic workflow from apply_rule_fix.py, add recipe subprocess dispatch)
- [ ] **Step 3: Create SKILL.md**
- [ ] **Step 4: Verify dispatcher parses**

```bash
python -c "import py_compile; py_compile.compile('.claude/skills/jade-core-rule-dispatcher/scripts/dispatcher.py', doraise=True); print('Syntax OK')"
```

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/jade-core-rule-dispatcher/
git commit -m "feat(skills): add jade-core-rule-dispatcher with recipe dispatch"
```

---

## Task 3: Create recipe skills from extracted transforms

**Files:**
- Create: `.claude/skills/java-migration-skill-registry/1.5-to-1.6/jade-recipe-java1.5-raw-types/SKILL.md`
- Create: `.claude/skills/java-migration-skill-registry/1.5-to-1.6/jade-recipe-java1.5-raw-types/scripts/apply.py`
- Create: `.claude/skills/java-migration-skill-registry/1.5-to-1.6/jade-recipe-java1.5-enhanced-for/SKILL.md`
- Create: `.claude/skills/java-migration-skill-registry/1.5-to-1.6/jade-recipe-java1.5-enhanced-for/scripts/apply.py`

Extract `apply_raw_types_fix()` and its helpers (`infer_generic_type`, `_resolve_arg_type`, `_infer_collection_element_type`, `atomic_file_write`) into `jade-recipe-java1.5-raw-types/scripts/apply.py`. Same for `apply_enhanced_for_fix()` into `jade-recipe-java1.5-enhanced-for/scripts/apply.py`.

Each recipe `apply.py` is a standalone CLI script:
```
python apply.py --file <path> --line <num>
```
It reads the file, applies the transform, writes back atomically, and prints a JSON result to stdout:
```json
{"status": "FIXED", "changes": 3, "warnings": []}
```
Exit code 0 = success. Exit code 2 = failure.

- [ ] **Step 1: Create raw-types recipe apply.py** (extract from current apply_rule_fix.py)
- [ ] **Step 2: Create enhanced-for recipe apply.py** (extract from current apply_rule_fix.py)
- [ ] **Step 3: Create SKILL.md files for both recipes**
- [ ] **Step 4: Verify both recipes parse**

```bash
python -c "import py_compile; py_compile.compile('.claude/skills/java-migration-skill-registry/1.5-to-1.6/jade-recipe-java1.5-raw-types/scripts/apply.py', doraise=True); print('raw-types OK')"
python -c "import py_compile; py_compile.compile('.claude/skills/java-migration-skill-registry/1.5-to-1.6/jade-recipe-java1.5-enhanced-for/scripts/apply.py', doraise=True); print('enhanced-for OK')"
```

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/java-migration-skill-registry/
git commit -m "feat(skills): add jade-recipe-java1.5-raw-types and enhanced-for recipe skills"
```

---

## Task 4: Delete `jade-rule-fixer` and update all cross-references

**Files:**
- Delete: `.claude/skills/jade-rule-fixer/`
- Modify: `tests/test_idempotency.py` — update `SCAN_SCRIPT` path
- Modify: `tests/test_orchestrator_integration.py` — update `ORCH_SCRIPT` path
- Modify: `docs/superpowers/plans/2026-05-21-cleanup-and-harden-jade-skills.md` — update skill path references
- Modify: `docs/superpowers/plans/2026-05-21-jade-skill-suite-product-first.md` — update skill path references
- Modify: `migration-runs/jade-1.5-to-1.6/artifacts/01-breaking-changes-manifest.json` — update `fix_strategy`

- [ ] **Step 1: Delete jade-rule-fixer**

```bash
git rm -r .claude/skills/jade-rule-fixer/
```

- [ ] **Step 2: Update test script paths**

In `tests/test_idempotency.py`: change `jade-scanner` → `jade-core-scanner`
In `tests/test_orchestrator_integration.py`: change `jade-migration-orchestrator` → `jade-core-orchestrator`

- [ ] **Step 3: Update plan docs**

In both plan docs, find-replace skill path references:
- `jade-scanner` → `jade-core-scanner`
- `jade-migration-orchestrator` → `jade-core-orchestrator`
- `jade-rule-fixer` → `jade-core-rule-dispatcher`
- etc.

- [ ] **Step 4: Update manifest fix_strategy**

In `01-breaking-changes-manifest.json`, change:
```json
"fix_strategy": "..."
```
to:
```json
"fix_strategy": "recipe:jade-recipe-java1.5-raw-types"
```

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest tests/ -v
```
Expected: 9 passed, 2 skipped.

- [ ] **Step 6: Commit**

```bash
git commit -m "refactor(skills): delete jade-rule-fixer, update cross-references to jade-core-* and jade-recipe-*"
```

---

## Execution order

Tasks must run sequentially: 1 → 2 → 3 → 4. Each task ends with a commit.

## DoD (Definition of Done)

- [ ] 10 core skills renamed to `jade-core-*` prefix
- [ ] `jade-core-rule-dispatcher` created with `recipe-registry.json` and `dispatcher.py`
- [ ] `jade-recipe-java1.5-raw-types` created with `apply.py` (pure transform, CLI-driven)
- [ ] `jade-recipe-java1.5-enhanced-for` created with `apply.py` (pure transform, CLI-driven)
- [ ] `jade-rule-fixer` deleted
- [ ] All cross-references updated (tests, docs, manifest)
- [ ] Full test suite passes: 9 passed, 2 skipped
