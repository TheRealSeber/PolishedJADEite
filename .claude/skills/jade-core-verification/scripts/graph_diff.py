#!/usr/bin/env python3
"""graph_diff.py -- Deterministic structural diff between two knowledge graph artifacts.

Compares nodes by path + declaration signature and edges by canonical
``(from, to, type)`` tuples. Writes a versioned report atomically
(tmp + fsync + rename). The canonical report content contains no timestamps,
so repeated runs over the same inputs produce byte-identical output.

Exit codes:
  0 = success (no warnings)
  1 = attention needed (warnings present, e.g. identity mismatch / graph diagnostics)
  2 = structural error (malformed JSON, missing nodes/edges, invalid report output)
  3 = missing file / environment error
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

GRAPH_DIFF_VERSION = 1

EDGE_TYPES = ("imports", "extends", "implements", "calls", "type_refs")

# Line metadata is volatile across rebuilds (comment/code insertions shift lines
# without changing declarations); exclude it from the change-detection signature.
_VOLATILE_NODE_KEYS = frozenset({"line_start", "line_end"})


def _canonical_dump(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _strip_volatile(value):
    """Recursively drop volatile line metadata from a node structure."""
    if isinstance(value, dict):
        return {
            k: _strip_volatile(v)
            for k, v in value.items()
            if k not in _VOLATILE_NODE_KEYS
        }
    if isinstance(value, list):
        return [_strip_volatile(v) for v in value]
    return value


def _node_signature(node: dict) -> str:
    """Stable signature for change detection of a single node."""
    return _canonical_dump(_strip_volatile(node))


def _identity(graph: dict) -> dict:
    source_identity = graph.get("source_identity")
    if not isinstance(source_identity, dict):
        source_identity = {}
    return {
        "schema_version": graph.get("schema_version"),
        "source_identity": dict(source_identity),
        "content_hash": graph.get("content_hash"),
    }


def _nodes(graph: dict) -> dict:
    nodes = graph.get("nodes")
    return nodes if isinstance(nodes, dict) else {}


def _edge_tuples(graph: dict):
    """Canonical, deduplicated (from, to, type) tuples for all edges."""
    result = set()
    edges = graph.get("edges")
    if not isinstance(edges, dict):
        return result
    for etype in EDGE_TYPES:
        for e in edges.get(etype, []):
            if not isinstance(e, dict):
                continue
            frm = e.get("from")
            to = e.get("to")
            if frm and to:
                result.add((frm, to, etype))
    return result


def _edge_objects(tuples) -> list:
    return [
        {"from": frm, "to": to, "type": etype}
        for frm, to, etype in sorted(tuples)
    ]


def _reverse_adjacency(graph: dict) -> dict:
    """Reverse-edge index keyed by target file; value is sorted (from, etype) pairs."""
    index = {}
    edges = graph.get("edges")
    if not isinstance(edges, dict):
        return index
    for etype in EDGE_TYPES:
        for e in edges.get(etype, []):
            if isinstance(e, dict) and e.get("from") and e.get("to"):
                index.setdefault(e["to"], []).append((e["from"], etype))
    for target in index:
        index[target].sort()
    return index


def _impact_paths(changed_nodes, graph: dict, seen: set) -> list:
    """Sorted explanation paths from each changed node to its transitive dependents.

    Mirrors the KnowledgeGraph.query_rule_scope path shape: each entry is
    {"file", "path", "reasons"} where path[0] is the changed node and reasons
    name the edge types traversed. Sorted by file/path/reasons for determinism.
    """
    reverse = _reverse_adjacency(graph)
    paths = []
    for target in sorted(changed_nodes):
        queue = [(target, [target], [])]
        visited = {target}
        while queue:
            node, path, reasons = queue.pop(0)
            for dependent, etype in reverse.get(node, []):
                if dependent in visited:
                    continue
                visited.add(dependent)
                next_path = path + [dependent]
                next_reasons = reasons + [etype]
                key = (dependent, tuple(next_path), tuple(next_reasons))
                if key in seen:
                    continue
                seen.add(key)
                paths.append(
                    {"file": dependent, "path": next_path, "reasons": next_reasons}
                )
                queue.append((dependent, next_path, next_reasons))
    return paths


def compute_diff(before_graph: dict, after_graph: dict) -> dict:
    """Compute a deterministic graph diff report between two graph artifacts."""
    before_nodes = _nodes(before_graph)
    after_nodes = _nodes(after_graph)
    before_edges = _edge_tuples(before_graph)
    after_edges = _edge_tuples(after_graph)

    added_nodes = sorted(set(after_nodes) - set(before_nodes))
    removed_nodes = sorted(set(before_nodes) - set(after_nodes))

    shared = sorted(set(before_nodes) & set(after_nodes))
    changed_nodes = [
        path
        for path in shared
        if _node_signature(before_nodes[path]) != _node_signature(after_nodes[path])
    ]

    added_edges = _edge_objects(after_edges - before_edges)
    removed_edges = _edge_objects(before_edges - after_edges)

    before_id = _identity(before_graph)
    after_id = _identity(after_graph)

    warnings = []
    before_key = {k: v for k, v in before_id.items() if k != "content_hash"}
    after_key = {k: v for k, v in after_id.items() if k != "content_hash"}
    if before_key != after_key:
        warnings.append(
            {
                "kind": "identity_mismatch",
                "message": "before and after graphs report different source identity",
                "before": before_key,
                "after": after_key,
            }
        )
    for side, graph in (("before", before_graph), ("after", after_graph)):
        diag = graph.get("diagnostics")
        if isinstance(diag, dict) and any(diag.values()):
            warnings.append(
                {
                    "kind": "graph_diagnostics",
                    "side": side,
                    "buckets": {k: len(v) for k, v in diag.items() if v},
                }
            )

    seen_paths = set()
    impact_paths = []
    if changed_nodes or removed_nodes:
        present_after = [p for p in changed_nodes if p in after_nodes]
        impact_paths.extend(_impact_paths(present_after, after_graph, seen_paths))
        present_before = [p for p in removed_nodes if p in before_nodes]
        impact_paths.extend(_impact_paths(present_before, before_graph, seen_paths))
    impact_paths = sorted(
        impact_paths, key=lambda p: (p["file"], p["path"], p["reasons"])
    )

    return {
        "graph_diff_version": GRAPH_DIFF_VERSION,
        "before_identity": before_id,
        "after_identity": after_id,
        "added_nodes": added_nodes,
        "removed_nodes": removed_nodes,
        "added_edges": added_edges,
        "removed_edges": removed_edges,
        "changed_nodes": changed_nodes,
        "impact_paths": impact_paths,
        "warnings": warnings,
    }


def _load_graph(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"graph artifact must be a JSON object: {path}")
    if not isinstance(data.get("nodes"), dict):
        raise ValueError(f"graph artifact missing 'nodes' map: {path}")
    if not isinstance(data.get("edges"), dict):
        raise ValueError(f"graph artifact missing 'edges' map: {path}")
    return data


def _write_json_atomic(path: str, payload: dict) -> None:
    path = os.path.abspath(path)
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".graph-diff-", suffix=".tmp", dir=directory)
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Diff two knowledge graph artifacts")
    parser.add_argument("--before", required=True, help="Path to before graph JSON")
    parser.add_argument("--after", required=True, help="Path to after graph JSON")
    parser.add_argument("--output", required=True, help="Path to write diff report JSON")
    args = parser.parse_args(argv)

    for label, path in (("before", args.before), ("after", args.after)):
        if not os.path.isfile(path):
            print(f"ERROR [GRAPH_NOT_FOUND] {label}: {path}", file=sys.stderr)
            return 3

    try:
        before = _load_graph(args.before)
        after = _load_graph(args.after)
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        print(f"ERROR [GRAPH_MALFORMED] {exc}", file=sys.stderr)
        return 2

    report = compute_diff(before, after)

    try:
        _write_json_atomic(args.output, report)
    except OSError as exc:
        print(f"ERROR [WRITE_FAILED] {exc}", file=sys.stderr)
        return 3

    print(f"Graph diff written: {args.output}")
    print(
        f"  added_nodes={len(report['added_nodes'])} "
        f"removed_nodes={len(report['removed_nodes'])}"
    )
    print(
        f"  added_edges={len(report['added_edges'])} "
        f"removed_edges={len(report['removed_edges'])}"
    )
    print(
        f"  changed_nodes={len(report['changed_nodes'])} "
        f"impact_paths={len(report['impact_paths'])}"
    )
    if report["warnings"]:
        print(f"  warnings={len(report['warnings'])}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())