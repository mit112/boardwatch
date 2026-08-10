"""Identity computation (design §1.2, §2, §2.1)."""

from datetime import datetime

import pytest

from boardwatch.core.identity_kinds import IDENTITY_KIND_NAMES
from boardwatch.core.posting_identity import (
    IdentityInputs,
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
