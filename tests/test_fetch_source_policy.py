import importlib.util
import json
import pathlib
import sys

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
