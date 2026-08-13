"""Task 22: the rank-agreement harness.

**This harness names no winner.** An earlier task (Task 21) already established that no
registered scorer is free of both demonstrated biases: `total_distinct` and
`coverage_then_density` fail the shallow-vs-focused probe, `mean_per_bullet` and `mean_top_k` fail
the comprehensive-vs-narrow probe, and the two failing sets are each other's exact complement
(`test_projection_scoring.py::test_no_scorer_is_free_of_both_demonstrated_biases`). So none of the
tests below compare one scorer's agreement against another's as "better" — they only pin
`rank_agreement`'s own arithmetic, and that `score_all` reports every registered scorer's own
number rather than filtering, ranking, or defaulting to one.
"""

from __future__ import annotations

import re
from decimal import Decimal

import pytest

from boardwatch.extract.taxonomy import Taxonomy, TaxonomyPattern
from boardwatch.projection.agreement import MatrixCase, rank_agreement, score_all
from boardwatch.projection.scoring import SCORERS
from boardwatch.tailor.equivalences import EquivalenceTable
from boardwatch.tailor.model import Bullet, Entry

# -- rank_agreement -----------------------------------------------------------------------


def test_perfect_agreement_is_one() -> None:
    assert rank_agreement(["a", "b", "c"], ["a", "b", "c"]) == Decimal(1)


def test_exact_reversal_is_negative_one() -> None:
    assert rank_agreement(["a", "b", "c"], ["c", "b", "a"]) == Decimal(-1)


def test_a_tie_in_expected_does_not_penalise_either_order_in_actual() -> None:
    """`("b", "c")` is one tied group. Whichever of `b`/`c` a scorer's own ranking happens to
    place first must not move the agreement score — that pair is excluded from both the
    concordant and discordant counts, not silently counted as a mismatch."""
    expected = ["a", ("b", "c"), "d"]

    agreement_b_first = rank_agreement(expected, ["a", "b", "c", "d"])
    agreement_c_first = rank_agreement(expected, ["a", "c", "b", "d"])

    assert agreement_b_first == agreement_c_first
    # Pinned against an independent hand computation, not just internal self-consistency: every
    # other pair is concordant (3 pairs), the tied pair is excluded, so C=5, D=0, n0=6, and the
    # denominator's expected-side term drops by exactly the one tied pair (n1=1).
    expected_value = Decimal(5) / (Decimal(6 - 1) * Decimal(6)).sqrt()
    assert agreement_b_first == expected_value
    # Non-vacuity: a broken implementation that always returns 1 (or 0) would satisfy the
    # equality checks above by accident; this rules that out.
    assert agreement_b_first != Decimal(1)


def test_rank_agreement_rejects_mismatched_id_sets() -> None:
    with pytest.raises(ValueError, match="same ids"):
        rank_agreement(["a", "b"], ["a", "c"])


def test_a_fully_tied_expected_yields_zero_not_a_crash() -> None:
    """Every pair tied in `expected` leaves no pair to compare, so tau-b's denominator is zero
    — reported as `0` (no information), never a `ZeroDivisionError`/`DivisionByZero`."""
    assert rank_agreement([("a", "b", "c")], ["a", "b", "c"]) == Decimal(0)


# -- score_all ----------------------------------------------------------------------------


def _taxonomy(skills: frozenset[str]) -> Taxonomy:
    return Taxonomy(
        patterns=tuple(
            TaxonomyPattern(
                name=n, category="tool", pattern=n, case_sensitive=False, regex=re.compile(n)
            )
            for n in skills
        ),
        version="agreement-test",
        source="bundled",
    )


def _entry(entry_id: str, *texts: str) -> Entry:
    return Entry(
        entry_id=entry_id,
        heading=entry_id,
        bullets=[Bullet(bullet_id=f"{entry_id}.{i}", text=t) for i, t in enumerate(texts)],
    )


#: One bullet engaging both JD skills deeply.
FOCUSED = _entry("entry.focused", "alpha beta")
#: Four bullets, each engaging exactly one distinct JD skill — the round-1 shape from
#: `test_projection_scoring.py`: an unnormalised union count rewards breadth here that the mean
#: does not.
SHALLOW = _entry("entry.shallow", "alpha", "beta", "gamma", "delta")

JD_SKILLS = frozenset({"alpha", "beta", "gamma", "delta"})


def test_score_all_returns_every_registered_scorer_key_even_on_an_empty_matrix() -> None:
    """No filtering, ranking, or defaulting: every registered scorer gets a reported number,
    always — an empty matrix is the baseline case (mean of nothing is 0), not a special-cased
    empty result."""
    result = score_all([], {}, EquivalenceTable((), "v"), _taxonomy(frozenset()))
    assert set(result) == set(SCORERS)
    assert all(value == Decimal(0) for value in result.values())


def test_score_all_matches_independently_hand_computed_agreement_per_scorer() -> None:
    """The owner's matrix ranks the focused entry above the shallow one. Different scorers
    disagree with that ranking differently — this pins each one's own number against arithmetic
    worked out independently of `score_all`, not against each other; none is asserted to be
    "better"."""
    pool = {"entry.focused": FOCUSED, "entry.shallow": SHALLOW}
    matrix = [MatrixCase(jd_skills=JD_SKILLS, expected=("entry.focused", "entry.shallow"))]
    table, taxonomy = EquivalenceTable((), "v"), _taxonomy(JD_SKILLS)

    # The premise: the four scorers really do disagree on this pool, or this test would not be
    # exercising score_all's per-scorer dispatch at all.
    assert SCORERS["total_distinct"](FOCUSED, JD_SKILLS, table, taxonomy) < SCORERS[
        "total_distinct"
    ](SHALLOW, JD_SKILLS, table, taxonomy)
    assert SCORERS["mean_per_bullet"](FOCUSED, JD_SKILLS, table, taxonomy) > SCORERS[
        "mean_per_bullet"
    ](SHALLOW, JD_SKILLS, table, taxonomy)

    result = score_all(matrix, pool, table, taxonomy)

    assert set(result) == set(SCORERS)
    # total_distinct ranks shallow (4) above focused (2): the exact reverse of the owner's
    # ranking, over just two ids -> tau-b = -1.
    assert result["total_distinct"] == Decimal(-1)
    assert result["coverage_then_density"] == Decimal(-1)
    # mean_per_bullet and mean_top_k both rank focused (2.0) above shallow (1.0), which is
    # exactly the owner's ranking -> tau-b = 1.
    assert result["mean_per_bullet"] == Decimal(1)
    assert result["mean_top_k"] == Decimal(1)


def test_score_all_averages_across_multiple_matrix_cases() -> None:
    """Two cases, one where `mean_per_bullet` agrees perfectly and one where it disagrees
    perfectly, average to 0 — proving `score_all` means over cases rather than, say, summing or
    keeping only the last one."""
    pool = {"entry.focused": FOCUSED, "entry.shallow": SHALLOW}
    table, taxonomy = EquivalenceTable((), "v"), _taxonomy(JD_SKILLS)
    agreeing_case = MatrixCase(jd_skills=JD_SKILLS, expected=("entry.focused", "entry.shallow"))
    disagreeing_case = MatrixCase(jd_skills=JD_SKILLS, expected=("entry.shallow", "entry.focused"))

    result = score_all([agreeing_case, disagreeing_case], pool, table, taxonomy)

    assert result["mean_per_bullet"] == Decimal(0)
