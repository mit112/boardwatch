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
    _POSTING_REF_PATTERNS,
    PostingTarget,
    UnresolvablePostingURL,
    parse_posting_target,
)
from boardwatch.providers import ashby, greenhouse, lever, workable, workday

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
_WORKDAY_REF = _POSTING_REF_PATTERNS["workday"]


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


def test_smartrecruiters_posting_url_resolves_to_the_id_not_the_whole_segment() -> None:
    """The evidence this module said it was waiting for now exists, so the refusal is lifted.

    It asked for "a live probe pinning at least one real `postingUrl`". What it got is stronger:
    **3,041 real SmartRecruiters URLs in the live store, on which the extracted reference equals
    the provider's own stored `provider_posting_id` 3,041 times out of 3,041**, plus 363 more from
    an independent second system. That is the convergence this dereference exists to create --
    a lane URL now mints exactly the identity a board scan already wrote.

    The naive hazard the old test pinned is still pinned, from the other side: the reference is
    the ID, never the whole `{id}-{title-slug}` segment.
    """
    target = parse_posting_target(
        "https://jobs.smartrecruiters.com/acme/12308096-quality-assurance-manager"
    )
    assert target.provider == "smartrecruiters"
    assert target.slug == "acme"
    assert target.posting_ref == "12308096"

    # The provider's own constructed-fallback shape -- a bare id -- resolves identically.
    bare = parse_posting_target("https://jobs.smartrecruiters.com/acme/744000122286883")
    assert bare.posting_ref == "744000122286883"


def test_a_smartrecruiters_uuid_reference_still_refuses() -> None:
    """The counter-example that makes the ANCHOR load-bearing rather than decorative.

    SmartRecruiters also issues UUID references -- measured in a second system's ledger:
    `jobs.smartrecruiters.com/servicenow/99c06c61-284f-4c2b-bd4d-1a7b53bf3fa4`. The rule this
    module previously recorded as its candidate future fix was a bare `^\\d+`, and against that
    URL it reads **"99"**: a two-character reference that would collide on
    `UNIQUE(company_id, provider_posting_id)` and overwrite a real body with a revision -- the
    exact defect class SmartRecruiters was refused for originally. Requiring the digit run to END
    the id refuses instead, and out-of-catalog stays a failure rather than a guess.
    """
    with pytest.raises(UnresolvablePostingURL):
        parse_posting_target(
            "https://jobs.smartrecruiters.com/servicenow/99c06c61-284f-4c2b-bd4d-1a7b53bf3fa4"
        )


def test_workday_round_trip() -> None:
    """The refusal is lifted for IDENTITY, and this pins the round trip the same way the
    four body-inlined providers are pinned: the fixture's own `externalUrl` back through
    `parse_posting_target`, asserted against the `provider_posting_id` the provider itself
    derived. The fixture carries the `en-US` locale form, which is one of the three real
    shapes and the reason the rule is positional rather than a fixed segment run.

    Synthetic-fixture caveat, same as the other four: this proves the mapping is internally
    consistent. The evidence that it holds against REAL URLs is measured elsewhere -- 93,044
    provider-supplied `externalUrl`s in the live store matching the stored
    `provider_posting_id` 93,044 of 93,044, plus an independent 4,407 from job-apps' ledger
    across 606 hosts. See the module docstring.
    """
    listed = _fixture_json("workday", "list_normal.json")["jobPostings"][0]
    detail = _fixture_json("workday", "detail_normal.json")
    posting = workday.parse_posting(
        "acme.wd5.myworkdayjobs.com", "AcmeCareers", listed, detail, None
    )
    target = parse_posting_target(posting.url)
    assert target.provider == "workday"
    assert target.slug == "acme.wd5.myworkdayjobs.com/acme/AcmeCareers"
    assert target.posting_ref == posting.provider_posting_id
    # Pinned as a LITERAL as well: asserting only against the provider's own output would
    # pass just as happily if both sides drifted to the whole externalPath together.
    assert target.posting_ref == "JR1000001-1"


