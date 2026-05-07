---
name: jade-1.5-to-1.6-raw-types
description: >-
  Adds generic type parameters to raw Java collections and iterators in JADE.
  Operates on JADE-4.6.0-java1.6/ (migration copy), never on the original.
  Handles JADE's jade.util.leap.Iterator constraint — never parameterises it.
  Run jade-phase0-scanner first to confirm RAW_INST_FILES > 0.
when_to_use: >-
  Use when the user says "add generics", "fix raw types", "parameterize collections",
  "fix unchecked warnings", or after jade-phase0-scanner recommends this skill.
arguments: [target_dir]
argument-hint: "[source-directory e.g. JADE-4.6.0/src/jade/src]"
disable-model-invocation: true
allowed-tools: Bash(ant *) Bash(cp *) Bash(grep *) Bash(find *) Bash(sed *) Read Write
env: JAVA_HOME=/usr/lib/jvm/java-8-openjdk
paths: "**/*.java"
---

# JADE 1.5→1.6 — Raw Types to Generics

Target: **$target_dir**

> For detailed JADE LEAP type catalogue and type-inference guide, see
> [references/jade-leap-types.md](references/jade-leap-types.md).

## Critical constraint

**Never parameterise `jade.util.leap.Iterator` or `jade.util.leap.List`.**
These are JADE's own MIDP-compatible abstractions, not `java.util` types.
See [references/jade-leap-types.md](references/jade-leap-types.md) for the full list.

---

## Step 1: Create the migration copy

```bash
if [ ! -d "JADE-4.6.0-java1.6" ]; then
  cp -r JADE-4.6.0 JADE-4.6.0-java1.6
  echo "Created JADE-4.6.0-java1.6/"
fi
```

Then update `source` and `target` in `JADE-4.6.0-java1.6/src/jade/build.xml` from `1.5` to `1.6`:

```bash
sed -i 's/source="1\.5"/source="1.6"/g; s/target="1\.5"/target="1.6"/g' \
  JADE-4.6.0-java1.6/src/jade/build.xml
```

All edits go to `JADE-4.6.0-java1.6/`. Never touch `JADE-4.6.0/`.

---

## Step 2: Baseline compile

```bash
cd JADE-4.6.0/src/jade && JAVA_HOME=/usr/lib/jvm/java-8-openjdk ant jade -q 2>&1 | tail -5 && cd ../../..
```

If the original does not compile, stop. Do not proceed.

---

## Step 3: Work package by package

List packages by raw-type density, start with fewest:

```bash
grep -rl "new Vector()\|new Hashtable()\|new ArrayList()\|new HashMap()\|new LinkedList()" \
  $target_dir --include="*.java" 2>/dev/null \
  | sed 's|/[^/]*\.java||' | sort | uniq -c | sort -n | head -20
```

---

## Step 4: Per-file type inference

For each raw collection variable, determine the correct type parameter:

1. Find all `.add(x)` / `.put(k,v)` calls → infer from argument
2. Find all `.get(i)` usages → check if result is cast
3. Check method signatures that pass this collection around
4. If type is ambiguous or mixed → use `Object` (do not guess)

**Examples from real JADE files:**

```java
// BEFORE — BootHelper.java:67
Vector l = new Vector();
l.add(someString);
String s = (String) l.get(i);

// AFTER
Vector<String> l = new Vector<String>();  // no diamond — target is Java 1.6
l.add(someString);
String s = l.get(i);                      // cast removed
```

```java
// BEFORE — GuiEvent.java:63
parameters = new ArrayList();
// getAllParameter() returns Iterator, params are Object

// AFTER — Object is correct, do not guess a narrower type
parameters = new ArrayList<Object>();
public Iterator<Object> getAllParameter() { return parameters.iterator(); }
```

> **No diamond operator.** Target is Java 1.6. Use `new Vector<String>()` not `new Vector<>()`.
> Diamond requires Java 1.7 — that's the next jump.

---

## Step 5: Apply and verify per file

After editing each file:

```bash
cd JADE-4.6.0-java1.6/src/jade && JAVA_HOME=/usr/lib/jvm/java-8-openjdk ant jade -q 2>&1 | grep "error:" | head -5 && cd ../../..
```

Fix any errors before moving to the next file.

---

## Step 6: Handle mixed-iterator files

Files using both `jade.util.leap.Iterator` and `java.util.Iterator`:
parameterise only the `java.util.*` usages, leave LEAP untouched, add comment:

```java
// MIGRATION: java.util.Iterator parameterised; jade.util.leap.Iterator left unchanged
```

---

## Step 7: Final verify

```bash
BEFORE=$(cd JADE-4.6.0/src/jade && JAVA_HOME=/usr/lib/jvm/java-8-openjdk ant jade 2>&1 | grep -c "\[unchecked\]")
AFTER=$(cd JADE-4.6.0-java1.6/src/jade && JAVA_HOME=/usr/lib/jvm/java-8-openjdk ant jade 2>&1 | grep -c "\[unchecked\]")
echo "Unchecked warnings: $BEFORE → $AFTER"
```

Report files modified, casts removed, and warning delta.

---

## Constraints

1. `JADE-4.6.0/` is never touched
2. `jade.util.leap.*` types are never modified
3. No diamond operator `<>` — use explicit type parameter
4. Remove casts only when the type parameter makes them provably safe
5. When type is ambiguous → `Object`, not a guess
6. Preserve all Javadoc, license headers, comments

## Exit criteria

- `JADE-4.6.0-java1.6/` compiles cleanly
- Unchecked warning count is lower than baseline
- No `jade.util.leap` types were modified
