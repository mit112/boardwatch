"""T178: an experience UPPER bound is a ceiling, not a minimum.

"Less than 2 years of experience." rejected a 1-year profile as `total_years_minimum unmet '1 < 2'`:
every years pattern starts at the NUMBER, so the comparative before it was invisible. A cue from the
catalog's closed `years_ceiling` list that TOUCHES the bar (whitespace only between them) carries the
bar as its family's ceiling pattern (`bounded_above_as`), span widened over the cue. A ceiling is MET
when the profile total is under it and abstains otherwise -- never UNMET, because a ceiling sentence
is often one rung of a level ladder, an invitation or a pay table rather than a bar.

The profile declares 1 year and the near-miss band is off, so a minimum reading of any of these bars
is decisive -- the headline cases can only leave `ineligible` if the ceiling reading replaces it.
"""

from pathlib import Path

import pytest

from boardwatch.eligibility.catalog import CatalogError, load_rules
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
def catalog(tmp_path_factory):
    return load_rules(tmp_path_factory.mktemp("no-override"))


def _rows(catalog, body: str, years: int | None = 1):
    result = evaluate(body, Facts(total_years_experience=years), POLICY, catalog)
    rows = sorted(
        (
            r.rule_id.split(":")[1], r.disposition,
            body[r.jd_locator["span"][0]:r.jd_locator["span"][1]],
        )
        for r in result.requirements
    )
    return result.verdict, rows


# The review's eight shapes (REVIEW-2026-09-23 F1, probe p1_ceiling_bars.py), each with the
# ceiling row it must now write and the raw span that row cites.
CEILINGS = [
    pytest.param("<2 years of experience.", "total_years_maximum", "<2 years of experience",
                 id="lt-sign"),
    pytest.param("Less than 2 years of experience.", "total_years_maximum",
                 "Less than 2 years of experience", id="less-than"),
    pytest.param("Fewer than 3 years of experience.", "total_years_maximum",
                 "Fewer than 3 years of experience", id="fewer-than"),
    pytest.param("Under 2 years of experience.", "total_years_maximum",
                 "Under 2 years of experience", id="under"),
    pytest.param("Maximum of 3 years of experience.", "total_years_maximum",
                 "Maximum of 3 years of experience", id="maximum-of"),
    pytest.param("At most 3 years of experience.", "total_years_maximum",
                 "At most 3 years of experience", id="at-most"),
    pytest.param("2 years of experience or less.", "total_years_maximum",
                 "2 years of experience or less", id="or-less"),
    pytest.param("This role is for candidates with less than 3 years of experience.",
                 "total_years_maximum", "less than 3 years of experience",
                 id="candidate-sentence"),
    pytest.param("Candidates with <2 years of professional experience.", "total_years_maximum",
                 "<2 years of professional experience", id="lt-sign-adjective-run"),
    # The two live store sentences the review sized (pv 159086, pv 66765): both skill-scoped.
    pytest.param(
        "Has less than 3 years of post-MBA experience / Relevant experience and is looking to "
        "build a career at the intersection of business, technology, and product management.",
        "scoped_years_maximum", "less than 3 years of post-MBA experience / Relevant experience",
        id="pv159086-scoped",
    ),
    pytest.param("Generally less than 2 years’ experience in a related field",
                 "scoped_years_maximum", "less than 2 years’ experience in", id="pv66765-scoped"),
]


@pytest.mark.parametrize("body,rule,span", CEILINGS)
def test_a_ceiling_the_profile_is_under_is_met(catalog, body, rule, span) -> None:
    assert _rows(catalog, body) == ("eligible", [(rule, "met", span)])


def test_a_months_bar_under_a_ceiling_is_carried_too(catalog) -> None:
    body = "Less than 18 months of experience."
    assert _rows(catalog, body) == (
        "eligible", [("total_years_maximum", "met", "Less than 18 months of experience")]
    )


# Store sentences whose ceiling is not a bar on the posting: a level ladder (pv 197815), an
# invitation (pv 376127) and a pay table (pv 367450). A senior total must not be rejected by them.
EXCEEDED = [
    pytest.param("Less than 2 years of experience.", "total_years_maximum", id="total"),
    pytest.param("Less than 3 years of Java experience.", "scoped_years_maximum", id="scoped"),
    pytest.param(
        "Research Associate I: Bachelor’s degree and fewer than 3 years of relevant, "
        "post-baccalaureate professional research experience.",
        "scoped_years_maximum", id="pv197815-ladder",
    ),
    pytest.param("If fewer than 6 years of experience, still encouraged to apply!",
                 "total_years_maximum", id="pv376127-invitation"),
    pytest.param(
        "We're excited to share our starting pay rate for new graduate registered nurses with "
        "less than 1 year of experience is $36.00/hour.",
        "total_years_maximum", id="pv367450-pay-table",
    ),
]


@pytest.mark.parametrize("body,rule", EXCEEDED)
def test_exceeding_a_ceiling_abstains_and_never_rejects(catalog, body, rule) -> None:
    verdict, rows = _rows(catalog, body, 10)
    assert verdict == "uncertain"
    assert [(r, d) for r, d, _s in rows] == [(rule, "unknown")]


