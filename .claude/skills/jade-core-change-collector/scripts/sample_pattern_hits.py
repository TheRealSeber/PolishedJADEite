#!/usr/bin/env python3
"""sample_pattern_hits.py -- Deterministic, population-faithful pattern sampler.

Phase 1 of the precision gate (see PRECISION_GATE_READY in orchestrator.py).
Computes the exact population of regex hits one manifest rule would produce
across the workspace -- using the scanner's own file-collection and
line-skipping logic via ``importlib`` so the population is provably
identical to what ``scan_and_tag.py`` would flag -- then samples a
deterministic, rank-ordered subset for an agent to judge for precision.

This script never mutates the workspace. It only reads.

Exit codes:
  0 = success (status SAMPLED, no warnings)
  1 = attention needed (status CENSUS/NO_POPULATION, or warnings present)
  2 = structural error (rule not in manifest, pattern does not compile,
      invalid --rule-id, --sample-size below the run-config floor,
      --context-lines out of range)
  3 = missing input file / environment error (write failure, missing
      run-config, manifest, or workspace)
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import sys
import tempfile
from typing import Any, Dict, List, Optional, Set, Tuple

SCHEMA_VERSION = 1

MANIFEST_ARTIFACT = "01-breaking-changes-manifest.json"
RUN_CONFIG_ARTIFACT = "00-run-config.json"

PRECISION_GATE_CONFIG_KEY = "precision_gate"
DEFAULT_SAMPLE_SIZE = 30
DEFAULT_CONTEXT_LINES = 3
DEFAULT_MAX_LINE_CHARS = 400
DEFAULT_SEED_SCOPE = "rule+pattern"

RULE_ID_RE = re.compile(r"[A-Za-z0-9_.-]+")

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]

_SCANNER_MODULE = None


# ---------------------------------------------------------------------------
# Small IO helpers
# ---------------------------------------------------------------------------


def read_json(path: pathlib.Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json_atomic(path: pathlib.Path, payload: Dict[str, Any]) -> None:
    abs_path = os.path.abspath(str(path))
    directory = os.path.dirname(abs_path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".sample-pattern-hits-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, abs_path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _artifact_repr(path: pathlib.Path) -> str:
    """POSIX path relative to REPO_ROOT, or absolute POSIX if outside it."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def rule_content_hash(rule: Dict[str, Any]) -> str:
    """Canonical content hash of a manifest rule dict.

    Shared (by re-implementation, not import) with score_pattern_precision.py
    and orchestrator.py so a rule's identity can be compared across
    artifacts written by different processes.
    """
    return hashlib.sha256(
        json.dumps(rule, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def _load_scanner_module() -> Any:
    """Import scan_and_tag.py by path so population matches the real scanner.

    Mirrors the ``importlib`` pattern already used by
    ``orchestrator._load_knowledge_graph`` for the same reason: two
    independent scripts must agree on what counts as a candidate file
    without importing each other as packages.
    """
    global _SCANNER_MODULE
    if _SCANNER_MODULE is not None:
        return _SCANNER_MODULE
    scanner_path = (
        pathlib.Path(__file__).resolve().parents[2]
        / "jade-core-scanner"
        / "scripts"
        / "scan_and_tag.py"
    )
    spec = importlib.util.spec_from_file_location("jade_scan_and_tag_for_sampler", scanner_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load scanner module from {scanner_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _SCANNER_MODULE = module
    return module


# ---------------------------------------------------------------------------
# Precision-gate policy defaults (see 00-run-config.json#precision_gate)
# ---------------------------------------------------------------------------


def precision_defaults() -> Dict[str, Any]:
    return {
        "sample_size": DEFAULT_SAMPLE_SIZE,
        "max_sample_size": 120,
        "context_lines": DEFAULT_CONTEXT_LINES,
        "max_line_chars": DEFAULT_MAX_LINE_CHARS,
        "seed_scope": DEFAULT_SEED_SCOPE,
    }


def load_policy(run_config: Dict[str, Any]) -> Dict[str, Any]:
    policy = precision_defaults()
    block = run_config.get(PRECISION_GATE_CONFIG_KEY)
    if isinstance(block, dict):
        for key in ("sample_size", "max_sample_size", "context_lines", "max_line_chars", "seed_scope"):
            if key in block:
                policy[key] = block[key]
    return policy


# ---------------------------------------------------------------------------
# Seeded ranking
# ---------------------------------------------------------------------------


def compute_seed(rule_id: str, pattern_revision: int, patterns: List[str], seed_scope: str) -> str:
    """Deterministic seed. See section 8 of the precision-gate spec:

    stdlib ``random`` is deliberately avoided -- its sampling algorithm is
    not guaranteed stable across CPython versions, so "reproducible run"
    would stop being true. A pure sha256 rank instead guarantees byte
    identical output forever, on every platform.
    """
    if seed_scope == "rule_id":
        material = rule_id
    else:
        material = "\0".join([rule_id, str(pattern_revision)] + list(patterns))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def rank_key(seed: str, file_: str, line: int, pattern_index: int) -> str:
    material = f"{seed}\0{file_}\0{line}\0{pattern_index}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def compute_hit_id(rule_id: str, file_: str, line: int, pattern_index: int) -> str:
    material = f"{rule_id}\0{file_}\0{line}\0{pattern_index}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def compute_line_hash(line_text: str) -> str:
    return hashlib.sha256(line_text.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Population computation
# ---------------------------------------------------------------------------


def compute_population(
    workspace: pathlib.Path,
    rule: Dict[str, Any],
    scanner_module: Any,
    max_line_chars: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]]]:
    """Compute every hit the scanner would flag for *rule*, without mutating.

    Returns (raw_hits, population_stats, warnings). raw_hits are unranked
    and unsampled -- every match found, one entry per (file, line,
    pattern_index).
    """
    warnings: List[Dict[str, Any]] = []
    rule_def = scanner_module.RuleDef(rule)

    all_extensions: Set[str] = {e.lower() for e in rule_def.extensions()}
    candidates = sorted(
        scanner_module.collect_candidate_files(workspace, all_extensions),
        key=lambda p: str(p),
    )
    files_scanned = len(candidates)

    raw_hits: List[Dict[str, Any]] = []
    hits_per_pattern: Dict[str, int] = {str(i): 0 for i in range(len(rule_def.patterns))}
    files_with_hits: Set[str] = set()
    per_file_counts: Dict[str, int] = {}

    for pattern_index, pattern in enumerate(rule_def.patterns):
        allowed = {e.lower() for e in pattern.target_extensions}
        for fp in candidates:
            ext = fp.suffix
            if ext.lower() not in allowed:
                continue
            rel = str(fp.relative_to(workspace)).replace("\\", "/")
            try:
                with fp.open("r", encoding="utf-8", errors="replace") as fh:
                    lines = [ln.rstrip("\n").rstrip("\r") for ln in fh.readlines()]
            except OSError as exc:
                warnings.append(
                    {"kind": "file_read_error", "file": rel, "message": str(exc)}
                )
                continue

            skip_prefixes = scanner_module._comment_skip_prefixes(ext)
            for i, raw_line in enumerate(lines):
                stripped = raw_line.strip()
                if stripped.startswith(skip_prefixes):
                    continue
                match = pattern.compiled.search(raw_line)
                if not match:
                    continue

                line_no = i + 1
                line_truncated = len(raw_line) > max_line_chars
                stored_line = raw_line[:max_line_chars] if line_truncated else raw_line
                raw_hits.append(
                    {
                        "pattern_index": pattern_index,
                        "file": rel,
                        "line": line_no,
                        "match_text": match.group(0),
                        "match_span": [match.start(), match.end()],
                        "line_text_full": raw_line,
                        "line_text": stored_line,
                        "line_truncated": line_truncated,
                        "context_before_src": lines,
                        "context_index": i,
                    }
                )
                hits_per_pattern[str(pattern_index)] += 1
                files_with_hits.add(rel)
                per_file_counts[rel] = per_file_counts.get(rel, 0) + 1

    total_hits = len(raw_hits)
    max_hits_in_one_file = max(per_file_counts.values()) if per_file_counts else 0

    population_keys = sorted(
        (h["file"], h["line"], h["pattern_index"]) for h in raw_hits
    )
    population_signature = hashlib.sha256(
        "\n".join(f"{f}\t{ln}\t{pi}" for f, ln, pi in population_keys).encode("utf-8")
    ).hexdigest()

    population_stats = {
        "total_hits": total_hits,
        "files_with_hits": len(files_with_hits),
        "files_scanned": files_scanned,
        "hits_per_pattern": hits_per_pattern,
        "max_hits_in_one_file": max_hits_in_one_file,
        "truncated": False,
        "population_signature": population_signature,
    }
    return raw_hits, population_stats, warnings


def _finalize_hit(
    raw: Dict[str, Any], rule_id: str, context_lines: int, rank: int
) -> Dict[str, Any]:
    lines = raw["context_before_src"]
    i = raw["context_index"]
    context_before = lines[max(0, i - context_lines): i]
    context_after = lines[i + 1: i + 1 + context_lines]
    hit_id = compute_hit_id(rule_id, raw["file"], raw["line"], raw["pattern_index"])
    return {
        "hit_id": hit_id,
        "rank": rank,
        "pattern_index": raw["pattern_index"],
        "file": raw["file"],
        "line": raw["line"],
        "match_text": raw["match_text"],
        "match_span": raw["match_span"],
        "line_text": raw["line_text"],
        "line_truncated": raw["line_truncated"],
        "line_hash": compute_line_hash(raw["line_text_full"]),
        "context_before": context_before,
        "context_after": context_after,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sample regex hits for one manifest rule (precision gate, phase 1)"
    )
    parser.add_argument("--run-config", required=True, help="Path to 00-run-config.json")
    parser.add_argument("--rule-id", required=True, help="Rule id to sample")
    parser.add_argument("--sample-size", type=int, default=None, help="Requested sample size (>= run-config floor)")
    parser.add_argument("--context-lines", type=int, default=None, help="Lines of context before/after each hit (0-10)")
    parser.add_argument("--output", default=None, help="Override output artifact path")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute population/sample statistics and print them without writing the artifact",
    )
    args = parser.parse_args(argv)

    if RULE_ID_RE.fullmatch(args.rule_id) is None:
        print(f"ERROR [INVALID_RULE_ID] {args.rule_id!r}", file=sys.stderr)
        return 2

    run_config_path = pathlib.Path(args.run_config)
    if not run_config_path.is_file():
        print(f"ERROR [INPUT_NOT_FOUND] run-config: {run_config_path}", file=sys.stderr)
        return 3

    try:
        run_config = read_json(run_config_path)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR [INPUT_MALFORMED] run-config: {exc}", file=sys.stderr)
        return 2
    if not isinstance(run_config, dict):
        print("ERROR [INPUT_MALFORMED] run-config must be a JSON object", file=sys.stderr)
        return 2

    run_id = run_config.get("run_id", "unknown")
    artifacts_dir = pathlib.Path(run_config.get("artifacts_path", run_config_path.parent))
    workspace = pathlib.Path(run_config.get("workspace_path", "workspace"))

    policy = load_policy(run_config)

    context_lines = args.context_lines if args.context_lines is not None else policy["context_lines"]
    if not (0 <= context_lines <= 10):
        print(f"ERROR [INVALID_CONTEXT_LINES] {context_lines} not in [0, 10]", file=sys.stderr)
        return 2

    floor_sample_size = policy["sample_size"]
    requested_sample_size = args.sample_size if args.sample_size is not None else floor_sample_size
    if args.sample_size is not None and args.sample_size < floor_sample_size:
        print(
            f"ERROR [SAMPLE_SIZE_BELOW_FLOOR] --sample-size {args.sample_size} "
            f"< run-config floor {floor_sample_size}",
            file=sys.stderr,
        )
        return 2

    max_line_chars = policy["max_line_chars"]
    seed_scope = policy["seed_scope"]

    if not workspace.is_dir():
        print(f"ERROR [INPUT_NOT_FOUND] workspace: {workspace}", file=sys.stderr)
        return 3

    manifest_path = artifacts_dir / MANIFEST_ARTIFACT
    if not manifest_path.is_file():
        print(f"ERROR [INPUT_NOT_FOUND] manifest: {manifest_path}", file=sys.stderr)
        return 3

    try:
        manifest = read_json(manifest_path)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR [INPUT_MALFORMED] manifest: {exc}", file=sys.stderr)
        return 2
    if not isinstance(manifest, dict) or not isinstance(manifest.get("rules"), list):
        print(f"ERROR [INPUT_MALFORMED] manifest must have a 'rules' list: {manifest_path}", file=sys.stderr)
        return 2

    rule: Optional[Dict[str, Any]] = None
    for r in manifest["rules"]:
        if isinstance(r, dict) and r.get("id") == args.rule_id:
            rule = r
            break
    if rule is None:
        print(f"ERROR [RULE_NOT_IN_MANIFEST] {args.rule_id}", file=sys.stderr)
        return 2

    pattern_revision = rule.get("pattern_revision", 1)
    if not isinstance(pattern_revision, int) or isinstance(pattern_revision, bool):
        pattern_revision = 1

    try:
        scanner_module = _load_scanner_module()
    except RuntimeError as exc:
        print(f"ERROR [SCANNER_UNAVAILABLE] {exc}", file=sys.stderr)
        return 3

    try:
        rule_def_probe = scanner_module.RuleDef(rule)
    except (ValueError, re.error, KeyError) as exc:
        print(f"ERROR [PATTERN_COMPILE_ERROR] {args.rule_id}: {exc}", file=sys.stderr)
        return 2

    pattern_texts = [p.pattern_str for p in rule_def_probe.patterns]
    seed = compute_seed(args.rule_id, pattern_revision, pattern_texts, seed_scope)

    raw_hits, population_stats, warnings = compute_population(
        workspace, rule, scanner_module, max_line_chars
    )

    ranked = sorted(
        raw_hits,
        key=lambda h: (
            rank_key(seed, h["file"], h["line"], h["pattern_index"]),
            h["file"],
            h["line"],
            h["pattern_index"],
        ),
    )

    total_hits = population_stats["total_hits"]
    if total_hits == 0:
        status = "NO_POPULATION"
        sample_size = 0
    elif total_hits <= requested_sample_size:
        status = "CENSUS"
        sample_size = total_hits
    else:
        status = "SAMPLED"
        sample_size = requested_sample_size

    hits = [
        _finalize_hit(raw, args.rule_id, context_lines, rank)
        for rank, raw in enumerate(ranked[:sample_size])
    ]

    patterns_payload = [
        {
            "index": i,
            "pattern": p.pattern_str,
            "target_extensions": list(p.target_extensions),
            "reason": p.reason,
        }
        for i, p in enumerate(rule_def_probe.patterns)
    ]

    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "rule_id": args.rule_id,
        "rule_name": rule.get("name", args.rule_id),
        "rule_description": rule.get("description", ""),
        "verification_hint": rule.get("verification_hint", ""),
        "manifest_artifact": _artifact_repr(manifest_path),
        "manifest_rule_hash": rule_content_hash(rule),
        "workspace": _artifact_repr(workspace),
        "pattern_revision": pattern_revision,
        "patterns": patterns_payload,
        "sampling": {
            "algorithm": "sha256-rank-uniform-v1",
            "seed_scope": seed_scope,
            "seed": seed,
            "requested_sample_size": requested_sample_size,
            "context_lines": context_lines,
            "max_line_chars": max_line_chars,
            "nested": True,
        },
        "population": population_stats,
        "status": status,
        "sample_size": sample_size,
        "hits": hits,
        "warnings": warnings,
    }

    output_path = (
        pathlib.Path(args.output)
        if args.output
        else artifacts_dir / f"01.5-precision-sample-{args.rule_id}.json"
    )

    if args.dry_run:
        print(
            f"DRY-RUN rule_id={args.rule_id} status={status} "
            f"files_scanned={population_stats['files_scanned']} "
            f"total_hits={total_hits} sample_size={sample_size}"
        )
    else:
        try:
            _write_json_atomic(output_path, payload)
        except OSError as exc:
            print(f"ERROR [WRITE_FAILED] {exc}", file=sys.stderr)
            return 3
        print(f"Sample written: {output_path}")

    print(
        f"  rule_id={args.rule_id} status={status} sample_size={sample_size} "
        f"total_hits={total_hits} files_with_hits={population_stats['files_with_hits']}"
    )

    if status != "SAMPLED" or warnings:
        for w in warnings:
            print(f"WARNING [SAMPLE_PATTERN_HITS] {json.dumps(w, sort_keys=True)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
