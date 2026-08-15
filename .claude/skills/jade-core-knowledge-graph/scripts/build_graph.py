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
    extract_local_variables,
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
            locals_raw = extract_local_variables(root, src, lang)
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
                parse_errors.append((rel, "no class/interface found", 1, 1))
                node = _create_partial_node(rel)
                node.imports = imports

            nodes[rel] = {
                "node": node,
                "calls": calls_raw,
                "locals": locals_raw,
                "methods": methods_raw,
                "imports": imports,
                "fields": fields_raw,
                "implements": node.implements,
                "extends": node.extends,
                "package": node.package,
            }
            if parse_issue:
                message, line, column = parse_issue
                parse_errors.append((rel, message, line, column))

        except Exception as e:
            parse_errors.append((rel, str(e), 1, 1))
            nodes[rel] = {
                "node": _create_partial_node(rel),
                "calls": [], "imports": [],
                "fields": [], "locals": [], "methods": [], "implements": [], "extends": "",
            }

    for rel, err, _, _ in parse_errors:
        print(f"WARNING: parse issue in {rel}: {err}", file=sys.stderr)

    if return_diagnostics:
        return nodes, [{"kind": "parse_error", "file": rel, "message": err,
                        "line": line, "column": column}
                       for rel, err, line, column in sorted(parse_errors)]
    return nodes


