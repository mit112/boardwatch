"""A board's employer name is read off its slug in ONE place (T74 part B).

THE MEASUREMENT THIS DEFENDS. `companies.name` is the input to `normalize_company`, which is a
component of the `cross_host` posting identity. A board the bundled registry does not know used
to be watched with `name = slug` (`cli/companies_cmd.py`), so a board on `careers.acme.test` was
NAMED `careers.acme.test`. Two rows naming one employer therefore normalized to two different
strings and could not group at all — and once a truncated board's coverage rises, the same
requisition genuinely exists under both, because the two boards have disjoint provider id spaces.

WHAT THIS DOES NOT DO, and must not. `exact_quad` — the only kind in `SUPPRESSING_KINDS` — keys
on `company_id`, and two boards are two `companies` rows, so no naming change can make it fire
across them (`scan/coordinator.host_queues` states the same fact). Grouping happens on
`cross_host`, whose suppression is a designed deferral (design §3.1, `core/dedup.py`'s module
docstring). Nothing here enables it.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from boardwatch.core.posting_identity import IdentityInputs, compute_identities
from boardwatch.providers.base import employer_label_from_host
from boardwatch.providers.registry import (
    PROVIDER_CLASSES,
    derive_employer_name,
    employer_name_map,
)


def _inputs(company_id: int, company_name: str) -> IdentityInputs:
    """Two rows for ONE requisition, differing only in which company row they hang off."""
    return IdentityInputs(
        posting_id=company_id,
        company_id=company_id,
        company_name=company_name,
        provider_posting_id=f"p-{company_id}",
        title="Senior Platform Engineer",
        locations=["Springfield, Acmeland"],
        content_hash="c" * 64,
        body_text="we are hiring a senior platform engineer",
        url="https://careers.acme.test/careers/job/1",
        first_seen_at=datetime(2026, 9, 1, 12, 0, 0),
    )


def _cross_host(company_id: int, company_name: str) -> str:
    keys = [
        identity.identity_key
        for identity in compute_identities(_inputs(company_id, company_name))
        if identity.kind == "cross_host"
    ]
    assert len(keys) == 1
    return keys[0]


# ---------------------------------------------------------------- the measurement

def test_a_hostname_named_company_does_not_group_with_its_employer_named_twin() -> None:
    """THE DEFECT, stated as a test rather than as prose. Not a red-first test — it passes
    before and after, because it measures the INPUT the fix changes, not the fix."""
    assert _cross_host(1, "careers.acme.test") != _cross_host(2, "Acme Corp")


def test_the_two_rows_share_every_other_component_so_naming_is_the_only_difference() -> None:
    """Otherwise the test above would pass for the wrong reason."""
    hostname_named = compute_identities(_inputs(1, "careers.acme.test"))
    employer_named = compute_identities(_inputs(1, "Acme Corp"))
    differing = {
        a.kind
        for a, b in zip(hostname_named, employer_named, strict=True)
        if a.identity_key != b.identity_key
    }
    assert differing == {"cross_host"}


def test_exact_quad_keys_on_company_id_so_no_naming_change_can_make_it_fire() -> None:
    """The ticket's premise was that `exact_quad` keys on `normalize_company`. It does not —
    `cross_host` does. Two boards are two `companies` rows, so `exact_quad` cannot group across
    them under ANY name, and this pins that so the naming fix is never read as enabling it."""
    quad_one = next(i for i in compute_identities(_inputs(1, "Acme Corp")) if i.kind == "exact_quad")
    quad_two = next(i for i in compute_identities(_inputs(2, "Acme Corp")) if i.kind == "exact_quad")
    assert quad_one.identity_key != quad_two.identity_key


# ---------------------------------------------------------------- the fix

def test_a_derived_name_groups_the_hostname_named_row_with_its_employer_named_twin() -> None:
    """RED before T74: `derive_employer_name` did not exist, and the name stored for this board
    was the slug — which is the assertion above, reading two different keys."""
    derived = derive_employer_name("eightfold", "careers.acme.test")
    assert derived == "acme"
    assert _cross_host(1, derived) == _cross_host(2, "Acme Corp")


def test_two_boards_of_one_employer_on_one_provider_derive_the_same_name() -> None:
    """The shape the throttle fix EXPOSES: one employer with a board on its own domain and a
    second on the vendor's, under disjoint id spaces."""
    own_domain = derive_employer_name("eightfold", "careers.acme.test")
    vendor_hosted = derive_employer_name("eightfold", "acme.eightfold.ai")
    assert own_domain == vendor_hosted == "acme"


# ---------------------------------------------------------------- one source of truth

