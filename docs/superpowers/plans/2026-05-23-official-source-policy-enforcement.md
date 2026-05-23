# Official Source Policy Enforcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce production-safe source governance so rule flags can be generated only from official migration evidence.

**Architecture:** Add policy enforcement at two gates: source ingestion (`fetch_source.py`) and manifest validation (`write_manifest.py`). Ingestion classifies and records source policy metadata from URL/domain and run mode. Manifest writing enforces that each rule's evidence maps to an official, fetched source line/hash before flags can be generated.

**Tech Stack:** Python 3, argparse, urllib, json, pytest, jsonschema-compatible artifact validation.

---

## File Structure

- Create: `docs/sources/official-allowlist.json`
  - Canonical machine-readable allowlist used by both ingestion and manifest gates.
- Modify: `.claude/skills/jade-core-change-collector/scripts/fetch_source.py`
  - Add official allowlist classification and production rejection for mock/local/non-official sources.
- Modify: `.claude/skills/jade-core-change-collector/scripts/write_manifest.py`
  - Add evidence-to-source policy checks against `01-source-index.json`.
- Modify: `tests/test_write_manifest.py`
  - Add failing then passing tests for official evidence enforcement.
- Create: `tests/test_fetch_source_policy.py`
  - Add tests for source policy mode and allowlist behavior.
- Create: `docs/sources/official-source-policy.md`
  - Document allowed domains, production/dev modes, and evidence gate behavior.

### Task 1: Add Failing Tests for Ingestion Policy

**Files:**
- Create: `tests/test_fetch_source_policy.py`
- Modify: `.claude/skills/jade-core-change-collector/scripts/fetch_source.py`
- Create: `docs/sources/official-allowlist.json`

- [ ] **Step 1: Write failing tests for production policy behavior**

```python
def test_production_rejects_local_mock_source(tmp_path):
    ...
    assert result.returncode == 1
    assert "POLICY_REJECTED" in result.stdout + result.stderr

def test_production_rejects_non_allowlisted_domain(tmp_path):
    ...
    assert result.returncode == 1
    assert "non-official domain" in (result.stdout + result.stderr).lower()

def test_production_accepts_allowlisted_oracle_domain(tmp_path):
    ...
    assert result.returncode == 0
    assert source_index_entry["is_official"] is True

def test_development_allows_local_source(tmp_path):
    ...
    assert result.returncode == 0
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_fetch_source_policy.py -q`
Expected: FAIL because policy logic not implemented yet.

- [ ] **Step 3: Implement minimal policy logic in fetcher**

```python
# read source_policy_mode from run config (default production)
# load allowlist from docs/sources/official-allowlist.json
# classify source as official/non-official/local
# in production: reject local/mock/non-allowlisted
# write source_tier/is_official/policy_status into 01-source-index.json
```

- [ ] **Step 3a: Add canonical allowlist file (minimal initial set)**

```json
{
  "allowed_domains": [
    "oracle.com",
    "docs.oracle.com",
    "openjdk.org"
  ],
  "allowed_url_prefixes": [
    "https://docs.oracle.com/javase/specs/",
    "https://openjdk.org/jeps/"
  ]
}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_fetch_source_policy.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_fetch_source_policy.py .claude/skills/jade-core-change-collector/scripts/fetch_source.py
git commit -m "test: enforce source policy at ingestion"
```

### Task 2: Add Failing Tests for Manifest Evidence Gate

**Files:**
- Modify: `tests/test_write_manifest.py`
- Modify: `.claude/skills/jade-core-change-collector/scripts/write_manifest.py`

- [ ] **Step 1: Write failing tests for evidence policy checks**

```python
def test_rejects_rule_with_evidence_label_not_in_source_index(tmp_path):
    ...
    assert result.returncode == 2

def test_rejects_non_official_evidence_in_production(tmp_path):
    ...
    assert result.returncode == 2
    assert "non-official" in (result.stdout + result.stderr).lower()

def test_rejects_evidence_hash_mismatch(tmp_path):
    ...
    assert result.returncode == 2

def test_rejects_malformed_evidence_ref_in_production(tmp_path):
    ...
    assert result.returncode == 2

def test_allows_legacy_evidence_ref_in_development_with_warning(tmp_path):
    ...
    assert result.returncode == 0
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_write_manifest.py -q`
Expected: FAIL on new tests.

- [ ] **Step 3: Implement minimal manifest gate logic**

```python
# parse source label from evidence_ref (label::lines ...)
# require label exists in 01-source-index.json
# require matching evidence_hash equals source content_hash
# in production mode require source is official
# for malformed/legacy evidence_ref:
#   - production: reject
#   - development: permit only with explicit warning artifact/log
```

