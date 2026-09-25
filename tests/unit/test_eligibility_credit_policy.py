"""T201: a credit or substitution rule is not a bar.

"The first 5 years of experience will be credited at the following rate" read a five-year
`total_years_minimum` and rejected a one-year profile, and "One year of acceptable experience will be
credited ..." wrote a required row, digit or spelled. The count is the SUBJECT of the predicate, so
the predicate is matched at the span's end (`suppressed_by_predicate`): the bar writes no row, and
never a preferred one. A bar followed by a credit rule about SOMETHING ELSE keeps its row.

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


def _years_rows(body: str, catalog) -> tuple[str, list[tuple[str, str, str]]]:  # type: ignore[no-untyped-def]
    result = evaluate(body, FACTS, POLICY, catalog)
    return result.verdict, sorted(
        (r.rule_id, r.requiredness, r.disposition)
        for r in result.requirements
        if r.rule_id.startswith("experience_years:")
    )


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            "The first 5 years of experience will be credited at the following rate",
            id="first-N-years-credited-digit",
        ),
        pytest.param(
            "The first five years of experience will be credited at the following rate",
            id="first-N-years-credited-spelled",
        ),
        pytest.param(
            "One year of acceptable experience will be credited toward the requirement.",
            id="one-year-credited-spelled",
        ),
        pytest.param(
            "1 year of acceptable experience will be credited toward the requirement.",
            id="one-year-credited-digit",
        ),
        pytest.param(
            "Four (4) years of additional software engineering experience on projects with similar "
            "software processes may be substituted for a bachelor’s degree.",
            id="substituted-for-a-degree",  # pv 19952
        ),
        pytest.param(
            "4 years of related experience (in addition to the minimum years of experience "
            "required) may be substituted in lieu of degree.",
            id="substituted-across-an-aside",  # pv 27972
        ),
    ],
)
def test_a_count_that_is_a_credit_rules_subject_writes_no_bar(body: str, catalog) -> None:  # type: ignore[no-untyped-def]
    assert _years_rows(body, catalog) == ("uncertain", [])


@pytest.mark.parametrize(
    "body,rule,count",
    [
        pytest.param(
            "5 years of experience required. Experience will be credited toward seniority.",
            "total_years_minimum", 1, id="credit-rule-in-the-next-sentence",
        ),
        pytest.param("5+ years of experience", "total_years_minimum", 1, id="plain-bar"),
        pytest.param(
            "5+ years of experience is required, and prior experience will be credited toward "
            "seniority.",
            "total_years_minimum", 1, id="a-later-clause-credits-another-noun",
        ),
        pytest.param(
            "Bachelor’s degree and 10+ years of relevant experience (additional experience may "
            "substitute for degree).",
            "total_years_minimum", 1, id="an-aside-substitutes-another-noun",  # pv 161976
        ),
        pytest.param(
            "2+ years of experience in controls software, PLC programming, SCADA development, or "
            "related automation work; substantial internship or co-op experience may be counted "
            "toward this at the hiring manager's discretion.",
            "scoped_years_minimum", 1, id="after-a-semicolon",  # pv 319933
        ),
        pytest.param(
            "2 + years of engineering experience(Internships will be counted towards experience)",
            "scoped_years_minimum", 1, id="the-predicate-inside-an-aside",  # pv 192922
        ),
        pytest.param(
            "A Bachelor’s degree may be substituted for 4 years of experience and a Master’s "
            "Degree may be substituted for 6 years of experience.",
            "total_years_minimum", 2, id="the-next-predicate-has-its-own-subject",  # pv 338256
        ),
    ],
)
def test_a_bar_followed_by_another_nouns_credit_rule_keeps_its_row(  # type: ignore[no-untyped-def]
    body: str, rule: str, count: int, catalog
) -> None:
    assert _years_rows(body, catalog) == (
        "ineligible", [(f"experience_years:{rule}", "required", "unmet")] * count
    )


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            "2 years of experience equals 24 months of education.", id="equals",
        ),
        pytest.param(
            "Two years’ relevant work experience is equivalent to one-year college.",
            id="is-equivalent-to",  # pv 197864
        ),
        pytest.param(
            "2 years of experience is equal to 1 year of college.", id="is-equal-to",
        ),
        pytest.param(
            "2 years of experience counts as one year of college.", id="counts-as",
        ),
    ],
)
def test_a_count_that_is_an_equivalence_rules_subject_writes_no_bar(  # type: ignore[no-untyped-def]
    body: str, catalog
) -> None:
    """T214: an `equals … months` conversion is the same substitution rule as T201's forms."""
    assert _years_rows(body, catalog) == ("uncertain", [])


