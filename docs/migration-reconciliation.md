# What the three jumps delivered, against what was forecast

The scoping pass in early September estimated the work left in each remaining
jump. The jumps were then executed. This records where the two agree, where
they diverge, and why — because the divergences are the interesting part, and
a reviewer meeting the numbers cold will otherwise assume something was
skipped.

| jump | forecast | delivered | build | consumers |
|---|---|---|---|---|
| 1.6 → 1.7 | 114 sites / 64 files | 115 sites / 50 files | exit 0 | 4/4 |
| 1.7 → 1.8 | 72 sites / 28 files | 179 lambdas / 64 files | exit 0 | 4/4 |
| 8 → 11 | 340 sites / 45 files | 43 files deleted | exit 0 | 4/4 |

All three runs reach `DONE`. Coverage is checkable rather than asserted:

```bash
python3 scripts/verify_delivery.py migration-runs/jade-1.6-to-1.7-v2
```

The script walks a run's artifacts and reports, per rule, flags raised against
results recorded, counting a deleted file as resolving the flags it carried.
All three runs report *every raised flag is accounted for*.

## 1.6 → 1.7 — matched on sites, not on files

115 sites against a forecast of 114. The file count came in lower, 50 against
64, because sites cluster: a single file often carries several diamond
conversions.

## 1.7 → 1.8 — the forecast could not see the work

179 conversions against a forecast of 72. The estimate was made before the
scanner could match a multi-line pattern.

`LAMBDA_CONVERSION` had been sitting in the manifest producing zero flags
across 1017 scanned files. The scanner read each file with `readlines()` and
searched line by line; an anonymous SAM class spans several lines, so the
pattern could never match. Once patterns could opt into `multiline`, the rule
found 384 sites, of which 179 converted and the rest were genuine refusals —
an anonymous class with a field, an interface with more than one abstract
method, a class whose constructor does real work, a body referring to its own
`this`.

Forecasting from a scanner that cannot see a construct will always
underestimate that construct.

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
became 43 deletions. The remaining seven sites were the two other rules:
`TLS_ANON_CIPHER_DISABLED`, fixed by reporting the JDK policy conflict rather
than re-enabling anonymous cipher suites, and `CLDR_LOCALE_DATA_DEFAULT`,
withdrawn on evidence.

## Two rules withdrawn rather than applied

Withdrawal is recorded in the manifest under `withdrawn_rules`, with the
reasoning, so a later run does not re-raise them without reading why.

**`THREAD_STOP_DISABLED`** — `java.lang.Thread.stop()` is `final`, so JADE
cannot override it, and all 14 flags resolve to JADE's own `stop()` methods.
The true hit count is zero. The run in `master` recorded all 14 as FIXED with
no lines of code changed.

**`CLDR_LOCALE_DATA_DEFAULT`** — the entire behaviour change is one comma in a
debug GUI timestamp: COMPAT renders `11/14/23 10:13 PM`, CLDR renders
`11/14/23, 10:13 PM`. The available fix hard-codes the English COMPAT pattern,
which stops the tools honouring the operator's locale — a worse outcome than
the comma it avoids.

## Why the forecast was wrong in a useful way

Both large divergences come from the same place: the estimate was built from
what the tooling could then observe. A scanner blind to multi-line constructs
under-counts them; a cost model assuming every flagged site needs an edit
over-counts a set that turns out to be deletable. Neither is a case of work
skipped, and the coverage script is there so that claim can be checked instead
of believed.
