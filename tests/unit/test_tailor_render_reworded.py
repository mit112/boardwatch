"""Tier B renderer marking: `reworded` bullets get a comment, payloads stay untouched.

Companion to test_tailor_render.py — proves the default `reworded=frozenset()` leaves
Tier A's emit() output byte-identical (Task 5's regression guard for the renderer half).
"""

from __future__ import annotations

import re

from boardwatch.tailor.model import Bullet, Entry, Resume
from boardwatch.tailor.render.typst import TypstRenderer

# `render.parse_bullets` is now scoped to the LaTeX `\resumeItem{}` firewall (see
# test_tailor_render_latex.py). This typst-specific test exercises typst's own
# `#resume-bullet(...)` escape/extract fidelity, so it uses the extractor typst was built
# against rather than the shared (now LaTeX-only) production function.
_TYPST_BULLET = re.compile(r'#resume-bullet\("((?:[^"\\]|\\.)*)"\)')


def _typst_bullets(source: str) -> list[str]:
    return [m.group(1).replace('\\"', '"').replace("\\\\", "\\") for m in _TYPST_BULLET.finditer(source)]


def _resume() -> Resume:
    return Resume(
        header=["h"],
        education=[],
        skill_groups=[],
        entries=[
            Entry(
                entry_id="e1",
                heading="Work",
                bullets=[Bullet(bullet_id="b1", text="Alpha"), Bullet(bullet_id="b2", text="Beta")],
            )
        ],
    )


def test_emit_default_has_no_reworded_comment() -> None:
    src = TypstRenderer().emit(_resume())
    assert "reworded (Tier B)" not in src


def test_emit_marks_reworded_bullets_without_touching_payloads() -> None:
    src = TypstRenderer().emit(_resume(), reworded=frozenset({"b1"}))
    assert "reworded (Tier B)" in src
    # The firewall payloads are unchanged — both bullets still parse.
    assert _typst_bullets(src) == ["Alpha", "Beta"]


def test_emit_default_is_byte_identical_to_no_kwarg_call() -> None:
    r = _resume()
    assert TypstRenderer().emit(r) == TypstRenderer().emit(r, reworded=frozenset())
