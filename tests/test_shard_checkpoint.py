"""Tests for jade-core-orchestrator scripts/shard_checkpoint.py.

Mechanism under test: a per-shard git-blob checkpoint/rollback/accept
ledger used by agent-mode RULE_BATCH_LOOP recipes. Every test creates its
own throwaway git repository under tmp_path (via ``git init``) — the
script must never touch the surrounding PolishedJADEite repository, and
must never create a commit, move HEAD, or use git stash in the repo it
does operate on.
"""

import importlib.util
import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / ".claude/skills/jade-core-orchestrator/scripts/shard_checkpoint.py"


def load_shard_checkpoint():
    spec = importlib.util.spec_from_file_location("shard_checkpoint_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _git(args, cwd):
    return subprocess.run(
        ["git", "-C", str(cwd)] + list(args), capture_output=True, text=True
    )


def init_repo_with_commit(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(["init", "-q"], cwd=path)
    _git(["config", "user.email", "test@example.com"], cwd=path)
    _git(["config", "user.name", "Test"], cwd=path)
    (path / "README.md").write_text("init\n", encoding="utf-8")
    _git(["add", "README.md"], cwd=path)
    _git(["commit", "-q", "-m", "init"], cwd=path)


def _shard(shard_id, editable_files, rule_id="R"):
    return {
        "shard_id": shard_id,
        "rule_id": rule_id,
        "class": "body-local",
        "editable_files": editable_files,
        "read_only_context": [],
        "entry_points": [],
        "invariants": ["EDITS_CONFINED_TO_EDITABLE_FILES"],
        "graph_artifact": "03.5-knowledge-graph.json",
        "parallel_safe": True,
    }


def _write_shard_plan(artifacts: Path, rule_id: str, shards, run_id: str = "test-run") -> None:
    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "rule_id": rule_id,
        "status": "OK",
        "blast_class": "body-local",
        "shard_count": len(shards),
        "shards": shards,
        "total_flags": 0,
        "total_flagged_files": 0,
        "warnings": [],
    }
    (artifacts / f"05-rule-shards-{rule_id}.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _ledger(artifacts: Path, rule_id: str):
    return json.loads((artifacts / f"06-shard-checkpoints-{rule_id}.json").read_text())


def test_create_records_blob_for_existing_file(tmp_path):
    repo = tmp_path / "repo"
    init_repo_with_commit(repo)
    workspace = repo / "workspace"
    workspace.mkdir()
    (workspace / "Foo.java").write_text("class Foo {}\n", encoding="utf-8")

    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _write_shard_plan(artifacts, "R", [_shard("R-001", ["Foo.java"])])

    module = load_shard_checkpoint()
    rc = module.main(
        [
            "--artifacts-dir", str(artifacts),
            "--rule-id", "R",
            "--shard-id", "R-001",
            "--workspace", str(workspace),
            "--create",
        ]
    )
    assert rc == 0

    ledger = _ledger(artifacts, "R")
    entry = ledger["shards"]["R-001"]
    assert entry["state"] == "CHECKPOINTED"
    assert entry["rollback_reason"] is None
    files = entry["files"]
    assert len(files) == 1
    assert files[0]["file"] == "Foo.java"
    assert files[0]["existed"] is True
    assert isinstance(files[0]["blob"], str) and len(files[0]["blob"]) == 40
    assert isinstance(files[0]["mode"], int)

    cat = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "blob", files[0]["blob"]],
        capture_output=True,
    )
    assert cat.stdout == b"class Foo {}\n"


def test_create_records_existed_false_for_missing_file(tmp_path):
    repo = tmp_path / "repo"
    init_repo_with_commit(repo)
    workspace = repo / "workspace"
    workspace.mkdir()

    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _write_shard_plan(artifacts, "R", [_shard("R-001", ["New.java"])])

    module = load_shard_checkpoint()
    rc = module.main(
        [
            "--artifacts-dir", str(artifacts),
            "--rule-id", "R",
            "--shard-id", "R-001",
            "--workspace", str(workspace),
            "--create",
        ]
    )
    assert rc == 0

    entry = _ledger(artifacts, "R")["shards"]["R-001"]
    files = entry["files"]
    assert len(files) == 1
    assert files[0]["file"] == "New.java"
    assert files[0]["existed"] is False
    assert files[0]["blob"] is None
    assert files[0]["mode"] is None


def test_rollback_restores_exact_bytes_and_mode(tmp_path):
    repo = tmp_path / "repo"
    init_repo_with_commit(repo)
    workspace = repo / "workspace"
    workspace.mkdir()
    target = workspace / "Foo.java"
    target.write_text("original content\n", encoding="utf-8")
    target.chmod(0o644)

    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _write_shard_plan(artifacts, "R", [_shard("R-001", ["Foo.java"])])

    module = load_shard_checkpoint()
    common = [
        "--artifacts-dir", str(artifacts),
        "--rule-id", "R",
        "--shard-id", "R-001",
        "--workspace", str(workspace),
    ]
    assert module.main(common + ["--create"]) == 0

    target.write_text("mutated content\n", encoding="utf-8")
    target.chmod(0o600)

    rc = module.main(common + ["--rollback", "--reason", "bad fix"])
    assert rc == 0
    assert target.read_text(encoding="utf-8") == "original content\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o644

    entry = _ledger(artifacts, "R")["shards"]["R-001"]
    assert entry["state"] == "ROLLED_BACK"
    assert entry["rollback_reason"] == "bad fix"


