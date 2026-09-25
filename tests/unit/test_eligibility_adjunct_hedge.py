"""T236: an adverb that opens an adjunct is not the bar's hedge, and a degree's length is no years bar.

- `ideally` after the bar, in its own clause, opening a prepositional adjunct ("... closing role
  ideally from SaaS", "... Market Data solutions ideally from a provider", pv 221193) hedges the
  adjunct's object. The clause hedge read it as the bar's, so a required bar was carried as a
  preference, or, on a total bar with no preferred twin that reads it, left no row at all. Sized over
  the 126,854 pinned postings by masking that `ideally`: 20 postings change, 19 of them real mandates
  read by hand (the twentieth writes no row either way). `ideally` sentence-final, before the bar, or
  after a comma is still a hedge.
- "2 year degree preferred", "Associate's degree or 2 year degree required", "4 year degree or
  equivalent experience": `degree(s)|diploma(s)` is a head stop on the domain, domain-list and scoped
  patterns and their range twins.

Not built, pinned as controls (store instances under the ten a preference-to-required change needs):
a hedge on a second bar in the same clause (2), `in the desired specialty` (3), a `(required)` past the
bar's clause under `Preferred:` (7 reachable). The near-miss band is off.
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
FACTS = Facts(total_years_experience=1, highest_degree="bachelor")


@pytest.fixture(scope="module")
def catalog(tmp_path_factory: pytest.TempPathFactory):  # type: ignore[no-untyped-def]
    return load_rules(Path(tmp_path_factory.mktemp("no-override")))


def _read(body: str, catalog) -> tuple[str, list[tuple[str, str, str, str]]]:  # type: ignore[no-untyped-def]
    result = evaluate(body, FACTS, POLICY, catalog)
    return result.verdict, sorted(
        (r.rule_id.split(":")[1], r.requiredness, r.disposition, body[slice(*r.jd_locator["span"])])
        for r in result.requirements
    )


ADJUNCTS = [
    pytest.param(
        "Candidates should have 3+ years of selling Market Data solutions ideally from a provider such "
        "as Bloomberg, Refinitiv or Factset.",
        ("domain_years_minimum", "3+ years of selling Market Data solutions"), id="domain-pv221193",
    ),
    pytest.param(
        "5+ years of experience in a full-cycle closing role ideally from SaaS",
        ("scoped_years_minimum", "5+ years of experience in"), id="scoped-pv57305",
    ),
    pytest.param(
        "4+ years of delivery within Agile SDLC teams ideally with CICD",
        ("domain_years_minimum", "4+ years of delivery within Agile SDLC teams"), id="domain-with",
    ),
    pytest.param(
        "Have 10-12 years of experience overseeing executive communications ideally in-house and within "
        "a fast-paced tech environment",
        ("range_years_minimum", "10-12 years of experience"), id="range-was-rowless-pv40299",
    ),
    pytest.param(
        "You have 2-4 years of experience ideally in logistics, tech, consulting, startups, AI or other "
        "related fields.",
        ("range_years_minimum", "2-4 years of experience"), id="range-was-rowless-pv308387",
    ),
    pytest.param(
        "5+ years of experience selling Market Data solutions ideally from a provider such as Bloomberg.",
        ("total_years_minimum", "5+ years of experience"), id="total-was-rowless",
    ),
]


@pytest.mark.parametrize(("body", "row"), ADJUNCTS)
def test_an_adverb_opening_an_adjunct_does_not_hedge_the_bar(body: str, row, catalog) -> None:  # type: ignore[no-untyped-def]
    assert _read(body, catalog) == ("ineligible", [(row[0], "required", "unmet", row[1])])


STILL_HEDGED = [
    pytest.param("5+ years of experience in Python ideally", id="sentence-final"),
    pytest.param("5+ years of experience in Python, ideally.", id="comma-sentence-final"),
    pytest.param("Ideally 5+ years of experience in Python", id="before-the-bar"),
    pytest.param("Ideally with 5+ years of experience in Python", id="before-the-bar-with-a-preposition"),
    pytest.param(
        "Preferred:\n- 5+ years of experience in a full-cycle closing role ideally from SaaS",
        id="a-hedge-heading-still-governs",
    ),
    # Only a preposition or subordinator after `ideally` opens the adjunct the store sample sized.
    pytest.param("5+ years of experience in Python ideally combined with Go", id="no-preposition-follows"),
]


@pytest.mark.parametrize("body", STILL_HEDGED)
def test_an_ideally_that_is_the_bars_own_hedge_still_hedges(body: str, catalog) -> None:  # type: ignore[no-untyped-def]
    verdict, rows = _read(body, catalog)
    assert verdict == "eligible" and [r[1] for r in rows] == ["preferred"]


def test_ideally_after_a_comma_was_never_the_bars(catalog) -> None:  # type: ignore[no-untyped-def]
    assert _read("5 years of experience, ideally in fintech", catalog) == (
        "ineligible", [("total_years_minimum", "required", "unmet", "5 years of experience")],
    )


DEGREE_LENGTHS = [
    pytest.param("2 year degree preferred", "eligible", id="domain-hedged"),
    pytest.param("4 year degree preferred.", "eligible", id="domain-hedged-full-stop"),
    pytest.param("2 year degree or technical degree preferred", "eligible", id="domain-hedged-pv338776"),
    pytest.param("Associate's degree or 2 year degree required.", "uncertain", id="domain-required"),
    pytest.param("Associate's degree or 2-4 year degree required.", "uncertain", id="domain-range-required"),
    # T221: the degree family reads these as a four-year degree or equivalent, met by the bachelor's.
    pytest.param("4 year degree or equivalent experience", "eligible", id="scoped-and-domain-list"),
    pytest.param("4 Year Degree or equivalent experience", "eligible", id="capitalised"),
    pytest.param("3 years Diploma in Electronics.", "uncertain", id="diploma"),
    pytest.param("Any 3 years degree (BBA, Bcom, BCA).", "uncertain", id="plural-years"),
    pytest.param("4-5 year degree or equivalent experience", "uncertain", id="range-twins"),
]


@pytest.mark.parametrize(("body", "verdict"), DEGREE_LENGTHS)
def test_a_degree_length_writes_no_years_row(body: str, verdict: str, catalog) -> None:  # type: ignore[no-untyped-def]
    got, rows = _read(body, catalog)
    assert (got, [r for r in rows if "years" in r[0]]) == (verdict, [])


def test_a_program_management_bar_is_no_degree_length(catalog) -> None:  # type: ignore[no-untyped-def]
    assert _read("5 years of program management experience.", catalog)[0] == "ineligible"


# Not built: fewer store instances than a preference-to-required change needs. Pinned so a change shows.
CONTROLS = [
    pytest.param(
        "From an experience standpoint having more than 8 years’ experience with 4+ years in "
        "Ophthalmology preferred",
        [("scoped_years_preferred", "preferred", "unmet", "4+ years in Ophthalmology"),
         ("scoped_years_preferred", "preferred", "unmet", "8 years’ experience with")],
        id="a-hedge-on-a-second-bar-pv244626",
    ),
    pytest.param(
        "2-3 years of product sales in the desired specialty.",
        [("scoped_years_preferred", "preferred", "unmet", "2-3 years of product sales in the")],
        id="the-desired-specialty-pv116186",
    ),
]


@pytest.mark.parametrize(("body", "rows"), CONTROLS)
def test_unbuilt_shapes_keep_their_reading(body: str, rows, catalog) -> None:  # type: ignore[no-untyped-def]
    assert _read(body, catalog) == ("eligible", rows)


def test_a_required_past_the_clause_is_the_items_mandate(catalog) -> None:  # type: ignore[no-untyped-def]
    """pv 32584, pinned here unbuilt in batch 8: T245 binds the item-final `(required)` to its bar."""
    body = (
        "Preferred Qualifications:\n12-15 years of general knowledge in EFT settlement and transaction "
        "processing (required)"
    )
    assert _read(body, catalog) == ("ineligible", [
        ("domain_range_years_minimum", "required", "unmet",
         "12-15 years of general knowledge in EFT settlement"),
    ])
