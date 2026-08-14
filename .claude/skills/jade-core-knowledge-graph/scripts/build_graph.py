#!/usr/bin/env python3
"""build_graph.py -- Build Knowledge Graph from Java workspace (tree-sitter 0.26+).

4-stage pipeline:
  1. SCAN: Walk workspace, collect .java paths
  2. PARSE: tree-sitter AST per file, extract declarations
  3. RESOLVE: Cross-reference imports, calls, type refs into edges
  4. SERIALIZE: Write 03.5-knowledge-graph.json

Exit codes: 0=success, 1=partial, 2=failure, 3=env-error
"""

import argparse
import json
import os
import sys
import time
import tempfile

from schema import (
    KnowledgeGraph, GraphNode, MethodInfo, FieldInfo,
    ConstructorInfo, Parameter,
)
from tree_sitter_java_queries import (
    get_parser, parse_file, extract_class_info, extract_methods,
    extract_fields, extract_constructors, extract_calls, extract_imports, extract_package,
)


def scan_workspace(workspace_path: str) -> list:
    """Stage 1: Walk workspace, collect all .java file paths (relative to workspace)."""
    java_files = []
    for root, dirs, files in os.walk(workspace_path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.endswith(".java"):
                full = os.path.join(root, f)
                rel = os.path.relpath(full, workspace_path).replace("\\", "/")
                java_files.append((full, rel))
    return sorted(java_files, key=lambda item: item[1])


def parse_files(java_files: list, parser, lang, return_diagnostics=False):
    """Stage 2: Parse each file with tree-sitter, extract declarations."""
    nodes = {}
    parse_errors = []
    for full, rel in java_files:
        try:
            tree, src = parse_file(parser, full)
            root = tree.root_node
            parse_issue = _find_parse_issue(root)

            class_infos = extract_class_info(root, src, lang)
            methods_raw = extract_methods(root, src, lang)
            fields_raw = extract_fields(root, src, lang)
            ctors_raw = extract_constructors(root, src, lang)
            calls_raw = extract_calls(root, src, lang)
            imports = extract_imports(root, src, lang)

            node = None
            if class_infos:
                main = class_infos[0]
                node = GraphNode(
                    path=rel,
                    package=extract_package(root, src),
                    class_name=main.get("name", ""),
                    kind=main.get("kind", "class"),
                    extends=main.get("superclass", ""),
                    implements=main.get("implements", []),
                    methods=[_build_method_info(m) for m in methods_raw],
                    fields=[_build_field_info(f) for f in fields_raw],
                    constructors=[_build_constructor_info(c) for c in ctors_raw],
                    imports=imports,
                )
            else:
                parse_errors.append((rel, "no class/interface found"))
                node = _create_partial_node(rel)
                node.imports = imports

            nodes[rel] = {
                "node": node,
                "calls": calls_raw,
                "imports": imports,
                "fields": fields_raw,
                "implements": node.implements,
                "extends": node.extends,
                "package": node.package,
            }
            if parse_issue:
                parse_errors.append((rel, parse_issue))

        except Exception as e:
            parse_errors.append((rel, str(e)))
            nodes[rel] = {
                "node": _create_partial_node(rel),
                "calls": [], "imports": [],
                "fields": [], "implements": [], "extends": "",
            }

    for rel, err in parse_errors:
        print(f"WARNING: parse issue in {rel}: {err}", file=sys.stderr)

    if return_diagnostics:
        return nodes, [{"kind": "parse_error", "file": rel, "message": err}
                       for rel, err in sorted(parse_errors)]
    return nodes


def resolve_graph(nodes: dict, diagnostics=None) -> KnowledgeGraph:
    """Stage 3: Cross-reference to build edges."""
    kg = KnowledgeGraph(diagnostics=diagnostics)

    fqn_to_rel = {}
    pkg_to_rels = {}
    for rel, data in nodes.items():
        node = data["node"]
        pkg = node.package
        cls = node.class_name
        fqn = f"{pkg}.{cls}" if pkg else cls
        if fqn in fqn_to_rel:
            kg.diagnostics.append({"kind": "ambiguous_declaration", "symbol": fqn,
                                   "files": sorted([fqn_to_rel[fqn], rel])})
            fqn_to_rel[fqn] = None
        elif fqn not in fqn_to_rel:
            fqn_to_rel[fqn] = rel
        pkg_to_rels.setdefault(pkg, set()).add(rel)
        kg.add_node(node)

    for rel, data in nodes.items():
        for imp in data.get("imports", []):
            target_rels, reason = _resolve_import(imp, fqn_to_rel, pkg_to_rels, rel, nodes, kg)
            for target_rel in target_rels:
                if target_rel != rel and target_rel in nodes:
                    kg.add_import_edge(rel, target_rel, reason)

    for rel, data in nodes.items():
        ext_val = data.get("extends", "")
        if ext_val:
            if isinstance(ext_val, list):
                ext_val = ext_val[0] if ext_val else ""
            if ext_val:
                target_rel = _resolve_type(ext_val, nodes, rel, fqn_to_rel, pkg_to_rels, kg)
                if target_rel and target_rel in nodes:
                    kg.add_extends_edge(rel, target_rel)

    for rel, data in nodes.items():
        for imp_iface in data.get("implements", []):
            if imp_iface:
                target_rel = _resolve_type(imp_iface, nodes, rel, fqn_to_rel, pkg_to_rels, kg)
                if target_rel and target_rel in nodes:
                    kg.add_implements_edge(rel, target_rel)

    for rel, data in nodes.items():
        for fd in data.get("fields", []):
            if isinstance(fd, dict):
                ftype = fd.get("type", "")
                target_rel = _resolve_type(ftype, nodes, rel, fqn_to_rel, pkg_to_rels, kg)
                if target_rel and target_rel in nodes:
                    kg.add_type_ref_edge(rel, target_rel, field=fd.get("name", ""), type_name=ftype)

    for rel, data in nodes.items():
        node = data["node"]
        for call in data.get("calls", []):
            if not isinstance(call, dict):
                continue
            obj = call.get("object")
            mname = call.get("method_name", "")
            if not mname:
                continue
            target_rel = None
            if obj:
                target_rel = _resolve_type(obj, nodes, rel, fqn_to_rel, pkg_to_rels, kg)
            if target_rel and target_rel in nodes:
                kg.add_call_edge(rel, "", target_rel, mname, call.get("line", 0))

    return kg


def serialize_graph(kg: KnowledgeGraph, artifacts_dir: str, run_id: str):
    """Stage 4: Write 03.5-knowledge-graph.json."""
    os.makedirs(artifacts_dir, exist_ok=True)
    output_path = os.path.join(artifacts_dir, "03.5-knowledge-graph.json")

    stats = kg.compute_stats()
    output = {
        "run_id": run_id,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "stats": stats,
        **kg.to_dict(),
    }
    fd, tmp_path = tempfile.mkstemp(prefix=".knowledge-graph-", suffix=".tmp", dir=artifacts_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, output_path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    print(f"Knowledge graph written: {output_path}")
    print(f"Stats: {stats}")


def _extract_package(rel: str) -> str:
    parts = rel.split("/")
    if len(parts) > 1:
        return ".".join(parts[:-1])
    return ""


def _build_method_info(m: dict) -> MethodInfo:
    if not isinstance(m, dict):
        return MethodInfo(name="")
    params = [Parameter(**p) if isinstance(p, dict) else Parameter(name=str(p), type="")
              for p in m.get("parameters", [])]
    return MethodInfo(
        name=m.get("name", ""),
        modifiers=m.get("modifiers", []),
        return_type=m.get("return_type", ""),
        parameters=params,
        exceptions=m.get("exceptions", []),
        annotations=m.get("annotations", []),
        line_start=m.get("line_start", 0),
        line_end=m.get("line_end", 0),
    )


def _build_field_info(f: dict) -> FieldInfo:
    if not isinstance(f, dict):
        return FieldInfo(name="", type="")
    return FieldInfo(
        name=f.get("name", ""),
        type=f.get("type", ""),
        modifiers=f.get("modifiers", []),
        annotations=f.get("annotations", []),
    )


def _build_constructor_info(c: dict) -> ConstructorInfo:
    if not isinstance(c, dict):
        return ConstructorInfo(name="")
    params = [Parameter(**p) if isinstance(p, dict) else Parameter(name=str(p), type="")
              for p in c.get("parameters", [])]
    return ConstructorInfo(
        name=c.get("name", ""),
        modifiers=c.get("modifiers", []),
        parameters=params,
        exceptions=c.get("exceptions", []),
        line_start=c.get("line_start", 0),
    )


def _create_partial_node(rel: str) -> GraphNode:
    return GraphNode(
        path=rel,
        package=_extract_package(rel),
        class_name=os.path.basename(rel).replace(".java", ""),
    )


def _resolve_import(imp: str, fqn_to_rel: dict, pkg_to_rels: dict, from_rel: str, nodes: dict, kg=None):
    if imp.endswith(".*"):
        pkg = imp[:-2]
        candidates = sorted(pkg_to_rels.get(pkg, set()))
        # A wildcard import creates one edge per declaration in that package.
        if not candidates and kg is not None:
            kg.diagnostics.append({"kind": "unresolved_import", "file": from_rel, "symbol": imp})
        return candidates, "wildcard"
    if imp in fqn_to_rel and fqn_to_rel[imp]:
        return [fqn_to_rel[imp]], "direct"
    if imp in fqn_to_rel and kg is not None:
        kg.diagnostics.append({"kind": "ambiguous_import", "file": from_rel, "symbol": imp})
    return [], "unresolved"


def _resolve_type(type_name: str, nodes: dict, from_rel: str, fqn_to_rel: dict, pkg_to_rels: dict, kg=None):
    if not type_name:
        return None
    if type_name in fqn_to_rel and fqn_to_rel[type_name]:
        return fqn_to_rel[type_name]
    from_pkg = nodes[from_rel]["node"].package
    candidate_fqn = f"{from_pkg}.{type_name}" if from_pkg else type_name
    if candidate_fqn in fqn_to_rel:
        return fqn_to_rel[candidate_fqn]
    candidates = sorted(rel for fqn, rel in fqn_to_rel.items()
                        if rel and fqn.endswith("." + type_name))
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1 and kg is not None:
        kg.diagnostics.append({"kind": "ambiguous_symbol", "file": from_rel,
                               "symbol": type_name, "candidates": candidates})
    return None


def _find_parse_issue(root):
    if root.has_error:
        return "tree-sitter reported parse errors"
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "ERROR" or node.is_missing:
            return "tree-sitter error node found"
        stack.extend(node.children)
    return None


def main():
    parser = argparse.ArgumentParser(description="Build Java Knowledge Graph")
    parser.add_argument("--workspace", required=True, help="Path to workspace root")
    parser.add_argument("--artifacts-dir", required=True, help="Path to artifacts directory")
    args = parser.parse_args()

    if not os.path.isdir(args.workspace):
        print(f"FATAL: workspace not found: {args.workspace}", file=sys.stderr)
        sys.exit(3)

    try:
        ts_parser, lang = get_parser()
    except Exception as e:
        print(f"FATAL: tree-sitter init failed: {e}", file=sys.stderr)
        sys.exit(3)

    run_id = os.path.basename(os.path.dirname(args.artifacts_dir)) or "unknown"

    t0 = time.time()

    print(f"Stage 1/4: SCAN -- workspace: {args.workspace}")
    java_files = scan_workspace(args.workspace)
    print(f"  Found {len(java_files)} .java files")

    print("Stage 2/4: PARSE -- tree-sitter AST extraction")
    nodes, diagnostics = parse_files(java_files, ts_parser, lang, return_diagnostics=True)
    print(f"  Parsed {len(nodes)} files")

    print("Stage 3/4: RESOLVE -- cross-referencing edges")
    kg = resolve_graph(nodes, diagnostics)
    kg.source_identity = {
        "workspace": os.path.abspath(args.workspace),
        "file_count": len(java_files),
    }
    stats = kg.compute_stats()
    print(f"  Nodes: {stats['total_files']}, Edges: {stats['total_edges']}")

    print("Stage 4/4: SERIALIZE -- writing artifact")
    serialize_graph(kg, args.artifacts_dir, run_id)

    elapsed = time.time() - t0
    print(f"Done in {elapsed:.1f}s")

    has_errors = bool(kg.diagnostics)
    sys.exit(1 if has_errors else 0)


if __name__ == "__main__":
    main()
