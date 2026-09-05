"""Comment- and string-literal-aware line classification for Java source.

Every JADE migration tool that greps Java source for a pattern (the
scanner, precision-gate scoring, recipe apply scripts) needs to tell live
code apart from comments and string/char literal content, or it flags
matches that do not exist in compiled output. This module is the single
shared, tested implementation of that classification. Nothing here is
Java-syntax-aware beyond comments and literals: it does not parse
expressions, types, or statements.

Handles: ``//`` line comments, ``/* */`` block comments (including
javadoc ``/** */`` — no special case needed, it is just a block comment
whose body happens to start with an extra ``*``), double-quoted string
literals and single-quoted char literals with backslash-escape
sequences, and the fact that ``//``/``/*`` appearing inside a literal is
just literal content, not a comment. Java block comments do not nest:
a ``/*`` seen while already inside a block comment is ordinary comment
text, and the comment still ends at the first ``*/`` found. Plain
string/char literals cannot legally span a line break in Java, so an
unterminated literal is treated as closed at end of line rather than
swallowing the rest of the file.
"""

from __future__ import annotations

# Per-character lexical states while scanning.
_NORMAL = 0
_LINE_COMMENT = 1
_BLOCK_COMMENT = 2
_STRING = 3
_CHAR = 4

# Per-line classifications (the public vocabulary of classify_lines/is_live_code).
CODE = "code"
COMMENT = "comment"
BLANK = "blank"

# Per-character tags used internally by _char_tags(). Only "code" and
# "comment" are shared with the per-line vocabulary above; the rest are
# finer-grained distinctions strip_comments_and_strings() needs (keep a
# literal's quotes but blank its interior; always keep newlines).
_TAG_CODE = CODE
_TAG_COMMENT = COMMENT
_TAG_STR_QUOTE = "str_quote"
_TAG_STR_BODY = "str_body"
_TAG_WS = "ws"
_TAG_NEWLINE = "newline"

_LIVE_TAGS = (_TAG_CODE, _TAG_STR_QUOTE, _TAG_STR_BODY)


def _char_tags(source: str) -> list[str]:
    """Tag every character of ``source`` with its lexical role.

    Returns a list the same length as ``source``. Each entry is one of:
    "code" (live code outside any literal), "str_quote" (the opening or
    closing quote of a string/char literal), "str_body" (the interior
    of a string/char literal, escape backslashes included), "comment"
    (line or block comment, delimiters included), "ws" (insignificant
    whitespace outside any literal or comment), or "newline".
    """
    tags = [""] * len(source)
    state = _NORMAL
    i = 0
    n = len(source)

    while i < n:
        ch = source[i]

        if ch in ("\n", "\r"):
            # JLS 3.4 line terminators: LF, CR and CRLF. A bare CR ends a line
            # just as LF does, so a // comment on a CR-terminated line must not
            # leak into the next one.
            tags[i] = _TAG_NEWLINE
            # A line comment ends at end of line. A plain string/char
            # literal cannot legally span a line break in Java either,
            # so treat it as closed here rather than let one missing
            # closing quote swallow the rest of the file.
            if state in (_LINE_COMMENT, _STRING, _CHAR):
                state = _NORMAL
            i += 1
            continue

        if state == _NORMAL:
            if ch == "/" and i + 1 < n and source[i + 1] == "/":
                tags[i] = _TAG_COMMENT
                tags[i + 1] = _TAG_COMMENT
                state = _LINE_COMMENT
                i += 2
                continue
            if ch == "/" and i + 1 < n and source[i + 1] == "*":
                tags[i] = _TAG_COMMENT
                tags[i + 1] = _TAG_COMMENT
                state = _BLOCK_COMMENT
                i += 2
                continue
            if ch == '"':
                tags[i] = _TAG_STR_QUOTE
                state = _STRING
                i += 1
                continue
            if ch == "'":
                tags[i] = _TAG_STR_QUOTE
                state = _CHAR
                i += 1
                continue
            tags[i] = _TAG_WS if ch.isspace() else _TAG_CODE
            i += 1
            continue

        if state == _LINE_COMMENT:
            tags[i] = _TAG_COMMENT
            i += 1
            continue

        if state == _BLOCK_COMMENT:
            tags[i] = _TAG_COMMENT
            # Non-nesting: an inner "/*" is just comment text: keep
            # scanning for the first "*/", do not track a nesting depth.
            if ch == "*" and i + 1 < n and source[i + 1] == "/":
                tags[i + 1] = _TAG_COMMENT
                state = _NORMAL
                i += 2
                continue
            i += 1
            continue

        # state in (_STRING, _CHAR)
        closer = '"' if state == _STRING else "'"
        if ch == "\\" and i + 1 < n and source[i + 1] != "\n":
            # Backslash escapes the next character, whatever it is
            # (including the closer or another backslash) — it does not
            # end the literal. Guarded against escaping across a
            # newline so a stray trailing backslash can't shift state
            # tracking onto the wrong line.
            tags[i] = _TAG_STR_BODY
            tags[i + 1] = _TAG_STR_BODY
            i += 2
            continue
        if ch == closer:
            tags[i] = _TAG_STR_QUOTE
            state = _NORMAL
            i += 1
            continue
        tags[i] = _TAG_STR_BODY
        i += 1

    return tags