def test_the_one_year_equivalence_writes_no_met_row(catalog) -> None:  # type: ignore[no-untyped-def]
    assert _years_rows("1 year of experience equals 12 months of education.", catalog) == (
        "uncertain", []
    )


@pytest.mark.parametrize(
    "body,expected",
    [
        pytest.param(
            "1 year of experience required.",
            ("eligible", [("experience_years:total_years_minimum", "required", "met")]),
            id="a-one-year-bar",
        ),
        pytest.param(
            "Pay equals market rate; 3 years of experience required.",
            ("ineligible", [("experience_years:total_years_minimum", "required", "unmet")]),
            id="equals-in-an-earlier-clause",
        ),
        pytest.param(
            "3 years of experience at a level equal to a Senior Engineer.",
            ("ineligible", [("experience_years:total_years_minimum", "required", "unmet")]),
            id="equal-to-without-a-copula",
        ),
        pytest.param(
            "Two years of specialized experience equivalent to the GS-11 level is required.",
            ("ineligible", [("experience_years:scoped_years_minimum", "required", "unmet")]),
            id="federal-equivalent-to-a-grade",
        ),
    ],
)
def test_an_equivalence_word_that_is_not_the_bars_predicate_keeps_the_bar(  # type: ignore[no-untyped-def]
    body: str, expected: tuple[str, list[tuple[str, str, str]]], catalog
) -> None:
    assert _years_rows(body, catalog) == expected


