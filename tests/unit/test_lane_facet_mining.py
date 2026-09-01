"""lanes.facets mining: search terms taken from the user's OWN delivered leads.

WHAT THIS DEFENDS. A profile's target titles are what the user could write down before running
anything; they are not what the market calls the jobs she actually gets. Measured on the live
store 2026-08-31, 957 postings had a lead built for them and 26 distinct title spellings recurred
at two or more employers — the strongest of them (`software development engineer`, 10 postings at
4 employers; `junior software engineer`, 13 at 5) absent from the profile entirely. Each was a
search the lane never made.

WHAT IT MUST NOT BECOME. Not one word of any field's vocabulary may enter this repo. Every test
below is written with titles from a field that is not the author's, for exactly that reason: if
any of these ever needs a software word to pass, the mechanism has stopped being generic and the
multi-tenancy requirement has been broken where nothing else would catch it.
"""

from __future__ import annotations

import pytest

from boardwatch.lanes.facets import (
    MAX_MINED_FACET_WORDS,
    MIN_TRIAL_POSTINGS,
    DeliveredPosting,
    FacetTrial,
    LaneFacets,
    mined_facet_candidates,
    search_term,
    surviving_mined_facets,
)


def _delivered(*rows: tuple[str, int, int]) -> tuple[DeliveredPosting, ...]:
    return tuple(
        DeliveredPosting(title=title, posting_id=posting_id, company_id=company_id)
        for title, posting_id, company_id in rows
    )


def _spread(title: str, *, count: int, first_id: int = 1) -> tuple[DeliveredPosting, ...]:
    """`count` delivered postings for one title, each at its own employer."""
    return _delivered(*((title, first_id + n, first_id + n) for n in range(count)))


# ---------------------------------------------------------------------------------------
# Generation: what the delivered leads support
# ---------------------------------------------------------------------------------------


def test_a_title_the_profile_never_listed_becomes_a_facet_when_the_market_repeats_it():
    """The whole point of mining. The profile asked for one thing; the leads the program
    actually built name another, and that one was never searched for."""
    delivered = _spread("Travel Nurse RN", count=2) + _spread(
        "Perioperative Nurse", count=3, first_id=10
    )

    assert mined_facet_candidates(delivered, ("registered nurse",)) == (
        "perioperative nurse",
        "travel nurse rn",
    )


def test_a_title_only_one_employer_uses_is_not_mined():
    """One employer's house style is not a market pattern, and a facet is a request.

    On the live store this rule is what excludes `servicenow developer` (10 delivered postings,
    all at ONE employer) while keeping `full stack software engineer` (9 postings, 9 employers).
    Drop the employer threshold to 1 and the single-employer title reappears — which is exactly
    what makes this assertion mean something.
    """
    one_employer = _delivered(
        ("Perioperative Nurse", 1, 500),
        ("Perioperative Nurse", 2, 500),
        ("Perioperative Nurse", 3, 500),
        ("Perioperative Nurse", 4, 500),
    )

    assert mined_facet_candidates(one_employer, ()) == ()


def test_a_title_delivered_once_is_not_mined_however_many_employers_are_in_the_pool():
    """A single lead is a coincidence. Both thresholds are needed and neither implies the
    other: this pool has four employers and no title reaching two postings."""
    singletons = _delivered(
        ("Travel Nurse RN", 1, 1),
        ("Perioperative Nurse", 2, 2),
        ("Charge Nurse", 3, 3),
        ("Nurse Navigator", 4, 4),
    )

    assert mined_facet_candidates(singletons, ()) == ()


def test_one_requisition_listed_in_several_cities_is_one_piece_of_evidence():
    """Postings and employers are counted DISTINCTLY. Summing rows would let a single
    multi-city requisition clear both thresholds on its own."""
    duplicated = _delivered(
        ("Travel Nurse RN", 1, 1),
        ("Travel Nurse RN", 1, 1),
        ("Travel Nurse RN", 1, 1),
        ("Travel Nurse RN", 1, 1),
    )

    assert mined_facet_candidates(duplicated, ()) == ()


