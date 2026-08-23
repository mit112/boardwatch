"""lanes.dereference: URL -> posting-reference, no network involved anywhere in this file.

Every round-trip test below feeds a PINNED fixture through the provider's own shipped
parser to get a real RawPosting, then feeds that posting's real `.url` back through
`parse_posting_target`. Asserting against a hand-written URL would only prove the URL and
the regex agree with each other by construction; this proves the reverse mapping against
recorded evidence instead.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from boardwatch.core.board_urls import UnknownBoardURL
from boardwatch.lanes.dereference import (
    DEREFERENCE_REQUIRED_PROVIDERS,
    PostingTarget,
    UnresolvablePostingURL,
    parse_posting_target,
)
from boardwatch.providers import ashby, greenhouse, lever, smartrecruiters, workable, workday
from boardwatch.providers.registry import build_providers

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _fixture_json(provider: str, name: str) -> Any:
    return json.loads((FIXTURES / provider / name).read_bytes())


def test_greenhouse_round_trip() -> None:
    jobs = _fixture_json("greenhouse", "normal.json")["jobs"]
    assert jobs
    for job in jobs:
        posting = greenhouse.parse_job(job)
        target = parse_posting_target(posting.url)
        assert target.provider == "greenhouse"
        assert target.slug == "acme"
        assert target.posting_ref == posting.provider_posting_id


def test_lever_round_trip() -> None:
    raw_postings = _fixture_json("lever", "normal.json")
    assert raw_postings
    for raw in raw_postings:
        posting = lever.parse_posting(raw)
        target = parse_posting_target(posting.url)
        assert target.provider == "lever"
        assert target.slug == "acme"
        assert target.posting_ref == posting.provider_posting_id


def test_ashby_round_trip() -> None:
    jobs = _fixture_json("ashby", "normal.json")["jobs"]
    assert jobs
    for job in jobs:
        posting = ashby.parse_job(job)
        target = parse_posting_target(posting.url)
        assert target.provider == "ashby"
        assert target.slug == "acme"
        assert target.posting_ref == posting.provider_posting_id


def test_workable_round_trip() -> None:
    jobs = _fixture_json("workable", "normal.json")["jobs"]
    assert jobs
    for job in jobs:
        posting = workable.parse_job(job)
        target = parse_posting_target(posting.url)
        assert target.provider == "workable"
        assert target.slug == "acme"
        assert target.posting_ref == posting.provider_posting_id


def test_smartrecruiters_round_trip() -> None:
    listed = _fixture_json("smartrecruiters", "list_normal.json")["content"][0]
    detail = _fixture_json("smartrecruiters", "detail_normal.json")
    posting = smartrecruiters.parse_posting(listed, detail)
    target = parse_posting_target(posting.url)
    assert target.provider == "smartrecruiters"
    assert target.slug == "acme"
    assert target.posting_ref == posting.provider_posting_id


def test_workday_posting_url_refuses() -> None:
    """Workday's detail endpoint needs an externalPath path-string, not an id, and the
    public en-US/{site}/job/... URL's mapping back to that CXS path is verified nowhere
    in this repo (one tenant's externalUrl was ever recorded; nothing confirms the locale
    segment or host form is stable). Refuse rather than guess it."""
    listed = _fixture_json("workday", "list_normal.json")["jobPostings"][0]
    detail = _fixture_json("workday", "detail_normal.json")
    posting = workday.parse_posting(
        "acme.wd5.myworkdayjobs.com", "AcmeCareers", listed, detail, None
    )
    with pytest.raises(UnresolvablePostingURL):
        parse_posting_target(posting.url)


def test_bare_board_root_refuses() -> None:
    with pytest.raises(UnresolvablePostingURL):
        parse_posting_target("https://boards.greenhouse.io/acme")


def test_unrecognized_url_raises_unknown_board_url_not_unresolvable() -> None:
    # Not a recognized board target at all: board_urls' own error must propagate
    # unchanged, distinct from our UnresolvablePostingURL.
    with pytest.raises(UnknownBoardURL):
        parse_posting_target("https://example.com/careers/123")


def test_dereference_required_providers_matches_detail_url_providers() -> None:
    # Counted through a DIFFERENT path than the one that produced the module constant:
    # instantiate every registered provider and check its class for `_detail_url`,
    # instead of re-importing the same two hardcoded names on both sides.
    expected = frozenset(
        name for name, inst in build_providers().items() if hasattr(type(inst), "_detail_url")
    )
    assert DEREFERENCE_REQUIRED_PROVIDERS == expected


def test_posting_target_is_frozen() -> None:
    target = PostingTarget(provider="greenhouse", slug="acme", posting_ref="1")
    with pytest.raises(AttributeError):
        target.slug = "other"  # type: ignore[misc]