- [ ] **Step 3a: Build deterministic test fixtures for source index**

```python
# in tmp_path/artifacts/01-source-index.json write controlled entries:
# - source_label
# - content_hash
# - is_official
# - fetch_status=success
# then run write_manifest.py against that tmp artifacts dir
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_write_manifest.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_write_manifest.py .claude/skills/jade-core-change-collector/scripts/write_manifest.py
git commit -m "fix: require official evidence for manifest rules"
```

### Task 3: Add Policy Documentation

**Files:**
- Create: `docs/sources/official-source-policy.md`

- [ ] **Step 1: Write policy document**

```markdown
# Official Source Policy
- production mode: official allowlist only
- development mode: non-official/local allowed with warnings
- evidence gate: evidence_ref label + evidence_hash must map to source-index
- canonical allowlist location: docs/sources/official-allowlist.json
- malformed/legacy evidence_ref behavior by mode
```

- [ ] **Step 2: Validate docs are accurate against code**

Run: `python -m pytest tests/test_fetch_source_policy.py tests/test_write_manifest.py -q`
Expected: PASS and policy wording matches behavior.

- [ ] **Step 3: Commit**

```bash
git add docs/sources/official-source-policy.md
git commit -m "docs: define official source policy and evidence gates"
```

### Task 4: Integration Verification for Policy Outcomes

**Files:**
- Create: `tests/fixtures/source-policy/00-run-config.production.json`
- Create: `tests/fixtures/source-policy/00-run-config.development.json`
- Create: `tests/fixtures/source-policy/mock-local.md`
- Create: `tests/fixtures/source-policy/artifacts/` (temp output location for smoke checks)

- [ ] **Step 0: Create deterministic fixture contents**

Run (example):

```bash
python -c "import json, pathlib; p=pathlib.Path('tests/fixtures/source-policy'); (p/'artifacts').mkdir(parents=True, exist_ok=True); (p/'mock-local.md').write_text('# local mock\n', encoding='utf-8'); json.dump({'run_id':'policy-prod','artifacts_path':str((p/'artifacts').as_posix()),'source_version':'1.5','target_version':'1.6','source_policy_mode':'production'}, open(p/'00-run-config.production.json','w',encoding='utf-8'), indent=2); json.dump({'run_id':'policy-dev','artifacts_path':str((p/'artifacts').as_posix()),'source_version':'1.5','target_version':'1.6','source_policy_mode':'development'}, open(p/'00-run-config.development.json','w',encoding='utf-8'), indent=2)"
```

Expected: fixture files exist with required run-config keys and isolated artifacts path.

- [ ] **Step 1: Run targeted suite for changed components**

Run: `python -m pytest tests/test_fetch_source_policy.py tests/test_write_manifest.py tests/test_artifact_contracts.py -q`
Expected: PASS.

- [ ] **Step 2: Smoke-check change collector in production mode**

Run: `python .claude/skills/jade-core-change-collector/scripts/fetch_source.py --run-config tests/fixtures/source-policy/00-run-config.production.json --source-url tests/fixtures/source-policy/mock-local.md --source-label mock`
Expected: non-zero / POLICY_REJECTED in production mode.

- [ ] **Step 3: Smoke-check allowlisted source classification with deterministic local fixture**

Run: `python .claude/skills/jade-core-change-collector/scripts/fetch_source.py --run-config tests/fixtures/source-policy/00-run-config.production.json --source-url tests/fixtures/source-policy/official-mirror/docs.oracle.com-jls.html --source-label oracle-specs-mirror`
Expected: success entry with `is_official=true`, fixed content hash asserted in test.

- [ ] **Step 3a: Optional live-network smoke check (non-blocking)**

Run: `python .claude/skills/jade-core-change-collector/scripts/fetch_source.py --run-config tests/fixtures/source-policy/00-run-config.production.json --source-url https://docs.oracle.com/javase/specs/ --source-label oracle-specs`
Expected: success entry with `is_official=true` when network is available; do not fail CI on network errors.

- [ ] **Step 4: Commit verification updates (if any fixture changes)**

```bash
git add <changed test fixtures>
git commit -m "test: verify production source policy end-to-end"
```

## Notes and Guardrails

- Keep default behavior strict: `source_policy_mode=production` unless explicitly set.
- Use one canonical allowlist file: `docs/sources/official-allowlist.json`.
- Do not degrade existing anti-hallucination checks (`confidence >= 0.7`, required evidence fields).
- Ensure all policy writes remain atomic and backwards-compatible for existing artifact readers.
- Preserve current `fetch_source.py` success/failure exit semantics (`0` success, `1` attention-needed, `2` invalid input).
