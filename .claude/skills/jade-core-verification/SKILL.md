---
name: jade-core-verification
description: >-
  Verifies JADE migration correctness by semantic outcome matching instead of raw
  textual log diffing. Normalizes traces (strips timestamps, thread IDs, nonces),
  extracts agent lifecycle / ACL protocol / DF-AMS state events, and compares
  state outcomes under configurable tolerance. Produces diff and metrics artifacts.
  Run this as the final verification gate after all migration rules have been applied.
when_to_use: >-
  Use when the user says "verify migration", "semantic verify", "compare traces",
  "outcome matching", "semantic diff", "migration gate check", "final verification",
  or after the orchestrator completes RULE_BATCH_LOOP and enters VERIFIED phase.
arguments: [baseline_logs, migrated_logs, tolerance_config]
argument-hint: "[baseline-traces-dir] [migrated-traces-dir] [tolerance-config.json]"
allowed-tools: Bash(docker *) Bash(python *) Bash(find *) Read Write
paths: "**/*.log" "**/*.trace" "**/*.xml" "**/*.json"
disable-model-invocation: true
---

# JADE Semantic Verification

## Objective
Confirm that the migrated JADE build produces the **same semantic outcomes** as the
baseline build — not that the raw log text is identical. Noise such as timestamps,
thread IDs, memory addresses, and platform-specific container names is stripped
before comparison. When a knowledge graph is available before and after a rule
batch, a structural graph diff (`07-graph-diff.json`) is recorded as
**supplementary evidence** — it never replaces the semantic gate.

## Semantic Verification Model

Rather than diffing character-level log output, this skill operates on a
three-layer event model:

### Layer 1 — Lifecycle Events
Extracted from container and agent logs:
| Event | Canonical form | Key |
|-------|---------------|-----|
| Agent born | `AGENT_STARTED` | agent local-name |
| Agent suspended | `AGENT_SUSPENDED` | agent local-name |
| Agent resumed | `AGENT_RESUMED` | agent local-name |
| Agent migrated | `AGENT_MOVED` | agent local-name, source, destination |
| Agent died | `AGENT_TERMINATED` | agent local-name |
| Container ready | `CONTAINER_READY` | container name |
| Container shutdown | `CONTAINER_SHUTDOWN` | container name |
| Platform joined | `PLATFORM_JOIN` | container name |
| Main container elected | `MAIN_ELECTED` | container name |

### Layer 2 — ACL Protocol States
Extracted from behaviour logs and sniffer traces:
| State | Canonical form | Key |
|-------|---------------|-----|
| Message sent | `ACL_SEND` | sender, receiver, performative, conversation-id |
| Message received | `ACL_RECEIVE` | receiver, sender, performative, conversation-id |
| Message reply | `ACL_REPLY` | sender, receiver, performative, in-reply-to |
| Conversation start | `CONV_START` | initiator, protocol, conversation-id |
| Conversation end | `CONV_END` | conversation-id, result |
| Timeout | `ACL_TIMEOUT` | waiting-agent, conversation-id |
| No-match handler | `ACL_NOMATCH` | agent, performative |

### Layer 3 — DF/AMS Outcomes
Extracted from directory-facilitator and agent-management-system logs:
| Outcome | Canonical form | Key |
|---------|---------------|-----|
| Service registered | `DF_REGISTER` | agent, service-type, service-name |
| Service deregistered | `DF_DEREGISTER` | agent, service-type, service-name |
| Service modified | `DF_MODIFY` | agent, service-type, service-name |
| DF search | `DF_SEARCH` | requesting-agent, service-type |
| DF search result | `DF_SEARCH_RESULT` | requesting-agent, count |
| AMS agent description | `AMS_DESCRIBE` | target-agent |
| AMS kill request | `AMS_KILL` | target-agent |

---

## Phase 0 — Optional codebase documentation

Before verification, the pipeline may run `codebase-analysis` (optional Phase 0) to
produce `JadeDocumentation/` in the workspace root. If this directory exists, the
verification skill consumes it for enriched semantic scenarios.

**Files consumed:**
| File | Purpose |
|------|---------|
| `JadeDocumentation/behavior/workflows.md` | Application-level process flows — converted into expected event sequences |
| `JadeDocumentation/migration/test-specifications.md` | Pre-written test case specifications — used as assertion targets |
| `JadeDocumentation/reference/data-models.md` | Type definitions — used to resolve agent/behaviour type names in traces |

