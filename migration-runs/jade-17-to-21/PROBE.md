# JDK 21 probe — what the 17 tree does before any rule is written

Reconnaissance, run before the manifest. The 11-to-17 jump found that `<rmic>`
was the only thing standing between the tree and a JDK 17 build; everything
else in that window compiled. This probe asks the same question of 21, against
evidence rather than release notes.

Baseline probed: `migration-runs/jade-11-to-17/workspace` — the verified output
of the 11-to-17 run (DONE, `BUILD SUCCESSFUL`, 4/4 consumers). 972 `.java` files.
Toolchain: `jade-ant:21` = `maven:3.9-eclipse-temurin-21` + Ant, giving
Temurin 21.0.12 LTS and Ant 1.10.14. Raw logs in `probe-logs/`.

## Result

| probe | command | outcome |
|---|---|---|
| build as-is, `source/target=17` | `ant clean lib` in `jade-ant:21` | **BUILD SUCCESSFUL**, exit 0 |
| build at `source/target=21` | same, build.xml bumped to 21 | **BUILD SUCCESSFUL**, exit 0, **0 errors** |
| bytecode emitted | `javap -v jade/core/Agent.class` | major version **65** |
| 4 consumers on JDK 21 | `runtime_verify.py` | **4/4 PASS** |

**Nothing in the 17-to-21 window stops this build.** The tree compiles on a
JDK 21 toolchain untouched, and also when the language level is raised to 21.
That is a different shape of jump from 11-to-17, which had one hard build
blocker, and from 8-to-11, which had CORBA.

A useful side effect: because `source=21` compiles with zero errors, **JEP 431
(Sequenced Collections) is empirically ruled out**. `jade.util.leap` reimplements
List, Map, SortedSet and friends, which is exactly the shape that clashes with
the retrofitted `java.util` interfaces — but the leap hierarchy is parallel to
`java.util` rather than derived from it, so nothing inherits the new methods.
Four independent probes reached the same conclusion by reading; the compiler
settles it.

## The measured 17-to-21 delta

Counting warnings needs two corrections that each change the answer:

- **javac stops at 100 warnings.** Two earlier probe runs both reported exactly
  "100 warnings" and disagreed about which ones. All counts below use
  `-Xmaxwarns 100000`.
- **JADE's build suppresses lint.** `build.xml:136` sets `nowarn="on"`, which is
  `-Xlint:none`; `deprecation="on"` then re-enables only the deprecation family.
  Whole categories are invisible in a stock build. Counts below use
  `nowarn="off"`.

With both corrected, the same tree built with the same flags on each toolchain:

| category | JDK 17 | JDK 21 |
|---|---:|---:|
| `[deprecation]` | 114 | 127 |
| `[dep-ann]` | 47 | 47 |
| `[removal]` | 1 | 6 |
| `[synchronization]` | 2 | 2 |

Diffing the warnings site by site rather than comparing totals gives the actual
window — everything JDK 18, 19, 20 or 21 added for this tree, and nothing else:

| what | sites | files | JDK | kind |
|---|---:|---:|---|---|
| `new URL(String)` and `new URL(String,String,int,String)` | 12 | 7 | 20 | deprecated |
| `finalize()` overrides — **escalated** `[deprecation]` → `[removal]` | 4 | 3 | 18, JEP 421 | deprecated for removal |
| `Thread.getId()` → `threadId()` | 3 | 1 | 19 | deprecated |
| `Runtime.exec(String)` | 2 | 1 | 18 | deprecated |
| `ThreadDeath` | 1 | 1 | 20 | deprecated for removal |

**18 genuinely new sites, plus 4 finalize overrides that changed severity.**
That is the entire compiler-visible cost of the jump.

Everything else in the warning list is pre-existing at 17 and out of window:
the 61 `Class.newInstance()` sites (deprecated in 9 — the 11-to-17 manifest
already withdrew that rule as belonging to the 8-to-11 ledger), the ~25
Swing/AWT deprecations in the debug GUI, the 8 `Observer`/`Observable` uses,
and the single `new Boolean(boolean)`.

