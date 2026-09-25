"""T234: the defects the domain patterns' twins inherited, fixed on both, and a 0-year floor.

- A time horizon is no bar. The single domain pattern had no `(?<!next\\s)` ("Over the next 5 years
  State Street will deploy ..."), and neither pattern stopped at a possessive, definite or
  demonstrative determiner before the count ("Our 3 year strategy", "the 3-5 year technical
  roadmap", "this 2 year program"). `a|an` stays: "a 5+ year proven track record" is a bar.
- A scoped or activity floor of 0 resolved `unknown` ("0-2 years in the medical device industry",
  pv 10645; "0 – 2 years of professional experience or equivalent college project experience",
  pv 75422): no declared total can miss it, so it is `met`. An undeclared total still abstains.
- A domain-list row over exactly the span of the scoped or total row beside it was that bar read a
  second time; it now `yields_to` its sibling.

Two of the ticket's sentences already read as preferences on this base (T211 stops the domain tail
before its own hedge); they are pinned as controls. The near-miss band is off.
"""

from pathlib import Path

import pytest

from boardwatch.eligibility.catalog import CatalogError, load_rules
from boardwatch.eligibility.detect import detect
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


def _read(body: str, years: int | None, catalog) -> tuple[str, list[tuple[str, str, str, str]]]:  # type: ignore[no-untyped-def]
    result = evaluate(body, Facts(total_years_experience=years), POLICY, catalog)
    return result.verdict, sorted(
        (r.rule_id.split(":")[1], r.requiredness, r.disposition, body[slice(*r.jd_locator["span"])])
        for r in result.requirements
    )


HORIZONS = [
    pytest.param("Our 3 year strategy.", id="our-single"),
    pytest.param("Our 3-5 year strategy.", id="our-range"),
    pytest.param("Define the 3–5 year technical roadmap for marketing measurement.", id="the-range"),
    pytest.param("During this 2 year program you will rotate through three teams.", id="this-single"),
    pytest.param("Manage the ECOs related to the 3 year product plan.", id="the-single"),
    pytest.param(
        "Over the next 5 years State Street will deploy a next generation platform.", id="next-single"
    ),
    pytest.param(
        "Understand the industry technology roadmap for next 10 years and implications.",
        id="next-single-no-article",  # pv 156869
    ),
]


@pytest.mark.parametrize("body", HORIZONS)
def test_a_time_horizon_writes_no_domain_bar(body: str, catalog) -> None:  # type: ignore[no-untyped-def]
    assert _read(body, 1, catalog) == ("uncertain", [])


BARS = [
    pytest.param(
        "14+ years of engineering experience with a 5+ year proven track record managing software teams.",
        [("domain_years_minimum", "required", "unmet",
          "5+ year proven track record managing software teams."),
         ("scoped_years_minimum", "required", "unmet", "14+ years of engineering experience")],
        id="indefinite-article-keeps-its-bar",  # pv 155982
    ),
    pytest.param(
        "Your background looks something like this\n6+ years as a product designer.",
        [("domain_years_minimum", "required", "unmet", "6+ years as a product designer.")],
        id="a-heading-line-ending-in-this-keeps-its-bar",  # pv 307591's shape, 15 rows
    ),
    pytest.param(
        "the last 3-4 years focused on building platforms.",
        [("domain_range_years_minimum", "required", "unmet", "3-4 years focused on building platforms.")],
        id="the-last-keeps-its-bar",  # pv 286912's shape
    ),
    pytest.param(
        "5 years in SaaS.", [("domain_years_minimum", "required", "unmet", "5 years in SaaS.")],
        id="bare-domain-bar",
    ),
]


@pytest.mark.parametrize(("body", "rows"), BARS)
def test_a_domain_bar_with_no_horizon_determiner_is_kept(body: str, rows, catalog) -> None:  # type: ignore[no-untyped-def]
    assert _read(body, 1, catalog) == ("ineligible", rows)


ZERO_FLOORS = [
    pytest.param(
        "• 0-2 years in the medical device industry or manufacturing industry previous experience.",
        [("domain_list_range_years_minimum", "required", "met",
          "0-2 years in the medical device industry or manufacturing industry previous experience")],
        id="domain-list-range",  # pv 10645
    ),
    pytest.param(
        "0 – 2 years of professional experience or equivalent college project experience.",
        [("domain_list_range_years_minimum", "required", "met",
          "0 – 2 years of professional experience or equivalent college project experience"),
         ("range_years_minimum", "required", "met", "0 – 2 years of professional experience")],
        id="beside-a-total-range",  # pv 75422
    ),
    pytest.param(
        "0 years of experience in Python.",
        [("scoped_years_minimum", "required", "met", "0 years of experience in")], id="scoped",
    ),
]


@pytest.mark.parametrize(("body", "rows"), ZERO_FLOORS)
def test_a_zero_year_scoped_floor_is_met(body: str, rows, catalog) -> None:  # type: ignore[no-untyped-def]
    assert _read(body, 0, catalog) == ("eligible", rows)


def test_a_zero_year_floor_still_abstains_on_an_undeclared_total(catalog) -> None:  # type: ignore[no-untyped-def]
    """The keystone: a missing profile field abstains, whatever the bar."""
    assert _read("0 years of experience in Python.", None, catalog) == (
        "uncertain", [("scoped_years_minimum", "required", "unknown", "0 years of experience in")],
    )


