"""T170 (prototype): a years bar whose OWN sentence ends by calling it preferred.

`"5+ years of experience, not required but preferred."` rejected a 2-year profile: the hedge sits
in a later clause than the bar, and the hedge suppressor is clause-scoped (`detect._clause_bounds`).
Widening that scope to the sentence is wrong the other way, because the commonest hedge after a
bar qualifies a SUB-CLAUSE of it. The line is structural (`detect._hedged_tail`): the hedge must be
the sentence-final predicate, and everything between the bar and it must be the bar's own
complement -- one phrase, no clause break, no second head, no adjunct or modifier phrase, and commas
only inside a closed list.

Every body is a real sentence from the live store, trimmed to the bar's own sentence. The profile
declares 1 year and the near-miss band is off, so every bar above one year is decisive and a
WILL-NOT case can only stay `ineligible` if the bar's required row survives.
"""

from pathlib import Path

import pytest

from boardwatch.eligibility.catalog import CatalogError, load_rules
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

# DEMOTE: the bar's pattern has a `preferred` twin, so the hedged bar is carried as that twin's
# row -- exactly the row its one-line form ("5+ years of experience preferred.") already writes.
# A preferred row never blocks, so the posting is decided by the rest of its rows.
DEMOTED = [
    pytest.param(
        "5+ years of experience, not required but preferred.",
        "total_years_preferred", id="T163-negated-requirement-then-hedge",
    ),
    pytest.param(
        "2+ years of experience selling into the U.S. Government and private government "
        "contractors preferred",
        "total_years_preferred", id="open-complement-no-delimiter",
    ),
    pytest.param(
        "3-5 years' experience selling to residential or commercial plumbing contractors, HVAC "
        "contractors, builders, remodelers, or other residential trade customers preferred",
        "range_years_preferred", id="range-bar-closed-oxford-list",
    ),
]

# DROP: the bar's pattern has no `preferred` twin, so the hedged bar is dropped -- exactly what
# the clause-scoped hedge already does to its one-line form. These bodies carry nothing else, so
# zero rows reads `uncertain` (`_no_evaluable_requirement`), never a clear by silence.
DROPPED = [
    pytest.param(
        "2-4 years of retirement industry experience, preferred",
        id="comma-then-bare-hedge",
    ),
    pytest.param(
        "3+ years of experience in strategic sourcing and supplier development – Highly "
        "preferred",
        id="dash-then-intensified-hedge",
    ),
    pytest.param(
        "At least 4 years of experience in fire and life safety system inspection or design "
        "preferred.",
        id="open-complement-with-internal-coordinators",
    ),
    pytest.param(
        "2+ years of experience in consulting, investment banking, or private equity a plus",
        id="closed-oxford-list-then-a-plus",
    ),
    pytest.param(
        "15+ years of experience in marketing, marketing operations, demand generation "
        "operations, or revenue operations within a matrixed or global enterprise environment is "
        "highly preferred",
        id="copula-and-intensifier",
    ),
    pytest.param(
        "5+ years of professional experience in accounting and/or finance (preferred)",
        id="bare-aside-hedge-after-complement",
    ),
    pytest.param(
        "3+ years of related electrical, mechanical, technical, manufacturing, construction, "
        "commissioning, or field service experience preferred.",
        id="the-bars-own-list-continues-past-the-span",
    ),
    pytest.param(
        "2+ years of shipping, receiving, or manufacturing experience preferred.",
        id="bar-stops-short-of-its-head-then-a-comma",
    ),
    pytest.param(
        "4+ years of experience building and developing software would be preferred.",
        id="bar-stops-short-of-its-head-then-a-coordinator",
    ),
]

