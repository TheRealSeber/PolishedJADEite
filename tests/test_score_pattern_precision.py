"""Tests for score_pattern_precision.py (precision gate, phase 2)."""

import hashlib
import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).parents[1]
SCORER = ROOT / ".claude/skills/jade-core-change-collector/scripts/score_pattern_precision.py"

REASON_TP = "Genuine construct match, exactly what the rule describes here."
REASON_FP = "This hit lands inside a comment, not the real construct at all."
assert len(REASON_TP) >= 20 and len(REASON_FP) >= 20


def load_scorer():
    spec = importlib.util.spec_from_file_location("score_pattern_precision_test", SCORER)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def make_hit(idx, file="src/A.java", pattern_index=0, line_hash=None):
    return {
        "hit_id": f"h{idx:04d}",
        "rank": idx,
        "pattern_index": pattern_index,
        "file": file,
        "line": idx + 1,
        "match_text": "(Foo.Bar)",
        "match_span": [0, 9],
        "line_text": f"Object o{idx} = (Foo.Bar) x;",
        "line_truncated": False,
        "line_hash": line_hash or f"lh{idx:04d}",
        "context_before": [],
        "context_after": [],
    }


def make_sample(rule_id, hits, status="CENSUS", total_hits=None, requested_sample_size=30, pattern_revision=1):
    total_hits = total_hits if total_hits is not None else len(hits)
    return {
        "schema_version": 1,
        "run_id": "test",
        "rule_id": rule_id,
        "rule_name": rule_id,
        "rule_description": "desc",
        "verification_hint": "hint",
        "manifest_artifact": "artifacts/01-breaking-changes-manifest.json",
        "manifest_rule_hash": "deadbeef",
        "workspace": "workspace",
        "pattern_revision": pattern_revision,
        "patterns": [{"index": 0, "pattern": "x", "target_extensions": [".java"], "reason": "r"}],
        "sampling": {
            "algorithm": "sha256-rank-uniform-v1",
            "seed_scope": "rule+pattern",
            "seed": "seed",
            "requested_sample_size": requested_sample_size,
            "context_lines": 3,
            "max_line_chars": 400,
            "nested": True,
        },
        "population": {
            "total_hits": total_hits,
            "files_with_hits": 1,
            "files_scanned": 1,
            "hits_per_pattern": {"0": total_hits},
            "max_hits_in_one_file": total_hits,
            "truncated": False,
            "population_signature": "sig",
        },
        "status": status,
        "sample_size": len(hits),
        "hits": hits,
        "warnings": [],
    }


def _dump(obj):
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_sample(artifacts, rule_id, sample):
    path = artifacts / f"01.5-precision-sample-{rule_id}.json"
    path.write_text(_dump(sample), encoding="utf-8")
    return path


def write_verdicts(artifacts, rule_id, sample_path, verdict_list):
    sample_hash = hashlib.sha256(sample_path.read_bytes()).hexdigest()
    verdicts = {
        "schema_version": 1,
        "rule_id": rule_id,
        "sample_artifact": sample_path.name,
        "sample_hash": sample_hash,
        "verdicts": verdict_list,
    }
    path = artifacts / f"01.5-precision-verdicts-{rule_id}.json"
    path.write_text(_dump(verdicts), encoding="utf-8")
    return path


def v(hit_id, verdict, reason=None, fp_class=None):
    entry = {"hit_id": hit_id, "verdict": verdict, "reason": reason or (REASON_TP if verdict == "TRUE_POSITIVE" else REASON_FP)}
    if fp_class:
        entry["false_positive_class"] = fp_class
    return entry


def _setup(tmp_path, precision_gate=None):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    cfg = {"run_id": "test", "artifacts_path": str(artifacts)}
    if precision_gate is not None:
        cfg["precision_gate"] = precision_gate
    (artifacts / "00-run-config.json").write_text(json.dumps(cfg), encoding="utf-8")
    return artifacts


