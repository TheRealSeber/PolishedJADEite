"""tree-sitter-java query patterns and AST extraction helpers for tree-sitter 0.26+."""

import tree_sitter_java as tsjava
from tree_sitter import Language, Parser, Query, QueryCursor


def get_java_language():
    return Language(tsjava.language())


def get_parser():
    lang = get_java_language()
    return Parser(lang), lang


# Query strings
CLASS_QUERY = """
(class_declaration) @class
"""

INTERFACE_QUERY = """
(interface_declaration) @iface
"""

ENUM_QUERY = """
(enum_declaration) @enum
"""

ANNOTATION_QUERY = """
(annotation_type_declaration) @annotation
"""

METHOD_QUERY = """
(method_declaration) @method
"""

FIELD_QUERY = """
(field_declaration) @field
"""

CONSTRUCTOR_QUERY = """
(constructor_declaration) @constructor
"""

IMPORT_QUERY = """
(import_declaration
  (scoped_identifier) @import
)
"""

CALL_QUERY = """
(method_invocation
  object: (identifier)? @object
  name: (identifier) @method_name
) @call
"""


def parse_file(parser, filepath):
    """Parse a single .java file, returning (tree, source_bytes)."""
    with open(filepath, "rb") as f:
        source = f.read()
    tree = parser.parse(source)
    return tree, source


def _run_query(lang, tree_root, query_str, group_by_node_type):
    """Run a tree-sitter query and group captures by a parent node type.
    
    Returns a dict keyed by the grouping node's id, each value a dict of capture_name -> [values].
    """
    q = Query(lang, query_str)
    cursor = QueryCursor(q)
    matches = cursor.matches(tree_root)
    
    results = {}
    for pattern_idx, captures in matches:
        # Find the grouping node (e.g., "class", "method", "field")
        group_node = None
        group_data = {}
        
        for cap_name, nodes in captures.items():
            if cap_name == group_by_node_type:
                group_node = nodes[0]
            else:
                group_data[cap_name] = nodes
        
        if group_node is not None:
            results[group_node.id] = {"node": group_node, "captures": group_data}
    
    return results


def extract_imports(tree_root, source_bytes, lang):
    """Extract import strings from parsed tree."""
    q = Query(lang, IMPORT_QUERY)
    cursor = QueryCursor(q)
    matches = cursor.matches(tree_root)
    imports = []
    for pattern_idx, captures in matches:
        for cap_name, nodes in captures.items():
            if cap_name == "import":
                imports.append(source_bytes[nodes[0].start_byte:nodes[0].end_byte].decode("utf-8"))
    return imports


def _child_text(child, source_bytes):
    return source_bytes[child.start_byte:child.end_byte].decode("utf-8")


def extract_class_info(tree_root, source_bytes, lang):
    """Extract class/interface/enum/annotation declarations."""
    results = []
    for query_str, kind in [
        (CLASS_QUERY, "class"),
        (INTERFACE_QUERY, "interface"),
        (ENUM_QUERY, "enum"),
        (ANNOTATION_QUERY, "annotation"),
    ]:
        q = Query(lang, query_str)
        cursor = QueryCursor(q)
        matches = cursor.matches(tree_root)
        
        for pattern_idx, captures in matches:
            for cap_name, nodes in captures.items():
                node = nodes[0]
                info = {"kind": kind, "line_start": node.start_point[0] + 1, "line_end": node.end_point[0] + 1}
                
                for child in node.children:
                    if child.type == "identifier":
                        info["name"] = _child_text(child, source_bytes)
                    elif child.type == "superclass":
                        for grandchild in child.children:
                            if grandchild.type == "type_identifier":
                                info["superclass"] = _child_text(grandchild, source_bytes)
                    elif child.type == "super_interfaces":
                        impls = []
                        for grandchild in child.children:
                            if grandchild.type == "type_list":
                                for type_child in grandchild.children:
                                    if type_child.type == "type_identifier":
                                        impls.append(_child_text(type_child, source_bytes))
                        if impls:
                            info["implements"] = impls
                results.append(info)
    return results


