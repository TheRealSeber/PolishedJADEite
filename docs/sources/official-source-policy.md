# Official Source Policy

> **Version:** 1.0  
> **Last updated:** 2026-05-23  
> **Status:** ACTIVE — all `jade-core-change-collector` skills enforce this policy.

---

## 1. Purpose

The JADE pipeline must guarantee that every migration rule is backed by **verifiable,
official evidence** — not LLM priors, blog posts, or fabrications. This policy governs
how sources are classified, accepted, and linked to manifest rules.

Two enforcement gates exist:

| Gate | Location | Phase |
|------|----------|-------|
| Ingestion gate | `fetch_source.py` | Phase 3 (MANIFEST) |
| Manifest gate | `write_manifest.py` | Phase 3 (MANIFEST) |

---

## 2. Source Classification

Every ingested source is classified into one of three tiers at fetch time:

| Tier | Criteria | `is_official` | `source_tier` |
|------|----------|---------------|---------------|
| **Official** | Domain matches allowlist AND scheme is HTTPS | `true` | `"official"` |
| **Non-official** | Domain does not match allowlist (but is remote) | `false` | `"non_official"` |
| **Local** | URL is a local file path (`file://` or bare path) | `false` | `"local"` |

Classification metadata is written into `01-source-index.json` per entry:
```json
{
  "sources": [{
    "source_label": "oracle-specs",
    "source_url": "https://docs.oracle.com/javase/specs/",
    "is_official": true,
    "source_tier": "official",
    "policy_status": "allowed",
    "content_hash": "sha256..."
  }]
}
```

---

## 3. Policy Modes

The pipeline runs in one of two modes, set via `source_policy_mode` in `00-run-config.json`.

### 3.1 Production Mode (default)

| Source type | Behavior |
|-------------|----------|
| Local file / mock source | **Rejected** — `POLICY_REJECTED`, exit code 1 |
| Non-allowlisted remote domain | **Rejected** — exit code 1 ("non-official domain") |
| Official domain with `http://` scheme | **Rejected** — exit code 1 ("https" error) |
| Official domain with `https://` scheme | **Accepted** — exit code 0 |
| Malformed `evidence_ref` (no `::`) | **Rejected** by manifest gate, exit code 2 |
| Evidence source not in `01-source-index.json` | **Rejected** — exit code 2 |
| Evidence source `is_official: false` | **Rejected** — exit code 2 ("non-official evidence") |
| Evidence hash mismatch | **Rejected** — exit code 2 |

### 3.2 Development Mode

Set `"source_policy_mode": "development"` in run config.

| Source type | Behavior |
|-------------|----------|
| Local file / mock source | **Allowed** — classified `source_tier: "local"`, `is_official: false` |
| Non-allowlisted remote domain | **Allowed** — classified `source_tier: "non_official"` |
| Official domain (any scheme) | Allowed but HTTP emits warning |
| Malformed/legacy `evidence_ref` | **Allowed with warning** — stderr warning printed, rule accepted |
| `is_official: false` sources in manifest | **Still rejected** — non-official evidence rejected in all modes |

> **Note:** Development mode relaxes *ingestion* only. The manifest gate always rejects
> non-official evidence regardless of mode (`write_manifest.py:198`).

---

## 4. Evidence Gate

Every rule in the manifest must link back to a specific, fetched source. The gate enforces:

### 4.1 `evidence_ref` Format

```
<source_label>::<locator>
```

- `source_label` — must match a `source_label` entry in `01-source-index.json`
- `locator` — freeform reference (e.g. `lines 1-5`, `section 3.2`, `JEP-123`)

Separator `::` is **required**. Missing separator is:
- **Production:** rejected with `"malformed evidence_ref (missing '::' separator)"`
- **Development:** permitted with `WARNING [LEGACY_REF]` to stderr

### 4.2 `evidence_hash` Match

`evidence_hash` in a rule must equal `content_hash` in the source index entry for the
matching `source_label`. Hash mismatch → rejected in **all modes**.

### 4.3 `is_official` Check

The source entry in `01-source-index.json` must have `"is_official": true`. Non-official
evidence is rejected in **all modes** — there is no development-mode bypass for this check.

---

## 5. Canonical Allowlist

**Location:** `docs/sources/official-allowlist.json`

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

| Field | Purpose |
|-------|---------|
| `allowed_domains` | Domains whose HTTPS URLs are classified as official. Subdomain matching: `docs.oracle.com` matches `docs.oracle.com` only, not `sub.docs.oracle.com`. |
| `allowed_url_prefixes` | Explicit URL prefixes that receive official classification. Must use `https://` scheme. Provides granular control beyond domain matching. |

**Scheme requirement:** All entries in `allowed_url_prefixes` must use `https://`. An
`http://` URL targeting an allowlisted domain is rejected with a scheme error.

---

## 6. Adding New Allowed Sources

1. Open `docs/sources/official-allowlist.json`.
2. Add domain to `allowed_domains` for broad acceptance, OR add a prefix to `allowed_url_prefixes` for narrow acceptance.
3. Ensure any `allowed_url_prefixes` entry uses `https://`.
4. Run the policy test suite to confirm:
   ```
   python -m pytest tests/test_fetch_source_policy.py tests/test_write_manifest.py -q
   ```
5. Commit with message: `docs: add <domain> to official source allowlist`

**Acceptance criteria:**
- Domain must be an authoritative source for Java/JVM migration evidence.
- Community sources (Stack Overflow, blog posts, wikis) are never added — they are not
  official and cannot produce confidence 1.0 rules.
- Allowed prefixes are preferred over domains when only a specific subtree of a site
  contains versioned specification documents.

---

## 7. Exit Codes

| Code | Meaning | Triggered by |
|------|---------|-------------|
| `0` | Success | Source accepted, classified, indexed |
| `1` | Attention needed | `POLICY_REJECTED` (non-official/local/HTTP in production) |
| `2` | Invalid input / failure | Missing artifacts, JSON parse errors, malformed evidence_ref in production, evidence gate failures |

---

## 8. Hard Constraints

1. **HTTPS-only for official sources.** HTTP URLs are rejected even if the domain is allowlisted.
2. **Non-official evidence rejected in all modes.** No mode bypass for `is_official: false`.
3. **Allowlist is the single source of truth.** `load_official_allowlist()` failure → exit code 2.
4. **Local sources are never official.** Even in development mode, `source_tier` is `"local"` and `is_official` is `false`.
5. **No fabrications.** If `01-source-index.json` is absent, manifest evidence policy checks are skipped to preserve backward compatibility — but a manifest without a source index cannot pass ingestion.
