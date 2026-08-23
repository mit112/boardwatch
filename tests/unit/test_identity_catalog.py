"""The identity-kind catalog is closed, ranked and versioned (design §2, §3)."""

import re

import pytest

from boardwatch.core.host_class import classify_host
from boardwatch.core.identity_kinds import (
    IDENTITY_KIND_NAMES,
    IDENTITY_KINDS,
    MERGING_KIND_NAMES,
    MERGING_KINDS,
    SUPPRESSING_KINDS,
    UnknownIdentityKind,
    kind_spec,
)


def test_the_suppressing_kinds_are_exactly_the_two_the_spec_admits():
    """PINNED. Do not add a kind to this list without changing the spec first.

    The spec WAS changed: PROGRAM P6 item 1 read "only exact identities may suppress", and
    the owner's ruling (D-294) admits `company_title_location` as a second suppressing kind
    on the strength of a measurement — postings sharing company, title and location reached
    leads twice and built two resumes each. Two things keep design §3.1's counterexample
    (two different requisitions, same normalized company/title/location, one suppressed) from
    coming true: the new kind may not MERGE, so no job anchor is rewritten, and it suppresses
    only when the two job descriptions are near-identical, which is the clause that tells a
    re-post apart from two openings sharing a generic title.

    `cross_host` stays out. It has neither company_id nor content_hash in its key, and unlike
    company_title_location it cannot compare bodies either — it spans hosts, so the same job
    legitimately carries different body text on each.
    """
    assert [s.name for s in SUPPRESSING_KINDS] == ["exact_quad", "company_title_location"]


def test_merging_is_a_strict_subset_of_suppressing():
    """A kind that cannot hide a posting must never be able to rewrite its job anchor.

    Documented as an invariant on `IdentityKindSpec.merges`; asserted here because the
    catalog is one line per kind and `merges=True, suppresses=False` is a plausible typo
    that would otherwise produce a silent no-op — a kind in MERGING_KIND_NAMES that no
    suppression can ever carry.
    """
    assert [s.name for s in MERGING_KINDS] == ["exact_quad"]
    assert MERGING_KIND_NAMES <= {s.name for s in SUPPRESSING_KINDS}
    for spec in IDENTITY_KINDS:
        assert not (spec.merges and not spec.suppresses), spec.name


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
    assert kind_spec("content_hash_only").merges is False


def test_company_title_location_suppresses_but_never_merges():
    """The asymmetry D-294 turns on, and the reason the two flags are separate.

    Hiding a posting is recoverable through `top --include-duplicates`; moving it onto
    another posting's job is undone only through `job_grouping_events`. The owner accepted
    the first on this key and not the second.
    """
    spec = kind_spec("company_title_location")
    assert spec.suppresses is True
    assert spec.merges is False


def test_suppressing_kinds_are_rank_ordered():
    ranks = [s.rank for s in SUPPRESSING_KINDS]
    assert ranks == sorted(ranks)


def test_ranks_are_unique_and_dense():
    assert sorted(k.rank for k in IDENTITY_KINDS) == list(range(len(IDENTITY_KINDS)))


def test_out_of_catalog_kind_raises_typed_error_not_a_new_bucket():
    with pytest.raises(UnknownIdentityKind):
        kind_spec("fuzzy_title_match")


def test_catalog_is_field_neutral():
    """Generalization: a US-citizen senior nurse must flow through unchanged.

    Identity is company/title/location/body — none of which encode a role, field or country.

    Tokenized on whitespace AND underscores. The earlier version joined the names with
    spaces and then split on `"_"` only, so the elements were fragments like
    `"location cross"` and a banned word was never one of them: adding a kind named `swe`
    yields the fragment `"host swe"`, and the test stayed green on the very mutation it
    exists to catch.
    """
    tokens = set(re.split(r"[\s_]+", " ".join(IDENTITY_KIND_NAMES).lower()))
    for banned in ("swe", "engineer", "software", "tech", "visa", "us", "nurse"):
        assert banned not in tokens


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
