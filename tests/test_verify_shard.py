"""Tests for jade-core-verification scripts/verify_shard.py."""

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / ".claude/skills/jade-core-verification/scripts/verify_shard.py"

DEFAULT_RULE_ID = "RULE"
DEFAULT_SHARD_ID = "RULE-body-local-001"
DEFAULT_EDITABLE_FILE = "src/jade/src/jade/core/Foo.java"


def load_verify_shard():
    spec = importlib.util.spec_from_file_location("verify_shard_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def make_shard(
    shard_id=DEFAULT_SHARD_ID,
    rule_id=DEFAULT_RULE_ID,
    shard_class="body-local",
    editable_files=None,
    read_only_context=None,
    entry_points=None,
    invariants=None,
    graph_artifact="03.5-knowledge-graph.json",
    parallel_safe=True,
):
    """Build a shard matching plan_shards.py's real output shape (9 keys):
    shard_id, rule_id, class, editable_files, read_only_context,
    entry_points, invariants, graph_artifact, parallel_safe.
    """
    editable_files = (
        editable_files if editable_files is not None else [DEFAULT_EDITABLE_FILE]
    )
    read_only_context = read_only_context if read_only_context is not None else []
    return {
        "shard_id": shard_id,
        "rule_id": rule_id,
        "class": shard_class,
        "editable_files": editable_files,
        "read_only_context": read_only_context,
        "entry_points": entry_points if entry_points is not None else [],
        "invariants": invariants if invariants is not None else [],
        "graph_artifact": graph_artifact,
        "parallel_safe": parallel_safe,
    }


def make_plan(rule_id=DEFAULT_RULE_ID, shards=None):
    return {
        "schema_version": 1,
        "run_id": "test-run",
        "rule_id": rule_id,
        "shards": shards if shards is not None else [make_shard(rule_id=rule_id)],
    }


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def prepare_run(
    tmp_root,
    *,
    editable_files=None,
    read_only_context=None,
    rule_id=DEFAULT_RULE_ID,
    shard_id=DEFAULT_SHARD_ID,
    shard_class="body-local",
    with_baseline_jar=True,
    target_version="1.6",
    commit_log=None,
):
    """Build a self-contained (workspace, artifacts) pair under tmp_root."""
    editable_files = (
        editable_files if editable_files is not None else [DEFAULT_EDITABLE_FILE]
    )
    read_only_context = read_only_context if read_only_context is not None else []

    workspace = tmp_root / "workspace"
    for relpath in list(editable_files) + list(read_only_context):
        full = workspace / relpath
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text("package jade.core;\npublic class Foo {}\n", encoding="utf-8")

    if with_baseline_jar:
        jar_path = workspace / "src/jade/lib/jade.jar"
        jar_path.parent.mkdir(parents=True, exist_ok=True)
        jar_path.write_bytes(b"PK\x03\x04fake-jar")

    artifacts = tmp_root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    run_config = {
        "run_id": "test-run",
        "workspace_path": "unused",
        "target_version": target_version,
    }
    write_json(artifacts / "00-run-config.json", run_config)

    shard = make_shard(
        shard_id=shard_id,
        rule_id=rule_id,
        shard_class=shard_class,
        editable_files=editable_files,
        read_only_context=read_only_context,
    )
    plan = make_plan(rule_id=rule_id, shards=[shard])
    write_json(artifacts / f"05-rule-shards-{rule_id}.json", plan)

    if commit_log is not None:
        write_json(artifacts / "09-rule-commit-log.json", commit_log)

    return workspace, artifacts


