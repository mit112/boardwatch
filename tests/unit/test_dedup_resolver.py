"""Suppression: only provable duplicates, precision over recall (design §2–§5).

The unrecoverable error in this system is suppressing a real lead. Every ambiguous case
below must resolve to "nothing suppressed".
"""

from datetime import datetime
from unittest import mock

import pytest

from boardwatch.core import dedup
from boardwatch.core.dedup import (
    MissingSuppressionResolver,
    _elect,
    elect_cross_host_survivor,
    resolve_duplicates,
)
from boardwatch.core.identity_kinds import IdentityKindSpec
from boardwatch.core.normalize import content_hash
from boardwatch.core.posting_identity import (
    IdentityInputs,
    PostingIdentity,
    compute_identities,
)


def _p(pid: int, **over: object) -> IdentityInputs:
    base: dict[str, object] = {
        "posting_id": pid,
        "company_id": 10,
        "company_name": "Datadog",
        "provider_posting_id": f"gh-{pid}",
        "title": "Technical Account Manager II, EMEA",
        "locations": ["Amsterdam"],
        "content_hash": "a" * 64,
        "body_text": "we are hiring a tam",
        "url": f"https://boards.greenhouse.io/datadog/jobs/{pid}",
        "first_seen_at": datetime(2026, 8, 1, 12, 0, 0),
    }
    base.update(over)
    return IdentityInputs(**base)  # type: ignore[arg-type]


def _resolve(
    *rows: IdentityInputs, overrides: dict[int, tuple[PostingIdentity, ...]] | None = None
):
    identities = {r.posting_id: compute_identities(r) for r in rows}
    if overrides:
        identities.update(overrides)
    return resolve_duplicates(rows, identities)


# --- the injected hash-collision test (Gate P6) --------------------------------------


def test_identical_content_hash_with_different_titles_is_never_suppressed():
    """Reproduces Datadog 5843/5846/5849: one content_hash, three requisitions.

    809 such groups exist in the live corpus and 727 of them span a different title or
    location. A hash-keyed dedup collapses all of them.
    """
    result = _resolve(
        _p(5843, title="Technical Account Manager II, EMEA"),
        _p(5846, title="Technical Account Manager II, South Africa"),
        _p(5849, title="Technical Account Manager III, Madrid"),
    )
    assert result == ()


def test_identical_content_hash_with_different_locations_is_never_suppressed():
    result = _resolve(
        _p(1, locations=["Amsterdam"]),
        _p(2, locations=["Madrid"]),
    )
    assert result == ()


def test_string_verify_blocks_suppression_when_bodies_diverge():
    """Force identity_key equality with divergent bodies.

    This is the test that proves the wrong job cannot be deduped even when the hashes
    agree: it simulates both a SHA-256 collision and, more realistically, a
    key-construction bug that hashes two different tuples to one string.
    """
    a, b = _p(1, body_text="alpha"), _p(2, body_text="beta")
    forged = compute_identities(a)
    result = _resolve(a, b, overrides={2: forged})
    assert result == ()


def test_postings_with_no_location_evidence_are_never_suppressed():
    """The §2.1 case: two postings identical on company, title and content_hash, both with
    no locations. No exact_quad identity is emitted for either, so nothing can suppress.

    This is the one the sentinel would have broken: with "[]", both sides compare equal and
    both string-verify and the recount happily agree on the wrong answer.
    """
    result = _resolve(_p(1, locations=None), _p(2, locations=None))
    assert result == ()


# --- exact_quad, the safe case --------------------------------------------------------


def test_exact_quad_duplicates_leave_exactly_one_survivor():
    result = _resolve(_p(1), _p(2))
    assert len(result) == 1
    assert result[0].posting_id == 2
    assert result[0].survivor_posting_id == 1
    assert result[0].kind == "exact_quad"


def test_three_way_duplicate_suppresses_two():
    result = _resolve(_p(1), _p(2), _p(3))
    assert {s.posting_id for s in result} == {2, 3}
    assert {s.survivor_posting_id for s in result} == {1}


def test_survivor_is_the_earliest_first_seen_not_the_lowest_id():
    result = _resolve(
        _p(9, first_seen_at=datetime(2026, 1, 1)),
        _p(1, first_seen_at=datetime(2026, 6, 1)),
    )
    assert result[0].survivor_posting_id == 9
    assert result[0].posting_id == 1


