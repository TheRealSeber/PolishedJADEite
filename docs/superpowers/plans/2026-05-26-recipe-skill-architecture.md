# Recipe Skill Architecture — SKILL.md-First Model

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert all recipe skill directories to proper skills with mandatory `SKILL.md`. `apply.py` remains only where the transform is mechanical and benefits from deterministic subprocess execution.

**Architecture:** Every recipe is a proper skill (SKILL.md frontmatter + body). `apply.py` is an optional cache — a compiled implementation of the same instructions. When `apply.py` fails or is absent, the agent follows SKILL.md instructions directly. The dispatcher/registry remains unchanged; registry entries now point to real skill directories instead of sharing the noop bucket.

**Tech Stack:** Markdown (SKILL.md frontmatter YAML), Python (apply.py for mechanical transforms), JSON (recipe-registry.json)

---

## File Structure

| Action | Path | Purpose |
|--------|------|---------|
| **Create** | `.claude/skills/jade-recipe-noop/SKILL.md` | Frontmatter + agent instructions for the noop fallback |
| **Create** | `.claude/skills/jade-recipe-1.5-1.6-arrays-copyof/SKILL.md` | Frontmatter + agent instructions for Arrays.copyOf transform |
| **Create** | `.claude/skills/jade-recipe-1.5-1.6-deque-retrofit/SKILL.md` | New skill: documents why LinkedList already implements Deque in Java 6 |
| **Create** | `.claude/skills/jade-recipe-1.5-1.6-deque-retrofit/scripts/apply.py` | Thin SKIPPED response (informational rule, no code change) |
| **Create** | `.claude/skills/jade-recipe-1.5-1.6-navigable-set-map/SKILL.md` | New skill: documents why TreeSet/TreeMap already implement Navigable* in Java 6 |
| **Create** | `.claude/skills/jade-recipe-1.5-1.6-navigable-set-map/scripts/apply.py` | Thin SKIPPED response (informational rule, no code change) |
| **Modify** | `.claude/skills/jade-core-rule-dispatcher/recipe-registry.json` | Update DEQUE and NAVIGABLE entries to point to their new skill dirs |
| *Keep* | `.claude/skills/jade-recipe-noop/scripts/apply.py` | Existing noop script (unchanged, still works) |
| *Keep* | `.claude/skills/jade-recipe-1.5-1.6-arrays-copyof/scripts/apply.py` | Existing copyof script (unchanged, still works) |

---

### Task 1: Create SKILL.md for jade-recipe-noop

**Files:**
- Create: `.claude/skills/jade-recipe-noop/SKILL.md`

- [ ] **Step 1: Write SKILL.md with frontmatter and agent instructions**

```markdown
---
name: jade-recipe-noop
description: >-
  Fallback recipe for rules with no specific transform. Marks flagged
  lines as SKIPPED — no source change needed. Used when the fix is
  informational (e.g., "LinkedList already implements Deque in Java 6").
  Invoked by jade-core-rule-dispatcher.
arguments: [--file, --line]
---
# jade-recipe-noop — No-Operation Fallback

Returns `SKIPPED` for every invocation. No source file is modified.

## When this skill applies

The dispatcher routes here when:
- A rule has no dedicated recipe skill registered
- The rule is informational (no code change required)
- The change was already addressed by a prior migration

## Agent fallback (when subprocess is unavailable)

1. Read the flagged file at the given `--line`
2. Read the manifest entry for the rule to understand what it flags
3. If the rule is informational (Java 6 already provides the feature):
   - Mark the file as SKIPPED — no code change needed
   - Optionally add a `// NOTE: <explanation>` comment for future readers
4. If the rule requires a transform but no recipe exists:
   - Mark as DEFERRED with `// JADE-MODERNIZATION-DEFERRED:<rule_id>`.
   - Write a summary of what the agent would need to do

## Edge cases

- Some manifest rules reference imaginary recipe skills (`jade-recipe-1.7-try-with-resources`).
  These route through this fallback. The agent should interpret the manifest entry's
  `fix_strategy` to understand what transform was intended.
```

- [ ] **Step 2: Verify SKILL.md frontmatter is valid YAML**

```bash
python -c "import yaml; yaml.safe_load(open('.claude/skills/jade-recipe-noop/SKILL.md'))"
```

- [ ] **Step 3: Verify existing apply.py still works unchanged**

```bash
python .claude/skills/jade-recipe-noop/scripts/apply.py --file .claude/skills/jade-recipe-noop/scripts/apply.py --line 1
```

Expected output: `{"status": "SKIPPED", "changes": 0, ...}`

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/jade-recipe-noop/SKILL.md
git commit -m "feat: add SKILL.md to jade-recipe-noop with agent fallback instructions"
```

