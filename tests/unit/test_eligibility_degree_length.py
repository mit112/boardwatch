"""T221: a degree's length before its `or equivalent` is a degree bar with an experience alternative.

"4 year college degree or equivalent experience", "2 year technical degree or equivalent
experience", "3-4 years of Accounting Degree or equivalent": the count is the degree's own length,
and the open-headed experience patterns read it as a years bar, so a degree-holder was `ineligible`
on a bar the degree meets. Sized over the 126,854 pinned postings: 15 required experience rows in
14 postings, and 3 preferred rows (`.agent/t221_scan.py`).

The six open-headed experience patterns (scoped, scoped range, domain list, domain list range,
domain, domain range) refuse the span (their T221 guard), and the degree family reads it as
`bachelor_length_or_equivalent_required` (three or four years) or
`associate_length_or_equivalent_required` (two): met by the degree, abstaining otherwise, since
the equivalent is never measured, and never unmet on a count that is the degree's own. A hedged bar
is carried as its carrier twin.

Not built, pinned as controls: a named level or a hedge before the `or` (both readings leave them,
so a refused years bar always has its degree row); and a count that is not a degree length, "5+ years college degree or
equivalent industrial sales experience" (the ticket's own sentence, one employer template, 5
postings), keeps the experience bar it reads as; reading it as a degree would clear a degree-holder
on what may be an experience bar. The near-miss band is off.
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
BACHELOR = Facts(total_years_experience=1, highest_degree="bachelor")


@pytest.fixture(scope="module")
def catalog(tmp_path_factory: pytest.TempPathFactory):  # type: ignore[no-untyped-def]
    return load_rules(Path(tmp_path_factory.mktemp("no-override")))


def _read(body: str, catalog, facts: Facts = BACHELOR) -> tuple[str, list[tuple[str, str, str, str]]]:  # type: ignore[no-untyped-def]
    result = evaluate(body, facts, POLICY, catalog)
    return result.verdict, sorted(
        (r.rule_id.split(":")[1], r.requiredness, r.disposition, body[slice(*r.jd_locator["span"])])
        for r in result.requirements
    )


LENGTHS = [
    pytest.param(
        "4 year college degree or equivalent experience required.",
        ("bachelor_length_or_equivalent_required", "4 year college degree or equivalent"),
        id="scoped-college-pv29390",
    ),
    pytest.param(
        "4 years of degree or equivalent practical experience",
        ("bachelor_length_or_equivalent_required", "4 years of degree or equivalent"),
        id="domain-list-pv27775",
    ),
    pytest.param(
        "3-4 years of Accounting Degree or equivalent.",
        ("bachelor_length_or_equivalent_required", "3-4 years of Accounting Degree or equivalent"),
        id="domain-range-pv243159",
    ),
    pytest.param(
        "3-4 year college degree or equivalent experience",
        ("bachelor_length_or_equivalent_required", "3-4 year college degree or equivalent"),
        id="scoped-range",
    ),
    pytest.param(
        "3-4 years college degree or equivalent sales experience",
        ("bachelor_length_or_equivalent_required", "3-4 years college degree or equivalent"),
        id="domain-list-range",
    ),
    pytest.param(
        "Four year college degree or equivalent experience required.",
        ("bachelor_length_or_equivalent_required", "Four year college degree or equivalent"),
        id="spelled-four",
    ),
    pytest.param(
        "2 year technical degree or equivalent experience",
        ("associate_length_or_equivalent_required", "2 year technical degree or equivalent"),
        id="scoped-technical-pv139524",
    ),
    pytest.param(
        "2 year Electronics/Electrical Technology degree OR an equivalent combination of education "
        "and experience.",
        (
            "associate_length_or_equivalent_required",
            "2 year Electronics/Electrical Technology degree OR an equivalent",
        ),
        id="domain-pv30106",
    ),
    pytest.param(
        "2 year Associate Degree in Product Definition or equivalent work related experience",
        (
            "associate_length_or_equivalent_required",
            "2 year Associate Degree in Product Definition or equivalent",
        ),
        id="domain-list-pv252491",
    ),
]


@pytest.mark.parametrize("body,row", LENGTHS)
def test_a_degree_length_is_a_degree_bar_the_degree_meets(catalog, body, row) -> None:  # type: ignore[no-untyped-def]
    rule, span = row
    assert _read(body, catalog) == ("eligible", [(rule, "required", "met", span)])


@pytest.mark.parametrize("body,row", LENGTHS)
def test_no_degree_abstains_and_is_never_unmet(catalog, body, row) -> None:  # type: ignore[no-untyped-def]
    rule, span = row
    none = Facts(total_years_experience=10, highest_degree="none")
    assert _read(body, catalog, none) == ("uncertain", [(rule, "required", "unknown", span)])


def test_an_associate_does_not_meet_a_four_year_length(catalog) -> None:  # type: ignore[no-untyped-def]
    associate = Facts(total_years_experience=1, highest_degree="associate")
    body = "4 year college degree or equivalent experience required."
    assert _read(body, catalog, associate) == (
        "uncertain",
        [("bachelor_length_or_equivalent_required", "required", "unknown",
          "4 year college degree or equivalent")],
    )
    two = "2 year technical degree or equivalent experience"
    assert _read(two, catalog, associate)[0] == "eligible"


@pytest.mark.parametrize(
    "body,row",
    [
        pytest.param(
            "4 year college degree or equivalent experience preferred.",
            ("bachelor_length_or_equivalent_preferred", "4 year college degree or equivalent"),
            id="tail-four",
        ),
        pytest.param(
            "Preferred Qualifications:\n- 4 year college degree or equivalent experience",
            ("bachelor_length_or_equivalent_preferred", "4 year college degree or equivalent"),
            id="heading-four",
        ),
        pytest.param(
            "2 year technical degree or equivalent experience preferred.",
            ("associate_length_or_equivalent_preferred", "2 year technical degree or equivalent"),
            id="tail-two",
        ),
    ],
)
def test_a_hedged_degree_length_is_carried_as_its_preference(catalog, body, row) -> None:  # type: ignore[no-untyped-def]
    rule, span = row
    assert _read(body, catalog) == ("eligible", [(rule, "preferred", "met", span)])


def test_a_real_bar_beside_a_degree_length_keeps_its_row(catalog) -> None:  # type: ignore[no-untyped-def]
    body = "2 years of Python experience; 4 year college degree or equivalent experience required."
    assert _read(body, catalog) == (
        "ineligible",
        [
            ("bachelor_length_or_equivalent_required", "required", "met",
             "4 year college degree or equivalent"),
            ("scoped_years_minimum", "required", "unmet", "2 years of Python experience"),
        ],
    )


@pytest.mark.parametrize(
    "body,row",
    [
        # The ticket's own sentence: five years is no degree length (control; not built).
        pytest.param(
            "5+ years college degree or equivalent industrial sales experience is required.",
            ("domain_list_years_minimum",
             "5+ years college degree or equivalent industrial sales experience"),
            id="ticket-five-years-pv236078",
        ),
        pytest.param(
            "8 years Computer Science degree or equivalent experience",
            ("domain_list_years_minimum", "8 years Computer Science degree or equivalent experience"),
            id="eight-years",
        ),
        pytest.param(
            "3 years of experience with AA degree or an equivalent",
            ("scoped_years_minimum", "3 years of experience with"),
            id="experience-before-the-degree",
        ),
        pytest.param(
            "3 years sales experience Associate degree or equivalent",
            ("scoped_years_minimum", "3 years sales experience"),
            id="experience-then-a-degree",
        ),
        pytest.param(
            "2+ years of post-degree clinical experience",
            ("scoped_years_minimum", "2+ years of post-degree clinical experience"),
            id="post-degree",
        ),
        pytest.param(
            "4 years of experience in software development",
            ("scoped_years_minimum", "4 years of experience in"),
            id="no-degree",
        ),
    ],
)
def test_control_a_count_that_is_not_the_degree_length_keeps_its_years_bar(catalog, body, row) -> None:  # type: ignore[no-untyped-def]
    rule, span = row
    verdict, rows = _read(body, catalog)
    assert verdict == "ineligible"
    assert (rule, "required", "unmet", span) in rows
    assert not any(r[0].endswith("_length_or_equivalent_required") for r in rows)


def test_control_a_named_level_or_a_hedge_before_the_or_is_neither_reading(catalog) -> None:  # type: ignore[no-untyped-def]
    """The guard and the two degree patterns read the same span, so a refused years bar always has its
    degree row. A named level and a hedge inside the span are left out of both, and read as on the
    base: `4 year Undergraduate degree` keeps its years bar beside the named degree row (1 store
    posting), `3 Years Bachelor's degree in ..., or equivalent` keeps its years bar (1), and so does
    `Two year university/Associate degree preferred or equivalent experience` (2)."""
    named = "4 year Undergraduate degree or equivalent experience"
    assert _read(named, catalog) == (
        "ineligible",
        [
            ("bachelor_or_equivalent_required", "required", "met", "Undergraduate degree or equivalent"),
            ("scoped_years_minimum", "required", "unmet",
             "4 year Undergraduate degree or equivalent experience"),
        ],
    )
    table = ("3 Years Bachelor's degree in business, finance, engineering, or related field, or "
             "equivalent experience in lieu of a bachelor's degree.")
    assert [r[0] for r in _read(table, catalog)[1]] == ["domain_years_minimum"]
    hedged = "Two year university/Associate degree preferred or equivalent experience."
    assert [r[0] for r in _read(hedged, catalog)[1]] == ["degree_preferred", "domain_list_years_minimum"]
