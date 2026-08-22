"""Identity computation (design §1.2, §2, §2.1)."""

import hashlib
from datetime import datetime

import pytest

from boardwatch.core.identity_kinds import IDENTITY_KIND_NAMES
from boardwatch.core.normalize import content_hash
from boardwatch.core.posting_identity import (
    IdentityInputs,
    body_evidence,
    compute_identities,
    normalized_locations,
)


def _inputs(**over: object) -> IdentityInputs:
    base: dict[str, object] = {
        "posting_id": 1,
        "company_id": 10,
        "company_name": "Datadog, Inc.",
        "provider_posting_id": "gh-5843",
        "title": "Technical Account Manager II, EMEA",
        "locations": ["Amsterdam", "Dublin"],
        "content_hash": "a" * 64,
        "body_text": "we are hiring",
        "url": "https://boards.greenhouse.io/datadog/jobs/5843",
        "first_seen_at": datetime(2026, 8, 1, 12, 0, 0),
    }
    base.update(over)
    return IdentityInputs(**base)  # type: ignore[arg-type]


def test_locations_are_order_and_case_independent():
    assert normalized_locations(["Dublin", "Amsterdam"]) == normalized_locations(
        ["amsterdam", "  DUBLIN "]
    )


@pytest.mark.parametrize("absent", [None, [], ["", "   "]])
def test_absent_location_evidence_is_None_not_an_empty_sentinel(absent):
    """None, never "[]" (design §2.1).

    An "[]" sentinel makes every location-less posting equal to every other location-less
    posting on the locations component. Neither string-verify nor the §6.3 recount can catch
    it, because both sides genuinely compare equal — they would agree on the wrong answer.
    None instead means the identity is not emitted at all, so no suppression is possible.
    """
    assert normalized_locations(absent) is None


def test_every_kind_is_in_the_closed_catalog():
    kinds = {i.kind for i in compute_identities(_inputs())}
    assert kinds <= set(IDENTITY_KIND_NAMES)


def test_all_five_kinds_are_emitted_when_every_input_is_present():
    assert {i.kind for i in compute_identities(_inputs())} == set(IDENTITY_KIND_NAMES)


def test_location_bearing_kinds_are_omitted_when_there_is_no_location_evidence():
    kinds = {i.kind for i in compute_identities(_inputs(locations=None))}
    assert kinds == {"exact_provider", "content_hash_only"}
    # Named individually so a future reader sees which three depend on locations.
    assert "exact_quad" not in kinds
    assert "cross_host" not in kinds
    assert "company_title_location" not in kinds


def test_one_row_per_kind():
    kinds = [i.kind for i in compute_identities(_inputs())]
    assert len(kinds) == len(set(kinds))


def test_computation_is_deterministic():
    assert compute_identities(_inputs()) == compute_identities(_inputs())


def test_posting_id_does_not_enter_any_key():
    a = compute_identities(_inputs(posting_id=1))
    b = compute_identities(_inputs(posting_id=999))
    assert a == b


def test_different_titles_produce_different_exact_quad_keys():
    # The real corpus case: Datadog 5843/5846/5849 share a content_hash and differ in title.
    def quad(inp: IdentityInputs) -> str:
        return next(i.identity_key for i in compute_identities(inp) if i.kind == "exact_quad")

    assert quad(_inputs(title="Technical Account Manager II, EMEA")) != quad(
        _inputs(title="Technical Account Manager III, Madrid")
    )


def test_different_locations_produce_different_exact_quad_keys():
    def quad(inp: IdentityInputs) -> str:
        return next(i.identity_key for i in compute_identities(inp) if i.kind == "exact_quad")

    assert quad(_inputs(locations=["Dublin"])) != quad(_inputs(locations=["Madrid"]))


def test_different_companies_produce_different_exact_quad_keys():
    """company_id is a component of the ONLY suppressing key, and had no test for it.

    The end-to-end test in test_dedup_resolver.py cannot cover this: drop `company` from the
    key and those two postings do group, but `_verify_quad` independently compares
    `a.company_id == b.company_id` and elects no losers, so the observable result is
    unchanged. That left the cross-company component of the suppressing key guarded by one
    mechanism and no test. Asserted at the key level, where the mutation is visible.
    """

    def quad(inp: IdentityInputs) -> str:
        return next(i.identity_key for i in compute_identities(inp) if i.kind == "exact_quad")

    assert quad(_inputs(company_id=10)) != quad(_inputs(company_id=11))


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("C++ Developer", "C# Developer"),
        ("C++ Developer", "C Developer"),
        ("C# Developer", "C Developer"),
    ],
)
def test_language_punctuation_survives_into_the_exact_quad_key(left, right):
    """`normalize_title` folds [\\W_] to spaces, which made C++, C# and C one title.

    exact_quad also requires an identical content_hash, so the collision only bites when one
    body is reused across a role family — which is exactly what boilerplate reqs do, and it
    would suppress a real, different role. `_verify_quad` cannot catch it either: it re-runs
    `normalize_title`, so it agrees with the key on the wrong answer.

    Removing the `+`/`#` folding from normalize_title turns all three of these red.
    """

    def quad(inp: IdentityInputs) -> str:
        return next(i.identity_key for i in compute_identities(inp) if i.kind == "exact_quad")

    assert quad(_inputs(title=left)) != quad(_inputs(title=right))