---

### Task 2: Create SKILL.md for jade-recipe-1.5-1.6-arrays-copyof

**Files:**
- Create: `.claude/skills/jade-recipe-1.5-1.6-arrays-copyof/SKILL.md`

- [ ] **Step 1: Write SKILL.md with frontmatter, transform docs, and agent fallback**

```markdown
---
name: jade-recipe-1.5-1.6-arrays-copyof
description: >-
  Replaces System.arraycopy() calls with Java 6 Arrays.copyOf()/copyOfRange().
  Handles three cases: same-source copy, destPos=0 copy, and non-zero
  destPos (leaves a NOTE comment). Invoked by jade-core-rule-dispatcher.
arguments: [--file, --line]
---
# jade-recipe-1.5-1.6-arrays-copyof — System.arraycopy → Arrays.copyOf

Java 6 introduced `java.util.Arrays.copyOf()` and `Arrays.copyOfRange()`,
which are more readable and less error-prone than `System.arraycopy()`.
This recipe replaces simple `System.arraycopy` calls with the new API.

## Automated transform (apply.py)

The `scripts/apply.py` subprocess handles three cases:

1. **Same source + destPos=0:** `System.arraycopy(arr, 0, arr, 0, newLen)`
   → `arr = java.util.Arrays.copyOf(arr, newLen)`

2. **Any source + destPos=0:** `System.arraycopy(src, sp, dest, 0, len)`
   → `dest = java.util.Arrays.copyOf(src, len)`

3. **Non-zero destPos:** Leaves the call as-is with a `// NOTE:` comment
   suggesting `Arrays.copyOfRange` for manual review.

The script also adds `import java.util.Arrays` if not already present.

## Agent fallback (when apply.py fails or the pattern is complex)

For each flagged `System.arraycopy` call:

1. Read the source file and the flagged line
2. Identify: source array, source position, destination array, destination position, length
3. **If destPos is 0:**
   - Replace with `destinationArray = java.util.Arrays.copyOf(sourceArray, length)`
   - If source and destination are the same, just: `arr = java.util.Arrays.copyOf(arr, newLen)`
4. **If destPos is non-zero:**
   - Replace with `System.arraycopy(src, srcPos, dest, destPos, length)` followed by
     `// NOTE: Consider Arrays.copyOfRange(src, srcPos, srcPos+length) for Java 6+`
5. **If the call is too complex to parse** (inline expressions, method calls as args):
   - Leave as-is with `// NOTE: Consider Arrays.copyOf/copyOfRange for Java 6+`
6. Add `import java.util.Arrays;` if not already present
7. Remove the `// JADE-FLAG:ARRAYS_COPY_OF_UPGRADE` comment

## Edge cases

- `System.arraycopy` inside a loop or conditional — the transform is still valid
- Non-literal arguments (method calls) — the regex may not parse; fall back to agent
- Source and dest are different arrays with non-zero destPos — use copyOfRange, add NOTE
```

- [ ] **Step 2: Verify YAML frontmatter**

```bash
python -c "import yaml; yaml.safe_load(open('.claude/skills/jade-recipe-1.5-1.6-arrays-copyof/SKILL.md'))"
```

- [ ] **Step 3: Verify apply.py still works after no changes to it**

```bash
python -c "
import pathlib, tempfile, subprocess, sys
tmp = tempfile.mkdtemp()
f = pathlib.Path(tmp) / 'Test.java'
f.write_text('System.arraycopy(src, 0, dest, 0, 10);\n', encoding='utf-8')
r = subprocess.run([sys.executable, '.claude/skills/jade-recipe-1.5-1.6-arrays-copyof/scripts/apply.py', '--file', str(f), '--line', '1'], capture_output=True, text=True)
print(r.stdout.strip())
import shutil; shutil.rmtree(tmp)
"
```

Expected output contains `"status": "FIXED"` and `Arrays.copyOf`.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/jade-recipe-1.5-1.6-arrays-copyof/SKILL.md
git commit -m "feat: add SKILL.md to arrays-copyof recipe with agent fallback"
```

---

### Task 3: Create jade-recipe-1.5-1.6-deque-retrofit as a proper skill

**Files:**
- Create: `.claude/skills/jade-recipe-1.5-1.6-deque-retrofit/scripts/` directory
- Create: `.claude/skills/jade-recipe-1.5-1.6-deque-retrofit/SKILL.md`
- Create: `.claude/skills/jade-recipe-1.5-1.6-deque-retrofit/scripts/apply.py`
- Modify: `.claude/skills/jade-core-rule-dispatcher/recipe-registry.json`

- [ ] **Step 1: Create the skill directory**