def _run(artifacts, extra_args=None):
    cmd = [sys.executable, str(SCORER), "--run-config", str(artifacts / "00-run-config.json")]
    if extra_args:
        cmd += extra_args
    return subprocess.run(cmd, capture_output=True, text=True)


# --- Test 13: happy path -------------------------------------------------


def test_happy_path_all_true_positive(tmp_path):
    artifacts = _setup(tmp_path)
    hits = [make_hit(i) for i in range(10)]
    sample_path = write_sample(artifacts, "R1", make_sample("R1", hits))
    write_verdicts(artifacts, "R1", sample_path, [v(h["hit_id"], "TRUE_POSITIVE") for h in hits])

    result = _run(artifacts)
    assert result.returncode == 0, result.stderr
    report = json.loads((artifacts / "01.5-precision-report.json").read_text(encoding="utf-8"))
    entry = report["rules"]["R1"]
    assert entry["pattern_precision"] == 1.0
    assert entry["status"] == "PASS"
    assert entry["queue_eligible"] is True


# --- Test 14: below threshold ---------------------------------------------


def test_below_threshold_rejected_with_counterexamples(tmp_path):
    artifacts = _setup(tmp_path)
    hits = [make_hit(i) for i in range(10)]
    sample_path = write_sample(artifacts, "R1", make_sample("R1", hits))
    verdict_list = [v(hits[i]["hit_id"], "TRUE_POSITIVE") for i in range(2)]
    verdict_list += [
        v(hits[i]["hit_id"], "FALSE_POSITIVE", fp_class="NOT_THE_CONSTRUCT") for i in range(2, 10)
    ]
    write_verdicts(artifacts, "R1", sample_path, verdict_list)

    result = _run(artifacts)
    assert result.returncode == 1
    report = json.loads((artifacts / "01.5-precision-report.json").read_text(encoding="utf-8"))
    entry = report["rules"]["R1"]
    assert entry["status"] == "REJECTED"
    assert entry["queue_eligible"] is False
    assert entry["pattern_precision"] == 0.2
    assert len(entry["counterexamples"]) == 5
    # deterministic ordering: ascending by (file, line)
    lines = [c["line"] for c in entry["counterexamples"]]
    assert lines == sorted(lines)
    assert (artifacts / "PRECISION_ACTION_REQUIRED.md").exists()


# --- Test 15: sample_hash mismatch ----------------------------------------


def test_sample_hash_mismatch_exits_2_and_no_report(tmp_path):
    artifacts = _setup(tmp_path)
    hits = [make_hit(i) for i in range(5)]
    sample_path = write_sample(artifacts, "R1", make_sample("R1", hits))
    verdicts_path = write_verdicts(artifacts, "R1", sample_path, [v(h["hit_id"], "TRUE_POSITIVE") for h in hits])
    # Corrupt the recorded sample_hash so it no longer matches the real file.
    verdicts = json.loads(verdicts_path.read_text(encoding="utf-8"))
    verdicts["sample_hash"] = "0" * 64
    verdicts_path.write_text(_dump(verdicts), encoding="utf-8")

    result = _run(artifacts)
    assert result.returncode == 2
    assert not (artifacts / "01.5-precision-report.json").exists()


# --- Test 16: hit_id mismatches --------------------------------------------


def test_missing_extra_duplicate_hit_id_exits_2(tmp_path):
    artifacts = _setup(tmp_path)
    hits = [make_hit(i) for i in range(3)]
    sample_path = write_sample(artifacts, "R1", make_sample("R1", hits))
    # Missing a verdict for h0002, duplicate for h0000, unknown extra hit_id.
    verdict_list = [
        v("h0000", "TRUE_POSITIVE"),
        v("h0000", "TRUE_POSITIVE"),
        v("h0001", "TRUE_POSITIVE"),
        v("h9999", "TRUE_POSITIVE"),
    ]
    write_verdicts(artifacts, "R1", sample_path, verdict_list)

    result = _run(artifacts)
    assert result.returncode == 2
    assert "h9999" in result.stdout or "h9999" in result.stderr
    assert not (artifacts / "01.5-precision-report.json").exists()


