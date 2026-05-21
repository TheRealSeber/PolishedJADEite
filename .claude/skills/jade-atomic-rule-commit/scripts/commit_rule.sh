#!/usr/bin/env bash
# commit_rule.sh — Stage files, create an atomic rule commit, and log the commit hash.
#
# Usage:
#   commit_rule.sh <rule_id> <artifacts_dir> "<short_description>" <file1> [file2 ...]
#
# Example:
#   commit_rule.sh raw-types artifacts "add generic type parameters" src/Foo.java src/Bar.java
#
# Outputs:
#   artifacts/09-rule-commit-log.json   — {rule_id, commit_hash, message, timestamp, files[]}
#
# Exit codes:
#   0 — success
#   1 — usage / argument error
#   2 — git stage or commit failure
#   3 — commit log write failure

set -euo pipefail

# ── Argument parsing ────────────────────────────────────────────────────────────
if [ $# -lt 4 ]; then
    echo "ERROR [USAGE] commit_rule.sh <rule_id> <artifacts_dir> \"<short_description>\" <file...>" >&2
    exit 1
fi

RULE_ID="$1"
ARTIFACTS_DIR="$2"
SHORT_DESC="$3"
shift 3
FILES=("$@")

if [ ${#FILES[@]} -eq 0 ]; then
    echo "ERROR [NO_FILES] No files provided to commit" >&2
    exit 1
fi

# ── Verify we are inside a git repo ─────────────────────────────────────────────
if ! git rev-parse --git-dir >/dev/null 2>&1; then
    echo "ERROR [NOT_GIT_REPO] $(pwd) is not a git repository" >&2
    exit 2
fi

# ── Safety gate: ensure all provided files exist (at least as tracked) ──────────
MISSING_FILES=()
for f in "${FILES[@]}"; do
    if [ ! -e "$f" ] && ! git ls-files --error-unmatch "$f" >/dev/null 2>&1; then
        MISSING_FILES+=("$f")
    fi
done

if [ ${#MISSING_FILES[@]} -gt 0 ]; then
    echo "ERROR [FILES_NOT_FOUND] The following files do not exist and are not tracked:" >&2
    for f in "${MISSING_FILES[@]}"; do
        echo "  - $f" >&2
    done
    exit 1
fi

# ── Stage the files ─────────────────────────────────────────────────────────────
git add -- "${FILES[@]}"

# ── Build commit message ────────────────────────────────────────────────────────
SUBJECT="fix(migration): resolved ${RULE_ID} - ${SHORT_DESC}"

COMMIT_MSG="${SUBJECT}"
if [ ${#FILES[@]} -gt 5 ]; then
    # Build an Affected: line grouping files by top-level directory
    DIRS=()
    for f in "${FILES[@]}"; do
        topdir="${f%%/*}"
        DIRS+=("$topdir")
    done
    # Deduplicate
    UNIQ_DIRS=($(printf '%s\n' "${DIRS[@]}" | sort -u))
    AFFECTED=$(IFS=, ; echo "${UNIQ_DIRS[*]}")
    COMMIT_MSG="${SUBJECT}"$'\n\n'"Affected: ${AFFECTED}"
fi

# ── Commit ──────────────────────────────────────────────────────────────────────
if ! git commit -m "${SUBJECT}" $([ ${#FILES[@]} -gt 5 ] && printf '%s' "-m Affected: ${AFFECTED}") >/dev/null 2>&1; then
    echo "ERROR [COMMIT_FAILED] git commit returned non-zero" >&2
    exit 2
fi

# ── Retrieve commit hash ────────────────────────────────────────────────────────
COMMIT_HASH=$(git rev-parse HEAD)

# ── Log commit to artifact ──────────────────────────────────────────────────────
LOG_DIR="${ARTIFACTS_DIR}"
mkdir -p "${LOG_DIR}"

LOG_FILE="${LOG_DIR}/09-rule-commit-log.json"

# Build JSON manually to avoid jq dependency
JSON_FILES=""
for f in "${FILES[@]}"; do
    JSON_FILES="${JSON_FILES}    \"$f\",\n"
done
# Trim trailing comma and newline
JSON_FILES="${JSON_FILES%,\\n}"

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

cat > "${LOG_FILE}" <<JSONEOF
{
  "rule_id": "${RULE_ID}",
  "commit_hash": "${COMMIT_HASH}",
  "message": "${SUBJECT}",
  "timestamp": "${TIMESTAMP}",
  "files": [
${JSON_FILES}
  ]
}
JSONEOF

if [ ! -s "${LOG_FILE}" ]; then
    echo "ERROR [COMMIT_LOG_WRITE_FAILED] Failed to write ${LOG_FILE}" >&2
    exit 3
fi

echo "${COMMIT_HASH}"
exit 0
