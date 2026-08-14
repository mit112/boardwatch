"""A derived check for `_projection_diagnostic`'s "no absolute path in any diagnostic" rule.

`_projection_diagnostic`'s own docstring (`cli/projection_cmd.py`) hand-lists exactly which
`ProjectionIssue` members it sanitizes (`BUNDLE_UNREADABLE`, `SHELL_SOURCE_UNREADABLE`) and hand-
asserts that every other reachable call site never carries a leak. That list is the one place on
this branch where a guarantee lives only in a docstring, not behind a check — the same shape the
sanitization map itself would have if this file merely restated it as a second hand-written list.

Instead, the set of members to verify is DISCOVERED from the five modules `project_pool` reaches
(`pool.py`, `declaration.py`, `contract.py`, `grammar.py`, `shell.py` — see
`_projection_diagnostic`'s own docstring for why exactly these five), via `ast`: every
`raise_violation(...)` call sitting inside an `except` clause that catches `OSError` is a site
whose message COULD embed `OSError.__str__`'s own absolute-path payload, whether or not the code
at that site actually chooses to use it. For each member so discovered, a real fault is triggered
through the real production function (never a hand-built `ProjectionViolation`), and the resulting
diagnostic is asserted not to carry the tmp path.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

from boardwatch.cli.projection_cmd import _projection_diagnostic
from boardwatch.projection.declaration import load_declaration
from boardwatch.projection.errors import ProjectionError
from boardwatch.projection.shell import load_shell

SRC = Path(__file__).resolve().parents[2] / "src" / "boardwatch" / "projection"

#: The five modules `project_pool` (the only path `project` calls) reaches — see
#: `cli/projection_cmd.py`'s own `_projection_diagnostic` docstring.
_MODULES = ("pool.py", "declaration.py", "contract.py", "grammar.py", "shell.py")


def _handler_catches_os_error(handler: ast.ExceptHandler) -> bool:
    node = handler.type
    if node is None:
        return False
    candidates = node.elts if isinstance(node, ast.Tuple) else [node]
    return any(isinstance(n, ast.Name) and n.id == "OSError" for n in candidates)


def _raise_violation_members(body: list[ast.stmt]) -> set[str]:
    """Every `ProjectionIssue.<MEMBER>` named as the first argument of a `raise_violation(...)`
    call anywhere in `body` — including nested blocks, so an `if` inside the handler is covered
    too."""
    members: set[str] = set()
    holder = ast.Module(body=body, type_ignores=[])
    for node in ast.walk(holder):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "raise_violation"
            and node.args
            and isinstance(node.args[0], ast.Attribute)
        ):
            members.add(node.args[0].attr)
    return members


def _os_error_catching_members() -> set[str]:
    """Every `ProjectionIssue` member raised from inside an `except` clause that catches
    `OSError`, across the five modules — discovered from source, never hand-listed."""
    found: set[str] = set()
    for filename in _MODULES:
        tree = ast.parse((SRC / filename).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                for handler in node.handlers:
                    if _handler_catches_os_error(handler):
                        found |= _raise_violation_members(handler.body)
    return found


def test_the_derivation_is_not_vacuous() -> None:
    """A derivation that silently found nothing would make every assertion below pass by never
    running at all. Two is the minimum expected today: `declaration.py`'s `DECLARATION_UNREADABLE`
    arm and `shell.py`'s `SHELL_SOURCE_UNREADABLE` arm both catch `OSError`."""
    members = _os_error_catching_members()
    assert len(members) >= 2, members


def _trigger_declaration_unreadable(tmp_path: Path) -> ProjectionError:
    path = tmp_path / "projection.yaml"
    path.write_text("projection_version: 1\n", encoding="utf-8")
    path.chmod(0o000)
    try:
        with pytest.raises(ProjectionError) as exc_info:
            load_declaration(path)
    finally:
        path.chmod(0o644)
    return exc_info.value


def _trigger_shell_source_unreadable(tmp_path: Path) -> ProjectionError:
    path = tmp_path / "master_resume.yaml"
    path.write_text("header: []\neducation: []\n", encoding="utf-8")
    path.chmod(0o000)
    try:
        with pytest.raises(ProjectionError) as exc_info:
            load_shell(path)
    finally:
        path.chmod(0o644)
    return exc_info.value


#: One real fault-trigger per member the AST scan can find today. If the scan ever finds a NEW
#: `OSError`-catching member, `test_every_discovered_member_has_a_registered_trigger` fails until
#: a trigger is registered for it here — the derivation must not silently stop covering something.
_TRIGGERS = {
    "DECLARATION_UNREADABLE": _trigger_declaration_unreadable,
    "SHELL_SOURCE_UNREADABLE": _trigger_shell_source_unreadable,
}


def test_every_discovered_member_has_a_registered_trigger() -> None:
    assert _os_error_catching_members() == set(_TRIGGERS)


@pytest.mark.skipif(os.name != "posix", reason="mode bits do not deny reads on Windows")
@pytest.mark.parametrize("member_name", sorted(_TRIGGERS))
def test_no_os_error_catching_member_leaks_an_absolute_path(
    member_name: str, tmp_path: Path
) -> None:
    exc = _TRIGGERS[member_name](tmp_path)
    assert exc.violation.issue.name == member_name

    diagnostic = _projection_diagnostic(exc.violation)
    where = diagnostic.details.get("where", "")
    haystack = f"{diagnostic.message} {where}"
    assert str(tmp_path) not in haystack, haystack