# --- Test 17: reason too short ---------------------------------------------


def test_reason_too_short_exits_2(tmp_path):
    artifacts = _setup(tmp_path)
    hits = [make_hit(i) for i in range(2)]
    sample_path = write_sample(artifacts, "R1", make_sample("R1", hits))
    write_verdicts(
        artifacts,
        "R1",
        sample_path,
        [v(hits[0]["hit_id"], "TRUE_POSITIVE", reason="too short"), v(hits[1]["hit_id"], "TRUE_POSITIVE")],
    )
    result = _run(artifacts)
    assert result.returncode == 2
    assert not (artifacts / "01.5-precision-report.json").exists()


# --- Test 18: FALSE_POSITIVE without class ---------------------------------


def test_false_positive_without_class_exits_2(tmp_path):
    artifacts = _setup(tmp_path)
    hits = [make_hit(i) for i in range(2)]
    sample_path = write_sample(artifacts, "R1", make_sample("R1", hits))
    verdict_list = [
        {"hit_id": hits[0]["hit_id"], "verdict": "FALSE_POSITIVE", "reason": REASON_FP},
        v(hits[1]["hit_id"], "TRUE_POSITIVE"),
    ]
    write_verdicts(artifacts, "R1", sample_path, verdict_list)
    result = _run(artifacts)
    assert result.returncode == 2
    assert not (artifacts / "01.5-precision-report.json").exists()


# --- Test 19: too many UNDECIDABLE -----------------------------------------


def test_undecidable_over_ratio_is_inconclusive(tmp_path):
    artifacts = _setup(tmp_path)
    hits = [make_hit(i) for i in range(10)]
    sample_path = write_sample(artifacts, "R1", make_sample("R1", hits))
    verdict_list = [v(hits[i]["hit_id"], "UNDECIDABLE") for i in range(3)]
    verdict_list += [v(hits[i]["hit_id"], "TRUE_POSITIVE") for i in range(3, 10)]
    write_verdicts(artifacts, "R1", sample_path, verdict_list)

    result = _run(artifacts)
    assert result.returncode == 1
    report = json.loads((artifacts / "01.5-precision-report.json").read_text(encoding="utf-8"))
    entry = report["rules"]["R1"]
    assert entry["status"] == "INCONCLUSIVE"
    assert entry["next_action"] == "REJUDGE_WITH_MORE_CONTEXT"


# --- Test 20: Wilson straddle vs CENSUS hard decision -----------------------


def test_wilson_straddle_inconclusive_when_sampled_census_is_decisive(tmp_path):
    artifacts = _setup(tmp_path)

    # SAMPLED: 30 judged out of a much larger population, borderline precision.
    hits = [make_hit(i) for i in range(30)]
    sample_path = write_sample(
        artifacts, "SAMPLED_RULE", make_sample("SAMPLED_RULE", hits, status="SAMPLED", total_hits=500)
    )
    verdict_list = [v(hits[i]["hit_id"], "TRUE_POSITIVE") for i in range(21)]
    verdict_list += [v(hits[i]["hit_id"], "FALSE_POSITIVE", fp_class="OTHER") for i in range(21, 30)]
    write_verdicts(artifacts, "SAMPLED_RULE", sample_path, verdict_list)

    # CENSUS: exact same 21/30 ratio, but the whole population was judged.
    hits2 = [make_hit(i, file="src/B.java") for i in range(30)]
    sample_path2 = write_sample(
        artifacts, "CENSUS_RULE", make_sample("CENSUS_RULE", hits2, status="CENSUS", total_hits=30)
    )
    verdict_list2 = [v(hits2[i]["hit_id"], "TRUE_POSITIVE") for i in range(21)]
    verdict_list2 += [v(hits2[i]["hit_id"], "FALSE_POSITIVE", fp_class="OTHER") for i in range(21, 30)]
    write_verdicts(artifacts, "CENSUS_RULE", sample_path2, verdict_list2)

    result = _run(artifacts)
    report = json.loads((artifacts / "01.5-precision-report.json").read_text(encoding="utf-8"))

    sampled_entry = report["rules"]["SAMPLED_RULE"]
    assert sampled_entry["status"] == "INCONCLUSIVE"
    assert sampled_entry["next_action"] == "ENLARGE_SAMPLE"
    assert "suggested_command" in sampled_entry
    assert "--sample-size" in sampled_entry["suggested_command"]

    census_entry = report["rules"]["CENSUS_RULE"]
    assert census_entry["status"] in ("PASS", "REJECTED")  # never INCONCLUSIVE for CENSUS
    assert census_entry["pattern_precision"] == 0.7


