import importlib.util
import pathlib

import pytest


ROOT = pathlib.Path(__file__).parents[1]
_LOGGER_JAVA = (
    ROOT
    / "migration-runs/jade-1.6-to-1.7/workspace/src/jade/src/jade/util/Logger.java"
)


def load_java_source():
    path = (
        ROOT
        / ".claude/skills/java-migration-skill-registry/shared/lib/java_source.py"
    )
    spec = importlib.util.spec_from_file_location("java_source_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def java_source():
    return load_java_source()


def test_line_comment_at_end_of_code_line(java_source):
    source = 'int x = 5; // set x\n'
    assert java_source.classify_lines(source) == ["code"]
    assert java_source.is_live_code(source, 1) is True


def test_block_comment_single_line(java_source):
    source = "/* just a comment */\n"
    assert java_source.classify_lines(source) == ["comment"]
    assert java_source.is_live_code(source, 1) is False


def test_block_comment_multi_line(java_source):
    source = (
        "before();\n"
        "/* start\n"
        "   middle, still inside\n"
        "end */ after();\n"
    )
    assert java_source.classify_lines(source) == [
        "code",  # before();
        "comment",  # /* start
        "comment",  # middle line, wholly inside the comment
        "code",  # comment closes then "after();" is live code
    ]


def test_line_comment_marker_inside_string_literal_is_not_a_comment(java_source):
    source = 'String s = "http://example.com";\n'
    assert java_source.classify_lines(source) == ["code"]
    assert java_source.is_live_code(source, 1) is True


def test_block_comment_marker_inside_string_literal_is_not_a_comment(java_source):
    source = 'String s = "/* not a comment */";\n'
    assert java_source.classify_lines(source) == ["code"]
    assert java_source.is_live_code(source, 1) is True


def test_string_literal_with_escaped_quote_does_not_end_early(java_source):
    # If the escaped quote were mistaken for the closing quote, the
    # trailing `);` would read as live code starting mid-literal instead
    # of the whole line being one code line — either way this line must
    # classify "code", but the point of this test is that the *second*,
    # real closing quote is what ends the literal.
    source = 'String s = "abc\\"def"; // trailing comment\n'
    assert java_source.classify_lines(source) == ["code"]


def test_char_literal_containing_a_double_quote(java_source):
    source = "char c = '\"';\n"
    assert java_source.classify_lines(source) == ["code"]


def test_blank_line(java_source):
    assert java_source.classify_lines("\n") == ["blank"]


def test_empty_source_has_zero_lines(java_source):
    # An empty file has zero lines (matching `wc -l` and editors), not
    # one phantom blank line.
    assert java_source.classify_lines("") == []
    assert java_source.is_live_code("", 1) is False


def test_whitespace_only_line(java_source):
    assert java_source.classify_lines("   \t  \n") == ["blank"]


def test_javadoc_comment(java_source):
    source = (
        "/**\n"
        " * Does a thing.\n"
        " */\n"
        "void doThing() {}\n"
    )
    assert java_source.classify_lines(source) == [
        "comment",
        "comment",
        "comment",
        "code",
    ]


def test_nested_looking_block_comment_does_not_nest(java_source):
    # Java block comments do not nest: the first "*/" closes the
    # comment, and the "/*" that looks nested inside is just text.
    source = "/* outer /* inner */ liveCode();\n"
    assert java_source.classify_lines(source) == ["code"]
    assert java_source.is_live_code(source, 1) is True


def test_is_live_code_out_of_range_is_false(java_source):
    source = "int x = 1;\n"
    assert java_source.is_live_code(source, 0) is False
    assert java_source.is_live_code(source, 2) is False
    assert java_source.is_live_code(source, -5) is False


def test_strip_comments_and_strings_preserves_shape(java_source):
    source = (
        'int x = 5; // set x\n'
        '/* block\n'
        'comment */\n'
        'String s = "keep // this /* out";\n'
    )
    stripped = java_source.strip_comments_and_strings(source)
    original_lines = source.split("\n")
    stripped_lines = stripped.split("\n")
    assert len(stripped_lines) == len(original_lines)
    for original, blanked in zip(original_lines, stripped_lines):
        assert len(blanked) == len(original)
    assert "set x" not in stripped
    assert "block" not in stripped
    assert "keep // this /* out" not in stripped
    assert "int x = 5;" in stripped
    # The literal's quotes survive; only its interior is blanked.
    assert 'String s = "' in stripped
    assert stripped.count('"') == source.count('"')


def test_strip_comments_and_strings_does_not_touch_live_code(java_source):
    source = "if (x > 0) { doThing(); }\n"
    assert java_source.strip_comments_and_strings(source) == source


def test_logger_java_regression_lines_are_classified_as_comment(java_source):
    # Regression fixture for D1: lines 341, 370 and 560 of the real
    # Logger.java sit inside //#J2ME_INCLUDE_BEGIN.../*..*/-style block
    # comments used by JADE's preprocessor, but were previously flagged
    # by pattern scans as live code. This module must always classify
    # them as "comment".
    assert _LOGGER_JAVA.exists(), f"missing fixture file: {_LOGGER_JAVA}"
    source = _LOGGER_JAVA.read_text(encoding="utf-8")
    lines = java_source.classify_lines(source)
    for line_number in (341, 370, 560):
        assert lines[line_number - 1] == "comment", (
            f"Logger.java:{line_number} expected comment, got "
            f"{lines[line_number - 1]!r}"
        )
        assert java_source.is_live_code(source, line_number) is False


def test_logger_java_line_count_matches_wc_l(java_source):
    source = _LOGGER_JAVA.read_text(encoding="utf-8")
    lines = java_source.classify_lines(source)
    # Logger.java has 695 lines per `wc -l`; classify_lines must not
    # invent a phantom extra line for the trailing newline.
    assert len(lines) == 695


def test_form_feed_is_whitespace_not_a_line_terminator():
    """JLS 3.6 counts form feed as whitespace; only LF/CR/CRLF end a line.

    str.splitlines() disagrees, and letting it drive the line split desynced
    the chunks from the character tags, reporting live code as commented.
    """
    mod = load_java_source()
    source = "/* start\x0c still comment */\nint live = 1;\n"

    assert mod.classify_lines(source) == ["comment", "code"]
    assert mod.is_live_code(source, 2) is True


def test_bare_cr_ends_a_line_comment():
    """A // comment on a CR-terminated line must not swallow the rest."""
    mod = load_java_source()
    source = "// a note\rint live = 1;\rint live2 = 2;\r"

    assert mod.classify_lines(source) == ["comment", "code", "code"]
    assert mod.is_live_code(source, 2) is True
    assert mod.is_live_code(source, 3) is True


def test_crlf_counts_as_one_terminator():
    mod = load_java_source()
    source = "// a note\r\nint live = 1;\r\n"

    assert mod.classify_lines(source) == ["comment", "code"]
    assert mod.is_live_code(source, 2) is True