def test_a_workday_site_named_jobs_refuses_rather_than_reading_the_location() -> None:
    """The counter-example that makes the site guard load-bearing rather than decorative.

    `workday.slug_from_path` takes the first path segment not in `_CHROME_SEGMENTS`, and
    `jobs` is in that set -- so for a tenant whose career site is literally named `Jobs`,
    it skips the site and reads the LOCATION as the site. Measured in the live store:
    `redhat.wd5.myworkdayjobs.com/Jobs/job/Canberra/...` derives site `Canberra`, and
    `redhat/jobs` + `paypal/jobs` are real watched rows. Without this guard the URL would
    resolve to a company row for a board that does not exist -- a different fiction per
    location -- and mint a real requisition id against it.

    157 URLs in the live store and 38 in an independent ledger take this branch.
    """
    with pytest.raises(UnresolvablePostingURL, match="is not the segment before"):
        parse_posting_target(
            "https://redhat.wd5.myworkdayjobs.com/Jobs/job/Canberra/Senior-Consultant_R-040324-1"
        )


def test_a_workday_reference_with_no_digit_bearing_token_refuses() -> None:
    """A board ROOT, or a site slug that merely contains an underscore, is not a posting.

    Measured in the independent ledger: `modernatx.wd1.myworkdayjobs.com/M_tx` would read
    `tx` as a reference -- two characters, shared by every posting at that employer, and a
    collision on `UNIQUE(company_id, provider_posting_id)` that overwrites a real body. The
    digit requirement is what refuses it. This is the Workday analogue of the SmartRecruiters
    UUID case above.
    """
    # This URL REACHES the workday branch and its last segment DOES carry an underscore, so
    # the only thing refusing it is the digit requirement. The earlier version of this test
    # used `M_tx` (refused for having no `job` segment) and `.../Engineer` (refused for having
    # no underscore) -- both would have passed against the unsafe digitless `_([^_]+)$`.
    with pytest.raises(UnresolvablePostingURL, match="not readable"):
        parse_posting_target(
            "https://acme.wd5.myworkdayjobs.com/AcmeCareers/job/Remote/Engineer_Staff"
        )
    # And the board-root form, which must refuse before the pattern is ever consulted.
    with pytest.raises(UnresolvablePostingURL):
        parse_posting_target("https://modernatx.wd1.myworkdayjobs.com/M_tx")


def test_the_workday_reference_pattern_matches_the_providers_own_id_rule() -> None:
    """Convergence is `UNIQUE(company_id, provider_posting_id)`, and `workday._posting_id`
    writes the stored side while this module writes the lane side. They are two separate
    implementations on purpose -- importing the provider would pull `core/politeness` into a
    module that promises no network code -- so the equivalence has to be PINNED or they drift
    apart silently and every Workday lane find stops converging.

    The segments below are the real shapes measured across both populations: a `JR`/`R`/`REQ`
    requisition, a `-1` revision suffix, an underscore inside the requisition itself, and the
    two that must refuse.
    """
    for segment in (
        "Senior-Platform-Engineer_JR1000001-1",
        "Software-Development-Engineer_R170921",
        "Commercial-Counsel_REQ_100000229-1",
        "Actuarial-Analyst-I_R7943",
        "Cyber-Security-Systems-Engineer_REQ_0000077635-2",
    ):
        matched = _WORKDAY_REF.search(segment)
        assert matched is not None, segment
        assert matched.group(1) == workday._posting_id(segment), segment

    for refuses in ("M_tx", "External_Career", "CMU", "apply", "application"):
        assert _WORKDAY_REF.search(refuses) is None, refuses
        # the provider's rule agrees: no digit-bearing token, so it falls back to the whole
        # string, which is exactly the class this module must refuse rather than adopt.
        assert workday._posting_id(refuses) == refuses, refuses