def build_argv(artifacts, rule_id, shard_id, **kwargs):
    argv = [
        "--artifacts-dir", str(artifacts),
        "--rule-id", rule_id,
        "--shard-id", shard_id,
    ]
    if kwargs.get("workspace") is not None:
        argv += ["--workspace", str(kwargs["workspace"])]
    if kwargs.get("baseline_jar") is not None:
        argv += ["--baseline-jar", str(kwargs["baseline_jar"])]
    if kwargs.get("run_config") is not None:
        argv += ["--run-config", str(kwargs["run_config"])]
    if kwargs.get("shards_artifact") is not None:
        argv += ["--shards-artifact", str(kwargs["shards_artifact"])]
    if kwargs.get("javac_encoding") is not None:
        argv += ["--javac-encoding", kwargs["javac_encoding"]]
    if kwargs.get("timeout_seconds") is not None:
        argv += ["--timeout-seconds", str(kwargs["timeout_seconds"])]
    if kwargs.get("output") is not None:
        argv += ["--output", str(kwargs["output"])]
    return argv


def patch_docker_ready(monkeypatch, mod):
    """Make the environment gate (shutil.which + docker info) pass."""
    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(
        mod.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0)
    )


def artifact_path(artifacts, shard_id=DEFAULT_SHARD_ID):
    return artifacts / f"07-shard-verify-{shard_id}.json"


def log_path(artifacts, shard_id=DEFAULT_SHARD_ID):
    return artifacts / f"07-shard-verify-{shard_id}.log"


# ---------------------------------------------------------------------------
# Environment gate -- exit 3, never any artifact
# ---------------------------------------------------------------------------
def test_docker_missing_exits_3_and_writes_no_artifact(tmp_path, monkeypatch, capsys):
    mod = load_verify_shard()
    workspace, artifacts = prepare_run(tmp_path)
    monkeypatch.setattr(mod.shutil, "which", lambda name: None)

    rc = mod.main(build_argv(artifacts, DEFAULT_RULE_ID, DEFAULT_SHARD_ID, workspace=workspace))

    assert rc == 3
    assert not artifact_path(artifacts).exists()
    assert not log_path(artifacts).exists()
    assert "ERROR [DOCKER_NOT_FOUND]" in capsys.readouterr().err


def test_docker_daemon_unreachable_exits_3(tmp_path, monkeypatch, capsys):
    mod = load_verify_shard()
    workspace, artifacts = prepare_run(tmp_path)
    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(
        mod.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1)
    )

    rc = mod.main(build_argv(artifacts, DEFAULT_RULE_ID, DEFAULT_SHARD_ID, workspace=workspace))

    assert rc == 3
    assert not artifact_path(artifacts).exists()
    assert "ERROR [DOCKER_DAEMON_UNREACHABLE]" in capsys.readouterr().err


def test_never_silent_pass_without_docker(tmp_path, monkeypatch):
    mod = load_verify_shard()
    workspace, artifacts = prepare_run(tmp_path)
    monkeypatch.setattr(mod.shutil, "which", lambda name: None)

    rc = mod.main(build_argv(artifacts, DEFAULT_RULE_ID, DEFAULT_SHARD_ID, workspace=workspace))

    assert rc == 3
    for path in artifacts.rglob("*"):
        if path.is_file():
            assert "PASS" not in path.read_text(encoding="utf-8", errors="ignore")


# ---------------------------------------------------------------------------
# Docker image resolution -- constraint #12, central registry only
# ---------------------------------------------------------------------------
def test_docker_image_resolved_from_central_registry_for_java8():
    mod = load_verify_shard()
    rv = mod._load_runtime_verify()
    registry = rv.load_docker_image_registry(mod.DOCKER_IMAGE_CONFIG_PATH)
    config = json.loads(mod.DOCKER_IMAGE_CONFIG_PATH.read_text(encoding="utf-8"))

    image = rv.resolve_docker_image("1.8", registry)
    key = rv.registry_key_for_runtime_version("1.8", registry)

    assert image == config["java-8"]
    assert key == "java-8"


def test_docker_image_registry_key_for_target_11_and_17():
    mod = load_verify_shard()
    rv = mod._load_runtime_verify()
    registry = rv.load_docker_image_registry(mod.DOCKER_IMAGE_CONFIG_PATH)
    config = json.loads(mod.DOCKER_IMAGE_CONFIG_PATH.read_text(encoding="utf-8"))

    assert rv.registry_key_for_runtime_version("11", registry) == "java-11"
    assert rv.resolve_docker_image("11", registry) == config["java-11"]

    assert rv.registry_key_for_runtime_version("17", registry) == "java-17"
    assert rv.resolve_docker_image("17", registry) == config["java-17"]