def test_the_raw_title_is_mined_and_not_the_stores_identity_normalization():
    """`postings.normalized_title` is the WRONG SPACE and mining it produces dead queries.

    `core.normalize.normalize_title` folds `+` to ` plus ` and `#` to ` sharp ` on purpose, for
    the identity quad. A facet built in that space asks an aggregator for `c plus plus`, a string
    no posting contains. Six of the live store's 957 built postings carry one of those two
    characters and 590 open postings do, so this is a live defect, not a hypothetical.
    """
    delivered = _spread("C++ Instrumentation Technician", count=2)

    (facet,) = mined_facet_candidates(delivered, ())
    assert facet == "c instrumentation technician"
    assert "plus" not in facet


def test_a_title_the_profile_already_asks_for_in_ANOTHER_WORD_ORDER_is_not_mined_again():
    """Exclusion is on the words, not the spelling, so the run cannot buy one search twice.

    A profile listing `Perioperative Nurse` and an employer writing `Nurse, Perioperative` are
    one ask of a keyword search. Compare the two spellings as strings and the second is mined as
    a brand-new facet, and the run pays a second time for the page it already requested.
    """
    delivered = _spread("Nurse, Perioperative", count=3)

    assert mined_facet_candidates(delivered, ("perioperative nurse",)) == ()


def test_two_spellings_of_one_ask_cost_one_facet_and_keep_the_commoner_spelling():
    """Grouped on words, so `Travel Nurse RN` and `RN, Travel Nurse` are one candidate. The
    surviving spelling is the one the market writes most often — a sorted word list is not a
    query anyone searches for."""
    delivered = _spread("Travel Nurse RN", count=3) + _spread(
        "RN, Travel Nurse", count=2, first_id=10
    )

    assert mined_facet_candidates(delivered, ()) == ("travel nurse rn",)


def test_a_title_longer_than_the_word_ceiling_is_not_mined():
    """A mined term is an EMPLOYER's words, not the user's, so it is held to a length the
    profile's own titles are not. An over-long term is not dangerous, only useless — and a
    facet that matches nothing still costs a request."""
    long_title = " ".join(f"Word{n}" for n in range(MAX_MINED_FACET_WORDS + 1))
    at_ceiling = " ".join(f"Word{n}" for n in range(MAX_MINED_FACET_WORDS))

    assert mined_facet_candidates(_spread(long_title, count=3), ()) == ()
    assert len(mined_facet_candidates(_spread(at_ceiling, count=3), ())) == 1


def test_a_title_that_normalizes_to_nothing_yields_no_facet():
    """The same rule `role_facets` holds: an empty term builds the UNFACETED listing, which is
    a different page, and would silently restore the noise the facet exists to remove."""
    assert mined_facet_candidates(_spread("!!! --- ///", count=3), ()) == ()


def test_no_delivered_leads_at_all_mines_nothing():
    """Every store before the program has built anything. A miner with no evidence must
    abstain, not invent a role query — that is the direction this repo's rules always fail."""
    assert mined_facet_candidates((), ("registered nurse",)) == ()


def test_the_ranking_is_fully_determined_so_one_store_yields_one_facet_list():
    """A run whose facet set varied between invocations could not be reproduced from the store
    that produced it — the same standard `role_facets`' truncating cap is held to. Ordering is
    postings, then employers, then the term, and the tie below is broken by the last."""
    delivered = (
        _spread("Charge Nurse", count=2)
        + _spread("Travel Nurse RN", count=2, first_id=10)
        + _spread("Perioperative Nurse", count=4, first_id=20)
    )

    assert mined_facet_candidates(delivered, ()) == (
        "perioperative nurse",
        "charge nurse",
        "travel nurse rn",
    )
    assert mined_facet_candidates(tuple(reversed(delivered)), ()) == mined_facet_candidates(
        delivered, ()
    )


def test_generation_and_role_facets_normalize_through_one_rule():
    """Two normalizers would let a profile facet through the exclusion under a spelling the
    other rule folds differently, and the run would pay twice for one search."""
    assert search_term("Full-Stack  Nurse / Technician") == "full stack nurse technician"


