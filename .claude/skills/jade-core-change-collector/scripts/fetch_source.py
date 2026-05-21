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
def main() -> int:
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
    args = parser.parse_args()

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

    source_url = args.source_url.strip()
    source_label = args.source_label.strip()

    # Fetch
    if is_url(source_url):
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
    }

    # Attach full content so collect_changes.py can use it; caller decides trim
    content = result.get("content")
    if content:
        entry["content"] = content

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
