---
name: jade-core-change-collector
description: >-
  Collects Java version breaking-change rules from user-supplied sources. Uses
  LLM reading comprehension to extract rules from fetched text — never regex.
  A schema-validating write_manifest.py enforces evidence, confidence, and
  format. If all sources fail, halts with AWAITING_SOURCE_INPUT.
when_to_use: >-
  Use when the orchestrator reaches MANIFEST_READY phase, or when the user says
  "collect breaking changes", "produce change manifest", "gather java version
  diffs". Requires user-supplied source list (URLs, file paths, or local KB files).
arguments: [artifacts_dir]
argument-hint: "[path to artifacts directory]"
allowed-tools: Bash(python *) Read Write
---

# JADE Change Collector — LLM-as-Extractor

## Objective

Produce `artifacts/01-breaking-changes-manifest.json` where every rule is extracted
by the agent's reading comprehension from actual fetched source text. Never regex.
Never fabricate.

## Strict-mode constraint

**It is forbidden to emit a rule unless the agent read it directly from a fetched
source file.** Every rule must cite a `source_label` and `evidence_ref` that the
agent just read. Confidence scores below `0.7` MUST NOT appear in the manifest.

---

## Required input

- `artifacts/00-run-config.json`
- User-supplied source list (URLs, file paths, or local `.md` KB files)

---

## Produced artifacts

| Artifact | Purpose |
|----------|---------|
| `artifacts/01-source-index.json` | Every source with fetch status, snippet, hash |
| `artifacts/01-source-content-{label}.txt` | **Clean, readable text** extracted from each source — the LLM reads THIS |
| `artifacts/01-source-fetch-errors.json` | Written only when **all** sources fail |
| `artifacts/01-breaking-changes-manifest.json` | Final rule list, schema-validated |
| `artifacts/01-evidence-map.json` | Rejected candidates, extraction notes |

---

## Workflow

### Phase A — Source Ingestion

1. Read `artifacts/00-run-config.json` to obtain `run_id` and `artifacts_path`.
2. Accept the user's source list. Sources are URLs, local files, or KB paths.
3. For each source, invoke `scripts/fetch_source.py`:

```
python scripts/fetch_source.py \
  --run-config artifacts/00-run-config.json \
  --source-url "<URL_OR_PATH>" \
  --source-label "<HUMAN_READABLE_LABEL>"
```

The script:
- Fetches URL content (handles 200, 404, timeout, paywall detection)
- Strips HTML tags to produce **clean readable text**
- Writes `artifacts/01-source-content-{label}.txt`
- Updates `artifacts/01-source-index.json`

**If zero sources succeed** (all 404/timeout/paywall): write `01-source-fetch-errors.json`,
set `AWAITING_SOURCE_INPUT` in `00-run-state.json`, and halt.

### Phase B — LLM Extraction (the agent does this)

**The agent MUST NOT invent rules from prior knowledge.** Every rule MUST come from
text the agent explicitly read.

1. **Read each source file** with the `Read` tool:
   - Read `artifacts/01-source-content-{label}.txt`
   - Scan for breaking changes between `source_version` and `target_version`
   - Identify rule candidates: new language features, deprecated APIs, removed components, behavioral changes

2. **For each candidate rule, cite evidence:**
   - `evidence_ref` — `source-label::line-range` (e.g., `mock-sources::lines 15-28`)
   - `evidence_hash` — SHA-256 from `01-source-index.json` for that source

3. **Build a JSON array of rules.** Each rule MUST have:
   - `id` — unique ID, e.g., `GENERICS_UPGRADE`, `LOOP_MODERNIZATION`
   - `name` — human-readable name
   - `fix_strategy` — `"recipe:jade-recipe-{version}-{id}"` format
   - `severity` — `HIGH`, `MEDIUM`, `LOW`, `WARNING`, `INFO`
   - `category` — `LANGUAGE_CHANGE`, `API_REMOVAL`, `DEPRECATION`, `BEHAVIOR_CHANGE`, etc.
   - `match_pattern` — valid regex to find instances in source
   - `patterns[]` — array with `{type: "regex", pattern, target_extensions, reason, confidence}`
   - `evidence_ref`, `evidence_hash`, `confidence` (0.7–1.0)
   - `verification_hint` — how to confirm the fix was applied correctly

4. **Save the rules to a temp JSON file:**
```bash
python -c "
import json
rules = [...]  # your extracted rules
json.dump(rules, open('artifacts/01-extracted-rules.tmp.json', 'w'), indent=2)
"
```

### Phase C — Validate and Write

1. Invoke `write_manifest.py` with the temp file:

```
python scripts/write_manifest.py \
  --input artifacts/01-extracted-rules.tmp.json \
  --artifacts-dir artifacts/ \
  --run-id <run_id> \
  --source-version <source_version> \
  --target-version <target_version>
```

2. `write_manifest.py` validates:
   - Every rule has required fields (`id`, `name`, `severity`, `patterns`)
   - Every rule has `evidence_ref` and `evidence_hash` (Anti-Hallucination gate)
   - `confidence >= 0.7`
   - `fix_strategy` starts with `"recipe:"`
   - `match_pattern` compiles as valid regex
   - No duplicate `rule_id` values
   - `severity` and `category` are valid values

3. If validation fails → print errors, exit 2. DO NOT proceed with invalid manifest.
4. If validation passes → `01-breaking-changes-manifest.json` is written atomically.

---

## Halt conditions

| Condition | Action |
|-----------|--------|
| All sources failed | Write `01-source-fetch-errors.json`, set `AWAITING_SOURCE_INPUT`, halt |
| Agent cannot extract any rule from sources | Write empty manifest (rules: []), note in evidence map |
| `write_manifest.py` validation fails | Fix extracted JSON, re-run Phase C |

---

## Constraints

1. Never fabricate a rule from model priors — evidence MUST be in the read text.
2. `confidence` rated by the agent based on source quality:
   - Official JLS/Oracle docs → 0.90–1.0
   - Secondary sources → 0.75–0.85
   - Ambiguous wording → DON'T extract (reject it)
3. `fix_strategy` always uses `recipe:` prefix to enable the dispatcher.
4. `evidence_hash` must match a hash from `01-source-index.json`.
5. The agent writes the extracted rules to a temp file, then `write_manifest.py`
   validates and saves — the agent never directly writes the manifest.
