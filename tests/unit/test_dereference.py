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
    PostingTarget,
    UnresolvablePostingURL,
    parse_posting_target,
)
from boardwatch.providers import ashby, greenhouse, lever, smartrecruiters, workable, workday

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


def test_smartrecruiters_posting_url_refuses() -> None:
    """The pinned `postingUrl` fixture is explicitly synthetic (see
    tests/fixtures/smartrecruiters/README.md) and was authored to mimic this provider's
    own CONSTRUCTED FALLBACK (.../{identifier}/{posting_id}), not a real public
    SmartRecruiters posting URL — see test below for what the real shape actually is.
    Refuse rather than trust a shape only the fixture's author, not evidence, supports."""
    listed = _fixture_json("smartrecruiters", "list_normal.json")["content"][0]
    detail = _fixture_json("smartrecruiters", "detail_normal.json")
    posting = smartrecruiters.parse_posting(listed, detail)
    with pytest.raises(UnresolvablePostingURL):
        parse_posting_target(posting.url)


def test_smartrecruiters_real_shape_combines_id_and_slug_in_one_segment() -> None:
    """Pins the hazard in code, not only in prose: SmartRecruiters' own public API
    documentation shows a real posting URL's last path segment is "{id}-{title-slug}"
    (e.g. .../12308096-quality-assurance-manager), not the bare id the fixture's
    synthetic postingUrl mimics. A naive last-segment extraction against this shape would
    return "12308096-quality-assurance-manager", not the id "12308096" — this must also
    refuse, exactly like the fixture-derived URL above."""
    real_shaped_url = "https://jobs.smartrecruiters.com/acme/12308096-quality-assurance-manager"
    with pytest.raises(UnresolvablePostingURL):
        parse_posting_target(real_shaped_url)


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


@pytest.mark.parametrize(
    "board_root",
    ["boards.greenhouse.io/acme", "jobs.lever.co/acme", "apply.workable.com/acme"],
)
def test_a_scheme_less_board_root_refuses_too(board_root: str) -> None:
    """parse_board_target accepts scheme-less input by prefixing `https://`, so these ARE
    recognized board targets. _path_segments must normalize the same way — otherwise
    urlparse reads the hostname as the first path segment and the board root parses as a
    posting whose reference is the slug. The scheme-ful test above cannot catch that."""
    with pytest.raises(UnresolvablePostingURL):
        parse_posting_target(board_root)


@pytest.mark.parametrize(
    "chrome_url",
    [
        # Each is the sibling field of the canonical URL in that provider's own pinned
        # fixture: lever `applyUrl`, ashby `applyUrl`, workable `application_url`.
        "https://jobs.lever.co/acme/a1000000-0000-4000-8000-000000000001/apply",
        "https://jobs.ashbyhq.com/acme/ashby-0001/application",
        "https://apply.workable.com/acme/j/AAAA111111/apply",
        "https://apply.workable.com/acme/j/AAAA111111/apply/",
        "https://boards.greenhouse.io/acme/jobs/6000001/apply",
    ],
)
def test_a_trailing_chrome_segment_refuses_rather_than_becoming_the_posting_ref(
    chrome_url: str,
) -> None:
    """`/apply` and `/application` are the providers' canonical APPLICATION URLs, and
    aggregators deep-link to them. Read as a posting reference they are CONSTANT per
    provider, so two postings at one employer would collide on
    UNIQUE(company_id, provider_posting_id) — the second applied as a revision of the
    first, one real body overwritten, and closed after two misses because no `complete`
    board scan ever lists `apply`."""
    with pytest.raises(UnresolvablePostingURL):
        parse_posting_target(chrome_url)


def test_a_path_shorter_than_its_providers_shape_refuses() -> None:
    """Greenhouse is `{slug}/jobs/{id}`, so a two-segment path is not a posting URL even
    though it is not a bare board root either. The rule is an exact shape, not a minimum
    length — `boards.greenhouse.io/embed/job_app` would otherwise yield `job_app`."""
    with pytest.raises(UnresolvablePostingURL):
        parse_posting_target("https://boards.greenhouse.io/embed/job_app")


def test_unrecognized_url_raises_unknown_board_url_not_unresolvable() -> None:
    # Not a recognized board target at all: board_urls' own error must propagate
    # unchanged, distinct from our UnresolvablePostingURL.
    with pytest.raises(UnknownBoardURL):
        parse_posting_target("https://example.com/careers/123")


def test_posting_target_is_frozen() -> None:
    target = PostingTarget(provider="greenhouse", slug="acme", posting_ref="1")
    with pytest.raises(AttributeError):
        target.slug = "other"  # type: ignore[misc]