def test_source_contains_no_hardcoded_docker_image():
    text = SCRIPT.read_text(encoding="utf-8")
    for forbidden in ("frekele", "eclipse-temurin", "maven:3", "openjdk"):
        assert forbidden not in text


def test_javac_source_target_derived_from_target_version(tmp_path, monkeypatch):
    mod = load_verify_shard()
    patch_docker_ready(monkeypatch, mod)
    monkeypatch.setattr(mod, "run_shard_in_docker", lambda cmd, bd, t: (0, "", ""))

    ws1, art1 = prepare_run(tmp_path / "v16", target_version="1.6")
    rc = mod.main(build_argv(art1, DEFAULT_RULE_ID, DEFAULT_SHARD_ID, workspace=ws1))
    assert rc in (0, 1)  # PASS; may carry the advisory baseline-jar-commit warning
    payload1 = json.loads(artifact_path(art1).read_text(encoding="utf-8"))
    assert payload1["status"] == "PASS"
    assert payload1["javac_source"] == "1.6"
    assert payload1["javac_target"] == "1.6"

    ws2, art2 = prepare_run(tmp_path / "v8", target_version="8")
    rc = mod.main(build_argv(art2, DEFAULT_RULE_ID, DEFAULT_SHARD_ID, workspace=ws2))
    assert rc in (0, 1)
    payload2 = json.loads(artifact_path(art2).read_text(encoding="utf-8"))
    assert payload2["status"] == "PASS"
    assert payload2["javac_source"] == "1.8"
    assert payload2["javac_target"] == "1.8"


# ---------------------------------------------------------------------------
# Baseline jar -- never built by this script, hard exit 3 when missing
# ---------------------------------------------------------------------------
def test_baseline_jar_missing_exit_3_with_explicit_message(tmp_path, monkeypatch, capsys):
    mod = load_verify_shard()
    workspace, artifacts = prepare_run(tmp_path, with_baseline_jar=False)
    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/docker")

    rc = mod.main(build_argv(artifacts, DEFAULT_RULE_ID, DEFAULT_SHARD_ID, workspace=workspace))

    assert rc == 3
    err = capsys.readouterr().err
    assert "ERROR [BASELINE_JAR_NOT_FOUND]" in err
    assert "Build the jar at the previous rule commit before verifying a shard" in err
    assert not artifact_path(artifacts).exists()


# ---------------------------------------------------------------------------
# build_docker_command -- pure, no I/O, no Docker required
# ---------------------------------------------------------------------------
def test_docker_command_mounts_workspace_read_only():
    mod = load_verify_shard()
    cmd = mod.build_docker_command(
        image="image:tag",
        ws_docker="/tmp/ws",
        build_docker="/tmp/build",
        classpath="/jar/jade.jar",
        javac_encoding="ISO-8859-1",
        javac_source="1.8",
        javac_target="1.8",
    )

    assert "/tmp/ws:/ws:ro" in cmd
    assert "/tmp/build:/out" in cmd
    ro_mounts = [part for part in cmd if part.endswith(":/ws:ro")]
    assert len(ro_mounts) == 1
    idx_w = cmd.index("-w")
    assert cmd[idx_w + 1] == "/out"


def test_docker_command_has_no_sourcepath_and_uses_argfile():
    mod = load_verify_shard()
    cmd = mod.build_docker_command(
        image="image:tag",
        ws_docker="/tmp/ws",
        build_docker="/tmp/build",
        classpath="/jar/jade.jar",
        javac_encoding="UTF-8",
        javac_source="1.8",
        javac_target="1.8",
    )

    assert cmd[-1] == "@/out/sources.txt"
    assert "-implicit:none" in cmd
    assert "-sourcepath" not in cmd


