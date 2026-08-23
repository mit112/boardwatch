"""Lane 1: hiring.cafe (contract pinned live, 2026-08-23).

Every request shape here is one this repo has actually made. Two of them, and no others:

    GET https://hiringcafe.com/                              -- search, server-rendered
    GET https://hiringcafe.com/api/job-description?id={id}   -- one body, one request

No key, no cookie, no TLS bypass, no app impersonation. That last clause is why this lane
exists at all: Indeed's free body is reachable only behind a key lifted from its iOS app with
certificate verification switched off, so Indeed is parked and hiring.cafe took lane 1.

ONE GET OF `/`, AND PAGING IS DELIBERATELY ABSENT. The response records `ssrPage`,
`ssrPageSize` and `ssrIsLastPage`, so a second page plainly exists; the request parameter that
turns one does NOT appear anywhere the probe reached. Inventing it would fabricate a request
contract, which is the exact defect `lanes/dereference.py` refuses SmartRecruiters and Workday
for. One response carries ~159 hits — four `ssrPageSize`s' worth — so the cost of refusing is
small and the cost of guessing is a client that silently fetches the wrong thing. Paging needs
its own probe.

`objectID` IS AN OPAQUE KEY. It looks like `{source}___{board_token}___{id}` and is exactly
that for 128 of 160 sampled hits, which is what makes it dangerous: a round-trip test over a
typical sample passes. Splitting on `___` mis-attributes 36 of 160 (22.5%) in three ways --
`taleo_careersection` separates with single underscores, `fountain`'s `board_token` itself
contains `___`, and `saashr` differs in case from its own `board_token`. `source` and
`board_token` are explicit top-level keys and non-blank on all 160. This module reads those and
uses `objectID` for nothing but the JD endpoint's `id` parameter.

WHAT THE LANE TRUSTS FROM THE PAYLOAD, AND WHAT IT DOES NOT. `v5_processed_job_data` is
untrusted for eligibility (D-278) and stays that way: the eligibility engine is body-only, so
it structurally cannot read these fields. The location TEXT lives nowhere else in the payload
(`_geoloc` is coordinates, and `rank/location_gate` matches text), so `workplace_*` populates
`RawPosting.locations` as provider-asserted metadata at exactly the trust level greenhouse's
`location.name` already has -- and never as evidence for a verdict.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from selectolax.parser import HTMLParser

from boardwatch.core.board_urls import UnknownBoardURL
from boardwatch.core.models import RawPosting
from boardwatch.core.politeness import Fetcher, FetchFailure
from boardwatch.lanes.base import CompanyAdmission, LaneCompanySnapshot, LaneResult, lane_snapshot
from boardwatch.lanes.dereference import UnresolvablePostingURL, parse_posting_target
from boardwatch.lanes.outcomes import AcquisitionOutcome, AcquisitionTally
from boardwatch.lanes.quality import assess_body

LANE_NAME = "hiringcafe"

# The provider a hit is keyed under when its `apply_url` names no board this repo can parse --
# which is 95% of them, and is the point of the lane.
LANE_PROVIDER = "hiringcafe"

# `hiring.cafe` 308-redirects to `hiringcafe.com`; the canonical host moved since the design
# was written. Recorded so a future reader does not "correct" it back.
SEARCH_URL = "https://hiringcafe.com/"
_JOB_DESCRIPTION_URL = "https://hiringcafe.com/api/job-description?id="

# D8's ceiling on body GETs per lane per run. A hard cap rather than a pacing knob: the search
# page returns ~159 hits and the runner's company cap does not bound postings, only companies.
DEFAULT_POSTING_BUDGET = 60

class SearchPageError(ValueError):
    """The search page was served but carried no usable `ssrHits`.

    Distinct from `FetchFailure`, which the fetcher already raises for a transport or status
    failure. Both propagate: a lane is additive breadth, so the runner catches and records
    rather than the lane returning an empty result that reads like a quiet day.
    """


class UnidentifiableHit(ValueError):
    """A hit carrying no `(provider, slug, posting id)` this repo can key a company on.

    Typed at the raise site rather than signalled by a None return, so the one caller that
    can tolerate it -- the grouping pass, which counts it and moves on -- says so explicitly
    instead of every caller having to remember that None means "skip".
    """


@dataclass(frozen=True)
class HitIdentity:
    """The store identity one search hit resolves to (design D2)."""

    provider: str
    slug: str
    posting_id: str


def search_hits(page_html: str) -> list[dict[str, Any]]:
    """`props.pageProps.ssrHits` out of the `__NEXT_DATA__` script block.

    Parsed with selectolax rather than a regex over the 1.28 MB page: the JSON contains
    `</div>` inside string values, so a regex terminated on the wrong tag boundary.
    """
    node = HTMLParser(page_html).css_first("script#__NEXT_DATA__")
    if node is None:
        raise SearchPageError("no <script id='__NEXT_DATA__'> in the search page")
    try:
        payload = json.loads(node.text())
        hits = payload["props"]["pageProps"]["ssrHits"]
    except (ValueError, KeyError, TypeError) as exc:
        raise SearchPageError(f"unreadable __NEXT_DATA__: {exc}") from exc
    if not isinstance(hits, list):
        raise SearchPageError(f"ssrHits is {type(hits).__name__}, not a list")
    return [hit for hit in hits if isinstance(hit, dict)]


def hit_identity(hit: dict[str, Any]) -> HitIdentity:
    """(provider, slug, posting id) for one hit, D2's order.

    The `apply_url` attempt comes first and is the convergence case: when the employer's real
    URL is a greenhouse / lever / ashby / workable posting, the identity recovered from it is
    the SAME `(company_id, provider_posting_id)` a later board scan produces, so the
    aggregator's copy converges through `UNIQUE(company_id, provider_posting_id)` instead of
    duplicating. Both dereference failures are ordinary here -- 95% of hits sit on an ATS this
    repo has no adapter for, which is the reach the lane was built for, not an error.
    """
    apply_url = _text(hit.get("apply_url"))
    if apply_url:
        try:
            target = parse_posting_target(apply_url)
        except (UnknownBoardURL, UnresolvablePostingURL):
            pass
        else:
            return HitIdentity(target.provider, target.slug, target.posting_ref)
    source = _text(hit.get("source"))
    board_token = _text(hit.get("board_token"))
    object_id = _text(hit.get("objectID"))
    if not (source and board_token and object_id):
        raise UnidentifiableHit(
            "hit is missing source / board_token / objectID, all of which the contract "
            f"records as non-blank on every sampled hit: {object_id or hit.get('id')!r}"
        )
    return HitIdentity(LANE_PROVIDER, f"{source}:{board_token}", object_id)


def company_name(hit: dict[str, Any]) -> str:
    """`enriched_company_data.name` -- non-blank on 159/159 probed hits -- else `board_token`.

    NOTE for the caller that inserts the company row: `LaneCompanySnapshot` carries no name
    field, so this is the only route from a `LaneResult` back to a display name, via each
    posting's `raw_json["hit"]`.
    """
    enriched = hit.get("enriched_company_data")
    name = _text(enriched.get("name")) if isinstance(enriched, dict) else ""
    return name or _text(hit.get("board_token"))


def job_description_url(object_id: str) -> str:
    return f"{_JOB_DESCRIPTION_URL}{quote(object_id, safe='')}"


class HiringCafeLane:
    name = LANE_NAME

    def __init__(self, posting_budget: int = DEFAULT_POSTING_BUDGET) -> None:
        self._posting_budget = posting_budget

    def collect(self, fetcher: Fetcher, admits: CompanyAdmission) -> LaneResult:
        """One search GET, then one body GET per posting at an admitted company.

        `admits` is asked once per distinct `(provider, slug)`, in first-seen order, BEFORE any
        body is fetched -- the protocol's contract, and the only ordering under which the
        per-run company cap saves requests instead of discarding paid-for ones.
        """
        result = fetcher.get(SEARCH_URL)
        hits = search_hits(result.content.decode("utf-8", "replace"))

        tally = AcquisitionTally()
        by_company = _group_by_company(hits, tally)
        snapshots: list[LaneCompanySnapshot] = []
        remaining = self._posting_budget
        for (provider, slug), company_hits in by_company.items():
            if not admits(provider, slug):
                # Nothing is tallied for a refused company: no request was attempted, and an
                # outcome recorded here would inflate `attempted` with non-attempts. Refusals
                # are reported by name through `admission.CompanyBudget.refused`, which is the
                # channel designed for them.
                continue
            postings: list[RawPosting] = []
            for identity, hit in company_hits:
                if remaining <= 0:
                    # Seen, not requested. The catalog is closed, and `not_attemptable` is its
                    # only member meaning that -- its stated reason (no resolvable URL) is
                    # narrower than this condition, but counting is the invariant and a silent
                    # drop is what the catalog exists to prevent.
                    tally.record("not_attemptable")
                    continue
                remaining -= 1
                posting = self._fetch_posting(fetcher, identity, hit, tally)
                if posting is not None:
                    postings.append(posting)
            if postings:
                # A company whose every body was refused yields no snapshot: an empty one would
                # still write a `board_scans` row and oblige a company row for zero postings,
                # and the refusal is already counted in the tally.
                snapshots.append(
                    LaneCompanySnapshot(
                        provider=provider,
                        slug=slug,
                        # Taken from the first hit in the group. Every hit in it shares one
                        # `(source, board_token)`, so they describe one employer; the probe
                        # found `enriched_company_data.name` non-blank on 159 of 159 hits, and
                        # `company_name` falls back to `board_token` rather than to a blank.
                        name=company_name(company_hits[0][1]),
                        snapshot=lane_snapshot(postings, SEARCH_URL),
                    )
                )
        return LaneResult(snapshots=tuple(snapshots), tally=tally)

    def _fetch_posting(
        self,
        fetcher: Fetcher,
        identity: HitIdentity,
        hit: dict[str, Any],
        tally: AcquisitionTally,
    ) -> RawPosting | None:
        object_id = _text(hit.get("objectID"))
        try:
            result = fetcher.get(job_description_url(object_id))
        except FetchFailure as exc:
            tally.record(_failure_outcome(exc))
            return None
        title = _title(hit)
        body_text, rejection = assess_body(_description(result.content), title=title)
        if rejection is not None:
            tally.record(rejection.outcome)
            return None
        tally.record("body_fetched")
        return _raw_posting(identity, hit, title=title, body_text=body_text)


def _failure_outcome(exc: FetchFailure) -> AcquisitionOutcome:
    """Status -> outcome. A transport failure has no status and is `fetch_unavailable`.

    The three buckets are kept apart because they mean different things to a reader of the
    run: 403 is the host refusing us, 404 is a posting that has gone, and a timeout is neither.
    Folding them is precisely how the prior art hid an eleven-day outage.
    """
    if exc.status_code in (401, 403):
        return "fetch_refused"
    if exc.status_code in (404, 410):
        return "fetch_gone"
    return "fetch_unavailable"


def _description(content: bytes) -> str:
    """`job.job_information.description` -- the HTML body, the one field the search omits.

    An unreadable payload returns "" rather than raising: `assess_body` then reports
    `extracted_empty`, which is what the catalog means by "a response arrived and extraction
    produced nothing substantive". A second failure mode here would need a second outcome name
    and the catalog is closed.
    """
    try:
        payload = json.loads(content)
        description = payload["job"]["job_information"]["description"]
    except (ValueError, KeyError, TypeError):
        return ""
    return description if isinstance(description, str) else ""


def _group_by_company(
    hits: list[dict[str, Any]], tally: AcquisitionTally
) -> dict[tuple[str, str], list[tuple[HitIdentity, dict[str, Any]]]]:
    """Hits bucketed by `(provider, slug)`, first-seen order preserved.

    Grouping by identity rather than by `enriched_company_data.name` is the same point
    `LaneCompanySnapshot` makes in its own docstring: a name is not what `companies` is unique
    on, so a name-keyed group applies one employer's two boards against one `company_id`.

    A hit this repo cannot key, or cannot title, is counted `not_attemptable` and dropped here
    rather than raised: one malformed row must not cost the other 159, which is the
    per-posting isolation every provider's board parse already applies. Dropping it BEFORE the
    body GET is the point -- `smartrecruiters.parse_posting` refuses an empty title for the
    same reason, and a lane can refuse it a whole request earlier.
    """
    grouped: dict[tuple[str, str], list[tuple[HitIdentity, dict[str, Any]]]] = {}
    for hit in hits:
        try:
            identity = hit_identity(hit)
        except UnidentifiableHit:
            tally.record("not_attemptable")
            continue
        if not _title(hit):
            tally.record("not_attemptable")
            continue
        grouped.setdefault((identity.provider, identity.slug), []).append((identity, hit))
    return grouped


def _raw_posting(
    identity: HitIdentity, hit: dict[str, Any], *, title: str, body_text: str
) -> RawPosting:
    return RawPosting(
        provider_posting_id=identity.posting_id,
        title=title,
        # The employer's own URL, not a hiring.cafe permalink: it is what the user clicks, and
        # in the convergence case it is the same URL the ATS provider would have recorded.
        url=_text(hit.get("apply_url")),
        locations=_locations(hit),
        # `posted_at`/`updated_at`/`remote_policy` stay unset. No date field appears in the
        # recorded top-level key list, and `v5_processed_job_data.workplace_type` is recorded
        # as present but its value vocabulary is not -- mapping it would be a guess, and an
        # unknown remote policy is already the honest default.
        body_text=body_text,
        # The JD HTML is deliberately NOT duplicated in here: `body_text` already carries it,
        # and `raw_json` is persisted per posting version.
        raw_json={"hit": hit},
    )


def _title(hit: dict[str, Any]) -> str:
    info = hit.get("job_information")
    if not isinstance(info, dict):
        return ""
    return _text(info.get("title")) or _text(info.get("job_title_raw"))


def _locations(hit: dict[str, Any]) -> list[str]:
    """Location TEXT out of `v5_processed_job_data.workplace_*`, the only place it exists.

    `_geoloc` is `[{"lat": ..., "lon": ...}]` and is never read: `rank/location_gate` matches
    text, so a coordinate reaches it as an unrecognized segment and resolves `unknown`, which
    fails OPEN through the hard US gate. A silently useless location is worse than none.

    Each `workplace_*` value is accepted as either a string or a list of them. The probe
    recorded the key names, not their types, and the gate classifies per segment either way.
    """
    processed = hit.get("v5_processed_job_data")
    if not isinstance(processed, dict):
        return []
    formatted = _text(processed.get("formatted_workplace_location"))
    if formatted:
        return [formatted]
    segments: list[str] = []
    for key in ("workplace_cities", "workplace_states", "workplace_countries"):
        for value in _text_list(processed.get(key)):
            if value not in segments:
                segments.append(value)
    return segments


def _text(value: Any) -> str:
    return str(value).strip() if isinstance(value, str) else ""


def _text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    return []
