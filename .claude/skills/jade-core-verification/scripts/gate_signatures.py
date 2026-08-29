#!/usr/bin/env python3
"""gate_signatures.py -- Gate a shard edit on signature leaks outside the shard.

Thin wrapper over ``graph_diff.compute_diff`` that compares the knowledge
graph before and after a shard edit and rejects the change whenever any
node's signature changed (or the node was removed) and one of its direct
dependents lies outside the shard's ``editable_files`` set. The report is
written atomically (tmp + fsync + rename); the canonical content contains
no timestamps, so repeated runs over the same graph pair produce
byte-identical output.

``graph_diff.py`` is imported, never reimplemented: this module owns none
of the signature-comparison or diff logic, only the shard-scoped leak
check layered on top of ``compute_diff``'s report.

Exit codes:
  0 = PASS with no warnings
  1 = PASS with graph_diff warnings (identity mismatch / graph diagnostics)
      or a truncated impact-path scan
  2 = REJECT (artifact written) or a structural error (malformed shard
      plan/graph, invalid id, unknown shard) -- artifact not written
  3 = missing input file or environment error (graph_diff unavailable,
      shard plan missing, write failure) -- artifact not written
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import re
import sys
import tempfile
from itertools import chain

SIGNATURE_GATE_VERSION = 1
GRAPH_DIFF_PATH = pathlib.Path(__file__).resolve().parent / "graph_diff.py"
ID_RE = re.compile(r"[A-Za-z0-9_.-]+")
PASS_REASON = "No signature change leaks outside the shard editable set"


# ---------------------------------------------------------------------------
# graph_diff loading
# ---------------------------------------------------------------------------


def _load_graph_diff():
    """Load graph_diff.py as a module without relying on sys.path[0].

    Uses importlib.util.spec_from_file_location rather than a plain
    ``import graph_diff`` -- a plain import only works when this script is
    run directly (sys.path[0] == this directory); a test harness that loads
    this module through importlib would not have that entry on sys.path.
    """
    spec = importlib.util.spec_from_file_location("jade_graph_diff", GRAPH_DIFF_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not build a module spec for {GRAPH_DIFF_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def read_json(path: pathlib.Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json_atomic(path: str, payload: dict) -> None:
    path = os.path.abspath(path)
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".signature-gate-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _find_leak(node_path: str, side: str, reverse_index: dict, editable: set):
    """Return a leaked_nodes entry for node_path, or None when nothing leaked.

    reverse_index is the (target -> [(from, edge_type), ...]) index produced
    by graph_diff._reverse_adjacency: only direct (one-hop) dependents are
    considered -- a signature change breaks compilation for direct
    consumers, not the whole transitive closure.
    """
    pairs = reverse_index.get(node_path, [])
    deps = {frm for frm, _etype in pairs if frm != node_path}
    leaked_deps = sorted(deps - editable)
    if not leaked_deps:
        return None
    leaked_set = set(leaked_deps)
    edge_types = sorted({etype for frm, etype in pairs if frm in leaked_set})
    return {
        "node": node_path,
        "side": side,
        "dependents": leaked_deps,
        "edge_types": edge_types,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Gate shard edits on signature leaks outside the shard editable set"
    )
    parser.add_argument("--artifacts-dir", required=True, help="Path to artifacts directory")
    parser.add_argument("--rule-id", required=True, help="Rule id owning the shard")
    parser.add_argument("--shard-id", required=True, help="Shard id to gate")
    parser.add_argument(
        "--before-graph", required=True, help="Knowledge graph built before the shard edit"
    )
    parser.add_argument(
        "--after-graph", required=True, help="Knowledge graph built after the shard edit"
    )
    parser.add_argument(
        "--shards-artifact",
        default=None,
        help="Shard plan artifact (default: <artifacts-dir>/05-rule-shards-<rule-id>.json)",
    )
    parser.add_argument("--output", default=None, help="Override output artifact path")
    args = parser.parse_args(argv)

    artifacts_dir = pathlib.Path(args.artifacts_dir)

    # Step 1: load graph_diff as a module (imported, never reimplemented).
    try:
        gd = _load_graph_diff()
    except Exception as exc:
        print(f"ERROR [GRAPH_DIFF_UNAVAILABLE] {exc}", file=sys.stderr)
        return 3

    # Step 2: validate ids and load the shard plan.
    if not ID_RE.fullmatch(args.rule_id) or not ID_RE.fullmatch(args.shard_id):
        print(
            f"ERROR [INVALID_ID] rule_id={args.rule_id!r} shard_id={args.shard_id!r} "
            f"must match {ID_RE.pattern!r}",
            file=sys.stderr,
        )
        return 2

    shards_path = (
        pathlib.Path(args.shards_artifact)
        if args.shards_artifact
        else artifacts_dir / f"05-rule-shards-{args.rule_id}.json"
    )
    if not shards_path.is_file():
        print(f"ERROR [SHARD_PLAN_NOT_FOUND] {shards_path}", file=sys.stderr)
        return 3

    try:
        shard_plan = read_json(shards_path)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR [SHARD_PLAN_MALFORMED] {exc}", file=sys.stderr)
        return 2
    if not isinstance(shard_plan, dict) or not isinstance(shard_plan.get("shards"), list):
        print(
            f"ERROR [SHARD_PLAN_MALFORMED] {shards_path} does not contain a 'shards' list",
            file=sys.stderr,
        )
        return 2

    shard = None
    for entry in shard_plan["shards"]:
        if isinstance(entry, dict) and entry.get("shard_id") == args.shard_id:
            shard = entry
            break
    if shard is None:
        print(
            f"ERROR [SHARD_NOT_FOUND] shard_id={args.shard_id!r} not found in {shards_path}",
            file=sys.stderr,
        )
        return 2

    editable_files = shard.get("editable_files")
    if (
        not isinstance(editable_files, list)
        or not editable_files
        or not all(isinstance(p, str) for p in editable_files)
    ):
        print(
            f"ERROR [SHARD_MALFORMED] shard {args.shard_id!r} has no non-empty "
            f"'editable_files' list of strings",
            file=sys.stderr,
        )
        return 2
    editable = set(editable_files)

    run_id = "unknown"
    run_config_path = artifacts_dir / "00-run-config.json"
    if run_config_path.is_file():
        try:
            run_config = read_json(run_config_path)
            if isinstance(run_config, dict) and isinstance(run_config.get("run_id"), str):
                run_id = run_config["run_id"]
        except (json.JSONDecodeError, OSError):
            run_id = "unknown"

    # Step 3: load both graphs (before, then after).
    for label, path in (("before", args.before_graph), ("after", args.after_graph)):
        if not os.path.isfile(path):
            print(f"ERROR [GRAPH_NOT_FOUND] {label}: {path}", file=sys.stderr)
            return 3

    try:
        before = gd._load_graph(args.before_graph)
        after = gd._load_graph(args.after_graph)
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        print(f"ERROR [GRAPH_MALFORMED] {exc}", file=sys.stderr)
        return 2

    # Step 4: the diff itself.
    try:
        report = gd.compute_diff(before, after)
    except (ValueError, TypeError) as exc:
        print(f"ERROR [GRAPH_DIFF_ERROR] {exc}", file=sys.stderr)
        return 2

    changed = list(report["changed_nodes"])
    removed = list(report["removed_nodes"])

    # Step 5: reverse-adjacency indexes for direct (one-hop) dependents only.
    rev_after = gd._reverse_adjacency(after)
    rev_before = gd._reverse_adjacency(before)

    # Step 6: leak detection.
    leaked_nodes = []
    expansion = set()
    for node_path in sorted(changed):
        entry = _find_leak(node_path, "after", rev_after, editable)
        if entry is not None:
            leaked_nodes.append(entry)
            expansion.update(entry["dependents"])
    for node_path in sorted(removed):
        entry = _find_leak(node_path, "before", rev_before, editable)
        if entry is not None:
            leaked_nodes.append(entry)
            expansion.update(entry["dependents"])
    leaked_nodes.sort(key=lambda item: (item["node"], item["side"]))

    out_of_scope_changed_nodes = sorted((set(changed) | set(removed)) - editable)
    expansion |= set(out_of_scope_changed_nodes)
    suggested_shard_expansion = sorted(expansion - editable)

    # Step 7: verdict and reason.
    verdict = "REJECT" if (leaked_nodes or out_of_scope_changed_nodes) else "PASS"
    if verdict == "PASS":
        reason = PASS_REASON
    else:
        parts = []
        if leaked_nodes:
            affected_files = set(chain(*[entry["dependents"] for entry in leaked_nodes]))
            parts.append(
                f"{len(leaked_nodes)} changed node(s) leak signature changes to "
                f"{len(affected_files)} file(s) outside the shard editable set"
            )
        if out_of_scope_changed_nodes:
            parts.append(
                f"{len(out_of_scope_changed_nodes)} node(s) changed outside the "
                f"shard editable set"
            )
        reason = "; ".join(parts)

    artifact = {
        "schema_version": SIGNATURE_GATE_VERSION,
        "run_id": run_id,
        "rule_id": args.rule_id,
        "shard_id": args.shard_id,
        "shard_class": shard.get("class"),
        "verdict": verdict,
        "editable_file_count": len(editable_files),
        "changed_nodes": changed,
        "removed_nodes": removed,
        "out_of_scope_changed_nodes": out_of_scope_changed_nodes,
        "leaked_nodes": leaked_nodes,
        "suggested_shard_expansion": suggested_shard_expansion,
        "reason": reason,
        "graph_diff_version": report["graph_diff_version"],
        "graph_diff_warnings": report["warnings"],
        "impact_path_truncated": report["impact_path_truncated"],
    }

    output_path = args.output or str(
        artifacts_dir / f"07-shard-signature-gate-{args.shard_id}.json"
    )

    # Step 8: atomic write and exit code.
    try:
        _write_json_atomic(output_path, artifact)
    except OSError as exc:
        print(f"ERROR [WRITE_FAILED] {exc}", file=sys.stderr)
        return 3

    print(f"Signature gate written: {output_path}")
    print(f"  shard_id={args.shard_id} verdict={verdict}")
    print(
        f"  changed={len(changed)} leaked={len(leaked_nodes)} "
        f"expansion={len(suggested_shard_expansion)}"
    )

    if verdict == "REJECT":
        print(f"ERROR [SIGNATURE_LEAK] {reason}", file=sys.stderr)
        for entry in leaked_nodes[:20]:
            preview = ", ".join(entry["dependents"][:10])
            print(f"ERROR [SIGNATURE_LEAK] {entry['node']} -> {preview}", file=sys.stderr)
        return 2

    if report["warnings"]:
        for warning in report["warnings"]:
            print(f"WARNING [GRAPH_DIFF] {json.dumps(warning, sort_keys=True)}", file=sys.stderr)

    if report["warnings"] or report["impact_path_truncated"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