# The equivalence arms suppress a bar only when their OBJECT is an education, credit or time-of-study
# unit. Codex round 1: a level, grade, role or title object is a restatement of the bar, not a
# conversion, and an unrestricted `is equivalent to` turned a real five-year bar `eligible` for a
# one-year profile holding the degree.
FACTS_BACHELOR = Facts(total_years_experience=1, highest_degree="bachelor")


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            "Bachelor's degree required. 5 years of experience is equivalent to a senior level"
            " and is required.",
            id="is-equivalent-to-a-level",  # the Codex sentence
        ),
        pytest.param(
            "Bachelor's degree required. 5 years of experience counts toward a senior title"
            " and is required.",
            id="counts-toward-a-title",
        ),
        pytest.param(
            "Bachelor's degree required. 5 years of experience will count toward a senior title"
            " and is required.",
            id="will-count-toward-a-title",
        ),
        pytest.param(
            "Bachelor's degree required. 5 years of experience counts as senior level experience"
            " and is required.",
            id="counts-as-experience",
        ),
        pytest.param(
            "Bachelor's degree required. 5 years of experience equals a senior level and is"
            " required.",
            id="equals-a-level",
        ),
        pytest.param(
            "Bachelor's degree required. 5 years of experience is equal to the GS-11 level and is"
            " required.",
            id="is-equal-to-a-grade",
        ),
        pytest.param(
            "Bachelor's degree required. 5 years of experience is considered equivalent to a"
            " Senior Engineer and is required.",
            id="considered-equivalent-to-a-role",
        ),
        # Codex round 2: an education word that BEGINS a level or role object is not the object.
        pytest.param(
            "Bachelor's degree required. 5 years of experience is equivalent to a master's level"
            " position and is required.",
            id="education-word-begins-a-level",
        ),
        pytest.param(
            "Bachelor's degree required. 5 years of experience is equivalent to a college professor"
            " role and is required.",
            id="education-word-begins-a-role",
        ),
        pytest.param(
            "Bachelor's degree required. 5 years of experience is equivalent to a bachelor's-level"
            " role and is required.",
            id="hyphenated-education-level",
        ),
        pytest.param(
            "Bachelor's degree required. 5 years of experience is equivalent to a PhD-level scientist"
            " and is required.",
            id="phd-level-scientist",
        ),
        pytest.param(
            "Bachelor's degree required. 5 years of experience counts as a degree-level position and"
            " is required.",
            id="degree-level-position",
        ),
        pytest.param(
            "Bachelor's degree required. 5 years of experience equals a high school teacher role and"
            " is required.",
            id="high-school-teacher",
        ),
        pytest.param(
            "Bachelor's degree required. 5 years of experience is equivalent to a university lecturer"
            " position and is required.",
            id="university-lecturer",
        ),
    ],
)
def test_an_equivalence_to_a_level_or_title_keeps_the_bar(  # type: ignore[no-untyped-def]
    body: str, catalog
) -> None:
    result = evaluate(body, FACTS_BACHELOR, POLICY, catalog)
    assert (result.verdict, sorted(
        (r.rule_id, r.requiredness, r.disposition) for r in result.requirements
    )) == ("ineligible", [
        ("degree:bachelor_required", "required", "met"),
        ("experience_years:total_years_minimum", "required", "unmet"),
    ])


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            "Education: Bachelor’s degree in Accounting, Finance, Taxation, or a related field; or"
            " equivalent work experience (Two years’ relevant work experience is equivalent to"
            " one-year college",
            id="pv197864",
        ),
        pytest.param(
            "Bachelor’s Degree in Computer Science, Electrical Engineering, Information Systems, or"
            " closely related field of study or equivalent work experience (two years’ relevant"
            " work experience is equivalent to one-year college)",
            id="pv197866-197876-224470-273393",
        ),
        pytest.param(
            "Required Education: Bachelor’s Degree in Business Administration, Healthcare"
            " Administration, Health Information Management or related field; or equivalent work"
            " experience (Two years’ relevant experience is equivalent to one-year college);"
            " Master's degree (MBA, MHA, MPH) strongly preferred.",
            id="pv197879",
        ),
        pytest.param(
            "Bachelor or International Equivalency degree in Cybersecurity, Computer Science,"
            " Electrical Engineering, Information Systems, or closely related field of study; or"
            " equivalent work experience (Two years’ relevant work experience is equivalent to"
            " one-year college)",
            id="pv197880",
        ),
        pytest.param(
            "Education: Bachelor’s Degree or equivalent work experience (Two years’ relevant work"
            " experience is equivalent to one-year college)",
            id="pv258730",
        ),
        pytest.param(
            "6 years of additional experience is equivalent to a Bachelor’s degree.",
            id="pv127257",
        ),
        pytest.param("2 years of experience is equal to 24 months of education.", id="months-of"),
        pytest.param("2 years of experience counts toward 30 credit hours.", id="credit-hours"),
        pytest.param("2 years of experience equals one year of college coursework.", id="coursework"),
        pytest.param(
            "2 years of experience is equivalent to a bachelor's degree in computer science.",
            id="degree-in-a-field",
        ),
        pytest.param("2 years of experience is equivalent to a graduate degree.", id="graduate-degree"),
        pytest.param("2 years of experience is equivalent to one year of college education.",
                     id="college-education"),
    ],
)
def test_an_equivalence_to_education_or_credit_still_writes_no_years_row(  # type: ignore[no-untyped-def]
    body: str, catalog
) -> None:
    result = evaluate(body, FACTS_BACHELOR, POLICY, catalog)
    assert [r.rule_id for r in result.requirements if r.rule_id.startswith("experience_years:")] == []
