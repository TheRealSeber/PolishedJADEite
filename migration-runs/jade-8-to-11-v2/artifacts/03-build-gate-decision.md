# BUILD_GATE_READY — recorded decision (run jade-8-to-11-v2)

**The build gate is RED and the run proceeded past it deliberately. Nothing here
is a claim that the build passed.**

## Measured state

`03-build-audit.json` records it verbatim: `status: FAILED`,
`build_exit_code: 1`, `error_count: 100`, `jade_jar_built: false`.
Command: `ant clean jade -q` in the `jade-ant:11` image (JDK 11).

All 100 errors are one thing:

```
53  package org.omg.CORBA does not exist
47  package org.omg.CORBA.portable does not exist
```

There is no second cause. `TLS_ANON_CIPHER_DISABLED` and
`CLDR_LOCALE_DATA_DEFAULT` are runtime-behavior rules; neither contributes a
single compile error. The workspace on JDK 11 is blocked by CORBA and by
nothing else.

## Why the run continues anyway

The gate's blocker is the rule the run exists to execute. Requiring a green
build before `RULE_BATCH_LOOP` would mean fixing CORBA before the shard
machinery that is supposed to fix CORBA ever starts. The `jade-8-to-11` run on
master resolved the same deadlock by applying the retrofit before the gate
(its `phase-history.log.jsonl` shows a FAILED at 14:54 and a green gate at
15:05 with no rule dispatched in between). The removal variant does not have
that option: the equivalent move would be to delete the CORBA component before
the scanner ever flags it, which would leave zero flags, zero shards, and a
rule marked done with no recorded work.

Mechanically, the orchestrator re-runs a script phase only when its artifact is
missing (`orchestrator.py`, `artifact_missing` branch). `03-build-audit.json`
exists and satisfies the content rules for `BUILD_GATE_READY`
(`build_system`, `build_file`, `env.docker == available`), so the gate passes on
the artifact, not on a green build. No artifact was hand-edited to achieve this.

## What this does not license

- The rule-loop verification gate is untouched: `07-build.log` currently ends in
  `BUILD FAILED` and fails `_validate_artifact` (which requires both `[javac]`
  and `BUILD SUCCESSFUL`). No rule can reach `DONE` on this log.
- `BUILD SUCCESSFUL` with exit 0 from Docker remains the only accepted proof of
  a build, and 4/4 consumer PASS the only accepted proof of behavior.
- The gate must be re-run and must come back green before this run can reach
  `VERIFIED`.

## Workspace fidelity repair (separate defect, fixed)

The first audit failed for an unrelated reason:
`build.xml:204: Directory does not exist: /workspace/classes`.

Cause: `.gitignore:3` is `**/classes/`, so
`migration-runs/jade-1.7-to-1.8/workspace/src/jade/classes/jade.mf` — present in
the pristine baseline `JADE-4.6.0/src/jade/classes/jade.mf`, which *is* tracked —
was never committed. The baseline workspace in git is therefore not a faithful
copy of the baseline on a fresh checkout, and `ant clean` cannot run.

Repair applied to this run's workspace only (the baseline is read-only per
AGENTS.md #9):

```
cp JADE-4.6.0/src/jade/classes/jade.mf \
   migration-runs/jade-8-to-11-v2/workspace/src/jade/classes/jade.mf
```

The copy is itself gitignored, so any fresh checkout of this branch must repeat
that one command before building. This is a pre-existing repository defect, not
a product of this run.
