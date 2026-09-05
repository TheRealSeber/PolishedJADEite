# 17 → 21: the proposed run

Derived from `PROBE.md`. Nothing here is applied; the workspace does not exist
yet. Two decisions below are the maintainer's and gate the run.

## Proposed rule set

Ordering is by blast radius, not by severity: the charset rules touch wire
formats and must land as one coherent batch, before anything cosmetic.

| # | rule | sites | files | blast | kind |
|---|---|---:|---:|---|---|
| 1 | `JEP400_ACL_AND_CONTENT_WIRE_CODEC_DEFAULT_CHARSET` | 7 | 4 | signature | behaviour |
| 2 | `JEP400_JICP_IMTP_TRANSPORT_DEFAULT_CHARSET` | 47 | 18 | body-local | behaviour |
| 3 | `JEP400_FILE_PERSISTENCE_AND_CONFIG_DEFAULT_CHARSET` | 26 | 13 | body-local | behaviour |
| 4 | `JEP400_SOCKET_PRINTSTREAM_TEXT_PROTOCOL` | 3 | 3 | body-local | behaviour |
| 5 | `JEP400_FILE_PRINTSTREAM_CSV_AND_LOG` | 3 | 1 | body-local | behaviour |
| 6 | `JEP400_STDIN_AND_URL_STREAM_READERS` | 5 | 5 | body-local | behaviour |
| 7 | `FINALIZE_DEPRECATED_FOR_REMOVAL` | 4 | 3 | body-local | removal |
| 8 | `THREADDEATH_DEPRECATED_FOR_REMOVAL` | 1 | 1 | body-local | removal |
| 9 | `URL_CONSTRUCTORS_DEPRECATED` | 12 | 7 | body-local | deprecation |
| 10 | `THREAD_GETID_DEPRECATED` | 3 | 1 | body-local | deprecation |
| 11 | `RUNTIME_EXEC_SINGLE_STRING_DEPRECATED` | 2 | 1 | body-local | deprecation |

**91 charset sites, 5 removal sites, 17 deprecation sites — 113 across ~50 files.**

Rules 1-6 are the jump. Rules 7-11 are the compiler-visible remainder and are
individually small. Rules 9-11 are optional: they are plain deprecations, not
removals, and JADE's build does not treat warnings as errors.

### Rule 1 is the one that needs a decision, not a recipe

`LEAPACLCodec` and `LEAPCodec` take a `charset` parameter and document it as
*"This parameter is not taken into account"*. Two fixes exist and they are not
equivalent:

- **Pin `US-ASCII`**, matching what `ACLCodec.DEFAULT_CHARSET` already declares
  and what `StringACLCodec` already honours. Wire-compatible with every existing
  JADE node in both directions. Keeps the existing inability to carry non-ASCII
  content through the binary codec.
- **Pin `UTF-8`.** Fixes non-ASCII content properly, and makes a JADE 21 node
  incompatible with a JADE 17 node running on a non-UTF-8 host — silently, as
  mojibake rather than an error.

The pipeline must not pick between these. It is a protocol compatibility
decision for the maintainer, in the same class as the TLS anonymous-cipher
question left open in 8-to-11.

Rules 2-6 have no such tension: every one of them is a case where both ends of
the conversation are the same code, or the file was written by this process and
is read back by this process, so pinning the charset explicitly preserves
today's behaviour on a UTF-8 host and removes the platform dependency. They are
mechanical.

## Rules deliberately not in the set

Recorded so they are not re-raised without reading why. All were raised by
reconnaissance and killed under verification — see `PROBE.md` for the evidence.

| rule | why not |
|---|---|
| `CLDR_LOCALE_DATA_FORMATTED_OUTPUT` | already withdrawn on evidence in 8-to-11 as `CLDR_LOCALE_DATA_DEFAULT`; the reasoning still holds |
| `CLASS_NEWINSTANCE_DEPRECATED` | 61 real sites, unchanged 17→21, already withdrawn as out-of-window by 11-to-17 |
| `JEP431_SEQUENCED_COLLECTIONS` (3 variants) | zero sites; `source=21` compiles with zero errors |
| Thread / ThreadGroup lifecycle (7 candidates) | zero sites; every hit is JADE's own method on its own type |
| Security Manager / JEP 411 (7 candidates) | zero sites |
| Strong encapsulation, JEP 396 / 451 (7 candidates) | zero sites |
| `APPLET_API_*` | present in 21, removed in 25; no error and no warning |
| `VALUE_BASED_CLASS_SYNCHRONIZATION` | real, but fires identically on 17 — out of window for this jump, and coupled to the `GuiAgent` decision below |

## Two decisions that gate the run

**1. Target bytecode: 61 or 65?** See the closing section of `PROBE.md`. Both
are proven to work. Emitting 65 drops consumers below JDK 21.

**2. Binary codec charset: `US-ASCII` or `UTF-8`?** See rule 1 above.

A third, smaller one is already teed up from 11-to-17 and can ride along:
`GuiAgent.guiEventQueueLock` should become a plain `Object`. It clears one
removal warning and both synchronization warnings and fixes a latent shared-lock
bug, but it is out of window for 17→21 and belongs in the run only if the
maintainer wants it swept up.

## Environment, already prepared and verified

| item | state |
|---|---|
| worktree `PolishedJADEite-1721`, branch `work/jump-1721` | created from `work/jump-1117` |
| `docker/Dockerfile.ant21`, image `jade-ant:21` | built; Temurin 21.0.12 LTS, Ant 1.10.14 |
| `config/docker-images.json` → `java-21` | added; `resolve_docker_image("21")` resolves it |
| registry bucket `17-to-21` | allowed by the dispatcher |
| `00-run-config.json` | baseline = the verified 11-to-17 workspace |
| gitignored build inputs (`commons-codec-1.3.jar`, `classes/jade.mf`) | copied into the baseline |
| consumer compiler selection | reads workspace bytecode, picks a javac that can read it |
| `hw-jade`, `jrba` runtime pins | 17 → 21 |
| build gate | now rejects an audit whose own `build_exit_code` is non-zero |
| test suite | 556 passed, 0 failed |

## First actions when the run starts

1. Copy baseline → `migration-runs/jade-17-to-21/workspace`, `INIT` → `WORKSPACE_READY`.
2. Write the manifest from the table above, with the two decisions resolved.
3. `BUILD_GATE_READY` on `jade-ant:21` — expected to pass untouched; if it does
   not, the probe was wrong and everything downstream is suspect.
4. Knowledge graph, then scan. Expect the charset rules to need `multiline`
   patterns for the `new BufferedReader(new FileReader(...))` shapes, the same
   scanner capability that `LAMBDA_CONVERSION` needed in 1.7-to-1.8.
5. Rule 1 first, alone, with its own consumer run.