```bash
mkdir -p .claude/skills/jade-recipe-1.5-1.6-deque-retrofit/scripts
```

- [ ] **Step 2: Write SKILL.md**

```markdown
---
name: jade-recipe-1.5-1.6-deque-retrofit
description: >-
  Informational rule. LinkedList already implements Deque in Java 6.
  No code change required. Invoked by jade-core-rule-dispatcher.
arguments: [--file, --line]
---
# jade-recipe-1.5-1.6-deque-retrofit — Informational

Java 6 added the `java.util.Deque` interface, and `java.util.LinkedList`
already implements it. No source code change is required.

## Automated transform (apply.py)

Returns `SKIPPED` for every file — informational rule only.

## Agent fallback

1. Verify the flagged file uses `LinkedList`
2. Confirm the code compiles on Java 6+ (LinkedList implements Deque natively)
3. Mark as SKIPPED — no transform needed
4. Optionally replace `List<X> x = new LinkedList<>()` with `Deque<X> x = new LinkedList<>()` if the variable is used only with Deque methods
```

- [ ] **Step 3: Write the thin apply.py**

```python
#!/usr/bin/env python3
"""Informational recipe — LinkedList already implements Deque in Java 6. No code change needed."""
import argparse, json, sys

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--line", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps({
        "status": "SKIPPED",
        "changes": 0,
        "warnings": ["LinkedList already implements Deque in Java 6 — informational rule"],
        "errors": [],
        "diff_summary": "LinkedList already implements Deque in Java 6; no code change needed",
    }))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Verify apply.py works**

```bash
python .claude/skills/jade-recipe-1.5-1.6-deque-retrofit/scripts/apply.py --file /dev/null --line 1
```

Expected: `{"status": "SKIPPED", ...}`

- [ ] **Step 5: Update recipe-registry.json**

The registry entry `DEQUE_LINKEDLIST_RETROFIT` currently points to `jade-recipe-noop/scripts/apply.py`. Change it to point to the new skill:

```json
"DEQUE_LINKEDLIST_RETROFIT": {
    "skill": "jade-recipe-1.5-1.6-deque-retrofit",
    "script": ".claude/skills/jade-recipe-1.5-1.6-deque-retrofit/scripts/apply.py",
    "description": "LinkedList already implements Deque in Java 6 — informational only"
}
```

- [ ] **Step 6: Verify registry is valid JSON**

```bash
python -c "import json; json.load(open('.claude/skills/jade-core-rule-dispatcher/recipe-registry.json'))"
```

- [ ] **Step 7: Commit**

```bash
git add .claude/skills/jade-recipe-1.5-1.6-deque-retrofit/ .claude/skills/jade-core-rule-dispatcher/recipe-registry.json
git commit -m "feat: create jade-recipe-1.5-1.6-deque-retrofit as proper skill"
```

---

### Task 4: Create jade-recipe-1.5-1.6-navigable-set-map as a proper skill

**Files:**
- Create: `.claude/skills/jade-recipe-1.5-1.6-navigable-set-map/scripts/` directory
- Create: `.claude/skills/jade-recipe-1.5-1.6-navigable-set-map/SKILL.md`
- Create: `.claude/skills/jade-recipe-1.5-1.6-navigable-set-map/scripts/apply.py`
- Modify: `.claude/skills/jade-core-rule-dispatcher/recipe-registry.json`

- [ ] **Step 1: Create the skill directory**

```bash
mkdir -p .claude/skills/jade-recipe-1.5-1.6-navigable-set-map/scripts
```

- [ ] **Step 2: Write SKILL.md**

```markdown
---
name: jade-recipe-1.5-1.6-navigable-set-map
description: >-
  Informational rule. TreeSet/TreeMap already implement NavigableSet/
  NavigableMap in Java 6. No code change required. Invoked by
  jade-core-rule-dispatcher.
arguments: [--file, --line]
---
# jade-recipe-1.5-1.6-navigable-set-map — Informational

Java 6 added `java.util.NavigableSet` and `java.util.NavigableMap` interfaces.
`java.util.TreeSet` and `java.util.TreeMap` already implement them natively.
No source code change is required.

## Automated transform (apply.py)

Returns `SKIPPED` for every file — informational rule only.

## Agent fallback

1. Verify the flagged file uses `TreeSet` or `TreeMap`
2. Confirm the code compiles on Java 6+ (these classes implement Navigable* natively)
3. Mark as SKIPPED — no transform needed
4. Optionally retype variables from `SortedSet`/`SortedMap` to `NavigableSet`/`NavigableMap`
   if the code uses navigation methods (ceiling, floor, higher, lower, etc.)