def extract_methods(tree_root, source_bytes, lang):
    """Extract method declarations with signatures."""
    results = []
    q = Query(lang, METHOD_QUERY)
    cursor = QueryCursor(q)
    matches = cursor.matches(tree_root)
    
    for pattern_idx, captures in matches:
        for cap_name, nodes in captures.items():
            node = nodes[0]
            method = {
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "modifiers": [],
                "annotations": [],
                "parameters": [],
                "exceptions": [],
            }
            
            children = list(node.children)
            seen_params = False
            seen_throws = False
            for i, child in enumerate(children):
                if child.type == "modifiers":
                    mod_text = _child_text(child, source_bytes)
                    toks = mod_text.split()
                    method["modifiers"] = [t for t in toks if not t.startswith("@")]
                    method["annotations"] = [t for t in toks if t.startswith("@")]
                elif child.type in ("type_identifier", "generic_type", "array_type",
                                     "void_type", "integral_type", "floating_point_type",
                                     "boolean_type", "scoped_type_identifier") and not seen_params:
                    method["return_type"] = _child_text(child, source_bytes)
                elif child.type == "identifier" and not seen_params:
                    method["name"] = _child_text(child, source_bytes)
                elif child.type == "formal_parameters":
                    method["parameters"] = _parse_parameters(_child_text(child, source_bytes))
                    seen_params = True
                elif child.type == "throws":
                    method["exceptions"] = _parse_exceptions(_child_text(child, source_bytes))
                    seen_throws = True
            
            if method.get("name"):
                results.append(method)
    return results


def extract_constructors(tree_root, source_bytes, lang):
    """Extract constructor declarations."""
    results = []
    q = Query(lang, CONSTRUCTOR_QUERY)
    cursor = QueryCursor(q)
    matches = cursor.matches(tree_root)
    
    for pattern_idx, captures in matches:
        for cap_name, nodes in captures.items():
            node = nodes[0]
            ctor = {
                "line_start": node.start_point[0] + 1,
                "modifiers": [],
                "parameters": [],
                "exceptions": [],
            }
            
            seen_params = False
            for child in node.children:
                if child.type == "modifiers":
                    mod_text = _child_text(child, source_bytes)
                    ctor["modifiers"] = [t for t in mod_text.split() if t]
                elif child.type == "identifier" and not seen_params:
                    ctor["name"] = _child_text(child, source_bytes)
                elif child.type == "formal_parameters":
                    ctor["parameters"] = _parse_parameters(_child_text(child, source_bytes))
                    seen_params = True
                elif child.type == "throws":
                    ctor["exceptions"] = _parse_exceptions(_child_text(child, source_bytes))
            
            if ctor.get("name"):
                results.append(ctor)
    return results


def extract_fields(tree_root, source_bytes, lang):
    """Extract field declarations with types."""
    results = []
    q = Query(lang, FIELD_QUERY)
    cursor = QueryCursor(q)
    matches = cursor.matches(tree_root)
    
    for pattern_idx, captures in matches:
        for cap_name, nodes in captures.items():
            node = nodes[0]
            field = {"modifiers": [], "annotations": []}
            seen_type = False
            for child in node.children:
                if child.type == "modifiers":
                    mod_text = _child_text(child, source_bytes)
                    toks = mod_text.split()
                    field["modifiers"] = [t for t in toks if not t.startswith("@")]
                    field["annotations"] = [t for t in toks if t.startswith("@")]
                elif child.type in ("type_identifier", "generic_type", "array_type",
                                     "integral_type", "floating_point_type",
                                     "boolean_type", "scoped_type_identifier") and not seen_type:
                    field["type"] = _child_text(child, source_bytes)
                    seen_type = True
                elif child.type == "variable_declarator":
                    for gc in child.children:
                        if gc.type == "identifier":
                            field["name"] = _child_text(gc, source_bytes)
            if field.get("name") and field.get("type"):
                results.append(field)
    return results


def extract_calls(tree_root, source_bytes, lang):
    """Extract method invocation call sites."""
    results = []
    q = Query(lang, CALL_QUERY)
    cursor = QueryCursor(q)
    matches = cursor.matches(tree_root)
    
    for pattern_idx, captures in matches:
        call_info = {}
        for cap_name, nodes in captures.items():
            node = nodes[0]
            val = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
            if cap_name == "call":
                call_info["line"] = node.start_point[0] + 1
            elif cap_name == "object":
                call_info["object"] = val
            elif cap_name == "method_name":
                call_info["method_name"] = val
        if call_info.get("method_name"):
            results.append(call_info)
    return results


def _parse_exceptions(throws_text):
    """Parse 'throws Foo, Bar' text into list of exception type names."""
    inner = throws_text.replace("throws", "").strip()
    if not inner:
        return []
    return [t.strip() for t in inner.split(",") if t.strip()]


def _parse_parameters(params_text):
    """Parse (Type name, Type name) into list of {name, type} dicts."""
    inner = params_text.strip("()").strip()
    if not inner:
        return []
    params = []
    for param in inner.split(","):
        param = param.strip()
        if not param:
            continue
        parts = param.rsplit(None, 1)
        if len(parts) == 2:
            params.append({"type": parts[0], "name": parts[1]})
        elif len(parts) == 1:
            params.append({"type": parts[0], "name": ""})
    return params
