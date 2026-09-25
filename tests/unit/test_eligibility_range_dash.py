"""T233: a spaced ASCII ` - ` range reads its LOW end, not its high end.

`_SENTENCE_SPLIT` cuts ` - ` as an inline bullet, so "5 - 7 years of experience" put "7 years of
experience" in a unit of its own. No lookbehind there can see the low end, and the total pattern
wrote a 7-year bar. The months-to-years form ("6 months - 2 years of experience in U.S. banking",
pv 20860) read a 2-year scoped bar the same way. `split_units` now keeps the cut out when the piece
before it ends in a number, optionally with `+` or `months`, that is no label's, and the piece after
it opens on a larger number that a time unit follows within two words. Every range pattern then sees
the whole range, as it does for `5-7` and `5 – 7`.

A real inline bullet keeps its cut: `Python - 5 years`, a requisition id (`10047 - 3+ years`), a
label (`Option 3 - 5 years`, `Level 7 - 2+ years`) and a number glued to a word (`UI5 - 7+ years`).

The near-miss band is off, so every bar above the profile's years is decisive.
"""

from pathlib import Path

import pytest

from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.detect import split_units
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


RANGES = [
    pytest.param(
        "5 - 7 years of experience.", 6,
        ("eligible", [("range_years_minimum", "required", "met", "5 - 7 years of experience")]),
        id="total",
    ),
    pytest.param(
        "2 - 4 years of professional experience required.", 3,
        ("eligible", [("range_years_minimum", "required", "met",
                       "2 - 4 years of professional experience")]),
        id="total-with-a-modifier",
    ),
    pytest.param(
        "Typically between 5 - 7 years of relevant experience and post-secondary degree in related field.", 6,
        ("eligible", [("range_years_minimum", "required", "met", "5 - 7 years of relevant experience")]),
        id="between-with-a-dash",  # pv 344000's shape; 384 store occurrences
    ),
    pytest.param(
        "Minimum of 3 - 5 years experience in the Operations field.", 4,
        ("uncertain", [("scoped_range_years_minimum", "required", "unknown", "3 - 5 years experience in")]),
        id="scoped",  # pv 6240's shape
    ),
    pytest.param(
        "3 - 5+ years of experience in communications, PR, marketing, consulting.", 1,
        ("ineligible", [("scoped_range_years_minimum", "required", "unmet",
                         "3 - 5+ years of experience in")]),
        id="a-plus-on-the-high-end",  # pv 47584
    ),
    pytest.param(
        "6.5 - 10 years of total software development experience.", 1,
        ("ineligible", [("scoped_range_years_minimum", "required", "unmet",
                         "6.5 - 10 years of total software development experience")]),
        id="a-decimal-low-end",  # pv 124692
    ),
    pytest.param(
        "8 - 12years related work experience.", 1,
        ("ineligible", [("scoped_range_years_minimum", "required", "unmet",
                         "8 - 12years related work experience")]),
        id="a-glued-unit",
    ),
    pytest.param(
        "6 months - 2 years of experience.", 1,
        ("eligible", [("total_months_minimum", "required", "met", "6 months - 2 years of experience")]),
        id="months-to-years-total",
    ),
    pytest.param(
        "6 months - 2 years of experience in U.S. banking and international markets.", 1,
        ("uncertain", [("scoped_months_minimum", "required", "unknown",
                        "6 months - 2 years of experience in")]),
        id="months-to-years-scoped",  # pv 20860
    ),
    # No months row reads "technical work"; what matters is that the high end is no 2-year bar.
    pytest.param(
        "3 months - 2 years of technical work to include technical internship.", 1,
        ("uncertain", []),
        id="months-to-years-without-experience",  # pv 308606
    ),
]


@pytest.mark.parametrize("body,years,expected", RANGES)
def test_a_spaced_ascii_dash_range_reads_its_low_end(body: str, years: int, expected, catalog) -> None:  # type: ignore[no-untyped-def]
    assert _read(body, years, catalog) == expected


# Each keeps its cut, so the number after the dash is the bar it has always been.
BULLETS = [
    pytest.param("Python - 5 years of experience.", "5 years of experience.", id="a-word"),
    pytest.param("Requirements - 3+ years of Java.", "3+ years of Java.", id="a-heading-word"),
    pytest.param(
        "10047 - 3+ years of engineering team management experience.",
        "3+ years of engineering team management experience.", id="a-requisition-id",
    ),
    pytest.param(
        "Option 3 - 5 years' experience in an analytics or related field.",
        "5 years' experience in an analytics or related field.", id="an-option-label",  # pv 153762
    ),
    pytest.param(
        "Level 7 - 2+ years proven engineering or maintenance experience.",
        "2+ years proven engineering or maintenance experience.", id="a-level-label",  # pv 262836
    ),
    pytest.param(
        "Headcount 10 - 3+ years of experience in sales.", "3+ years of experience in sales.",
        id="a-larger-number-before-the-dash",
    ),
    pytest.param(
        "SAP FIORI UI5 - 7+ years of experience.", "7+ years of experience.",
        id="a-number-glued-to-a-word",  # pv 119683's shape
    ),
    pytest.param("Section 2 - 3 teams report here.", "3 teams report here.", id="no-time-unit"),
    pytest.param("Openings: 5 • 7 years of experience.", "7 years of experience.", id="a-round-bullet"),
]


@pytest.mark.parametrize("body,after", BULLETS)
def test_a_real_inline_bullet_keeps_its_cut(body: str, after: str) -> None:
    units = [unit for _offset, unit in split_units(body, "sentence")]
    assert units[-1] == after and len(units) == 2


CONTROLS = [
    pytest.param(
        "5-7 years of experience.", 6,
        ("eligible", [("range_years_minimum", "required", "met", "5-7 years of experience")]),
        id="unspaced-dash",
    ),
    pytest.param(
        "5 – 7 years of experience.", 6,
        ("eligible", [("range_years_minimum", "required", "met", "5 – 7 years of experience")]),
        id="spaced-en-dash",
    ),
    pytest.param(
        "2 to 5 years of experience.", 1,
        ("ineligible", [("range_years_minimum", "required", "unmet", "2 to 5 years of experience")]),
        id="t200-low-end",
    ),
    pytest.param(
        "Python - 5 years of experience.", 1,
        ("ineligible", [("total_years_minimum", "required", "unmet", "5 years of experience")]),
        id="inline-bullet-bar",
    ),
    pytest.param(
        "Requirements - 3+ years of Java.", 1,
        ("ineligible", [("domain_years_minimum", "required", "unmet", "3+ years of Java.")]),
        id="inline-bullet-domain-bar",
    ),
    # T237c, NOT BUILT: an unspaced left dash is no cut, so the splitter never touches it, and the
    # digit guards need a space before the dash. 0 store bodies carry it; this pins today's read.
    pytest.param(
        "6 months- 2 years of experience in U.S. banking.", 1,
        ("ineligible", [("scoped_months_minimum", "required", "unknown", "6 months- 2 years of experience in"),
                        ("scoped_years_minimum", "required", "unmet", "2 years of experience in")]),
        id="t237c-unspaced-left-dash-unchanged",
    ),
]


@pytest.mark.parametrize("body,years,expected", CONTROLS)
def test_other_dashes_keep_their_read(body: str, years: int, expected, catalog) -> None:  # type: ignore[no-untyped-def]
    assert _read(body, years, catalog) == expected