# --- Test 21: anti-bypass ----------------------------------------------------


def test_min_precision_and_sample_size_flags_do_not_exist(tmp_path):
    artifacts = _setup(tmp_path)
    result = _run(artifacts, extra_args=["--min-precision", "0.0"])
    assert result.returncode != 0
    assert "unrecognized arguments" in result.stderr

    result2 = _run(artifacts, extra_args=["--sample-size", "5"])
    assert result2.returncode != 0
    assert "unrecognized arguments" in result2.stderr


# --- Test 22: rule may only raise the threshold, never lower it ------------


def test_rule_stricter_threshold_is_respected(tmp_path):
    artifacts = _setup(tmp_path, precision_gate={"enabled": True, "min_precision": 0.5})
    (artifacts / "01-breaking-changes-manifest.json").write_text(
        json.dumps({"rules": [{"id": "R1", "min_pattern_precision": 0.9}]}), encoding="utf-8"
    )
    hits = [make_hit(i) for i in range(10)]
    sample_path = write_sample(artifacts, "R1", make_sample("R1", hits))
    # precision = 8/10 = 0.8: passes the 0.5 policy floor but not the rule's 0.9.
    verdict_list = [v(hits[i]["hit_id"], "TRUE_POSITIVE") for i in range(8)]
    verdict_list += [v(hits[i]["hit_id"], "FALSE_POSITIVE", fp_class="OTHER") for i in range(8, 10)]
    write_verdicts(artifacts, "R1", sample_path, verdict_list)

    result = _run(artifacts)
    report = json.loads((artifacts / "01.5-precision-report.json").read_text(encoding="utf-8"))
    entry = report["rules"]["R1"]
    assert entry["effective_min_precision"] == 0.9
    assert entry["min_precision_source"] == "rule"
    assert entry["status"] == "REJECTED"


# --- Test 23: NO_POPULATION never blocks ------------------------------------


def test_no_population_does_not_block(tmp_path):
    artifacts = _setup(tmp_path)
    sample = make_sample("R1", [], status="NO_POPULATION", total_hits=0)
    write_sample(artifacts, "R1", sample)
    # No verdicts artifact needed/required for NO_POPULATION.

    result = _run(artifacts)
    assert result.returncode == 0
    report = json.loads((artifacts / "01.5-precision-report.json").read_text(encoding="utf-8"))
    entry = report["rules"]["R1"]
    assert entry["pattern_precision"] is None
    assert entry["queue_eligible"] is True
    assert entry["status"] == "NO_POPULATION"


# --- Test 24: ABANDONED after too many revisions ----------------------------


def test_abandoned_after_max_revisions(tmp_path):
    artifacts = _setup(tmp_path, precision_gate={"enabled": True, "max_revisions": 3})
    hits = [make_hit(i) for i in range(10)]
    sample_path = write_sample(
        artifacts, "R1", make_sample("R1", hits, pattern_revision=4)
    )
    verdict_list = [v(hits[i]["hit_id"], "FALSE_POSITIVE", fp_class="OTHER") for i in range(10)]
    write_verdicts(artifacts, "R1", sample_path, verdict_list)

    result = _run(artifacts)
    assert result.returncode == 1
    report = json.loads((artifacts / "01.5-precision-report.json").read_text(encoding="utf-8"))
    entry = report["rules"]["R1"]
    assert entry["status"] == "ABANDONED"
    assert entry["next_action"] == "HUMAN_DECISION"


