"""Task 22: the rank-agreement harness.

Measures how well each of `scoring.SCORERS`'s four candidates reproduces an owner's hand-ranked
order of candidate entries for one JD (Task 20's matrix, when it exists). **This module names no
winner.** Two probes already falsified every registered scorer on one axis or the other
(`test_projection_scoring.py`'s `KNOWN_BIASES`): `total_distinct` and `coverage_then_density` fail
the shallow-vs-focused probe, `mean_per_bullet` and `mean_top_k` fail the
comprehensive-vs-narrow probe, and the two failing sets are each other's exact complement — no
scorer is free of both. A harness that assumed some scorer agrees with everything would be
measuring nothing, so `score_all` always returns every registered scorer's own number, never a
filtered, ranked, or defaulted subset. Picking among them is Task 23's decision, made by reading
this mapping against Task 20's matrix and its cut line — not this module's.

## Representing ties

Task 20's matrix format allows a rank tie ("write them on one line"). `rank_agreement`'s
`expected` parameter represents that as one `tuple[str, ...]` group in place of a bare `str` at
that position; `actual` (a scorer's own output, sorted descending and tie-broken by id for
determinism — see `score_all`) is always a flat, duplicate-free `Sequence[str]`. Kendall's tau-b
is the standard statistic for exactly this asymmetry: a pair tied in `expected` is excluded from
both the concordant and discordant counts (and from the `expected`-side term of tau-b's
denominator), so which of two tied ids `actual` happens to place first can never move the score
either way.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from boardwatch.extract.taxonomy import Taxonomy
from boardwatch.projection.scoring import SCORERS, EntryScorer
from boardwatch.tailor.equivalences import EquivalenceTable
from boardwatch.tailor.model import Entry

#: One rank position in an owner-labeled ranking: a single id, or a tuple of ids tied at that
#: position. `actual` (a scorer's own ranking) never contains one of these — see the module
#: docstring.
RankedItem = str | tuple[str, ...]


def _rank_map(ranking: Sequence[RankedItem]) -> dict[str, int]:
    """id -> rank index. Ids in the same tied group share one index; only the ORDERING of the
    indices matters to the caller below, never their spacing."""
    ranks: dict[str, int] = {}
    for position, item in enumerate(ranking):
        group = (item,) if isinstance(item, str) else item
        for entry_id in group:
            ranks[entry_id] = position
    return ranks


def rank_agreement(expected: Sequence[RankedItem], actual: Sequence[str]) -> Decimal:
    """Kendall's tau-b between `expected` (the owner's ranking, ties allowed) and `actual` (a
    scorer's ranking, a flat total order) over the same set of ids.

    `1` for perfect agreement, `-1` for exact reversal, `0` when every pair is tied on one side
    (no pair left to compare). Raises `ValueError` — not a `ProjectionIssue`: mismatched id sets
    are a precondition on this function's own two arguments, a programming error in the caller,
    never a runtime projection refusal — if `expected` and `actual` do not name exactly the same
    set of ids.
    """
    expected_rank = _rank_map(expected)
    expected_ids = frozenset(expected_rank)
    actual_ids = frozenset(actual)
    if expected_ids != actual_ids:
        raise ValueError(
            "expected and actual must rank exactly the same ids: "
            f"only in expected={sorted(expected_ids - actual_ids)}, "
            f"only in actual={sorted(actual_ids - expected_ids)}"
        )
    actual_rank = {entry_id: position for position, entry_id in enumerate(actual)}

    ids = list(expected_ids)
    concordant = 0
    discordant = 0
    ties_expected = 0
    ties_actual = 0
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            e_diff = expected_rank[a] - expected_rank[b]
            act_diff = actual_rank[a] - actual_rank[b]
            if e_diff == 0 and act_diff == 0:
                continue
            if e_diff == 0:
                ties_expected += 1
                continue
            if act_diff == 0:
                ties_actual += 1
                continue
            if (e_diff > 0) == (act_diff > 0):
                concordant += 1
            else:
                discordant += 1

    n = len(ids)
    n0 = n * (n - 1) // 2
    denominator_sq = Decimal(n0 - ties_expected) * Decimal(n0 - ties_actual)
    if denominator_sq <= 0:
        # Every pair is tied on at least one side: no pair left to compare, so tau-b is
        # undefined by division rather than informative. Reported as "no information" rather
        # than raising, since an empty/fully-tied matrix row is a legitimate (if useless) input,
        # not a caller error.
        return Decimal(0)
    return (Decimal(concordant) - Decimal(discordant)) / denominator_sq.sqrt()


@dataclass(frozen=True)
class MatrixCase:
    """One posting's row from Task 20's owner-labeled matrix: the JD skills extracted, and the
    owner's ranked order over some subset of a shared candidate pool's ids — ties allowed, per
    `RankedItem`.
    """

    jd_skills: frozenset[str]
    expected: tuple[RankedItem, ...]


def _flatten(ranking: Sequence[RankedItem]) -> tuple[str, ...]:
    flat: list[str] = []
    for item in ranking:
        flat.extend((item,) if isinstance(item, str) else item)
    return tuple(flat)


def _rank_by_scorer(
    case: MatrixCase,
    pool: Mapping[str, Entry],
    scorer: EntryScorer,
    table: EquivalenceTable,
    taxonomy: Taxonomy,
) -> tuple[str, ...]:
    """`case`'s named ids, ordered by `scorer`'s own output against `case.jd_skills`, descending;
    ties broken by id ascending so the result is always a flat, duplicate-free total order — the
    shape `rank_agreement`'s `actual` parameter requires (see the module docstring)."""
    ids = _flatten(case.expected)
    # `EntryScorer.__call__` is typed to `set[str]` (`scoring.py`); `frozenset` is not a subtype
    # of `set`, so `MatrixCase.jd_skills` (frozenset, matching `PostingContext.jd_skills`'s own
    # immutable convention) is converted at this one call site rather than widening the shared
    # protocol.
    jd_skills = set(case.jd_skills)
    scored = [(scorer(pool[eid], jd_skills, table, taxonomy), eid) for eid in ids]
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return tuple(entry_id for _, entry_id in scored)


def _mean(values: Sequence[Decimal]) -> Decimal:
    if not values:
        return Decimal(0)
    return sum(values, Decimal(0)) / Decimal(len(values))


def score_all(
    matrix: Sequence[MatrixCase],
    pool: Mapping[str, Entry],
    table: EquivalenceTable,
    taxonomy: Taxonomy,
    *,
    scorers: Mapping[str, EntryScorer] = SCORERS,
) -> Mapping[str, Decimal]:
    """Every registered scorer's mean rank agreement across `matrix`.

    For each case, scores exactly the ids `case.expected` names (looked up in `pool`), orders
    them descending by that scorer's own output with ties broken by id, and averages
    `rank_agreement(case.expected, actual)` over every case in `matrix`. An empty `matrix` yields
    `0` for every scorer — the mean of nothing, not a special-cased result.

    Returns one entry per key in `scorers`, always every key: never a ranked, filtered, or "best"
    subset. Which key a caller prefers is a decision made by reading this mapping against Task
    20's matrix and its cut line, not by this function.
    """
    return {
        name: _mean(
            [
                rank_agreement(case.expected, _rank_by_scorer(case, pool, scorer, table, taxonomy))
                for case in matrix
            ]
        )
        for name, scorer in scorers.items()
    }


__all__ = ["MatrixCase", "RankedItem", "rank_agreement", "score_all"]
