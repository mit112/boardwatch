"""`rank_tier`: the one rule the ranker and every list that shows its result sort by (D-688)."""

from __future__ import annotations

import pytest

from boardwatch.rank.leveling import FieldTier, entry_first_tier, rank_tier

TIER = FieldTier(
    words={},
    roman={},
    entry_markers=("new grad",),
    entry_body_markers=("0 2 years",),
    entry_marker_vetoes=("intern",),
)


def tier_of(
    title: str = "Software Engineer",
    *,
    role: str = "in_field",
    eligible: bool = False,
    uncertain: bool = False,
    entry_tier: FieldTier | None = TIER,
    body_marked: bool = False,
) -> int:
    return rank_tier(
        role=role,
        title=title,
        decided_eligible=eligible,
        uncertain=uncertain,
        entry_tier=entry_tier,
        entry_body_marked=body_marked,
    )


def test_an_entry_marked_in_field_title_is_tier_zero_whatever_its_verdict() -> None:
    assert tier_of("Software Engineer, New Grad") == 0
    assert tier_of(body_marked=True) == 0


def test_an_entry_marker_lifts_nothing_out_of_field_or_vetoed() -> None:
    assert tier_of("Accounting Clerk, New Grad", role="uncertain") == 3
    assert tier_of("Software Engineer Intern, New Grad", eligible=True) == 1
    assert tier_of("Software Engineer Intern", body_marked=True) == 3


def test_without_an_entry_tier_the_verdict_alone_decides() -> None:
    assert tier_of("Software Engineer, New Grad", entry_tier=None) == 3
    assert tier_of("Software Engineer, New Grad", entry_tier=None, eligible=True) == 1


@pytest.mark.parametrize(
    ("role", "eligible", "uncertain", "expected"),
    [
        ("in_field", True, False, 1),
        ("in_field", False, True, 2),
        ("in_field", False, False, 3),
        ("uncertain", True, False, 3),
        ("out_of_field", False, True, 3),
    ],
)
def test_the_verdict_tiers(role: str, eligible: bool, uncertain: bool, expected: int) -> None:
    assert tier_of(role=role, eligible=eligible, uncertain=uncertain) == expected


def test_only_an_entry_band_with_markers_earns_an_entry_tier() -> None:
    assert entry_first_tier("entry", TIER) is TIER
    assert entry_first_tier("any", TIER) is None
    assert entry_first_tier("entry", None) is None
    assert entry_first_tier("entry", FieldTier(words={}, roman={})) is None