### The two synchronization warnings are older than this jump

`jade/gui/GuiAgent.java:94` and `:154` synchronize on a value-based class. They
fire identically on javac 17 and javac 21, so they are **not** a 17-to-21 item.
They are listed here because the 11-to-17 manifest withdrew
`VALUE_BASED_CLASS_SYNCHRONIZATION` with the reason *"every synchronized(...)
lock expression in the tree was enumerated; all are ordinary objects and
dedicated monitor fields, none is a primitive wrapper. javac on 17 emitted no
synchronization warning."*

The second sentence is true of JADE's build as shipped — `nowarn="on"` disables
the category. It is not true of the toolchain: javac 17 warns on these two
sites the moment lint is enabled. The withdrawal was reached from a build
configured not to show the evidence.

The site itself is worth reading before anyone touches it:

```java
private Boolean guiEventQueueLock;          // line 77
guiEventQueueLock = new Boolean(true);      // line 140  -> [removal]
synchronized (guiEventQueueLock) { ... }    // lines 94, 154 -> [synchronization]
```

One object trips both warnings, and the obvious fix is a bug. Rewriting line 140
as `Boolean.valueOf(true)` silences the removal warning and returns the cached
JVM-wide `Boolean.TRUE` — every `GuiAgent` in the process would then share one
monitor with each other and with any other library that locks on `Boolean.TRUE`.
The correct fix is `private final Object guiEventQueueLock = new Object();`,
which clears both warnings and removes the latent contention. The 11-to-17 run
flagged this line as `WRAPPER_CONSTRUCTOR_DEPRECATED_FOR_REMOVAL` and skipped
it; the skip was right.

## What the compiler cannot see: JEP 400

A separate reconnaissance pass — nine probes across the JDK 18-21 change
surface, each candidate then handed to an adversarial verifier instructed to
refute it — raised 72 rule candidates and killed 60 of them. The 12 survivors
are dominated by one change that produces **no warning at either version**.

JEP 400 (JDK 18) switched every charset-less text API from the platform default
charset to UTF-8: `new String(byte[])`, `String.getBytes()`, `FileReader`,
`FileWriter`, `InputStreamReader`, `PrintStream(File|OutputStream)`. The code
compiles identically. The bytes change.

| rule | sites | files | severity |
|---|---:|---:|---|
| `JEP400_JICP_IMTP_TRANSPORT_DEFAULT_CHARSET` | 47 | 18 | HIGH |
| `JEP400_FILE_PERSISTENCE_AND_CONFIG_DEFAULT_CHARSET` | 26 | 13 | MEDIUM |
| `JEP400_ACL_AND_CONTENT_WIRE_CODEC_DEFAULT_CHARSET` | 7 | 4 | HIGH |
| `JEP400_STDIN_AND_URL_STREAM_READERS` | 5 | 5 | LOW |
| `JEP400_SOCKET_PRINTSTREAM_TEXT_PROTOCOL` | 3 | 3 | MEDIUM |
| `JEP400_FILE_PRINTSTREAM_CSV_AND_LOG` | 3 | 1 | LOW |

**91 sites across 44 files, none of which the compiler will ever mention.**

### Why the two HIGH rules are HIGH

The FIPA *string* ACL representation is charset-explicit and needs no change:
`jade/lang/acl/ACLCodec.java:38` declares `DEFAULT_CHARSET = "US-ASCII"`, the
encode and decode signatures both carry a `String charset` parameter, and
`StringACLCodec` honours it on both sides (`:327` `getBytes(charset)`, `:341`
`new InputStreamReader(..., charset)`).

The *binary* LEAP representation does not. `LEAPACLCodec.java:52` and `:73`
document the charset parameter as *"This parameter is not taken into account"*,
and the implementation drops it — `:175` `content.getBytes()`, `:233`
`new String(content)` both fall through to the platform default. That codec is
the default wire format (`OutgoingEncodingFilter.java:172` sets
`defaultRepresentation = LEAPACLCodec.NAME`) and is called directly by the JICP
transport. The same defect repeats one layer up in
`jade/content/lang/leap/LEAPCodec.java:420/:459`, where the surrounding code
uses `readUTF`/`writeUTF` and only falls back to raw `getBytes()` for strings
over 65535 bytes — so it bites on large payloads and hides in small ones.

