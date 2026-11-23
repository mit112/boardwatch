"""Text a user reads carries no ticket, decision, design-section or bar reference (T269, T271).

`T43`, `D-498`, `§18` and `B8` name this repository's own tickets, decision log, design spec and
acceptance bars. A user who runs boardwatch has none of them, so a message that cites one reads as
an unfinished sentence. The references belong in a code comment beside the text, where a developer
finds them and a user never does.

Three surfaces, each checked where the user meets it rather than where the text is written:

* every command's `--help` output, which Typer builds from docstrings and option help;
* every string literal in `src/boardwatch` that is not a docstring or a bare string statement,
  which covers the funnel's notes and captions, error messages, alerts and report lines;
* the committed web bundle's string literals, which carry the web app's copy.

The first two walk the real program, so a command or message added tomorrow is checked without
anyone listing it here. Docstrings of non-command code are developer text and are exempt on
purpose; a command's own docstring is its help text and is covered by the first check.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest
from typer.core import TyperCommand, TyperGroup
from typer.main import get_command
from typer.testing import CliRunner

import boardwatch
from boardwatch.cli.app import app

# A ticket (`T43`), a decision (`D-498`, `D-P3-13`), a design-spec section (`§18`), a program
# phase (`P6`, `P1a`) or an acceptance bar (`B8`). `\b` keeps an ISO time such as `06:00T12` and
# a word such as `P2P` from matching.
INTERNAL_REF = re.compile(r"\b(?:T\d{1,4}|D-\d{2,4}|B[1-8]|P\d+[a-z]?|R-\d+)\b|§")

PACKAGE_ROOT = Path(boardwatch.__file__).resolve().parent
BUNDLE_ASSETS = PACKAGE_ROOT / "web" / "static" / "assets"

FIX = (
    "reword the text for a user who has never seen this repository, and keep the reference as a "
    "code comment beside it"
)


def internal_refs(text: str) -> list[str]:
    return [match.group(0) for match in INTERNAL_REF.finditer(text)]


def string_literals(source: str) -> Iterator[tuple[int, str]]:
    """Every string literal that is program text, with its line.

    A bare string statement is a docstring or an attribute docstring (`NAME = 1` then a string on
    the next line): developer text that no code path ever prints. Everything else is data the
    program can hand to a user, whether or not today's caller does, so it is checked.
    """
    tree = ast.parse(source)
    docstrings = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            yield node.lineno, node.value


def _commands(
    command: TyperCommand | TyperGroup, path: tuple[str, ...] = ()
) -> Iterator[tuple[str, ...]]:
    """Every command path, groups included: `eligibility --help` is help a user reads too."""
    yield path
    if isinstance(command, TyperGroup):
        for name, child in command.commands.items():
            yield from _commands(cast("TyperCommand | TyperGroup", child), (*path, name))


def _snippet(text: str, ref: str) -> str:
    flat = " ".join(text.split())
    at = flat.index(ref)
    return flat[max(0, at - 50) : at + len(ref) + 30]


# --- the scanner itself: each check needs a case it must refuse, or a silent scanner passes ---


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("under B8's bar of 20", ["B8"]),
        ("a silent degrade (D-006)", ["D-006"]),
        ("never re-judged (T43), see D-498", ["T43", "D-498"]),
        ("forbidden by §18 in a locator", ["§"]),
        ("this is P6 item 6 and P1a", ["P6", "P1a"]),
        ("the D-P3-13 rule", ["P3"]),
        ("run R-12 recorded it", ["R-12"]),
        # Plain text and shapes that only look like a reference.
        ("2026-08-14T06:00:04Z", []),
        ("P2P and T-shirt and DT-1 and B9 and BD-12", []),
        ("a render tool is unavailable", []),
    ],
)
def test_the_pattern_matches_a_reference_and_nothing_else(text: str, expected: list[str]) -> None:
    assert internal_refs(text) == expected


def test_a_docstring_is_exempt_and_a_message_is_not() -> None:
    source = '''
"""Module note (T1)."""
LIMIT = 2
"""Attribute docstring (D-123)."""

def f() -> str:
    """Function docstring (T2)."""
    return "message (T3)"

g = ["note (D-456)", f"{1} f-string (§7)"]
'''
    assert [text for _, text in string_literals(source)] == [
        "message (T3)",
        "note (D-456)",
        " f-string (§7)",
    ]


# --- the real surfaces ---


def test_no_command_help_names_an_internal_reference() -> None:
    root = cast(TyperGroup, get_command(app))
    runner = CliRunner()
    walked = 0
    offenders: list[str] = []
    for path in _commands(root):
        result = runner.invoke(app, [*path, "--help"], terminal_width=200)
        assert result.exit_code == 0, f"`{' '.join(path)} --help` failed: {result.output}"
        walked += 1
        offenders += [
            f"`boardwatch {' '.join(path)} --help`: ...{_snippet(result.output, ref)}..."
            for ref in dict.fromkeys(internal_refs(result.output))
        ]
    # A walk that found no commands would pass for the wrong reason.
    assert walked > 90
    assert not offenders, f"{FIX}:\n" + "\n".join(offenders)


def test_no_program_string_names_an_internal_reference() -> None:
    offenders: list[str] = []
    scanned = 0
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        for line, text in string_literals(path.read_text(encoding="utf-8")):
            scanned += 1
            offenders += [
                f"{path.relative_to(PACKAGE_ROOT.parent)}:{line}: ...{_snippet(text, ref)}..."
                for ref in dict.fromkeys(internal_refs(text))
            ]
    assert scanned > 5000
    assert not offenders, f"{FIX}:\n" + "\n".join(offenders)


def test_the_web_bundle_names_no_internal_reference() -> None:
    bundles = sorted(BUNDLE_ASSETS.glob("*.js"))
    assert bundles, f"no committed bundle under {BUNDLE_ASSETS}"
    offenders = [
        f"{bundle.name}: ...{_snippet(text, ref)}..."
        for bundle in bundles
        for text in [bundle.read_text(encoding="utf-8")]
        for ref in dict.fromkeys(internal_refs(text))
    ]
    assert not offenders, f"{FIX} in web/src, then run `make web`:\n" + "\n".join(offenders)
