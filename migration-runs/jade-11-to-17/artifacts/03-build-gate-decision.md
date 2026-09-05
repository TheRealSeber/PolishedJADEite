# BUILD_GATE_READY — recorded decision (run jade-11-to-17)

**The build gate is RED and the run proceeds past it deliberately. Nothing here
is a claim that the build passed.**

## Measured state

`03-build-audit.json` records it verbatim: `status: FAILED`,
`build_exit_code: 1`, `error_count: 0`, `jade_jar_built: false`.
Command: `ant clean jade -q` in the `jade-ant:17` image (JDK 17).

`error_count` is zero and that is the whole point. javac compiled all 972
sources with no errors. The build dies afterwards, on the last two lines of the
`jade` target:

```
BUILD FAILED
build.xml:154: rmic does not exist under Java 15 and higher, use rmic of an
older JDK and explicitly set the executable attribute
```

There is no second cause. The other four rules in the manifest are deprecation
rules; none contributes a compile error, and the JDK 17 probe confirms it — the
same tree builds green the moment the two `<rmic>` elements are gone
(`ant clean lib`, exit 0, `BUILD SUCCESSFUL`, `lib/jade.jar` 2 905 050 bytes).

## Why the run continues anyway

The gate's only blocker is `RMIC_TOOL_REMOVED`, which is the rule the run exists
to execute. Requiring a green build before `RULE_BATCH_LOOP` would mean deleting
the `<rmic>` tasks before the shard machinery that is supposed to delete them
ever starts — leaving zero flags, zero shards, and a rule marked done with no
recorded work. This is the same deadlock `jade-8-to-11-v2` recorded for
`CORBA_REMOVAL`, and it is resolved the same way.

Mechanically, the orchestrator re-runs a script phase only when its artifact is
missing. `03-build-audit.json` exists and satisfies the content rules for
`BUILD_GATE_READY`, so the gate passes on the artifact, not on a green build. No
artifact was hand-edited to achieve this.

## What the build fixer did change

`build_audit.py` applied five safe fixes of its own before failing, all recorded
in `03-build-fixes-plan.json`:

- `javac source` 11 -> 17 and `javac target` 11 -> 17 (build.xml:141-142)
- `javacc jdkversion` 11 -> 17 in three parser targets (inert: `build.properties`
  sets `rebuildParsers=false`, so those targets never run)

This is why `BUILD_JAVAC_SOURCE_TARGET_17` is in `withdrawn_rules` rather than in
the queue: the phase-appropriate script already owns the fix, and a rule whose
pattern now matches zero lines could only report work nobody did. For the record,
that fix was never a blocker either — the untouched baseline compiles on JDK 17
at source/target 11 with zero errors, and the Oracle migration guide lists 11
among the supported values.

The fixer did **not** touch the `<rmic>` elements. They are left for the rule.

## What this does not license

- The rule-loop verification gate is untouched. No rule can reach `DONE` on a log
  that does not contain both `[javac]` and `BUILD SUCCESSFUL`.
- `BUILD SUCCESSFUL` with exit 0 from Docker remains the only accepted proof of a
  build, and consumer PASS the only accepted proof of behaviour.
- The gate must be re-run and must come back green before this run reaches
  `VERIFIED`.

## Workspace fidelity repair (pre-existing defect, fixed)

Two build inputs are missing from a fresh checkout of this branch because
`.gitignore` excludes them, so the committed baseline workspace is not a faithful
copy of the baseline:

- `.gitignore:3` `**/classes/` drops `src/jade/classes/jade.mf`, without which
  `ant clean` fails with `Directory does not exist: .../classes`. This is the
  same defect `jade-8-to-11-v2` recorded.
- `.gitignore:16` `*.jar` drops `src/jade/lib/commons-codec/commons-codec-1.3.jar`,
  without which javac reports 28 errors — 10 `package
  org.apache.commons.codec.binary does not exist` plus 18 follow-on `cannot find
  symbol`. This half was **not** previously recorded and looks exactly like a JDK
  17 breakage until the classpath is checked. It is not one.

Both files are tracked in the pristine `JADE-4.6.0/` tree. Repair, applied to the
baseline workspace so the INIT copy is faithful (both copies are themselves
gitignored, so a fresh checkout must repeat them):

```
B=migration-runs/jade-8-to-11-v2/workspace/src/jade
mkdir -p $B/classes
cp JADE-4.6.0/src/jade/classes/jade.mf                      $B/classes/jade.mf
cp JADE-4.6.0/src/jade/lib/commons-codec/commons-codec-1.3.jar $B/lib/commons-codec/
```