def test_docker_command_mounts_jar_dir_when_outside_workspace():
    mod = load_verify_shard()
    cmd = mod.build_docker_command(
        image="image:tag",
        ws_docker="/tmp/ws",
        build_docker="/tmp/build",
        classpath="/jar/jade.jar",
        javac_encoding="UTF-8",
        javac_source="1.8",
        javac_target="1.8",
        jar_dir_docker="/tmp/jar-dir",
    )

    assert "/tmp/jar-dir:/jar:ro" in cmd


def test_sources_file_lists_editable_files_only(tmp_path, monkeypatch):
    mod = load_verify_shard()
    editable = [
        "src/jade/src/jade/core/Foo.java",
        "src/jade/src/jade/core/Bar.java",
    ]
    read_only = ["src/jade/src/jade/core/Ctx.java"]
    workspace, artifacts = prepare_run(
        tmp_path, editable_files=editable, read_only_context=read_only
    )
    patch_docker_ready(monkeypatch, mod)

    captured = {}

    def fake_run(cmd, build_dir, timeout):
        captured["sources"] = (build_dir / "sources.txt").read_text(encoding="utf-8")
        return 0, "", ""

    monkeypatch.setattr(mod, "run_shard_in_docker", fake_run)

    rc = mod.main(build_argv(artifacts, DEFAULT_RULE_ID, DEFAULT_SHARD_ID, workspace=workspace))

    assert rc in (0, 1)  # PASS; may carry the advisory baseline-jar-commit warning
    lines = captured["sources"].splitlines()
    assert len(lines) == len(editable)
    assert lines == [f"/ws/{relpath}" for relpath in sorted(editable)]
    for relpath in read_only:
        assert f"/ws/{relpath}" not in lines


# ---------------------------------------------------------------------------
# parse_javac_output
# ---------------------------------------------------------------------------
def test_parse_javac_output_extracts_errors():
    mod = load_verify_shard()
    log = (
        "/ws/src/jade/src/jade/core/AID.java:412: error: incompatible types\n"
        "/ws/src/A.java:7: warning: deprecation\n"
        "2 errors\n"
    )

    errors, warning_count = mod.parse_javac_output(log)

    assert errors == [
        {"file": "src/jade/src/jade/core/AID.java", "line": 412, "message": "incompatible types"}
    ]
    assert warning_count == 1


def test_parse_javac_output_strips_container_prefix_only_once():
    mod = load_verify_shard()
    log = (
        "/ws/src/ws/Foo.java:3: error: boom\n"
        "src/NoPrefix.java:5: error: also boom\n"
    )

    errors, _ = mod.parse_javac_output(log)

    files = {e["file"] for e in errors}
    assert "src/ws/Foo.java" in files
    assert "src/NoPrefix.java" in files


def test_parse_javac_output_deduplicates_and_sorts():
    mod = load_verify_shard()
    log = "\n".join(
        [
            "/ws/b/File.java:5: error: dup",
            "/ws/b/File.java:5: error: dup",
            "/ws/b/File.java:5: error: dup",
            "/ws/a/File.java:1: error: first",
        ]
    )

    errors, _ = mod.parse_javac_output(log)

    assert errors == [
        {"file": "a/File.java", "line": 1, "message": "first"},
        {"file": "b/File.java", "line": 5, "message": "dup"},
    ]