`JICPPacket.java:245/:298/:354` and 44 further sites encode recipient IDs and
addresses on the JICP wire the same way.

The consequence is a **cross-version wire incompatibility**, not a crash: a
JADE 21 node encodes non-ASCII content as UTF-8, a JADE 17 node on a
Windows-1252 or Shift_JIS host decodes it as its own platform default, and
every non-ASCII character silently mojibakes. The 4/4 consumer pass above does
not exercise it — the consumers are all-ASCII and single-version.

### What was raised and refuted

60 of 72 candidates died under verification, including every candidate in five
whole areas. Recorded so a later run does not re-raise them:

- **Thread and ThreadGroup lifecycle** — all 7 candidates, zero sites. Same
  discipline that correctly withdrew `THREAD_STOP_DISABLED` earlier: the hits
  are JADE's own `stop()`/`suspend()` on its own types.
- **Security Manager / JEP 411** — all 7, zero sites. No `SecurityManager`,
  `doPrivileged` or `AccessController` anywhere.
- **Strong encapsulation and reflection / JEP 396, 451** — all 7, zero sites.
- **Sequenced Collections / JEP 431** — all 3, zero sites, and the compiler agrees.
- **Applet API** — still present in 21 (removed in 25), compiles with no error
  and no warning. Not a 21 rule.
- **`Class.newInstance()`** — 61 real sites, but unchanged between 17 and 21 and
  already withdrawn as out-of-window by the 11-to-17 manifest.
- **`CLDR_LOCALE_DATA_FORMATTED_OUTPUT`** — re-raised at 5 sites; this is
  `CLDR_LOCALE_DATA_DEFAULT` under a new name, withdrawn on evidence in the
  8-to-11 run because the whole behaviour change is one comma in a debug GUI
  timestamp and the available fix hard-codes English. That reasoning still
  holds. Withdraw again.

## Two toolchain constraints, found by running rather than reading

**1. Raising JADE to bytecode 65 breaks the consumer compile step on this host.**
`runtime_verify.py` resolved the consumer compiler with `shutil.which("javac")`.
Here that is JDK 17, which cannot read a v65 class file at all, so all four
consumers failed with `class file has wrong version 65.0, should be 61.0` —
which reads as a JDK 21 incompatibility in the migrated library and is nothing
of the kind. The script now reads the class-file version out of the workspace
jars and picks a compiler that can read them (`JADE_CONSUMER_JAVAC`, then
`JAVA_HOME`, then `PATH`), reporting an environment error naming the requirement
instead of a wall of import failures.

**2. `runtime_java_version` was pinned to 17 on two consumers.** `hw-jade` and
`jrba` overrode the run's target and would have run JDK 21 artifacts on a JDK 17
JVM. Both are now 21. `jrba` deliberately stays compiled at `release 17` while
running on 21 — that combination is the closest thing the playground has to a
downstream user who has not moved their own language level.

With both corrected, against a bytecode-65 `jade.jar` on `jade-ant:21`:

```
[PASS] hw-jade (22.9s)   [PASS] jrba (26.4s)
[PASS] restaurant-recommendation (11.5s)   [PASS] version-check (4.3s)
```

## Open decision: does "migrate to 21" mean bytecode 21?

The probe establishes both halves independently:

- The existing bytecode-61 jar runs on a JDK 21 JVM, 4/4 consumers passing.
- A bytecode-65 jar also runs, 4/4 consumers passing, once the consumer
  toolchain is new enough.

So this is a product decision, not a technical blocker. Emitting 65 drops every
downstream user still on a JDK below 21 — the consumer failures above are a
small model of exactly that. Staying at 61 keeps that audience and still gets a
library that runs on 21. It belongs to the maintainer, not to the pipeline.

Nothing here has been decided or applied. The workspace has not been created.