# ---------------------------------------------------------------------------------------
# Pruning and the cap: what is worth a request THIS run
# ---------------------------------------------------------------------------------------


def test_a_facet_credited_with_enough_postings_and_no_delivered_lead_is_dropped():
    """Ranking is NOT pruning, and this is the gap it leaves.

    A candidate's rank comes from leads delivered across EVERY source, so a term this lane's
    search never converts keeps its rank for as long as the title keeps being delivered on some
    board. Without this rule the barren facet is bought every run, forever.
    """
    barren = FacetTrial(credited=MIN_TRIAL_POSTINGS, delivered=0)

    assert surviving_mined_facets(("charge nurse",), {"charge nurse": barren}) == ()


def test_one_delivered_lead_keeps_a_facet_no_matter_how_many_postings_it_took():
    """The rule is zero conversion, not a conversion RATE. The weakest of the 14 live profile
    facets delivered 2 leads from 52 credited postings; a rate threshold set anywhere above that
    would have retired a facet that was working."""
    working = FacetTrial(credited=MIN_TRIAL_POSTINGS * 10, delivered=1)

    assert surviving_mined_facets(("charge nurse",), {"charge nurse": working}) == ("charge nurse",)


def test_a_facet_with_too_few_credited_postings_to_judge_is_kept():
    """Small-sample silence is not evidence of barrenness. A facet dropped on its first quiet
    run could never earn its way back, and the same store measured a working facet at 2 leads
    per 52 postings — a run of 39 empty ones is ordinary."""
    unproven = FacetTrial(credited=MIN_TRIAL_POSTINGS - 1, delivered=0)

    assert surviving_mined_facets(("charge nurse",), {"charge nurse": unproven}) == (
        "charge nurse",
    )


def test_a_facet_that_has_never_been_searched_is_kept():
    """Never-searched and searched-with-nothing-to-show are different facts. An absent trial
    record must not read as the second, or no mined facet could ever run once."""
    assert surviving_mined_facets(("charge nurse",), {}) == ("charge nurse",)


def test_at_most_eight_mined_facets_are_bought_in_one_run():
    """The whole added request cost of mining, asserted as a LITERAL rather than against the
    constant the code caps with — an assertion that reads its own subject cannot fail when the
    subject moves. Eight facets is <=40 extra search GETs at the live `lane_search_pages=5`,
    about 40 s against a lane measured at ~198 requests on runs 134-137.
    """
    candidates = tuple(f"role number {n}" for n in range(30))

    assert len(surviving_mined_facets(candidates, {})) == 8


def test_the_cap_truncates_the_ranking_rather_than_sampling_it():
    """Best-evidenced first, and the eight kept are the eight best. Sampling would make the
    request set unreproducible from the store that chose it."""
    candidates = tuple(f"role number {n}" for n in range(30))

    assert surviving_mined_facets(candidates, {}) == candidates[:8]


def test_a_pruned_facet_does_not_consume_a_slot():
    """The cap counts what is BOUGHT. Counting drops against it would let one barren term
    shrink the run's real facet set by one, silently."""
    barren = FacetTrial(credited=MIN_TRIAL_POSTINGS, delivered=0)
    candidates = tuple(f"role number {n}" for n in range(30))

    kept = surviving_mined_facets(candidates, {candidates[0]: barren})
    assert len(kept) == 8
    assert candidates[0] not in kept


# ---------------------------------------------------------------------------------------
# The two sources stay apart
# ---------------------------------------------------------------------------------------


def test_lane_facets_defaults_to_neither_source():
    """A lane constructed before either read has happened must search unfaceted, exactly as it
    did before mining existed."""
    assert LaneFacets() == LaneFacets(profile=(), mined=())


@pytest.mark.parametrize(
    "title", ["Registered Nurse", "REGISTERED  NURSE", "registered-nurse", "Registered, Nurse"]
)
def test_spellings_of_a_profile_title_all_fold_onto_the_same_exclusion(title):
    """The exclusion has to hold under case, separators and word order together — each of the
    four spellings below is one an employer really writes."""
    assert mined_facet_candidates(_spread(title, count=3), ("registered nurse",)) == ()
