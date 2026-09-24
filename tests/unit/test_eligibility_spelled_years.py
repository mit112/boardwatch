"""T193: a years count spelled as a word, with or without its digit in parentheses.

"five (5) years of experience" and "four (4) years of related experience required" wrote no
`experience_years` row at all, where "5 years of experience" writes its bar: every years pattern's
number group read digits only. The zero-row posting then read `uncertain` on nothing. The number
group now reads `<word> (<digit>)` and the bare words one ... twenty (a closed list); the digit is
the capture when present, else the word's value.

The profile declares 1 year and the near-miss band is off, so every bar above one year is decisive.
"""

from pathlib import Path

import pytest

from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.engine import evaluate
from boardwatch.eligibility.facts import Facts, Policy

FACTS = Facts(total_years_experience=1)
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


def _read(body: str, catalog) -> tuple[str, list[tuple[str, str, str, str]]]:  # type: ignore[no-untyped-def]
    result = evaluate(body, FACTS, POLICY, catalog)
    return result.verdict, sorted(
        (r.rule_id, r.requiredness, r.disposition, r.requirement_text) for r in result.requirements
    )


# The run-474 audit's two sentences (D-589): each is a required bar a one-year profile misses.
AUDIT = [
    pytest.param(
        "Bachelor’s degree or equivalent in Computer Science, Engineering, or related and five (5) "
        "years of experience as a Software Developer or related",
        [
            ("degree:bachelor_or_equivalent_required", "required", "unknown"),
            ("experience_years:scoped_years_minimum", "required", "unmet"),
        ],
        id="posting-221163-five-(5)-years",  # pv 224384
    ),
    pytest.param(
        "Associates degree in Computer Science, Information Technology, or related field with four "
        "(4) years of related experience required.",
        [("experience_years:scoped_years_minimum", "required", "unmet")],
        id="pv-171-four-(4)-years",
    ),
]


@pytest.mark.parametrize("body,rows", AUDIT)
def test_the_audit_sentences_write_their_required_bar(body: str, rows, catalog) -> None:  # type: ignore[no-untyped-def]
    verdict, got = _read(body, catalog)
    assert [row[:3] for row in got] == rows
    assert verdict == "ineligible"


# Each spelled shape reads exactly as its digit twin: same verdict, same rows, same stored text.
TWINS = [
    pytest.param("five (5) years of experience.", "5 years of experience.", id="total-word-digit"),
    pytest.param("Five years of experience.", "5 years of experience.", id="total-bare-word"),
    pytest.param("one (1) year of experience required.", "1 year of experience required.", id="one"),
    pytest.param(
        "twenty (20) years of experience.", "20 years of experience.", id="twenty-the-list-end"
    ),
    pytest.param(
        "At least three (3) years of experience with Python.",
        "At least 3 years of experience with Python.", id="scoped",
    ),
    pytest.param(
        "Seven years of building distributed systems.", "7 years of building distributed systems.",
        id="activity",
    ),
    pytest.param("Experience: five (5) years", "Experience: 5 years", id="labeled"),
    pytest.param(
        "five (5) years of experience is preferred.", "5 years of experience is preferred.",
        id="preferred",
    ),
    pytest.param(
        "Preferred: five (5) years of experience.", "Preferred: 5 years of experience.",
        id="preferred-hedge-first",
    ),
    # The escapes read the spelled count too, or the new bar would reject where its digit twin
    # abstains or stands down.
    pytest.param(
        "Bachelor's degree or five (5) years of experience.",
        "Bachelor's degree or 5 years of experience.", id="degree-alternative-abstains",
    ),
    pytest.param(
        "five (5) years of experience or a Bachelor's degree.",
        "5 years of experience or a Bachelor's degree.", id="years-first-degree-alternative-abstains",
    ),
    pytest.param(
        "With over twenty years of experience, our team is committed to quality.",
        "With over 20 years of experience, our team is committed to quality.",
        id="company-tenure-stands-down",
    ),
]


@pytest.mark.parametrize("spelled,digits", TWINS)
def test_a_spelled_count_reads_as_its_digit_twin(spelled: str, digits: str, catalog) -> None:  # type: ignore[no-untyped-def]
    assert _read(spelled, catalog) == _read(digits, catalog)


def test_the_parenthesised_digit_is_the_capture(catalog) -> None:  # type: ignore[no-untyped-def]
    # Word and digit disagree: the digit is what the posting's number says.
    _, rows = _read("five (8) years of experience.", catalog)
    assert rows == [
        ("experience_years:total_years_minimum", "required", "unmet",
         "At least 8 years of total experience"),
    ]


# CONTROLS: stay as they were.
@pytest.mark.parametrize(
    "body",
    [
        pytest.param("Two (2) weeks of onboarding training.", id="weeks-not-years"),
        pytest.param("Within thirty (30) days of hire.", id="days-not-years"),
        pytest.param("twenty-five years of experience.", id="compound-word-outside-the-list"),
        pytest.param("Someone with years of experience.", id="no-count"),
        # `domain_years_minimum` (no experience noun) stays digits-only: spelled, it read prose.
        pytest.param(
            "The vacation accrual rate is 13 days annually for the first three years of employment.",
            id="domain-benefits-prose",
        ),
        pytest.param("three (3) years of Kubernetes, Docker, or Terraform", id="domain-word-digit"),
    ],
)
def test_a_spelled_count_on_no_years_bar_writes_nothing(body: str, catalog) -> None:  # type: ignore[no-untyped-def]
    assert _read(body, catalog) == ("uncertain", [])


def test_the_digit_form_is_unchanged(catalog) -> None:  # type: ignore[no-untyped-def]
    assert _read("5 years of experience.", catalog) == (
        "ineligible",
        [("experience_years:total_years_minimum", "required", "unmet",
          "At least 5 years of total experience")],
    )
