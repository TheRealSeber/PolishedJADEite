# Java 1.5 → 1.6 Breaking Changes Knowledge Base

**Source:** Java Language Specification, 3rd Edition (JLS SE 6)
**URL:** https://docs.oracle.com/javase/specs/jls/se6/html/

This document contains verbatim excerpts describing language features that changed
between Java 1.4 and Java 1.5/1.6, which are relevant for migrating legacy JADE
source code.

---

## 1. Raw Types (JLS 3rd Ed. §4.8)

> A raw type is defined to be one of:
> - The reference type that is formed by taking the name of a generic type
>   declaration without an accompanying type argument list.
> - An array type whose element type is a raw type.
> - A non-static member type of a raw type R that is not inherited from a
>   superclass or superinterface of R.
>
> A non-generic class or interface type is not a raw type.
>
> To facilitate interfacing with non-generic legacy code, it is possible to use
> as a type the erasure of a parameterized type or the erasure of an array type
> whose element type is a parameterized type. Such a type is called a raw type.
>
> More precisely, a raw type is defined to be one of:
> - The reference type that is formed by taking the name of a generic type
>   declaration without an accompanying type argument list. For example,
>   `List` is a raw type, while `List<String>` is not.
> - An array type whose element type is a raw type.
> - A non-static member type of a raw type R that is not inherited from a
>   superclass or superinterface of R.

**Key insight for migration:** Legacy code using `Vector`, `ArrayList`, `HashMap`,
`Hashtable`, `LinkedList`, or `HashSet` without type parameters (e.g.,
`new Vector()`) is using raw types. Java 1.5+ generates unchecked warnings for
these. The migration must add appropriate type parameters inferred from usage
(e.g., `new Vector<String>()`).

**Warning from JLS §4.8:**

> The use of raw types is allowed only as a concession to compatibility of
> legacy code. The use of raw types in code written after the introduction of
> genericity into the Java programming language is strongly discouraged. It is
> possible that future versions of the Java programming language will disallow
> the use of raw types.

---

## 2. Enhanced For Statement (JLS 3rd Ed. §14.14.2)

> The enhanced for statement has the form:
>
> **EnhancedForStatement:**
>   `for ( FormalParameter : Expression ) Statement`
>
> The type of the Expression must be Iterable or an array type, or a
> compile-time error occurs.
>
> The enhanced for statement is equivalent to a basic for statement of the form:
>
> ```
> for (I #i = Expression.iterator(); #i.hasNext(); ) {
>     VariableModifiers_opt TargetType Identifier = (TargetType) #i.next();
>     Statement
> }
> ```
>
> If the type of Expression is a subtype of Iterable for some type argument T,
> then let I be the type java.util.Iterator<T>; otherwise let I be the raw type
> Iterator. The enhanced for statement is equivalent to a basic for statement of
> the above form.
>
> If the type of Expression is an array type T[], then the meaning of the
> enhanced for statement is given by the following translation:
>
> ```
> T[] #a = Expression;
> L1: L2: ... Lm:
> for (int #i = 0; #i < #a.length; #i++) {
>     VariableModifiers_opt TargetType Identifier = #a[#i];
>     Statement
> }
> ```

**Key insight for migration:** Legacy code using indexed for-loops of the form
`for (int i = 0; i < list.size(); i++) { Type x = (Type) list.get(i); ... }`
or `for (int i = 0; i < array.length; i++) { Type x = array[i]; ... }` can be
converted to enhanced for-loops:
`for (Type x : list) { ... }` or `for (Type x : array) { ... }`.

**Safety constraint:** Loops that modify the collection by index (`list.remove(i)`,
`list.set(i, x)`), iterate two parallel collections simultaneously, or use the
index variable after the loop body MUST NOT be converted. They should be marked
with a `// MIGRATION-SKIP: <reason>` comment.

**Note from JLS:** The enhanced for statement provides a simpler, less
error-prone way to iterate over collections and arrays. It eliminates the need
for explicit iterator declarations and index management.

---

## 3. Generics — Type Checking Changes (JLS 3rd Ed. §4.5)

> A type argument T1 is said to contain another type argument T2 if T2 is
> used in a type declaration that appears in T1. For example, T2 contains
> T1 in `Foo<T1 extends Bar<T2>>`.
>
> The direct supertype relationship is used in the definitions of narrowing
> reference conversion, method invocation type inference, and cast
> conversion.

**Key impact for JADE migration:** JADE's `jade.util.leap.*` package provides
MIDP/J2ME-compatible collection types (`jade.util.leap.List`,
`jade.util.leap.ArrayList`, `jade.util.leap.Map`, `jade.util.leap.HashMap`,
`jade.util.leap.Set`, `jade.util.leap.HashSet`, `jade.util.leap.LinkedList`,
`jade.util.leap.Iterator`) that mirror `java.util.*` but do NOT extend them.

**These LEAP types MUST NEVER be parameterized or replaced with java.util.*
equivalents.** They exist for platform compatibility and have different
bytecode signatures. The scanner must detect and skip any raw-type match
involving `jade.util.leap.*` types.

---

## 4. Java Language Features Added in J2SE 5.0 (Affecting 1.5 → 1.6)

From Oracle's official Java 5.0 release documentation:

- **Generics:** Provides compile-time type safety for collections and
  eliminates the need for most typecasts (parameterized types).
  Affects: `java.util.Vector`, `java.util.ArrayList`, `java.util.HashMap`,
  `java.util.Hashtable`, `java.util.LinkedList`, `java.util.HashSet`.

- **Enhanced for Loop:** New language syntax for iterating over collections
  and arrays without explicit iterators or index variables. Eliminates
  common off-by-one errors and iterator boilerplate.

- **Autoboxing/Unboxing:** Automatic conversion between primitive types and
  their wrapper classes. (Not relevant for this migration phase — deferred
  to a later pass.)

- **Typesafe Enums:** Full class-based enums replacing integer constant
  patterns. (Not relevant for this migration phase — deferred.)

- **Varargs:** Methods with variable-length argument lists using `Type...`
  syntax. (Not relevant for this migration phase — deferred.)

- **Static Import:** Allows static members to be imported directly.
  (Not relevant for this migration phase.)

**Priority for JADE 1.5 → 1.6 migration:**
1. **HIGH:** Raw types → generics (eliminates unchecked warnings, improves type safety)
2. **MEDIUM:** Indexed for-loops → enhanced-for (improves readability, prevents bugs)

Other features (autoboxing, enums, varargs) are deferred to later migration
passes to keep each pass focused and verifiable.