def test_a_one_year_scoped_floor_is_not_a_zero_floor(catalog) -> None:  # type: ignore[no-untyped-def]
    assert _read("1 year of experience in Python.", 0, catalog) == (
        "ineligible", [("scoped_years_minimum", "required", "unmet", "1 year of experience in")],
    )
    assert _read("1 year of experience in Python.", 1, catalog) == (
        "uncertain", [("scoped_years_minimum", "required", "unknown", "1 year of experience in")],
    )


DUPLICATES = [
    pytest.param(
        "4 years of professional, post University experience.",
        ("scoped_years_minimum", "4 years of professional, post University experience"),
        id="single-beside-scoped",
    ),
    pytest.param(
        "2-4 years of professional, post University experience.",
        ("scoped_range_years_minimum", "2-4 years of professional, post University experience"),
        id="range-beside-scoped-range",  # corpus m1048
    ),
    pytest.param(
        "5 years of sales or marketing pharmaceutical experience.",
        ("scoped_years_minimum", "5 years of sales or marketing pharmaceutical experience"),
        id="a-short-list-the-scoped-tail-reaches",  # pv 508
    ),
    pytest.param(
        "12 years of relevant, progressive experience.",
        ("total_years_minimum", "12 years of relevant, progressive experience"),
        id="single-beside-total",  # pv 24216
    ),
    pytest.param(
        "4–6 years of progressive, hands-on experience.",
        ("range_years_minimum", "4–6 years of progressive, hands-on experience"),
        id="range-beside-total-range",  # pv 45403
    ),
]


@pytest.mark.parametrize(("body", "row"), DUPLICATES)
def test_one_bar_over_one_span_is_one_row(body: str, row, catalog) -> None:  # type: ignore[no-untyped-def]
    verdict, rows = _read(body, 1, catalog)
    assert (verdict, [(r[0], r[3]) for r in rows]) == ("ineligible", [row])


KEPT_LISTS = [
    pytest.param(
        "7+ years of relevant and successful program management experience.",
        "7+ years of relevant and successful program management experience", id="no-sibling-reads-it",
    ),
    pytest.param(
        "5 years of Java, Python, and Go experience.", "5 years of Java, Python, and Go experience",
        id="a-comma-list",
    ),
]


@pytest.mark.parametrize(("body", "span"), KEPT_LISTS)
def test_a_domain_list_no_sibling_reads_keeps_its_row(body: str, span: str, catalog) -> None:  # type: ignore[no-untyped-def]
    assert _read(body, 1, catalog) == (
        "ineligible", [("domain_list_years_minimum", "required", "unmet", span)],
    )


# Two of the ticket's shapes already read as preferences on this base; pinned so a change shows.
PREMISE_FALSE = [
    pytest.param("8+ years strongly preferred for Staff-level scope.", "8+ years strongly", id="for-scope"),
    pytest.param("3 years Management/Supervisory Preferred", "3 years Management/Supervisory", id="slash"),
]


@pytest.mark.parametrize(("body", "span"), PREMISE_FALSE)
def test_the_hedged_sibling_shapes_already_read_as_preferences(body: str, span: str, catalog) -> None:  # type: ignore[no-untyped-def]
    assert _read(body, 1, catalog) == (
        "eligible", [("scoped_years_preferred", "preferred", "unmet", span)],
    )


_YIELDING = """
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
    implies_vocabulary: [degree_required]
    exclusive_groups: []
    patterns:
      - id: first
        requiredness: required
        implies: degree_required
        scope: sentence
        required_rank: 3
        requirement_text: "A bachelor's degree is required"
        pattern: "bachelor"
        yields_to: [FIRST]
      - id: second
        requiredness: required
        implies: degree_required
        scope: sentence
        required_rank: 3
        requirement_text: "A bachelor's degree is required"
        pattern: "bachelor"
        yields_to: [SECOND]
"""


@pytest.mark.parametrize(
    ("first", "second"),
    [("first", "[]"), ("nowhere", "[]"), ("second", "[first]")],
    ids=["itself", "not-a-sibling", "mutual"],
)
def test_yields_to_must_name_another_sibling_that_does_not_yield_back(
    tmp_path: Path, first: str, second: str
) -> None:
    (tmp_path / "rules.yaml").write_text(
        _YIELDING.replace("[FIRST]", f"[{first}]").replace("[SECOND]", second), encoding="utf-8"
    )
    with pytest.raises(CatalogError, match="yields_to"):
        load_rules(tmp_path)


def test_a_one_way_yield_drops_only_the_same_reading(tmp_path: Path) -> None:
    """`first` yields to `second` over one span; an abstain only `first` reads keeps both rows,
    because a sibling that decides the bar is not the same reading as one that waives it."""
    (tmp_path / "rules.yaml").write_text(
        _YIELDING.replace("[FIRST]", "[second]").replace("[SECOND]", "[]"), encoding="utf-8"
    )
    catalog = load_rules(tmp_path)
    assert catalog.family("degree").patterns[0].yields_to == ("second",)
    rows = detect("A bachelor.", catalog, enabled_families=frozenset({"degree"}))
    assert [(d.pattern.id, d.span) for d in rows] == [("second", (2, 10))]
    (tmp_path / "rules.yaml").write_text(
        _YIELDING.replace("[FIRST]", "[second]\n        abstain_by_sentence: [\"equivalent\"]")
        .replace("[SECOND]", "[]"),
        encoding="utf-8",
    )
    rows = detect("A bachelor or equivalent.", load_rules(tmp_path), enabled_families=frozenset({"degree"}))
    assert sorted((d.pattern.id, d.abstained) for d in rows) == [
        ("first", "equivalent"), ("second", None),
    ]
