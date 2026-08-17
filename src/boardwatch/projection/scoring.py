"""The entry scorer protocol and four candidate scorers (Task 21).

Each candidate ranks how well one résumé `Entry` covers a JD's skills, for Task 22's later use
in choosing which entries a projected résumé surfaces. All four route through
`boardwatch.tailor.plan.effective_skills` — the one coverage primitive `build_plan` itself uses,
so a bullet's skill match here agrees with the tailoring plan that will actually select or drop
it, rather than a second, drifting notion of "matches."

`Decimal`, never `float`: a score ends up on the manifest, and `canonical._normalize` raises on
floats.

This module deliberately names no winner. Four candidates sit behind `EntryScorer`; which one a
projected résumé actually uses is Task 22's call, made by measurement against an owner-labeled
matrix that does not exist yet — not by this module's ordering, naming, or any default. The
mapping below is ordered alphabetically by key for exactly that reason: alphabetical order
carries no ranking signal.

The two known biases below (recorded in `tests/projection/test_projection_scoring.py` as
`KNOWN_BIASES`) are not defects — every one of the four candidates trades one demonstrated bias
for the other. `total_distinct` and `coverage_then_density` reward breadth (many bullets that
each add a new skill) but a shallow entry can inflate that count without engaging deeply with
any skill. `mean_per_bullet` and `mean_top_k` reward depth (skills demonstrated per bullet) but
one unrelated bullet dilutes a genuinely comprehensive entry's average.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Protocol

from boardwatch.extract.taxonomy import Taxonomy
from boardwatch.tailor.equivalences import EquivalenceTable
from boardwatch.tailor.model import Entry
from boardwatch.tailor.plan import MAX_BULLETS_PER_ENTRY, effective_skills


class EntryScorer(Protocol):
    """One candidate's ranking of `entry`'s coverage of `jd_skills`. Higher is better; the
    scale is comparable only across entries scored by the SAME scorer, never across scorers.
    """

    def __call__(
        self,
        entry: Entry,
        jd_skills: set[str],
        table: EquivalenceTable,
        taxonomy: Taxonomy,
    ) -> Decimal: ...


def _bullet_coverage(
    entry: Entry, jd_skills: set[str], table: EquivalenceTable, taxonomy: Taxonomy
) -> list[int]:
    """`|effective_skills(bullet.text, ...) & jd_skills|` for each bullet, in bullet order."""
    return [
        len(effective_skills(b.text, jd_skills, table, taxonomy) & jd_skills) for b in entry.bullets
    ]


def _mean(counts: list[int]) -> Decimal:
    if not counts:
        return Decimal(0)
    return Decimal(sum(counts)) / Decimal(len(counts))


def coverage_then_density(
    entry: Entry, jd_skills: set[str], table: EquivalenceTable, taxonomy: Taxonomy
) -> Decimal:
    """Lexicographic `(total_distinct, mean_per_bullet)`, coverage first, density as tiebreak.

    Encoded into one `Decimal` as `coverage * multiplier + density`. The assumed range:
    `coverage` (an entry's `total_distinct`) and any single bullet's own coverage count are both
    bounded above by `len(jd_skills)` — neither can count a skill twice or a skill outside the
    JD set — so `density` (a mean of such per-bullet counts) is bounded above by `len(jd_skills)`
    too. `multiplier = len(jd_skills) + 1` therefore always exceeds `density`, so one extra point
    of `coverage` outranks any `density` value the fixtures can produce; ties in `coverage` fall
    through to `density` unchanged. `len(jd_skills) + 1` still holds when `jd_skills` is empty
    (`multiplier = 1`, and both terms are then forced to `0`).
    """
    coverage = total_distinct(entry, jd_skills, table, taxonomy)
    density = mean_per_bullet(entry, jd_skills, table, taxonomy)
    multiplier = Decimal(len(jd_skills) + 1)
    return coverage * multiplier + density


def mean_per_bullet(
    entry: Entry, jd_skills: set[str], table: EquivalenceTable, taxonomy: Taxonomy
) -> Decimal:
    """Mean over bullets of `|effective_skills(bullet.text, ...) & jd_skills|`."""
    return _mean(_bullet_coverage(entry, jd_skills, table, taxonomy))


def mean_top_k(
    entry: Entry, jd_skills: set[str], table: EquivalenceTable, taxonomy: Taxonomy
) -> Decimal:
    """Mean over the top-`MAX_BULLETS_PER_ENTRY` bullets by coverage, the same ranking
    `build_plan` uses to select which bullets an entry keeps. Removes the truncation
    disagreement `mean_per_bullet` would otherwise have with the selection cap by construction:
    a bullet the cap would drop is dropped here too, before averaging.
    """
    counts = sorted(_bullet_coverage(entry, jd_skills, table, taxonomy), reverse=True)
    return _mean(counts[:MAX_BULLETS_PER_ENTRY])


def total_distinct(
    entry: Entry, jd_skills: set[str], table: EquivalenceTable, taxonomy: Taxonomy
) -> Decimal:
    """`|union of effective_skills(bullet.text, ...) over bullets & jd_skills|`."""
    union: set[str] = set()
    for b in entry.bullets:
        union |= effective_skills(b.text, jd_skills, table, taxonomy) & jd_skills
    return Decimal(len(union))


#: Ordered alphabetically by key — carries no ranking. Task 22 picks; this module does not.
SCORERS: Mapping[str, EntryScorer] = {
    "coverage_then_density": coverage_then_density,
    "mean_per_bullet": mean_per_bullet,
    "mean_top_k": mean_top_k,
    "total_distinct": total_distinct,
}

#: The scorer a caller that was given no choice uses. `mean_per_bullet` is the owner's measured
#: adoption (D-198): highest mean rank agreement with the labeled selection matrix, and normalized
#: per bullet, so it resists the bullet-count inflation that fools `total_distinct`.
#:
#: Named here rather than left as a literal in `--scorer`'s Typer option so an unattended caller
#: (which has no CLI option to read) does not become a second source of truth for the same choice.
#: This is a DEFAULT, not the ranking this module's own docstring declines to make — the choice was
#: made by measurement outside this module and is recorded here, not derived here.
DEFAULT_SCORER_ID = "mean_per_bullet"