# --- Test 25: overrides -----------------------------------------------------


def test_override_with_reason_and_approved_by(tmp_path):
    artifacts = _setup(
        tmp_path,
        precision_gate={
            "enabled": True,
            "overrides": {"R1": {"reason": "Known false positives, accepted risk", "approved_by": "user"}},
        },
    )
    hits = [make_hit(i) for i in range(10)]
    sample_path = write_sample(artifacts, "R1", make_sample("R1", hits))
    verdict_list = [v(hits[i]["hit_id"], "FALSE_POSITIVE", fp_class="OTHER") for i in range(10)]
    write_verdicts(artifacts, "R1", sample_path, verdict_list)

    result = _run(artifacts)
    assert result.returncode == 0
    report = json.loads((artifacts / "01.5-precision-report.json").read_text(encoding="utf-8"))
    entry = report["rules"]["R1"]
    assert entry["status"] == "OVERRIDDEN"
    assert entry["queue_eligible"] is True
    assert any(w["kind"] == "precision_override" for w in report["warnings"])


def test_override_missing_fields_exits_2(tmp_path):
    artifacts = _setup(
        tmp_path,
        precision_gate={"enabled": True, "overrides": {"R1": {"reason": "no approver given"}}},
    )
    hits = [make_hit(i) for i in range(2)]
    sample_path = write_sample(artifacts, "R1", make_sample("R1", hits))
    write_verdicts(artifacts, "R1", sample_path, [v(h["hit_id"], "TRUE_POSITIVE") for h in hits])

    result = _run(artifacts)
    assert result.returncode == 2
    assert not (artifacts / "01.5-precision-report.json").exists()


# --- Test 26: carry-forward on sample enlargement ---------------------------


def test_carry_forward_verdicts_preserves_unchanged_hits(tmp_path):
    scorer = load_scorer()
    old_hits = [make_hit(i) for i in range(5)]
    old_sample = make_sample("R1", old_hits)
    old_verdicts = {
        "schema_version": 1,
        "rule_id": "R1",
        "sample_artifact": "01.5-precision-sample-R1.json",
        "sample_hash": "irrelevant",
        "verdicts": [v(h["hit_id"], "TRUE_POSITIVE") for h in old_hits],
    }

    # Enlarged sample: same first 5 hit_ids/line_hashes (nested prefix) plus
    # 5 new ones, EXCEPT h0002's line_hash changed (source line edited).
    new_hits = [make_hit(i) for i in range(10)]
    new_hits[2] = dict(new_hits[2], line_hash="CHANGED")
    new_sample = make_sample("R1", new_hits)

    merged = scorer.carry_forward_verdicts(old_sample, old_verdicts, new_sample)
    carried_ids = {v_["hit_id"] for v_ in merged["verdicts"]}
    assert carried_ids == {"h0000", "h0001", "h0003", "h0004"}  # h0002 invalidated, h0005-9 not yet judged


# --- Test 27: determinism and atomicity -------------------------------------


def test_report_is_deterministic_and_atomic(tmp_path):
    artifacts = _setup(tmp_path)
    hits = [make_hit(i) for i in range(10)]
    sample_path = write_sample(artifacts, "R1", make_sample("R1", hits))
    write_verdicts(artifacts, "R1", sample_path, [v(h["hit_id"], "TRUE_POSITIVE") for h in hits])

    out1 = artifacts / "report1.json"
    out2 = artifacts / "report2.json"
    r1 = _run(artifacts, extra_args=["--output", str(out1)])
    r2 = _run(artifacts, extra_args=["--output", str(out2)])
    assert r1.returncode == r2.returncode == 0
    assert out1.read_bytes() == out2.read_bytes()
    leftovers = list(artifacts.glob("*.tmp")) + list(artifacts.glob(".score-pattern-precision-*"))
    assert leftovers == []