#: One well-formed slug per REGISTERED provider, with the employer name it must derive to.
#: Keyed by provider so `test_every_provider_in_the_registry_...` can assert the table covers
#: `PROVIDER_CLASSES` exactly — a new provider then fails here until its naming is decided,
#: rather than silently taking the "the slug is the employer token" default it may not want.
_SLUG_SHAPES: dict[str, tuple[str, str]] = {
    # the slug IS the employer's token
    "greenhouse": ("acme", "acme"),
    "lever": ("acme", "acme"),
    "ashby": ("acme", "acme"),
    "workable": ("acme", "acme"),
    "smartrecruiters": ("acme", "acme"),
    # a HOST names the employer through its first non-career-site label
    "eightfold": ("careers.acme.test", "acme"),
    "jibe": ("careers.acme.test", "acme"),
    "phenom": ("careers.acme.test/us/en", "acme"),
    # a composite slug names it in ONE of its segments, never in the career-site segment
    "workday": ("acme.wd1.myworkdayjobs.com/acme/Acme_External_Site", "acme"),
    "oraclehcm": ("acme.fa.us2.oraclecloud.com/CX_1", "acme"),
    # the one provider whose slug is a CATEGORY, not an employer
    "amazon": ("software-development", "Amazon"),
}


def test_every_provider_in_the_registry_resolves_through_the_one_entry_point() -> None:
    """`derive_employer_name` answers for EVERY registered provider, including the five whose
    slug is already the employer's token and declare no deriver of their own. A provider that
    fell through would be a second, silent naming rule."""
    assert set(_SLUG_SHAPES) == {cls.name for cls in PROVIDER_CLASSES}
    for provider, (slug, _expected) in _SLUG_SHAPES.items():
        assert derive_employer_name(provider, slug) is not None, provider


def test_an_unregistered_provider_derives_nothing() -> None:
    assert derive_employer_name("nosuchprovider", "acme") is None


def test_only_providers_whose_slug_is_not_the_employer_token_declare_a_deriver() -> None:
    """Pins the split so a sixth deriver has to justify itself, and so a provider losing its
    deriver in a refactor is a failing test rather than a silently mis-named company."""
    assert set(employer_name_map()) == {
        "amazon", "eightfold", "jibe", "oraclehcm", "phenom", "workday",
    }


@pytest.mark.parametrize("provider", sorted(_SLUG_SHAPES))
def test_the_derived_name_for_every_registry_slug_shape(provider: str) -> None:
    slug, expected = _SLUG_SHAPES[provider]
    assert derive_employer_name(provider, slug) == expected


@pytest.mark.parametrize(
    ("slug", "expected"),
    [("acme.eightfold.ai", "acme"), ("jobs.acmecorp.example", "acmecorp")],
)
def test_the_other_eightfold_host_shapes(slug: str, expected: str) -> None:
    assert derive_employer_name("eightfold", slug) == expected


@pytest.mark.parametrize(
    "slug",
    [
        "garbage",                 # not a hostname at all
        "careers.eightfold.ai",    # every label is the vendor's or a career-site word
        "jobs.eightfold.ai",
    ],
)
def test_a_slug_that_names_no_employer_derives_nothing_rather_than_guessing(slug: str) -> None:
    """A wrong employer name MERGES two different companies' postings. That is strictly worse
    than a leaked duplicate, so the honest answer is None and the caller keeps what it has."""
    assert derive_employer_name("eightfold", slug) is None


# ---------------------------------------------------------------- the host rule itself

@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("careers.acme.test", "acme"),
        ("jobs.acme.test", "acme"),
        ("www.acme.test", "acme"),
        ("acme.test", "acme"),
        # no public suffix list here, and the first-label rule does not need one
        ("careers.acme.co.uk", "acme"),
        ("acme.co.uk", "acme"),
        # nested career-site chrome
        ("www.jobs.acme.test", "acme"),
        # every label is a career-site word once the public label is dropped
        ("jobs.test", None),
        ("careers.jobs.test", None),
    ],
)
def test_the_first_non_career_site_label_is_the_employer(host: str, expected: str | None) -> None:
    assert employer_label_from_host(host) == expected


def test_a_declared_vendor_suffix_is_removed_before_the_labels_are_read() -> None:
    """Without it, `careers.eightfold.ai` would read the VENDOR's name as the employer's."""
    assert employer_label_from_host("careers.eightfold.ai") == "eightfold"
    assert (
        employer_label_from_host("careers.eightfold.ai", vendor_suffixes=(".eightfold.ai",))
        is None
    )


def test_no_capitalization_is_invented() -> None:
    """`northropgrumman` cannot be word-split without a dictionary, so nothing here tries.
    `normalize_company` folds case before any two names are compared, so the casing costs the
    grouping nothing — and a guessed display name would be a claim the slug does not carry."""
    assert derive_employer_name("eightfold", "jobs.acmecorp.example") == "acmecorp"
