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
from string import Template

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
    # T170d CONTROL (coordinator correction): a bare second `experience` with no `with` before it
    # is the bar's OWN coordinated list closing out, not a second requirement -- the v1 C6 fix
    # (1b64e1b0) wrongly rejected this one; the with-gated v2 fix must still demote it. pv 236615.
    pytest.param(
        "2+ years experience prior Construction Project Management or Project Coordinator "
        "experience, preferred",
        "total_years_preferred", id="T170d-bare-second-head-no-with-still-demotes",  # pv 236615
    ),
    # T202: a degree's LENGTH is not a second duration, spelled or digit, so the hedge still
    # predicates the bar. `two (2) year college` stopped it and rejected a one-year profile.
    pytest.param(
        "2+ years' experience working in a manufacturing setting or a Two-year degree or "
        "certificate from an accredited two (2) year college, university, or technical school "
        "preferred",
        "total_years_preferred", id="T202-spelled-year-college",  # pv 323521
    ),
    pytest.param(
        "2+ years' experience working in a manufacturing setting or a Two-year degree or "
        "certificate from an accredited 2 year college, university, or technical school preferred",
        "total_years_preferred", id="T202-digit-year-college",
    ),
]

# DROP: a TOTAL bar whose preferred twin cannot read the posting's wording. Its one-line hedge
# drops it, as before T173 (only a bar `hedged_as` a carrier is carried on that hedge). This body
# carries nothing else, so zero rows reads `uncertain` (`_no_evaluable_requirement`), never a
# clear by silence.
DROPPED = [
    # T180 F6: `an advantage` is catalog vocabulary now, and here it sits in the bar's own clause,
    # so the unit-scoped hedge drops it as it drops `... is preferred but not required.` (DESIGN
    # §2 listed it as a known miss). No twin reads past `auditing`, so no preferred row. pv 217254.
    pytest.param(
        "8+ years of experience auditing in a financial institution or similar public accounting "
        "experience in the financial services industry is an advantage but not required.",
        id="an-advantage-but-not-required-in-the-bars-own-clause",
    ),
]