def test_rollback_deletes_file_created_by_shard(tmp_path):
    repo = tmp_path / "repo"
    init_repo_with_commit(repo)
    workspace = repo / "workspace"
    workspace.mkdir()

    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _write_shard_plan(artifacts, "R", [_shard("R-001", ["New.java"])])

    module = load_shard_checkpoint()
    common = [
        "--artifacts-dir", str(artifacts),
        "--rule-id", "R",
        "--shard-id", "R-001",
        "--workspace", str(workspace),
    ]
    assert module.main(common + ["--create"]) == 0

    new_file = workspace / "New.java"
    new_file.write_text("class New {}\n", encoding="utf-8")
    assert new_file.exists()

    rc = module.main(common + ["--rollback", "--reason", "undo"])
    assert rc == 0
    assert not new_file.exists()


def test_rollback_of_one_shard_preserves_sibling_shard_edits(tmp_path):
    repo = tmp_path / "repo"
    init_repo_with_commit(repo)
    workspace = repo / "workspace"
    workspace.mkdir()
    file_a = workspace / "A.java"
    file_a.write_text("A original\n", encoding="utf-8")
    file_b = workspace / "B.java"
    file_b.write_text("B original\n", encoding="utf-8")

    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _write_shard_plan(
        artifacts,
        "R",
        [_shard("R-001", ["A.java"]), _shard("R-002", ["B.java"])],
    )

    module = load_shard_checkpoint()
    common = [
        "--artifacts-dir", str(artifacts),
        "--rule-id", "R",
        "--workspace", str(workspace),
    ]
    assert module.main(common + ["--shard-id", "R-001", "--create"]) == 0
    assert module.main(common + ["--shard-id", "R-002", "--create"]) == 0

    file_a.write_text("A modified by shard1\n", encoding="utf-8")
    file_b.write_text("B modified by shard2\n", encoding="utf-8")

    rc = module.main(
        common + ["--shard-id", "R-001", "--rollback", "--reason", "shard1 bad"]
    )
    assert rc == 0
    assert file_a.read_text(encoding="utf-8") == "A original\n"
    # Sibling shard's edit is completely untouched by shard1's rollback.
    assert file_b.read_text(encoding="utf-8") == "B modified by shard2\n"

    ledger = _ledger(artifacts, "R")
    assert ledger["shards"]["R-001"]["state"] == "ROLLED_BACK"
    assert ledger["shards"]["R-002"]["state"] == "CHECKPOINTED"


def test_create_refuses_file_already_checkpointed_by_another_shard(tmp_path):
    repo = tmp_path / "repo"
    init_repo_with_commit(repo)
    workspace = repo / "workspace"
    workspace.mkdir()
    (workspace / "A.java").write_text("x\n", encoding="utf-8")

    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    # Two shards claiming the same file is a plan_shards.py bug in
    # practice (shards should be graph-disjoint), but shard_checkpoint.py
    # is the second line of defense and must refuse it regardless.
    _write_shard_plan(
        artifacts,
        "R",
        [_shard("R-001", ["A.java"]), _shard("R-002", ["A.java"])],
    )

    module = load_shard_checkpoint()
    common = [
        "--artifacts-dir", str(artifacts),
        "--rule-id", "R",
        "--workspace", str(workspace),
    ]
    assert module.main(common + ["--shard-id", "R-001", "--create"]) == 0
    before = (artifacts / "06-shard-checkpoints-R.json").read_bytes()

    rc = module.main(common + ["--shard-id", "R-002", "--create"])
    assert rc == 2

    after = (artifacts / "06-shard-checkpoints-R.json").read_bytes()
    assert after == before


def test_create_refuses_path_outside_workspace(tmp_path):
    repo = tmp_path / "repo"
    init_repo_with_commit(repo)
    workspace = repo / "workspace"
    workspace.mkdir()

    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _write_shard_plan(artifacts, "R", [_shard("R-001", ["../outside.java"])])

    module = load_shard_checkpoint()
    rc = module.main(
        [
            "--artifacts-dir", str(artifacts),
            "--rule-id", "R",
            "--shard-id", "R-001",
            "--workspace", str(workspace),
            "--create",
        ]
    )
    assert rc == 2
    assert not (artifacts / "06-shard-checkpoints-R.json").exists()


def test_accept_requires_checkpointed_state(tmp_path):
    repo = tmp_path / "repo"
    init_repo_with_commit(repo)
    workspace = repo / "workspace"
    workspace.mkdir()
    (workspace / "A.java").write_text("A\n", encoding="utf-8")

    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _write_shard_plan(artifacts, "R", [_shard("R-001", ["A.java"])])

    module = load_shard_checkpoint()
    common = [
        "--artifacts-dir", str(artifacts),
        "--rule-id", "R",
        "--shard-id", "R-001",
        "--workspace", str(workspace),
    ]
    assert module.main(common + ["--create"]) == 0
    assert module.main(common + ["--rollback", "--reason", "already handled"]) == 0
    before = (artifacts / "06-shard-checkpoints-R.json").read_bytes()

    # Shard is now ROLLED_BACK, not CHECKPOINTED — accept must refuse it.
    rc = module.main(common + ["--accept"])
    assert rc == 2

    after = (artifacts / "06-shard-checkpoints-R.json").read_bytes()
    assert after == before


