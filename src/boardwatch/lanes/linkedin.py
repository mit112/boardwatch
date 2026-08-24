"""Lane 2: LinkedIn guest search (contract transcribed from D-290, 2026-08-24).

Contract: `docs/superpowers/research/2026-08-24-linkedin-lane-contract.md`. Two request shapes, and
no others:

    GET .../jobs-guest/jobs/api/seeMoreJobPostings/search?f_TPR=r86400  -- an HTML card list
    GET .../jobs-guest/jobs/api/jobPosting/{id}                         -- one body, one request

No key, no cookie, no TLS bypass, no app impersonation -- the search answers 200 with no User-Agent
at all, so there is nothing to spoof (D-290). That is why this lane can exist where Indeed could
not: Indeed's free body needed an iOS-app key with certificate verification off; this needs none.

**Permission is a separate axis and it is refused.** `robots.txt` disallows `/jobs-guest/` in all
77 agent groups and names `ClaudeBot` / `anthropic-ai` / `Claude-User` by name; User Agreement §8.2
forbids scripted scraping; the repo is public. Mit ruled BUILD with all of that in front of him
(D-290) -- an owner's call about the owner's own risk, recorded, not re-litigated. The lane ships
OFF by default (`lanes_enabled` is empty) and is not armed.

THE IDENTITY IS THE SLUG, AND THAT IS THE ONE STRUCTURAL DIFFERENCE FROM hiring.cafe. LinkedIn
exposes NO external apply URL (`externalApply` = 0), so a card carries no employer/ATS link to
dereference -- there is nothing for `parse_posting_target` to converge onto. Every posting is keyed
under `(provider="linkedin", slug=<company_slug>)`, where the slug is the `/company/{slug}` segment
on the card, a stable key (D-290: 0 opaque URNs). Cross-source convergence with an ATS copy of the
same role happens downstream through the P6 identity quad (company+title+location+body), never here
through a link -- exactly D-290's constraint.

THE ID IS THE URN, NOT THE URL. The job id is read from `data-entity-urn="urn:li:jobPosting:{id}"`.
The job-view URL's trailing number is NOT a reliable id and is never parsed for one -- see the
`URN_URL_MISMATCH_CARD` trap in `tests/unit/linkedin_shape.py`.

PAGING AND QUERY ARE DELIBERATELY ABSENT. The client makes ONE search GET with `f_TPR=r86400` and
no keywords or location facet. Paging (`start`) is implied by D-290's cost model but was not pinned
as a request contract, so inventing it is the defect `lanes/dereference.py` refuses SmartRecruiters;
and baking a role query in would make the lane Mit-specific and break multi-tenancy -- the hard US
gate and the role gate run downstream. Both are contract §4/§5 and both are clean later extensions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

from selectolax.parser import HTMLParser, Node

from boardwatch.core.models import RawPosting
from boardwatch.core.politeness import Fetcher, FetchFailure
from boardwatch.lanes.base import CompanyAdmission, LaneCompanySnapshot, LaneResult, lane_snapshot
from boardwatch.lanes.outcomes import AcquisitionOutcome, AcquisitionTally
from boardwatch.lanes.quality import assess_body

LANE_NAME = "linkedin"

# The provider every LinkedIn posting is keyed under. There is no ATS to converge onto through a
# link (contract §2: no external apply URL), so unlike hiring.cafe this never resolves to a
# six-provider board -- convergence is the P6 identity quad's job, downstream.
LANE_PROVIDER = "linkedin"

# Contract §1: the guest search, last-24h filtered. `f_TPR=r86400` is the one filter parameter the
# probe evidenced; `f_WT=2` (remote) returned a byte-identical id set to unfiltered and is not sent.
SEARCH_URL = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?f_TPR=r86400"
)
_JOB_POSTING_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/"

# The ceiling on body GETs per run. A hard cap, not a pacing knob: one search returns ~10 cards and
# the runner's company cap bounds companies, not postings.
DEFAULT_POSTING_BUDGET = 60


class SearchPageError(ValueError):
    """The search response carried no card nodes at all.

    A structural failure -- the fragment moved, or a challenge/error page answered in its place --
    that the runner must see, never a benign zero. Distinct from `FetchFailure` (transport/status).
    Both propagate: a lane is additive breadth, so the runner catches and records rather than the
    lane returning an empty result that reads like a quiet day. The zero-genuine-results shape was
    not pinned by the probe, so this errs LOUD by design (contract §4).
    """


class UnparseableCard(ValueError):
    """A card missing an id, a title, or a company slug -- none of which can be recovered.

    Typed at the raise site rather than signalled by a None return, so the one caller that tolerates
    it -- the grouping pass, which counts it `not_attemptable` and moves on -- says so explicitly.
    """


@dataclass(frozen=True)
class SearchCard:
    """One search-result card, in the fields D-290 recorded as 100/100 complete."""

    job_id: str
    title: str
    company_name: str
    company_slug: str
    location: str
    posted_date: str
    url: str


def card_nodes(page_html: str) -> list[Node]:
    """The `<li>` card units in a guest search fragment.

    `<li>` and not `div.base-card[data-entity-urn]`, deliberately: a card whose id is missing is
    still a card that was SEEN, and must be counted `not_attemptable` rather than vanishing from
    every tally. Selecting on the id would make a missing id invisible.
    """
    nodes = HTMLParser(page_html).css("li")
    if not nodes:
        raise SearchPageError("no <li> card nodes in the search fragment")
    return nodes


def parse_card(node: Node) -> SearchCard:
    """Pull the recorded fields out of one card node.

    Raises `UnparseableCard` when the id, title or company slug is absent -- the three fields a
    posting cannot be keyed or shown without. Location and date are allowed to be blank; a posting
    with no location is still rankable (it fails OPEN through the hard US gate, same as any
    unclassifiable location), and a missing date is not fatal.
    """
    job_id = _urn_job_id(node)
    title = _text(node.css_first("h3.base-search-card__title"))
    anchor = node.css_first("h4.base-search-card__subtitle a")
    company_name = _text(anchor)
    company_slug = _company_slug(anchor.attributes.get("href") if anchor else None)
    if not (job_id and title and company_slug):
        raise UnparseableCard(
            f"card missing id/title/company slug: id={job_id!r} title={title!r} "
            f"slug={company_slug!r}"
        )
    link = node.css_first("a.base-card__full-link")
    return SearchCard(
        job_id=job_id,
        title=title,
        company_name=company_name,
        company_slug=company_slug,
        location=_text(node.css_first("span.job-search-card__location")),
        posted_date=_time_attr(node.css_first("time")),
        url=(link.attributes.get("href") or "").strip() if link else "",
    )


def job_posting_url(job_id: str) -> str:
    return f"{_JOB_POSTING_URL}{job_id}"


class LinkedInLane:
    name = LANE_NAME

    def __init__(self, posting_budget: int = DEFAULT_POSTING_BUDGET) -> None:
        self._posting_budget = posting_budget

    def collect(self, fetcher: Fetcher, admits: CompanyAdmission) -> LaneResult:
        """One search GET, then one body GET per posting at an admitted company.

        `admits` is asked once per distinct `(linkedin, slug)`, in first-seen order, BEFORE any body
        is fetched -- the protocol's contract, and the only ordering under which the per-run company
        cap saves requests instead of discarding paid-for ones.
        """
        result = fetcher.get(SEARCH_URL)
        nodes = card_nodes(result.content.decode("utf-8", "replace"))

        tally = AcquisitionTally()
        by_company = _group_by_company(nodes, tally)
        snapshots: list[LaneCompanySnapshot] = []
        remaining = self._posting_budget
        for slug, cards in by_company.items():
            if not admits(LANE_PROVIDER, slug):
                # Nothing tallied for a refused company: no request was attempted, and an outcome
                # here would inflate `attempted` with non-attempts. Refusals are reported by name
                # through `admission.CompanyBudget.refused`.
                continue
            postings: list[RawPosting] = []
            for card in cards:
                if remaining <= 0:
                    # Seen, not requested. `not_attemptable` is the closed catalog's only member
                    # meaning that; a silent drop is what the catalog exists to prevent.
                    tally.record("not_attemptable")
                    continue
                remaining -= 1
                posting = self._fetch_posting(fetcher, card, tally)
                if posting is not None:
                    postings.append(posting)
            if postings:
                # A company whose every body was refused yields no snapshot: an empty one would
                # still write a `board_scans` row and oblige a company row for zero postings.
                snapshots.append(
                    LaneCompanySnapshot(
                        provider=LANE_PROVIDER,
                        slug=slug,
                        name=cards[0].company_name or slug,
                        snapshot=lane_snapshot(postings, SEARCH_URL),
                    )
                )
        return LaneResult(snapshots=tuple(snapshots), tally=tally)

    def _fetch_posting(
        self, fetcher: Fetcher, card: SearchCard, tally: AcquisitionTally
    ) -> RawPosting | None:
        try:
            result = fetcher.get(job_posting_url(card.job_id))
        except FetchFailure as exc:
            tally.record(_failure_outcome(exc))
            return None
        body_text, rejection = assess_body(_description(result.content), title=card.title)
        if rejection is not None:
            tally.record(rejection.outcome)
            return None
        tally.record("body_fetched")
        return _raw_posting(card, body_text=body_text)


def _group_by_company(
    nodes: list[Node], tally: AcquisitionTally
) -> dict[str, list[SearchCard]]:
    """Cards bucketed by company slug, first-seen order preserved.

    Grouping by slug rather than display name is the point the `NAME_COLLISION_CARDS` trap makes: a
    name-keyed group applies two employers' postings against one `company_id`. An unparseable card,
    or a second card resolving to a posting already taken this run, is counted `not_attemptable` and
    dropped here rather than raised -- one malformed row must not cost the others, and the duplicate
    drop is not tidiness: without it the run aborts. `apply.py` snapshots `existing` once before its
    loop, so two rows with one `provider_posting_id` both take the INSERT branch and the second
    violates UNIQUE(company_id, provider_posting_id) inside `apply_board`'s single transaction,
    rolling the whole board back and taking every later company's results with it. An aggregator MAY
    serve one posting twice; every ATS provider enumerates a board once and may assume distinct ids.
    """
    grouped: dict[str, list[SearchCard]] = {}
    seen: set[tuple[str, str]] = set()
    for node in nodes:
        try:
            card = parse_card(node)
        except UnparseableCard:
            tally.record("not_attemptable")
            continue
        key = (card.company_slug, card.job_id)
        if key in seen:
            tally.record("not_attemptable")
            continue
        seen.add(key)
        grouped.setdefault(card.company_slug, []).append(card)
    return grouped


def _raw_posting(card: SearchCard, *, body_text: str) -> RawPosting:
    return RawPosting(
        provider_posting_id=card.job_id,
        title=card.title,
        # The LinkedIn job-view URL -- the only URL a card exposes. There is no employer apply URL.
        url=card.url,
        locations=[card.location] if card.location else [],
        # `remote_policy` stays `unknown`: `f_WT` is silently ignored, so no reliable remote signal
        # is available and unknown is the honest default.
        posted_at=_date_to_naive_utc(card.posted_date),
        body_text=body_text,
        raw_json={"card": asdict(card)},
    )


def _description(content: bytes) -> str:
    """The `.show-more-less-html__markup` inner HTML -- the body, the field the search omits.

    An absent markup div returns "" rather than raising: `assess_body` then reports
    `extracted_empty`, the catalog's name for "a response arrived and extraction produced nothing".
    """
    node = HTMLParser(content.decode("utf-8", "replace")).css_first(
        "div.show-more-less-html__markup"
    )
    return node.html or "" if node is not None else ""


def _failure_outcome(exc: FetchFailure) -> AcquisitionOutcome:
    """Status -> outcome. A transport failure has no status and is `fetch_unavailable`.

    Kept apart because they mean different things to a reader: 403 is the host refusing us, 404 is a
    posting gone, a timeout is neither. Folding them is how the prior art hid an eleven-day outage.
    """
    if exc.status_code in (401, 403):
        return "fetch_refused"
    if exc.status_code in (404, 410):
        return "fetch_gone"
    return "fetch_unavailable"


def _urn_job_id(node: Node) -> str:
    """The posting id from `data-entity-urn="urn:li:jobPosting:{id}"`, never from the URL tail."""
    holder = node.css_first("[data-entity-urn]")
    urn = (holder.attributes.get("data-entity-urn") or "") if holder else ""
    return urn.rsplit(":", 1)[-1].strip() if "urn:li:jobPosting:" in urn else ""


def _company_slug(href: str | None) -> str:
    """The `{slug}` in `/company/{slug}`, stripped of query and trailing slash."""
    if not href:
        return ""
    parts = [segment for segment in urlsplit(href).path.split("/") if segment]
    if "company" in parts:
        index = parts.index("company")
        if index + 1 < len(parts):
            return parts[index + 1]
    return ""


def _time_attr(node: Node | None) -> str:
    return (node.attributes.get("datetime") or "").strip() if node is not None else ""


def _text(node: Node | None) -> str:
    return node.text(strip=True) if node is not None else ""


def _date_to_naive_utc(value: str) -> datetime | None:
    """The card's `datetime` is date-only ("2026-08-23"); interpret it as UTC midnight, naive.

    Naive UTC matches every provider's `posted_at` (`core.clock.to_naive_utc`); a tz-aware value
    here would compare unequal against the store's naive column.
    """
    if not value.strip():
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").replace(tzinfo=UTC).replace(tzinfo=None)
    except ValueError:
        return None