# ---------------------------------------------------------------------------
# Status derivation -- PASS iff exit_code == 0 and error_count == 0
# ---------------------------------------------------------------------------
def test_status_pass_requires_exit_zero_and_zero_errors(tmp_path, monkeypatch):
    mod = load_verify_shard()
    # A warning-free run needs a non-empty, on-disk read_only_context and a
    # matching commit-log entry -- otherwise PASS still carries advisory
    # warnings and exits 1, not 0 (covered separately below).
    workspace, artifacts = prepare_run(
        tmp_path,
        read_only_context=["src/jade/src/jade/core/Ctx.java"],
        commit_log={
            "rule_id": DEFAULT_RULE_ID,
            "commit_hash": "deadbeef",
            "message": "m",
            "timestamp": "2026-01-01T00:00:00Z",
            "files": [],
        },
    )
    patch_docker_ready(monkeypatch, mod)
    monkeypatch.setattr(mod, "run_shard_in_docker", lambda cmd, bd, t: (0, "", ""))

    rc = mod.main(build_argv(artifacts, DEFAULT_RULE_ID, DEFAULT_SHARD_ID, workspace=workspace))

    assert rc == 0
    payload = json.loads(artifact_path(artifacts).read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert payload["error_count"] == 0
    assert payload["exit_code"] == 0


def test_status_fail_when_javac_exit_nonzero(tmp_path, monkeypatch):
    mod = load_verify_shard()
    workspace, artifacts = prepare_run(tmp_path)
    patch_docker_ready(monkeypatch, mod)
    log = f"/ws/{DEFAULT_EDITABLE_FILE}:10: error: cannot find symbol\n1 error\n"
    monkeypatch.setattr(mod, "run_shard_in_docker", lambda cmd, bd, t: (1, log, ""))

    rc = mod.main(build_argv(artifacts, DEFAULT_RULE_ID, DEFAULT_SHARD_ID, workspace=workspace))

    assert rc == 2
    assert artifact_path(artifacts).exists()
    payload = json.loads(artifact_path(artifacts).read_text(encoding="utf-8"))
    assert payload["status"] == "FAIL"
    assert payload["error_count"] == 1
    assert log_path(artifacts).exists()
    assert "cannot find symbol" in log_path(artifacts).read_text(encoding="utf-8")


def test_status_fail_when_exit_nonzero_without_parsed_errors(tmp_path, monkeypatch):
    mod = load_verify_shard()
    workspace, artifacts = prepare_run(tmp_path)
    patch_docker_ready(monkeypatch, mod)
    monkeypatch.setattr(
        mod, "run_shard_in_docker", lambda cmd, bd, t: (1, "javac: invalid flag", "")
    )

    rc = mod.main(build_argv(artifacts, DEFAULT_RULE_ID, DEFAULT_SHARD_ID, workspace=workspace))

    assert rc == 2
    payload = json.loads(artifact_path(artifacts).read_text(encoding="utf-8"))
    assert payload["status"] == "FAIL"
    assert payload["error_count"] == 0


def test_timeout_maps_to_exit_code_minus_one_and_fail(tmp_path, monkeypatch):
    mod = load_verify_shard()
    workspace, artifacts = prepare_run(tmp_path)
    patch_docker_ready(monkeypatch, mod)
    monkeypatch.setattr(
        mod,
        "run_shard_in_docker",
        lambda cmd, bd, t: (-1, "", "\nContainer timed out after 615s"),
    )

    rc = mod.main(build_argv(artifacts, DEFAULT_RULE_ID, DEFAULT_SHARD_ID, workspace=workspace))

    assert rc == 2
    payload = json.loads(artifact_path(artifacts).read_text(encoding="utf-8"))
    assert payload["exit_code"] == -1
    assert payload["status"] == "FAIL"
    assert "timed out" in log_path(artifacts).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Shard plan / structural validation -- exit 2, no artifact, no Docker
# ---------------------------------------------------------------------------
def test_shard_not_found_in_plan_exit_2(tmp_path, capsys):
    mod = load_verify_shard()
    workspace, artifacts = prepare_run(tmp_path)

    rc = mod.main(build_argv(artifacts, DEFAULT_RULE_ID, "NOPE-shard", workspace=workspace))

    assert rc == 2
    assert "ERROR [SHARD_NOT_FOUND]" in capsys.readouterr().err
    assert not artifact_path(artifacts, "NOPE-shard").exists()


def test_missing_editable_file_on_disk_exit_2(tmp_path, monkeypatch, capsys):
    mod = load_verify_shard()
    workspace, artifacts = prepare_run(tmp_path)
    (workspace / DEFAULT_EDITABLE_FILE).unlink()
    docker_probed = {"called": False}

    def fake_which(name):
        docker_probed["called"] = True
        return "/usr/bin/docker"

    monkeypatch.setattr(mod.shutil, "which", fake_which)

    rc = mod.main(build_argv(artifacts, DEFAULT_RULE_ID, DEFAULT_SHARD_ID, workspace=workspace))

    assert rc == 2
    assert "ERROR [SHARD_FILE_MISSING]" in capsys.readouterr().err
    assert not artifact_path(artifacts).exists()
    assert docker_probed["called"] is False


def test_missing_read_only_file_is_only_a_warning(tmp_path, monkeypatch):
    mod = load_verify_shard()
    workspace, artifacts = prepare_run(
        tmp_path, read_only_context=["src/jade/src/jade/core/Ctx.java"]
    )
    (workspace / "src/jade/src/jade/core/Ctx.java").unlink()
    patch_docker_ready(monkeypatch, mod)
    monkeypatch.setattr(mod, "run_shard_in_docker", lambda cmd, bd, t: (0, "", ""))

    rc = mod.main(build_argv(artifacts, DEFAULT_RULE_ID, DEFAULT_SHARD_ID, workspace=workspace))

    assert rc == 1
    payload = json.loads(artifact_path(artifacts).read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    kinds = {w["kind"] for w in payload["warnings"]}
    assert "read_only_file_missing_on_disk" in kinds


def test_shard_id_with_path_separator_rejected_exit_2(tmp_path, capsys):
    mod = load_verify_shard()
    workspace, artifacts = prepare_run(tmp_path)
    before = sorted(p.name for p in tmp_path.iterdir())

    rc = mod.main(build_argv(artifacts, DEFAULT_RULE_ID, "../evil", workspace=workspace))

    assert rc == 2
    assert "ERROR [INVALID_ID]" in capsys.readouterr().err
    after = sorted(p.name for p in tmp_path.iterdir())
    assert after == before


# ---------------------------------------------------------------------------
# Build directory hygiene
# ---------------------------------------------------------------------------
def test_build_dir_is_removed_after_run(tmp_path, monkeypatch):
    mod = load_verify_shard()

    def assert_no_leftovers(artifacts):
        leftovers = [p for p in artifacts.iterdir() if p.name.startswith(".shard-verify-")]
        assert leftovers == []

    ws_pass, art_pass = prepare_run(tmp_path / "case-pass")
    patch_docker_ready(monkeypatch, mod)
    monkeypatch.setattr(mod, "run_shard_in_docker", lambda cmd, bd, t: (0, "", ""))
    rc = mod.main(build_argv(art_pass, DEFAULT_RULE_ID, DEFAULT_SHARD_ID, workspace=ws_pass))
    assert rc in (0, 1)  # PASS, possibly with advisory warnings
    assert_no_leftovers(art_pass)

    ws_fail, art_fail = prepare_run(tmp_path / "case-fail")
    monkeypatch.setattr(
        mod,
        "run_shard_in_docker",
        lambda cmd, bd, t: (1, f"/ws/{DEFAULT_EDITABLE_FILE}:1: error: boom\n", ""),
    )
    rc = mod.main(build_argv(art_fail, DEFAULT_RULE_ID, DEFAULT_SHARD_ID, workspace=ws_fail))
    assert rc == 2
    assert_no_leftovers(art_fail)

    ws_env, art_env = prepare_run(tmp_path / "case-env")
    monkeypatch.setattr(mod.shutil, "which", lambda name: None)
    rc = mod.main(build_argv(art_env, DEFAULT_RULE_ID, DEFAULT_SHARD_ID, workspace=ws_env))
    assert rc == 3
    assert_no_leftovers(art_env)


# ---------------------------------------------------------------------------
# Baseline jar commit lookup
# ---------------------------------------------------------------------------
def test_baseline_jar_commit_read_from_commit_log(tmp_path, monkeypatch):
    mod = load_verify_shard()
    patch_docker_ready(monkeypatch, mod)
    monkeypatch.setattr(mod, "run_shard_in_docker", lambda cmd, bd, t: (0, "", ""))

    ws_match, art_match = prepare_run(
        tmp_path / "match",
        commit_log={
            "rule_id": DEFAULT_RULE_ID,
            "commit_hash": "abc123",
            "message": "m",
            "timestamp": "2026-01-01T00:00:00Z",
            "files": [],
        },
    )
    rc = mod.main(build_argv(art_match, DEFAULT_RULE_ID, DEFAULT_SHARD_ID, workspace=ws_match))
    assert rc in (0, 1)  # PASS; empty read_only_context still warns independently
    payload = json.loads(artifact_path(art_match).read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert payload["baseline_jar_commit"] == "abc123"
    assert "baseline_jar_commit_unknown" not in {w["kind"] for w in payload["warnings"]}

    ws_mismatch, art_mismatch = prepare_run(
        tmp_path / "mismatch",
        commit_log={
            "rule_id": "OTHER_RULE",
            "commit_hash": "zzz999",
            "message": "m",
            "timestamp": "2026-01-01T00:00:00Z",
            "files": [],
        },
    )
    rc = mod.main(
        build_argv(art_mismatch, DEFAULT_RULE_ID, DEFAULT_SHARD_ID, workspace=ws_mismatch)
    )
    assert rc == 1
    payload2 = json.loads(artifact_path(art_mismatch).read_text(encoding="utf-8"))
    assert payload2["baseline_jar_commit"] is None
    kinds = {w["kind"] for w in payload2["warnings"]}
    assert "baseline_jar_commit_unknown" in kinds


# ---------------------------------------------------------------------------
# Real-data cross-check (best effort; skips when the graph or a shard
# planner artifact are not present in this checkout)
# ---------------------------------------------------------------------------
def test_real_shard_plan_is_accepted_without_docker(tmp_path, monkeypatch, capsys):
    graph_artifacts_dir = ROOT / "migration-runs/jade-1.7-to-1.8/artifacts"
    graph_path = graph_artifacts_dir / "03.5-knowledge-graph.json"
    if not graph_path.exists():
        pytest.skip(f"{graph_path} not found")

    plan_shards_script = (
        ROOT / ".claude/skills/jade-core-knowledge-graph/scripts/plan_shards.py"
    )
    real_flags_path = ROOT / "migration-runs/jade-1.5-to-1.6/artifacts/04-flag-index.json"
    real_manifest_path = (
        ROOT / "migration-runs/jade-1.5-to-1.6/artifacts/01-breaking-changes-manifest.json"
    )
    real_workspace = ROOT / "migration-runs/jade-1.5-to-1.6/workspace"
    if not (
        plan_shards_script.is_file()
        and real_flags_path.is_file()
        and real_manifest_path.is_file()
        and real_workspace.is_dir()
    ):
        pytest.skip(
            "plan_shards.py or its real inputs are not present in this checkout; "
            "shard-plan generation is not available, so the real-shard-plan "
            "cross-check cannot run"
        )

    rule_id = "STRICTER_CAST_CHECKING"
    manifest = json.loads(real_manifest_path.read_text(encoding="utf-8"))
    if not any(
        isinstance(r, dict) and r.get("id") == rule_id for r in manifest.get("rules", [])
    ):
        pytest.skip(f"{rule_id} not present in the real manifest")

    # The committed manifest predates blast_class classification for this
    # rule; annotate a scratch copy so the real plan_shards.py can shard it,
    # without touching the committed artifact (constraint: never edit
    # existing pipeline outputs in place).
    manifest["rules"] = [
        {**r, "blast_class": "body-local"} if r.get("id") == rule_id else r
        for r in manifest["rules"]
    ]

    plan_inputs = tmp_path / "plan-inputs"
    plan_inputs.mkdir()
    write_json(plan_inputs / "01-breaking-changes-manifest.json", manifest)
    shutil.copy(real_flags_path, plan_inputs / "04-flag-index.json")

    plan_output = tmp_path / f"05-rule-shards-{rule_id}.json"
    result = subprocess.run(
        [
            sys.executable, str(plan_shards_script),
            "--artifacts-dir", str(plan_inputs),
            "--rule-id", rule_id,
            "--graph-artifacts-dir", str(graph_artifacts_dir),
            "--output", str(plan_output),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1) or not plan_output.exists():
        pytest.skip(
            "plan_shards.py could not produce a real shard plan in this "
            f"checkout (exit {result.returncode}): {result.stderr[-500:]}"
        )

    plan = json.loads(plan_output.read_text(encoding="utf-8"))
    shards = plan.get("shards", [])
    if not shards:
        pytest.skip("plan_shards.py produced zero shards for the real rule/graph pairing")

    largest = max(shards, key=lambda s: len(s.get("editable_files", [])))

    verify_artifacts = tmp_path / "verify-artifacts"
    verify_artifacts.mkdir()
    write_json(verify_artifacts / f"05-rule-shards-{rule_id}.json", plan)
    write_json(
        verify_artifacts / "00-run-config.json",
        {"run_id": "real-check", "workspace_path": "unused", "target_version": "1.6"},
    )

    mod = load_verify_shard()
    monkeypatch.setattr(mod.shutil, "which", lambda name: None)
    rc = mod.main(
        build_argv(
            verify_artifacts,
            rule_id,
            largest["shard_id"],
            workspace=real_workspace,
        )
    )

    err = capsys.readouterr().err
    # No jade.jar has been built for this run yet, so the real, current
    # outcome is BASELINE_JAR_NOT_FOUND; if a future run vendors one, the
    # docker-missing gate below it is the next honest stopping point. Either
    # way, reaching either error (not a shard/workspace structural error) is
    # proof the real shard -- with its real editable_files -- loaded and
    # resolved against the real workspace correctly.
    assert rc == 3
    assert not any(
        code in err
        for code in (
            "SHARD_PLAN_MALFORMED",
            "SHARD_NOT_FOUND",
            "SHARD_MALFORMED",
            "SHARD_FILE_MISSING",
            "RUN_CONFIG_MALFORMED",
            "WORKSPACE_NOT_FOUND",
        )
    )
    assert ("ERROR [BASELINE_JAR_NOT_FOUND]" in err) or ("ERROR [DOCKER_NOT_FOUND]" in err)


def test_lib_jar_symlinked_outside_workspace_is_skipped_not_fatal(tmp_path):
    """A jar symlinked out of the workspace must not raise ValueError.

    Only the workspace is bind-mounted into the container, so such a jar is
    unreachable there. It is dropped from the classpath and recorded as a
    warning instead of crashing the whole shard verification.
    """
    mod = load_verify_shard()

    outside = tmp_path / "outside"
    outside.mkdir()
    stray = outside / "stray.jar"
    stray.write_bytes(b"")

    workspace = tmp_path / "workspace"
    lib_dir = workspace / str(mod.DEFAULT_LIB_RELPATH)
    lib_dir.mkdir(parents=True)
    (lib_dir / "real.jar").write_bytes(b"")
    (lib_dir / "linked.jar").symlink_to(stray)

    warnings = []
    entries = mod._collect_workspace_lib_jars(workspace, warnings)

    assert entries == [f"{mod.CONTAINER_WS}/{mod.DEFAULT_LIB_RELPATH}/real.jar"]
    assert [w["kind"] for w in warnings] == ["lib_jar_outside_workspace"]
    assert warnings[0]["file"].endswith("linked.jar")


def test_collect_workspace_lib_jars_warnings_argument_is_optional(tmp_path):
    """Callers that do not care about skips may omit the warnings list."""
    mod = load_verify_shard()

    outside = tmp_path / "outside"
    outside.mkdir()
    stray = outside / "stray.jar"
    stray.write_bytes(b"")

    workspace = tmp_path / "workspace"
    lib_dir = workspace / str(mod.DEFAULT_LIB_RELPATH)
    lib_dir.mkdir(parents=True)
    (lib_dir / "linked.jar").symlink_to(stray)

    assert mod._collect_workspace_lib_jars(workspace) == []
