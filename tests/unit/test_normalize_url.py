"""normalize_url is an allowlist, not a denylist (design §4.1).

`gh_jid` is load-bearing in real posting URLs (stripe.com/jobs/search?gh_jid=7976987).
A denylist that has not yet learned a new tracking param silently splits one posting
into two; an allowlist that has not learned a new identity param merges two postings,
which string-verify (§4.2) then catches. Merge-then-verify is the recoverable failure.
"""

import pytest

from boardwatch.core.normalize import normalize_url


def test_identity_param_survives():
    assert normalize_url("https://stripe.com/jobs/search?gh_jid=7976987") == (
        "https://stripe.com/jobs/search?gh_jid=7976987"
    )


def test_tracking_params_are_dropped():
    assert (
        normalize_url(
            "https://stripe.com/jobs/search?gh_jid=7976987&utm_source=x&gh_src=abc&ref=y"
        )
        == "https://stripe.com/jobs/search?gh_jid=7976987"
    )


def test_param_order_is_not_identity():
    assert normalize_url("https://e.com/j?a=1&gh_jid=7") == normalize_url(
        "https://e.com/j?gh_jid=7&a=1"
    )


def test_only_non_allowlisted_params_leaves_no_stray_question_mark():
    assert normalize_url("https://e.com/jobs?utm_source=x") == "https://e.com/jobs"


def test_host_scheme_port_and_path_folding():
    assert normalize_url("HTTP://WWW.Example.COM:80//jobs//123/#apply") == (
        "https://example.com/jobs/123"
    )


def test_unparseable_input_is_returned_stripped_not_raised():
    # Fail-safe: a URL we cannot parse must never blow up an identity computation.
    assert normalize_url("  not a url  ") == "not a url"


@pytest.mark.parametrize("param", ["gh_jid", "jid", "id", "jobId", "req_id", "posting_id"])
def test_allowlist_matches_case_insensitively(param: str):
    assert f"{param}=42" in normalize_url(f"https://e.com/j?{param}=42")
