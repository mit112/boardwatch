"""T214: a `N months to M years` range reads its LOW end, in months.

"6 months to 2 years of experience" wrote no row: the range patterns need one unit on both ends, and
the years patterns' `(?<!to\\s)` guard blocks the high end. The spaced-dash form "6 months - 2 years
of experience in U.S. banking" was worse: the digit guards look for a DIGIT before the dash, so the
scoped pattern read the high end and rejected a one-year profile. The months patterns now read the
low end as the floor, so the range resolves on the same axis as every other months bar.

The near-miss band is off, so every bar above the profile's years is decisive, except where a test
turns it on to pin that a months bar under 36 months can never reject.
"""

from pathlib import Path

import pytest

from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.engine import evaluate
from boardwatch.eligibility.facts import Facts, Policy

FAMILIES = {
    "work_auth": "blocker", "experience_years": "blocker",
    "clearance": "blocker", "degree": "blocker",
}
POLICY = Policy(families=FAMILIES, near_miss_years_ceilings={"experience_years": 0})
BANDED = Policy(families=FAMILIES, near_miss_years_ceilings={"experience_years": 3})


@pytest.fixture(scope="module")
def catalog(tmp_path_factory: pytest.TempPathFactory):  # type: ignore[no-untyped-def]
    return load_rules(Path(tmp_path_factory.mktemp("no-override")))


def _read(body: str, catalog, policy: Policy = POLICY) -> tuple[str, list[tuple[str, str, str, str]]]:  # type: ignore[no-untyped-def]
    result = evaluate(body, Facts(total_years_experience=1), policy, catalog)
    return result.verdict, sorted(
        (r.rule_id.split(":")[1], r.requiredness, r.disposition, body[slice(*r.jd_locator["span"])])
        for r in result.requirements
    )


RANGES = [
    pytest.param(
        "6 months to 2 years of experience.",
        ("eligible", [("total_months_minimum", "required", "met",
                       "6 months to 2 years of experience")]),
        id="to-total",
    ),
    pytest.param(
        "6 months to 2 years of experience in healthcare IT.",
        ("uncertain", [("scoped_months_minimum", "required", "unknown",
                        "6 months to 2 years of experience in")]),
        id="to-scoped",  # pv 136595
    ),
    pytest.param(
        "3 months to 2 years relatable sales experience.",
        ("uncertain", [("scoped_months_minimum", "required", "unknown",
                        "3 months to 2 years relatable sales experience")]),
        id="to-domain-words",  # pv 293499
    ),
    pytest.param(
        "6 months – 2 years of experience in U.S. banking and international markets.",
        ("uncertain", [("scoped_months_minimum", "required", "unknown",
                        "6 months – 2 years of experience in")]),
        id="spaced-en-dash-scoped",  # pv 20860's shape; its ASCII ` - ` form is T233's (range_dash)
    ),
    pytest.param(
        "6 months – 2 years of relevant experience.",
        ("eligible", [("total_months_minimum", "required", "met",
                       "6 months – 2 years of relevant experience")]),
        id="spaced-en-dash-total",
    ),
    pytest.param(
        "18 months to 3 years of experience.",
        ("ineligible", [("total_months_minimum", "required", "unmet",
                         "18 months to 3 years of experience")]),
        id="an-18-month-low-end-is-read-as-18-months",
    ),
]


@pytest.mark.parametrize("body,expected", RANGES)
def test_a_months_to_years_range_reads_its_low_end(body: str, expected, catalog) -> None:  # type: ignore[no-untyped-def]
    assert _read(body, catalog) == expected


@pytest.mark.parametrize(
    "body,expected",
    [
        pytest.param(
            "18 months to 3 years of experience.",
            ("uncertain", [("total_months_minimum", "required", "unknown",
                            "18 months to 3 years of experience")]),
            id="total",
        ),
        pytest.param(
            "30 months to 4 years of experience in retail.",
            ("uncertain", [("scoped_months_minimum", "required", "unknown",
                            "30 months to 4 years of experience in")]),
            id="scoped",
        ),
    ],
)
def test_a_months_low_end_under_36_months_never_rejects(body: str, expected, catalog) -> None:  # type: ignore[no-untyped-def]
    assert _read(body, catalog, BANDED) == expected


CONTROLS = [
    pytest.param("6 to 24 months of experience.", ("uncertain", []), id="a-months-only-range"),
    pytest.param(
        "2 to 5 years of experience.",
        ("ineligible", [("range_years_minimum", "required", "unmet", "2 to 5 years of experience")]),
        id="a-years-only-range-keeps-its-low-end",
    ),
    pytest.param(
        "6 months of experience.",
        ("eligible", [("total_months_minimum", "required", "met", "6 months of experience")]),
        id="a-single-months-bar",
    ),
    pytest.param(
        "Within 6 months to 1 year, you will own the pipeline.", ("uncertain", []),
        id="a-ramp-up-window-is-not-a-bar",  # pv 214377
    ),
    # A hedged months bar is DROPPED, as every hedged months bar is: there is no months_preferred
    # arm (see total_months_minimum in rules.yaml). What matters here is that it never rejects.
    pytest.param(
        "6 months to 2 years of experience preferred.", ("uncertain", []), id="hedged",
    ),
    # T237b, NOT BUILT: the months patterns are digits-only, so a spelled range writes no row. One
    # store body carries the shape (pv 308287, an `OR equivalent combination` arm); this pins today's
    # read so a spelled low end shows up here.
    pytest.param(
        "AND six months to one year of related experience and/or training.", ("uncertain", []),
        id="t237b-spelled-range-unread",
    ),
]


@pytest.mark.parametrize("body,expected", CONTROLS)
def test_other_ranges_keep_their_read(body: str, expected, catalog) -> None:  # type: ignore[no-untyped-def]
    assert _read(body, catalog) == expected
