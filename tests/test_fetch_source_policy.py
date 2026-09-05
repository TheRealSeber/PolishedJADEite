import importlib.util
import json
import pathlib
import sys

# ---------------------------------------------------------------------------
# Soft-404 fixtures: a fake urllib.request.urlopen() response used to drive
# fetch_source.fetch_url() through its real network-fetch code path (as
# opposed to monkeypatching fetch_url itself away), so the soft-404
# detection wired inside main()/fetch_url actually runs.
# ---------------------------------------------------------------------------


class _FakeHTTPResponse:
    def __init__(self, content: str, final_url: str, status: int = 200):
        self._content = content.encode("utf-8")
        self._final_url = final_url
        self.status = status

    def read(self) -> bytes:
        return self._content

    def geturl(self) -> str:
        return self._final_url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _make_fake_urlopen(content: str, final_url: str, status: int = 200):
    def _fake_urlopen(_req, timeout=30):
        return _FakeHTTPResponse(content, final_url, status)

    return _fake_urlopen


_LONG_ORACLE_CONTENT = (
    "Oracle Java SE Language Specification covers the specs of the platform. " * 10
)  # well over MIN_EXPECTED_CONTENT_CHARS, mentions the "oracle"/"specs" label terms

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    _REPO_ROOT / ".claude/skills/jade-core-change-collector/scripts/fetch_source.py"
)


