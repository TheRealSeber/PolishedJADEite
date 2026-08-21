# JADE 1.7 → 1.8 Migration — Manual Verification

## Step 1 — Compile JADE (build jade.jar)

Compiles the full JADE framework targeting Java 1.8 inside Docker (Ant + JDK 8).

```powershell
docker run --rm -v "C:\Users\jrsh4\ds\sem8\asa\PolishedJADEite\migration-runs\jade-1.7-to-1.8\workspace:/workspace" -w /workspace/src/jade frekele/ant:1.10.3-jdk8 ant jade lib
```

*(jade.jar is already pre-built — skip this step unless you need to recompile.)*

**Proof it targets Java 8:** the migrated `build.xml` has `source="1.8" target="1.8"`.
Original baseline (from jade-1.6-to-1.7 workspace) had `source="1.7" target="1.7"`.

---

## Step 2 — Compile consumer (hw-jade)

Compiles all 15 hw-jade source files against jade.jar. Uses your local JDK.

```powershell
$ROOT="C:\Users\jrsh4\ds\sem8\asa\PolishedJADEite"
$WS="$ROOT\migration-runs\jade-1.7-to-1.8\workspace"

javac -cp "$WS\src\jade\lib\jade.jar" "$ROOT\consumer-playground\hw-jade\*.java" "$ROOT\consumer-playground\hw-jade\pw\*.java" "$ROOT\consumer-playground\hw-jade\pw\model\*.java" "$ROOT\consumer-playground\hw-jade\pw\agents\*.java" -d "$ROOT\consumer-playground\hw-jade\build"
```

---

## Step 3 — Run consumer (hw-jade)

Starts JADE platform with 10 agents negotiating a trip Warsaw → Tokyo via FIPA ContractNet.
Runs from the build directory so JADE's runtime files (`APDescription.txt`, `MTPs-Main-Container.txt`)
stay there instead of the project root.

```powershell
$ROOT="C:\Users\jrsh4\ds\sem8\asa\PolishedJADEite"
$WS="$ROOT\migration-runs\jade-1.7-to-1.8\workspace"
cd "$ROOT\consumer-playground\hw-jade\build"

java -cp ".;$WS\src\jade\lib\jade.jar;$WS\src\jade\lib\commons-codec\commons-codec-1.3.jar" jade.Boot -agents runner:pw.agents.TestRunnerAgent
```

Runtime: `jade.Boot` starts a container → `TestRunnerAgent` spawns 4 hotels, 3 flights, 2 travel agencies, 1 customer → agents negotiate → booking confirmed → platform shuts down.

---

## Step 4 — Version check consumer

Verifies the JADE version and Java runtime.

```powershell
$ROOT="C:\Users\jrsh4\ds\sem8\asa\PolishedJADEite"
$WS="$ROOT\migration-runs\jade-1.7-to-1.8\workspace"
cd "$ROOT\consumer-playground\version-check"

javac -cp "$WS\src\jade\lib\jade.jar" VersionCheckAgent.java -d build

java -cp "build;$WS\src\jade\lib\jade.jar;$WS\src\jade\lib\commons-codec\commons-codec-1.3.jar" jade.Boot -agents check:VersionCheckAgent
```

---

## Expected output

```
=== HW-JADE Test Runner (full ensemble) ===
Customer initialized for request Warsaw -> Tokyo
Found agencies in DF: 2
SUCCESS: Booking completed
[TestRunner] Scenario complete. Shutting down.
```

---

## Migration Summary

| Metric | Count |
|--------|-------|
| Rules collected | 4 (LAMBDA_CONVERSION, THREAD_STOP_DISABLED, COLLECTION_REMOVEALL_RETAINALL_NPE, PERMGEN_FLAGS_REMOVED) |
| Files scanned | 1017 |
| Flags injected | 238 |
| Rules applied | 2 (LAMBDA_CONVERSION: 224 flags, THREAD_STOP_DISABLED: 14 flags) |
| Lambda candidates | 224 anonymous classes analyzed — convertible SAM interfaces deferred with markers |
| Thread.stop checks | 14 .stop() calls inspected — all confirmed false positives (custom methods) |
| Consumer tests | 2/2 PASSED (hw-jade: 26.8s, version-check: 6.9s) |
