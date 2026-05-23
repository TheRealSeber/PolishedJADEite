#!/usr/bin/env python3
"""fetch_source.py — Ingest one source (URL or local file) and update the source index.

Part of jade-change-collector-strict.  Never invents content — only records what was
actually retrieved.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
import urllib.error
import urllib.request
from typing import Dict, Optional, Set
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Paywall / block indicators — domains or URL patterns known to require auth
# ---------------------------------------------------------------------------
_PAYWALL_DOMAINS: Set[str] = {
    "dl.acm.org",
    "ieeexplore.ieee.org",
    "link.springer.com",
    "sciencedirect.com",
    "jcp.org",
}

_PAYWALL_PATH_TOKENS: Set[str] = {
    "/subscription",
    "/premium",
    "/paywall",
}

_LOCAL_HOSTS: Set[str] = {"localhost", "127.0.0.1", "0.0.0.0"}


def iso_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def read_json(path: pathlib.Path) -> Dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def repo_root_from_script() -> pathlib.Path:
    # fetch_source.py -> scripts -> jade-core-change-collector -> skills -> .claude -> repo
    return pathlib.Path(__file__).resolve().parents[4]


def sanitize_label(label: str) -> str | None:
    if ".." in label:
        return None
    sanitized = re.sub(r"[^A-Za-z0-9._\-]", "_", label)
    if not sanitized:
        sanitized = "unnamed"
    return sanitized


def load_official_allowlist() -> Dict:
    allowlist_path = (
        repo_root_from_script() / "docs" / "sources" / "official-allowlist.json"
    )
    payload = read_json(allowlist_path)
    return {
        "allowed_domains": [d.lower() for d in payload.get("allowed_domains", [])],
        "allowed_url_prefixes": payload.get("allowed_url_prefixes", []),
    }


def _host_matches_allowlist(host: str, allowlist: Dict) -> bool:
    for allowed_domain in allowlist.get("allowed_domains", []):
        if host == allowed_domain or host.endswith(f".{allowed_domain}"):
            return True
    return False


def is_allowlisted_url(source: str, allowlist: Dict) -> bool:
    parsed = urlparse(source)
    if parsed.scheme == "http":
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False

    if _host_matches_allowlist(host, allowlist):
        return True

    for prefix in allowlist.get("allowed_url_prefixes", []):
        if source.startswith(prefix):
            return True
    return False


def classify_source(source: str, allowlist: Dict) -> Dict[str, object]:
    if not is_url(source):
        return {
            "source_tier": "local",
            "is_official": False,
            "policy_reason": "local source path is not permitted in production mode",
        }

    parsed = urlparse(source)
    host = (parsed.hostname or "").lower()

    if host in _LOCAL_HOSTS or host.endswith(".local"):
        return {
            "source_tier": "local",
            "is_official": False,
            "policy_reason": f"local/mock host is not permitted in production mode: {host}",
        }

    if is_allowlisted_url(source, allowlist):
        return {
            "source_tier": "official",
            "is_official": True,
            "policy_reason": None,
        }

    if _host_matches_allowlist(host, allowlist) and parsed.scheme == "http":
        return {
            "source_tier": "non_official",
            "is_official": False,
            "policy_reason": f"HTTP scheme rejected for allowlisted domain: {host} (require HTTPS)",
        }

    return {
        "source_tier": "non_official",
        "is_official": False,
        "policy_reason": f"non-official domain is not allowlisted: {host or source}",
    }


def write_json(path: pathlib.Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    tmp.replace(path)


def is_url(source: str) -> bool:
    parsed = urlparse(source)
    return bool(parsed.scheme and parsed.netloc)


def detect_paywall(source: str) -> Optional[str]:
    """Return a human-readable reason if the source looks like a paywall target."""
    parsed = urlparse(source)
    host = parsed.hostname or ""
    path = parsed.path or ""
    if host in _PAYWALL_DOMAINS:
        return f"paywall domain: {host}"
    for tok in _PAYWALL_PATH_TOKENS:
        if tok in path.lower():
            return f"paywall path token: {tok}"
    return None


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def strip_html(raw: str) -> str:
    """Remove HTML tags and decode entities to produce readable text."""
    import html as _html
    import re as _re

    text = _re.sub(
        r"<script[^>]*?>.*?</script>", " ", raw, flags=_re.DOTALL | _re.IGNORECASE
    )
    text = _re.sub(
        r"<style[^>]*?>.*?</style>", " ", text, flags=_re.DOTALL | _re.IGNORECASE
    )
    text = _re.sub(r"<[^>]+?>", " ", text)
    text = _html.unescape(text)
    text = _re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


def looks_like_html(text: str) -> bool:
    return bool(
        re.search(r"<\s*(html|head|body|div|p|script|meta)\b", text, re.IGNORECASE)
    )


def fetch_url(url: str, timeout_sec: int = 30) -> Dict:
    """Fetch a URL and return a structured result dict."""
    paywall_reason = detect_paywall(url)
    if paywall_reason:
        return {
            "status": "error",
            "error_type": "PAYWALL",
            "error_message": paywall_reason,
            "content": None,
            "content_hash": None,
            "content_length": 0,
        }

    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "jade-change-collector/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("latin-1", errors="replace")
            content_hash = sha256(text)
            return {
                "status": "success",
                "error_type": None,
                "error_message": None,
                "content": text,
                "content_hash": content_hash,
                "content_length": len(text),
                "http_status": resp.status,
            }
    except urllib.error.HTTPError as exc:
        return {
            "status": "error",
            "error_type": "HTTP_ERROR",
            "error_message": f"HTTP {exc.code}: {exc.reason}",
            "content": None,
            "content_hash": None,
            "content_length": 0,
            "http_status": exc.code,
        }
    except urllib.error.URLError as exc:
        return {
            "status": "error",
            "error_type": "URL_ERROR",
            "error_message": str(exc.reason),
            "content": None,
            "content_hash": None,
            "content_length": 0,
        }
    except TimeoutError:
        return {
            "status": "error",
            "error_type": "TIMEOUT",
            "error_message": f"Timed out after {timeout_sec}s",
            "content": None,
            "content_hash": None,
            "content_length": 0,
        }


def fetch_file(path: pathlib.Path) -> Dict:
    """Read a local file and return a structured result dict."""
    if not path.exists():
        return {
            "status": "error",
            "error_type": "FILE_NOT_FOUND",
            "error_message": str(path),
            "content": None,
            "content_hash": None,
            "content_length": 0,
        }
    try:
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1", errors="replace")
        content_hash = sha256(text)
        return {
            "status": "success",
            "error_type": None,
            "error_message": None,
            "content": text,
            "content_hash": content_hash,
            "content_length": len(text),
        }
    except OSError as exc:
        return {
            "status": "error",
            "error_type": "FILE_READ_ERROR",
            "error_message": str(exc),
            "content": None,
            "content_hash": None,
            "content_length": 0,
        }


# ---------------------------------------------------------------------------
# Source index helpers
# ---------------------------------------------------------------------------
_SOURCE_INDEX_FIELDS = {
    "source_label",
    "source_url",
    "fetch_status",
    "error_type",
    "error_message",
    "content_hash",
    "content_length",
    "http_status",
    "content_snippet",
    "fetched_at",
    "source_tier",
    "is_official",
    "policy_status",
}


def load_or_create_index(index_path: pathlib.Path, run_id: str) -> Dict:
    if index_path.exists():
        return read_json(index_path)
    return {"run_id": run_id, "sources": []}


def upsert_source_entry(index: Dict, entry: Dict) -> Dict:
    """Insert or update a source entry in the index, keyed by source_url."""
    url = entry["source_url"]
    sources: list = index.setdefault("sources", [])
    for i, existing in enumerate(sources):
        if existing.get("source_url") == url:
            sources[i] = entry
            return index
    sources.append(entry)
    return index


def trim_content(entry: Dict, max_chars: int = 2000) -> Dict:
    """Replace full content with a truncated snippet to control index size."""
    content = entry.pop("content", None)
    if content and isinstance(content, str) and len(content) > 0:
        entry["content_snippet"] = content[:max_chars]
    else:
        entry["content_snippet"] = None
    return entry


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch one source for jade-change-collector-strict"
    )
    parser.add_argument(
        "--run-config",
        required=True,
        help="Path to 00-run-config.json",
    )
    parser.add_argument(
        "--source-url",
        required=True,
        help="URL or local file path of the source to fetch",
    )
    parser.add_argument(
        "--source-label",
        required=True,
        help="Human-readable label for this source",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="HTTP fetch timeout in seconds",
    )
    parser.add_argument(
        "--full-content",
        action="store_true",
        help="Store full content in index (default: snippet only)",
    )
    args = parser.parse_args(argv)

    config_path = pathlib.Path(args.run_config)
    if not config_path.exists():
        print(f"ERROR [CONFIG_NOT_FOUND] {config_path}", file=sys.stderr)
        return 2

    cfg = read_json(config_path)
    required = {"run_id", "artifacts_path", "source_version", "target_version"}
    missing = sorted(required - set(cfg.keys()))
    if missing:
        print(
            f"ERROR [CONFIG_INVALID] Missing keys: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 2

    artifacts_dir = pathlib.Path(cfg["artifacts_path"])
    index_path = artifacts_dir / "01-source-index.json"
    source_policy_mode = (
        str(cfg.get("source_policy_mode", "production")).strip().lower()
    )
    if source_policy_mode not in {"production", "development"}:
        print(
            f"CONFIG_INVALID: unknown source_policy_mode: {source_policy_mode!r}",
            file=sys.stderr,
        )
        return 2

    try:
        allowlist = load_official_allowlist()
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"ALLOWLIST_LOAD_FAILED: {exc}", file=sys.stderr)
        return 2

    source_url = args.source_url.strip()
    source_label = args.source_label.strip()

    source_classification = classify_source(source_url, allowlist)
    source_tier = str(source_classification["source_tier"])
    is_official = bool(source_classification["is_official"])

    policy_rejected = source_policy_mode == "production" and not is_official
    policy_status = "rejected" if policy_rejected else "allowed"

    # Fetch
    if policy_rejected:
        result = {
            "status": "error",
            "error_type": "POLICY_REJECTED",
            "error_message": str(
                source_classification.get("policy_reason") or "source blocked by policy"
            ),
            "content": None,
            "content_hash": None,
            "content_length": 0,
        }
    elif is_url(source_url):
        result = fetch_url(source_url, args.timeout)
    else:
        result = fetch_file(pathlib.Path(source_url))

    entry: Dict = {
        "source_label": source_label,
        "source_url": source_url,
        "fetch_status": result["status"],
        "error_type": result.get("error_type"),
        "error_message": result.get("error_message"),
        "content_hash": result.get("content_hash"),
        "content_length": result.get("content_length"),
        "http_status": result.get("http_status"),
        "fetched_at": iso_now(),
        "source_tier": source_tier,
        "is_official": is_official,
        "policy_status": policy_status,
    }

    # Attach full content so the agent can read it; caller decides trim
    content = result.get("content")
    if content:
        entry["content"] = content
        # Write clean text file for LLM reading comprehension
        clean = strip_html(content) if looks_like_html(content) else content
        safe_label = sanitize_label(source_label)
        if safe_label is None:
            print(
                f"       [SKIP] Unsafe source_label rejected: {source_label!r}",
                file=sys.stderr,
            )
        else:
            content_path = artifacts_dir / f"01-source-content-{safe_label}.txt"
            try:
                content_path_resolved = content_path.resolve()
                artifacts_resolved = artifacts_dir.resolve()
                if content_path_resolved.is_relative_to(artifacts_resolved):
                    content_path.write_text(clean, encoding="utf-8", errors="replace")
                    print(
                        f"       Clean text written to {content_path} ({len(clean)} chars)"
                    )
                else:
                    print(
                        f"       [SKIP] Unsafe source_label rejected by path validation: {source_label!r}",
                        file=sys.stderr,
                    )
            except (OSError, ValueError) as exc:
                print(
                    f"       [SKIP] Failed to write content file: {exc}",
                    file=sys.stderr,
                )

    if not args.full_content:
        entry = trim_content(entry)

    # Persist
    index = load_or_create_index(index_path, cfg["run_id"])
    index = upsert_source_entry(index, entry)
    write_json(index_path, index)

    status = "OK" if result["status"] == "success" else "FAIL"
    print(f"[{status}] {source_label} → {source_url}")
    if result["status"] != "success":
        print(f"       {result.get('error_type')}: {result.get('error_message')}")

    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
