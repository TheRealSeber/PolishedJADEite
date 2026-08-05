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

from schema import (
    KnowledgeGraph, GraphNode, MethodInfo, FieldInfo,
    ConstructorInfo, Parameter,
)
from tree_sitter_java_queries import (
    get_parser, parse_file, extract_class_info, extract_methods,
    extract_fields, extract_constructors, extract_calls, extract_imports,
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
    return java_files


def parse_files(java_files: list, parser, lang) -> dict:
    """Stage 2: Parse each file with tree-sitter, extract declarations."""
    nodes = {}
    parse_errors = []
    for full, rel in java_files:
        try:
            tree, src = parse_file(parser, full)
            root = tree.root_node

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
                    package=_extract_package(rel),
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
            }

        except Exception as e:
            parse_errors.append((rel, str(e)))
            nodes[rel] = {
                "node": _create_partial_node(rel),
                "calls": [], "imports": [],
                "fields": [], "implements": [], "extends": "",
            }

    for rel, err in parse_errors:
        print(f"WARNING: parse issue in {rel}: {err}", file=sys.stderr)

    return nodes


def resolve_graph(nodes: dict) -> KnowledgeGraph:
    """Stage 3: Cross-reference to build edges."""
    kg = KnowledgeGraph()

    fqn_to_rel = {}
    pkg_to_rels = {}
    for rel, data in nodes.items():
        node = data["node"]
        parts = rel.replace(".java", "").split("/")
        pkg = ".".join(parts[:-1]) if len(parts) > 1 else ""
        cls = parts[-1]
        fqn = f"{pkg}.{cls}" if pkg else cls
        fqn_to_rel[fqn] = rel
        pkg_to_rels.setdefault(pkg, set()).add(rel)
        kg.add_node(node)

    for rel, data in nodes.items():
        for imp in data.get("imports", []):
            target_rel = _resolve_import(imp, fqn_to_rel, pkg_to_rels)
            if target_rel and target_rel != rel and target_rel in nodes:
                kg.add_import_edge(rel, target_rel)

    for rel, data in nodes.items():
        ext_val = data.get("extends", "")
        if ext_val:
            if isinstance(ext_val, list):
                ext_val = ext_val[0] if ext_val else ""
            if ext_val:
                target_rel = _resolve_type(ext_val, nodes, rel, fqn_to_rel, pkg_to_rels)
                if target_rel and target_rel in nodes:
                    kg.add_extends_edge(rel, target_rel)

    for rel, data in nodes.items():
        for imp_iface in data.get("implements", []):
            if imp_iface:
                target_rel = _resolve_type(imp_iface, nodes, rel, fqn_to_rel, pkg_to_rels)
                if target_rel and target_rel in nodes:
                    kg.add_implements_edge(rel, target_rel)

    for rel, data in nodes.items():
        for fd in data.get("fields", []):
            if isinstance(fd, dict):
                ftype = fd.get("type", "")
                target_rel = _resolve_type(ftype, nodes, rel, fqn_to_rel, pkg_to_rels)
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
                target_rel = _resolve_type(obj, nodes, rel, fqn_to_rel, pkg_to_rels)
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
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

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


def _resolve_import(imp: str, fqn_to_rel: dict, pkg_to_rels: dict):
    if imp.endswith(".*"):
        return None
    if imp in fqn_to_rel:
        return fqn_to_rel[imp]
    short = imp.split(".")[-1]
    for fqn, rel in fqn_to_rel.items():
        if fqn.endswith("." + short):
            return rel
    return None


def _resolve_type(type_name: str, nodes: dict, from_rel: str, fqn_to_rel: dict, pkg_to_rels: dict):
    if not type_name:
        return None
    if type_name in fqn_to_rel:
        return fqn_to_rel[type_name]
    from_pkg = _extract_package(from_rel)
    candidate_fqn = f"{from_pkg}.{type_name}" if from_pkg else type_name
    if candidate_fqn in fqn_to_rel:
        return fqn_to_rel[candidate_fqn]
    for fqn, rel in fqn_to_rel.items():
        if fqn.endswith("." + type_name):
            return rel
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
    nodes = parse_files(java_files, ts_parser, lang)
    print(f"  Parsed {len(nodes)} files")

    print("Stage 3/4: RESOLVE -- cross-referencing edges")
    kg = resolve_graph(nodes)
    stats = kg.compute_stats()
    print(f"  Nodes: {stats['total_files']}, Edges: {stats['total_edges']}")

    print("Stage 4/4: SERIALIZE -- writing artifact")
    serialize_graph(kg, args.artifacts_dir, run_id)

    elapsed = time.time() - t0
    print(f"Done in {elapsed:.1f}s")

    has_errors = stats["total_files"] < len(java_files)
    sys.exit(1 if has_errors else 0)


if __name__ == "__main__":
    main()
