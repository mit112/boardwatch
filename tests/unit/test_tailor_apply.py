from __future__ import annotations

import pytest

from boardwatch.tailor.apply import ApplyError, apply_plan, whole_token_sub
from boardwatch.tailor.equivalences import load_equivalences
from boardwatch.tailor.model import Bullet, Entry, Resume
from boardwatch.tailor.plan import Delete, EquivalenceSwap, Reorder, Select, TailorPlan

TBL = load_equivalences()


def R() -> Resume:
    return Resume(
        header=["h"],
        education=[],
        skill_groups=[],
        entries=[
            Entry(
                entry_id="e1",
                heading="H",
                bullets=[
                    Bullet(bullet_id="b1", text="Shipped JS at scale"),
                    Bullet(bullet_id="b2", text="Ran Postgres in prod"),
                    Bullet(bullet_id="b3", text="Wrote docs"),
                ],
            )
        ],
    )


def test_delete_removes_bullet() -> None:
    out = apply_plan(R(), TailorPlan(ops=(Delete(bullet_id="b3"),)), TBL)
    assert [b.bullet_id for b in out.entries[0].bullets] == ["b1", "b2"]


def test_reorder_within_entry() -> None:
    out = apply_plan(
        R(), TailorPlan(ops=(Reorder(entry_id="e1", order=("b2", "b1", "b3")),)), TBL
    )
    assert [b.bullet_id for b in out.entries[0].bullets] == ["b2", "b1", "b3"]


def test_equivalence_swap_whole_token() -> None:
    out = apply_plan(
        R(),
        TailorPlan(ops=(EquivalenceSwap(bullet_id="b1", from_phrase="JS", to_phrase="JavaScript"),)),
        TBL,
    )
    assert out.entries[0].bullets[0].text == "Shipped JavaScript at scale"


def test_swap_not_in_table_rejected() -> None:
    with pytest.raises(ApplyError):
        apply_plan(
            R(),
            TailorPlan(ops=(EquivalenceSwap(bullet_id="b1", from_phrase="JS", to_phrase="Senior"),)),
            TBL,
        )


def test_swap_not_whole_token_rejected() -> None:
    # "JSON" must not be mangled by a "JS" swap.
    r = Resume(
        header=["h"],
        education=[],
        skill_groups=[],
        entries=[
            Entry(
                entry_id="e1",
                heading="H",
                bullets=[Bullet(bullet_id="b1", text="Parsed JSON quickly")],
            )
        ],
    )
    with pytest.raises(ApplyError):
        apply_plan(
            r,
            TailorPlan(ops=(EquivalenceSwap(bullet_id="b1", from_phrase="JS", to_phrase="JavaScript"),)),
            TBL,
        )


def test_unknown_id_rejected() -> None:
    with pytest.raises(ApplyError):
        apply_plan(R(), TailorPlan(ops=(Delete(bullet_id="zzz"),)), TBL)


def test_select_keep_true_unknown_bullet_id_rejected() -> None:
    with pytest.raises(ApplyError):
        apply_plan(R(), TailorPlan(ops=(Select(bullet_id="zzz", keep=True),)), TBL)


def test_reorder_unknown_entry_id_rejected() -> None:
    with pytest.raises(ApplyError):
        apply_plan(R(), TailorPlan(ops=(Reorder(entry_id="zzz", order=()),)), TBL)


def test_equivalence_swap_unknown_bullet_id_rejected() -> None:
    with pytest.raises(ApplyError):
        apply_plan(
            R(),
            TailorPlan(
                ops=(EquivalenceSwap(bullet_id="zzz", from_phrase="JS", to_phrase="JavaScript"),)
            ),
            TBL,
        )


def test_reorder_must_cover_exactly_kept_bullets() -> None:
    with pytest.raises(ApplyError):
        apply_plan(
            R(), TailorPlan(ops=(Reorder(entry_id="e1", order=("b1", "b2")),)), TBL
        )


def test_whole_token_sub_none_when_absent() -> None:
    assert whole_token_sub("Parsed JSON", "JS", "JavaScript") is None
    assert whole_token_sub("Shipped JS", "JS", "JavaScript") == "Shipped JavaScript"
