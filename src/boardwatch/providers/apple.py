"""Apple provider: the jobs.apple.com hydration payload (live-verified 2026-09-07).

THERE IS NO JSON API. `/api/role/search` and `/api/csrfToken` both 301 to
`apple.com/pagenotfound`, and `GET /api/v1/search` answers `401 User Unauthorized`. What the
site actually ships is a server-rendered React Router document whose data is inlined:

    <script nonce="...">window.__staticRouterHydrationData = JSON.parse("{\\"loaderData\\":...}");

The argument is a DOUBLE-ENCODED JSON string -- a JSON string literal whose contents are
themselves JSON -- so reading it is `json.loads` twice (see `hydration_data`). Measured on the
live document, `JSON.parse(` occurs exactly once and the terminating `");` exactly once after
the marker, so the non-greedy capture below is unambiguous. A capture that will not decode is
an ERROR and never an empty board: that is the signature of Apple changing its front end, and
reading it as "this board has no jobs" would authorize `apply_board` to close every posting
the board holds.

Listing: `GET https://jobs.apple.com/en-us/search?location={filter}&page={n}`, path
`loaderData.search` -> `searchResults` (rows), `totalRecords`, `page`, `sort`, `searchMeta`,
`staticData`, `filters`.
Detail: `GET https://jobs.apple.com/en-us/details/{positionId}/{transformedPostingTitle}`,
same hydration blob, path `loaderData.jobDetails.jobsData`.

SEVEN MEASURED PROPERTIES DRIVE THIS DESIGN. Each has a regression test; none is decoration.

1. THE REDIRECT TRAP. A bare `GET /en-us/search` 301s to
   `/en-us/search?location=united-states-USA` and reports `totalRecords: 4509`; adding ANY
   query parameter suppresses the redirect, and `?page=1` reports `6108` (worldwide). The two
   numbers describe DIFFERENT BOARDS. So `board_url` always carries an explicit `location`,
   and every fetch ASSERTS the effective URL still carries the filter the slug asked for --
   a redirect that changes the filter is an ERROR, not a board. Without the assertion a
   silently re-scoped fetch would enumerate the wrong corpus under the right slug's name.

2. AN UNKNOWN LOCATION CODE EMPTIES THE BOARD, IT DOES NOT ERROR. `location=x-ZZZ` answers
   HTTP 200 with `totalRecords: 0` and `searchResults: []`. That is the amazon `category[]`
   failure mode, and an empty `complete` board is the one status that authorizes `apply_board`
   to close every posting it holds. `_LOCATIONS` is the defence.

3. ONLY THE TRAILING `-CODE` OF A LOCATION TOKEN IS READ, AND THE CODE IS NOT GUESSABLE.
   Measured: `x-USA`, `-USA` and `completelybogusname-USA` all return the same 4,509 as
   `united-states-USA`, while `united-states-usa` returns 0 -- the name part is decorative and
   the code is case-sensitive. The codes follow NO rule: Japan is `JPNC` and Australia `AUSC`,
   but Ireland is `IRL`, Singapore `SGP` and the United States `USA`; `IRLC`, `SGPC` and
   `USAC` are all empty. Worse, the code namespace is FLAT and mixes country rollups with
   site codes, so a plausible-looking ISO code can silently be a building: `NOR`, `FIN`,
   `GRC`, `HUN`, `LUX` and `ARG` all return rows whose `countryName` is the United States, and
   `PRT`, `CHL` and `PHL` return Australian ones. Every entry in `_LOCATIONS` was therefore
   accepted only after its page-1 rows reported the EXPECTED `countryName`; nine candidates
   that passed a `totalRecords > 0` check failed that one and are not in the catalog.

4. `totalRecords` COUNTS POSITION-LOCATION ROWS, NOT POSTINGS. A multi-location requisition is
   served once PER LOCATION, each row carrying a single-entry `locations` array: measured
   160 rows over 8 pages of the US board holding 120 distinct `positionId`s, one requisition
   appearing 4 times. The arithmetic confirms the unit -- the worldwide board reported 6,108
   and paged out as 305 full pages plus a final page of 8. This is why
   `board_reported_total` is None: the column's meaning is fixed repo-wide by D-271 as the
   denominator of `board_reported_total - board_enumerated`, `board_enumerated` is DISTINCT
   POSTING IDS, and a row count in that subtraction would report a permanent ~25% shortfall
   that no scan could ever close -- an unfailable ratio, which D-271 calls worse than no
   ratio. The board's own number is not discarded: the walk compares it against DISTINCT ROWS
   (`(positionId, postLocationIds)`, unique across all 160 measured rows) and forces `partial`
   when the walk came up short, which is the check that actually catches a truncated listing.

5. THE PAGE SIZE IS 20 AND IS NOT SETTABLE. `limit`, `pageSize` and `perPage` are all ignored
   (20 rows each). Paging is 1-indexed via `page`. Past the last page the server answers
   HTTP 200 with `searchResults: []` AND `totalRecords: 0` -- it does not 4xx and does not
   wrap -- which is the second reason `totalRecords` is read on the FIRST page only: a later
   page would rewrite the denominator to zero.

6. AN ETAG IS SENT AND IS USELESS. Both routes answer `ETag: W/"..."` with no
   `Last-Modified`, under `cache-control: no-store, no-cache, must-revalidate`; a conditional
   GET carrying that exact ETag answered 200, not 304. The observed validator is echoed rather
   than hardcoded to None so a service that starts honouring it is picked up without a code
   change, but `unchanged` is unreachable against the live site and the 304 branch is covered
   only by a mocked 304.

7. A DEAD DETAIL IS A 200, NOT A 404. `/en-us/details/000000000/nope` answers HTTP 200 with a
   perfectly valid hydration blob whose `loaderData` holds ONLY `root` -- no `jobDetails` key.
   Like Eightfold's 404 and unlike SmartRecruiters' explicit `active: false`, that is
   indistinguishable from an edge blip, so the id STAYS in `listed_ids` and the posting is
   simply not materialised this run.

BODIES LIVE ONLY ON THE DETAIL PAGE. The listing's `jobSummary` is a TEASER -- measured over a
full page: min 626, mean 668, max 1,055 characters -- and it is never allowed to stand in for a
body. `body_text` is assembled from the DETAIL payload's `jobSummary`, `description`,
`minimumQualifications` and `preferredQualifications`, in that order, blank sections skipped.
A row whose detail was not fetched (budget, failure, or property 7) is NOT MATERIALISED AT ALL:
it stays in `listed_ids` so `apply_board` does not close it, and it is counted in
`detail_deferred`. Because it was never stored it is still absent from `known_posting_ids` on
the next scan, so the next run fetches its detail -- which is how the deferral repairs itself.
This is the D-492 phenom defect, deliberately not reproduced.

Salary is never mined: neither payload carries any salary field (D19), so all four scalars
stay NULL.

`fetch_board` must never raise: every JSON level is validated as dict/list before use.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

from boardwatch.core.clock import to_naive_utc
from boardwatch.core.html_text import html_to_text
from boardwatch.core.models import BoardRequest, BoardSnapshot, RawPosting, RemotePolicy
from boardwatch.core.politeness import Fetcher, FetchFailure
from boardwatch.providers.base import BoardHealth, health_from_failure

_HOST = "jobs.apple.com"
_LOCALE = "en-us"
_SEARCH_URL = f"https://{_HOST}/{_LOCALE}/search"
_DETAIL_URL = f"https://{_HOST}/{_LOCALE}/details"
# Server-fixed (property 5): `limit`, `pageSize` and `perPage` are all ignored, not clamped.
_PAGE_SIZE = 20
# 500 x 20 = 10,000 rows, ~1.6x the LARGEST BOARD OBSERVABLE ON THIS SITE: the unfiltered
# worldwide listing, 6,108 rows on 2026-09-07, which paged out as 305 full pages plus a final
# page of 8 (page 307 was empty). No catalog slug is that large -- the biggest is
# `united-states` at 4,509 rows / 226 pages -- so the backstop sits above a board no slug can
# even address. Sized off a MEASURED board rather than a guess: D-492's Eightfold backstop was
# guessed and truncated a live 3,817-posting board the night it shipped. Normal termination is
# a short page; reaching this cap is reported as a shortfall rather than closing unseen rows.
_MAX_PAGES = 500
# The hydration marker. `JSON.parse(` occurs exactly once in the document and the terminating
# `");` exactly once after the marker (measured), so the non-greedy capture is unambiguous.
_HYDRATION = re.compile(r'window\.__staticRouterHydrationData\s*=\s*JSON\.parse\("(.*?)"\);',
                        re.DOTALL)
# The detail payload's sections, in the order they are concatenated into `body_text`.
_SECTIONS = ("jobSummary", "description", "minimumQualifications", "preferredQualifications")
# The query parameter that names a board, and the one whose value a redirect must not change.
_FILTER_PARAM = "location"

# Slug token -> the EXACT `location` value to send. 35 country boards, every one verified live
# on 2026-09-07 by BOTH tests property 3 demands: `totalRecords > 0`, and every location on
# page 1 reporting the expected `countryName`. Trailing comment is that day's row count.
#
# The slug is a clean country token and the VALUE carries Apple's own code, because the code is
# the only part the server reads and it cannot be derived from the country (property 3). This is
# a CLOSED, versioned catalog for the reason property 2 gives: an out-of-catalog token would be
# answered with an empty board and no error, and an empty `complete` board authorizes
# `apply_board` to close every posting it holds. The 35 boards summed to 6,100 of the
# worldwide 6,108 rows, so this axis partitions the board with a residual of 8 rows in
# countries no probe reached.
_LOCATIONS: dict[str, str] = {
    "australia": "australia-AUSC",  # 37
    "austria": "austria-AUT",  # 10
    "belgium": "belgium-BELC",  # 5
    "brazil": "brazil-BRAC",  # 12
    "canada": "canada-CANC",  # 36
    "china": "china-CHNC",  # 514
    "denmark": "denmark-DNK",  # 1
    "france": "france-FRAC",  # 26
    "germany": "germany-DEU",  # 77
    "hong-kong": "hong-kong-HKG",  # 2
    "india": "india-INDC",  # 177
    "indonesia": "indonesia-IDN",  # 3
    "ireland": "ireland-IRL",  # 34
    "israel": "israel-ISR",  # 116
    "italy": "italy-ITAC",  # 17
    "japan": "japan-JPNC",  # 62
    "macao": "macao-MAC",  # 1
    "malaysia": "malaysia-MYS",  # 24
    "mexico": "mexico-MEXC",  # 15
    "netherlands": "netherlands-NLD",  # 12
    "new-zealand": "new-zealand-NZL",  # 5
    "poland": "poland-POL",  # 2
    "saudi-arabia": "saudi-arabia-SAU",  # 17
    "singapore": "singapore-SGP",  # 106
    "south-korea": "korea-KOR",  # 24
    "spain": "spain-ESPC",  # 19
    "sweden": "sweden-SWEC",  # 7
    "switzerland": "switzerland-CHEC",  # 18
    "taiwan": "taiwan-TWN",  # 11
    "thailand": "thailand-THA",  # 2
    "turkiye": "turkiye-TURC",  # 8
    "united-arab-emirates": "united-arab-emirates-ARE",  # 12
    "united-kingdom": "united-kingdom-GBR",  # 137
    "united-states": "united-states-USA",  # 4509
    "vietnam": "vietnam-VNM",  # 42
}


def _failed(url: str, error: str) -> BoardSnapshot:
    return BoardSnapshot(
        status="failed", postings=[], url=url, observed_validators=None, error=error,
    )


def hydration_data(content: bytes) -> dict[str, Any]:
    """`window.__staticRouterHydrationData` as a dict, or ValueError.

    The argument to `JSON.parse` is a JSON STRING LITERAL whose contents are themselves JSON,
    so it decodes twice: the captured text is re-quoted and read as a string (which applies
    the `\\"` unescaping), and that string is read as the object. Both failures raise, and
    every caller maps a raise to ERROR rather than to an empty board (property 1's rationale).
    """
    match = _HYDRATION.search(content.decode("utf-8", "replace"))
    if match is None:
        raise ValueError("no window.__staticRouterHydrationData blob: not a jobs.apple.com page")
    try:
        inner = json.loads(f'"{match.group(1)}"')
    except ValueError as exc:
        raise ValueError(f"hydration blob is not a JSON string literal: {exc}") from exc
    if not isinstance(inner, str):
        raise ValueError("hydration blob did not decode to a string")
    try:
        blob = json.loads(inner)
    except ValueError as exc:
        raise ValueError(f"hydration payload is not JSON: {exc}") from exc
    if not isinstance(blob, dict):
        raise ValueError("hydration payload is not a JSON object")
    return blob


def _loader(content: bytes, key: str) -> dict[str, Any]:
    """`loaderData.{key}` out of a hydration blob, or ValueError.

    A MISSING KEY RAISES rather than returning empty, because the two conditions this
    distinguishes are opposite: a search page whose `search` loader is gone has changed shape
    (ERROR), and a detail page with no `jobDetails` is a posting that is not there (property 7).
    Both callers need to tell those apart from a board that legitimately listed nothing.
    """
    loader = hydration_data(content).get("loaderData")
    if not isinstance(loader, dict):
        raise ValueError("hydration payload carries no loaderData object")
    section = loader.get(key)
    if not isinstance(section, dict):
        raise ValueError(f"hydration payload carries no loaderData.{key} object")
    return section


def _row_key(row: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    """The natural key of a LISTING ROW: its posting id plus the locations that row names.

    Rows are position-LOCATION pairs (property 4), so the posting id alone does not identify
    one and `totalRecords` is a count of these. Unique across all 160 rows measured over 8
    consecutive pages, which is what makes it usable as the completeness denominator.
    """
    locations = row.get("locations")
    codes = (
        tuple(sorted(
            code
            for loc in locations
            if isinstance(loc, dict) and (code := _post_location_id(loc))
        ))
        if isinstance(locations, list)
        else ()
    )
    return str(row.get("positionId")), codes


def _post_location_id(loc: dict[str, Any]) -> str:
    """A location entry's own identifier. THE TWO PAYLOADS SPELL IT DIFFERENTLY: a listing
    row carries `postLocationId`, the detail payload carries `id` (both `postLocation-{CODE}`).
    Reading only one of them would collapse every row of a multi-location requisition onto a
    single key, and the walk would then report a spurious shortfall against `totalRecords` and
    downgrade every healthy board to `partial`."""
    for key in ("postLocationId", "id"):
        value = str(loc.get(key) or "").strip()
        if value:
            return value
    return ""


class AppleProvider:
    name = "apple"
    board_hosts: tuple[str, ...] = (_HOST,)
    # A board is a COUNTRY, and a country lives in the QUERY STRING (`?location=...`), never in
    # the path -- the only path segment before `search` is the locale (`en-us`). So no path
    # segment of any jobs.apple.com URL names a board, `slug_from_path` answers None for every
    # URL, and both the board-URL and posting-URL paste routes fall through to `slug_help`
    # instead of letting the default extractor hand `normalize_slug` the locale and produce a
    # catalog diagnostic about a word the user never typed. Identical to amazon's situation, and
    # it is also why `lanes/dereference.py` refuses this provider; its own section there says so.
    slug_help = (
        "a jobs.apple.com board is one country, and a country is a query parameter rather "
        "than a path segment, so no URL names one. Add it as apple:<country>, e.g. "
        "apple:united-states"
    )

    @staticmethod
    def slug_from_path(host: str, parts: list[str]) -> str | None:
        return None

    @staticmethod
    def normalize_slug(slug: str) -> str:
        """The lowercased catalog token. Raises ValueError outside `_LOCATIONS` --
        `board_urls._normalize_slug` turns that into UnknownBoardURL so the CLI does not
        traceback.

        The guard is the whole reason the slug is a token rather than the location value: a
        code Apple does not know is answered with `totalRecords: 0` and no error (property 2),
        so a typo would be watched forever as a board that is merely empty today -- and a code
        that looks like the right country can silently be a building in another one
        (property 3)."""
        token = slug.strip().lower()
        if token not in _LOCATIONS:
            raise ValueError(
                f"expected one of the {len(_LOCATIONS)} jobs.apple.com country boards, "
                f"got {slug!r}"
            )
        return token

    def board_url(self, slug: str) -> str:
        """Page 1 == the http_cache key; stable parameter order.

        ALWAYS carries an explicit `location`, which is what makes the fetch immune to
        property 1's redirect: a bare search URL is 301'd to the US board, so a slug-shaped
        URL with no parameter could be silently re-scoped to a different corpus."""
        return self._page_url(self.normalize_slug(slug), 1)

    def _page_url(self, token: str, page: int) -> str:
        query = urlencode([(_FILTER_PARAM, _LOCATIONS[token]), ("page", page)])
        return f"{_SEARCH_URL}?{query}"

    def _detail_url(self, position_id: str, title_slug: str) -> str:
        return f"{_DETAIL_URL}/{position_id}/{title_slug}"

    def _filter_intact(self, token: str, final_url: str) -> bool:
        """Whether an effective URL still names the board the slug asked for (property 1).

        An empty `final_url` PASSES: `FetchResult` documents it as "no URL was observed" (a
        mocked or 304 response), and treating an absent observation as a re-scope would fail
        every board on a condition nothing measured.
        """
        if not final_url:
            return True
        values = parse_qs(urlsplit(final_url).query).get(_FILTER_PARAM, [])
        return values == [_LOCATIONS[token]]

    def fetch_board(self, fetcher: Fetcher, request: BoardRequest) -> BoardSnapshot:
        try:
            token = self.normalize_slug(request.slug)
        except ValueError as exc:
            return _failed(request.url, f"invalid apple slug: {exc}")

        errors: list[str] = []
        rows: list[dict[str, Any]] = []
        seen_rows: set[tuple[str, tuple[str, ...]]] = set()
        reported_rows: int | None = None
        observed = None

        for page in range(1, _MAX_PAGES + 1):
            first = page == 1
            # Page 1 is request.url (the cache key) verbatim; later pages are the same route
            # with their own `page`, so a conditional GET is only ever sent for the first.
            url = request.url if first else self._page_url(token, page)
            try:
                result = fetcher.get(url, validators=request.validators if first else None)
            except FetchFailure as exc:
                if first:
                    return _failed(request.url, str(exc))
                errors.append(f"page {page}: {exc}")
                break
            if first:
                if result.not_modified:
                    return BoardSnapshot(
                        status="unchanged", postings=[], url=request.url,
                        observed_validators=None, error=None,
                    )
                observed = result.observed_validators
            if not self._filter_intact(token, result.final_url):
                # A REDIRECT THAT CHANGED THE FILTER IS AN ERROR, NEVER A BOARD (property 1).
                # Fatal on any page: the rows this page served belong to a different corpus,
                # and keeping the earlier pages would file two boards' postings under one slug.
                return _failed(
                    request.url,
                    f"page {page} was re-scoped by a redirect: expected "
                    f"{_FILTER_PARAM}={_LOCATIONS[token]!r}, effective URL was "
                    f"{result.final_url!r}",
                )
            try:
                section = _loader(result.content, "search")
            except ValueError as exc:
                # The hydration blob being absent or undecodable is ERROR, never EMPTY.
                if first:
                    return _failed(request.url, f"search page: {exc}")
                errors.append(f"page {page}: {exc}")
                break
            listed = section.get("searchResults")
            if not isinstance(listed, list):
                message = f"page {page}: payload carries no searchResults list"
                if first:
                    return _failed(request.url, message)
                errors.append(message)
                break
            if first:
                # Page 1's `totalRecords` is the one read: past the last page the server
                # reports 0 (property 5), which would rewrite the denominator to zero.
                total = section.get("totalRecords")
                reported_rows = (
                    max(0, total) if isinstance(total, int) and not isinstance(total, bool)
                    else None
                )
            page_rows = [row for row in listed if isinstance(row, dict)]
            if len(page_rows) != len(listed):
                # NEVER silent: an entry we cannot read is a row we cannot key, and dropping it
                # quietly shrinks the listing while `status` stays "complete".
                errors.append(
                    f"page {page}: dropped {len(listed) - len(page_rows)} entries "
                    "that are not objects"
                )
            for row in page_rows:
                key = _row_key(row)
                if key in seen_rows:
                    continue
                seen_rows.add(key)
                rows.append(row)
            if len(listed) < _PAGE_SIZE:
                # THE termination condition, counted off the RAW array rather than off
                # `page_rows`: an unreadable entry still occupied a slot, so filtering before
                # the comparison would read a full page as a short one and stop the walk early.
                break
        else:
            errors.append(f"page cap of {_MAX_PAGES} pages reached; listing may be incomplete")

        # DISTINCT POSTING IDS, off the RAW rows -- before the detail budget truncates anything
        # and before a per-row parse failure drops one (D-271). An id-less row is excluded
        # rather than counted: it is a posting we cannot fetch, dedupe or close.
        listed_ids = {
            str(row["positionId"]) for row in rows if row.get("positionId") is not None
        }
        idless = sum(1 for row in rows if row.get("positionId") is None)
        if idless:
            errors.append(f"skipped {idless} rows with no positionId")
        if reported_rows is not None and len(seen_rows) < reported_rows:
            # A SHORT PAGE IS NOT PROOF THE BOARD ENDED. Compared in ROWS, which is the unit
            # `totalRecords` speaks (property 4) -- comparing it against distinct posting ids
            # would force `partial` on every healthy multi-location board instead.
            errors.append(
                f"incomplete listing: collected {len(seen_rows)} of {reported_rows} rows; "
                "treating as partial so unseen postings are not closed"
            )

        postings, detail_errors, deferred = self._fetch_details(fetcher, rows, request)
        errors.extend(detail_errors)

        if errors:
            status, error = "partial", f"{len(errors)} issue(s): " + "; ".join(errors[:3])
        else:
            status, error = "complete", None
        return BoardSnapshot(
            status=status,
            postings=postings,
            url=request.url,
            # Apple DOES send an ETag and it does NOT yield a 304 (property 6). Echoed rather
            # than hardcoded None so a service that starts honouring it needs no code change.
            observed_validators=observed,
            error=error,
            listed_ids=frozenset(listed_ids),
            # None DELIBERATELY: `totalRecords` counts rows, not postings, and this column is
            # the denominator of a postings subtraction (property 4).
            board_reported_total=None,
            board_enumerated=len(listed_ids),
            detail_deferred=deferred,
        )

    def _fetch_details(
        self, fetcher: Fetcher, rows: list[dict[str, Any]], request: BoardRequest
    ) -> tuple[list[RawPosting], list[str], int]:
        """The newly-fetched postings, the issues, and how many rows the budget deferred.

        One detail fetch per DISTINCT posting id, not per row: a multi-location requisition is
        several rows and one posting (property 4), and the detail payload carries all of that
        posting's locations, so fetching per row would spend the budget several times over on
        the same document.
        """
        errors: list[str] = []
        unseen: list[dict[str, Any]] = []
        chosen: set[str] = set()
        for row in rows:
            posting_id = row.get("positionId")
            # An id-less row is skipped here for the same reason it is kept out of
            # `listed_ids`: `str(None)` is the truthy literal "None", so keeping it would spend
            # a detail request on it and, on any 200, mint a posting keyed "None" that collides
            # with every other id-less row under UNIQUE(company_id, provider_posting_id) and is
            # absent from `listed_ids`, so `apply_board` would close it the instant it was
            # written. The D-492 defect.
            if posting_id is None:
                continue
            identifier = str(posting_id)
            if identifier in request.known_posting_ids or identifier in chosen:
                continue
            chosen.add(identifier)
            unseen.append(row)

        # Captured BEFORE the budget slice rebinds `unseen`, so `detail_deferred` reflects what
        # the budget actually cut rather than the post-truncation length (D-271).
        unseen_before_truncation = len(unseen)
        budget = request.detail_budget
        if unseen_before_truncation > budget:
            errors.append(
                f"detail budget of {budget} exceeded ({unseen_before_truncation} unseen "
                "postings); raise detail_fetch_budget or rescan"
            )
            unseen = unseen[:budget]

        postings: list[RawPosting] = []
        failures = 0
        for row in unseen:
            posting_id = str(row["positionId"])
            title_slug = str(row.get("transformedPostingTitle") or "").strip()
            if not title_slug:
                # The detail route needs BOTH halves and a row missing either is skipped
                # rather than given an invented URL.
                failures += 1
                errors.append(f"posting {posting_id}: no transformedPostingTitle")
                continue
            try:
                detail_res = fetcher.get(self._detail_url(posting_id, title_slug))
            except FetchFailure as exc:
                failures += 1
                errors.append(f"posting {posting_id} detail: {exc}")
                continue
            try:
                detail = _loader(detail_res.content, "jobDetails")
                jobs_data = detail.get("jobsData")
                if not isinstance(jobs_data, dict):
                    raise ValueError("jobDetails carries no jobsData object")
            except ValueError as exc:
                # Property 7: a dead detail is a 200 whose loaderData holds only `root`. A
                # FAILURE, never a close signal -- the id stays in `listed_ids` and the
                # posting is simply not materialised. The teaser is NEVER promoted to a body.
                failures += 1
                errors.append(f"posting {posting_id} detail: {exc}")
                continue
            try:
                postings.append(parse_posting(row, jobs_data))
            except Exception as exc:  # per-posting isolation
                errors.append(f"posting {posting_id}: {exc}")

        if unseen and failures == len(unseen):
            # FIRST, not appended: only the first three issues reach `BoardSnapshot.error`,
            # and "every detail fetch failed" is the one an operator has to see.
            errors.insert(0, f"all {len(unseen)} detail fetches failed")
        return postings, errors, max(0, unseen_before_truncation - budget)

    def healthcheck(self, fetcher: Fetcher, slug: str) -> BoardHealth:
        """Page 1 of the slug's filter. A missing or undecodable hydration blob is ERROR, never
        EMPTY: that is the signature of Apple changing its front end, and it must not read as
        "this board has no jobs"."""
        try:
            token = self.normalize_slug(slug)
        except ValueError:
            return BoardHealth.ERROR
        try:
            result = fetcher.get(self._page_url(token, 1))
        except FetchFailure as exc:
            return health_from_failure(exc)
        if not self._filter_intact(token, result.final_url):
            return BoardHealth.ERROR
        try:
            section = _loader(result.content, "search")
        except ValueError:
            return BoardHealth.ERROR
        listed = section.get("searchResults")
        if not isinstance(listed, list):
            return BoardHealth.ERROR
        return BoardHealth.OK if listed else BoardHealth.EMPTY


def parse_posting(listed: dict[str, Any], detail: dict[str, Any]) -> RawPosting:
    posting_id = str(listed["positionId"])
    title = str(listed.get("postingTitle") or detail.get("postingTitle") or "").strip()
    if not title:
        raise ValueError("empty title")
    title_slug = str(
        detail.get("transformedPostingTitle") or listed.get("transformedPostingTitle") or ""
    ).strip()
    if not title_slug:
        raise ValueError("no transformedPostingTitle")
    return RawPosting(
        provider_posting_id=posting_id,
        title=title,
        url=f"{_DETAIL_URL}/{posting_id}/{title_slug}",
        locations=_locations(detail, listed),
        department=_department(detail, listed),
        remote_policy=_remote_policy(detail, listed),
        posted_at=_posted_at(detail, listed),
        # Neither payload carries a modification timestamp. `postingDate` and `postingDateMeta`
        # are display renderings of the same posting date, not an update.
        updated_at=None,
        body_text=_body_text(detail),
        # NESTED, never merged: the two payloads collide on `jobSummary`, `positionId`,
        # `postingDate`, `locations` and `homeOffice`, so a flat merge would silently drop one
        # side's reading of a field this module actually reads.
        raw_json={"listed": listed, "detail": detail},
    )


def _body_text(detail: dict[str, Any]) -> str:
    """jobSummary, description, minimumQualifications, preferredQualifications -- from the
    DETAIL payload only. The listing's `jobSummary` is a teaser and is never a body; a posting
    with no detail is not materialised at all, so this is never called with one."""
    sections = [text for key in _SECTIONS if (text := str(detail.get(key) or "").strip())]
    return html_to_text("\n".join(sections))


def _locations(detail: dict[str, Any], listed: dict[str, Any]) -> list[str]:
    """The DETAIL payload's `locations` first, because it carries ALL of a multi-location
    posting's locations while a listing row names only the one that row was served for
    (property 4) -- measured: a 4-row requisition whose detail listed all four.

    `name` is preferred over `city`: it is the label Apple itself shows ("San Francisco Bay
    Area", "Austin Metro Area") and is populated on rows where `city` is blank.
    """
    for source in (detail, listed):
        values = source.get("locations")
        if not isinstance(values, list):
            continue
        labels = [
            label
            for loc in values
            if isinstance(loc, dict)
            and (label := _location_label(loc))
        ]
        if labels:
            return labels
    return []


def _location_label(loc: dict[str, Any]) -> str:
    """One location's label: `name`, else `city`, else `countryName`; "" when it names none."""
    for key in ("name", "city", "countryName"):
        label = str(loc.get(key) or "").strip()
        if label:
            return label
    return ""


def _department(detail: dict[str, Any], listed: dict[str, Any]) -> str | None:
    """`teamNames` on the detail (a LIST -- measured `["Apple Retail", "Sales and Business
    Development"]`), else the listing row's `team.teamName`. Joined rather than truncated so a
    posting filed under two teams does not silently become one."""
    names = detail.get("teamNames")
    if isinstance(names, list):
        labels = [label for name in names if (label := str(name or "").strip())]
        if labels:
            return ", ".join(labels)
    team = listed.get("team")
    if isinstance(team, dict):
        label = str(team.get("teamName") or "").strip()
        if label:
            return label
    return None


def _remote_policy(detail: dict[str, Any], listed: dict[str, Any]) -> RemotePolicy:
    """`homeOffice` is the ONLY signal, and there is deliberately no location-text fallback.

    Measured 2026-09-07 over ~140 US rows: no location `name` contained "remote" or "home"
    even once, so a text rule is a rule that can never fire on any Apple board -- which this
    repo treats as a monitoring failure, not conservatism (the same finding amazon recorded).
    `homeOffice: true` rows still carry physical city locations, so the flag is what
    distinguishes them and the text could not.

    A false `homeOffice` is NOT mapped to `onsite`: it is the feed's default for anything
    unstated, and no probe here can separate "this role is onsite" from "the field was not
    set". `hybrid` has no signal at all.
    """
    for source in (detail, listed):
        value = source.get("homeOffice")
        if isinstance(value, bool):
            return "remote" if value else "unknown"
    return "unknown"


def _posted_at(detail: dict[str, Any], listed: dict[str, Any]) -> datetime | None:
    """`postDateInGMT`, detail first. NEVER `postingDate` -- that is a display string
    ("Sep 07, 2026") whose month name would be read through the process locale.

    The two payloads spell the same instant differently -- the listing carries nanosecond
    precision with a `Z` (`2026-09-07T05:22:08.324174937Z`) and the detail milliseconds with
    an offset (`2026-09-07T12:42:42.277+00:00`) -- and `fromisoformat` reads both on this
    project's Python.
    """
    for source in (detail, listed):
        value = source.get("postDateInGMT")
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            return to_naive_utc(datetime.fromisoformat(value.strip().replace("Z", "+00:00")))
        except ValueError:
            continue
    return None
