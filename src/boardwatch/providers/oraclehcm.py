"""Oracle Recruiting Cloud (HCM) career sites (live-verified 2026-09-06).

A board is a {host, siteNumber} PAIR, carried as the composite slug "{host}/{site}" —
`eeho.fa.us2.oraclecloud.com/CX_1`. Hosts are unbounded
({tenant}.fa.{region}.oraclecloud.com, fa-{x}-saasfaprod1.fa.ocs.oraclecloud.com), so
identity is the `.oraclecloud.com` SUFFIX and there are no exact paste hosts. The pair
never leaves this module.

Two public endpoints, both plain GETs:

  LIST   /hcmRestApi/resources/latest/recruitingCEJobRequisitions
         ?onlyData=true&expand=requisitionList.secondaryLocations
         &finder=findReqs;siteNumber={site},limit=200,offset={n},sortBy=POSTING_DATES_DESC
  DETAIL /hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails
         ?expand=all&onlyData=true&finder=ById;Id={id},siteNumber={site}

The list carries no body text worth having (`ShortDescriptionStr` is a teaser), so each
posting needs the second request — the SmartRecruiters/Workday shape. Detail fetches are
therefore bounded by `detail_budget` and SKIP ids already in `known_posting_ids`, which
makes `snapshot.postings` the newly-fetched subset while `snapshot.listed_ids` carries the
FULL live inventory. Without that split `apply_board._process_missing` would close every
known-but-unrefreshed posting. Bodies fill in incrementally across scans, as they do for
both sibling providers. Salary is never mined (D19).

FIVE MEASURED PROPERTIES DRIVE THIS DESIGN. Each has a regression test; none should be
"simplified" away.

1. `expand` IS LOAD-BEARING, NOT DECORATION. Without
   `expand=requisitionList.secondaryLocations` the list answers HTTP 200 with a populated
   `TotalJobsCount` and NO `requisitionList` KEY AT ALL — measured on eeho/CX_1: total 2273,
   zero rows. A pager that treated `expand` as an optimisation would report a 2,273-posting
   board it enumerated 0 of, on a 200, forever. It is pinned into every page URL.

2. `limit` MAX IS 200, SILENTLY CLAMPED, AND THE ECHO LIES. limit=201, 300 and 500 each
   return exactly 200 rows while `items[0].Limit` echoes back the number ASKED FOR. So the
   response cannot be trusted to report its own page size, and termination is on a SHORT
   PAGE (the Workday rule), never on the echoed limit.

3. `TotalJobsCount` IS ONLY MEANINGFUL AT offset=0. An out-of-range offset answers 200 with
   `TotalJobsCount: 0` and no rows — measured at offset=99000 on a 2,273-posting board. Read
   at any other offset it would report a live board as empty, so it is captured once, on the
   first page, and never re-read.

4. AN UNKNOWN siteNumber SILENTLY SERVES THE HOST'S DEFAULT BOARD. This is strictly worse
   than SmartRecruiters' unknown-org case and is the reason `healthcheck` can never return
   DEAD. `siteNumber=CX_999` and `siteNumber=ZZnotasite` both returned eeho's CX_1 board —
   same `TotalJobsCount` of 2273, same first five ids — and echoed the BOGUS site back in
   `SiteNumber`, so even the echo cannot be used to detect the typo. On hdpc the same two
   bogus sites returned that host's CampusHiring board (1322, same ids). A mistyped site is
   therefore indistinguishable not merely from an empty board but from a REAL and DIFFERENT
   one, which no response field can catch. See `healthcheck`.

5. DETAIL HAS NO 404. An unknown or withdrawn requisition answers HTTP 200 with
   `items: []`, count 0 — measured with Id=99999999. That is read as "no longer listable",
   the same disposition SmartRecruiters gives `active: false`: the posting is dropped from
   `postings` AND from `listed_ids`, so `apply_board` closes it rather than holding it open
   forever against an id the board will never serve again.

BODY TEXT excludes `CorporateDescriptionStr` and `OrganizationDescriptionStr` for the reason
SmartRecruiters excludes `companyDescription`: both are identical boilerplate across a
tenant's whole board (measured — every eeho posting repeats the same corporate paragraph)
and would pollute `content_hash`, which is what detects a real revision. Only the three
`External*Str` sections are read, in a FIXED order, and they are HTML — `html_to_text` is on
this path.

`fetch_board` must never raise: every JSON level is validated as dict/list before use.

6. PAST 10,000 ROWS THE LIST ANSWERS EMPTY (T352). A board over that window is listed as two
   children instead, by the posting-date facet in the finder: `selectedPostingDatesFacet=30`
   (under 30 days) and `=31` (over). Measured 2026-11-24, the ids are the same on three tenants
   and the two children partition each board exactly: ejwl 9,214 + 3,724 = 12,938, jpmc
   3,420 + 3,403 = 6,823, eigx 331 + 4,250 = 4,581. Facet 7 ("under 7 days") is a SUBSET of 30,
   so it is never a child. The split board is `complete` only when the children's totals sum to
   the root's, each is within the window and listed its own total in distinct ids, and nothing
   failed; a child still over the window leaves the board `partial`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from functools import partial
from typing import Any
from urllib.parse import urlsplit

from boardwatch.core.clock import to_naive_utc
from boardwatch.core.html_text import html_to_text
from boardwatch.core.models import BoardRequest, BoardSnapshot, RawPosting, RemotePolicy
from boardwatch.core.politeness import Fetcher, FetchFailure
from boardwatch.providers.base import (
    BoardHealth,
    apply_listing_gate,
    detail_phase_stops,
    employer_label_from_host,
    head_shadow,
    health_from_failure,
)

_HOST_SUFFIX = ".oraclecloud.com"
# Server maximum. 201/300/500 all return exactly 200 rows while echoing the asked-for value
# back in `Limit`, so this is a real ceiling that the response will not confirm (property 2).
_PAGE_LIMIT = 200
# 60 pages x 200 = 12,000, well past the largest board measured (2,273). A backstop only:
# normal termination is a short page.
_MAX_PAGES = 60
# Property 6: the rows a query can page through, and the two posting-date facet values that
# partition a board (under 30 days, over 30 days). A split board may spend two full windows:
# each child's pages and the short page that ends it, plus the root's first page.
_RESULT_WINDOW = 10_000
_POSTING_DATE_PARTS = ("30", "31")
_SPLIT_MAX_PAGES = 2 * (_RESULT_WINDOW // _PAGE_LIMIT + 1) + 1
# The three external sections, in the order they are concatenated. Fixed, because
# content_hash is order-sensitive and a reordering would read as a revision on every posting.
_BODY_SECTIONS = (
    "ExternalDescriptionStr",
    "ExternalQualificationsStr",
    "ExternalResponsibilitiesStr",
)
# Anything that would make the composite slug reinterpretable as a URL with a different
# authority, path or query than the pair says (the Workday guard).
_HOST_FORBIDDEN = frozenset(":@?#\\%[]")
_SLUG_FORM = "expected host/site, e.g. acme.fa.us2.oraclecloud.com/CX_1"
# The fixed run of segments a public career-site URL puts before the locale and the site.
_UI_PREFIX = ("hcmui", "candidateexperience")
# The segment that introduces the site in a public career-site URL.
_SITES_SEGMENT = "sites"
# WorkplaceTypeCode is a CLOSED, locale-independent catalog and is preferred over the
# `WorkplaceType` label it accompanies, which is localized prose ("Hybrid", "On-site").
# Measured across one 100-posting board: 93 ORA_HYBRID, 4 ORA_ON_SITE, 1 ORA_REMOTE, 2 null.
_WORKPLACE_CODES: dict[str, RemotePolicy] = {
    "ORA_REMOTE": "remote",
    "ORA_HYBRID": "hybrid",
    "ORA_ON_SITE": "onsite",
}


def split_slug(slug: str) -> tuple[str, str]:
    """(host, site) from the composite slug, canonicalized: host lowercased, SITE CASE
    PRESERVED.

    Case is preserved on the same reason `workday.split_slug` records: nothing requires
    lowering it. Identity does not depend on it, because `store/queries.py:stored_slug` folds
    case and is what stops one board being stored twice. Live sites are spelled `CX_1`, `CX`
    and `CampusHiring`, and preserving the provider's own spelling is the cheaper default,
    NOT a correctness requirement.

    Raises ValueError on anything that is not a valid pair; `board_urls._normalize_slug`
    converts that to UnknownBoardURL so the CLI does not traceback.
    """
    parts = slug.strip().split("/")
    if len(parts) != 2 or not all(p.strip() for p in parts):
        raise ValueError(_SLUG_FORM)
    host = _validated_host(parts[0].strip().lower())
    site = parts[1].strip()
    if any(c.isspace() or ord(c) < 32 for c in site):
        raise ValueError(f"site {site!r} contains whitespace or a control character")
    # The site lands inside the `finder` query parameter, whose own grammar is
    # `name;key=value,key=value`. A `,` or `;` there would silently add or truncate a finder
    # argument rather than 400, so the slug must not be able to carry one.
    if any(c in _HOST_FORBIDDEN or c in ",;/" for c in site):
        raise ValueError(f"site {site!r} contains a forbidden character")
    return host, site


def _validated_host(host: str) -> str:
    if any(c.isspace() or ord(c) < 32 for c in host):
        raise ValueError(f"host {host!r} contains whitespace or a control character")
    if any(c in _HOST_FORBIDDEN for c in host):
        raise ValueError(f"host {host!r} contains a forbidden character")
    # endswith on a LEADING-DOT suffix is the label boundary: notoraclecloud.com must not
    # match, and the length test requires at least one label before the suffix.
    if not host.endswith(_HOST_SUFFIX) or len(host) <= len(_HOST_SUFFIX):
        raise ValueError(f"host {host!r} is not a *{_HOST_SUFFIX} hostname")
    return host


def _json_object(content: bytes) -> dict[str, Any] | None:
    """Parsed JSON iff it is an object, else None. Never raises — a career host behind a WAF
    can answer 200 with an HTML challenge page."""
    try:
        obj = json.loads(content)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def _search_item(content: bytes) -> dict[str, Any] | None:
    """`items[0]`, the single search-result envelope every list page wraps its rows in.

    The rows, the board total and the echoed site all hang off this one object; a payload
    whose `items` is absent, empty or not a list of objects is not a usable page.
    """
    payload = _json_object(content)
    if payload is None or not isinstance(payload.get("items"), list):
        return None
    items = payload["items"]
    if not items or not isinstance(items[0], dict):
        return None
    return items[0]


def _requisition_rows(item: dict[str, Any]) -> list[dict[str, Any]] | None:
    """The page's `requisitionList` rows, or None if the key is absent or not a list.

    None and [] are DIFFERENT and the caller must keep them apart: [] is a genuinely short
    page (the pager's termination condition), while None is the missing-`expand` signature of
    property 1 — a 200 carrying a real `TotalJobsCount` and no rows at all. Collapsing them
    would turn a silently truncated board into a clean `complete` scan.
    """
    rows = item.get("requisitionList")
    if not isinstance(rows, list):
        return None
    return [row for row in rows if isinstance(row, dict)]


def _failed(
    url: str, error: str, *, board_reported_total: int | None = None,
    board_enumerated: int | None = None, detail_deferred: int | None = None,
) -> BoardSnapshot:
    """A failed snapshot. A board whose every detail failed also carries its listing counts
    (T252): the cap's verdict for a board its clock cut at the first detail takes the provider's
    counts, and these are all it has. Every other failure happens before there is a listing."""
    return BoardSnapshot(
        status="failed", postings=[], url=url, observed_validators=None, error=error,
        board_reported_total=board_reported_total, board_enumerated=board_enumerated,
        detail_deferred=detail_deferred,
    )


@dataclass
class _Listing:
    """A board's listing as it is read: every row once by `Id`, in request order.

    `requests` counts every listing GET sent, failed ones included, and is what the page budget
    bounds; `page_ends` has one entry per page READ, which is what `listing_pages` reports."""

    requests: int = 0
    listed: list[dict[str, Any]] = field(default_factory=list)
    seen_ids: set[str] = field(default_factory=set)
    page_ends: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def read(self, rows: list[dict[str, Any]], scope: set[str]) -> int:
        """Take one page into the board's inventory and into `scope`, the ids the query that
        served it has listed, and return how many of its ids that query had ALREADY served. An
        id-less row is skipped, as it always was: it is counted by `TotalJobsCount`, so a board
        serving one stays short of complete."""
        repeated = 0
        for row in rows:
            posting_id = row.get("Id")
            if posting_id is None:
                continue
            key = str(posting_id)
            repeated += key in scope
            scope.add(key)
            if key not in self.seen_ids:
                self.seen_ids.add(key)
                self.listed.append(row)
        self.page_ends.append(len(self.listed))
        return repeated


def _page_query(
    fetcher: Fetcher,
    page_url: Callable[..., str],
    first_rows: list[dict[str, Any]],
    listing: _Listing,
    *,
    budget: int,
    label: str = "",
    watch_deadline: bool = False,
) -> tuple[str, set[str], int]:
    """Page one query to its end, its offset-0 page (`first_rows`) already requested.

    Returns how it ended, the ids THIS query listed, and how many ids it served on more than one
    page (offset paging over a listing that moved while it was read). "short" is the only complete
    ending; the others are "repeat", "cap" (`budget` requests spent across the board), "failed"
    and "deadline". The unsplit listing is exactly the pager this module always ran: the same
    requests and the same notes. Only a split watches the board's deadline."""
    scope: set[str] = set()
    rows, offset, repeated = first_rows, 0, 0
    while True:
        before = len(scope)
        repeated += listing.read(rows, scope)
        if len(rows) < _PAGE_LIMIT:
            # THE termination condition. NOT the echoed `Limit`, which reports whatever
            # was asked for even when the server clamped the page to 200 (property 2).
            return "short", scope, repeated
        if len(scope) == before:
            # A FULL page that added no new id is a repeat of one already collected.
            # Stop, and stay partial so apply_board does not close postings we stopped
            # re-listing (the Workday offset-wrap guard, same failure mode).
            listing.errors.append(
                f"{label}page at offset {offset} added no new postings; stopping "
                f"({len(scope)} collected, listing may be incomplete)"
            )
            return "repeat", scope, repeated
        if listing.requests >= budget:
            return "cap", scope, repeated
        offset += _PAGE_LIMIT
        if watch_deadline and not fetcher.request_fits_board_deadline():
            return "deadline", scope, repeated
        listing.requests += 1
        try:
            page = fetcher.get(page_url(offset=offset))
        except FetchFailure as exc:
            listing.errors.append(f"{label}page at offset {offset}: {exc}")
            return "failed", scope, repeated
        item = _search_item(page.content)
        if item is None:
            listing.errors.append(f"{label}page at offset {offset}: invalid payload")
            return "failed", scope, repeated
        next_rows = _requisition_rows(item)
        if next_rows is None:
            # Property 1. Distinguished from a short page ([]) on purpose: this is a 200
            # that enumerates nothing while claiming a total, which must never read as a
            # complete empty board.
            listing.errors.append(
                f"{label}page at offset {offset}: no 'requisitionList' in the response "
                "(the expand parameter is required to get any rows)"
            )
            return "failed", scope, repeated
        rows = next_rows


def _total(item: dict[str, Any]) -> int | None:
    """`TotalJobsCount`, meaningful at offset 0 only (property 3)."""
    try:
        return max(0, int(item["TotalJobsCount"]))
    except (KeyError, TypeError, ValueError):
        return None


class OracleHCMProvider:
    name = "oraclehcm"
    # Skips the detail read for an id the store holds open (T350): the scan loads the set only
    # for a provider that declares this.
    reads_known_ids = True
    # Oracle Fusion hostnames are unbounded ({tenant}.fa.{region}.oraclecloud.com,
    # fa-{x}-saasfaprod1.fa.ocs.oraclecloud.com), so identity is a SUFFIX and there are no
    # exact paste hosts.
    board_hosts: tuple[str, ...] = ()
    board_host_suffixes: tuple[str, ...] = (_HOST_SUFFIX,)
    # the slug is a host/site PAIR, so board_urls must let "/" through the qualified form
    composite_slug = True
    slug_help = (
        "an Oracle HCM board needs the career-site path: paste "
        "{tenant}.fa.{region}.oraclecloud.com/hcmUI/CandidateExperience/en/sites/<Site> "
        "or use oraclehcm:<host>/<Site>."
    )

    @staticmethod
    def employer_name_from_slug(slug: str) -> str | None:
        """The tenant label out of the host (T74). The SITE half is a career-site name of the
        tenant's own choosing (`CX_1`, `CampusHiring`) and names no employer."""
        try:
            host, _site = split_slug(slug)
        except ValueError:
            return None
        return employer_label_from_host(host, vendor_suffixes=(_HOST_SUFFIX,))

    @staticmethod
    def normalize_slug(slug: str) -> str:
        return "/".join(split_slug(slug))

    @staticmethod
    def slug_from_path(host: str, parts: list[str]) -> str | None:
        """Composite slug from a pasted career-site URL, read by GRAMMAR.

        Oracle serves one public shape and it names the site at a fixed marker:
        `/hcmUI/CandidateExperience/{locale}/sites/{site}[/job/{id}]`. The site is the
        segment immediately after `sites` — full stop. Read off the MARKER rather than off a
        position because the locale segment is the only variable part before it, and keying
        on `sites` tolerates that without having to enumerate locales.

        Returns None when the path carries no `sites` marker or nothing after it: that is a
        host on this suffix serving something other than a career site (Oracle Fusion hosts
        also serve the ERP, HCM and CX application UIs from the same names), and guessing a
        slug there would mint a company row for a board that does not exist.
        """
        lowered = [part.lower() for part in parts]
        if lowered[:2] != list(_UI_PREFIX):
            return None
        if _SITES_SEGMENT not in lowered:
            return None
        index = lowered.index(_SITES_SEGMENT)
        if index + 1 >= len(parts):
            return None
        return f"{host}/{parts[index + 1]}"

    def board_url(self, slug: str) -> str:
        """Canonical fetch URL == the http_cache key; stable parameter order. Raises
        ValueError on a malformed stored slug; scan/coordinator.py and scan/health.py guard
        the call."""
        return self._page_url(*split_slug(slug), offset=0)

    def _page_url(
        self, host: str, site: str, *, offset: int, posting_dates: str | None = None
    ) -> str:
        # `expand` is NOT optional here — without it the response carries no requisitionList
        # at all (property 1). Parameter order is fixed because this string is the cache key.
        # `posting_dates` is a split child's facet (property 6); the root's URL never has one.
        facet = "" if posting_dates is None else f",selectedPostingDatesFacet={posting_dates}"
        return (
            f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
            "?onlyData=true&expand=requisitionList.secondaryLocations"
            f"&finder=findReqs;siteNumber={site},limit={_PAGE_LIMIT},offset={offset}"
            f",sortBy=POSTING_DATES_DESC{facet}"
        )

    def _detail_url(self, host: str, site: str, posting_id: str) -> str:
        # The finder is `ById`, whose arguments are `Id` and `siteNumber`. The names matter:
        # `ByRequisitionId;requisitionId=...` is rejected with HTTP 400 "not valid", and
        # passing `siteNumber` as its own query parameter is rejected with "cannot be used in
        # this context". Both were measured; the resource's own /describe is what named `ById`.
        return details_url(host, site, posting_id)

    def fetch_board(self, fetcher: Fetcher, request: BoardRequest) -> BoardSnapshot:
        try:
            host, site = split_slug(request.slug)
        except ValueError as exc:
            return _failed(request.url, f"invalid oraclehcm slug: {exc}")

        try:
            page = fetcher.get(request.url, validators=request.validators)
        except FetchFailure as exc:
            return _failed(request.url, str(exc))
        if page.not_modified:
            return BoardSnapshot(
                status="unchanged", postings=[], url=request.url,
                observed_validators=None, error=None,
            )
        observed = page.observed_validators
        item = _search_item(page.content)
        if item is None:
            return _failed(request.url, "invalid board payload: missing search 'items' envelope")
        rows = _requisition_rows(item)
        if rows is None:
            return _failed(
                request.url,
                "invalid board payload: page at offset 0: no 'requisitionList' in the response "
                "(the expand parameter is required to get any rows)",
            )
        total = _total(item)
        listing = _Listing(requests=1)
        errors = listing.errors
        split = total is not None and total > _RESULT_WINDOW
        if split:
            assert total is not None
            # The root's own rows are kept, and not paged further: its children read them again.
            listing.read(rows, set())
            self._list_by_posting_date(fetcher, host, site, total, listing)
        else:
            ending, _, _ = _page_query(
                fetcher, partial(self._page_url, host, site), rows, listing, budget=_MAX_PAGES,
            )
            if ending == "cap":
                errors.append(
                    f"page cap of {_MAX_PAGES} pages reached; listing may be incomplete, "
                    "treating as partial so unseen postings are not closed"
                )
            elif total is not None and len(listing.seen_ids) < total:
                errors.append(
                    f"incomplete listing: collected {len(listing.seen_ids)} of {total} postings; "
                    "treating as partial so unseen postings are not closed"
                )
        listed, seen_ids, page_ends = listing.listed, listing.seen_ids, listing.page_ends

        # The FULL live inventory, computed BEFORE the detail phase: known and budget-skipped
        # postings must stay in it or apply_board's _process_missing closes them.
        listed_ids = set(seen_ids)

        unseen = [
            row for row in listed if str(row["Id"]) not in request.known_posting_ids
        ]
        unseen, gated = apply_listing_gate(request, unseen, _listing_fields)
        shadow = head_shadow(
            listed, page_ends, {str(row["Id"]) for row in unseen},
            lambda row: str(row["Id"]), _listed_day,
        )
        # Captured BEFORE the detail-budget slice below rebinds `unseen`, so detail_deferred
        # reflects what the budget actually cut, not the post-truncation length.
        unseen_before_truncation = unseen
        if len(unseen) > request.detail_budget:
            errors.append(
                f"detail budget of {request.detail_budget} exceeded "
                f"({len(unseen)} unseen postings); raise detail_fetch_budget or rescan"
            )
            unseen = unseen[: request.detail_budget]

        postings: list[RawPosting] = []
        detail_failures = 0
        first_failure: str | None = None
        for index, row in enumerate(unseen):
            # T248: the stop Workday and SmartRecruiters have had since T243 — past here the
            # board's clock could fail the board and discard every detail already fetched.
            if detail_phase_stops(
                fetcher, kept=bool(postings), left=len(unseen) - index, errors=errors
            ):
                unseen = unseen[:index]
                break
            posting_id = str(row["Id"])
            try:
                detail_res = fetcher.get(self._detail_url(host, site, posting_id))
            except FetchFailure as exc:
                detail_failures += 1
                errors.append(f"posting {posting_id} detail: {exc}")
                first_failure = first_failure or errors[-1]
                continue
            detail = _detail_item(detail_res.content)
            if detail is None:
                detail_failures += 1
                errors.append(f"posting {posting_id} detail: malformed payload")
                first_failure = first_failure or errors[-1]
                continue
            if not detail:
                # Property 5: 200 with `items: []` is a withdrawn or unknown requisition, not
                # an error. Drop it from the live inventory so apply_board closes it.
                listed_ids.discard(posting_id)
                continue
            try:
                postings.append(parse_posting(host, site, row, detail))
            except Exception as exc:  # per-posting isolation
                errors.append(f"posting {posting_id}: {exc}")

        if unseen and detail_failures == len(unseen):
            return _failed(
                request.url, f"all {len(unseen)} detail fetches failed; {first_failure}",
                board_reported_total=total, board_enumerated=len(seen_ids),
                detail_deferred=len(unseen_before_truncation) - len(unseen),
            )

        return BoardSnapshot(
            status="complete" if not errors else "partial",
            postings=postings,
            url=request.url,
            observed_validators=observed,
            error=None if not errors else "; ".join(errors),
            listed_ids=frozenset(listed_ids),
            board_reported_total=total,
            # DISTINCT ids off the RAW rows, before the detail budget truncated anything and
            # before a per-row parse failure dropped one, with id-less rows excluded. Every
            # provider means exactly this by the column.
            board_enumerated=len(seen_ids),
            detail_deferred=len(unseen_before_truncation) - len(unseen),
            gated_listings=gated,
            listing_pages=shadow.listing_pages,
            # A split has no single newest-first order, so no head-scan stop point (T352).
            head_pages=None if split else shadow.head_pages,
            head_missed=None if split else shadow.head_missed,
        )

    def _list_by_posting_date(
        self, fetcher: Fetcher, host: str, site: str, total: int, listing: _Listing
    ) -> None:
        """List a board over the window as its two posting-date children (property 6), noting in
        `errors` every way the split falls short: no note left is the certificate.

        Beyond each child's own count, the children's ids together must reach the board's total
        (two overlapping children can sum right while a row is in neither), and no child may
        serve an id on two pages: a listing that moved while it was read can push rows past the
        window, or skip one while a newer row fills the count."""
        totals: dict[str, int | None] = dict.fromkeys(_POSTING_DATE_PARTS)
        union: set[str] = set()
        for part in _POSTING_DATE_PARTS:
            label = f"posting-date facet {part}: "
            if listing.requests >= _SPLIT_MAX_PAGES:
                listing.errors.append(
                    f"{label}not read, the page budget of {_SPLIT_MAX_PAGES} is spent"
                )
                break
            if not fetcher.request_fits_board_deadline():
                listing.errors.append(f"{label}not read, the board deadline is near")
                break
            listing.requests += 1
            try:
                page = fetcher.get(self._page_url(host, site, offset=0, posting_dates=part))
            except FetchFailure as exc:
                listing.errors.append(f"{label}page at offset 0: {exc}")
                continue
            item = _search_item(page.content)
            rows = None if item is None else _requisition_rows(item)
            if item is None or rows is None:
                listing.errors.append(f"{label}page at offset 0: invalid payload")
                continue
            totals[part] = child_total = _total(item)
            ending, scope, repeated = _page_query(
                fetcher, partial(self._page_url, host, site, posting_dates=part), rows,
                listing, budget=_SPLIT_MAX_PAGES, label=label, watch_deadline=True,
            )
            union |= scope
            distinct = len(scope)
            if repeated:
                listing.errors.append(
                    f"{label}{repeated} postings served on two pages: the listing moved while it "
                    "was read"
                )
            if ending == "cap":
                listing.errors.append(
                    f"{label}stopped, the page budget of {_SPLIT_MAX_PAGES} is spent"
                )
            elif ending == "deadline":
                listing.errors.append(f"{label}stopped, the board deadline is near")
            elif ending == "short" and child_total is not None and distinct < child_total:
                listing.errors.append(
                    f"{label}incomplete listing: collected {distinct} of {child_total} postings"
                )
        recent, older = (totals[part] for part in _POSTING_DATE_PARTS)
        if (
            recent is None or older is None or recent + older != total
            or max(recent, older) > _RESULT_WINDOW
        ):
            listing.errors.append(
                f"posting-date split does not certify: {recent} under 30 days and {older} over, "
                f"against the board's {total}, with a window of {_RESULT_WINDOW}"
            )
        elif len(union) < total:
            listing.errors.append(
                f"posting-date split listed {len(union)} distinct postings of the board's {total}"
            )

    def healthcheck(self, fetcher: Fetcher, slug: str) -> BoardHealth:
        """NOTE: DEAD IS UNREACHABLE HERE, and for a worse reason than SmartRecruiters'.

        An unknown `siteNumber` does not answer 404 and does not answer empty — it silently
        serves the HOST'S DEFAULT BOARD (property 4). `CX_999` and `ZZnotasite` each returned
        eeho's CX_1 inventory (TotalJobsCount 2273, identical leading ids) and hdpc's
        CampusHiring inventory (1322, identical leading ids) respectively, echoing the bogus
        site straight back in `SiteNumber`. So a typo'd site is indistinguishable from a real
        and DIFFERENT board, which no amount of response inspection can catch, and this can
        only ever return OK/EMPTY/ERROR/UNREACHABLE.

        A real 404 (CDN/WAF blip, malformed host, future API change) must therefore classify
        as ERROR, not DEAD, so `dead_status` is a sentinel no HTTP status can equal.
        """
        try:
            url = self.board_url(slug)
        except ValueError:
            return BoardHealth.ERROR
        try:
            result = fetcher.get(url)
        except FetchFailure as exc:
            return health_from_failure(exc, dead_status=-1)
        item = _search_item(result.content)
        if item is None:
            return BoardHealth.ERROR
        rows = _requisition_rows(item)
        if rows is None:
            # A 200 with no requisitionList is the missing-expand signature, not an empty
            # board. board_url always sends expand, so reaching this means the API changed.
            return BoardHealth.ERROR
        return BoardHealth.OK if rows else BoardHealth.EMPTY


def _detail_item(content: bytes) -> dict[str, Any] | None:
    """The single detail object, `{}` for a withdrawn/unknown requisition, or None if the
    payload is unusable.

    THREE states, and the caller depends on all three staying apart: a dict is a live
    posting, `{}` is the 200-with-`items: []` signature that must CLOSE the posting, and None
    is a malformed body that must be counted as a detail FAILURE and leave the posting open.
    """
    payload = _json_object(content)
    if payload is None or not isinstance(payload.get("items"), list):
        return None
    items = payload["items"]
    if not items:
        return {}
    return items[0] if isinstance(items[0], dict) else None


def _listed_day(row: dict[str, Any], today: date) -> date | None:
    """The listing's date-only `PostedDate`, or None when it cannot be read (fresh)."""
    posted = _iso_to_naive_utc(row.get("PostedDate"))
    return None if posted is None else posted.date()


def _listing_fields(row: dict[str, Any]) -> tuple[str, str, list[str], str]:
    locations = [row.get("PrimaryLocation")]
    locations += [
        x.get("Name") if isinstance(x, dict) else x
        for x in row.get("secondaryLocations") or []
    ]
    return (
        str(row["Id"]), str(row.get("Title") or "").strip(),
        [str(x) for x in locations if x], "unknown",
    )


def parse_posting(
    host: str, site: str, listed: dict[str, Any], detail: dict[str, Any]
) -> RawPosting:
    posting_id = str(listed["Id"])
    title = str(listed.get("Title") or detail.get("Title") or "").strip()
    if not title:
        raise ValueError("empty title")
    return RawPosting(
        provider_posting_id=posting_id,
        title=title,
        url=posting_url(host, site, posting_id),
        locations=_locations(listed, detail),
        department=_department(listed, detail),
        remote_policy=_remote_policy(listed, detail),
        # The detail's timestamp is a full ISO instant; the list's `PostedDate` is date-only.
        posted_at=_iso_to_naive_utc(
            detail.get("ExternalPostedStartDate") or listed.get("PostedDate")
        ),
        updated_at=None,  # no update timestamp on either endpoint
        body_text=_body_text(detail),
        raw_json={"listed": listed, "detail": detail},
    )


def details_url(host: str, site: str, posting_id: str) -> str:
    """One requisition's detail resource. Shared by the scan's detail fetch and the liveness
    probe, so the two ask the same question."""
    return (
        f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"
        f"?expand=all&onlyData=true&finder=ById;Id={posting_id},siteNumber={site}"
    )


# The tails a public posting page ends in after `/sites/{site}/`, each followed by the numeric
# requisition id. `job` is what the scan stores; the two `requisitions/` forms are what
# aggregator copies carry (233 and 4 of 279 open unwatched rows on 2026-10-27).
# A site as live boards spell it (`CX_1`, `CX`, `CampusHiring`): nothing the finder grammar or a
# query string could read as structure.
_PAGE_SITE = re.compile(r"[A-Za-z0-9_-]+")
_POSTING_TAILS = (("job",), ("requisitions", "preview"), ("requisitions", "job"))


def details_url_for_page(url: str) -> str | None:
    """The detail resource for a public posting page, or None if `url` is not exactly one.

    The page is a client-rendered shell that answers 200 whatever the requisition's state, so
    the liveness probe asks this resource instead (`pipeline/liveness.py`). Exactly
    `{host}/hcmUI/CandidateExperience/{locale}/sites/{site}/{tail}/{id}`, with the query string
    ignored. Anything looser (no site segment, a redirect wrapper) is None and keeps the page
    probe: a guessed site would answer an empty `items`, and that is read as a death.
    """
    parts_url = urlsplit(url)
    parts = [part for part in parts_url.path.split("/") if part]
    if len(parts) < 7 or tuple(x.lower() for x in parts[:2]) != _UI_PREFIX:
        return None
    if parts[3].lower() != _SITES_SEGMENT or not parts[-1].isdigit():
        return None
    if tuple(x.lower() for x in parts[5:-1]) not in _POSTING_TAILS:
        return None
    # The site lands in the finder unescaped. A scanned slug is validated by `split_slug`, but a
    # stored aggregator URL is anyone's text, and `+` or `&` there changes what is asked.
    if not _PAGE_SITE.fullmatch(parts[4]):
        return None
    try:
        host, site = split_slug(f"{parts_url.hostname or ''}/{parts[4]}")
    except ValueError:
        return None
    return details_url(host, site, parts[-1])


def posting_url(host: str, site: str, posting_id: str) -> str:
    """The public career-site URL. The locale segment is pinned to `en` because the API is
    queried with no locale and answers `ContentLocale: "en"`; a URL claiming a locale the
    body was not fetched in would misdescribe what we stored."""
    return f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{posting_id}"


def _body_text(detail: dict[str, Any]) -> str:
    """The three External*Str sections, in a fixed order. `CorporateDescriptionStr` and
    `OrganizationDescriptionStr` are EXCLUDED (per-tenant boilerplate; would pollute
    content_hash) — the SmartRecruiters `companyDescription` rule."""
    parts: list[str] = []
    for key in _BODY_SECTIONS:
        text = html_to_text(str(detail.get(key) or "").strip())
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def _department(listed: dict[str, Any], detail: dict[str, Any]) -> str | None:
    """`Department` first -- it is the only field NAMED for this and BOTH endpoints carry it --
    then the list row's `JobFamily`.

    The order and the sources are measured, not guessed. `Department` is a key on the detail
    payload AND on every listed row. `JobFamily` is a key on the LISTED ROW ONLY: the detail
    payload carries `JobFamilyId` instead, so reading `detail["JobFamily"]` would be a read
    that can never hit. Both fields were null on all three tenants probed on 2026-09-06 (eeho
    2273 postings, hdpc 1322, egug 417 -- 100 rows sampled each, zero populated), so this
    column arrives empty from these tenants and only a differently-configured one will fill
    it. That is why it falls back rather than picking one field and stopping.
    """
    return _first_text(
        detail.get("Department"), listed.get("Department"), listed.get("JobFamily")
    )


def _locations(listed: dict[str, Any], detail: dict[str, Any]) -> list[str]:
    """PrimaryLocation first, then each secondary location's `Name`, deduped in order.

    Secondaries are preferred off the DETAIL payload and fall back to the listed row: both
    carry the same `secondaryLocations` array, but a posting whose detail fetch shape changes
    should still keep the locations the list already gave us.
    """
    names: list[str] = []
    primary = _first_text(detail.get("PrimaryLocation"), listed.get("PrimaryLocation"))
    if primary:
        names.append(primary)
    secondaries = detail.get("secondaryLocations")
    if not isinstance(secondaries, list):
        secondaries = listed.get("secondaryLocations")
    for entry in secondaries if isinstance(secondaries, list) else []:
        if not isinstance(entry, dict):
            continue
        name = _first_text(entry.get("Name"))
        if name:
            names.append(name)
    seen: set[str] = set()
    deduped: list[str] = []
    for name in names:
        if name not in seen:
            seen.add(name)
            deduped.append(name)
    return deduped


def _remote_policy(listed: dict[str, Any], detail: dict[str, Any]) -> RemotePolicy:
    """`WorkplaceTypeCode` is a closed, locale-independent catalog and is read first; the
    localized `WorkplaceType` label is the fallback for a tenant that populates only it.

    BOTH fields are present-but-EMPTY rather than absent on postings that set no workplace
    type ("" and null were measured side by side on the same board), so emptiness is checked
    rather than key presence — `.get(key, default)` substitutes only for an ABSENT key. An
    out-of-catalog code yields `unknown`, never a new bucket.
    """
    for source in (detail, listed):
        code = _first_text(source.get("WorkplaceTypeCode"))
        if code and code.upper() in _WORKPLACE_CODES:
            return _WORKPLACE_CODES[code.upper()]
    for source in (detail, listed):
        label = _first_text(source.get("WorkplaceType"))
        if not label:
            continue
        lowered = label.casefold()
        if "hybrid" in lowered:
            return "hybrid"
        if "remote" in lowered:
            return "remote"
        if "on-site" in lowered or "onsite" in lowered:
            return "onsite"
    return "unknown"


def _first_text(*values: Any) -> str | None:
    """The first value that is a non-empty string once stripped, else None."""
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _iso_to_naive_utc(value: Any) -> datetime | None:
    """`ExternalPostedStartDate` is a full offset-aware instant
    (`2026-09-06T21:02:29+00:00`); the list's `PostedDate` is date-only (`2026-09-06`) and
    becomes UTC midnight."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return to_naive_utc(parsed)
