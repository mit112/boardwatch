"""Tier B renderer marking: `reworded` bullets get a comment, payloads stay untouched.

Companion to test_tailor_render.py — proves the default `reworded=frozenset()` leaves
Tier A's emit() output byte-identical (Task 5's regression guard for the renderer half).
"""

from __future__ import annotations

from boardwatch.tailor.model import Bullet, Entry, Resume
from boardwatch.tailor.render import parse_bullets
from boardwatch.tailor.render.typst import TypstRenderer


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
    assert parse_bullets(src) == ["Alpha", "Beta"]


def test_emit_default_is_byte_identical_to_no_kwarg_call() -> None:
    r = _resume()
    assert TypstRenderer().emit(r) == TypstRenderer().emit(r, reworded=frozenset())
