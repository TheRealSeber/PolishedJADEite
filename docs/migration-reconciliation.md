# What the jumps delivered, against what was forecast

A scoping pass in early September estimated the work left in three remaining
jumps. Those three were executed, and two more followed. This records where
forecast and delivery agree, where they diverge, and why — because the
divergences are the interesting part, and a reviewer meeting the numbers cold
will otherwise assume something was skipped.

## How these numbers were measured

Every figure below comes from one method applied to all five runs: compare the
run's baseline tree with its workspace, **filtering `JADE-FLAG:` and
`JADE-MODERNIZATION-DEFERRED:` lines out of both sides**, and count files whose
remaining lines differ.

That filter is not a detail. An earlier pass filtered markers only on the added
side, so removing 2548 old flag comments counted as real change and the same
run measured 345 files instead of 22. A file that differs *only* by a marker is
not a changed file, and a run that injects markers everywhere will look like it
rewrote the tree if you let it.

| jump | forecast | files changed | files deleted | lines |
|---|---|---:|---:|---|
| 1.6 → 1.7 | 114 sites / 64 files | 50 | 0 | +460 / −541 |
| 1.7 → 1.8 | 72 sites / 28 files | 65 | 0 | +478 / −1075 |
| 8 → 11 | 340 sites / 45 files | 3 | **43** | +45 / −4 |
| 11 → 17 | *none recorded* | 56 | 0 | +157 / −154 |
| 17 → 21 | 113 sites / ~50 files | 14 | 0 | +38 / −49 |

All five runs reach `DONE` with `BUILD SUCCESSFUL` and exit 0 from Docker, and
4/4 consumers passing. Coverage is checkable rather than asserted:

```bash
python3 scripts/verify_delivery.py migration-runs/<run>
```

Each run reports *every raised flag is accounted for*.

## 1.6 → 1.7 — matched on sites, not on files

115 sites fixed against a forecast of 114: 57 diamond operators, 52
try-with-resources, 6 switch-on-string. The file count came in lower, 50 against
64, because sites cluster — a single file often carries several diamonds.

The 51 sites deliberately not converted (38 try-with-resources, 12 switch, 1
diamond) are recorded with reasons, not dropped.

## 1.7 → 1.8 — the forecast could not see the work

The forecast said 72 sites. **200 anonymous classes became lambdas**, counted
directly from the source rather than from a status field: the changed files hold
200 fewer `new X() {` openings and 224 more `->` arrows.

`LAMBDA_CONVERSION` had been sitting in the manifest producing **zero** flags
across 1017 scanned files. The scanner read each file with `readlines()` and
searched line by line; an anonymous SAM class spans several lines, so the
pattern could never match. Once patterns could opt into `multiline`, the rule
found 399 sites, and the refusals are as interesting as the conversions — an
anonymous class with a field, an interface with more than one abstract method, a
constructor that does real work, a body referring to its own `this`.

Forecasting from a scanner that cannot see a construct will always
underestimate that construct.

> An earlier version of this document reported 179 conversions. That figure came
> from a status tally rather than from the source, and it was low. The direct
> count is 200.

## 8 → 11 — the fix was not the one costed

The forecast assumed 340 discrete edits across 45 files, and priced rewriting
public signatures, because 333 of those sites were `CORBA_REMOVAL` flags on
`Helper` and `Holder` classes whose method signatures name `org.omg` types.

Reconnaissance changed the shape of the work. The CORBA set is 43 files: 42
generated IDL stubs under `FIPA/` and the single `jade/mtp/iiop`
implementation. The knowledge graph shows **zero incoming edges** into those
files from the other 972 — no imports, extends, implements, calls or type
refs. IIOP is one of two message transports behind `jade.mtp.MTP`, HTTP is the
default in `ProfileImpl`, and no consumer selects it.

Signatures in a file that gets deleted do not need rewriting. 340 costed edits
became 43 deletions. The remaining sites were the two other rules:
`TLS_ANON_CIPHER_DISABLED`, closed by reporting the JDK policy conflict rather
than re-enabling anonymous cipher suites, and `CLDR_LOCALE_DATA_DEFAULT`,
withdrawn on evidence.

## 11 → 17 — no forecast to diverge from

This jump was not in the scoping pass. It found exactly one thing that stopped
the build: Ant's `<rmic>` task, driving a tool removed in JDK 15. Everything
else in the window compiled. 147 wrapper-constructor sites dominate the flag
count; 4 were skipped deliberately, including `GuiAgent.java:140`, where the
obvious fix is a bug (see below).

## 17 → 21 — the forecast was mine, and I narrowed it

`PLAN.md` proposed eleven rules, 113 sites across roughly 50 files, and called
rules 2–6 mechanical. Two of them were not.

`JEP400_JICP_IMTP_TRANSPORT_DEFAULT_CHARSET` (47 sites) and
`JEP400_SOCKET_PRINTSTREAM_TEXT_PROTOCOL` (3) encode bytes crossing a process or
node boundary. Pinning a charset there is the same protocol-compatibility
decision as the ACL wire codecs, and that decision belongs to the maintainer.
Applying UTF-8 would have foreclosed it. The run covers what is genuinely
mechanical — files JADE writes and reads back itself, plus the two removal rules
— and the narrowing is recorded in the rule queue's `decision` field.

The measurable result, same tree and same compiler flags before and after:

| javac category | before | after |
|---|---:|---:|
| `[removal]` | 6 | **1** |
| `[deprecation]` | 127 | 127 |
| `[synchronization]` | 2 | 2 |

All five in-window removal sites are gone. The survivor is `GuiAgent.java:140`,
`new Boolean(boolean)` used as a monitor — out of window (JEP 390, JDK 16), and
a trap: rewriting it as `Boolean.valueOf(true)` returns the shared JVM-wide
`Boolean.TRUE`, so every `GuiAgent` in the process would lock on one object.

## Rules withdrawn rather than applied

Withdrawal is recorded in each manifest under `withdrawn_rules`, with the
reasoning, so a later run does not re-raise them without reading why.

**`THREAD_STOP_DISABLED`** — `java.lang.Thread.stop()` is `final`, so JADE
cannot override it, and all 14 flags resolve to JADE's own `stop()` methods.
The true hit count is zero. The run on `master` recorded all 14 as FIXED with
no lines of code changed.

**`CLDR_LOCALE_DATA_DEFAULT`** — the entire behaviour change is one comma in a
debug GUI timestamp: COMPAT renders `11/14/23 10:13 PM`, CLDR renders
`11/14/23, 10:13 PM`. The available fix hard-codes the English COMPAT pattern,
which stops the tools honouring the operator's locale — a worse outcome than
the comma it avoids. Reconnaissance for 17 → 21 raised it again under a new
name; the same reasoning applies and it stays withdrawn.

Five whole areas were raised and refuted for 17 → 21 on zero true sites: Thread
and ThreadGroup lifecycle, the Security Manager, strong encapsulation, Sequenced
Collections, and the Applet API.

## Why the forecasts were wrong in a useful way

Every large divergence comes from the same place: the estimate was built from
what the tooling could then observe. A scanner blind to multi-line constructs
under-counts them. A cost model assuming every flagged site needs an edit
over-counts a set that turns out to be deletable. A plan written before the
recipe meets the code calls a wire-format change mechanical.

None of these is work skipped, and `verify_delivery.py` exists so that claim can
be checked instead of believed.