def test_a_workday_path_longer_than_the_measured_shape_refuses() -> None:
    """The segment bound, pinned separately because the reference pattern cannot stand in
    for it. An unbounded tail is the trailing-chrome defect this module refuses lever,
    ashby and workable for: a constant final segment read as a reference collides on
    `UNIQUE(company_id, provider_posting_id)` and overwrites a real body.

    The pattern alone does NOT catch this. Here the extra segment sits BEFORE the
    reference, so the last segment still matches and the URL resolves unless the distance
    from `job` to the end is bounded. Measured over 97,451 real URLs, that distance is
    always 1 or 2; anything else is a shape this repo has not seen and must refuse.
    """
    with pytest.raises(UnresolvablePostingURL, match="is not that shape"):
        parse_posting_target(
            "https://acme.wd5.myworkdayjobs.com/AcmeCareers/job/Remote-USA/Extra"
            "/Senior-Platform-Engineer_JR1000001-1"
        )
    # And the trailing-chrome direction, for completeness.
    with pytest.raises(UnresolvablePostingURL):
        parse_posting_target(
            "https://acme.wd5.myworkdayjobs.com/AcmeCareers/job/Remote-USA"
            "/Senior-Platform-Engineer_JR1000001-1/apply"
        )


def test_a_second_reference_looking_segment_makes_the_workday_url_ambiguous() -> None:
    """Two segments after `job` is `{location}/{ref}` in every measured URL -- but the shape
    alone cannot tell that from `{ref}/{trailing_chrome}`, and reading the last segment of
    `.../job/Engineer_REQ999/apply_REQ123` yields REQ123 while the posting is REQ999. Ingesting
    that overwrites a real REQ123 as a revision, which is the defect class this module exists
    to prevent and the reason lever, ashby and workable refuse a trailing chrome segment.

    The length bound does NOT catch this: two post-`job` segments is a legal shape. Only
    requiring the reference to be unambiguous does.

    Measured cost: 2 of 91,871 real URLs, both Lowe's, whose location segment ends in a
    digit-bearing token. Given up deliberately -- identity minting fails safe.
    """
    with pytest.raises(UnresolvablePostingURL, match="ambiguous"):
        parse_posting_target(
            "https://acme.wd5.myworkdayjobs.com/AcmeCareers/job/Engineer_REQ999/apply_REQ123"
        )


def test_an_unmeasured_segment_before_the_workday_career_site_refuses() -> None:
    """The prefix is closed, not only the suffix. `slug_from_path` skips ANY number of chrome
    or locale-shaped segments, so without this rule `login/12-34/AcmeCareers/job/...` resolves
    as though it were a canonical URL -- which would contradict the closed-catalog invariant
    this module states about itself.

    The two forms that DO occur are admitted, and pinned here so the rule is not tightened
    into a regression: a locale, and a repeat of the career site itself (measured:
    `SemtechCareers/SemtechCareers`, `en-US/wellsfargojobs/wellsfargojobs`).
    """
    with pytest.raises(UnresolvablePostingURL, match="only a locale or a repeated career site"):
        parse_posting_target(
            "https://acme.wd5.myworkdayjobs.com/login/12-34/AcmeCareers/job/Austin/Eng_REQ999"
        )

    repeated = parse_posting_target(
        "https://semtech.wd1.myworkdayjobs.com/SemtechCareers/SemtechCareers"
        "/job/CAN---Richmond-BC/Product-Manager_REQ3"
    )
    assert repeated.slug == "semtech.wd1.myworkdayjobs.com/semtech/SemtechCareers"
    assert repeated.posting_ref == "REQ3"

    localed = parse_posting_target(
        "https://wf.wd1.myworkdayjobs.com/en-US/wellsfargojobs/wellsfargojobs"
        "/job/ALBUQUERQUE-NM/Business-Banker_R-568"
    )
    assert localed.slug == "wf.wd1.myworkdayjobs.com/wf/wellsfargojobs"
    assert localed.posting_ref == "R-568"


def test_a_workday_url_on_the_myworkdaysite_host_still_raises_unknown_board_url() -> None:
    """Not an oversight, and adding the host suffix would NOT fix it. The same tenant is
    stored under the other host -- `chewy.wd5.myworkdayjobs.com/chewy/External` -- so a slug
    parsed out of `wd5.myworkdaysite.com/recruiting/chewy/External/...` would still not equal
    it, and would mint a second company row rather than converge. 5,472 live-store URLs.
    """
    with pytest.raises(UnknownBoardURL):
        parse_posting_target(
            "https://wd5.myworkdaysite.com/recruiting/chewy/External/job/Plantation-FL/Vet_8271"
        )


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
