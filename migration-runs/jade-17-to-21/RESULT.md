# 17 → 21: what the run did

State `DONE`. `BUILD SUCCESSFUL` exit 0 on `jade-ant:21` at `source/target=21`,
bytecode major 65, 4/4 consumers PASS. Coverage is checkable rather than
asserted:

```bash
python3 scripts/verify_delivery.py migration-runs/jade-17-to-21
```

It reports *every raised flag is accounted for*.

## Scope, and where it differs from PLAN.md

`PLAN.md` proposed eleven rules and called rules 2–6 mechanical. Two of them
were not, and the run does not include them.

`JEP400_JICP_IMTP_TRANSPORT_DEFAULT_CHARSET` (47 sites) and
`JEP400_SOCKET_PRINTSTREAM_TEXT_PROTOCOL` (3 sites) encode bytes that cross a
process or node boundary — JICP recipient IDs between containers, the
SocketProxyAgent text protocol to an external client. Pinning a charset there is
the same protocol-compatibility decision as the ACL and content wire codecs, and
that decision is the maintainer's. Applying UTF-8 would have foreclosed it.

What ran is the part that is genuinely mechanical: files JADE writes and reads
back itself, plus the two removal rules.

| rule | raised | edited | skipped | needs review |
|---|---:|---:|---:|---:|
| `JEP400_FILE_IO_DEFAULT_CHARSET` | 33 | 21 | 6 | 6 |
| `FINALIZE_DEPRECATED_FOR_REMOVAL` | 5 | 5 | 0 | 0 |
| `THREADDEATH_DEPRECATED_FOR_REMOVAL` | 1 | 1 | 0 | 0 |

14 files carry a real source change, +38/−49 lines, and 12 `JADE-FLAG` markers
are deliberately left in place. Every non-edit is named with its reason in
`artifacts/REVIEW_REQUIRED.md`.

Twenty files differ from the baseline if you diff them raw, but six of those
differ *only* by a retained marker comment. A file that differs only by a marker
is not a changed file; `docs/migration-reconciliation.md` explains why that
distinction is load-bearing and how all five runs are measured the same way.

## The measurable result

Same tree, same flags (`nowarn="off"`, `-Xlint:removal,deprecation`,
`-Xmaxwarns 100000`), before and after:

| category | before | after |
|---|---:|---:|
| `[removal]` | 6 | **1** |
| `[deprecation]` | 127 | 127 |
| `[dep-ann]` | 47 | 47 |
| `[synchronization]` | 2 | 2 |

All five in-window removal sites are gone. The one that remains is
`GuiAgent.java:140`, `new Boolean(boolean)` — JEP 390, JDK 16, out of window for
this jump and coupled to the shared-lock decision described in `PROBE.md`.

`[deprecation]` is unchanged by design: the twelve `new URL(...)`, three
`Thread.getId()` and two `Runtime.exec(String)` sites are deprecations, not
removals, JADE's build does not treat warnings as errors, and they were listed
as optional in `PLAN.md`.

## Four things the run found that reconnaissance had not

**The charset overload widens the checked exception.** `new FileReader(String)`
throws `FileNotFoundException`; `new FileReader(String, Charset)` throws
`IOException`. At `DummyAgentGui.java:218` and `ACLPanel.java:261` the enclosing
`try` catches only the narrow one, so the transform does not compile. Widening
those catches changes the user-facing error path, so both sites were left with
their markers and recorded `NEEDS_REVIEW`.

**Four sites read files JADE never writes.** `SocketProxyAgent.java:103` and
`Sniffer.java:568` read hand-authored `.inf` configuration; a tree-wide grep
finds readers and no writer. `AccessControlList.java:255` and `:266` read the
administrator's black/white list. Their encoding is not JADE's to pin.

**`finalize()` removal is a signature rule, not a body-local one.** The first
shard was planned `body-local`, and the signature gate rejected it: deleting a
declared member changes the node whatever calls it. The shard was rolled back,
the rule reclassified in the manifest, and the re-planned `signature` shard
carries the dependency closure and passes with 0 leaks. The earlier reasoning
— that nothing calls `JarClassLoader.finalize()` — was about reachability and
is still true; it just is not what the gate measures.

**`Server.finalize()` was never a finalizer in practice.** Its javadoc said
"try to clean up on GC", but `run()` calls it explicitly from a `finally` block,
so the body always ran on the normal path. It was renamed to `cleanup()` rather
than deleted, and the javadoc corrected.

## Three pipeline defects fixed to get here

Each has regression tests; the suite is 565 passed, 0 failed.

**The signature gate counted an added import as a signature change.** All 10
changed nodes in the charset shard differed by exactly one entry —
`java.nio.charset.StandardCharsets` — and nothing else. An import is file-local
name resolution that no dependent can observe, so it is now excluded from the
declaration signature, the same way line numbers already were. An import that
does change meaning by shadowing an in-tree type still shows up, because that
moves the file's `type_refs`/`calls` edges, and edges are diffed separately.

**Re-planning after a rollback deadlocked the ledger check.** It demanded exact
set equality between ledger keys and plan shard ids, but recovery from a
rejected shard means re-planning, and re-planning renames the shards. A ledger
entry outside the plan is now allowed when it is `ROLLED_BACK`; `CHECKPOINTED`
or `ACCEPTED` outside the plan is still a hard failure, because that would mean
live edits in a shard nobody is tracking.

**The build gate accepted a failed build.** `NEEDS_MANUAL` is reachable only
when `build_rc != 0`, yet it returned exit 0 and printed "Build succeeded",
and `03-build-audit.json` never checked its own recorded `build_exit_code`.
Both sides are closed.

## Still open, and still the maintainer's

1. **Bytecode 61 or 65.** The build gate set `source/target=21` because
   `target_version` is the compiler level in this pipeline; there is no
   supported way to run a 21 migration that emits 61. Reverting is two
   attributes in `build.xml`, and `PROBE.md` shows both levels pass 4/4.
2. **The wire charset** — the ACL and content codecs, the JICP/IMTP transport
   and the socket print streams, 57 sites in one decision.
3. **`GuiAgent.guiEventQueueLock`** — one object, one removal warning and both
   synchronization warnings; the obvious fix is a bug. See `PROBE.md`.