def _load_fetch_source_module():
    spec = importlib.util.spec_from_file_location("fetch_source", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_run_config(tmp_path: pathlib.Path, mode: str = "production") -> pathlib.Path:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    cfg = {
        "run_id": "test-policy",
        "artifacts_path": str(artifacts_dir),
        "source_version": "1.5",
        "target_version": "1.6",
        "source_policy_mode": mode,
    }
    cfg_path = tmp_path / "00-run-config.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    return cfg_path


def _read_source_index(tmp_path: pathlib.Path) -> dict:
    index_path = tmp_path / "artifacts" / "01-source-index.json"
    return json.loads(index_path.read_text(encoding="utf-8"))


def test_production_rejects_local_mock_source(tmp_path, capsys):
    fetch_source = _load_fetch_source_module()
    run_config = _write_run_config(tmp_path, mode="production")
    local_source = tmp_path / "mock-local.md"
    local_source.write_text("# mock\n", encoding="utf-8")

    rc = fetch_source.main(
        [
            "--run-config",
            str(run_config),
            "--source-url",
            str(local_source),
            "--source-label",
            "mock-local",
        ]
    )

    output = capsys.readouterr()
    combined = output.out + output.err
    assert rc == 1
    assert "POLICY_REJECTED" in combined


def test_production_rejects_non_allowlisted_domain(tmp_path, capsys, monkeypatch):
    fetch_source = _load_fetch_source_module()
    run_config = _write_run_config(tmp_path, mode="production")

    def _unexpected_fetch(*_args, **_kwargs):
        raise AssertionError("network fetch should not execute for rejected source")

    monkeypatch.setattr(fetch_source, "fetch_url", _unexpected_fetch)

    rc = fetch_source.main(
        [
            "--run-config",
            str(run_config),
            "--source-url",
            "https://example.com/java-breaks",
            "--source-label",
            "example",
        ]
    )

    output = capsys.readouterr()
    combined = (output.out + output.err).lower()
    assert rc == 1
    assert "non-official domain" in combined


def test_production_accepts_allowlisted_oracle_domain(tmp_path, monkeypatch):
    fetch_source = _load_fetch_source_module()
    run_config = _write_run_config(tmp_path, mode="production")

    def _fake_fetch(_url: str, _timeout_sec: int = 30):
        return {
            "status": "success",
            "error_type": None,
            "error_message": None,
            "content": "Oracle Java SE specs",
            "content_hash": fetch_source.sha256("Oracle Java SE specs"),
            "content_length": len("Oracle Java SE specs"),
            "http_status": 200,
        }

    monkeypatch.setattr(fetch_source, "fetch_url", _fake_fetch)

    rc = fetch_source.main(
        [
            "--run-config",
            str(run_config),
            "--source-url",
            "https://docs.oracle.com/javase/specs/",
            "--source-label",
            "oracle-specs",
        ]
    )

    assert rc == 0
    source_entry = _read_source_index(tmp_path)["sources"][0]
    assert source_entry["source_label"] == "oracle-specs"
    assert source_entry["is_official"] is True
    assert source_entry["source_tier"] == "official"
    assert source_entry["policy_status"] == "allowed"


def test_development_allows_local_source(tmp_path):
    fetch_source = _load_fetch_source_module()
    run_config = _write_run_config(tmp_path, mode="development")
    local_source = tmp_path / "mock-local.md"
    local_source.write_text("# local source\n", encoding="utf-8")

    rc = fetch_source.main(
        [
            "--run-config",
            str(run_config),
            "--source-url",
            str(local_source),
            "--source-label",
            "mock-local-dev",
        ]
    )

    assert rc == 0
    source_entry = _read_source_index(tmp_path)["sources"][0]
    assert source_entry["source_tier"] == "local"
    assert source_entry["is_official"] is False
    assert source_entry["policy_status"] == "allowed"


def test_rejects_malicious_source_label_path_traversal(tmp_path, capsys, monkeypatch):
    fetch_source = _load_fetch_source_module()
    run_config = _write_run_config(tmp_path, mode="development")
    local_source = tmp_path / "safe-file.md"
    local_source.write_text("# safe\n", encoding="utf-8")

    rc = fetch_source.main(
        [
            "--run-config",
            str(run_config),
            "--source-url",
            str(local_source),
            "--source-label",
            "../../etc/passwd",
            "--full-content",
        ]
    )

    output = capsys.readouterr()
    combined = output.out + output.err
    assert rc == 0
    assert "Unsafe source_label rejected" in combined


def test_rejects_unknown_source_policy_mode(tmp_path, capsys):
    fetch_source = _load_fetch_source_module()
    run_config = _write_run_config(tmp_path, mode="bogus_mode")
    local_source = tmp_path / "mock.md"
    local_source.write_text("# mock\n", encoding="utf-8")

    rc = fetch_source.main(
        [
            "--run-config",
            str(run_config),
            "--source-url",
            str(local_source),
            "--source-label",
            "test",
        ]
    )

    output = capsys.readouterr()
    combined = output.out + output.err
    assert rc == 2
    assert "CONFIG_INVALID" in combined


def test_rejects_http_scheme_for_official_domain(tmp_path, capsys, monkeypatch):
    fetch_source = _load_fetch_source_module()
    run_config = _write_run_config(tmp_path, mode="production")

    def _unexpected_fetch(*_args, **_kwargs):
        raise AssertionError("network fetch should not execute for rejected source")

    monkeypatch.setattr(fetch_source, "fetch_url", _unexpected_fetch)

    rc = fetch_source.main(
        [
            "--run-config",
            str(run_config),
            "--source-url",
            "http://docs.oracle.com/javase/specs/",
            "--source-label",
            "oracle-http",
        ]
    )

    output = capsys.readouterr()
    combined = (output.out + output.err).lower()
    assert rc == 1
    assert "http" in combined


def test_allowlist_load_failure_returns_exit_code_2(tmp_path, capsys, monkeypatch):
    fetch_source = _load_fetch_source_module()

    def _force_allowlist_failure():
        raise FileNotFoundError("mocked allowlist not found")

    monkeypatch.setattr(
        fetch_source, "load_official_allowlist", _force_allowlist_failure
    )

    run_config = _write_run_config(tmp_path, mode="production")
    local_source = tmp_path / "mock.md"
    local_source.write_text("# mock\n", encoding="utf-8")

    rc = fetch_source.main(
        [
            "--run-config",
            str(run_config),
            "--source-url",
            str(local_source),
            "--source-label",
            "test",
        ]
    )

    output = capsys.readouterr()
    combined = output.out + output.err
    assert rc == 2
    assert "ALLOWLIST_LOAD_FAILED" in combined


# ---------------------------------------------------------------------------
# Soft-404 policy: an HTTP 200 that actually landed on a homepage / generic
# error page must not be recorded as a successfully-fetched source.
# ---------------------------------------------------------------------------


def test_real_fetch_with_no_redirect_and_good_content_succeeds(
    tmp_path, monkeypatch
):
    """Sanity check: the soft-404 gate must not false-positive on a normal fetch."""
    fetch_source = _load_fetch_source_module()
    run_config = _write_run_config(tmp_path, mode="production")
    requested_url = "https://docs.oracle.com/javase/specs/oracle-specs.html"

    monkeypatch.setattr(
        fetch_source.urllib.request,
        "urlopen",
        _make_fake_urlopen(_LONG_ORACLE_CONTENT, final_url=requested_url),
    )

    rc = fetch_source.main(
        [
            "--run-config",
            str(run_config),
            "--source-url",
            requested_url,
            "--source-label",
            "oracle-specs",
        ]
    )

    assert rc == 0
    source_entry = _read_source_index(tmp_path)["sources"][0]
    assert source_entry["fetch_status"] == "success"


def test_soft_404_redirect_to_site_root_is_rejected(tmp_path, monkeypatch, capsys):
    fetch_source = _load_fetch_source_module()
    run_config = _write_run_config(tmp_path, mode="production")
    requested_url = "https://docs.oracle.com/javase/specs/jls-deep-page.html"

    monkeypatch.setattr(
        fetch_source.urllib.request,
        "urlopen",
        _make_fake_urlopen(
            _LONG_ORACLE_CONTENT, final_url="https://docs.oracle.com/"
        ),
    )

    rc = fetch_source.main(
        [
            "--run-config",
            str(run_config),
            "--source-url",
            requested_url,
            "--source-label",
            "oracle-specs",
        ]
    )

    output = capsys.readouterr()
    combined = output.out + output.err
    assert rc == 1
    assert "SUSPECTED_SOFT_404" in combined
    assert "redirected to the site root" in combined
    source_entry = _read_source_index(tmp_path)["sources"][0]
    assert source_entry["fetch_status"] == "error"
    assert source_entry["error_type"] == "SUSPECTED_SOFT_404"


def test_soft_404_redirect_to_different_host_is_rejected(
    tmp_path, monkeypatch, capsys
):
    fetch_source = _load_fetch_source_module()
    run_config = _write_run_config(tmp_path, mode="production")
    requested_url = "https://docs.oracle.com/javase/specs/jls.html"

    monkeypatch.setattr(
        fetch_source.urllib.request,
        "urlopen",
        _make_fake_urlopen(
            _LONG_ORACLE_CONTENT, final_url="https://example.com/parked"
        ),
    )

    rc = fetch_source.main(
        [
            "--run-config",
            str(run_config),
            "--source-url",
            requested_url,
            "--source-label",
            "oracle-specs",
        ]
    )

    output = capsys.readouterr()
    combined = output.out + output.err
    assert rc == 1
    assert "SUSPECTED_SOFT_404" in combined
    assert "different host" in combined


def test_soft_404_content_not_found_marker_is_rejected(tmp_path, monkeypatch, capsys):
    fetch_source = _load_fetch_source_module()
    run_config = _write_run_config(tmp_path, mode="production")
    requested_url = "https://docs.oracle.com/javase/specs/jls.html"
    content = (
        "Oracle Page Not Found. The specs page you requested (oracle) has moved. "
        * 5
    )

    monkeypatch.setattr(
        fetch_source.urllib.request,
        "urlopen",
        _make_fake_urlopen(content, final_url=requested_url),
    )

    rc = fetch_source.main(
        [
            "--run-config",
            str(run_config),
            "--source-url",
            requested_url,
            "--source-label",
            "oracle-specs",
        ]
    )

    output = capsys.readouterr()
    combined = output.out + output.err
    assert rc == 1
    assert "SUSPECTED_SOFT_404" in combined
    assert "not-found indicator" in combined


def test_soft_404_content_too_short_is_rejected(tmp_path, monkeypatch, capsys):
    fetch_source = _load_fetch_source_module()
    run_config = _write_run_config(tmp_path, mode="production")
    requested_url = "https://docs.oracle.com/javase/specs/jls.html"
    content = "oracle specs stub"  # well under MIN_EXPECTED_CONTENT_CHARS

    monkeypatch.setattr(
        fetch_source.urllib.request,
        "urlopen",
        _make_fake_urlopen(content, final_url=requested_url),
    )

    rc = fetch_source.main(
        [
            "--run-config",
            str(run_config),
            "--source-url",
            requested_url,
            "--source-label",
            "oracle-specs",
        ]
    )

    output = capsys.readouterr()
    combined = output.out + output.err
    assert rc == 1
    assert "SUSPECTED_SOFT_404" in combined
    assert "drastically shorter" in combined


def test_soft_404_missing_label_terms_is_rejected(tmp_path, monkeypatch, capsys):
    fetch_source = _load_fetch_source_module()
    run_config = _write_run_config(tmp_path, mode="production")
    requested_url = "https://docs.oracle.com/javase/specs/jls.html"
    # Long enough, no 404 markers, but never mentions "oracle" or "specs".
    content = "This unrelated marketing copy talks about cloud pricing tiers. " * 10

    monkeypatch.setattr(
        fetch_source.urllib.request,
        "urlopen",
        _make_fake_urlopen(content, final_url=requested_url),
    )

    rc = fetch_source.main(
        [
            "--run-config",
            str(run_config),
            "--source-url",
            requested_url,
            "--source-label",
            "oracle-specs",
        ]
    )

    output = capsys.readouterr()
    combined = output.out + output.err
    assert rc == 1
    assert "SUSPECTED_SOFT_404" in combined
    assert "source-label terms" in combined


def test_allow_redirect_host_flag_suppresses_redirect_check(
    tmp_path, monkeypatch
):
    """A known-legitimate redirect target, passed via --allow-redirect-host,
    must not be flagged as a soft-404 on host/path grounds alone."""
    fetch_source = _load_fetch_source_module()
    run_config = _write_run_config(tmp_path, mode="production")
    requested_url = "https://docs.oracle.com/javase/specs/jls-deep-page.html"

    monkeypatch.setattr(
        fetch_source.urllib.request,
        "urlopen",
        _make_fake_urlopen(
            _LONG_ORACLE_CONTENT, final_url="https://cdn.oracle-mirror.example/jls.html"
        ),
    )

    rc = fetch_source.main(
        [
            "--run-config",
            str(run_config),
            "--source-url",
            requested_url,
            "--source-label",
            "oracle-specs",
            "--allow-redirect-host",
            "cdn.oracle-mirror.example",
        ]
    )

    assert rc == 0
    source_entry = _read_source_index(tmp_path)["sources"][0]
    assert source_entry["fetch_status"] == "success"


def test_allow_redirect_host_flag_does_not_bypass_content_heuristics(
    tmp_path, monkeypatch, capsys
):
    """--allow-redirect-host only silences the host/path check — a genuinely
    broken (too-short / not-found) page on that same host is still rejected."""
    fetch_source = _load_fetch_source_module()
    run_config = _write_run_config(tmp_path, mode="production")
    requested_url = "https://docs.oracle.com/javase/specs/jls-deep-page.html"

    monkeypatch.setattr(
        fetch_source.urllib.request,
        "urlopen",
        _make_fake_urlopen(
            "oracle specs stub", final_url="https://cdn.oracle-mirror.example/jls.html"
        ),
    )

    rc = fetch_source.main(
        [
            "--run-config",
            str(run_config),
            "--source-url",
            requested_url,
            "--source-label",
            "oracle-specs",
            "--allow-redirect-host",
            "cdn.oracle-mirror.example",
        ]
    )

    output = capsys.readouterr()
    combined = output.out + output.err
    assert rc == 1
    assert "SUSPECTED_SOFT_404" in combined
    assert "drastically shorter" in combined