def resolve_graph(nodes: dict, diagnostics=None) -> KnowledgeGraph:
    """Stage 3: Cross-reference to build edges."""
    kg = KnowledgeGraph(diagnostics=diagnostics)

    fqn_to_rel = {}
    declarations = {}
    pkg_to_rels = {}
    receiver_types_by_scope = {}
    for rel, data in nodes.items():
        field_receiver_types = {
            field.get("name"): field.get("type") for field in data.get("fields", [])
            if isinstance(field, dict) and field.get("name")
        }
        for method in data.get("methods", []):
            if isinstance(method, dict):
                method_name = method.get("name", "")
                scoped = receiver_types_by_scope.setdefault((rel, method_name), dict(field_receiver_types))
                scoped.update({param.get("name"): param.get("type")
                               for param in method.get("parameters", [])
                               if isinstance(param, dict) and param.get("name")})
        for local in data.get("locals", []):
            if isinstance(local, dict) and local.get("name"):
                receiver_types_by_scope.setdefault((rel, local.get("method", "")), dict(field_receiver_types))[
                    local["name"]
                ] = local.get("type")
        receiver_types_by_scope.setdefault((rel, ""), field_receiver_types)
        node = data["node"]
        pkg = node.package
        cls = node.class_name
        fqn = f"{pkg}.{cls}" if pkg else cls
        declarations.setdefault(fqn, []).append(rel)
        pkg_to_rels.setdefault(pkg, set()).add(rel)
        kg.add_node(node)

    ambiguous_fqns = set()
    short_name_files = {}
    for fqn, files in declarations.items():
        short_name_files.setdefault(fqn.rsplit(".", 1)[-1], []).extend(files)
        if len(files) == 1:
            fqn_to_rel[fqn] = files[0]
        else:
            ambiguous_fqns.add(fqn)
            kg.add_diagnostic({"kind": "ambiguous_declaration", "symbol": fqn,
                               "files": sorted(files)})
    ambiguous_short_names = {name for name, files in short_name_files.items() if len(files) > 1}

    wildcard_ambiguities = {}
    for rel, data in nodes.items():
        exports = {}
        for imp in data.get("imports", []):
            if not imp.endswith(".*"):
                continue
            pkg = imp[:-2]
            for candidate in sorted(pkg_to_rels.get(pkg, set())):
                name = nodes[candidate]["node"].class_name
                exports.setdefault(name, []).append((pkg, candidate))
        for name, entries in exports.items():
            if len({pkg for pkg, _ in entries}) > 1:
                candidates = sorted(candidate for _, candidate in entries)
                wildcard_ambiguities.setdefault(rel, set()).add(name)
                kg.add_diagnostic({"kind": "ambiguous_symbol", "file": rel,
                                   "symbol": name, "candidates": candidates})

    for rel, data in nodes.items():
        for imp in data.get("imports", []):
            target_rels, reason = _resolve_import(
                imp, fqn_to_rel, pkg_to_rels, rel, nodes, kg, ambiguous_fqns,
                wildcard_ambiguities.get(rel, set()))
            for target_rel in target_rels:
                if target_rel != rel and target_rel in nodes:
                    kg.add_import_edge(rel, target_rel, reason)

    for rel, data in nodes.items():
        ext_val = data.get("extends", "")
        if ext_val:
            if isinstance(ext_val, list):
                ext_val = ext_val[0] if ext_val else ""
            if ext_val:
                target_rel = _resolve_type(ext_val, nodes, rel, fqn_to_rel, pkg_to_rels, kg,
                                           ambiguous_fqns, ambiguous_short_names)
                if target_rel and target_rel in nodes:
                    kg.add_extends_edge(rel, target_rel)

    for rel, data in nodes.items():
        for imp_iface in data.get("implements", []):
            if imp_iface:
                target_rel = _resolve_type(imp_iface, nodes, rel, fqn_to_rel, pkg_to_rels, kg,
                                           ambiguous_fqns, ambiguous_short_names)
                if target_rel and target_rel in nodes:
                    kg.add_implements_edge(rel, target_rel)

    for rel, data in nodes.items():
        for fd in data.get("fields", []):
            if isinstance(fd, dict):
                ftype = fd.get("type", "")
                target_rel = _resolve_type(ftype, nodes, rel, fqn_to_rel, pkg_to_rels, kg,
                                           ambiguous_fqns, ambiguous_short_names)
                if target_rel and target_rel in nodes:
                    kg.add_type_ref_edge(rel, target_rel, field=fd.get("name", ""), type_name=ftype)

    for rel, data in nodes.items():
        for method in data.get("methods", []):
            if not isinstance(method, dict):
                continue
            method_name = method.get("name", "")
            type_refs = [(method.get("return_type", ""), f"method:{method_name}:return")]
            type_refs.extend((param.get("type", ""), f"method:{method_name}:parameter:{param.get('name', '')}")
                             for param in method.get("parameters", []) if isinstance(param, dict))
            type_refs.extend((exception, f"method:{method_name}:throws")
                             for exception in method.get("exceptions", []))
            for type_name, field_name in type_refs:
                target_rel = _resolve_type(type_name, nodes, rel, fqn_to_rel, pkg_to_rels, kg,
                                           ambiguous_fqns, ambiguous_short_names)
                if target_rel and target_rel in nodes:
                    kg.add_type_ref_edge(rel, target_rel, field=field_name, type_name=type_name)

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
                receiver_types = receiver_types_by_scope.get((rel, call.get("caller_method", "")), {})
                receiver_type = receiver_types.get(obj, obj)
                target_rel = _resolve_type(receiver_type, nodes, rel, fqn_to_rel, pkg_to_rels, kg, ambiguous_fqns,
                                           ambiguous_short_names, report_unresolved=False)
                if target_rel is None:
                    kg.add_diagnostic({"kind": "unresolved_receiver_call", "file": rel,
                                       "line": call.get("line", 0), "receiver": obj,
                                       "method": mname, "caller_method": call.get("caller_method", "")})
            else:
                target_rel = rel
            if target_rel and target_rel in nodes:
                kg.add_call_edge(rel, call.get("caller_method", ""), target_rel, mname, call.get("line", 0))

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


def _resolve_import(imp: str, fqn_to_rel: dict, pkg_to_rels: dict, from_rel: str, nodes: dict, kg=None,
                    ambiguous_fqns=None, ambiguous_wildcards=None):
    if imp.endswith(".*"):
        pkg = imp[:-2]
        candidates = sorted(pkg_to_rels.get(pkg, set()))
        # A wildcard import creates one edge per declaration in that package.
        if not candidates and kg is not None:
            kg.add_diagnostic({"kind": "unresolved_import", "file": from_rel, "symbol": imp})
        by_name = {}
        for candidate in candidates:
            name = nodes[candidate]["node"].class_name
            by_name.setdefault(name, []).append(candidate)
        resolved = []
        for name, files in sorted(by_name.items()):
            if name in (ambiguous_wildcards or set()):
                continue
            if len(files) > 1:
                if kg is not None:
                    kg.add_diagnostic({"kind": "ambiguous_symbol", "file": from_rel,
                                       "symbol": f"{pkg}.{name}", "candidates": sorted(files)})
            else:
                resolved.extend(files)
        return sorted(resolved), "wildcard"
    if imp in fqn_to_rel and fqn_to_rel[imp]:
        return [fqn_to_rel[imp]], "direct"
    if imp in (ambiguous_fqns or set()) and kg is not None:
        kg.add_diagnostic({"kind": "ambiguous_import", "file": from_rel, "symbol": imp})
    elif not _is_external_reference(imp, nodes.get(from_rel, {}).get("node")) and kg is not None:
        kg.add_diagnostic({"kind": "unresolved_import", "file": from_rel, "symbol": imp})
    return [], "unresolved"