**Dynamic Scenario Generation:**
When `JadeDocumentation/behavior/workflows.md` exists, the verification skill extracts
workflow descriptions and produces **dynamic trace scenarios**. Each documented workflow
becomes a required event sequence that must be matched in the migrated traces.

Example: if `workflows.md` documents a "ContractNet protocol (initiate → propose →
accept → confirm)", the verification gate asserts that all four event types appear in
the migrated traces with matching conversation IDs.

These scenarios are merged with the static `tolerance_config.json` — if a workflow
requires an event NOT listed in `require_events`, it is added dynamically at runtime.

Without `JadeDocumentation/`, verification falls back to the static tolerance config
only. The pipeline is never blocked by missing documentation.

## Input Requirements

| Input | Description |
|-------|-------------|
| `baseline_logs/` | Directory of logs/traces from the **pre-migration** JADE build |
| `migrated_logs/` | Directory of logs/traces from the **post-migration** JADE build |
| `tolerance_config.json` | Per-event-type tolerance rules (see below) |
| `JadeDocumentation/` *(optional)* | Codebase documentation from Phase 0 — enables dynamic scenarios |

If a trace format requires XML parsing (JADE Sniffer XML exports), the normalizer
detects the format automatically.

### Tolerance Configuration Schema

```json
{
  "tolerance": {
    "agent_count_delta": { "max_deviation": 0, "allow_extra": false, "allow_missing": false },
    "lifecycle_order": { "strict": true, "allowed_reorder_events": [] },
    "acl_message_count": { "max_deviation": 0, "allow_duplicates": false },
    "df_outcome_count": { "max_deviation": 0, "allow_extra": false, "allow_missing": false },
    "timing": { "ignore": true, "max_skew_ms": 5000 }
  },
  "ignore_events": [],
  "require_events": [],
  "agent_allowlist": [],
  "agent_blocklist": [],
  "conversation_id_matching": "strict"
}
```

| Field | Default | Description |
|-------|---------|-------------|
| `agent_count_delta.max_deviation` | `0` | Allowed difference in agent count |
| `agent_count_delta.allow_extra` | `false` | Allow migrated to have more agents |
| `lifecycle_order.strict` | `true` | Require same event order |
| `lifecycle_order.allowed_reorder_events` | `[]` | Events whose order can differ |
| `acl_message_count.max_deviation` | `0` | Allowed difference in ACL message count |
| `acl_message_count.allow_duplicates` | `false` | Allow duplicate messages in migrated |
| `df_outcome_count.max_deviation` | `0` | Allowed difference in DF outcomes |
| `timing.ignore` | `true` | Ignore timing differences entirely |
| `ignore_events` | `[]` | Event types to skip during comparison |
| `require_events` | `[]` | Events that must be present in both |
| `agent_allowlist` | `[]` | Only compare these agent names |
| `agent_blocklist` | `[]` | Exclude these agent names |
| `conversation_id_matching` | `"strict"` | `"strict"` or `"relaxed"` |

---

## Pipeline

### Step 1: Collect input traces

```bash
ls baseline_logs/*.log baseline_logs/*.trace baseline_logs/*.xml 2>/dev/null
ls migrated_logs/*.log migrated_logs/*.trace migrated_logs/*.xml 2>/dev/null
```

If no trace files are found, fail with `TRACE_NOT_FOUND`.

### Step 2: Run normalizer on baseline

```bash
python scripts/normalize_trace.py \
  --input-dir baseline_logs/ \
  --output artifacts/07-semantic-trace-baseline.json \
  --format auto
```

### Step 3: Run normalizer on migrated

```bash
python scripts/normalize_trace.py \
  --input-dir migrated_logs/ \
  --output artifacts/07-semantic-trace-migrated.json \
  --format auto
```

### Step 4: Build migrated JADE and capture build log

All builds run in Docker — no host JDK required.

```bash
docker run --rm \
  -v "$(pwd)/JADE-4.6.0:/workspace" \
  -w /workspace/src/jade \
  frekele/ant:1.10.3-jdk8 ant jade -q 2>&1 | tee artifacts/07-build.log
```

If build fails, fail with `BUILD_FAILED` — migration is not verifiable.

### Step 5: Run semantic comparison

```bash
python scripts/semantic_verify.py \
  --baseline artifacts/07-semantic-trace-baseline.json \
  --migrated artifacts/07-semantic-trace-migrated.json \
  --tolerance tolerance_config.json \
  --artifacts-dir artifacts/
```

Produces:
- `artifacts/07-semantic-diff.json`
- `artifacts/07-metrics.json`

