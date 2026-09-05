# Independent re-verification of the CORBA-removal variant (jade-8-to-11-v2)

Run in a fresh session on 2026-09-05, against the workspace as committed at
`32b24c5` on `work/jump-811`. Every claim below was re-executed independently
in this session (not copied from earlier artifacts) unless explicitly marked
"cached artifact".

## 1. Docker build with zero CORBA jars on the classpath

Command:

```
docker run --rm -v <workspace>/src/jade:/workspace -w /workspace jade-ant:11 bash -c "ant clean lib"
```

The container's only classpath entry is `lib/commons-codec/commons-codec-1.3.jar`
(see `build.xml` line 135); no GlassFish/ORB jar exists anywhere in the image
or the mounted workspace. Last 40 lines:

```
    [javac] Note: Some input files additionally use or override a deprecated API.
    [javac] Note: Some input files use unchecked or unsafe operations.
    [javac] Note: Recompile with -Xlint:unchecked for details.
    [javac] 100 warnings
     [copy] Copying 119 files to /workspace/classes
     [rmic] RMI Compiling 1 class to /workspace/classes
     [rmic] Warning: generation and use of skeletons and static stubs for JRMP
     [rmic] is deprecated. Skeletons are unnecessary, and static stubs have
     [rmic] been superseded by dynamically generated stubs. Users are
     [rmic] encouraged to migrate away from using rmic to generate skeletons and static
     [rmic] stubs. See the documentation for java.rmi.server.UnicastRemoteObject.
     [rmic] RMI Compiling 1 class to /workspace/classes
     [rmic] Warning: generation and use of skeletons and static stubs for JRMP
     [rmic] is deprecated. Skeletons are unnecessary, and static stubs have
     [rmic] been superseded by dynamically generated stubs. Users are
     [rmic] encouraged to migrate away from using rmic to generate skeletons and static
     [rmic] stubs. See the documentation for java.rmi.server.UnicastRemoteObject.

lib:
   [delete] Deleting: /workspace/lib/jade.jar
      [jar] Building jar: /workspace/lib/jade.jar

BUILD SUCCESSFUL
Total time: 6 seconds
```

Exit code: `0`.

## 2. `org.omg` grep on sources

```
grep -rIn "org\.omg" <workspace>/src/jade   -> 0 matches
find <workspace>/src/jade/src/FIPA          -> No such file or directory
find <workspace>/src/jade/src/jade/mtp/iiop -> No such file or directory
```

Zero, as required.

## 3. `build.xml` / `build.properties` CORBA references

```
grep -n -i "corba\|idlj\|glassfish\|orb\b" build.xml   -> no match (exit 1)
lib/ contents: commons-codec/, jade.jar                -> no CORBA/GlassFish jar present
```

## 4. Runtime verification, all consumers, freshly re-run

Re-ran `runtime_verify.py` from scratch against the freshly rebuilt (step 1)
`jade.jar`:

```
python .claude/skills/jade-core-verification/scripts/runtime_verify.py \
  --workspace migration-runs/jade-8-to-11-v2/workspace \
  --artifacts /tmp/rtv-fresh-811 \
  --config migration-runs/jade-8-to-11-v2/artifacts/00-run-config.json
```

| consumer | status | duration | note |
|---|---|---|---|
| hw-jade | PASS | 22.8s | booted, full travel-agent scenario completes |
| jrba | PASS | 21.0s | all 4 JRBA scenarios pass, JDK 17 runtime |
| restaurant-recommendation | PASS | 16.9s | see caveat below |
| version-check | PASS | 4.3s | reports `java.version: 11.0.21` |

`overall_pass: true`, 4/4. jar entry count 1984, zero `FIPA/` or
`jade/mtp/iiop/` classes (`jar tf lib/jade.jar | grep -E 'FIPA/|jade/mtp/iiop/'`
-> no match).

**Caveat found and investigated (not a CORBA-removal regression):**
`restaurant-recommendation`'s captured stdout+stderr ends with a stray
`RESTAURANT_TEST_FAILED` line *after* `RESTAURANT_TEST_PASSED`. Root cause:
`BookingAgent.orderCompleted()` prints `RESTAURANT_TEST_PASSED` then spawns a
bare thread that sleeps 3s and calls `System.exit(0)`; `TestRunnerAgent`'s own
`OneShotBehaviour` is independently sitting in a 30s fallback `Thread.sleep`
wrapped in a broad `catch (Exception e)` that prints `RESTAURANT_TEST_FAILED`
and calls `System.exit(1)` on *any* exception, including whatever the JVM
teardown triggers in that second thread. This is a pre-existing race in the
consumer's own two-exit-path test design, not something introduced by CORBA
removal: the byte-identical trailing marker is present in the **original,
already-accepted retrofit run** (`migration-runs/jade-8-to-11/artifacts/07-runtime-verify.json`,
consumer `restaurant-recommendation`, PASS, same `RESTAURANT_TEST_FAILED` tail).
`test-config.json` only declares `expected_stdout_markers` (positive) for this
consumer, no `failure_stdout_markers`, so `runtime_verify.py` correctly (per
its own configured contract) does not fail on this marker; the container's
own exit code was 0 in both runs. Recommendation for a future pass: add
`"RESTAURANT_TEST_FAILED"` to this consumer's `failure_stdout_markers` and fix
the shutdown race (single exit path) — filed here for visibility, not fixed,
since it is out of scope for the CORBA-removal proof and predates it.