# WILL NOT: the hedge belongs to a sub-clause, a second noun, a second bar, or nothing at all.
# The bar keeps its required row, so the posting stays `ineligible`.
KEPT = [
    pytest.param(
        "3+ years of retail management experience, preferably in a specialty or culinary retail "
        "environment.",
        "scoped_years_minimum", id="preferably-in-X",
    ),
    pytest.param(
        "3–5 years of experience in payroll processing or related field, ideally within a "
        "multi-country EMEA environment",
        "scoped_range_years_minimum", id="ideally-within-X-not-sentence-final",
    ),
    pytest.param(
        "8-10 years of progressive experience in supply chain operations, procurement, or "
        "manufacturing within the high-tech industry (IT hardware, electronics manufacturing "
        "preferred).",
        "scoped_range_years_minimum", id="parenthetical-X-preferred",
    ),
    pytest.param(
        "2 years of experience in Identity and Access Management, with a focus on RBAC "
        "preferred.",
        "scoped_years_minimum", id="with-a-focus-on-X-preferred",
    ),
    pytest.param(
        "7 years of experience in marketing, strategy, or client engagement, with financial "
        "services experience preferred",
        "scoped_years_minimum", id="comma-with-X-preferred",
    ),
    pytest.param(
        "5+ years’ experience in the Pharmaceutical/Biotechnology industry with medical coding "
        "experience using WHODrug and MedDRA preferred",
        "scoped_years_minimum", id="with-X-preferred-no-comma",
    ),
    pytest.param(
        "3 years of experience, banking experience preferred.",
        "total_years_minimum", id="different-noun-preferred",
    ),
    pytest.param(
        "5 years nursing experience required, pediatric and ambulatory experience preferred.",
        "scoped_years_minimum", id="bar-required-other-noun-preferred",
    ),
    pytest.param(
        "5+ years industry experience in financial services or a related field, 10+ years "
        "preferred",
        "scoped_years_minimum", id="N-then-M-preferred",
    ),
    pytest.param(
        "2 years of management experience; fitness/personal training management is a plus!",
        "scoped_years_minimum", id="a-plus-on-another-noun",
    ),
    pytest.param(
        "5+ years of contracting experience in the enterprise software/SaaS space, state and "
        "local governments strongly preferred",
        "scoped_years_minimum", id="one-comma-new-noun-phrase",
    ),
    pytest.param(
        "8+ years of experience with Java Microservices, Rest API, Mongo DB, Oracle, Distributed "
        "computing using OpenShift, Kafka integration and Pega(Preferred).",
        "scoped_years_minimum", id="hedge-glued-to-the-last-item",
    ),
    pytest.param(
        "4-6 years of experience within Financial Services, in a Risk Management, Audit or "
        "Compliance role preferred",
        "range_years_minimum", id="comma-then-prepositional-adjunct",
    ),
    pytest.param(
        "3+ years of leadership and people management experience at managing senior manager "
        "level above persons, and experience of 2nd line management preferred",
        "scoped_years_minimum", id="second-experience-head",
    ),
    pytest.param(
        "7 years of experience in pharmaceutical manufacturing Some medical device engineering "
        "and/or quality assurance experience preferred",
        "scoped_years_minimum", id="lost-sentence-break",
    ),
    # Each case below is one that ONE guard alone rejects in the live store, so each guard is
    # pinned by a real sentence rather than only by a case another guard also catches.
    pytest.param(
        "3-7 years’ experience in mechanical design engineering; Medical device experience "
        "strongly preferred",
        "scoped_range_years_minimum", id="semicolon-clause-break",
    ),
    pytest.param(
        "5 years of experience in a Medical Science Liaison or other relevant medical role, and/or "
        "at least 2 years in a relevant managerial or leadership position in industry is strongly "
        "preferred.",
        "scoped_years_minimum", id="second-duration-in-the-tail",
    ),
    pytest.param(
        "5+ years of execution trading experience required, and buy-side institution (asset "
        "management or hedge fund) experience is a plus.",
        "scoped_years_minimum", id="bar-marked-required-then-a-plus",
    ),
    pytest.param(
        "Experience: 2-3+ years of hands-on e-commerce experience, specifically within the Beauty, "
        "Cosmetics, Skincare, or Personal Care industry preferred.",
        "labeled_years_minimum", id="specifically-within-X-preferred",
    ),
    pytest.param(
        "5+ years high-level customer care experience Managing/supervising phlebotomy operations "
        "and teams experience preferred BS/BA degree (preferred)",
        "scoped_years_minimum", id="a-hedge-inside-the-complement",
    ),
    pytest.param(
        "3+ years of experience in Sales or Marketing for Construction Supplies with a proven "
        "track record delivering results and experience selling to high-level executives, "
        "C-Suite, and jobsite directors preferred",
        "scoped_years_minimum", id="with-a-track-record-phrase",
    ),
    pytest.param(
        "2+ years of industry experience, with experience in cloud security and/or performance "
        "industries preferred.",
        "domain_list_years_minimum", id="span-crosses-into-a-second-head",
    ),
    pytest.param(
        "8 years of relevant experience and a BA/BS degree preferred.",
        "total_years_minimum", id="bar-at-its-head-then-and-a-new-noun",
    ),
]


@pytest.fixture(scope="module")
def catalog(tmp_path_factory: pytest.TempPathFactory):  # type: ignore[no-untyped-def]
    return load_rules(tmp_path_factory.mktemp("no-override"))


