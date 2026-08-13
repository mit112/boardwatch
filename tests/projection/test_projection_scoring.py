"""Both probes that falsified a design round, as executable fixtures, plus the two rulings
Task 21 added on top (R12, R13).

The design cited two demonstrated biases but no fixture, script, or log for them exists in the
repo — they lived in external reviewers' contexts. So they are AUTHORED here rather than named,
which is this repo's own rule: a plan fixture must be run against the real schema, not
referenced.

Each fixture pair was checked against the real four scorers (not hand arithmetic alone) before
this file was written. A probe drafted as a single assertion ("focused >= shallow", then
"comprehensive >= focused") turns out to falsify TWO of the four scorers each time, not one:

  - Round 1 (shallow beats focused): `total_distinct` counts the union of matched skills with no
    normalization, so a size bias lifts to entry level that does not exist at bullet level (an
    unrelated fact, since `build_plan` ranks bullets independently). `coverage_then_density`
    inherits this exactly, because its primary key IS `total_distinct` and neither fixture ties
    on it.
  - Round 2 (narrow beats comprehensive): `mean_per_bullet` is diluted by one unrelated bullet
    in the comprehensive entry. `mean_top_k` cannot avoid this on `COMPREHENSIVE_SIX`
    specifically, because that fixture has exactly `MAX_BULLETS_PER_ENTRY` (6) bullets — top-6
    degenerates to all-6, so it cannot disagree with `mean_per_bullet` there by construction.

`KNOWN_BIASES` below records this as a table (R12), and both probes iterate every registered
scorer (`sorted(SCORERS)`) so a fifth candidate is covered the day it lands rather than silently
skipped. Neither probe asserts a winner, and this file does not either — `SCORERS` ships with no
default; Task 22's measurement, against an owner-labeled matrix that does not exist yet, makes
that call.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

import pytest

from boardwatch.extract.taxonomy import Taxonomy, TaxonomyPattern
from boardwatch.projection.scoring import SCORERS
from boardwatch.tailor.equivalences import EquivalenceTable
from boardwatch.tailor.model import Bullet, Entry
from boardwatch.tailor.plan import MAX_BULLETS_PER_ENTRY, effective_skills

JD = {"airflow", "snowflake", "dbt", "spark", "kafka", "python", "sql", "terraform", "aws"}


def _taxonomy() -> Taxonomy:
    return Taxonomy(
        patterns=tuple(
            TaxonomyPattern(
                name=n,
                category="tool",
                pattern=n,
                case_sensitive=False,
                regex=re.compile(n, re.IGNORECASE),
            )
            for n in JD
        ),
        version="probe-1",
        source="bundled",
    )


def _entry(entry_id: str, *texts: str) -> Entry:
    return Entry(
        entry_id=entry_id,
        heading=entry_id,
        bullets=[Bullet(bullet_id=f"{entry_id}.{i}", text=t) for i, t in enumerate(texts)],
    )


FOCUSED_ONE = _entry("entry.focused", "Built an airflow and snowflake ingestion pipeline")
SHALLOW_FOUR = _entry(
    "entry.shallow",
    "Attended a snowflake vendor talk",
    "Ran one airflow job during an internship",
    "Read about dbt",
    "Saw a spark demo",
)
COMPREHENSIVE_SIX = _entry(
    "entry.comprehensive",
    "Built airflow DAGs and snowflake models",
    "Wrote dbt transformations and spark jobs",
    "Ran kafka ingestion in python",
    "Tuned sql warehouses",
    "Provisioned terraform on aws",
    "Wrote documentation",
)

#: Which scorers the arithmetic falsifies for each probe. Derived by hand from the fixtures
#: above and pinned by the probes themselves (a change here that does not match the real
#: scorer outputs turns the corresponding parametrized case red, since it stops xfailing a
#: scorer that still fails, or starts xfailing one that no longer does — caught as an
#: unexpected pass, see `strict=True` below).
KNOWN_BIASES: dict[str, frozenset[str]] = {
    "shallow_beats_focused": frozenset({"total_distinct", "coverage_then_density"}),
    "narrow_beats_comprehensive": frozenset({"mean_per_bullet", "mean_top_k"}),
}


def test_known_biases_names_only_registered_scorers() -> None:
    """Non-vacuity of the table's shape: a typo in `KNOWN_BIASES` naming a retired or
    not-yet-added scorer would silently stop covering anything real."""
    named = frozenset().union(*KNOWN_BIASES.values())
    assert named, "KNOWN_BIASES names no scorer at all"
    assert named <= frozenset(SCORERS), f"unregistered names in KNOWN_BIASES: {named - frozenset(SCORERS)}"


def _cases(probe: str) -> list[Any]:
    """Every registered scorer, marked `xfail(strict=True)` for the ones `KNOWN_BIASES` names
    for `probe`. `strict=True` so a scorer that stops being biased shows up as an unexpected
    pass (a real failure) instead of a silently-still-xfailing case — the assertion always
    actually runs; nothing here short-circuits before it."""
    biased = KNOWN_BIASES[probe]
    return [
        pytest.param(
            name, marks=pytest.mark.xfail(reason=f"{name} is known-biased by {probe}", strict=True)
        )
        if name in biased
        else name
        for name in sorted(SCORERS)
    ]


@pytest.mark.parametrize("name", _cases("shallow_beats_focused"))
def test_round_one_bias_the_shallow_entry_must_not_beat_the_focused_one(name: str) -> None:
    """Round 1's probe: 4 distinct beats 2 distinct despite the focused entry engaging each
    matched skill more deeply. An unnormalized count lifts a size bias to entry level that does
    not exist at bullet level, because `build_plan` ranks bullets independently."""
    scorer = SCORERS[name]
    table, taxonomy = EquivalenceTable((), "v"), _taxonomy()
    focused = scorer(FOCUSED_ONE, JD, table, taxonomy)
    shallow = scorer(SHALLOW_FOUR, JD, table, taxonomy)
    assert focused >= shallow, f"{name}: focused={focused} shallow={shallow}"


@pytest.mark.parametrize("name", _cases("narrow_beats_comprehensive"))
def test_round_two_bias_the_comprehensive_entry_must_not_lose_to_the_narrow_one(name: str) -> None:
    """Round 2's probe: a one-bullet entry matching two JD skills must not beat a six-bullet
    entry matching nine — density winning over coverage."""
    scorer = SCORERS[name]
    table, taxonomy = EquivalenceTable((), "v"), _taxonomy()
    comprehensive = scorer(COMPREHENSIVE_SIX, JD, table, taxonomy)
    focused = scorer(FOCUSED_ONE, JD, table, taxonomy)
    assert comprehensive >= focused, f"{name}: comp={comprehensive} focused={focused}"


def test_at_least_one_scorer_survives_each_probe_individually() -> None:
    """Per-probe non-vacuity: `KNOWN_BIASES` must not name every registered scorer for a single
    probe — that would make the probe's parametrized test above xfail unconditionally for every
    case and assert nothing. This does not claim the SAME scorer survives both probes; see
    `test_no_scorer_is_free_of_both_demonstrated_biases` immediately below for that question,
    which the fixtures answer 'none' — a real, deliberate finding, not an oversight."""
    all_names = frozenset(SCORERS)
    for probe, biased in KNOWN_BIASES.items():
        survivors = all_names - biased
        assert survivors, f"{probe}: every registered scorer is known-biased — table is vacuous"


def test_no_scorer_is_free_of_both_demonstrated_biases() -> None:
    """Pinned, deliberate finding, not a bug: the set of scorers that survive round 1 and the
    set that survive round 2 are each other's exact complement over the four registered
    scorers, so their intersection is empty. `total_distinct` and `coverage_then_density` both
    key on `total_distinct`, which wins round 2 (comprehensive's 9 distinct beats focused's 2)
    but loses round 1 (shallow's 4 distinct beats focused's 2, the same unnormalized-count
    mechanism). `mean_per_bullet` and `mean_top_k` both key on a per-bullet mean, which wins
    round 1 (focused's 2.0 beats shallow's 1.0) but loses round 2 (focused's 2.0 beats
    comprehensive's 1.5, the same dilution mechanism in reverse). No candidate is free of both
    known biases at once — that is the reason Task 22 measures against a labeled matrix instead
    of naming a winner here."""
    survives_round_one = frozenset(SCORERS) - KNOWN_BIASES["shallow_beats_focused"]
    survives_round_two = frozenset(SCORERS) - KNOWN_BIASES["narrow_beats_comprehensive"]
    assert survives_round_one, "round 1 has no survivor at all"
    assert survives_round_two, "round 2 has no survivor at all"
    assert survives_round_one & survives_round_two == frozenset(), (
        "expected no scorer to be bias-free on both probes; if one now is, the four scorers "
        "changed and Task 22's premise (no free lunch) needs re-checking, not this assertion"
    )
    assert survives_round_one | survives_round_two == frozenset(SCORERS), (
        "expected every scorer to be known-biased in exactly one probe"
    )


#: Six bullets that each match a JD skill, then six that match nothing. `MAX_BULLETS_PER_ENTRY`
#: is 6, so `build_plan` keeps exactly the first six — the scorer must agree with that cap.
MATCHING_SIX = [
    "Built airflow DAGs",
    "Wrote dbt models",
    "Ran spark jobs",
    "Tuned sql warehouses",
    "Used kafka streams",
    "Provisioned aws infrastructure",
]
FILLER_SIX = [f"Wrote internal documentation, part {i}" for i in range(6)]


def test_no_scorer_penalises_a_bullet_the_cap_would_keep() -> None:
    """The truncation-agreement requirement. A twelve-bullet entry whose six matching bullets
    are exactly the survivors of `MAX_BULLETS_PER_ENTRY` must not be scored down for the six it
    loses.
    """
    twelve = _entry("entry.twelve", *(MATCHING_SIX + FILLER_SIX))
    six = _entry("entry.six", *MATCHING_SIX)
    table, taxonomy = EquivalenceTable((), "v"), _taxonomy()

    # The premise: the filler really does match nothing, or the two entries are trivially equal
    # and this test would pass without the cap-awareness it exists to check.
    assert all(not (effective_skills(t, JD, table, taxonomy) & JD) for t in FILLER_SIX)

    scorer = SCORERS["mean_top_k"]
    assert scorer(twelve, JD, table, taxonomy) == scorer(six, JD, table, taxonomy)


def test_max_bullets_per_entry_is_six() -> None:
    """Pins the constant `mean_top_k` and the cap-agreement test above both depend on, and that
    `COMPREHENSIVE_SIX`'s bullet count was chosen to match exactly. A future change to the
    tailoring cap must fail loudly here rather than silently changing which fixtures degenerate
    into which."""
    assert MAX_BULLETS_PER_ENTRY == 6


# -- R13: coverage_then_density's order-preserving encoding --------------------------------


def test_coverage_then_density_orders_by_coverage_first() -> None:
    """Primary key: a higher `total_distinct` outranks any density, matching round 2's own win
    condition for this scorer (comprehensive's 9 distinct beats focused's 2)."""
    scorer = SCORERS["coverage_then_density"]
    table, taxonomy = EquivalenceTable((), "v"), _taxonomy()
    comprehensive = scorer(COMPREHENSIVE_SIX, JD, table, taxonomy)
    focused = scorer(FOCUSED_ONE, JD, table, taxonomy)
    assert comprehensive > focused


def test_coverage_then_density_tiebreak_decides_when_coverage_ties() -> None:
    """R13's pinning case: two entries with the SAME `total_distinct` (2) but different
    `mean_per_bullet` (2.0 vs 1.0). If the encoding dropped the density term, or mis-ordered
    the pair, these would tie or invert instead of separating by density."""
    table, taxonomy = EquivalenceTable((), "v"), _taxonomy()
    dense = _entry("entry.dense", "Built an airflow and snowflake pipeline")
    diluted = _entry(
        "entry.diluted",
        "Built an airflow and snowflake pipeline",
        "Wrote internal documentation",
    )

    # The premise: the two entries really do tie on total_distinct and really do differ on
    # mean_per_bullet, or this is not the tiebreak-decides case R13 asks for.
    assert SCORERS["total_distinct"](dense, JD, table, taxonomy) == SCORERS["total_distinct"](
        diluted, JD, table, taxonomy
    )
    assert SCORERS["mean_per_bullet"](dense, JD, table, taxonomy) > SCORERS["mean_per_bullet"](
        diluted, JD, table, taxonomy
    )

    scorer = SCORERS["coverage_then_density"]
    assert scorer(dense, JD, table, taxonomy) > scorer(diluted, JD, table, taxonomy)


def test_coverage_then_density_encoding_does_not_collide_at_the_assumed_range() -> None:
    """The assumed range: both `total_distinct` and any single bullet's coverage are bounded
    above by `len(jd_skills)` (neither can count a skill twice or a skill outside the JD set),
    so `mean_per_bullet` — a mean of such per-bullet counts — is bounded above by
    `len(jd_skills)` too. The encoding's multiplier (`len(jd_skills) + 1`) is chosen to exceed
    that bound, so one extra point of coverage must outrank any density, however large.

    This is the adversarial case at that boundary: an 8-of-9 entry at its own maximum possible
    density (a single bullet, mean 8.0) against a 9-of-9 entry diluted by filler bullets down to
    a much lower density (mean 1.125). If the multiplier were too small — e.g. `len(jd_skills)`
    with no `+1` — density could still tip this comparison; the assumed range says it cannot.
    """
    table, taxonomy = EquivalenceTable((), "v"), _taxonomy()
    eight_of_nine = _entry(
        "entry.eight",
        "Worked with airflow snowflake dbt spark kafka python sql terraform",  # every JD skill but aws
    )
    nine_of_nine_diluted = _entry(
        "entry.nine_diluted",
        "Worked with airflow snowflake dbt spark kafka python sql terraform",
        "Provisioned aws infrastructure",
        *(f"Handled administrative task {i}" for i in range(6)),
    )

    # The premise: the coverage gap really is exactly one, and the density gap really does
    # favor the lower-coverage entry, or this is not the boundary case the docstring claims.
    eight_distinct = SCORERS["total_distinct"](eight_of_nine, JD, table, taxonomy)
    nine_distinct = SCORERS["total_distinct"](nine_of_nine_diluted, JD, table, taxonomy)
    assert nine_distinct - eight_distinct == Decimal(1)
    eight_density = SCORERS["mean_per_bullet"](eight_of_nine, JD, table, taxonomy)
    nine_density = SCORERS["mean_per_bullet"](nine_of_nine_diluted, JD, table, taxonomy)
    assert eight_density > nine_density

    scorer = SCORERS["coverage_then_density"]
    assert scorer(nine_of_nine_diluted, JD, table, taxonomy) > scorer(eight_of_nine, JD, table, taxonomy)
