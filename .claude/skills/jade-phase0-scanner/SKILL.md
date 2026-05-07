---
name: jade-phase0-scanner
description: >-
  Scans a JADE source directory for Java 1.5-era idiom patterns and outputs a
  structured flag report. Always run this before any jade-1.5-to-X migration skill
  to know which skills are needed and how much work is involved.
when_to_use: >-
  Use when the user says "scan jade", "phase 0", "what patterns exist", "which skills
  do I need", "before migration", "analyze jade source", or "how much work is this".
arguments: [target_dir]
argument-hint: "[source-directory]"
context: fork
agent: Explore
allowed-tools: Bash(grep *) Bash(find *) Bash(wc *)
paths: "**/*.java"
---

# JADE Phase 0 — Idiom Scanner

Scanning: **$target_dir**

## Live counts

Total `.java` files: !`find $target_dir -name "*.java" 2>/dev/null | wc -l`

**Raw collection instantiations** (files affected):
!`grep -rl "new Vector()\|new Hashtable()\|new ArrayList()\|new HashMap()\|new LinkedList()\|new HashSet()" $target_dir --include="*.java" 2>/dev/null | wc -l`

**Raw collection declarations** (lines):
!`grep -rn "Vector \|Hashtable \|ArrayList \|HashMap \|LinkedList \|HashSet \|Iterator " $target_dir --include="*.java" 2>/dev/null | grep -v "<\|import\|//\|\*\|jade\.util\.leap" | wc -l`

**Cast-get patterns** (lines — casts that generics will remove):
!`grep -rn "([A-Z][a-zA-Z]*) .*\.get\b" $target_dir --include="*.java" 2>/dev/null | grep -v "//\|\*\|import" | wc -l`

**JADE LEAP files** (do not touch — JADE's own MIDP iterator abstraction):
!`grep -rl "jade\.util\.leap\.Iterator\|jade\.util\.leap\.List" $target_dir --include="*.java" 2>/dev/null | wc -l`

**Mixed-iterator files** (both LEAP and java.util — needs careful handling):
!`grep -rl "jade\.util\.leap\.Iterator" $target_dir --include="*.java" 2>/dev/null | xargs grep -l "Iterator [a-zA-Z]" 2>/dev/null | wc -l`

**Traditional for-loops over collections** (`.size()` guard):
!`grep -rn "for.*int [a-z].*=.*0.*\.size()" $target_dir --include="*.java" 2>/dev/null | grep -v "//\|\*" | wc -l`

**Traditional for-loops over arrays** (`.length` guard):
!`grep -rn "for.*int [a-z].*=.*0.*\.length" $target_dir --include="*.java" 2>/dev/null | grep -v "//\|\*" | wc -l`

**JVMDI/JVMPI references** (removed in Java 6 — must be zero):
!`grep -rn "JVMDI\|JVMPI\|JDK1_1InitArgs\|JDK1_1AttachArgs" $target_dir --include="*.java" 2>/dev/null | wc -l`

---

## Your task

Using the counts above, produce this exact report:

```
=== JADE Phase 0 Scan Report ===
Target: $target_dir

FLAG                        COUNT    SEVERITY
---------------------------------------------
RAW_INST_FILES              <N>      HIGH / MEDIUM / LOW / NONE
RAW_DECL_LINES              <N>      ...
CAST_GET_LINES              <N>      ...
LEAP_ITER_FILES             <N>      INFO (never modify)
MIXED_ITER_FILES            <N>      WARN if > 0
FOR_SIZE_LOOPS              <N>      ...
FOR_LENGTH_LOOPS            <N>      ...
JVMDI_JVMPI_REFS            <N>      BLOCKER if > 0 (removed in Java 6)

=== Recommended Skills ===
1. jade-1.5-to-1.6-raw-types    (invoke as: /jade-1.5-to-1.6-raw-types $target_dir)
2. jade-1.5-to-1.6-enhanced-for (invoke after raw-types: /jade-1.5-to-1.6-enhanced-for $target_dir)
```

Severity thresholds: HIGH > 100, MEDIUM 20–100, LOW 1–19, NONE = 0.
BLOCKER = migration must not proceed until resolved.
Only recommend a skill if its relevant count is > 0.
If JVMDI_JVMPI_REFS > 0, add a BLOCKER notice above the skill recommendations and do not recommend migration skills.
Skip the recommendation section entirely if all counts are 0.