## 5. Test floor

```
pytest tests/ -q -> 485 passed, 2 skipped
```

Unchanged, matches the required floor.

## 6. Orchestrator resume attempt (this is the one negative finding)

The prior session left `00-run-state.json` at
`state=AWAITING_AGENT, current_rule_id=TLS_ANON_CIPHER_DISABLED`, explicitly
because it judged that running `dispatcher.py --emit-agent-tasks` for that
rule would trip the orchestrator's `SHARD_NEEDS_REVIEW_ACCEPTED` integrity
gate. This session reproduced that empirically rather than taking it on
faith:

```
dispatcher.py --rule-id TLS_ANON_CIPHER_DISABLED --emit-agent-tasks   # exit 0, writes 05-agent-tasks-*.json
orchestrator.py --config .../00-run-config.json --run
  -> ERROR [SHARD_NEEDS_REVIEW_ACCEPTED] Shard TLS_ANON_CIPHER_DISABLED-body-local-001
     of rule TLS_ANON_CIPHER_DISABLED is ACCEPTED in the ledger but its
     recorded fix status is NEEDS_REVIEW
  -> state: FAILED
```

This confirms the gate is real, not hypothetical: `orchestrator.py`'s
`_process_agent_rule` refuses to advance past *any* shard whose checkpoint
ledger says `ACCEPTED` while its `06-fix-results-*.json` entry says
`NEEDS_REVIEW` (both `TLS_ANON_CIPHER_DISABLED-body-local-001` and all four
`CLDR_LOCALE_DATA_DEFAULT` shards are in exactly that state — every
`BEHAVIOR_CHANGE`-category rule's shard is unconditionally marked
`NEEDS_REVIEW` by `dispatcher.py`, regardless of fix quality). There is no
"approve"/sign-off script anywhere under `.claude/skills/jade-core-*` that
reclassifies a `NEEDS_REVIEW` shard into something the gate accepts — the
only two paths the tooling offers are (a) roll the shard back, or (b) leave
it at `AWAITING_AGENT` for a human decision.

**Decision made this session:** did not fabricate a `DONE` state and did not
roll back the (working, independently-verified) TLS/CLDR shards just to
silence the gate. Reverted this session's own probe
(`00-run-state.json`, `PROGRESS.md`, `phase-history.log.jsonl` back to their
committed `AWAITING_AGENT` content via `git checkout`; deleted the
newly-created `05-agent-tasks-TLS_ANON_CIPHER_DISABLED.json` and
`failure-summary.json` scratch artifacts) so the run-state file continues to
honestly say what it said before this session touched it: blocked on a human
decision, not broken, not done.

**What actually needs a human answer before this run can reach `DONE`:**
1. TLS_ANON_CIPHER_DISABLED — keep the restored anonymous
   (unauthenticated) `TLS_ECDH_anon_WITH_AES_128_CBC_SHA` suite between JADE
   platforms, or require authenticated suites (a keystore/truststore
   architecture change, out of scope for this shard)?
2. CLDR_LOCALE_DATA_DEFAULT — keep the hard-coded COMPAT-equivalent
   `SimpleDateFormat` patterns in the 5 shard files, or switch to the
   JVM-wide `-Djava.locale.providers=COMPAT,CLDR` system property instead
   (a deployment-wide decision, also out of scope for a body-local shard)?

Once a decision is recorded for both, the correct next step is *not* to force
`--run` again — it will hit the same gate — but to have a human (or an agent
explicitly authorized to act as the reviewer) mark those two shards reviewed
through whatever review-recording mechanism gets added to the dispatcher, or
to accept the current `AWAITING_AGENT` pause as this run's terminal state for
now.

## Summary of this session's conclusion

CORBA removal itself (`CORBA_REMOVAL`, the HIGH-risk, mandatory rule) is
fully proven: real deletion (not exclusion), zero `org.omg` left, build green
without any CORBA/GlassFish jar anywhere in reach, 4/4 consumers pass on a
freshly rebuilt jar, floor maintained. That part is safe to call `DONE` on
its own merits. The run as a whole cannot honestly be marked `DONE` yet
because two unrelated, already-flagged `BEHAVIOR_CHANGE` rules
(TLS/CLDR) are sitting on a real, working-as-designed human-review gate —
this was verified, not assumed, and left exactly as found.