def test_lowest_posting_id_breaks_an_identical_first_seen_at():
    """Not a rare tiebreak — the common one.

    first_seen_at is second-resolution and a single board's postings are inserted in one
    pass, so two rows sharing a timestamp is routine. A survivor that moves between runs
    makes the 7-day duplicate-leakage measurement Gate P6 requires meaningless.

    This pins the end-to-end guarantee. It does NOT isolate the `_elect` tiebreak, and an
    earlier docstring wrongly claimed it did ("without it the survivor depends on dict
    ordering"): `resolve_duplicates` groups over `sorted(by_id.items())`, so members always
    reach `_elect` in posting-id order and `min` returns the lowest id on a tie whether or
    not the key mentions posting_id. Deleting that term leaves this test green. The
    tiebreak is isolated by `test_elect_breaks_a_first_seen_tie_by_lowest_posting_id`.
    """
    same = datetime(2026, 3, 3, 9, 0, 0)
    forward = _resolve(_p(7, first_seen_at=same), _p(4, first_seen_at=same))
    backward = _resolve(_p(4, first_seen_at=same), _p(7, first_seen_at=same))
    assert forward[0].survivor_posting_id == 4
    assert forward[0].posting_id == 7
    assert forward == backward


def test_elect_breaks_a_first_seen_tie_by_lowest_posting_id():
    """The tiebreak itself, reached with members deliberately out of posting-id order.

    `_elect` is the sole guard on tie determinism if the caller's ordering ever changes —
    a `.values()` iteration, a different GROUP BY, a set. Called directly with the higher
    id first, an election keyed only on (host_class, first_seen_at) returns that first row,
    so dropping the posting_id term turns this red where the end-to-end test above cannot.
    """
    same = datetime(2026, 3, 3, 9, 0, 0)
    members = [_p(7, first_seen_at=same), _p(4, first_seen_at=same)]
    assert _elect(members).posting_id == 4
    assert _elect(list(reversed(members))).posting_id == 4


def test_survivor_is_stable_under_shuffled_input_order():
    rows = [_p(3), _p(1), _p(2)]
    forward = resolve_duplicates(rows, {r.posting_id: compute_identities(r) for r in rows})
    backward = resolve_duplicates(
        list(reversed(rows)), {r.posting_id: compute_identities(r) for r in rows}
    )
    assert forward == backward


def test_a_single_posting_is_never_a_duplicate_of_itself():
    assert _resolve(_p(1)) == ()


def test_different_companies_do_not_match_on_exact_quad():
    """`assert result == ()`, not `all(... for s in result)`.

    The old assertion was vacuous: `result` is empty here, so `all()` was true regardless.
    Worse, it could not observe its own mutation — dropping `company` from the exact_quad
    key lets these two group, but `_verify_quad` still compares `a.company_id == b.company_id`
    and elects no losers, so `result` stays `()` and the old form stayed green. The key-level
    guard is `test_different_companies_produce_different_exact_quad_keys` in
    test_posting_identity.py; this one pins the end-to-end outcome.
    """
    assert _resolve(_p(1, company_id=10), _p(2, company_id=11)) == ()


def test_elect_prefers_the_ats_host_over_an_earlier_first_seen_aggregator():
    """host_class is the FIRST term of the election key (D-086), ahead of first_seen_at.

    Every other exact_quad test seeds a single Greenhouse host, so none of them can observe
    the precedence — with one host class the key collapses to (first_seen_at, posting_id) and
    reordering the terms changes nothing. Here the aggregator was seen first, so an election
    keyed on first_seen_at before host_class returns posting 1 and this goes red.
    """
    aggregator = _p(1, url=_LINKEDIN, first_seen_at=datetime(2026, 1, 1))
    ats = _p(2, url=_GREENHOUSE, first_seen_at=datetime(2026, 6, 1))
    assert _elect([aggregator, ats]).posting_id == 2
    assert _elect([ats, aggregator]).posting_id == 2


# --- cross_host: annotate-only (design §3, §3.1) --------------------------------------

_LINKEDIN = "https://www.linkedin.com/jobs/view/999"
_COMPANY_SITE = "https://careers.datadoghq.com/detail/1/"
_GREENHOUSE = "https://boards.greenhouse.io/datadog/jobs/1"
_LEVER = "https://jobs.lever.co/datadog/2"