def _resolve_type(type_name: str, nodes: dict, from_rel: str, fqn_to_rel: dict, pkg_to_rels: dict, kg=None,
                  ambiguous_fqns=None, ambiguous_short_names=None, report_unresolved=True):
    if not type_name:
        return None
    base_type = type_name.split("<", 1)[0].strip().replace("[]", "")
    if base_type in fqn_to_rel and fqn_to_rel[base_type]:
        return fqn_to_rel[base_type]
    explicit_import = next((imp for imp in nodes[from_rel].get("imports", [])
                            if not imp.endswith(".*") and imp.rsplit(".", 1)[-1] == base_type), None)
    if explicit_import:
        if explicit_import in fqn_to_rel and fqn_to_rel[explicit_import]:
            return fqn_to_rel[explicit_import]
        if explicit_import in (ambiguous_fqns or set()):
            if kg is not None:
                kg.add_diagnostic({"kind": "ambiguous_symbol", "file": from_rel,
                                   "symbol": base_type,
                                   "candidates": sorted(_declaration_candidates(explicit_import, ambiguous_fqns, nodes))})
            return None
    from_pkg = nodes[from_rel]["node"].package
    candidate_fqn = f"{from_pkg}.{base_type}" if from_pkg else base_type
    if candidate_fqn in fqn_to_rel:
        return fqn_to_rel[candidate_fqn]
    if (candidate_fqn in (ambiguous_fqns or set()) or
            base_type in (ambiguous_fqns or set()) or
            base_type in (ambiguous_short_names or set())):
        if kg is not None:
            kg.add_diagnostic({"kind": "ambiguous_symbol", "file": from_rel,
                               "symbol": base_type,
                               "candidates": sorted(_declaration_candidates(base_type, ambiguous_fqns, nodes))})
        return None
    candidates = sorted(rel for fqn, rel in fqn_to_rel.items()
                        if rel and fqn.endswith("." + base_type))
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1 and kg is not None:
        kg.add_diagnostic({"kind": "ambiguous_symbol", "file": from_rel,
                           "symbol": base_type, "candidates": candidates})
    elif report_unresolved and not candidates and kg is not None and not _is_external_reference(base_type, nodes[from_rel]["node"]):
        kg.add_diagnostic({"kind": "unresolved_type", "file": from_rel, "symbol": base_type})
    return None


def _declaration_candidates(type_name, ambiguous_fqns, nodes):
    return [rel for rel, data in nodes.items()
            if data["node"].class_name == type_name or
            f"{data['node'].package}.{data['node'].class_name}" == type_name]


def _is_external_reference(name, node):
    if name.startswith(("java.", "javax.")):
        return True
    if name in {"String", "Object", "Class", "Integer", "Long", "Boolean", "Exception", "RuntimeException"}:
        return True
    imports = getattr(node, "imports", []) if node else []
    return any(imp.startswith(("java.", "javax.")) and
               (imp.endswith("." + name) or imp.endswith(".*")) for imp in imports)


def _find_parse_issue(root):
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "ERROR" or node.is_missing:
            return ("tree-sitter error node found", node.start_point[0] + 1,
                    node.start_point[1] + 1)
        stack.extend(node.children)
    if root.has_error:
        return ("tree-sitter reported parse errors", root.start_point[0] + 1,
                root.start_point[1] + 1)
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
    kg.source = {
        "workspace_root": os.path.abspath(args.workspace),
        "java_files": len(java_files),
        "workspace": os.path.abspath(args.workspace),
        "java_file_count": len(java_files),
    }
    kg.source_identity = kg.source.copy()
    stats = kg.compute_stats()
    print(f"  Nodes: {stats['total_files']}, Edges: {stats['total_edges']}")

    print("Stage 4/4: SERIALIZE -- writing artifact")
    serialize_graph(kg, args.artifacts_dir, run_id)

    elapsed = time.time() - t0
    print(f"Done in {elapsed:.1f}s")

    has_errors = any(kg.diagnostics.values())
    sys.exit(1 if has_errors else 0)


if __name__ == "__main__":
    main()