def test_ledger_write_is_atomic(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    init_repo_with_commit(repo)
    workspace = repo / "workspace"
    workspace.mkdir()
    (workspace / "A.java").write_text("A\n", encoding="utf-8")
    (workspace / "B.java").write_text("B\n", encoding="utf-8")

    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _write_shard_plan(
        artifacts,
        "R",
        [_shard("R-001", ["A.java"]), _shard("R-002", ["B.java"])],
    )

    module = load_shard_checkpoint()
    common = [
        "--artifacts-dir", str(artifacts),
        "--rule-id", "R",
        "--workspace", str(workspace),
    ]
    assert module.main(common + ["--shard-id", "R-001", "--create"]) == 0
    ledger_path = artifacts / "06-shard-checkpoints-R.json"
    before = ledger_path.read_bytes()

    def _boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(module.os, "replace", _boom)
    with pytest.raises(OSError):
        module.main(common + ["--shard-id", "R-002", "--create"])

    after = ledger_path.read_bytes()
    assert after == before
    leftovers = [p for p in artifacts.iterdir() if p.name.startswith(".shard-checkpoint-")]
    assert leftovers == []


def test_no_commit_and_no_head_movement(tmp_path):
    repo = tmp_path / "repo"
    init_repo_with_commit(repo)
    workspace = repo / "workspace"
    workspace.mkdir()
    (workspace / "Foo.java").write_text("class Foo {}\n", encoding="utf-8")

    # Artifacts deliberately live OUTSIDE the repo so the ledger write
    # itself can never appear in `git status` for the repo under test —
    # isolating the assertion to exactly the invariant under test: no
    # commit, no HEAD movement, no stash, from --create's git plumbing.
    artifacts = tmp_path / "artifacts_outside_repo"
    artifacts.mkdir()
    _write_shard_plan(artifacts, "R", [_shard("R-001", ["Foo.java"])])

    head_before = _git(["rev-parse", "HEAD"], cwd=repo).stdout
    status_before = _git(["status", "--porcelain"], cwd=repo).stdout
    stash_before = _git(["stash", "list"], cwd=repo).stdout

    module = load_shard_checkpoint()
    rc = module.main(
        [
            "--artifacts-dir", str(artifacts),
            "--rule-id", "R",
            "--shard-id", "R-001",
            "--workspace", str(workspace),
            "--create",
        ]
    )
    assert rc == 0

    head_after = _git(["rev-parse", "HEAD"], cwd=repo).stdout
    status_after = _git(["status", "--porcelain"], cwd=repo).stdout
    stash_after = _git(["stash", "list"], cwd=repo).stdout

    assert head_before == head_after
    assert status_before == status_after
    assert stash_before == "" and stash_after == ""


def test_status_lists_shards_sorted(tmp_path, capsys):
    repo = tmp_path / "repo"
    init_repo_with_commit(repo)
    workspace = repo / "workspace"
    workspace.mkdir()
    (workspace / "A.java").write_text("A\n", encoding="utf-8")
    (workspace / "B.java").write_text("B\n", encoding="utf-8")

    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _write_shard_plan(
        artifacts,
        "R",
        [_shard("R-002", ["B.java"]), _shard("R-001", ["A.java"])],
    )

    module = load_shard_checkpoint()
    common = [
        "--artifacts-dir", str(artifacts),
        "--rule-id", "R",
        "--workspace", str(workspace),
    ]
    assert module.main(common + ["--shard-id", "R-002", "--create"]) == 0
    assert module.main(common + ["--shard-id", "R-001", "--create"]) == 0

    capsys.readouterr()
    rc = module.main(["--artifacts-dir", str(artifacts), "--rule-id", "R", "--workspace", str(workspace), "--status"])
    assert rc == 0
    out = capsys.readouterr().out.splitlines()
    assert out == ["R-001 CHECKPOINTED", "R-002 CHECKPOINTED"]


def test_shard_id_required_for_create_rollback_accept(tmp_path):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    module = load_shard_checkpoint()
    with pytest.raises(SystemExit) as exc:
        module.main(
            [
                "--artifacts-dir", str(artifacts),
                "--rule-id", "R",
                "--workspace", str(workspace),
                "--create",
            ]
        )
    assert exc.value.code == 2


def test_reason_required_for_rollback(tmp_path):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    module = load_shard_checkpoint()
    with pytest.raises(SystemExit) as exc:
        module.main(
            [
                "--artifacts-dir", str(artifacts),
                "--rule-id", "R",
                "--shard-id", "R-001",
                "--workspace", str(workspace),
                "--rollback",
            ]
        )
    assert exc.value.code == 2