def test_a_total_at_the_ceiling_abstains(catalog) -> None:
    """Whole years cannot say which side of `less than 2` (strict) or `at most 2` a 2 sits."""
    for body in ("Less than 2 years of experience.", "At most 2 years of experience."):
        verdict, [(rule, disposition, _span)] = _rows(catalog, body, 2)
        assert (verdict, rule, disposition) == ("uncertain", "total_years_maximum", "unknown")


def test_an_undeclared_total_abstains_on_a_ceiling(catalog) -> None:
    verdict, rows = _rows(catalog, "Less than 2 years of experience.", None)
    assert verdict == "uncertain"
    assert [(r, d) for r, d, _s in rows] == [("total_years_maximum", "unknown")]


# CONTROLS: a floor stays a floor. `(no|not) less than` is the catalog's comparative-FLOOR idiom.
FLOORS = [
    pytest.param("Minimum 2 years of experience.", "Minimum 2", id="minimum"),
    pytest.param("2+ years of experience.", "2+", id="plus"),
    pytest.param("2-4 years of experience.", "2-4", id="range"),
    pytest.param("At least 2 years of experience.", "at least", id="at-least"),
    pytest.param("No less than 2 years of experience.", "no-less-than", id="no-less-than"),
    pytest.param("More than 2 years of experience.", "more-than", id="more-than"),
]


@pytest.mark.parametrize("body,_label", FLOORS)
def test_a_floor_is_unchanged(catalog, body, _label) -> None:
    verdict, rows = _rows(catalog, body)
    assert verdict == "ineligible"
    assert [(r, d) for r, d, _s in rows] in (
        [("total_years_minimum", "unmet")], [("range_years_minimum", "unmet")]
    )


def test_a_ceiling_reaches_only_the_bar_it_touches(catalog) -> None:
    """The cue qualifies THIS number: a second floor in the same clause keeps its minimum."""
    verdict, rows = _rows(
        catalog, "Less than 2 years of management experience and 5 years of experience."
    )
    assert verdict == "ineligible"
    assert [(r, d) for r, d, _s in rows] == [
        ("scoped_years_maximum", "met"), ("total_years_minimum", "unmet"),
    ]


def test_a_word_that_merely_precedes_a_bar_is_not_a_ceiling(catalog) -> None:
    """`under` is a ceiling only touching the number; after the bar it is ordinary prose."""
    verdict, rows = _rows(catalog, "5 years of experience under pressure.")
    assert (verdict, [(r, d) for r, d, _s in rows]) == (
        "ineligible", [("total_years_minimum", "unmet")]
    )


def test_a_trailing_or_less_is_a_ceiling_only_touching_the_bar(catalog) -> None:
    """`or less` later in the sentence qualifies another quantity, not the bar."""
    verdict, rows = _rows(catalog, "5 years of experience, with travel of 10% or less.")
    assert (verdict, [(r, d) for r, d, _s in rows]) == (
        "ineligible", [("total_years_minimum", "unmet")]
    )


def test_an_escape_that_waives_the_bar_still_abstains_its_ceiling(catalog) -> None:
    """The abstain is carried with the bar, never folded: a ceiling the profile is not under reads
    `unknown` BECAUSE the posting may waive it, and says so. (One it is under reads `met`: the
    engine never lets a waiver make a satisfied bar undecidable.)"""
    body = "Less than 2 years of experience or a Bachelor's degree."
    result = evaluate(body, Facts(total_years_experience=5), POLICY, catalog)
    [row] = result.requirements
    assert (result.verdict, row.rule_id, row.disposition) == (
        "uncertain", "experience_years:total_years_maximum", "unknown"
    )
    assert row.rationale.startswith("the posting may waive this:")


_FAMILY = """
version: 1
negation_cues: ["not"]
families:
  - id: experience_years
    label: Years
    tier: profile
    fact: total_years_experience
    answer_type: int
    default_policy: preference
    question: "Years?"
    fields:
      - name: total_years_experience
        type: int
    implies_vocabulary: [total_years_minimum, total_years_maximum, total_years_preferred]
    patterns:
      - id: floor
        requiredness: required
        implies: total_years_minimum
        scope: sentence
        requirement_text: "floor"
        pattern: '(?P<years>\\d+) years'
        bounded_above_by: ["under"]
        bounded_above_as: {target}
      - id: ceiling
        requiredness: required
        implies: total_years_maximum
        scope: sentence
        requirement_text: "ceiling"
        pattern: '(?!)'
      - id: hedged
        requiredness: preferred
        implies: total_years_preferred
        scope: sentence
        requirement_text: "hedged"
        pattern: '(?P<years>\\d+) years preferred'
"""


@pytest.mark.parametrize("target", ["missing", "hedged"])
def test_the_catalog_refuses_a_ceiling_target_that_is_not_a_required_pattern(
    tmp_path: Path, target: str
) -> None:
    (tmp_path / "rules.yaml").write_text(_FAMILY.format(target=target), encoding="utf-8")
    with pytest.raises(CatalogError, match="bounded_above_as"):
        load_rules(tmp_path)


def test_the_catalog_accepts_a_required_ceiling_target(tmp_path: Path) -> None:
    (tmp_path / "rules.yaml").write_text(_FAMILY.format(target="ceiling"), encoding="utf-8")
    floor = load_rules(tmp_path).family("experience_years").patterns[0]
    assert floor.bounded_above_as == "ceiling"
    assert len(floor.bounded_above_by) == 1
