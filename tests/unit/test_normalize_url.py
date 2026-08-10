"""normalize_url is an allowlist, not a denylist (design §4.1).

`gh_jid` is load-bearing in real posting URLs (stripe.com/jobs/search?gh_jid=7976987).
A denylist that has not yet learned a new tracking param silently splits one posting
into two; an allowlist that has not learned a new identity param merges two postings,
which string-verify (§4.2) then catches. Merge-then-verify is the recoverable failure.
"""

from urllib.parse import urlsplit

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
    """Both params must be ALLOWLISTED, or the test cannot observe the sort.

    The earlier version used `a=1`, which is not allowlisted and so was dropped from both
    sides — leaving exactly one surviving param each, which is identically ordered however
    `kept` is joined. Deleting `sorted()` left it green. With two allowlisted params the two
    inputs produce `gh_jid=7&req_id=9` only if the join sorts.
    """
    assert normalize_url("https://e.com/j?gh_jid=7&req_id=9") == normalize_url(
        "https://e.com/j?req_id=9&gh_jid=7"
    )
    assert normalize_url("https://e.com/j?req_id=9&gh_jid=7") == (
        "https://e.com/j?gh_jid=7&req_id=9"
    )


def test_only_non_allowlisted_params_leaves_no_stray_question_mark():
    assert normalize_url("https://e.com/jobs?utm_source=x") == "https://e.com/jobs"


def test_host_scheme_port_and_path_folding():
    assert normalize_url("HTTP://WWW.Example.COM:80//jobs//123/#apply") == (
        "https://example.com/jobs/123"
    )


def test_input_with_no_host_is_returned_stripped():
    # Fail-safe: something that is not a URL must never blow up an identity computation.
    # This exits via the `not parts.netloc` branch — urlsplit parses it fine, as a path.
    assert normalize_url("  not a url  ") == "not a url"


def test_input_that_urlsplit_rejects_is_returned_stripped_not_raised():
    """The `except ValueError` branch, which nothing reached before.

    `urlsplit("not a url")` succeeds (scheme='', netloc='', path='not a url'), so the old
    single test left the handler entirely uncovered — deleting `try/except ValueError` kept
    it green. An unterminated IPv6 literal is what actually raises.
    """
    with pytest.raises(ValueError):
        urlsplit("http://[")
    assert normalize_url("  http://[  ") == "http://["


@pytest.mark.parametrize("param", ["gh_jid", "jid", "id", "jobId", "req_id", "posting_id"])
def test_allowlist_matches_case_insensitively(param: str):
    assert f"{param}=42" in normalize_url(f"https://e.com/j?{param}=42")