def _cross(pid: int, url: str, **over: object) -> IdentityInputs:
    # Different company rows and different bodies, so ONLY cross_host can ever match.
    # `over` is merged rather than splatted alongside the defaults: the ENG-241 test below
    # overrides provider_posting_id, which would otherwise be passed twice.
    fields: dict[str, object] = {
        "company_id": pid,
        "provider_posting_id": f"x-{pid}",
        "content_hash": f"{pid:064d}",
        "body_text": f"body {pid}",
        "url": url,
    }
    fields.update(over)
    return _p(pid, **fields)


def test_cross_host_never_suppresses_even_with_a_clean_ats_aggregator_pair():
    """The pair the design would most like to dedup, and still does not.

    PROGRAM item 1 restricts suppression to exact identities; cross_host keys on
    (normalized_company, normalized_title, normalized_locations) with no company_id and no
    content_hash. Both rows stay visible. See design §3.1 for the deferral and its re-entry
    path.
    """
    assert _resolve(_cross(1, _GREENHOUSE), _cross(2, _LINKEDIN)) == ()


def test_the_eng_241_counterexample_stays_visible():
    """Two genuinely different requisitions that cross_host would have collapsed.

    Acme runs Greenhouse req ENG-241; LinkedIn carries req ENG-319. Same normalized company,
    same title, same location, different bodies. String-verify cannot catch it, because it
    re-compares the same three weak fields. This test must stay green for as long as
    cross_host is annotate-only.
    """
    a = _cross(1, _GREENHOUSE, provider_posting_id="ENG-241", body_text="build the api")
    b = _cross(2, _LINKEDIN, provider_posting_id="ENG-319", body_text="build the ui")
    assert _resolve(a, b) == ()


def test_no_suppression_anywhere_ever_carries_the_cross_host_kind():
    """Guards the whole surface, not one pair: nothing in this module may emit it.

    The exact_quad pair carries a *different* company name and title from the cross pair on
    purpose. Sharing them — as an earlier version of this test did — puts all three
    unsuppressed rows in one cross_host group with two ATS members, which
    `elect_cross_host_survivor` declines as ambiguous. The test then stayed green even with
    `cross_host.suppresses` flipped to True, i.e. it could not fail for its own claim.

    `assert result` matters too: `all()` over an empty tuple is vacuously true.
    """
    result = _resolve(
        _cross(1, _GREENHOUSE),
        _cross(2, _LINKEDIN),
        _p(3, company_name="Acme", title="Backend Engineer"),
        _p(4, company_name="Acme", title="Backend Engineer"),
    )
    assert result
    assert all(s.kind == "exact_quad" for s in result)


# The election logic ships and is proven now, so enabling it later is one boolean (§3.1).
# These test elect_cross_host_survivor directly; none of them can produce a suppression.


def test_election_picks_the_single_ats_row():
    a, b = _cross(1, _GREENHOUSE), _cross(2, _LINKEDIN)
    assert elect_cross_host_survivor([a, b]) is a


def test_election_declines_when_there_is_no_ats_row():
    assert (
        elect_cross_host_survivor(
            [_cross(1, _LINKEDIN), _cross(2, "https://indeed.com/viewjob?jk=2")]
        )
        is None
    )


def test_election_declines_when_two_ats_rows_make_the_survivor_ambiguous():
    assert (
        elect_cross_host_survivor([_cross(1, _GREENHOUSE), _cross(2, _LEVER), _cross(3, _LINKEDIN)])
        is None
    )


def test_election_declines_when_the_only_non_aggregator_is_unknown():
    # A company's own careers host classifies unknown: it is neither kept nor dropped.
    assert elect_cross_host_survivor([_cross(1, _COMPANY_SITE), _cross(2, _LINKEDIN)]) is None


def test_election_declines_when_there_is_nothing_to_drop():
    assert elect_cross_host_survivor([_cross(1, _GREENHOUSE), _cross(2, _LEVER)]) is None


# --- the floor (design §2) ------------------------------------------------------------


def test_exact_provider_never_suppresses():
    """It keys on (company_id, provider_posting_id), which postings enforces UNIQUE.

    If this ever fires, that constraint has been lost. Asserted as `== ()` rather than
    `all(s.kind != ... for s in result)`: the result is empty, so the `all()` form was true
    for any implementation at all.
    """
    a = _p(1, title="Alpha", provider_posting_id="gh-1")
    b = _p(2, title="Beta", provider_posting_id="gh-1")
    assert _resolve(a, b) == ()


