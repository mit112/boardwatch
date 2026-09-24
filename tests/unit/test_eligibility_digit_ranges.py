"""T200: a DIGIT range never reads its high end as the floor.

"3 to 5 years of experience with Python" wrote `scoped_range_years_minimum` (3) AND
`scoped_years_minimum` (5), because the scoped pattern lacked the `(?<!to\\s)` its siblings carry,
and "Between 5 and 7 years of relevant experience" wrote a seven-year `total_years_minimum`, because
no digit alternative had a `between N and` guard; a spaced dash (`5 – 7 years`) read 7 the same way.
The digit alternatives now carry the guards T193 gave the spelled ones, so a digit range writes its
range row (the low end) where a range pattern reads it, and no row where none does.

The near-miss band is off, so every bar above the profile's years is decisive.
"""

from pathlib import Path

import pytest

from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.engine import evaluate
from boardwatch.eligibility.facts import Facts, Policy

POLICY = Policy(
    families={
        "work_auth": "blocker", "experience_years": "blocker",
        "clearance": "blocker", "degree": "blocker",
    },
    near_miss_years_ceilings={"experience_years": 0},
)


@pytest.fixture(scope="module")
def catalog(tmp_path_factory: pytest.TempPathFactory):  # type: ignore[no-untyped-def]
    return load_rules(Path(tmp_path_factory.mktemp("no-override")))


def _read(body: str, years: int, catalog) -> tuple[str, list[tuple[str, str, str, str]]]:  # type: ignore[no-untyped-def]
    result = evaluate(body, Facts(total_years_experience=years), POLICY, catalog)
    return result.verdict, sorted(
        (r.rule_id.split(":")[1], r.requiredness, r.disposition, body[slice(*r.jd_locator["span"])])
        for r in result.requirements
    )


# Each range writes its range row alone, or no row at all: never a row on the high end.
RANGES = [
    pytest.param(
        "3 to 5 years of experience with Python", 4,
        ("uncertain", [("scoped_range_years_minimum", "required", "unknown",
                        "3 to 5 years of experience with")]),
        id="to-scoped",
    ),
    pytest.param(
        "Between 5 and 7 years of relevant experience", 6, ("uncertain", []), id="between-total",
    ),
    pytest.param(
        "Between 5 and 7 years of experience with Python", 6, ("uncertain", []),
        id="between-scoped",
    ),
    pytest.param(
        "Between 5 and 7 years building web applications", 6, ("uncertain", []),
        id="between-activity",
    ),
    pytest.param(
        "Between 5 and 7 years of Python, Java, and Go experience", 6, ("uncertain", []),
        id="between-domain-list",
    ),
    pytest.param(
        "Between 5 and 7 years in welding", 6, ("uncertain", []), id="between-domain",
    ),
    pytest.param(
        "between 10 and 12 years of relevant experience", 11, ("uncertain", []),
        id="between-two-digit-low-end",
    ),
    pytest.param(
        "Between 5 and 7 years of relevant experience preferred", 6, ("uncertain", []),
        id="between-preferred",
    ),
    pytest.param(
        "5 – 7 years of relevant experience", 6,
        ("eligible", [("range_years_minimum", "required", "met",
                       "5 – 7 years of relevant experience")]),
        id="spaced-en-dash-total",
    ),
    pytest.param(
        "5 — 7 years of experience with Python", 6,
        ("uncertain", [("scoped_range_years_minimum", "required", "unknown",
                        "5 — 7 years of experience with")]),
        id="spaced-em-dash-scoped",
    ),
    pytest.param(
        "5– 7 years of relevant experience", 6,
        ("eligible", [("range_years_minimum", "required", "met",
                       "5– 7 years of relevant experience")]),
        id="dash-then-space",
    ),
]


@pytest.mark.parametrize("body,years,expected", RANGES)
def test_a_digit_range_does_not_read_its_high_end(body: str, years: int, expected, catalog) -> None:  # type: ignore[no-untyped-def]
    assert _read(body, years, catalog) == expected


# Controls: the single-number bars and the range rows the guards must not touch.
CONTROLS = [
    pytest.param(
        "5 and 7 years of relevant experience", 6,
        ("ineligible", [("total_years_minimum", "required", "unmet",
                         "7 years of relevant experience")]),
        id="and-without-between-keeps-its-bar",
    ),
    pytest.param(
        "5 years of experience with Python", 4,
        ("ineligible", [("scoped_years_minimum", "required", "unmet",
                         "5 years of experience with")]),
        id="single-scoped-bar",
    ),
    pytest.param(
        "5 to 7 years of experience with Python", 4,
        ("ineligible", [("scoped_range_years_minimum", "required", "unmet",
                        "5 to 7 years of experience with")]),
        id="scoped-range-row",
    ),
    pytest.param(
        "Requirements – 5 years of relevant experience", 4,
        ("ineligible", [("total_years_minimum", "required", "unmet",
                         "5 years of relevant experience")]),
        id="a-dash-after-a-word-is-not-a-range",
    ),
]


@pytest.mark.parametrize("body,years,expected", CONTROLS)
def test_a_single_number_bar_keeps_its_row(body: str, years: int, expected, catalog) -> None:  # type: ignore[no-untyped-def]
    assert _read(body, years, catalog) == expected
