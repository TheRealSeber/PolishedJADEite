# JADE LEAP Type Catalogue

JADE's LEAP (Lightweight Extensible Agent Platform) provides its own collection types
for MIDP/J2ME compatibility. These are **not** `java.util` types and must **never** be
parameterised or replaced with `java.util.*` equivalents.

## LEAP types — never modify

| LEAP type | JADE package | Notes |
|-----------|-------------|-------|
| `jade.util.leap.Iterator` | `jade.util.leap` | JADE's own iterator — no type params |
| `jade.util.leap.List` | `jade.util.leap` | JADE's own list interface |
| `jade.util.leap.ArrayList` | `jade.util.leap` | JADE's own ArrayList |
| `jade.util.leap.LinkedList` | `jade.util.leap` | JADE's own LinkedList |
| `jade.util.leap.Map` | `jade.util.leap` | JADE's own map interface |
| `jade.util.leap.HashMap` | `jade.util.leap` | JADE's own HashMap |
| `jade.util.leap.Set` | `jade.util.leap` | JADE's own set interface |
| `jade.util.leap.HashSet` | `jade.util.leap` | JADE's own HashSet |

## How to detect LEAP usage in a file

```bash
grep -n "jade\.util\.leap\|import jade\.util\.leap" <file.java>
```

## Decision tree for Iterator variables

```
Iterator variable found?
├── Has "jade.util.leap" in declaration or import? → LEAP — skip entirely
├── Comes from a jade.util.leap.List.iterator()? → LEAP — skip entirely
└── Comes from a java.util.* collection? → java.util.Iterator — parameterise safely
```

## Mixed-file example

```java
import jade.util.leap.Iterator as LeapIterator;  // or full package reference
import java.util.Iterator;

// LEAP — leave as-is
LeapIterator leapIt = myLeapList.iterator();

// java.util — safe to parameterise
Iterator javaIt = myArrayList.iterator();   // → Iterator<String> javaIt
```

Add this comment when handling a mixed file:
```java
// MIGRATION: java.util.Iterator parameterised; jade.util.leap.Iterator left unchanged
```

## Why LEAP exists

JADE's LEAP module allows the same source to compile for both J2SE and J2ME/MIDP
environments. The LEAP collections mirror the `java.util` API but do not extend it,
making them incompatible with `java.util.Collection` and its generic type system.