def _split_java_lines(source: str) -> list[str]:
    """Split *source* into lines on LF, CR and CRLF only, keeping terminators.

    Mirrors JLS 3.4. Every other character str.splitlines() would break on --
    form feed, vertical tab, U+0085, U+2028, U+2029 -- stays inside its line,
    because Java counts those as whitespace, not as line terminators.
    """
    chunks: list[str] = []
    start = 0
    i = 0
    n = len(source)
    while i < n:
        ch = source[i]
        if ch == "\r":
            end = i + 2 if i + 1 < n and source[i + 1] == "\n" else i + 1
            chunks.append(source[start:end])
            start = i = end
            continue
        if ch == "\n":
            chunks.append(source[start : i + 1])
            start = i = i + 1
            continue
        i += 1
    if start < n:
        chunks.append(source[start:])
    return chunks


def classify_lines(source: str) -> list[str]:
    """Classify every line of ``source`` as "code", "comment", or "blank".

    Returns a list the same length as the number of lines in ``source``
    (a trailing newline does not count as an extra blank line, matching
    what an editor or ``wc -l`` reports). A line is "blank" when it is
    empty or all whitespace, "code" when it contains any live code
    (including string/char literal content — a literal is code, not a
    comment), and "comment" only when every non-whitespace character on
    it belongs to a comment.
    """
    tags = _char_tags(source)
    # Split on the line terminators the Java Language Specification defines
    # (JLS 3.4: LF, CR, CRLF) and nothing else. str.splitlines() would also
    # split on form feed, vertical tab and the Unicode separators, which JLS
    # 3.6 treats as ordinary whitespace -- that disagreement would desync
    # these chunks from the character tags below, which only reset state on a
    # real terminator, and report a live line as commented.
    raw_chunks = _split_java_lines(source)
    result = []
    pos = 0
    for chunk in raw_chunks:
        text = chunk.rstrip("\r\n")
        line_tags = tags[pos : pos + len(text)]
        pos += len(chunk)
        if text.strip() == "":
            result.append(BLANK)
        elif any(t in _LIVE_TAGS for t in line_tags):
            result.append(CODE)
        elif any(t == _TAG_COMMENT for t in line_tags):
            result.append(COMMENT)
        else:
            result.append(BLANK)
    return result


def is_live_code(source: str, line_number: int) -> bool:
    """True when line ``line_number`` (1-indexed) of ``source`` is "code".

    Out-of-range line numbers (including anything less than 1) return
    False rather than raising.
    """
    lines = classify_lines(source)
    if line_number < 1 or line_number > len(lines):
        return False
    return lines[line_number - 1] == CODE


def strip_comments_and_strings(source: str) -> str:
    """Blank out comment text and literal interiors with spaces.

    Returns a string with the same number of lines and the same length
    per line as ``source``: every character that is part of a comment
    (delimiters included) or the interior of a string/char literal is
    replaced with a single space, so patterns can be grepped against the
    result without ever matching inside a comment or a literal's text.
    Everything else — real code, whitespace, a literal's own quote
    characters, and line breaks — is left untouched, so line/column
    positions still line up with the original source.
    """
    tags = _char_tags(source)
    out = []
    for ch, tag in zip(source, tags):
        if tag in (_TAG_COMMENT, _TAG_STR_BODY):
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)
