---
name: jade-core-change-collector
description: >-
  Collects Java version breaking-change rules from user-supplied sources (URLs,
  files, KB references) and produces an evidence-backed manifest. Strict mode —
  never invents diffs without evidence. If all sources fail, halts with
  AWAITING_SOURCE_INPUT.
when_to_use: >-
  Use when the user says "collect breaking changes", "produce change manifest",
  "gather java version diffs", "strict source collection", or after
  jade-migration-orchestrator reaches MANIFEST_READY phase and needs the
  breaking-changes manifest populated.
arguments: [artifacts_dir]
argument-hint: "[path to artifacts directory, e.g. migration-runs/sample/artifacts]"
allowed-tools: Bash(python *) Read Write
---

# JADE Change Collector — Strict

## Objective

Collect Java version breaking-change rules from **user-supplied sources only** and produce
`artifacts/01-breaking-changes-manifest.json` with every rule pinned to a specific piece of
evidence. Never infer, guess, or invent a diff from model priors.

## Strict-mode constraint

**It is forbidden to emit a rule unless it can cite a specific source URL, line, or document
reference.**  If the collector cannot find evidence for a suspected change, it MUST omit the
rule entirely.  Confidence scores below `0.7` MUST NOT appear in the manifest; those candidates
go into `artifacts/01-evidence-map.json` under `rejected_candidates`.

## Required input

- `artifacts/00-run-config.json`
- A user-provided source list (URLs, file paths, or knowledge-base references)

## Produced artifacts

| Artifact | Purpose |
|----------|---------|
| `artifacts/01-source-index.json` | Every source with fetch status, retrieved content digest, and error details |
| `artifacts/01-source-fetch-errors.json` | Written only when **all** sources fail; triggers halt |
| `artifacts/01-breaking-changes-manifest.json` | Final rule list, each backed by evidence |
| `artifacts/01-evidence-map.json` | Rule-to-source mapping, rejected candidates, confidence scores |

## Workflow

### Phase A — Source ingestion

1. Read `artifacts/00-run-config.json` to obtain the `run_id` and `artifacts_path`.
2. Accept the user's source list.  Each source is a URL, a local file path (relative to
   workspace root), or a named knowledge-base reference (e.g. "Oracle Java 6 compat notes").
3. For each source, invoke `scripts/fetch_source.py`:
   ```
   python scripts/fetch_source.py \
     --run-config artifacts/00-run-config.json \
     --source-url "<URL_OR_PATH>" \
     --source-label "<HUMAN_READABLE_LABEL>"
   ```
   The script writes/updates `01-source-index.json` as it goes.  Run sources sequentially;
   parallel fetches are permitted only when sources are on distinct hosts.

4. After all fetches complete, read `artifacts/01-source-index.json` and count
   `status == "success"` entries.

   **If zero successes**: write `artifacts/01-source-fetch-errors.json`, set the run state
   to `AWAITING_SOURCE_INPUT` in `artifacts/00-run-state.json`, and halt with the message:

   > All web/file sources failed.  Please provide local file paths (PDF, HTML, plaintext) or
   > an archived mirror of the Java version compatibility documentation.

### Phase B — Rule extraction

1. Run `scripts/collect_changes.py`:
   ```
   python scripts/collect_changes.py \
     --run-config artifacts/00-run-config.json
   ```
   The script reads `01-source-index.json`, processes every successfully-fetched source,
   and produces:
   - `artifacts/01-breaking-changes-manifest.json`
   - `artifacts/01-evidence-map.json`

2. Validate the manifest:
   - Every entry has a non-empty `evidence_ref` and `evidence_hash`.
   - No `confidence` is below `0.7`.
   - `version_from` and `version_to` match the `source_version` / `target_version` from the
     run config (or a sub-range within them).
   - `rule_id` values are unique and follow the pattern `BC-{version_to}-{NNNN}` (e.g.
     `BC-1.6-0001`).

### Phase C — Handoff

Once `01-breaking-changes-manifest.json` exists and passes validation, the orchestrator
can transition to `MANIFEST_READY`.  No further action is needed from the collector.

## Rule schema

Each entry in `01-breaking-changes-manifest.json`:

```json
{
  "rule_id": "BC-1.6-0001",
  "version_from": "1.5",
  "version_to": "1.6",
  "severity": "BLOCKER|ERROR|WARNING|INFO",
  "category": "API_REMOVAL|DEPRECATION|BEHAVIOR_CHANGE|NAMESPACE|BYTECODE|BUILD",
  "match_pattern": "regex or structured match descriptor",
  "fix_strategy": "short, actionable fix instruction",
  "verification_hint": "how to confirm fix was applied correctly",
  "evidence_ref": "source-label::section-anchor::line-range",
  "evidence_hash": "sha256 of the exact source text snippet that supports this rule",
  "confidence": 0.95
}
```

## Evidence map schema

Each entry in `01-evidence-map.json`:

```json
{
  "source_label": "oracle-java-6-compat",
  "source_url": "https://...",
  "fetch_status": "success",
  "extracted_rules": ["BC-1.6-0001", "BC-1.6-0002"],
  "rejected_candidates": [
    {
      "suspected_change": "description",
      "reason": "insufficient_evidence|ambiguous_wording|contradicts_other_source",
      "source_snippet_hash": "sha256"
    }
  ]
}
```

## Halt conditions

| Condition | Action |
|-----------|--------|
| `00-run-config.json` missing or invalid | Log error, exit code 2 |
| No sources provided by user | Prompt user, do not proceed |
| All sources failed (404/timeout/paywall) | Write `01-source-fetch-errors.json`, set `AWAITING_SOURCE_INPUT`, halt |
| Manifest empty after extraction | Write manifest with empty `rules` array, set confidence note |

## Constraints

1. Never fabricate a `match_pattern` or `fix_strategy`.
2. If a source describes a change but the wording is ambiguous, place it in
   `rejected_candidates` — do not promote it to a rule.
3. When two sources disagree, keep the one with the higher-quality evidence (official >
   community) and note the conflict in `rejected_candidates`.
4. `evidence_hash` MUST be computed from the exact text range that supports the rule,
   not the entire page.
5. Confidence `1.0` is reserved for official Oracle/OpenJDK release notes or JEP documents.
   Community sources cap at `0.85`.

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/fetch_source.py` | Fetch one source, update source index |
| `scripts/collect_changes.py` | Parse all sources, produce manifest + evidence map |
