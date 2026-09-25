"""T200: a DIGIT range never reads its high end as the floor.

"3 to 5 years of experience with Python" wrote `scoped_range_years_minimum` (3) AND
`scoped_years_minimum` (5), because the scoped pattern lacked the `(?<!to\\s)` its siblings carry,
and "Between 5 and 7 years of relevant experience" wrote a seven-year `total_years_minimum`, because
no digit alternative had a `between N and` guard; a spaced dash (`5 – 7 years`) read 7 the same way.
The digit alternatives now carry the guards T193 gave the spelled ones, so a digit range writes its
range row (the low end) where a range pattern reads it, and no row where none does.

The range patterns read the forms that left a real bar rowless (round 2): a spelled low end
(`eight to 10`), a plus or `or more` on either end (`5 – 8+`, `5+ to 12`, `5 to 10 or more`),
`between N and M` on the total, scoped and activity patterns, and a digit range on the domain and
domain-list patterns, which had no range twin.

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
        "Between 5 and 7 years of relevant experience", 6,
        ("eligible", [("range_years_minimum", "required", "met",
                       "5 and 7 years of relevant experience")]),
        id="between-total",
    ),
    pytest.param(
        "Between 5 and 7 years of experience with Python", 6,
        ("uncertain", [("scoped_range_years_minimum", "required", "unknown",
                        "5 and 7 years of experience with")]),
        id="between-scoped",
    ),
    pytest.param(
        "Between 5 and 7 years building web applications", 6,
        ("uncertain", [("scoped_range_years_activity", "required", "unknown",
                        "5 and 7 years building")]),
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
        "between 10 and 12 years of relevant experience", 11,
        ("eligible", [("range_years_minimum", "required", "met",
                       "10 and 12 years of relevant experience")]),
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


# The range forms that left a real bar rowless: each now writes its range row, low end the floor.
# At one year every low end is unmet, so the verdict is `ineligible` through that row.
LOW_ENDS = [
    pytest.param(
        "- Typically eight to 10 years of related experience", 1,
        ("ineligible", [("scoped_range_years_minimum", "required", "unmet",
                         "eight to 10 years of related experience")]),
        id="spelled-low-digit-high-pv30410",
    ),
    pytest.param(
        "Seven to 10 years of applicable experience", 1,
        ("ineligible", [("scoped_range_years_minimum", "required", "unmet",
                         "Seven to 10 years of applicable experience")]),
        id="spelled-low-digit-high-pv30498",
    ),
    pytest.param(
        "Eight to 10 years of related experience", 1,
        ("ineligible", [("scoped_range_years_minimum", "required", "unmet",
                         "Eight to 10 years of related experience")]),
        id="spelled-low-digit-high-pv257554",
    ),
    pytest.param(
        "Minimum of 5 – 8+ years in management consulting, with a focus on private equity or"
        " operational improvements", 1,
        ("ineligible", [("domain_range_years_minimum", "required", "unmet",
                         "5 – 8+ years in management consulting, with a focus")]),
        id="plus-high-end-domain-pv106563",
    ),
    pytest.param(
        "minimum 5 – 7 years in related Business Field", 1,
        ("ineligible", [("domain_range_years_minimum", "required", "unmet",
                         "5 – 7 years in related Business Field")]),
        id="spaced-dash-domain-pv250918",
    ),
    pytest.param(
        "3 – 5 years of product supporting a SaaS solution, appliance or equivalent experience"
        " with demonstrated ability to discover opportunities, and then define and deliver"
        " products.", 1,
        ("ineligible", [("domain_list_range_years_minimum", "required", "unmet",
                         "3 – 5 years of product supporting a SaaS solution, appliance or"
                         " equivalent experience")]),
        id="spaced-dash-domain-list-pv96209",
    ),
    pytest.param(
        "5 to 10 or more years of SEO experience, ideally in a tech or SaaS environment.", 1,
        ("ineligible", [("scoped_range_years_minimum", "required", "unmet",
                         "5 to 10 or more years of SEO experience")]),
        id="or-more-high-end-pv287433",
    ),
    pytest.param(
        "5+ to 12 years of hands-on experience in Software development", 1,
        ("ineligible", [("scoped_range_years_minimum", "required", "unmet",
                         "5+ to 12 years of hands-on experience in")]),
        id="plus-low-end",
    ),
    pytest.param(
        "three to five years of relevant experience", 1,
        ("ineligible", [("range_years_minimum", "required", "unmet",
                         "three to five years of relevant experience")]),
        id="spelled-low-spelled-high",
    ),
    pytest.param(
        "Between 5 and 7 years of relevant experience", 1,
        ("ineligible", [("range_years_minimum", "required", "unmet",
                         "5 and 7 years of relevant experience")]),
        id="between-total-unmet",
    ),
    # A decimal low end reads its whole part, never its fraction (pv 119740, pv 318532).
    pytest.param(
        "2.2–3 years' experience in AI, software development, digitalization, or process"
        " automation projects.", 1,
        ("ineligible", [("scoped_range_years_minimum", "required", "unmet",
                         "2.2–3 years' experience in")]),
        id="decimal-low-end-pv119740",
    ),
    pytest.param(
        "Minimum of 3.5 to 8+ years of relevant experience in the MEP field", 1,
        ("ineligible", [("scoped_range_years_minimum", "required", "unmet",
                         "3.5 to 8+ years of relevant experience in")]),
        id="decimal-low-end-pv318532",
    ),
]


@pytest.mark.parametrize("body,years,expected", LOW_ENDS)
def test_a_range_reads_its_low_end_as_the_floor(body: str, years: int, expected, catalog) -> None:  # type: ignore[no-untyped-def]
    assert _read(body, years, catalog) == expected


# Controls: a ceiling and a months-to-years range stay rowless, and so do a decimal whose whole part
# is under the domain pattern's bound, a domain range under that bound, and a time horizon.
ROWLESS = [
    pytest.param("Up to 5 years of experience in Customer Success", 1, id="up-to-is-a-ceiling"),
    pytest.param("upto 5 years of relevant experience", 1, id="upto-is-a-ceiling"),
    pytest.param(
        "6 months to 2 years of experience in healthcare IT, consulting, or related fields.", 1,
        id="months-to-years-left-rowless",
    ),
    # pv 32676: a decimal's fraction is not the floor.
    pytest.param("Experience: 0,5- 3 years in SRE and-or DevTools support roles.", 1,
                 id="decimal-low-end-pv32676"),
    # pv 4142: the domain range twin keeps its sibling's 2-19 bound on the count.
    pytest.param("at least 1-2 years specifically passionate about Generative AI", 1,
                 id="domain-range-low-end-under-two-pv4142"),
    # pv 92841: a time horizon is not a bar.
    pytest.param("Over the next 3-5 years State Street will deploy a next generation platform", 1,
                 id="over-the-next-is-a-horizon-pv92841"),
]


@pytest.mark.parametrize("body,years", ROWLESS)
def test_a_ceiling_or_an_unread_range_writes_no_row(body: str, years: int, catalog) -> None:  # type: ignore[no-untyped-def]
    assert _read(body, years, catalog) == ("uncertain", [])
