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

# ---------------------------------------------------------------------------
# Soft-404 detection — a redirect that returns HTTP 200 but actually landed
# on a generic error/home page instead of the requested document.
# ---------------------------------------------------------------------------
_SOFT_404_TEXT_MARKERS: tuple[str, ...] = (
    "page not found",
    "404 not found",
    "error 404",
)
_SOFT_404_404_PATTERN = re.compile(r"\b404\b")
MIN_EXPECTED_CONTENT_CHARS = 300


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
                "final_url": resp.geturl(),
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


def extract_label_terms(label: str) -> Set[str]:
    """Pull meaningful search terms out of a source label for content sanity-checks.

    Short/numeric-only tokens are dropped since they are too generic to prove
    anything about whether the fetched content matches what was asked for.
    """
    tokens = re.findall(r"[A-Za-z0-9]+", label.lower())
    return {t for t in tokens if len(t) >= 4}


def parse_allow_redirect_hosts(raw_values: Optional[list]) -> Set[str]:
    """Normalize --allow-redirect-host values (repeatable and/or comma-separated)."""
    hosts: Set[str] = set()
    for raw in raw_values or []:
        for piece in str(raw).split(","):
            piece = piece.strip().lower()
            if piece:
                hosts.add(piece)
    return hosts


def detect_soft_404(
    requested_url: str,
    final_url: Optional[str],
    content: Optional[str],
    source_label: str,
    allow_redirect_hosts: Optional[Set[str]] = None,
) -> Optional[str]:
    """Detect a "soft 404": an HTTP 200 response that did not actually deliver
    the requested source (typically a redirect to a homepage or generic error
    page). Returns a human-readable reason string when suspicious, else None.

    Checks (any one is enough to flag the fetch as suspicious):
      1. The final URL (after redirects) lands on a different host, or on a
         different/shallower path than what was requested — unless that host
         is explicitly trusted via allow_redirect_hosts.
      2. The content contains an explicit not-found marker ("404", "page not
         found", ...).
      3. The content is drastically shorter than a real document would be.
      4. The content contains none of the meaningful terms from the source
         label (i.e. nothing ties the page back to what was asked for).
    """
    if not content:
        return None

    allow_redirect_hosts = allow_redirect_hosts or set()
    reasons: list[str] = []

    if final_url:
        requested = urlparse(requested_url)
        final = urlparse(final_url)
        requested_host = (requested.hostname or "").lower()
        final_host = (final.hostname or "").lower()
        host_is_trusted = final_host in allow_redirect_hosts

        if not host_is_trusted:
            if final_host and final_host != requested_host:
                reasons.append(
                    f"redirected to a different host: requested {requested_host!r}, "
                    f"landed on {final_host!r}"
                )
            else:
                requested_path = (requested.path or "/").rstrip("/") or "/"
                final_path = (final.path or "/").rstrip("/") or "/"
                if final_path != requested_path and final_path in ("", "/"):
                    reasons.append(
                        f"redirected to the site root: requested path "
                        f"{requested.path or '/'!r}, landed on {final.path or '/'!r}"
                    )

    lowered = content.lower()
    if _SOFT_404_404_PATTERN.search(lowered) or any(
        marker in lowered for marker in _SOFT_404_TEXT_MARKERS
    ):
        reasons.append('content contains a not-found indicator ("404" / "page not found")')

    stripped_len = len(content.strip())
    if stripped_len < MIN_EXPECTED_CONTENT_CHARS:
        reasons.append(
            f"content drastically shorter than expected ({stripped_len} chars < "
            f"{MIN_EXPECTED_CONTENT_CHARS})"
        )

    label_terms = extract_label_terms(source_label)
    if label_terms and not any(term in lowered for term in label_terms):
        reasons.append(
            "content contains none of the source-label terms: "
            f"{sorted(label_terms)}"
        )

    if not reasons:
        return None
    return "SUSPECTED_SOFT_404: " + "; ".join(reasons)


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
    parser.add_argument(
        "--allow-redirect-host",
        action="append",
        default=None,
        metavar="HOST",
        help=(
            "Host(s) allowed to be the final destination of a redirect "
            "(repeatable, or comma-separated). Suppresses only the "
            "redirect-host/path soft-404 check for that host — content "
            "heuristics (404 markers, size, label terms) still apply."
        ),
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
        # Soft-404 detection only applies to a real network round trip: it
        # needs the actual final_url reached (after any redirects), which is
        # only present when fetch_url really ran (not when a caller/test has
        # substituted a stand-in fetch_url that returns a bare result dict).
        if result["status"] == "success" and result.get("final_url"):
            allow_redirect_hosts = parse_allow_redirect_hosts(args.allow_redirect_host)
            soft_404_reason = detect_soft_404(
                requested_url=source_url,
                final_url=result.get("final_url"),
                content=result.get("content"),
                source_label=source_label,
                allow_redirect_hosts=allow_redirect_hosts,
            )
            if soft_404_reason:
                result = {
                    "status": "error",
                    "error_type": "SUSPECTED_SOFT_404",
                    "error_message": soft_404_reason,
                    "content": None,
                    "content_hash": None,
                    "content_length": 0,
                    "http_status": result.get("http_status"),
                }
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
    try:
        print(f"[{status}] {source_label} → {source_url}")
    except UnicodeEncodeError:
        print(f"[{status}] {source_label} -> {source_url}")
    if result["status"] != "success":
        try:
            print(f"       {result.get('error_type')}: {result.get('error_message')}")
        except UnicodeEncodeError:
            print(
                f"       {result.get('error_type', '')}: {result.get('error_message', '')}"
            )

    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