def _rows(result) -> list[list[str]]:  # type: ignore[no-untyped-def]
    return sorted([r.rule_id, r.requiredness, r.disposition] for r in result.requirements)


@pytest.mark.parametrize(("body", "twin"), DEMOTED)
def test_a_hedged_bar_with_a_twin_is_carried_as_the_twin(catalog, body: str, twin: str) -> None:  # type: ignore[no-untyped-def]
    result = evaluate(body, FACTS, POLICY, catalog)
    assert _rows(result) == [[f"experience_years:{twin}", "preferred", "unmet"]]
    assert result.verdict == "eligible"
    # The demoted row still cites the posting: its span quotes the bar through its hedge.
    (row,) = result.requirements
    start, end = row.jd_locator["span"]
    assert body[start:end].startswith(body.split(" ")[0])
    assert body[start:end].rstrip(".").lower().endswith(("preferred", "a plus"))


@pytest.mark.parametrize("body", DROPPED)
def test_a_hedged_bar_without_a_twin_is_dropped(catalog, body: str) -> None:  # type: ignore[no-untyped-def]
    result = evaluate(body, FACTS, POLICY, catalog)
    assert _rows(result) == []
    assert result.verdict == "uncertain"


@pytest.mark.parametrize(("body", "rule"), KEPT)
def test_a_hedge_on_a_sub_clause_keeps_the_bar(catalog, body: str, rule: str) -> None:  # type: ignore[no-untyped-def]
    result = evaluate(body, FACTS, POLICY, catalog)
    assert [f"experience_years:{rule}", "required", "unmet"] in _rows(result)
    assert result.verdict == "ineligible"


def test_a_twin_already_in_reach_is_not_written_twice(catalog) -> None:  # type: ignore[no-untyped-def]
    """`total_years_preferred` reaches a hedge 25 characters on, so here it fired beside the
    required row and the posting was rejected anyway. The demoted row must not duplicate it."""
    result = evaluate("5+ years of experience, preferred.", FACTS, POLICY, catalog)
    assert _rows(result) == [["experience_years:total_years_preferred", "preferred", "unmet"]]
    assert result.verdict == "eligible"


def test_a_plain_bar_is_untouched(catalog) -> None:  # type: ignore[no-untyped-def]
    """CONTROL, must stay green on both sides of the change."""
    result = evaluate("5+ years of experience required.", FACTS, POLICY, catalog)
    assert _rows(result) == [["experience_years:total_years_minimum", "required", "unmet"]]
    assert result.verdict == "ineligible"


HEDGED_AS = """
version: 1
negation_cues: ["not"]
families:
  - id: degree
    label: Degree
    tier: profile
    fact: highest_degree
    answer_type: choice
    default_policy: preference
    question: "Highest degree?"
    fields:
      - name: highest_degree
        type: choice
        choices: [none, bachelor]
        ranks: {{none: 0, bachelor: 3}}
    implies_vocabulary: [degree_required, degree_preferred]
    exclusive_groups: []
    patterns:
      - id: bachelor_required
        requiredness: required
        implies: degree_required
        scope: sentence
        required_rank: 3
        requirement_text: "A bachelor's degree is required"
        hedged_by_tail: ["preferred"]
        hedged_as: {target}
        pattern: "bachelor"
      - id: bachelor_preferred
        requiredness: preferred
        implies: degree_preferred
        scope: sentence
        required_rank: 3
        requirement_text: "A bachelor's degree is preferred"
        pattern: "bachelor.{{0,20}}preferred"
"""


@pytest.mark.parametrize("target", ["bachelor_required", "no_such_pattern"])
def test_hedged_as_must_name_a_preferred_pattern_of_the_family(
    tmp_path: Path, target: str
) -> None:
    (tmp_path / "rules.yaml").write_text(HEDGED_AS.format(target=target), encoding="utf-8")
    with pytest.raises(CatalogError, match="hedged_as"):
        load_rules(tmp_path)


def test_hedged_as_carries_a_valid_target(tmp_path: Path) -> None:
    """POSITIVE CONTROL for the two refusals above: a real preferred target loads."""
    (tmp_path / "rules.yaml").write_text(
        HEDGED_AS.format(target="bachelor_preferred"), encoding="utf-8"
    )
    pattern = load_rules(tmp_path).family("degree").patterns[0]
    assert pattern.hedged_as == "bachelor_preferred"
    assert [rx.pattern for rx in pattern.hedged_by_tail] == ["preferred"]