### Step 5b: Optional graph-diff evidence (supplementary)

When the knowledge graph is rebuilt at batch boundaries (`03.5-knowledge-graph.json`),
pass the before-batch and after-batch graphs to semantic verification:

```bash
python scripts/semantic_verify.py \
  --baseline artifacts/07-semantic-trace-baseline.json \
  --migrated artifacts/07-semantic-trace-migrated.json \
  --tolerance tolerance_config.json \
  --artifacts-dir artifacts/ \
  --graph-before artifacts/03.5-knowledge-graph.before.json \
  --graph-after artifacts/03.5-knowledge-graph.json
```

When `--graph-before`/`--graph-after` are supplied, the verifier runs the
deterministic `graph_diff.py` diff and records it as **additive evidence**:

- Produces `artifacts/07-graph-diff.json`
- Adds a `graph_evidence` section to `artifacts/07-semantic-diff.json` and a
  `graph_diff` section to `artifacts/07-metrics.json`

The diff report is versioned (`graph_diff_version: 1`), contains no timestamps,
and is byte-deterministic for identical inputs. It compares:
- nodes by path with a declaration + import signature (volatile line numbers excluded)
- edges as canonical `(from, to, type)` tuples
- changed-node `impact_paths` derived from the graph's reverse dependency edges,
  bounded by `MAX_IMPACT_PATHS_PER_NODE` and `MAX_IMPACT_PATHS_TOTAL`; when the
  bound is hit the report sets `impact_path_truncated` and lists the affected
  changed nodes

**Graph evidence is supplementary only.** It may expand diagnostics and
verification scope, but it can NEVER convert a failed build, semantic gate, or
runtime test into success. The semantic `overall_pass` and the exit code are
computed purely from the trace layers. If a graph is missing or malformed, the
verifier records an additive warning (`graph_file_not_found`,
`graph_parse_error`, `missing_graph_input`, or `graph_diff_unavailable`) and
continues the existing semantic gate unchanged.

### Step 6: Interpret results

Read `artifacts/07-semantic-diff.json` and `artifacts/07-metrics.json`.

| Metric | Meaning |
|--------|---------|
| `baseline_event_count` | Total events in baseline |
| `migrated_event_count` | Total events in migrated |
| `matched_count` | Events with identical semantic signatures |
| `tolerated_diff_count` | Events differing within tolerance |
| `unmatched_baseline` | Events present only in baseline |
| `unmatched_migrated` | Events present only in migrated |
| `lifecycle_outcome_pass` | Agent lifecycle match result |
| `acl_outcome_pass` | ACL protocol match result |
| `df_ams_outcome_pass` | DF/AMS match result |
| `overall_pass` | Final gate decision |

If `overall_pass` is `false`, the migration gate is `VERIFICATION_FAILED`.

---

## Normalization Rules

The normalizer (`normalize_trace.py`) applies these transformations:

1. **Strip timestamps** — all `HH:mm:ss.SSS`, ISO-8601, JADE `MMM dd, yyyy` formats
2. **Strip thread IDs** — `[Thread-N]`, `[pool-N-thread-M]`, `[ForkJoinPool-...]`
3. **Strip hex nonces** — `[a-f0-9]{8,}`, UUID v4
4. **Strip memory addresses** — `@[a-f0-9]{4,16}`
5. **Normalize whitespace** — collapse multiple spaces, trim
6. **Normalize platform address** — `@host:port/JADE` → `@PLATFORM`
7. **Normalize container names** — `Main-Container@...` → `Main-Container@PLATFORM`
8. **Detect format** — plain JADE log, JADE Sniffer XML, or generic JSON lines

---

## Event Extraction Rules

### Lifecycle event detection

| JADE log pattern | Canonical event |
|------------------|-----------------|
| `Agent .* started` or `Agent .* is born` | `AGENT_STARTED {agent}` |
| `Agent .* suspended` | `AGENT_SUSPENDED {agent}` |
| `Agent .* resumed` | `AGENT_RESUMED {agent}` |
| `Agent .* moved` or `Agent .* migrated` | `AGENT_MOVED {agent} {src}→{dst}` |
| `Agent .* terminated` or `Agent .* died` | `AGENT_TERMINATED {agent}` |
| `Agent container .* is ready` | `CONTAINER_READY {container}` |
| `Agent container .* shut` | `CONTAINER_SHUTDOWN {container}` |
| `joinPlatform` success | `PLATFORM_JOIN {container}` |

### ACL protocol detection

