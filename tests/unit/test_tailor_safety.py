from __future__ import annotations

from pathlib import Path

import pytest

from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.tailor.apply import apply_plan
from boardwatch.tailor.equivalences import load_equivalences
from boardwatch.tailor.model import Bullet, Entry, Resume
from boardwatch.tailor.plan import (
    Delete,
    EquivalenceSwap,
    Reorder,
    TailorPlan,
    build_plan,
)
from boardwatch.tailor.safety import (
    TierASafetyError,
    enforce_tier_a,
    output_is_entailed,
    plan_is_structurally_safe,
)

TBL = load_equivalences()
TAX = load_taxonomy(Path("/nonexistent"))


def M() -> Resume:
    return Resume(
        header=["h"],
        education=[],
        skill_groups=[],
        entries=[
            Entry(
                entry_id="e1",
                heading="H",
                bullets=[
                    Bullet(bullet_id="b1", text="Shipped JS"),
                    Bullet(bullet_id="b2", text="Built Python service"),
                ],
            )
        ],
    )


def test_legit_tailoring_is_entailed() -> None:
    m = M()
    plan = build_plan(m, {"JavaScript", "Python"}, TBL, TAX)
    t = apply_plan(m, plan, TBL)
    assert output_is_entailed(m, t, TBL)
    enforce_tier_a(m, t, plan, TBL)  # no raise


def test_added_token_rejected() -> None:
    m = M()
    bad = m.model_copy(
        update={
            "entries": [
                m.entries[0].model_copy(
                    update={
                        "bullets": [
                            m.entries[0].bullets[0].model_copy(
                                update={"text": "Shipped JS at massive scale"}
                            )
                        ],
                    }
                )
            ]
        }
    )
    assert not output_is_entailed(m, bad, TBL)


def test_non_table_swap_rejected_by_output_check() -> None:
    m = M()
    bad = m.model_copy(
        update={
            "entries": [
                m.entries[0].model_copy(
                    update={
                        "bullets": [
                            m.entries[0].bullets[0].model_copy(
                                update={"text": "Shipped Golang"}
                            )
                        ]
                    }
                )
            ]
        }
    )
    assert not output_is_entailed(m, bad, TBL)


def test_altered_non_bullet_region_rejected() -> None:
    m = M()
    plan = build_plan(m, {"Python"}, TBL, TAX)
    t = apply_plan(m, plan, TBL)
    tampered = t.model_copy(update={"header": ["different"]})
    with pytest.raises(TierASafetyError):
        enforce_tier_a(m, tampered, plan, TBL)


# --- plan_is_structurally_safe branch coverage ---


def test_structurally_safe_accepts_valid_plan() -> None:
    m = M()
    plan = build_plan(m, {"JavaScript", "Python"}, TBL, TAX)
    assert plan_is_structurally_safe(m, plan, TBL)


def test_structural_unknown_bullet_id_rejected() -> None:
    m = M()
    plan = TailorPlan(ops=(Delete(bullet_id="nope"),))
    assert not plan_is_structurally_safe(m, plan, TBL)


def test_structural_unknown_entry_id_rejected() -> None:
    m = M()
    plan = TailorPlan(ops=(Reorder(entry_id="nope", order=("b1",)),))
    assert not plan_is_structurally_safe(m, plan, TBL)


def test_structural_non_table_pair_rejected() -> None:
    m = M()
    plan = TailorPlan(
        ops=(EquivalenceSwap(bullet_id="b1", from_phrase="JS", to_phrase="Golang"),)
    )
    assert not plan_is_structurally_safe(m, plan, TBL)


def test_structural_swap_from_phrase_not_whole_token_rejected() -> None:
    # AM-4: from_phrase must appear as a whole token in the referenced master bullet.
    # b2 = "Built Python service" does not contain "JS" as a whole token.
    m = M()
    plan = TailorPlan(
        ops=(EquivalenceSwap(bullet_id="b2", from_phrase="JS", to_phrase="JavaScript"),)
    )
    assert not plan_is_structurally_safe(m, plan, TBL)
