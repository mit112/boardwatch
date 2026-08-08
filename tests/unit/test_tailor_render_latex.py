from __future__ import annotations

from boardwatch.tailor.render import parse_bullets
from boardwatch.tailor.render.latex import escape, unescape


def test_escape_latex_specials():
    assert escape("40% & $5 #1 a_b {x} ~ ^ c\\d") == r"40\% \& \$5 \#1 a\_b \{x\} \textasciitilde{} \textasciicircum{} c\textbackslash{}d"


def test_escape_collapses_whitespace():
    assert escape("a   b\n c") == "a b c"


def test_escape_unescape_roundtrip():
    # includes backslash/tilde/caret to exercise unescape's longest-first ordering (re-review 2 minor)
    for s in ["Cut p99 latency 40%", "C/C++ & .NET", "a_b {x} $y$ #z", "path\\to ~file ^2"]:
        assert unescape(escape(s)) == " ".join(s.split())


def test_parse_bullets_brace_depth_and_unescape():
    src = (
        r"\resumeItem{Improved startup by 40\% via caching}" "\n"
        r"\resumeItem{Nested \emph{group} stays balanced}" "\n"
        r"\section{Skills}"
    )
    assert parse_bullets(src) == [
        "Improved startup by 40% via caching",
        "Nested \\emph{group} stays balanced",
    ]


def test_parse_bullets_handles_escaped_literal_braces():
    # re-review 2 M2: the fixture MUST carry a LONE/unbalanced brace. The earlier draft used a
    # BALANCED `{ … }` pair, so deleting the load-bearing `if c == "\\": pos += 2` skip still
    # extracted correctly — the test could not fail for its own claim. With ONE `{` and no matching
    # `}`, removing the skip makes depth never return to 0 at the wrapper's close, so the extraction
    # over-runs into `\resumeItemListEnd` and the assertion goes red.
    from boardwatch.tailor.render.latex import escape
    body = escape("Config uses { only and 100% coverage")  # lone '{' -> escape() -> \{
    src = f"\\resumeItem{{{body}}}\n\\resumeItemListEnd"
    assert parse_bullets(src) == ["Config uses { only and 100% coverage"]