def test_annotate_only_kinds_never_appear_in_a_suppression():
    """Same vacuity as above: `result` is empty, so the old `all()` observed nothing.

    Flipping `suppresses=True` on either annotate-only kind now raises
    MissingSuppressionResolver rather than returning a suppression — pinned separately by
    test_a_suppressing_kind_without_a_resolver_raises_a_typed_error.
    """
    assert (
        _resolve(
            _p(1, content_hash="b" * 64, title="A"),
            _p(2, content_hash="b" * 64, title="B"),
        )
        == ()
    )


def test_a_posting_is_suppressed_at_most_once():
    """Asserted as the concrete outcome, because the de-duplication is structural.

    `resolve_duplicates` accumulates into a dict keyed on posting_id, so
    `len({s.posting_id ...}) == len(result)` is true for every possible input and no mutation
    of the resolver can make it red. The observable claim is which rows lose, so assert that.
    """
    result = _resolve(_p(1), _p(2), _p(3))
    assert {s.posting_id for s in result} == {2, 3}
    assert {s.survivor_posting_id for s in result} == {1}


def test_a_stale_exact_quad_cannot_suppress_postings_with_no_location_evidence():
    """The stored path, which is the only path production uses (design §1.2, D-083).

    `compute_identities` emits no exact_quad without location evidence, but this resolver
    groups STORED identities and nothing in the scan path rewrites them: `scan/apply.py`
    refreshes `locations_json` on every observation while `identities_complete` checks only
    that a current-version row EXISTS. So a posting can lose its locations and keep the
    exact_quad row that was written when it still had them.

    `_verify_quad` must then refuse on absence, not compare: two Nones are EQUAL, so a check
    that only compares passes and suppresses on evidence the catalog marks non-suppressing.
    Dropping the `loc_a is not None` clause turns this red.
    """
    stale = (PostingIdentity("exact_quad", "key-from-when-they-had-locations"),)
    result = _resolve(
        _p(1, locations=None),
        _p(2, locations=None),
        overrides={1: stale, 2: stale},
    )
    assert result == ()


def test_a_suppressing_kind_without_a_resolver_raises_a_typed_error():
    """A catalog edit reaches this: it is not unreachable just because defaults avoid it.

    Marking content_hash_only as suppressing names a kind `_RESOLVERS` has no entry for. That
    used to surface as a bare KeyError from inside the ranker; violations are typed at the
    raise site so behaviour is never classified by string-matching a message.
    """
    fake = IdentityKindSpec("content_hash_only", 4, True)
    rows = [_p(1), _p(2)]
    identities = {r.posting_id: compute_identities(r) for r in rows}
    with mock.patch.object(dedup, "SUPPRESSING_KINDS", (fake,)):
        with pytest.raises(MissingSuppressionResolver) as excinfo:
            resolve_duplicates(rows, identities)
    assert excinfo.value.name == "content_hash_only"


# --- body evidence on the STORED path (design §4.3 of the JD-acquisition spec) ---------


@pytest.mark.parametrize("blank", ["", "   \n\t "])
def test_a_stale_exact_quad_cannot_suppress_two_bodyless_postings(blank):
    """Presence, not equality, exactly as for locations — and for the same reason.

    `compute_identities` no longer emits an `exact_quad` without body evidence, but this
    resolver groups **stored** identities and nothing in the scan path rewrites them on its
    own schedule. The live corpus already holds rows written before the body check existed.
    Two absent bodies compare EQUAL, so an equality-only check would pass and suppress on
    evidence the catalog marks non-suppressing.
    """
    a = _p(1, body_text=blank, content_hash=content_hash(blank))
    b = _p(2, body_text=blank, content_hash=content_hash(blank))
    stale = (PostingIdentity("exact_quad", "a-key-written-before-the-body-check"),)
    assert _resolve(a, b, overrides={1: stale, 2: stale}) == ()


def test_one_bodyless_side_cannot_be_suppressed_by_a_real_posting():
    """Asymmetric case: a real body and a stub are not the same posting."""
    a = _p(1, body_text="we are hiring a tam")
    b = _p(2, body_text="   ", content_hash=content_hash("   "))
    stale = (PostingIdentity("exact_quad", "a-key-written-before-the-body-check"),)
    assert _resolve(a, b, overrides={1: stale, 2: stale}) == ()


def test_two_real_postings_with_one_body_still_suppress():
    """The fix must not disarm suppression where the evidence is genuinely present."""
    a = _p(1, body_text="we are hiring a tam")
    b = _p(2, body_text="we are hiring a tam")
    suppressions = _resolve(a, b)
    assert [s.posting_id for s in suppressions] == [2]
    assert suppressions[0].kind == "exact_quad"
