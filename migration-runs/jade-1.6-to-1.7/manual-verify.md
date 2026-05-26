# JADE 1.6 → 1.7 Migration — Manual Verification

## Step 1 — Compile JADE (build jade.jar)

Compiles the full JADE framework targeting Java 1.7 inside Docker (Ant + JDK 8).
Produces `jade.jar` at `migration-runs/jade-1.6-to-1.7/workspace/src/jade/lib/jade.jar`.

```powershell
docker run --rm -v "C:\Users\jrsh4\ds\sem8\asa\PolishedJADEite\migration-runs\jade-1.6-to-1.7\workspace:/workspace" -w /workspace/src/jade frekele/ant:1.10.3-jdk8 ant jade lib
```

*(jade.jar is already pre-built — skip this step unless you need to recompile from scratch.)*

---

## Step 2 — Compile consumer (hw-jade)

Compiles all 15 hw-jade source files against jade.jar. Uses your local JDK.

```powershell
$ROOT="C:\Users\jrsh4\ds\sem8\asa\PolishedJADEite"
$WS="$ROOT\migration-runs\jade-1.6-to-1.7\workspace"

javac -cp "$WS\src\jade\lib\jade.jar" "$ROOT\consumer-playground\hw-jade\*.java" "$ROOT\consumer-playground\hw-jade\pw\*.java" "$ROOT\consumer-playground\hw-jade\pw\model\*.java" "$ROOT\consumer-playground\hw-jade\pw\agents\*.java" -d "$ROOT\consumer-playground\hw-jade\build"
```

---

## Step 3 — Run consumer (hw-jade)

Starts JADE platform with 10 agents negotiating a trip Warsaw → Tokyo via FIPA ContractNet.

```powershell
$ROOT="C:\Users\jrsh4\ds\sem8\asa\PolishedJADEite"
$WS="$ROOT\migration-runs\jade-1.6-to-1.7\workspace"

java -cp "$ROOT\consumer-playground\hw-jade\build;$WS\src\jade\lib\jade.jar;$WS\src\jade\lib\commons-codec\commons-codec-1.3.jar" jade.Boot -agents runner:pw.agents.TestRunnerAgent
```

Runtime: `jade.Boot` starts a container → `TestRunnerAgent` spawns 4 hotels, 3 flights, 2 travel agencies, 1 customer → agents negotiate → booking confirmed → platform shuts down.

---

## Expected output

```
=== HW-JADE Test Runner (full ensemble) ===
Customer initialized for request Warsaw -> Tokyo
Found agencies in DF: 2
SUCCESS: Booking completed
[TestRunner] Scenario complete. Shutting down.
```