| JADE log pattern | Canonical event |
|------------------|-----------------|
| `sends ACL(...)` or `send ACL(...)` | `ACL_SEND {sender}→{receiver} {performative} [{conv-id}]` |
| `received ACL(...)` or `receive ACL(...)` | `ACL_RECEIVE {receiver}←{sender} {performative} [{conv-id}]` |
| `<performative>` in Sniffer XML | `ACL_SEND` / `ACL_RECEIVE` from XML attributes |

### DF/AMS outcome detection

| JADE log pattern | Canonical event |
|------------------|-----------------|
| `registered.*service` or `DFService.*register` | `DF_REGISTER {agent} {type} {name}` |
| `deregistered.*service` | `DF_DEREGISTER {agent} {type} {name}` |
| `modified.*service` | `DF_MODIFY {agent} {type} {name}` |
| `search.*DF` or `DFService.*search` | `DF_SEARCH {agent} {type}` |
| `DF search.*result` or `DFService.*result` | `DF_SEARCH_RESULT {agent} {count}` |
| `AMS.*describe` | `AMS_DESCRIBE {target}` |
| `AMS.*kill` | `AMS_KILL {target}` |

---

## Semantic Diff Format

`artifacts/07-semantic-diff.json`:

```json
{
  "timestamp": "2026-01-01T00:00:00Z",
  "overall_pass": true,
  "sections": [
    {
      "layer": "lifecycle",
      "pass": true,
      "diffs": [],
      "baseline_count": 15,
      "migrated_count": 15,
      "matched_count": 14,
      "tolerated_count": 1,
      "unmatched_baseline": [],
      "unmatched_migrated": []
    },
    {
      "layer": "acl",
      "pass": true,
      "diffs": [
        {
          "type": "order_mismatch",
          "event": "ACL_SEND",
          "baseline_index": 12,
          "migrated_index": 14,
          "tolerated": true,
          "reason": "allowed_reorder_events includes ACL_SEND"
        }
      ],
      "baseline_count": 42,
      "migrated_count": 42,
      "matched_count": 40,
      "tolerated_count": 2,
      "unmatched_baseline": [],
      "unmatched_migrated": []
    },
    {
      "layer": "df_ams",
      "pass": true,
      "diffs": [],
      "baseline_count": 6,
      "migrated_count": 6,
      "matched_count": 6,
      "tolerated_count": 0,
      "unmatched_baseline": [],
      "unmatched_migrated": []
    }
  ]
}
```

---

## Constraints

1. Never modify baseline logs — read-only
2. Never compare raw log files with `diff` — only compare normalized semantic events
3. Agent names are compared by **local name** only (the part before `@`)
4. Platform addresses (`@host:port/JADE`) are normalized to `@PLATFORM` before comparison
5. Conversation IDs are compared exactly unless `conversation_id_matching` is `"relaxed"`
6. Build failure in the migrated tree is a hard gate fail — `BUILD_FAILED`
7. If the migrated build succeeds but semantic verification fails, output `VERIFICATION_FAILED`
8. All output artifacts are written atomically (`.tmp` → rename)

## Exit Criteria

- `artifacts/07-build.log` exists and shows successful compilation
- `artifacts/07-semantic-trace-baseline.json` and `artifacts/07-semantic-trace-migrated.json` exist
- `artifacts/07-semantic-diff.json` exists with `overall_pass` result
- `artifacts/07-metrics.json` exists with all metric fields populated
- When `--graph-before`/`--graph-after` are supplied, `artifacts/07-graph-diff.json`
  records the additive graph diff (or a skip/malformed warning) — supplementary only
- If `overall_pass` is `false`, `artifacts/failure-summary.json` is written with code `VERIFICATION_FAILED`

## runtime_verify.py — Consumer Playground Runtime Tests

**Purpose:** Compiles consumer projects from `consumer-playground/`, injects migrated `jade.jar`, runs each in Docker, and asserts expected output markers.

**Invocation:**
```
python .claude/skills/jade-core-verification/scripts/runtime_verify.py \
  --workspace <migrated_workspace> \
  --artifacts <artifacts_dir> \
  --config <00-run-config.json>
```

**Consumer projects:** Stored in `consumer-playground/<name>/` with:
- `*.java` — JADE agent source files
- `test-config.json` — docker image, boot args, expected markers, classpath deps

**Output:** `artifacts/07-runtime-verify.json` — per-consumer PASS/FAIL with stdout evidence.

**Exit codes:** 0 = all pass, 2 = failures, 3 = env error
