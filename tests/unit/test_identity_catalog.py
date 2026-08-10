"""The identity-kind catalog is closed, ranked and versioned (design §2, §3)."""

import pytest

from boardwatch.core.host_class import classify_host
from boardwatch.core.identity_kinds import (
    IDENTITY_KIND_NAMES,
    IDENTITY_KINDS,
    SUPPRESSING_KINDS,
    UnknownIdentityKind,
    kind_spec,
)


def test_exact_quad_is_the_only_suppressing_kind():
    """PINNED. Do not change this assertion to add a kind — change the spec first.

    PROGRAM P6 item 1: "only exact identities may suppress". core/identity.py:3 records the
    same as a standing contract: "cross-ID heuristics may only annotate". `cross_host` has
    neither company_id nor content_hash in its key, so it is not an exact identity; design
    §3.1 carries the concrete false-suppression counterexample (two different requisitions,
    same normalized company/title/location, one suppressed).
    """
    assert [s.name for s in SUPPRESSING_KINDS] == ["exact_quad"]


def test_cross_host_annotates_but_never_suppresses():
    assert kind_spec("cross_host").suppresses is False


def test_exact_provider_is_the_floor_and_never_suppresses():
    # It keys on (company_id, provider_posting_id), which postings enforces UNIQUE, so a
    # collision is impossible by construction. Stored anyway so the catalog is total.
    assert kind_spec("exact_provider").rank == 0
    assert kind_spec("exact_provider").suppresses is False


def test_content_hash_alone_never_suppresses():
    # The live corpus holds 809 hash-collision groups, 727 of which span different titles
    # or locations (design §2). Suppressing on the bare hash collapses different jobs.
    assert kind_spec("content_hash_only").suppresses is False
    assert kind_spec("company_title_location").suppresses is False


def test_suppressing_kinds_are_rank_ordered():
    ranks = [s.rank for s in SUPPRESSING_KINDS]
    assert ranks == sorted(ranks)


def test_ranks_are_unique_and_dense():
    assert sorted(k.rank for k in IDENTITY_KINDS) == list(range(len(IDENTITY_KINDS)))


def test_out_of_catalog_kind_raises_typed_error_not_a_new_bucket():
    with pytest.raises(UnknownIdentityKind):
        kind_spec("fuzzy_title_match")


def test_catalog_is_field_neutral():
    # Generalization: a US-citizen senior nurse must flow through unchanged. Identity is
    # company/title/location/body — none of which encode a role, field or country.
    blob = " ".join(IDENTITY_KIND_NAMES).lower()
    for banned in ("swe", "engineer", "software", "tech", "visa", "us", "nurse"):
        assert banned not in blob.split("_")


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://boards.greenhouse.io/acme/jobs/1", "ats"),
        ("https://jobs.lever.co/acme/abc", "ats"),
        ("https://acme.wd1.myworkdayjobs.com/en-US/acme/job/x", "ats"),
        ("https://www.linkedin.com/jobs/view/123", "aggregator"),
        ("https://indeed.com/viewjob?jk=1", "aggregator"),
        # A company's own careers host is NOT ats — companies has no URL column to match
        # against (design §3, correction). Unknown costs recall, never precision.
        ("https://careers.datadoghq.com/detail/1/", "unknown"),
        ("https://stripe.com/jobs/search?gh_jid=1", "unknown"),
        ("", "unknown"),
        ("not a url", "unknown"),
    ],
)
def test_classify_host(url: str, expected: str):
    assert classify_host(url) == expected


def test_subdomains_of_an_ats_host_classify_as_ats():
    assert classify_host("https://job-boards.eu.greenhouse.io/x/jobs/2") == "ats"


def test_a_host_merely_containing_an_ats_name_is_not_ats():
    # Suffix match on a dot boundary, never substring: this is an attacker-shaped and
    # typo-shaped hole that would let an arbitrary host win survivor election.
    assert classify_host("https://greenhouse.io.evil.example/x") == "unknown"
    assert classify_host("https://notgreenhouse.io/x") == "unknown"