def test_punctuation_noise_still_collapses():
    """The counterweight: the folding above must not start splitting real duplicates.

    Measured on the live corpus, 8 of 147 suppression groups differ in raw title and every
    one differs only in punctuation, spacing or case on the same role. These are the real
    shapes from that set; if a future "stricter title" change breaks them, it is trading 8
    genuine suppressions for a collision that corpus does not contain.
    """

    def quad(inp: IdentityInputs) -> str:
        return next(i.identity_key for i in compute_identities(inp) if i.kind == "exact_quad")

    for left, right in (
        ("Mobile Expert - Bilingual Spanish Preferred", "Mobile Expert, Bilingual Spanish"
         " Preferred"),
        ("Mobile Associate, Store-in-Store, Retail Sales", "Mobile Associate, Store in Store"
         " - Retail Sales"),
        ("Lead Software Engineer (Java, Javascript)", "Lead Software Engineer (Java, JavaScript)"),
        ("IC design Engineer", "IC Design Engineer"),
        ("Manager, Clinical Study Lead", "Manager Clinical Study Lead"),
    ):
        assert quad(_inputs(title=left)) == quad(_inputs(title=right)), (left, right)


def test_key_components_cannot_be_shifted_across_the_separator():
    """Without a separator, ("ab", "c") and ("a", "bc") hash alike and two postings collide.

    The shift has to be aimed at the company_id/title boundary, because that is the only
    place two *bare* components meet. `locations` is emitted by `json.dumps`, so it always
    arrives wrapped in `["..."]` and delimits itself on both sides; a title cannot end in
    `[` either, since `normalize_title` folds every non-alphanumeric to a space. An earlier
    version of this test shifted a word between `title` and `locations` and therefore could
    not fail under `_SEP = ""` — the JSON quoting kept the two keys distinct on its own.

    company_id 10 + title "1data" and company_id 101 + title "data" both concatenate to
    "101data", so this goes red the moment the separator stops separating.
    """

    def ctl(inp: IdentityInputs) -> str:
        return next(
            i.identity_key for i in compute_identities(inp) if i.kind == "company_title_location"
        )

    assert ctl(_inputs(company_id=10, title="1data")) != ctl(
        _inputs(company_id=101, title="data")
    )


# --- body evidence (design §4.3 of the JD-acquisition spec) ---------------------------


def test_empty_and_whitespace_bodies_share_one_content_hash():
    """The premise of every test below, asserted so it cannot rot silently.

    `postings.body_text` is NOT NULL, but NOT NULL is not non-empty. A stub posting stores
    "" or whitespace, and `content_hash` folds both to the SHA-256 of the empty string — so
    the hash component of `exact_quad` carries no information at all for a stub.
    """
    assert content_hash("") == content_hash("   \n\t ")
    assert content_hash("") == hashlib.sha256(b"").hexdigest()


@pytest.mark.parametrize("absent", ["", "   ", "  \n\t "])
def test_absent_body_evidence_is_None_not_an_empty_sentinel(absent):
    """None, for the same reason `normalized_locations` returns None (design §2.1).

    An "" sentinel makes every body-less posting equal to every other one on the hash
    component, and neither the string re-verify nor the §6.3 recount can catch it: both
    sides genuinely compare equal, so they agree on the wrong answer.
    """
    assert body_evidence(absent) is None


def test_body_evidence_is_the_normalized_body_when_present():
    assert body_evidence("  We Are\tHIRING ") == "we are hiring"


@pytest.mark.parametrize("absent", ["", "   \n\t "])
def test_exact_quad_is_omitted_when_there_is_no_body_evidence(absent):
    """Suppression requires body evidence; an empty body is its absence (D-250's reasoning).

    Without this, two genuinely different body-less postings at one company sharing a
    normalized title and locations suppress each other — `exact_quad` is the only
    suppressing kind, and its hash component is identical for every stub.
    """
    kinds = {i.kind for i in compute_identities(_inputs(body_text=absent))}
    assert "exact_quad" not in kinds


@pytest.mark.parametrize("absent", ["", "   \n\t "])
def test_only_exact_quad_is_withheld_when_the_body_is_absent(absent):
    """The non-suppressing kinds still land, so `identities_complete` stays true.

    It counts distinct posting_ids carrying any current-version row, not kinds per posting.
    A stub that emitted nothing at all would make it False and turn suppression off
    corpus-wide.
    """
    kinds = {i.kind for i in compute_identities(_inputs(body_text=absent))}
    assert kinds == set(IDENTITY_KIND_NAMES) - {"exact_quad"}
    assert kinds


def test_a_body_bearing_stub_hash_still_earns_an_exact_quad():
    """The guard reads the body, not the hash: a real body with a hand-set hash is fine."""
    kinds = {i.kind for i in compute_identities(_inputs(body_text="we are hiring"))}
    assert "exact_quad" in kinds
