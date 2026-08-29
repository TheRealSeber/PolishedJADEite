"""Tests for jade-core-knowledge-graph scripts/plan_shards.py."""

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / ".claude/skills/jade-core-knowledge-graph/scripts/plan_shards.py"

RULE_ID = "STRICTER_CAST_CHECKING"
REAL_MANIFEST = ROOT / "migration-runs/jade-1.5-to-1.6/artifacts/01-breaking-changes-manifest.json"
REAL_FLAGS = ROOT / "migration-runs/jade-1.5-to-1.6/artifacts/04-flag-index.json"
REAL_GRAPH_DIR = ROOT / "migration-runs/jade-1.7-to-1.8/artifacts"
REAL_GRAPH = REAL_GRAPH_DIR / "03.5-knowledge-graph.json"


def load_plan_shards():
    spec = importlib.util.spec_from_file_location("plan_shards_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _require_real_data():
    if not (REAL_MANIFEST.is_file() and REAL_FLAGS.is_file() and REAL_GRAPH.is_file()):
        pytest.skip("real migration-run artifacts not present")


def node(path, package="test.pkg", **kwargs):
    data = {
        "path": path,
        "package": package,
        "class_name": path.rsplit("/", 1)[-1].replace(".java", ""),
        "kind": "class",
    }
    data.update(kwargs)
    return data


def edge(frm, to, **kwargs):
    data = {"from": frm, "to": to}
    data.update(kwargs)
    return data


def rule(rule_id, blast_class=None, **kwargs):
    data = {"id": rule_id, "name": rule_id}
    if blast_class is not None:
        data["blast_class"] = blast_class
    data.update(kwargs)
    return data


def flag(rule_id, file, line=1, confidence=0.8, reason="test"):
    return {
        "rule_id": rule_id,
        "file": file,
        "line": line,
        "confidence": confidence,
        "reason": reason,
    }


def _write_artifacts(directory, rules, flags, nodes, edges=None, run_id="test-run"):
    manifest_data = {"run_id": run_id, "rules": rules}
    flags_data = {"run_id": run_id, "total_flags": len(flags), "flags": flags}
    graph_data = {
        "schema_version": 2,
        "content_hash": "deadbeef",
        "nodes": nodes,
        "edges": {
            etype: (edges or {}).get(etype, [])
            for etype in ("imports", "extends", "implements", "calls", "type_refs")
        },
    }
    (directory / "01-breaking-changes-manifest.json").write_text(
        json.dumps(manifest_data), encoding="utf-8"
    )
    (directory / "04-flag-index.json").write_text(
        json.dumps(flags_data), encoding="utf-8"
    )
    (directory / "03.5-knowledge-graph.json").write_text(
        json.dumps(graph_data), encoding="utf-8"
    )
    return directory


def _load_real_manifest_with_blast_class(blast_class):
    data = json.loads(REAL_MANIFEST.read_text(encoding="utf-8"))
    found = False
    for r in data["rules"]:
        if r.get("id") == RULE_ID:
            r["blast_class"] = blast_class
            found = True
    assert found, f"{RULE_ID} not found in real manifest"
    return data


def _write_real_artifacts(directory, blast_class):
    manifest_data = _load_real_manifest_with_blast_class(blast_class)
    (directory / "01-breaking-changes-manifest.json").write_text(
        json.dumps(manifest_data), encoding="utf-8"
    )
    shutil.copyfile(REAL_FLAGS, directory / "04-flag-index.json")


# ---------------------------------------------------------------------------
# Reference measurement (jade.util.leap coupling)
# ---------------------------------------------------------------------------


def test_reference_leap_coupling_matches_1655_flags():
    _require_real_data()
    mod = load_plan_shards()
    graph = json.loads(REAL_GRAPH.read_text(encoding="utf-8"))
    flags = json.loads(REAL_FLAGS.read_text(encoding="utf-8"))["flags"]

    forward, _reverse = mod.build_edge_index(graph)
    leap = {
        p for p, n in graph["nodes"].items() if n.get("package") == "jade.util.leap"
    }
    assert len(leap) == 17

    # Codebase-wide: every file (of all 1015 nodes) with an edge into leap.
    users = {f for f in forward if forward[f] & leap} - leap

    # Restricted to the 336 STRICTER_CAST-flagged files: this is the "169
    # files" figure quoted in the reference measurement notes.
    flagged_files = {fl["file"] for fl in flags}
    users_among_flagged = users & flagged_files
    assert len(users_among_flagged) == 169

    matched = [fl for fl in flags if fl["file"] in users]
    assert len(matched) == 1655
    assert len(flags) == 2548
    assert round(100 * 1655 / 2548, 2) == 64.95


def test_reference_measurement_breaks_without_implements_bucket():
    _require_real_data()
    mod = load_plan_shards()
    assert mod.EDGE_TYPES == ("imports", "extends", "implements", "calls", "type_refs")

    graph = json.loads(REAL_GRAPH.read_text(encoding="utf-8"))
    flags = json.loads(REAL_FLAGS.read_text(encoding="utf-8"))["flags"]
    leap = {
        p for p, n in graph["nodes"].items() if n.get("package") == "jade.util.leap"
    }

    forward_without_implements = {}
    for etype in ("imports", "extends", "calls", "type_refs"):
        for e in graph["edges"].get(etype, []):
            if not isinstance(e, dict):
                continue
            a, b = e.get("from"), e.get("to")
            if isinstance(a, str) and isinstance(b, str) and a and b and a != b:
                forward_without_implements.setdefault(a, set()).add(b)

    users = {
        f for f in forward_without_implements if forward_without_implements[f] & leap
    } - leap
    matched = [fl for fl in flags if fl["file"] in users]
    assert len(matched) == 1649
    assert len(matched) != 1655


# ---------------------------------------------------------------------------
# Real-data body-local / signature shard plans
# ---------------------------------------------------------------------------


def test_body_local_real_data_yields_eleven_shards(tmp_path):
    _require_real_data()
    _write_real_artifacts(tmp_path, "body-local")
    mod = load_plan_shards()
    rc = mod.main(
        [
            "--artifacts-dir", str(tmp_path),
            "--rule-id", RULE_ID,
            "--graph-artifacts-dir", str(REAL_GRAPH_DIR),
        ]
    )
    assert rc == 0
    report = json.loads(
        (tmp_path / f"05-rule-shards-{RULE_ID}.json").read_text(encoding="utf-8")
    )
    assert report["shard_count"] == 11
    assert sorted(len(s["editable_files"]) for s in report["shards"]) == [1] * 10 + [326]


def test_body_local_first_shard_is_the_giant_component(tmp_path):
    _require_real_data()
    _write_real_artifacts(tmp_path, "body-local")
    mod = load_plan_shards()
    rc = mod.main(
        [
            "--artifacts-dir", str(tmp_path),
            "--rule-id", RULE_ID,
            "--graph-artifacts-dir", str(REAL_GRAPH_DIR),
        ]
    )
    assert rc == 0
    report = json.loads(
        (tmp_path / f"05-rule-shards-{RULE_ID}.json").read_text(encoding="utf-8")
    )
    shard0 = report["shards"][0]
    assert shard0["shard_id"] == f"{RULE_ID}-body-local-001"
    assert len(shard0["editable_files"]) == 326
    assert shard0["editable_files"][0] == "src/jade/src/FIPA/AgentIDHelper.java"
    assert len(shard0["read_only_context"]) == 253
    assert len(shard0["entry_points"]) == 2514


def test_body_local_shards_are_disjoint_and_cover_every_flagged_file(tmp_path):
    _require_real_data()
    _write_real_artifacts(tmp_path, "body-local")
    mod = load_plan_shards()
    rc = mod.main(
        [
            "--artifacts-dir", str(tmp_path),
            "--rule-id", RULE_ID,
            "--graph-artifacts-dir", str(REAL_GRAPH_DIR),
        ]
    )
    assert rc == 0
    report = json.loads(
        (tmp_path / f"05-rule-shards-{RULE_ID}.json").read_text(encoding="utf-8")
    )
    seen = set()
    total = 0
    for s in report["shards"]:
        s_set = set(s["editable_files"])
        assert not (seen & s_set)
        seen |= s_set
        total += len(s["editable_files"])
    assert total == 336
    flags = json.loads(REAL_FLAGS.read_text(encoding="utf-8"))["flags"]
    flagged_files = {f["file"] for f in flags}
    assert seen == flagged_files


def test_entry_points_total_equals_flag_count(tmp_path):
    _require_real_data()
    _write_real_artifacts(tmp_path, "body-local")
    mod = load_plan_shards()
    rc = mod.main(
        [
            "--artifacts-dir", str(tmp_path),
            "--rule-id", RULE_ID,
            "--graph-artifacts-dir", str(REAL_GRAPH_DIR),
        ]
    )
    assert rc == 0
    report = json.loads(
        (tmp_path / f"05-rule-shards-{RULE_ID}.json").read_text(encoding="utf-8")
    )
    total_entry_points = 0
    for s in report["shards"]:
        eps = s["entry_points"]
        for ep in eps:
            assert set(ep.keys()) == {"file", "line"}
            assert isinstance(ep["line"], int)
        assert eps == sorted(eps, key=lambda ep: (ep["file"], ep["line"]))
        total_entry_points += len(eps)
    assert total_entry_points == 2548


def test_signature_real_data_yields_single_shard_593_editable(tmp_path):
    _require_real_data()
    _write_real_artifacts(tmp_path, "signature")
    mod = load_plan_shards()
    rc = mod.main(
        [
            "--artifacts-dir", str(tmp_path),
            "--rule-id", RULE_ID,
            "--graph-artifacts-dir", str(REAL_GRAPH_DIR),
        ]
    )
    assert rc == 0
    report = json.loads(
        (tmp_path / f"05-rule-shards-{RULE_ID}.json").read_text(encoding="utf-8")
    )
    assert report["shard_count"] == 1
    shard = report["shards"][0]
    assert shard["shard_id"] == f"{RULE_ID}-signature-001"
    assert len(shard["editable_files"]) == 593
    assert len(shard["read_only_context"]) == 129
    assert shard["parallel_safe"] is False
    assert len(shard["entry_points"]) == 2548


def test_shipped_manifest_classifies_every_rule(tmp_path):
    """The shipped 1.5-to-1.6 manifest must carry a valid blast_class per rule."""
    _require_real_data()
    mod = load_plan_shards()
    data = json.loads(REAL_MANIFEST.read_text(encoding="utf-8"))
    for r in data["rules"]:
        assert r.get("blast_class") in mod.BLAST_CLASSES, r.get("id")
    by_id = {r["id"]: r["blast_class"] for r in data["rules"]}
    assert by_id[RULE_ID] == "signature"
    assert by_id["BUILD_XML_SOURCE_TARGET_UPGRADE"] == "body-local"


def test_missing_blast_class_yields_unclassified_exit_1(tmp_path):
    _require_real_data()
    mod = load_plan_shards()
    manifest_data = json.loads(REAL_MANIFEST.read_text(encoding="utf-8"))
    for r in manifest_data["rules"]:
        r.pop("blast_class", None)
    (tmp_path / "01-breaking-changes-manifest.json").write_text(
        json.dumps(manifest_data), encoding="utf-8"
    )
    shutil.copyfile(REAL_FLAGS, tmp_path / "04-flag-index.json")
    output = tmp_path / "out.json"
    rc = mod.main(
        [
            "--artifacts-dir", str(tmp_path),
            "--rule-id", RULE_ID,
            "--graph-artifacts-dir", str(REAL_GRAPH_DIR),
            "--output", str(output),
        ]
    )
    assert rc == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "UNCLASSIFIED"
    assert report["blast_class"] is None
    assert report["shards"] == []
    assert report["shard_count"] == 0
    assert report["total_flags"] == 2548
    assert any(w["kind"] == "missing_blast_class" for w in report["warnings"])
    assert output.is_file()


# ---------------------------------------------------------------------------
# Synthetic-graph structural tests
# ---------------------------------------------------------------------------


def test_invalid_blast_class_value_exit_2_no_artifact(tmp_path, capsys):
    mod = load_plan_shards()
    _write_artifacts(
        tmp_path,
        rules=[rule("R1", blast_class="module-wide")],
        flags=[flag("R1", "A.java", 1)],
        nodes={"A.java": node("A.java")},
    )
    rc = mod.main(["--artifacts-dir", str(tmp_path), "--rule-id", "R1"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "ERROR [INVALID_BLAST_CLASS]" in err
    assert not (tmp_path / "05-rule-shards-R1.json").exists()


def test_read_only_context_never_overlaps_editable_files(tmp_path):
    mod = load_plan_shards()
    nodes = {f"{c}.java": node(f"{c}.java") for c in "ABCD"}
    edges = {
        "imports": [
            edge("A.java", "B.java"),
            edge("B.java", "C.java"),
            edge("C.java", "D.java"),
        ],
    }
    for blast_class in ("body-local", "signature"):
        d = tmp_path / blast_class
        d.mkdir()
        _write_artifacts(
            d,
            rules=[rule("R1", blast_class=blast_class)],
            flags=[flag("R1", "A.java"), flag("R1", "B.java")],
            nodes=nodes,
            edges=edges,
        )
        rc = mod.main(["--artifacts-dir", str(d), "--rule-id", "R1"])
        assert rc in (0, 1)
        report = json.loads((d / "05-rule-shards-R1.json").read_text(encoding="utf-8"))
        for s in report["shards"]:
            assert set(s["editable_files"]) & set(s["read_only_context"]) == set()


def test_invariants_vocabulary_is_exact(tmp_path):
    mod = load_plan_shards()
    expectations = (
        (
            "body-local",
            [
                "EDITS_CONFINED_TO_EDITABLE_FILES",
                "PUBLIC_SIGNATURES_UNCHANGED",
                "READ_ONLY_CONTEXT_NOT_MODIFIED",
            ],
        ),
        (
            "signature",
            [
                "EDITS_CONFINED_TO_EDITABLE_FILES",
                "READ_ONLY_CONTEXT_NOT_MODIFIED",
                "SEQUENTIAL_EXECUTION_REQUIRED",
                "SIGNATURE_CHANGES_CONFINED_TO_EDITABLE_FILES",
            ],
        ),
    )
    for blast_class, expected in expectations:
        d = tmp_path / blast_class
        d.mkdir()
        _write_artifacts(
            d,
            rules=[rule("R1", blast_class=blast_class)],
            flags=[flag("R1", "A.java")],
            nodes={"A.java": node("A.java")},
        )
        rc = mod.main(["--artifacts-dir", str(d), "--rule-id", "R1"])
        assert rc == 0
        report = json.loads((d / "05-rule-shards-R1.json").read_text(encoding="utf-8"))
        assert report["shards"][0]["invariants"] == expected
        assert expected == sorted(expected)


def test_parallel_safe_matches_class(tmp_path):
    mod = load_plan_shards()
    for blast_class, expected_parallel_safe in (("body-local", True), ("signature", False)):
        d = tmp_path / blast_class
        d.mkdir()
        _write_artifacts(
            d,
            rules=[rule("R1", blast_class=blast_class)],
            flags=[flag("R1", "A.java")],
            nodes={"A.java": node("A.java")},
        )
        rc = mod.main(["--artifacts-dir", str(d), "--rule-id", "R1"])
        assert rc == 0
        report = json.loads((d / "05-rule-shards-R1.json").read_text(encoding="utf-8"))
        for s in report["shards"]:
            assert s["parallel_safe"] is expected_parallel_safe
            assert (s["class"] == "body-local") == expected_parallel_safe


def test_self_loops_do_not_merge_components(tmp_path):
    mod = load_plan_shards()
    nodes = {f"{c}.java": node(f"{c}.java") for c in "ABC"}
    edges = {
        "calls": [
            edge("A.java", "A.java"),
            edge("B.java", "B.java"),
            edge("C.java", "C.java"),
        ]
    }
    _write_artifacts(
        tmp_path,
        rules=[rule("R1", blast_class="body-local")],
        flags=[flag("R1", "A.java"), flag("R1", "B.java"), flag("R1", "C.java")],
        nodes=nodes,
        edges=edges,
    )
    rc = mod.main(["--artifacts-dir", str(tmp_path), "--rule-id", "R1"])
    assert rc == 0
    report = json.loads((tmp_path / "05-rule-shards-R1.json").read_text(encoding="utf-8"))
    assert report["shard_count"] == 3


def test_edges_between_unflagged_files_do_not_merge_body_local_shards(tmp_path):
    mod = load_plan_shards()
    nodes = {f"{c}.java": node(f"{c}.java") for c in "ABC"}
    edges = {
        "imports": [
            edge("A.java", "C.java"),
            edge("B.java", "C.java"),
        ]
    }
    _write_artifacts(
        tmp_path,
        rules=[rule("R1", blast_class="body-local")],
        flags=[flag("R1", "A.java"), flag("R1", "B.java")],
        nodes=nodes,
        edges=edges,
    )
    rc = mod.main(["--artifacts-dir", str(tmp_path), "--rule-id", "R1"])
    assert rc == 0
    report = json.loads((tmp_path / "05-rule-shards-R1.json").read_text(encoding="utf-8"))
    assert report["shard_count"] == 2
    for s in report["shards"]:
        # C is not a dependent of A or B (edges point A->C, B->C, not the
        # reverse), so it must not appear as read-only context here.
        assert s["read_only_context"] == []


def test_flagged_file_absent_from_graph_becomes_singleton_with_warning(tmp_path):
    mod = load_plan_shards()
    nodes = {"A.java": node("A.java")}
    _write_artifacts(
        tmp_path,
        rules=[rule("R1", blast_class="body-local")],
        flags=[flag("R1", "A.java"), flag("R1", "Missing.java")],
        nodes=nodes,
    )
    rc = mod.main(["--artifacts-dir", str(tmp_path), "--rule-id", "R1"])
    assert rc == 1
    report = json.loads((tmp_path / "05-rule-shards-R1.json").read_text(encoding="utf-8"))
    missing_shard = next(
        s for s in report["shards"] if s["editable_files"] == ["Missing.java"]
    )
    assert missing_shard["read_only_context"] == []
    assert any(
        w["kind"] == "flagged_file_not_in_graph" and w["file"] == "Missing.java"
        for w in report["warnings"]
    )
    assert report["flagged_files_missing_from_graph"] == ["Missing.java"]


def test_rule_with_zero_flags_exit_1_status_empty(tmp_path):
    mod = load_plan_shards()
    _write_artifacts(
        tmp_path,
        rules=[rule("R1", blast_class="body-local")],
        flags=[flag("OTHER_RULE", "A.java")],
        nodes={"A.java": node("A.java")},
    )
    rc = mod.main(["--artifacts-dir", str(tmp_path), "--rule-id", "R1"])
    assert rc == 1
    report = json.loads((tmp_path / "05-rule-shards-R1.json").read_text(encoding="utf-8"))
    assert report["status"] == "EMPTY"
    assert report["shards"] == []
    assert any(w["kind"] == "no_flags" for w in report["warnings"])


def test_cli_missing_graph_exit_3_writes_nothing(tmp_path, capsys):
    mod = load_plan_shards()
    manifest_data = {"run_id": "t", "rules": [rule("R1", blast_class="body-local")]}
    flags_data = {"run_id": "t", "total_flags": 0, "flags": []}
    (tmp_path / "01-breaking-changes-manifest.json").write_text(
        json.dumps(manifest_data), encoding="utf-8"
    )
    (tmp_path / "04-flag-index.json").write_text(
        json.dumps(flags_data), encoding="utf-8"
    )
    rc = mod.main(["--artifacts-dir", str(tmp_path), "--rule-id", "R1"])
    assert rc == 3
    err = capsys.readouterr().err
    assert "ERROR [INPUT_NOT_FOUND] graph:" in err
    assert not (tmp_path / "05-rule-shards-R1.json").exists()


def test_cli_malformed_graph_exit_2(tmp_path, capsys):
    mod = load_plan_shards()
    manifest_data = {"run_id": "t", "rules": [rule("R1", blast_class="body-local")]}
    flags_data = {"run_id": "t", "total_flags": 0, "flags": []}
    (tmp_path / "01-breaking-changes-manifest.json").write_text(
        json.dumps(manifest_data), encoding="utf-8"
    )
    (tmp_path / "04-flag-index.json").write_text(
        json.dumps(flags_data), encoding="utf-8"
    )
    (tmp_path / "03.5-knowledge-graph.json").write_text(
        json.dumps({"nodes": {}}), encoding="utf-8"
    )  # missing 'edges'
    rc = mod.main(["--artifacts-dir", str(tmp_path), "--rule-id", "R1"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "ERROR [INPUT_MALFORMED]" in err


def test_malformed_edges_do_not_crash(tmp_path):
    mod = load_plan_shards()
    nodes = {"A.java": node("A.java"), "x.java": node("x.java")}
    edges = {
        "calls": [5, None, {"from": 1, "to": "x.java"}, {"from": "a.java"}],
    }
    _write_artifacts(
        tmp_path,
        rules=[rule("R1", blast_class="body-local")],
        flags=[flag("R1", "A.java")],
        nodes=nodes,
        edges=edges,
    )
    rc = mod.main(["--artifacts-dir", str(tmp_path), "--rule-id", "R1"])
    assert rc in (0, 1)


def test_rule_id_with_path_separator_rejected_exit_2(tmp_path, capsys):
    mod = load_plan_shards()
    rc = mod.main(["--artifacts-dir", str(tmp_path), "--rule-id", "../../etc/passwd"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "ERROR [INVALID_RULE_ID]" in err
    assert list(tmp_path.rglob("*")) == []


def test_output_is_byte_deterministic_and_leaves_no_tmp_files(tmp_path):
    mod = load_plan_shards()
    nodes = {f"{c}.java": node(f"{c}.java") for c in "ABC"}
    edges = {"imports": [edge("A.java", "B.java")]}
    _write_artifacts(
        tmp_path,
        rules=[rule("R1", blast_class="body-local")],
        flags=[flag("R1", "A.java"), flag("R1", "B.java")],
        nodes=nodes,
        edges=edges,
    )
    output_path = tmp_path / "05-rule-shards-R1.json"

    rc1 = mod.main(["--artifacts-dir", str(tmp_path), "--rule-id", "R1"])
    bytes1 = output_path.read_bytes()
    rc2 = mod.main(["--artifacts-dir", str(tmp_path), "--rule-id", "R1"])
    bytes2 = output_path.read_bytes()

    assert rc1 == 0
    assert rc2 == 0
    assert bytes1 == bytes2

    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".plan-shards-")]
    assert leftovers == []

    report = json.loads(bytes1.decode("utf-8"))
    assert "generated_at" not in report


def test_dry_run_prints_summary_and_writes_nothing(tmp_path, capsys):
    mod = load_plan_shards()
    _write_artifacts(
        tmp_path,
        rules=[rule("R1", blast_class="body-local")],
        flags=[flag("R1", "A.java")],
        nodes={"A.java": node("A.java")},
    )
    rc = mod.main(["--artifacts-dir", str(tmp_path), "--rule-id", "R1", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "rule_id=" in out
    assert "shards=" in out
    assert not (tmp_path / "05-rule-shards-R1.json").exists()


def test_output_path_override_is_respected(tmp_path):
    mod = load_plan_shards()
    _write_artifacts(
        tmp_path,
        rules=[rule("R1", blast_class="body-local")],
        flags=[flag("R1", "A.java")],
        nodes={"A.java": node("A.java")},
    )
    custom = tmp_path / "custom.json"
    rc = mod.main(
        ["--artifacts-dir", str(tmp_path), "--rule-id", "R1", "--output", str(custom)]
    )
    assert rc == 0
    assert custom.is_file()
    assert not (tmp_path / "05-rule-shards-R1.json").exists()