```

- [ ] **Step 3: Write the thin apply.py**

```python
#!/usr/bin/env python3
"""Informational recipe — TreeSet/TreeMap already implement NavigableSet/NavigableMap in Java 6."""
import argparse, json, sys

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--line", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps({
        "status": "SKIPPED",
        "changes": 0,
        "warnings": ["TreeSet/TreeMap already implement NavigableSet/NavigableMap in Java 6 — informational rule"],
        "errors": [],
        "diff_summary": "TreeSet/TreeMap already implement Navigable* in Java 6; no code change needed",
    }))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Verify apply.py works**

```bash
python .claude/skills/jade-recipe-1.5-1.6-navigable-set-map/scripts/apply.py --file /dev/null --line 1
```

Expected: `{"status": "SKIPPED", ...}`

- [ ] **Step 5: Update recipe-registry.json**

The registry entry `NAVIGABLE_SET_MAP` currently points to `jade-recipe-noop/scripts/apply.py`. Change it:

```json
"NAVIGABLE_SET_MAP": {
    "skill": "jade-recipe-1.5-1.6-navigable-set-map",
    "script": ".claude/skills/jade-recipe-1.5-1.6-navigable-set-map/scripts/apply.py",
    "description": "TreeSet/TreeMap already implement NavigableSet/NavigableMap in Java 6 — informational only"
}
```

- [ ] **Step 6: Verify registry JSON is valid**

```bash
python -c "import json; json.load(open('.claude/skills/jade-core-rule-dispatcher/recipe-registry.json'))"
```

- [ ] **Step 7: Commit**

```bash
git add .claude/skills/jade-recipe-1.5-1.6-navigable-set-map/ .claude/skills/jade-core-rule-dispatcher/recipe-registry.json
git commit -m "feat: create jade-recipe-1.5-1.6-navigable-set-map as proper skill"
```

---

### Task 5: Final verification — audit all recipe skills

**Files:**
- Verify all 7 recipe directories now have SKILL.md
- Verify recipe-registry.json points to real directories

- [ ] **Step 1: List all recipe skills and verify SKILL.md presence**

```bash
for d in .claude/skills/jade-recipe-*/; do
  name=$(basename "$d")
  if [ -f "$d/SKILL.md" ]; then
    echo "OK  $name (has SKILL.md)"
  else
    echo "MISSING $name (NO SKILL.md)"
  fi
done
```

Expected: All 7 directories show `OK`.

- [ ] **Step 2: Verify all registry script paths point to real files**

```bash
python -c "
import json, pathlib
registry = json.load(open('.claude/skills/jade-core-rule-dispatcher/recipe-registry.json'))
for rule_id, entry in registry.items():
    if rule_id.startswith('_'):
        continue
    script_path = entry.get('script', '')
    skill_name = entry.get('skill', '')
    if not pathlib.Path(script_path).exists():
        print(f'MISSING SCRIPT: {rule_id} -> {script_path}')
    elif not pathlib.Path(f'.claude/skills/{skill_name}/SKILL.md').exists():
        print(f'MISSING SKILL.MD: {rule_id} -> {skill_name}')
    else:
        print(f'OK  {rule_id} -> {skill_name}')
"
```

Expected: All entries show `OK`.

- [ ] **Step 3: Run full test suite to confirm no regressions**

```bash
python -m pytest tests/ -q --deselect tests/test_orchestrator_integration.py::test_transition_table_integrity
```

Expected: All pass (41 passed, pre-existing orchestrator failure deselected).

- [ ] **Step 4: Commit (if any final tweaks)**

```bash
git status
# Only commit if there are uncommitted changes from audit fixes
```

---

### Completed State

After all tasks:

```
.claude/skills/jade-recipe-dummy/SKILL.md                         ✅ (was already present)
.claude/skills/jade-recipe-noop/SKILL.md                          ✅ NEW
.claude/skills/jade-recipe-1.5-1.6-arrays-copyof/SKILL.md         ✅ NEW
.claude/skills/jade-recipe-1.5-1.6-deque-retrofit/SKILL.md        ✅ NEW
.claude/skills/jade-recipe-1.5-1.6-deque-retrofit/scripts/apply.py ✅ NEW
.claude/skills/jade-recipe-1.5-1.6-navigable-set-map/SKILL.md      ✅ NEW
.claude/skills/jade-recipe-1.5-1.6-navigable-set-map/scripts/apply.py ✅ NEW
.claude/skills/jade-recipe-1.7-diamond-operator/SKILL.md           ✅ (was already present)
.claude/skills/jade-recipe-1.7-strings-in-switch/SKILL.md          ✅ (was already present)
```

Registry: All entries now point to real skill directories (no more shared noop bucket).
