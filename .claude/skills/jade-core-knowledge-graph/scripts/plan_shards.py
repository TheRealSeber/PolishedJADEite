#!/usr/bin/env python3
"""plan_shards.py -- Plan graph-closed edit shards for one migration rule.

Splits the flagged files of a single migration rule into disjoint,
graph-closed shards and writes them to ``05-rule-shards-<rule_id>.json``.
The grouping strategy is selected solely from the rule's ``blast_class``
field in the breaking-changes manifest:

  * ``body-local`` -- flagged files are grouped into their connected
    components on the undirected graph induced by the five knowledge-graph
    edge buckets. Each component becomes an independently editable,
    parallel-safe shard.
  * ``signature`` -- a single shard covering every flagged file plus every
    file with a direct (one-hop) incoming edge to a flagged file. Not
    parallel-safe: signature changes ripple across the whole shard.

The report is written atomically (tmp + fsync + rename) and contains no
timestamps, so repeated runs over the same inputs produce byte-identical
output.

Exit codes:
  0 = success (status OK, no warnings)
  1 = attention needed (status UNCLASSIFIED/EMPTY, or warnings present)
  2 = structural error (malformed JSON, missing rule, invalid blast_class,
      shard invariant violated, invalid --rule-id)
  3 = missing input file / environment error (write failure)
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import tempfile
from typing import Any, Dict, List, Optional, Set, Tuple

PLAN_SHARDS_VERSION = 1

EDGE_TYPES = ("imports", "extends", "implements", "calls", "type_refs")

GRAPH_ARTIFACT = "03.5-knowledge-graph.json"
FLAG_INDEX_ARTIFACT = "04-flag-index.json"
MANIFEST_ARTIFACT = "01-breaking-changes-manifest.json"
RUN_CONFIG_ARTIFACT = "00-run-config.json"

BODY_LOCAL = "body-local"
SIGNATURE = "signature"
BLAST_CLASSES = (BODY_LOCAL, SIGNATURE)

INVARIANTS_BY_CLASS = {
    BODY_LOCAL: sorted(
        [
            "EDITS_CONFINED_TO_EDITABLE_FILES",
            "PUBLIC_SIGNATURES_UNCHANGED",
            "READ_ONLY_CONTEXT_NOT_MODIFIED",
        ]
    ),
    SIGNATURE: sorted(
        [
            "EDITS_CONFINED_TO_EDITABLE_FILES",
            "READ_ONLY_CONTEXT_NOT_MODIFIED",
            "SEQUENTIAL_EXECUTION_REQUIRED",
            "SIGNATURE_CHANGES_CONFINED_TO_EDITABLE_FILES",
        ]
    ),
}

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]

RULE_ID_RE = re.compile(r"[A-Za-z0-9_.-]+")


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
    fd, tmp = tempfile.mkstemp(prefix=".plan-shards-", suffix=".tmp", dir=directory)
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


# ---------------------------------------------------------------------------
# Graph adjacency
# ---------------------------------------------------------------------------


def build_edge_index(
    graph: Dict[str, Any]
) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]]]:
    """Build forward/reverse adjacency sets over all five edge buckets.

    forward[a] = {b, ...} when an edge a -> b exists in any bucket.
    reverse[b] = {a, ...} for the same edges.

    Malformed edges (non-dict, non-string endpoints, empty strings) are
    skipped, matching the filter used by graph_diff._reverse_adjacency.
    Self-loops (from == to) are dropped -- the ``calls`` bucket alone
    carries thousands of them and they would otherwise be meaningless for
    component grouping.
    """
    forward: Dict[str, Set[str]] = {}
    reverse: Dict[str, Set[str]] = {}
    edges = graph.get("edges")
    if not isinstance(edges, dict):
        return forward, reverse
    for etype in EDGE_TYPES:
        bucket = edges.get(etype, [])
        if not isinstance(bucket, list):
            continue
        for e in bucket:
            if not isinstance(e, dict):
                continue
            a = e.get("from")
            b = e.get("to")
            if not (isinstance(a, str) and isinstance(b, str) and a and b):
                continue
            if a == b:
                continue
            forward.setdefault(a, set()).add(b)
            reverse.setdefault(b, set()).add(a)
    return forward, reverse


def _connected_components(
    known: List[str], forward: Dict[str, Set[str]], reverse: Dict[str, Set[str]]
) -> List[List[str]]:
    """Connected components of the undirected graph induced on ``known``.

    Iterative (stack-based) traversal -- ``known`` can be a few hundred
    files and recursion depth should not depend on component size.
    """
    known_set = set(known)
    adjacency: Dict[str, Set[str]] = {}
    for f in known:
        adjacency[f] = (forward.get(f, set()) | reverse.get(f, set())) & known_set

    visited: Set[str] = set()
    components: List[List[str]] = []
    for start in sorted(known):
        if start in visited:
            continue
        visited.add(start)
        stack = [start]
        component: List[str] = []
        while stack:
            node = stack.pop()
            component.append(node)
            for neighbor in adjacency.get(node, ()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        components.append(sorted(component))
    return components


# ---------------------------------------------------------------------------
# Shard construction
# ---------------------------------------------------------------------------


def _plan_body_local(
    rule_id: str,
    known: List[str],
    missing: List[str],
    forward: Dict[str, Set[str]],
    reverse: Dict[str, Set[str]],
) -> List[Dict[str, Any]]:
    components = _connected_components(known, forward, reverse)
    for f in missing:
        components.append([f])
    components.sort(key=lambda c: c[0])

    shards: List[Dict[str, Any]] = []
    for index, component in enumerate(components, start=1):
        editable_files = sorted(component)
        deps: Set[str] = set()
        for f in editable_files:
            deps |= reverse.get(f, set())
        read_only_context = sorted(deps - set(editable_files))
        shards.append(
            {
                "shard_id": f"{rule_id}-{BODY_LOCAL}-{index:03d}",
                "rule_id": rule_id,
                "class": BODY_LOCAL,
                "editable_files": editable_files,
                "read_only_context": read_only_context,
                "entry_points": [],
                "invariants": INVARIANTS_BY_CLASS[BODY_LOCAL],
                "graph_artifact": "",
                "parallel_safe": True,
            }
        )
    return shards


def _plan_signature(
    rule_id: str, flagged_files: List[str], reverse: Dict[str, Set[str]]
) -> List[Dict[str, Any]]:
    deps: Set[str] = set()
    for f in flagged_files:
        deps |= reverse.get(f, set())
    editable_files = sorted(set(flagged_files) | deps)

    context_deps: Set[str] = set()
    for f in editable_files:
        context_deps |= reverse.get(f, set())
    read_only_context = sorted(context_deps - set(editable_files))

    shard = {
        "shard_id": f"{rule_id}-{SIGNATURE}-001",
        "rule_id": rule_id,
        "class": SIGNATURE,
        "editable_files": editable_files,
        "read_only_context": read_only_context,
        "entry_points": [],
        "invariants": INVARIANTS_BY_CLASS[SIGNATURE],
        "graph_artifact": "",
        "parallel_safe": False,
    }
    return [shard]


def _entry_points_for_shard(
    shard: Dict[str, Any],
    rule_flags: List[Dict[str, Any]],
    warnings: List[Dict[str, Any]],
) -> None:
    editable = set(shard["editable_files"])
    seen: Set[Tuple[str, int]] = set()
    for f in rule_flags:
        file_ = f.get("file")
        if file_ not in editable:
            continue
        line = f.get("line")
        if not isinstance(line, int) or isinstance(line, bool):
            warnings.append(
                {
                    "kind": "flag_missing_line",
                    "file": file_,
                    "value": repr(line),
                    "message": "Flag has no integer line; entry point skipped",
                }
            )
            continue
        seen.add((file_, line))
    shard["entry_points"] = [
        {"file": a, "line": b} for a, b in sorted(seen)
    ]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Plan graph-closed edit shards for one migration rule"
    )
    parser.add_argument(
        "--artifacts-dir", required=True, help="Path to artifacts directory"
    )
    parser.add_argument(
        "--rule-id", required=True, help="Rule id to plan shards for"
    )
    parser.add_argument(
        "--graph-artifacts-dir",
        default=None,
        help="Artifacts directory holding 03.5-knowledge-graph.json (default: --artifacts-dir)",
    )
    parser.add_argument(
        "--output", default=None, help="Override output artifact path"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute the plan and print the summary without writing the artifact",
    )
    args = parser.parse_args(argv)

    if RULE_ID_RE.fullmatch(args.rule_id) is None:
        print(f"ERROR [INVALID_RULE_ID] {args.rule_id}", file=sys.stderr)
        return 2

    artifacts_dir = pathlib.Path(args.artifacts_dir)
    graph_artifacts_dir = (
        pathlib.Path(args.graph_artifacts_dir)
        if args.graph_artifacts_dir
        else artifacts_dir
    )

    graph_path = graph_artifacts_dir / GRAPH_ARTIFACT
    flags_path = artifacts_dir / FLAG_INDEX_ARTIFACT
    manifest_path = artifacts_dir / MANIFEST_ARTIFACT

    for label, path in (
        ("manifest", manifest_path),
        ("flags", flags_path),
        ("graph", graph_path),
    ):
        if not path.is_file():
            print(f"ERROR [INPUT_NOT_FOUND] {label}: {path}", file=sys.stderr)
            return 3

    try:
        manifest = read_json(manifest_path)
        if not isinstance(manifest, dict) or not isinstance(
            manifest.get("rules"), list
        ):
            raise ValueError(
                f"manifest must be a JSON object with a 'rules' list: {manifest_path}"
            )
        flag_index = read_json(flags_path)
        if not isinstance(flag_index, dict) or not isinstance(
            flag_index.get("flags"), list
        ):
            raise ValueError(
                f"flag index must be a JSON object with a 'flags' list: {flags_path}"
            )
        graph = read_json(graph_path)
        if (
            not isinstance(graph, dict)
            or not isinstance(graph.get("nodes"), dict)
            or not isinstance(graph.get("edges"), dict)
        ):
            raise ValueError(
                f"graph artifact must be a JSON object with 'nodes' and 'edges' maps: {graph_path}"
            )
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        print(f"ERROR [INPUT_MALFORMED] {exc}", file=sys.stderr)
        return 2

    run_id = "unknown"
    run_config_path = artifacts_dir / RUN_CONFIG_ARTIFACT
    if run_config_path.is_file():
        try:
            run_config = read_json(run_config_path)
            if isinstance(run_config, dict):
                run_id = run_config.get("run_id", "unknown")
        except (json.JSONDecodeError, OSError, ValueError):
            run_id = "unknown"

    rule = None
    for r in manifest["rules"]:
        if isinstance(r, dict) and r.get("id") == args.rule_id:
            rule = r
            break
    if rule is None:
        print(f"ERROR [RULE_NOT_IN_MANIFEST] {args.rule_id}", file=sys.stderr)
        return 2

    raw_blast_class = rule.get("blast_class")
    blast_class: Optional[str] = None
    status: str
    if raw_blast_class is None:
        status = "UNCLASSIFIED"
    elif isinstance(raw_blast_class, str) and raw_blast_class in BLAST_CLASSES:
        blast_class = raw_blast_class
        status = "OK"  # provisional; may become EMPTY below
    else:
        print(
            f"ERROR [INVALID_BLAST_CLASS] {raw_blast_class!r}", file=sys.stderr
        )
        return 2

    rule_flags = [
        f
        for f in flag_index["flags"]
        if isinstance(f, dict) and f.get("rule_id") == args.rule_id
    ]
    flagged_files = sorted(
        {
            f["file"]
            for f in rule_flags
            if isinstance(f.get("file"), str) and f["file"]
        }
    )
    total_flags = len(rule_flags)
    total_flagged_files = len(flagged_files)

    warnings: List[Dict[str, Any]] = []
    shards: List[Dict[str, Any]] = []
    flagged_files_missing_from_graph: List[str] = []

    graph_artifact_repr = _artifact_repr(graph_path)
    flag_index_artifact_repr = _artifact_repr(flags_path)
    manifest_artifact_repr = _artifact_repr(manifest_path)
    graph_content_hash = graph.get("content_hash", "")

    if status == "UNCLASSIFIED":
        warnings.append(
            {
                "kind": "missing_blast_class",
                "message": f"Rule {args.rule_id} has no blast_class field; refusing to shard",
            }
        )
    elif total_flagged_files == 0:
        status = "EMPTY"
        warnings.append(
            {
                "kind": "no_flags",
                "message": f"No flags for rule {args.rule_id} in 04-flag-index.json",
            }
        )
    else:
        graph_nodes = graph["nodes"]
        forward, reverse = build_edge_index(graph)

        known = [f for f in flagged_files if f in graph_nodes]
        missing = sorted(f for f in flagged_files if f not in graph_nodes)
        flagged_files_missing_from_graph = missing
        for f in missing:
            warnings.append(
                {
                    "kind": "flagged_file_not_in_graph",
                    "file": f,
                    "message": "Flagged file is absent from the knowledge graph; isolated shard",
                }
            )

        if blast_class == BODY_LOCAL:
            shards = _plan_body_local(args.rule_id, known, missing, forward, reverse)

            total_editable = sum(len(s["editable_files"]) for s in shards)
            seen_files: Set[str] = set()
            disjoint = True
            for s in shards:
                s_set = set(s["editable_files"])
                if seen_files & s_set:
                    disjoint = False
                    break
                seen_files |= s_set
            if (
                total_editable != total_flagged_files
                or seen_files != set(flagged_files)
                or not disjoint
            ):
                print("ERROR [SHARD_INVARIANT_VIOLATED]", file=sys.stderr)
                return 2
        else:
            shards = _plan_signature(args.rule_id, flagged_files, reverse)

        for s in shards:
            s["graph_artifact"] = graph_artifact_repr
        for s in shards:
            _entry_points_for_shard(s, rule_flags, warnings)

    shard_count = len(shards)
    warnings.sort(key=lambda w: json.dumps(w, sort_keys=True))

    payload = {
        "schema_version": PLAN_SHARDS_VERSION,
        "run_id": run_id,
        "rule_id": args.rule_id,
        "status": status,
        "blast_class": blast_class,
        "graph_artifact": graph_artifact_repr,
        "graph_content_hash": graph_content_hash,
        "flag_index_artifact": flag_index_artifact_repr,
        "manifest_artifact": manifest_artifact_repr,
        "total_flags": total_flags,
        "total_flagged_files": total_flagged_files,
        "flagged_files_missing_from_graph": flagged_files_missing_from_graph,
        "shard_count": shard_count,
        "shards": shards,
        "warnings": warnings,
    }

    output_path = (
        pathlib.Path(args.output)
        if args.output
        else artifacts_dir / f"05-rule-shards-{args.rule_id}.json"
    )

    if not args.dry_run:
        try:
            _write_json_atomic(output_path, payload)
        except OSError as exc:
            print(f"ERROR [WRITE_FAILED] {exc}", file=sys.stderr)
            return 3

    parallel_safe_display = blast_class == BODY_LOCAL
    print(f"Shard plan written: {output_path}")
    print(
        f"  rule_id={args.rule_id} class={blast_class if blast_class else 'UNCLASSIFIED'} status={status}"
    )
    print(
        f"  shards={shard_count} flagged_files={total_flagged_files} flags={total_flags}"
    )
    print(f"  parallel_safe={'true' if parallel_safe_display else 'false'}")

    if status != "OK" or warnings:
        for w in warnings:
            print(f"WARNING [SHARD_PLAN] {json.dumps(w, sort_keys=True)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
