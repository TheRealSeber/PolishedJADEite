---
name: jade-1.5-to-1.6-enhanced-for
description: >-
  Converts traditional indexed for-loops to enhanced-for loops in JADE.
  Operates on JADE-4.6.0-java1.6/ (migration copy). Only converts provably safe
  loops — marks unsafe ones with MIGRATION-SKIP comments.
  Run after jade-1.5-to-1.6-raw-types (generics make element types known).
when_to_use: >-
  Use when the user says "enhanced for", "for-each", "convert for loops",
  or after jade-phase0-scanner recommends this skill.
arguments: [target_dir]
argument-hint: "[source-directory e.g. JADE-4.6.0/src/jade/src]"
disable-model-invocation: true
allowed-tools: Bash(ant *) Bash(grep *) Bash(find *) Read Write
env: JAVA_HOME=/usr/lib/jvm/java-8-openjdk
paths: "**/*.java"
---

# JADE 1.5→1.6 — Enhanced For Loops

Target: **$target_dir**

---

## Step 1: Confirm migration copy and generics are done

```bash
[ -d "JADE-4.6.0-java1.6" ] && echo "OK" || echo "ERROR: run jade-1.5-to-1.6-raw-types first"
cd JADE-4.6.0-java1.6/src/jade && JAVA_HOME=/usr/lib/jvm/java-8-openjdk ant jade -q 2>&1 | grep "error:" | head -3 && cd ../../..
```

---

## Step 2: Find candidate loops

```bash
# Collection loops
grep -rn "for.*int [a-z].*=.*0.*\.size()" $target_dir --include="*.java" 2>/dev/null | grep -v "//\|\*"

# Array loops
grep -rn "for.*int [a-z].*=.*0.*\.length" $target_dir --include="*.java" 2>/dev/null | grep -v "//\|\*"
```

---

## Step 3: Safety classification

**SAFE — convert:**
- Index used only for `.get(i)` or `array[i]`
- No `.remove(i)`, `.set(i, x)`, `.add(i, x)` inside loop
- Not iterating two parallel collections with same index
- Index not used after the loop body

**UNSAFE — add `// MIGRATION-SKIP:` comment, leave loop unchanged:**
- `list.remove(i)` or `list.set(i, x)` inside loop
- Index used to write into a parallel array (`other[i] = list.get(i)`)
- `i` stored or returned after loop
- Backwards loop or step > 1
- Loop over `jade.util.leap.List` — leave entirely unchanged

---

## Step 4: Convert SAFE loops

```java
// BEFORE — pure iteration, index only used for .get(i)
for (int i = 0; i < services.size(); i++) {
    ServiceDescriptor sd = (ServiceDescriptor) services.get(i);
    sd.install(container);
}

// AFTER — cast also removed because raw-types skill already typed services
for (ServiceDescriptor sd : services) {
    sd.install(container);
}
```

```java
// BEFORE — typed Iterator while-loop (raw-types already parameterised it)
Iterator<String> it = list.iterator();
while (it.hasNext()) {
    String s = it.next();
    process(s);
}

// AFTER — only if it.remove() is never called
for (String s : list) {
    process(s);
}
// Leave as Iterator if it.remove() is called inside the loop.
```

**UNSAFE example — add comment, do not convert:**
```java
// MIGRATION-SKIP: i3 used as index into agentArgs[] — enhanced-for not safe
Object agentArgs[] = new Object[asArgs.size()];
for (int i3 = 0; i3 < asArgs.size(); i3++) {
    agentArgs[i3] = asArgs.get(i3);
}
```

---

## Step 5: Verify after each file

```bash
cd JADE-4.6.0-java1.6/src/jade && JAVA_HOME=/usr/lib/jvm/java-8-openjdk ant jade -q 2>&1 | grep "error:" | head -5 && cd ../../..
```

---

## Step 6: Final report

Report: loops converted, loops skipped (with reason breakdown), compile result.

---

## Constraints

1. `JADE-4.6.0/` is never touched
2. Never convert loops over `jade.util.leap.List`
3. When in doubt → `// MIGRATION-SKIP:` and leave it
4. Use meaningful loop variable names (`agent` not `a`)
5. Preserve all comments inside loop body

## Exit criteria

- All SAFE loops converted
- All UNSAFE loops have `// MIGRATION-SKIP:` comment
- `JADE-4.6.0-java1.6/` compiles with zero errors
