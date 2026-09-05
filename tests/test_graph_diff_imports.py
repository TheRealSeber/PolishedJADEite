"""An added import is not a signature change.

The signature gate asks one question: did this shard change something that files
OUTSIDE the shard depend on? A file's import list cannot answer yes -- imports
are file-local name resolution and no dependent can observe them. Including them
in the change-detection signature made every recipe that has to add an import
(StandardCharsets, for one) trip the gate on every file it touched, with no
declaration having moved.

An import that DOES change meaning by shadowing an in-tree type still shows up,
because that changes the file's resolved edges, and edges are diffed separately.
"""

import importlib.util
import pathlib

SCRIPT = (
    pathlib.Path(__file__).parent.parent
    / ".claude/skills/jade-core-verification/scripts/graph_diff.py"
)


def load():
    spec = importlib.util.spec_from_file_location("graph_diff_imports_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _node(imports, methods=None):
    return {
        "path": "src/A.java",
        "package": "p",
        "imports": list(imports),
        "methods": methods
        if methods is not None
        else [{"name": "f", "return_type": "void", "parameters": [], "line_start": 3, "line_end": 5}],
        "fields": [],
        "line_start": 1,
        "line_end": 40,
    }


def test_added_import_is_not_a_signature_change():
    gd = load()
    before = _node(["java.io.FileWriter"])
    after = _node(["java.io.FileWriter", "java.nio.charset.StandardCharsets"])
    assert gd._node_signature(before) == gd._node_signature(after)


def test_shifted_lines_are_not_a_signature_change():
    gd = load()
    before = _node(["java.io.FileWriter"])
    after = _node(
        ["java.io.FileWriter"],
        methods=[{"name": "f", "return_type": "void", "parameters": [], "line_start": 4, "line_end": 6}],
    )
    assert gd._node_signature(before) == gd._node_signature(after)


def test_a_real_declaration_change_is_still_detected():
    gd = load()
    before = _node(["java.io.FileWriter"])
    after = _node(
        ["java.io.FileWriter"],
        methods=[{"name": "f", "return_type": "String", "parameters": [], "line_start": 3, "line_end": 5}],
    )
    assert gd._node_signature(before) != gd._node_signature(after)


def test_a_new_method_is_still_detected():
    gd = load()
    before = _node(["java.io.FileWriter"])
    after = _node(
        ["java.io.FileWriter"],
        methods=[
            {"name": "f", "return_type": "void", "parameters": [], "line_start": 3, "line_end": 5},
            {"name": "g", "return_type": "void", "parameters": [], "line_start": 7, "line_end": 9},
        ],
    )
    assert gd._node_signature(before) != gd._node_signature(after)
