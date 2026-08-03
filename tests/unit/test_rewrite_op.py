from __future__ import annotations

import pydantic
import pytest

from boardwatch.tailor.apply import ApplyError, apply_plan
from boardwatch.tailor.equivalences import load_equivalences
from boardwatch.tailor.model import Bullet, Entry, Resume
from boardwatch.tailor.plan import Rewrite, TailorPlan


def _resume() -> Resume:
    return Resume(
        header=["A"],
        education=[],
        skill_groups=[],
        entries=[
            Entry(
                entry_id="e1",
                heading="Work",
                bullets=[Bullet(bullet_id="b1", text="Built the thing in Python")],
            )
        ],
    )


def test_rewrite_replaces_bullet_text() -> None:
    out = apply_plan(
        _resume(),
        TailorPlan(ops=(Rewrite(bullet_id="b1", text="Shipped the thing in Python"),)),
        load_equivalences(),
    )
    assert out.entries[0].bullets[0].text == "Shipped the thing in Python"


def test_rewrite_unknown_bullet_raises() -> None:
    with pytest.raises(ApplyError):
        apply_plan(
            _resume(),
            TailorPlan(ops=(Rewrite(bullet_id="nope", text="x"),)),
            load_equivalences(),
        )


def test_rewrite_is_frozen() -> None:
    with pytest.raises(pydantic.ValidationError):
        Rewrite(bullet_id="b1", text="x").text = "y"  # type: ignore[misc]