# SCOPED: a scoped, activity or domain bar has no `preferred` wording of its own, so the hedged
# bar is carried as the `scoped_years_preferred` carrier (T173) -- the row its one-line form now
# writes too. It resolves only in the direction the total forces, so a 1-year profile is `unmet`
# on it, and a preferred row never blocks.
SCOPED = [
    pytest.param(
        "2-4 years of retirement industry experience, preferred",
        id="comma-then-bare-hedge",
    ),
    # T170d (C6, v3): a capitalised `Experience` after the bar's own `with` is a proper noun, not a
    # second head -- the bare-head guard is case-sensitive like the break guards. pv 232543.
    pytest.param(
        "5+ years of experience with Adobe Experience Cloud and Sitecore preferred",
        id="C6-capitalised-Experience-in-a-product-name-is-not-a-head",
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
    # A `with` that is the head's own preposition, or a gerund's, still continues the bar when
    # what follows is its object rather than a modifier phrase (T170b controls).
    pytest.param(
        "3+ years’ experience with innovative products in the Geosynthetics and Stormwater "
        "Management space, preferred",
        id="span-ends-in-with-then-its-object",  # pv 236742
    ),
    pytest.param(
        "5+ years of experience with software configuration, business process analysis, and/or "
        "end-user training is preferred.",
        id="the-heads-own-with-then-a-closed-list",  # pv 117957
    ),
    pytest.param(
        "3+ years of experience on a manufacturing floor working with technical issues and "
        "material flow preferred",
        id="a-gerunds-with-then-its-object",  # pv 208039
    ),
    pytest.param(
        "3-5 years legal and/or compliance/regulatory experience with a national securities "
        "exchange or self-regulatory organization, registered broker-dealer, registered investment "
        "adviser, proprietary trading firm, or other financial institution is preferred.",
        id="the-heads-own-with-then-a-determiner-and-its-object",  # pv 305901
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
    # T170d (C6, v2): a BARE second head is a second requirement only when it is the object of a
    # WITH-adjunct -- `_TAIL_NEW_HEAD` alone only catches `experience in|with|of...` glued to the
    # noun itself. pv 69669: `domain_years_minimum`'s own `{0,4}` grab swallows "with direct and
    # indirect" INTO its span (no comma/coordinator follows "indirect", so it is not a
    # continuation of the bar's own list either); the `with`-search covers the bar too, so this
    # still counts, and "packaging experience" closing out the `with` adjunct is a second head.
    pytest.param(
        "At least 10 years of sales leadership with direct and indirect sales channel food "
        "industry and/or primary packaging experience is a plus",
        "domain_years_minimum", id="C6-bare-second-head-no-preposition",  # pv 69669
    ),
    # Same shape, one clause over: the bar's own pattern stops at "with" (its own preposition, in
    # the SPAN this time, not swallowed past it), and the complement's "and" opens a second
    # coordinated object whose own head is a second bare `experience` after that same `with`.
    pytest.param(
        "5+ years of experience with strong Python and Django experience preferred",
        "scoped_years_minimum", id="C6-bare-second-head-after-with",
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
    # T170b: the three wrong movers of the first measurement. A `with` that opens a modifier
    # phrase, and a hedge that is the object complement of `as`, qualify a sub-phrase.
    pytest.param(
        "8+ years of industry experience with a focus on digital communication systems, "
        "high-speed SerDes, or HBM protocols is highly preferred.",
        "scoped_years_minimum", id="span-ends-in-with-then-a-determiner",  # pv 5874
    ),
    pytest.param(
        "Minimum 5 years of underwriting experience with demonstrated expertise in E&S and "
        "specialty lines underwriting preferred",
        "scoped_years_minimum", id="with-a-quality-noun-modifier",  # pv 245709
    ),
    pytest.param(
        "4+ years SQL experience with either Python, and/or Spark as a plus",
        "scoped_years_minimum", id="as-a-plus-on-the-nearest-noun",  # pv 200836
    ),
    # Known misses (DESIGN §2), all in the conservative direction: the bar stays required.
    pytest.param(
        "2-4 years Experience with Dynamics 365, Office 365 and Microsoft Power Platform preferred",
        "scoped_range_years_minimum", id="MISS-one-comma-non-oxford-list",  # pv 298526
    ),
    pytest.param(
        "4 -7 years of relevant leadership experience including directing the work of others, "
        "preferred",
        "scoped_range_years_minimum", id="MISS-including-X-then-preferred",  # pv 354344
    ),
    # T202 control: a real second duration still stops the tail hedge, as it did before.
    pytest.param(
        "5+ years of experience, or 2 years in a senior role, preferred",
        "total_years_minimum", id="T202-control-a-real-second-duration",
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


@pytest.mark.parametrize("body", SCOPED)
def test_a_hedged_scoped_bar_is_carried_as_a_scoped_preference(catalog, body: str) -> None:  # type: ignore[no-untyped-def]
    result = evaluate(body, FACTS, POLICY, catalog)
    assert _rows(result) == [["experience_years:scoped_years_preferred", "preferred", "unmet"]]
    assert result.verdict == "eligible"


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
    """Before T174 `total_years_preferred` reached across the comma, so here it fired beside the
    required row and the demoted row must not duplicate it. The twin now stops at the comma, and
    the one row is the demoted one."""
    result = evaluate("5+ years of experience, preferred.", FACTS, POLICY, catalog)
    assert _rows(result) == [["experience_years:total_years_preferred", "preferred", "unmet"]]
    assert result.verdict == "eligible"


# T174: a preferred twin reaches its hedge only inside the bar's own clause, the bound the required
# row's hedge uses (`detect._CLAUSE_BOUNDARY`). Across it the hedge belongs to another noun, and a
# `preferred` row there claims a bar the posting requires is preferred: false evidence beside the
# required row that still blocks.
CROSS_CLAUSE = [
    pytest.param(
        "3 years of experience, banking experience preferred.",
        "total_years_minimum", id="total-comma-then-another-noun",  # pv 243714
    ),
    pytest.param(
        "3-5 years of experience, banking experience preferred.",
        "range_years_minimum", id="range-comma-then-another-noun",
    ),
    pytest.param(
        "3 years of experience and a degree preferred.",
        "total_years_minimum", id="total-and-then-another-noun",
    ),
]


@pytest.mark.parametrize(("body", "rule"), CROSS_CLAUSE)
def test_a_twin_does_not_reach_a_hedge_in_another_clause(catalog, body: str, rule: str) -> None:  # type: ignore[no-untyped-def]
    result = evaluate(body, FACTS, POLICY, catalog)
    experience = [r for r in _rows(result) if r[0].startswith("experience_years:")]
    assert experience == [[f"experience_years:{rule}", "required", "unmet"]]
    assert result.verdict == "ineligible"


@pytest.mark.parametrize(
    ("body", "twin"),
    [
        pytest.param("5+ years of experience preferred.", "total_years_preferred", id="total"),
        pytest.param("3-5 years of experience preferred.", "range_years_preferred", id="range"),
        pytest.param(
            "5 years of professional, relevant experience preferred.", "total_years_preferred",
            id="comma-inside-the-bar",
        ),
    ],
)
def test_a_twin_in_the_bars_own_clause_still_fires(catalog, body: str, twin: str) -> None:  # type: ignore[no-untyped-def]
    """CONTROL: the one-line hedge still writes its twin row."""
    result = evaluate(body, FACTS, POLICY, catalog)
    assert _rows(result) == [[f"experience_years:{twin}", "preferred", "unmet"]]
    assert result.verdict == "eligible"


# An ABSTAINING bar keeps its `unknown` row whatever its tail says: the tail hedge applies only to
# a bar no escape waived, so an abstain is never folded into a demoted or dropped row (keystone).
# Each expected row is the base's (`66d9de44`) exactly.
ABSTAINING = [
    pytest.param(
        "Bachelor degree or 5 years of experience, not required but preferred.",
        [["experience_years:total_years_minimum", "required", "unknown"]],
        id="demote-candidate-abstains",
    ),
    pytest.param(
        "5 years of experience in a related field or a Master degree, not required but preferred.",
        [["experience_years:scoped_years_minimum", "required", "unknown"]],
        id="drop-candidate-abstains",
    ),
    pytest.param(
        "Bachelor degree or 5 years of experience required.",
        [["experience_years:total_years_minimum", "required", "unknown"]],
        id="CONTROL-abstaining-bar-without-a-hedge",
    ),
    # T175: the clause-scoped hedge, inline or as a heading, reads the bar after its abstains too,
    # so the one-line forms keep the same `unknown` row the split form keeps. The trailing form
    # also writes its twin: `5 years of experience preferred` is a preference the sentence states.
    pytest.param(
        "Preferred: Bachelor degree or 5 years of experience.",
        [["experience_years:total_years_minimum", "required", "unknown"]],
        id="one-line-heading-hedge",
    ),
    pytest.param(
        "Preferred:\n- Bachelor degree or 5 years of experience.",
        [["experience_years:total_years_minimum", "required", "unknown"]],
        id="heading-line-hedge",
    ),
    pytest.param(
        "Bachelor degree or 5 years of experience preferred.",
        [
            ["experience_years:total_years_minimum", "required", "unknown"],
            ["experience_years:total_years_preferred", "preferred", "unmet"],
        ],
        id="trailing-one-line-hedge",
    ),
    pytest.param(
        "5 years of experience in a related field or a Master degree preferred.",
        [
            ["degree:degree_preferred", "preferred", "unknown"],
            ["experience_years:scoped_years_minimum", "required", "unknown"],
        ],
        id="trailing-one-line-hedge-scoped",
    ),
]


@pytest.mark.parametrize(("body", "rows"), ABSTAINING)
def test_an_abstaining_bar_keeps_its_unknown_row_whatever_its_tail(  # type: ignore[no-untyped-def]
    catalog, body: str, rows: list[list[str]]
) -> None:
    result = evaluate(body, FACTS, POLICY, catalog)
    assert _rows(result) == rows
    assert result.verdict == "uncertain"


def test_a_split_form_abstaining_bar_reads_as_its_one_line_form(catalog) -> None:  # type: ignore[no-untyped-def]
    """Equivalence, abstain direction: the split-form bar does not clear where its one-line form
    (the hedge as a heading) leaves the posting undecided."""
    split = evaluate(
        "Bachelor degree or 5 years of experience, not required but preferred.",
        FACTS, POLICY, catalog,
    )
    one_line = evaluate(
        "Preferred: Bachelor degree or 5 years of experience.", FACTS, POLICY, catalog
    )
    assert split.verdict == one_line.verdict == "uncertain"


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
        pattern: "{source}"
      - id: bachelor_preferred
        requiredness: preferred
        implies: degree_preferred
        scope: sentence
        required_rank: 3
        requirement_text: "A bachelor's degree is preferred"
        pattern: "bachelor.{{0,20}}preferred"
"""


@pytest.mark.parametrize(
    ("target", "source"),
    [
        pytest.param("bachelor_required", "bachelor", id="target-is-not-preferred"),
        pytest.param("no_such_pattern", "bachelor", id="target-is-not-in-the-family"),
        # The carried row reads the source's captures through the target, so a target that
        # captures less than the source is refused too.
        pytest.param(
            "bachelor_preferred", r"(?P<rank>\\d+) bachelor",
            id="target-does-not-capture-the-sources-groups",
        ),
    ],
)
def test_hedged_as_must_name_a_preferred_pattern_of_the_family(
    tmp_path: Path, target: str, source: str
) -> None:
    (tmp_path / "rules.yaml").write_text(
        HEDGED_AS.format(target=target, source=source), encoding="utf-8"
    )
    with pytest.raises(CatalogError, match="hedged_as"):
        load_rules(tmp_path)


def test_hedged_as_carries_a_valid_target(tmp_path: Path) -> None:
    """POSITIVE CONTROL for the two refusals above: a real preferred target loads."""
    (tmp_path / "rules.yaml").write_text(
        HEDGED_AS.format(target="bachelor_preferred", source="bachelor"), encoding="utf-8"
    )
    pattern = load_rules(tmp_path).family("degree").patterns[0]
    assert pattern.hedged_as == "bachelor_preferred"
    assert [rx.pattern for rx in pattern.hedged_by_tail] == ["preferred"]


# T180 F6: the one-line forms that still read differently from their comma twin after T170, each
# decided by the same rule (P + C1..C7). A HEDGE shape must write exactly what its reference writes;
# the review's forms are synthetic, `F6_STORE` below holds the real sentences.
_PREFERRED = [["experience_years:total_years_preferred", "preferred", "unmet"]]
F6_HEDGES = [
    # (P) opens on `;` or `:` as it does on `,`: only the predicate follows the delimiter.
    pytest.param("5+ years of experience; preferred.", "5+ years of experience, preferred.",
                 "eligible", _PREFERRED, id="semicolon-then-bare-hedge"),
    pytest.param("5+ years of experience: preferred.", "5+ years of experience, preferred.",
                 "eligible", _PREFERRED, id="colon-then-bare-hedge"),
    # (P) a spaced ASCII dash opens the predicate as `–` does; the splitter cuts it as a bullet, so
    # the predicate is read across that one inline cut.
    pytest.param("5+ years of experience - nice to have", "5+ years of experience – nice to have",
                 "eligible", _PREFERRED, id="spaced-hyphen-then-hedge"),
    # Catalog vocabulary: three hedges the review found, read by the unit scope and the tail alike.
    pytest.param("5+ years of experience would be nice.", "5+ years of experience is preferred.",
                 "eligible", _PREFERRED, id="would-be-nice"),
    pytest.param("5+ years of experience is an advantage.", "5+ years of experience is preferred.",
                 "eligible", _PREFERRED, id="is-an-advantage"),
    pytest.param("5+ years of experience, if possible.", "5+ years of experience, preferred.",
                 "eligible", _PREFERRED, id="if-possible"),
    # A bare negated bar says the bar is not required, and states no preference: it drops the bar
    # without carrying it, exactly as `(not required)` inside the clause already does.
    pytest.param("5+ years of experience, but not required.", "5+ years of experience (not required).",
                 "uncertain", [], id="but-not-required"),
    pytest.param("5+ years of experience, not mandatory.", "5+ years of experience (not required).",
                 "uncertain", [], id="not-mandatory"),
]


@pytest.mark.parametrize(("body", "reference", "verdict", "rows"), F6_HEDGES)
def test_a_one_line_hedge_shape_reads_as_its_reference(  # type: ignore[no-untyped-def]
    catalog, body: str, reference: str, verdict: str, rows: list[list[str]]
) -> None:
    result, ref = evaluate(body, FACTS, POLICY, catalog), evaluate(reference, FACTS, POLICY, catalog)
    assert (result.verdict, _rows(result)) == (verdict, rows)
    assert (ref.verdict, _rows(ref)) == (verdict, rows)


def test_a_negated_bar_aside_between_a_hedge_label_and_its_bar_is_read_through(catalog) -> None:  # type: ignore[no-untyped-def]
    """`Preferred (not required): 5+ years ...` states the bar is not required. The required row
    goes; no preferred row is written (the twin cannot read across the aside), so the verdict is
    `uncertain` where `Preferred: 5+ years ...` is `eligible` -- the conservative residual."""
    result = evaluate("Preferred (not required): 5+ years of experience.", FACTS, POLICY, catalog)
    assert (result.verdict, _rows(result)) == ("uncertain", [])


@pytest.mark.parametrize(
    ("body", "rule"),
    [
        # CONTROLS for the widened predicate: the delimiter opens it only when nothing but the
        # hedge follows, and a bare negation after a second noun is that noun's.
        pytest.param("5+ years of experience; Kubernetes preferred.", "total_years_minimum",
                     id="semicolon-then-another-noun-hedged"),
        pytest.param("5+ years of experience; a degree is not required.", "total_years_minimum",
                     id="semicolon-then-another-bar-negated"),
        pytest.param("5+ years of experience - Bachelor's degree preferred", "total_years_minimum",
                     id="hyphen-bullet-then-another-noun-hedged"),
        # The inline-dash read stays on one line: a bullet on the next line is its own item.
        pytest.param("5+ years of experience\n - nice to have\n", "total_years_minimum",
                     id="bar-line-then-a-bullet-on-the-next-line"),
        pytest.param("5+ years of experience, travel not required.", "total_years_minimum",
                     id="comma-then-another-noun-negated"),
    ],
)
def test_a_widened_predicate_still_keeps_a_bar_whose_tail_is_another_nouns(  # type: ignore[no-untyped-def]
    catalog, body: str, rule: str
) -> None:
    result = evaluate(body, FACTS, POLICY, catalog)
    assert [f"experience_years:{rule}", "required", "unmet"] in _rows(result)
    assert result.verdict == "ineligible"


# T196: `a plus` is a hedge only as two words. `bar_hedges` read it with no leading boundary, so the
# last letter of "diploma" and the conjunction `plus` read as the hedge, and the clause-scoped hedge
# dropped the required bar beside it (T173's measurement, D-590). pv 89429.
def test_the_a_plus_hedge_needs_a_word_boundary(catalog) -> None:  # type: ignore[no-untyped-def]
    body = (
        "Minimum requirement is High school diploma plus a minimum of 8 years of sales/clinical "
        "work experience in cardiac mapping and navigation."
    )
    result = evaluate(body, FACTS, POLICY, catalog)
    assert ["experience_years:scoped_years_minimum", "required", "unmet"] in _rows(result)
    assert result.verdict == "ineligible"


@pytest.mark.parametrize(
    "body",
    [
        # CONTROLS: the two-word hedge still hedges. (The domain form, "3+ years of Kubernetes a
        # plus", is T211's, below.)
        pytest.param("3+ years of Kubernetes experience a plus", id="bar-then-a-plus"),
        pytest.param("3+ years of experience with Kubernetes a plus", id="scoped-bar-then-a-plus"),
    ],
)
def test_a_two_word_a_plus_still_hedges_the_bar(catalog, body: str) -> None:  # type: ignore[no-untyped-def]
    result = evaluate(body, FACTS, POLICY, catalog)
    assert not any(row[1] == "required" for row in _rows(result))
    assert result.verdict in ("eligible", "uncertain")


# T197: an aside that names its OWN head noun qualifies that noun, not the bar before it, so its hedge
# does not hedge the bar (T173's measurement). The head noun is a capitalised product or company
# word, or `experience|background|knowledge|skills` after a modifier. A bare or restated hedge --
# `(preferred)`, `(preferred only)` -- still hedges the bar.
@pytest.mark.parametrize(
    ("body", "rule"),
    [
        pytest.param(
            "5-10 years of experience in related field (Abbott Instruments Experience is an "
            "advantage)",
            "scoped_range_years_minimum", id="aside-names-a-product-experience",  # pv 225434
        ),
        pytest.param(
            "3+ years of experience with HVAC maintenance (commercial experience preferred).",
            "scoped_years_minimum", id="aside-names-a-modified-experience",
        ),
        pytest.param(
            "5+ years of experience in cloud infrastructure (AWS preferred)",
            "scoped_years_minimum", id="aside-names-a-capitalised-product",  # pv 5016's shape
        ),
    ],
)
def test_an_aside_about_another_noun_keeps_the_bar(catalog, body: str, rule: str) -> None:  # type: ignore[no-untyped-def]
    result = evaluate(body, FACTS, POLICY, catalog)
    assert [f"experience_years:{rule}", "required", "unmet"] in _rows(result)
    assert result.verdict == "ineligible"


# CONTROLS for T197: a BARE aside is the bar's own hedge wherever it sits, so a mid-sentence one --
# which the sentence-final tail predicate cannot reach -- still demotes the bar in its clause.
@pytest.mark.parametrize(
    "body",
    [
        pytest.param("5 years of experience (preferred) in accounting.", id="bare"),
        pytest.param(
            "5+ years of experience (strongly preferred) in public accounting.", id="intensified"
        ),
        pytest.param(
            "3+ years of experience (preferred but not required) with Python and SQL.",
            id="negated-bar-restated",
        ),
    ],
)
def test_a_bare_aside_mid_sentence_still_hedges_the_bar(catalog, body: str) -> None:  # type: ignore[no-untyped-def]
    result = evaluate(body, FACTS, POLICY, catalog)
    assert _rows(result) == _PREFERRED
    assert result.verdict == "eligible"


# T197, round 2: an aside that only RESTATES the hedge names no noun of its own, so it is the bar's
# hedge exactly as `(preferred)` is. The first round let any non-bare aside own its hedge, and
# "5+ years of experience (preferred only)" kept a required row that rejected a one-year profile.
@pytest.mark.parametrize(
    "body",
    [
        pytest.param("5+ years of experience (preferred)", id="bare"),
        pytest.param("5+ years of experience (preferred only)", id="preferred-only"),
        pytest.param("5+ years of experience (Preferred Qualification)", id="restated-heading"),
        pytest.param("5+ years of experience (nice to have)", id="nice-to-have"),
        pytest.param("5+ years of experience (a plus)", id="a-plus"),
    ],
)
def test_an_aside_restating_the_hedge_still_hedges_the_bar(catalog, body: str) -> None:  # type: ignore[no-untyped-def]
    result = evaluate(body, FACTS, POLICY, catalog)
    assert _rows(result) == _PREFERRED
    assert result.verdict == "eligible"


# T173: the one-line and split forms of ONE hedged scoped bar write the same preferred row. The
# first two are the split form (`_hedged_tail`); the rest are the one-line hedge, in-clause, as an
# introducer, and as a heading (`suppressed_by_unit`, `_hedged_by_heading`), which dropped the bar.
SCOPED_FORMS = [
    pytest.param("3+ years of experience in power electronics, preferred.", id="split-comma"),
    pytest.param(
        "3+ years of experience in power electronics, not required but preferred.",
        id="split-negated-requirement",
    ),
    pytest.param("3+ years of experience in power electronics preferred.", id="one-line-trailing"),
    pytest.param("Nice to have: 3+ years of experience in power electronics.", id="one-line-introducer"),
    pytest.param(
        "Preferred Qualifications:\n- 3+ years of experience in power electronics",
        id="one-line-heading",
    ),
]


@pytest.mark.parametrize("body", SCOPED_FORMS)
def test_every_form_of_a_hedged_scoped_bar_writes_the_same_preferred_row(catalog, body: str) -> None:  # type: ignore[no-untyped-def]
    result = evaluate(body, FACTS, POLICY, catalog)
    assert _rows(result) == [["experience_years:scoped_years_preferred", "preferred", "unmet"]]
    assert result.verdict == "eligible"
    (row,) = result.requirements
    start, end = row.jd_locator["span"]
    assert body[start:end].startswith("3+ years of experience in")
    assert row.rationale == "1 total < 3 scoped to a skill"


def test_an_unhedged_scoped_bar_is_unchanged(catalog) -> None:  # type: ignore[no-untyped-def]
    """CONTROL, must stay green on both sides of the change."""
    result = evaluate("3+ years of experience in power electronics.", FACTS, POLICY, catalog)
    assert _rows(result) == [["experience_years:scoped_years_minimum", "required", "unmet"]]
    assert result.verdict == "ineligible"


def test_a_scoped_preference_never_claims_met_on_total_years(catalog) -> None:  # type: ignore[no-untyped-def]
    """The trap `total_years_preferred` would spring (DESIGN-T170 §3(b)): ten total years say
    nothing about power electronics, so the carried row abstains instead of resolving `met`."""
    result = evaluate(
        "3+ years of experience in power electronics preferred.",
        Facts(total_years_experience=10), POLICY, catalog,
    )
    assert _rows(result) == [["experience_years:scoped_years_preferred", "preferred", "unknown"]]
    assert result.verdict == "eligible"


def test_a_scoped_preference_does_not_straddle_a_required_total(catalog) -> None:  # type: ignore[no-untyped-def]
    """The carrier has its OWN implies, outside the refinement group: sharing
    `scoped_years_minimum` would let an unmet preference straddle a met required total and
    rewrite both to `unknown`, so a met floor would read `uncertain`."""
    result = evaluate(
        "3 years of experience required. 5+ years of experience in power electronics preferred.",
        Facts(total_years_experience=4), POLICY, catalog,
    )
    assert _rows(result) == [
        ["experience_years:scoped_years_preferred", "preferred", "unmet"],
        ["experience_years:total_years_minimum", "required", "met"],
    ]
    assert result.verdict == "eligible"


def test_a_one_line_abstaining_scoped_bar_keeps_its_unknown_row(catalog) -> None:  # type: ignore[no-untyped-def]
    """CONTROL. A degree alternative waives this bar before its one-line hedge is read (T175), so
    it keeps its `required unknown` row and is never carried as a preference: an abstain is not
    folded into a carried row."""
    result = evaluate(
        "5 years of experience in a related field or a Master degree preferred.",
        FACTS, POLICY, catalog,
    )
    assert [r for r in _rows(result) if r[0].startswith("experience_years:")] == [
        ["experience_years:scoped_years_minimum", "required", "unknown"]
    ]


CARRIER = Template("""
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
        ranks: {none: 0, bachelor: 3}
    implies_vocabulary: [degree_required, degree_preferred]
    exclusive_groups: []
    patterns:
      - id: bachelor_required
        requiredness: required
        implies: degree_required
        scope: sentence
        required_rank: 3
        requirement_text: "A bachelor's degree is required"
        suppressed_by_unit: $unit
        hedged_by_tail: ["preferred"]
        $hedged_as
        pattern: "bachelor"
      - id: bachelor_preferred
        requiredness: $requiredness
        implies: degree_preferred
        scope: sentence
        required_rank: 3
        requirement_text: "$text"
        carrier: true
        $extra
""")
VALID_CARRIER = {
    "unit": '["preferred"]', "hedged_as": "hedged_as: bachelor_preferred",
    "requiredness": "preferred", "text": "A bachelor's degree is preferred", "extra": "",
}


@pytest.mark.parametrize(
    "change",
    [
        pytest.param({"extra": 'pattern: "bachelor preferred"'}, id="carrier-has-its-own-pattern"),
        pytest.param({"requiredness": "required"}, id="carrier-is-not-preferred"),
        pytest.param({"text": "{rank} is preferred"}, id="carrier-text-has-a-placeholder"),
        pytest.param({"hedged_as": ""}, id="carrier-no-pattern-is-hedged-as"),
        # Every one-line suppression of a carried bar must be a hedge: a non-hedge suppressor
        # (`counts toward`) would otherwise be carried as a preference.
        pytest.param({"unit": '["preferred", "counts toward"]'}, id="source-suppressor-not-a-hedge"),
    ],
)
def test_a_carrier_is_refused_unless_it_is_a_preferred_hedged_as_target(
    tmp_path: Path, change: dict[str, str]
) -> None:
    (tmp_path / "rules.yaml").write_text(
        CARRIER.substitute({**VALID_CARRIER, **change}), encoding="utf-8"
    )
    # Not bare "carrier": the tmp path carries the test's own name.
    with pytest.raises(CatalogError, match="a carrier pattern"):
        load_rules(tmp_path)


def test_a_valid_carrier_loads_and_never_matches_on_its_own(tmp_path: Path) -> None:
    """POSITIVE CONTROL for the refusals above."""
    (tmp_path / "rules.yaml").write_text(CARRIER.substitute(VALID_CARRIER), encoding="utf-8")
    carrier = load_rules(tmp_path).family("degree").patterns[1]
    assert carrier.carrier is True
    assert carrier.regex.search("bachelor preferred") is None


def test_a_carried_scoped_bar_is_not_written_over_a_row_another_pattern_wrote(catalog) -> None:  # type: ignore[no-untyped-def]
    """Corpus m1111. A scoped pattern also reads the total bar here, as `3 years of experience,
    banking experience`, and the one-line hedge used to drop that second reading silently. Carried,
    it would claim the same 3-year bar is a scoped preference: the rows must stay the base's."""
    result = evaluate("3 years of experience, banking experience preferred.", FACTS, POLICY, catalog)
    assert _rows(result) == [["experience_years:total_years_minimum", "required", "unmet"]]


# T211: `domain_years_minimum`'s `{0,4}`-token domain tail swallowed its own trailing hedge, so the
# hedge sat INSIDE the span, where neither the clause hedge nor the tail predicate looks, and the bar
# stayed required. A tail token with a hedge ahead of it in its clause now ends the span, and the
# hedge is read exactly as it is after any other bar: here, carried as a scoped preference (T173).
@pytest.mark.parametrize(
    "body",
    [
        pytest.param("3+ years of Kubernetes preferred", id="preferred"),
        pytest.param("3+ years of Kubernetes a plus", id="a-plus"),
        pytest.param("3+ years of Kubernetes, strongly preferred.", id="comma-intensified"),
        pytest.param("3+ years of Kubernetes and Terraform preferred", id="coordinated-list"),
        pytest.param("3+ years of Kubernetes nice-to-have", id="hyphenated-nice-to-have"),
    ],
)
def test_a_domain_bar_does_not_swallow_its_own_hedge(catalog, body: str) -> None:  # type: ignore[no-untyped-def]
    result = evaluate(body, FACTS, POLICY, catalog)
    assert _rows(result) == [["experience_years:scoped_years_preferred", "preferred", "unmet"]]
    assert result.verdict == "eligible"


def test_a_domain_bar_keeps_its_tail_up_to_the_hedge(catalog) -> None:  # type: ignore[no-untyped-def]
    """The span stops before the hedge, not at the head: the carried row quotes the whole bar."""
    body = "5 years of direct project management preferred."
    (row,) = evaluate(body, FACTS, POLICY, catalog).requirements
    start, end = row.jd_locator["span"]
    assert body[start:end] == "5 years of direct project management"


# CONTROLS for T211. A mandate, a plain two-token tail, and a hedge on a LATER list item keep the
# bar required: the hedge is not the whole bar's predicate, as `3+ years of experience with Java,
# Python preferred` is not (the tail's comma opens an open list, `_hedged_tail`).
@pytest.mark.parametrize(
    ("body", "quote"),
    [
        pytest.param("3+ years of Kubernetes required", "3+ years of Kubernetes required", id="mandate"),
        pytest.param(
            "3+ years of Kubernetes and Terraform", "3+ years of Kubernetes and Terraform",
            id="two-token-tail",
        ),
        pytest.param(
            "Minimum 5 years of Java development, AWS preferred.", "5 years of Java development",
            id="hedge-on-a-later-item",
        ),
        pytest.param("5 years of SQL, Tableau a plus", "5 years of SQL", id="a-plus-on-a-later-item"),
    ],
)
def test_a_domain_bar_whose_hedge_is_not_its_own_stays_required(  # type: ignore[no-untyped-def]
    catalog, body: str, quote: str
) -> None:
    result = evaluate(body, FACTS, POLICY, catalog)
    assert _rows(result) == [["experience_years:domain_years_minimum", "required", "unmet"]]
    assert result.verdict == "ineligible"
    (row,) = result.requirements
    start, end = row.jd_locator["span"]
    assert body[start:end] == quote


# T212: T196 bounded `a plus` in `bar_hedges` alone. `&degree_hedges` and the preferred patterns'
# inline hedge lists read it with no leading boundary too, so the end of "diploma" and the
# conjunction `plus` were a hedge: the degree bar beside it dropped, or a preferred twin was written
# over a bar that states no preference.
@pytest.mark.parametrize(
    ("body", "required"),
    [
        pytest.param(
            "High school diploma plus a Bachelor's degree or equivalent.",
            "degree:bachelor_or_equivalent_required", id="degree-hedges",
        ),
        pytest.param(
            "Master's degree or equivalent experience or a diploma plus 6 years.",
            "degree:master_or_equivalent_required", id="master-or-equivalent-preferred-list",
        ),
        pytest.param(
            "Bachelor's degree or equivalent experience, or a high school diploma plus 4 years of "
            "experience.",
            "degree:bachelor_or_equivalent_required", id="bachelor-or-equivalent-preferred-list",
        ),
        pytest.param(
            "5 years of experience or a diploma plus training.",
            "experience_years:total_years_minimum", id="total-years-preferred-list",
        ),
        pytest.param(
            "3-5 years of experience or a diploma plus training.",
            "experience_years:range_years_minimum", id="range-years-preferred-list",
        ),
    ],
)
def test_diploma_plus_is_not_the_a_plus_hedge(catalog, body: str, required: str) -> None:  # type: ignore[no-untyped-def]
    rows = _rows(evaluate(body, FACTS, POLICY, catalog))
    assert [required, "required"] in [row[:2] for row in rows]
    assert not [row for row in rows if row[1] == "preferred"]


# CONTROLS for T212: the two-word hedge still hedges at every site bounded.
@pytest.mark.parametrize(
    ("body", "preferred"),
    [
        pytest.param("Bachelor's degree a plus.", "degree:degree_preferred", id="degree-preferred"),
        pytest.param(
            "Bachelor's degree or equivalent a plus.", "degree:bachelor_or_equivalent_preferred",
            id="bachelor-or-equivalent-preferred",
        ),
        pytest.param(
            "Security clearance a plus.", "clearance:clearance_preferred", id="clearance-preferred"
        ),
        pytest.param(
            "5+ years of experience a plus.", "experience_years:total_years_preferred",
            id="total-years-preferred",
        ),
        pytest.param(
            "3-5 years of experience a plus.", "experience_years:range_years_preferred",
            id="range-years-preferred",
        ),
    ],
)
def test_a_two_word_a_plus_still_hedges_every_list(catalog, body: str, preferred: str) -> None:  # type: ignore[no-untyped-def]
    result = evaluate(body, FACTS, POLICY, catalog)
    assert [row[:2] for row in _rows(result)] == [[preferred, "preferred"]]
    assert result.verdict == "eligible"


# T213: a hedged domain bar lands in `scoped_years_preferred`, the carrier `domain_years_minimum` is
# already `hedged_as` (T173) -- no sibling of its own. It resolves as a scoped preference: `unmet`
# under the bar, and never `met` on total years, which say nothing about Kubernetes.
@pytest.mark.parametrize(("years", "disposition"), [(1, "unmet"), (5, "unknown")])
def test_a_hedged_domain_bar_is_a_scoped_preference(  # type: ignore[no-untyped-def]
    catalog, years: int, disposition: str
) -> None:
    result = evaluate(
        "3+ years of Kubernetes preferred.", Facts(total_years_experience=years), POLICY, catalog
    )
    assert _rows(result) == [["experience_years:scoped_years_preferred", "preferred", disposition]]
    assert result.verdict == "eligible"


def test_a_hedged_domain_bar_never_yields_ineligible(catalog) -> None:  # type: ignore[no-untyped-def]
    """A `preference` row never blocks, at any profile: only a `required` row can reject."""
    for years in range(21):
        result = evaluate(
            "10+ years of Kubernetes a plus", Facts(total_years_experience=years), POLICY, catalog
        )
        assert [row[1] for row in _rows(result)] == ["preferred"]
        assert result.verdict != "ineligible"
