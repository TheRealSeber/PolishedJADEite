# JRBA Consumer Validation Design

## Goal

Add JRBA as a reproducible consumer validation project that exercises a JADE
agent through the migrated workspace without requiring a full EGCS deployment.

## Scope

This phase covers JRBA and the runtime verification infrastructure only. EGCS,
PostgreSQL, GUI, socket-server, and external weather services are explicitly
out of scope.

## Architecture

The consumer remains isolated under `consumer-playground/jrba/`. Its Maven
project owns JRBA source compilation and dependency resolution. A dedicated
integration agent starts through `jade.Boot`, executes one deterministic JRBA
behaviour, prints `JRBA_TEST_PASSED`, and exits cleanly. The verifier gains a
Maven consumer mode while retaining the current javac mode for existing
consumers.

The verifier must not hardcode a Java image. Consumer configuration uses
`${TARGET_DOCKER_IMAGE}` and the existing central registry. Maven mode must
compile the consumer against the migrated workspace JADE artifact and expose
the resulting runtime classpath inside Docker.

## Consumer Contract

`consumer-playground/jrba/test-config.json` will declare:

- Maven build mode and project root.
- `jade.Boot` as the main class.
- the fully qualified integration agent in `boot_args`.
- `JRBA_TEST_PASSED` as the required marker.
- `${TARGET_DOCKER_IMAGE}` as the image placeholder.
- the workspace JADE dependency path.
- a deterministic timeout.

The consumer's `pom.xml` must compile JRBA sources with Java 17 unless static
inspection proves a Java 21 language feature is required. If Java 21 is
required, the registry and verifier must be extended before the consumer is
enabled; the test must not silently downgrade the source level.

## Verification Gates

1. Existing verifier unit tests remain green.
2. Config validation rejects malformed Maven consumer settings and unsafe paths.
3. JRBA Maven compilation succeeds against the selected migrated JADE artifact.
4. Docker runtime output contains `JRBA_TEST_PASSED` and no reverse-assertion
   failure patterns.
5. The process exits before the configured timeout.
6. A fresh review agent finds no unrelated file changes, hardcoded image, source
   exclusions, or missing dependency declaration.

## Failure Handling

Compilation failures are actionable blockers and stop the workflow. Missing
optional tooling must not be converted into a fake pass. Runtime timeout,
exceptions, or missing markers fail the consumer. Fix agents may only address
the concrete failure reported by the preceding gate, then the same gate is
rerun.

## Non-Goals

- Adding EGCS modules in this phase.
- Running JRBA's complete unit-test suite inside runtime verification.
- Copying binary dependencies into the repository without an explicit artifact
  policy.
- Modifying the baseline JADE source tree.
