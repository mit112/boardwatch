"""Amazon provider: the amazon.jobs public search API (live-verified 2026-09-07).

`GET https://www.amazon.jobs/en/search.json?offset={n}&result_limit={k}&sort=recent
&category[]={category}`. Unauthenticated -- no cookie, no token, no Referer.

Shape: `{"error": null, "hits": N, "facets": {}, "content": {...}, "jobs": [ {...} ],
"job_posting_search_request": "<json string>"}`.

BODIES ARE INLINE AND THERE IS NO DETAIL ENDPOINT. `description`, `basic_qualifications` and
`preferred_qualifications` are full HTML-ish text on the LISTING row, so this provider defines no
`_detail_url`, `detail_deferred` is always 0, and `detail_fetch_budget` never applies to it. The
whole 2,597-posting Software Development category costs 26 requests and nothing more.

FIVE MEASURED HARD LIMITS, AND EVERY ONE OF THEM ANSWERS HTTP 200 -- the status code is never the
signal here, `error` is:

1. `result_limit` maxes at 100. `result_limit=500` answers `{"error": "Result limit cannot be
   greater than 100", "hits": 0, "jobs": null}`. It is NOT clamped, so the page size is PINNED.
2. `offset` ceiling is 10000. `offset=10000` answers `{"error": "Cannot return more than 10000
   results at once", ...}`, so ONE query can never enumerate more than 10,000 rows.
3. `hits` is CAPPED at 10000 and is not a true total. Unfiltered `hits` reads exactly 10000 while
   the real corpus summed 22,282 over the category facet on 2026-09-07.
4. AN UNKNOWN FACET VALUE IS A SILENT LIE, NOT AN ERROR. `category[]=Totally Made Up` answers
   `{"error": null, "hits": 0, "jobs": []}`, and a bogus `job_function_id[]` answers
   `hits: 10000` (i.e. unfiltered). That is the Oracle `siteNumber` failure mode: a wrong slug
   does not error, it empties or widens the board. `_CATEGORIES` is the defence.
5. `category[]` IS honoured: `category[]=Software Development` answered `hits: 2597`.

THE CATEGORY FACET IS BOTH THE SLICING KEY AND THE CATALOG, and the slicing is what makes this
provider correct rather than convenient. `...&facets[]=category` returns 38 single-key dicts whose
largest count is 3,370 -- every category sits comfortably under the 10,000 offset ceiling, so
category-per-board enumerates the whole corpus while the unfiltered query provably cannot.

PAGINATION IS NOT A STABLE SNAPSHOT. `sort=recent` orders by created date descending, so a
posting landing mid-walk shifts every later page by one and a row can be served twice. Rows are
therefore deduped by `id_icims` across pages; `board_enumerated` counts distinct listed ids.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from urllib.parse import quote, urlencode

from boardwatch.core.html_text import html_to_text
from boardwatch.core.models import BoardRequest, BoardSnapshot, RawPosting, RemotePolicy
from boardwatch.core.politeness import Fetcher, FetchFailure
from boardwatch.providers.base import BoardHealth, count_listed_ids, health_from_failure

_HOST = "www.amazon.jobs"
_SEARCH_URL = f"https://{_HOST}/en/search.json"
_PAGE_LIMIT = 100  # HARD server maximum: result_limit=101+ answers an `error`, it is not clamped
_SORT = "recent"
# 100 x 100 = 10,000, WHICH IS THE SERVER'S OWN `offset` CEILING. This is not a tunable: the last
# offset this loop can request is 9,900, and raising the cap would walk straight into
# `{"error": "Cannot return more than 10000 results at once"}`. The largest live category held
# 3,370 postings, so the real termination is always a short page.
_MAX_PAGES = 100
# `hits` is CAPPED at this value rather than reported, so it means ">= 10000", never "== 10000".
# Compare `providers/workday.py:_TOTAL_CENSOR`, which this follows deliberately.
_HITS_CENSOR = 10000
# description, then basic_qualifications, then preferred_qualifications. All three were non-empty
# on 2,597 of 2,597 probed Software Development rows; blank sections are skipped anyway so a feed
# that stops publishing one contributes nothing rather than an empty block.
_SECTIONS = ("description", "basic_qualifications", "preferred_qualifications")
# `posted_date` is a HUMAN STRING, and it is parsed against this table rather than `%B` because
# `strptime` reads `%B` through the process locale: on a machine whose LC_TIME is not English
# every Amazon `posted_at` would silently become NULL. boardwatch is built to fit anyone who runs
# it, so the month names the API emits are pinned here instead.
_MONTHS = {
    name: number
    for number, name in enumerate(
        (
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december",
        ),
        start=1,
    )
}
# The per-location `type` inside a `locations` entry that means "not tied to a building".
# Measured 2026-09-07 over 770 rows / 1,456 locations across four categories: ONSITE 1,432,
# VIRTUAL 24, nothing else. See `_remote_policy` for why ONSITE is deliberately not mapped.
_VIRTUAL = "VIRTUAL"

# Slug -> the EXACT Amazon category string, all 38 live entries as of 2026-09-07 with their
# counts. The slug is a CATALOG TOKEN, not the category itself: the category names carry spaces,
# commas, `&`, `/` and `--` (`Project/Program/Product Management--Non-Tech`), none of which
# survives `provider:slug` parsing or a URL path intact. A closed, versioned catalog is also the
# only defence against limit 4 above -- an out-of-catalog token is a FAILURE, never a new bucket,
# because the API would answer a wrong one with an empty board and `error: null`, and an empty
# `complete` board is the one status that authorizes apply_board to close every posting it holds.
_CATEGORIES: dict[str, str] = {
    "administrative-support": "Administrative Support",  # 645
    "applied-science": "Applied Science",  # 427
    "audio-video-photography-production": "Audio / Video / Photography Production",  # 35
    "business-intelligence": "Business Intelligence",  # 222
    "business-merchant-development": "Business & Merchant Development",  # 388
    "buying-planning-instock-management": "Buying, Planning, & Instock Management",  # 305
    "corporate-operations": "Corporate Operations",  # 569
    "customer-service": "Customer Service",  # 197
    "data-science": "Data Science",  # 170
    "database-administration": "Database Administration",  # 19
    "design": "Design",  # 354
    "economics": "Economics",  # 27
    "editorial-writing-content-management": "Editorial, Writing, & Content Management",  # 81
    "facilities-maintenance-real-estate": "Facilities, Maintenance, & Real Estate",  # 907
    "finance-accounting": "Finance & Accounting",  # 668
    "fulfillment-associate": "Fulfillment Associate",  # 234
    "fulfillment-operations-management": "Fulfillment & Operations Management",  # 2245
    "fulfillment-warehouse-associate": "Fulfillment / Warehouse Associate",  # 36
    "hardware-development": "Hardware Development",  # 701
    "human-resources": "Human Resources",  # 500
    "investigation-loss-prevention": "Investigation & Loss Prevention",  # 212
    "leadership-development-training": "Leadership Development & Training",  # 40
    "legal": "Legal",  # 159
    "machine-learning-science": "Machine Learning Science",  # 131
    "marketing-pr": "Marketing & PR",  # 345
    "medical-health-safety": "Medical, Health, & Safety",  # 585
    "operations-it-support-engineering": "Operations, IT, & Support Engineering",  # 3370
    "pr": "PR",  # 41
    "procurement": "Procurement",  # 121
    "project-program-product-management-non-tech":  # 1211
        "Project/Program/Product Management--Non-Tech",
    "project-program-product-management-technical":  # 1187
        "Project/Program/Product Management--Technical",
    "public-policy": "Public Policy",  # 23
    "research-science": "Research Science",  # 65
    "sales-advertising-account-management": "Sales, Advertising, & Account Management",  # 1181
    "software-development": "Software Development",  # 2597
    "solutions-architect": "Solutions Architect",  # 973
    "supply-chain-transportation-management": "Supply Chain/Transportation Management",  # 598
    "systems-quality-security-engineering": "Systems, Quality, & Security Engineering",  # 713
}


class AmazonProvider:
    name = "amazon"
    board_hosts: tuple[str, ...] = (_HOST, "amazon.jobs")
    # A board is a CATEGORY, and a category lives in the QUERY STRING (`?category[]=...`), never
    # in the path -- so no path segment of any amazon.jobs URL names one. `slug_from_path`
    # therefore answers None for every URL, which routes both the board-URL and the posting-URL
    # paste through `slug_help` below instead of letting the default extractor hand
    # `normalize_slug` a locale segment (`en`) and produce a catalog diagnostic about a word the
    # user never typed. The same fact is why `lanes/dereference.py` refuses this provider; its
    # own section there says so.
    slug_help = (
        "an amazon.jobs board is one job category, and a category is a query parameter rather "
        "than a path segment, so no URL names one. Add it as amazon:<category>, e.g. "
        "amazon:software-development"
    )

    @staticmethod
    def slug_from_path(host: str, parts: list[str]) -> str | None:
        return None

    @staticmethod
    def normalize_slug(slug: str) -> str:
        """The lowercased catalog token. Raises ValueError on anything outside `_CATEGORIES` --
        `board_urls._normalize_slug` turns that into UnknownBoardURL so the CLI does not
        traceback.

        The guard is the whole reason the slug is a token. A category the API does not know is
        answered with `hits: 0`, `jobs: []` and `error: null`, so a typo would be watched
        forever as a board that is merely empty today."""
        token = slug.strip().lower()
        if token not in _CATEGORIES:
            raise ValueError(
                f"expected one of the {len(_CATEGORIES)} amazon.jobs job categories, "
                f"got {slug!r}"
            )
        return token

    def board_url(self, slug: str) -> str:
        """Offset 0 == the http_cache key; stable parameter order."""
        return self._page_url(self.normalize_slug(slug), 0, _PAGE_LIMIT)

    def _page_url(self, token: str, offset: int, result_limit: int) -> str:
        query = urlencode(
            [
                ("offset", offset),
                ("result_limit", result_limit),
                ("sort", _SORT),
                ("category[]", _CATEGORIES[token]),
            ],
            quote_via=quote,
        )
        return f"{_SEARCH_URL}?{query}"

    def fetch_board(self, fetcher: Fetcher, request: BoardRequest) -> BoardSnapshot:
        try:
            token = self.normalize_slug(request.slug)
        except ValueError as exc:
            return _failed(request.url, f"invalid amazon slug: {exc}")

        errors: list[str] = []
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        reported_total: int | None = None
        censored: bool | None = None
        observed = None

        for page in range(_MAX_PAGES):
            offset = page * _PAGE_LIMIT
            first = page == 0
            # Offset 0 is request.url (the cache key) verbatim; every later page is the same
            # route with its own `offset`, so a conditional GET is only ever sent for the first.
            url = request.url if first else self._page_url(token, offset, _PAGE_LIMIT)
            try:
                result = fetcher.get(url, validators=request.validators if first else None)
            except FetchFailure as exc:
                if first:
                    return _failed(request.url, str(exc))
                errors.append(f"offset {offset}: {exc}")
                break
            if first:
                if result.not_modified:
                    return BoardSnapshot(
                        status="unchanged", postings=[], url=request.url,
                        observed_validators=None, error=None,
                    )
                observed = result.observed_validators
            payload = _payload(result.content)
            if payload is None:
                if first:
                    return _failed(request.url, "invalid board payload: not a JSON object")
                errors.append(f"offset {offset}: invalid payload")
                break
            # `error` IS CHECKED BEFORE `jobs`, and the order is load-bearing: on a refused
            # request `jobs` is `null` rather than `[]`, so reading it first would report
            # "invalid payload" and throw away the only sentence the server said about why.
            message = _stated_error(payload)
            if message is not None:
                # A refusal on the FIRST page means nothing was read and the board is `failed`.
                # A refusal on a later page is a `partial` -- the same shape jibe gives a page
                # that 500s, and the shape the offset ceiling would take were the server ever to
                # lower it below `_MAX_PAGES`'s bound. Classified by WHICH PAGE, never by
                # matching the message text.
                if first:
                    return _failed(request.url, f"board refused the request: {message}")
                errors.append(f"offset {offset}: {message}")
                break
            listed = payload.get("jobs")
            if not isinstance(listed, list):
                if first:
                    return _failed(request.url, "invalid board payload: missing 'jobs' list")
                errors.append(f"offset {offset}: missing 'jobs' list")
                break
            if first:
                # Offset 0's `hits` is the one reported, so a board that changes size mid-walk
                # does not rewrite its own denominator.
                reported_total, censored = _stated_total(payload)
            page_rows, dropped = _job_rows(listed)
            if dropped:
                # NEVER silent. An entry we cannot read is a posting we cannot key, and dropping
                # it quietly shrinks the listing while `status` stays "complete" -- the one
                # status that authorizes apply_board to close everything it no longer sees.
                errors.append(f"offset {offset}: dropped {dropped} entries that are not objects")
            for row in page_rows:
                identifier = row.get("id_icims")
                if identifier is None:
                    rows.append(row)  # kept so it fails to parse loudly; count_listed_ids skips it
                    continue
                if str(identifier) in seen:
                    continue  # the `sort=recent` re-serve; see the module docstring
                seen.add(str(identifier))
                rows.append(row)
            if len(listed) < _PAGE_LIMIT:
                # THE termination condition, and it is counted off the RAW `jobs` array rather
                # than off `page_rows`: an unreadable entry still occupied a slot on the page, so
                # filtering before the comparison would read a full page as a short one and stop
                # the walk early. NOT `len(rows) < hits` either -- the loop bound must be what
                # the server served, not what it claims to hold (and `hits` is capped anyway).
                break
        else:
            errors.append(
                f"page cap of {_MAX_PAGES} pages reached; listing may be incomplete"
            )

        postings: list[RawPosting] = []
        row_errors: list[str] = []
        for row in rows:
            try:
                postings.append(parse_job(row))
            except Exception as exc:  # per-row isolation: one bad row never fails the board
                row_errors.append(f"job {row.get('id_icims', '?')}: {exc}")

        if row_errors and not postings and rows:
            return _failed(request.url, f"all {len(rows)} jobs failed to parse")
        if row_errors:
            errors.append(
                f"{len(row_errors)} of {len(rows)} jobs failed to parse: "
                + "; ".join(row_errors[:3])
            )
        return BoardSnapshot(
            status="complete" if not errors else "partial",
            postings=postings,
            url=request.url,
            observed_validators=observed,
            error=None if not errors else "; ".join(errors),
            board_reported_total=reported_total,
            # DISTINCT ids across EVERY page, off the raw rows -- before the per-row parse
            # failures above dropped any (D-271). `len(postings)` would make this a
            # parse-failure count while every other paged provider means a listing census by
            # it, and the column is persisted, so the two readings could never be told apart.
            board_enumerated=count_listed_ids(rows, "id_icims"),
            # There is no detail endpoint, so nothing can ever be deferred. Stated rather than
            # left None: None means "not measured", and this is measured at zero by design.
            detail_deferred=0,
            board_total_censored=censored,
        )

    def healthcheck(self, fetcher: Fetcher, slug: str) -> BoardHealth:
        try:
            token = self.normalize_slug(slug)
        except ValueError:
            return BoardHealth.ERROR
        try:
            result = fetcher.get(self._page_url(token, 0, 1))
        except FetchFailure as exc:
            return health_from_failure(exc)
        payload = _payload(result.content)
        if payload is None or _stated_error(payload) is not None:
            return BoardHealth.ERROR
        listed = payload.get("jobs")
        if not isinstance(listed, list):
            return BoardHealth.ERROR
        return BoardHealth.OK if listed else BoardHealth.EMPTY


def _failed(url: str, error: str) -> BoardSnapshot:
    return BoardSnapshot(
        status="failed", postings=[], url=url, observed_validators=None, error=error,
    )


def _payload(content: bytes) -> dict[str, Any] | None:
    """The parsed body iff it is a JSON object, else None. Never raises, and deliberately does
    NOT require a `jobs` list: a refused request answers 200 with `jobs: null` and its reason in
    `error`, which the caller reads first."""
    try:
        obj = json.loads(content)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def _stated_error(payload: dict[str, Any]) -> str | None:
    """The server's own refusal message, or None when it stated none. Every measured refusal
    still answers HTTP 200, so this -- not the status code -- is the page-level failure signal."""
    raw = payload.get("error")
    if raw is None:
        return None
    return str(raw).strip() or None


def _stated_total(payload: dict[str, Any]) -> tuple[int | None, bool | None]:
    """Return (board_total, censored) from `hits`. None means the board stated no total -- never
    0, and `censored` is itself None in that case: with no total there is nothing to have
    censored, so False would be a claim this function cannot support.

    AT THE CAP THE ANSWER IS `(None, True)`, NOT `(10000, True)`. `hits` is capped, so 10000 is
    the board refusing to say how big it is, and persisting it as a total would collapse "the
    board holds 10,000" and "the board holds at least 10,000" into one indistinguishable row.
    Workday's `_uncapped_total` makes the same call for the same reason, and unlike Workday
    there is no second uncapped path to recover from: `facets[]=category` on a category-filtered
    query just echoes `hits` back (measured 19/19 on 2026-09-07), so the flag is the whole
    answer. In practice this cannot fire for a catalog slug -- the largest category held 3,370 --
    which is exactly why category-per-board is the enumeration strategy."""
    raw = payload.get("hits")
    if raw is None or isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None, None
    total = max(0, int(raw))
    if total >= _HITS_CENSOR:
        return None, True
    return total, False


def _job_rows(listed: list[Any]) -> tuple[list[dict[str, Any]], int]:
    """The `jobs` entries that are objects, plus the number that were not. The COUNT is returned
    so the caller can say so out loud rather than shrinking the listing silently."""
    rows = [job for job in listed if isinstance(job, dict)]
    return rows, len(listed) - len(rows)


def parse_job(job: dict[str, Any]) -> RawPosting:
    """One listing row -> RawPosting. Raises for a row that cannot be keyed, titled or linked;
    `fetch_board` isolates the failure to that row.

    `id_icims` is the posting id, not `id`. `id` is a UUID
    (`88d3dd17-0968-4084-af1d-95e161519f1e`); `id_icims` is the number the public posting URL
    carries (`/en/jobs/10530555/...`), so it is the only one an aggregator's deep link could ever
    converge onto. Measured over a full category on 2026-09-07: present and DISTINCT on 2,597 of
    2,597 rows, and equal to the `job_path` id segment on all 2,597.

    NO SALARY FIELDS EXIST. The payload carries no pay key of any kind (checked over 2,597 rows),
    so all four salary scalars keep their NULL defaults -- D19 is structured-only and there is no
    structure here to read.

    `updated_at` IS ALWAYS NULL, and that is not an omission. The only update signal is
    `updated_time`, which is RELATIVE (`"2 days"`, `"10 months"`) rather than a timestamp; it
    could only become a datetime by pinning it to the moment of the fetch, which would rewrite
    itself on every scan. It stays in `raw_json`.
    """
    posting_id = str(job["id_icims"]).strip()
    if not posting_id:
        raise ValueError("empty id_icims")
    title = str(job.get("title") or "").strip()
    if not title:
        raise ValueError("empty title")
    path = str(job.get("job_path") or "").strip()
    if not path.startswith("/"):
        # The row is skipped rather than given an invented URL. `job_path` was present and
        # `/en/jobs/{id_icims}/{title-slug}` on 2,597 of 2,597 rows, so there is no second shape
        # to fall back to, and a URL built from a path that is not one would name a page that
        # does not exist -- or, if it ever carried an absolute URL, an authority we did not check.
        raise ValueError(f"unusable job_path {job.get('job_path')!r}")
    locations = _locations(job)
    return RawPosting(
        provider_posting_id=posting_id,
        title=title,
        url=f"https://{_HOST}{path}",
        locations=locations,
        # `job_family` (Amazon's own hiring taxonomy: "Data Center Operations", "Tech Ops
        # Engineering"), NOT `job_category`. `job_category` is the search facet this board IS,
        # so it is a constant per board and carries nothing; measured over 370 rows in two
        # categories, `job_family` held 33 distinct values and equalled `job_category` 0 times.
        department=str(job.get("job_family") or "").strip() or None,
        remote_policy=_remote_policy(job, locations),
        posted_at=_parse_posted(job.get("posted_date")),
        updated_at=None,
        body_text=_body_text(job),
        raw_json=job,
    )


def _body_text(job: dict[str, Any]) -> str:
    """description, then basic_qualifications, then preferred_qualifications. Separated by
    `<br/>` runs in the live payload, which `html_to_text` turns into line breaks."""
    sections = [html for key in _SECTIONS if (html := str(job.get(key) or "").strip())]
    return html_to_text("\n".join(sections))


def _locations(job: dict[str, Any]) -> list[str]:
    """`normalized_location` when the board sets one, else `city, state, country_code`.

    `normalized_location` ("Seattle, Washington, USA") was non-empty on 770 of 770 probed rows,
    so the fallback is the unmeasured path and is kept only because the shape permits it. `state`
    was blank on 115 of those 770, which is why the parts are filtered rather than joined
    blindly. The `locations` array is NOT read for text: its entries are JSON-encoded STRINGS,
    and one posting carried up to ten of them."""
    name = str(job.get("normalized_location") or "").strip()
    if name:
        return [name]
    parts = [
        value
        for key in ("city", "state", "country_code")
        if (value := str(job.get(key) or "").strip())
    ]
    return [", ".join(parts)] if parts else []


def _remote_policy(job: dict[str, Any], locations: list[str]) -> RemotePolicy:
    """`locations[].type == "VIRTUAL"` read as the structured signal first, then location text.

    THE STRUCTURED FIELD IS THE ONE THAT FIRES, and this is a DEPARTURE from the ticket, which
    said Amazon has no explicit remote flag and that the location text should decide. Measured
    2026-09-07 over 770 rows: the location TEXT said "remote" or "virtual" 0 times, so a
    text-only rule is a rule that can never fire on any Amazon board -- which this repo treats as
    a monitoring failure, not conservatism. Meanwhile each `locations` entry is a JSON-encoded
    string carrying an explicit `"type"`, and over those rows' 1,456 locations it read ONSITE
    1,432 times and VIRTUAL 24. The text rule is kept underneath because it costs one clause and
    a feed that starts spelling remote in `normalized_location` should still be read.

    ONSITE IS DELIBERATELY NOT MAPPED to `onsite`, even though it is the same field. A posting
    carried up to ten locations and the type is PER LOCATION, so a row is only unambiguously
    onsite when every one of its locations says so -- and asserting `onsite` for ~98% of the
    corpus off a value that is also the feed's default for anything unstated is a claim no probe
    here can separate from "the field was not set". `hybrid` has no signal at all."""
    for encoded in job.get("locations") or []:
        if not isinstance(encoded, str):
            continue
        try:
            entry = json.loads(encoded)
        except ValueError:
            continue
        if isinstance(entry, dict) and str(entry.get("type") or "").upper() == _VIRTUAL:
            return "remote"
    return (
        "remote"
        if any(word in loc.casefold() for loc in locations for word in ("remote", "virtual"))
        else "unknown"
    )


def _parse_posted(value: Any) -> datetime | None:
    """`posted_date` is a HUMAN STRING, and a DOUBLE SPACE before a single-digit day is normal:
    `"September  4, 2026"` and `"October 12, 2026"` both occur (819 of 2,597 probed rows carried
    the double space). Split on whitespace after dropping the comma, so both spellings parse and
    neither is special-cased. A value that will not parse yields None -- the row keeps
    `posted_at = NULL` rather than failing."""
    if not isinstance(value, str):
        return None
    parts = value.replace(",", " ").split()
    if len(parts) != 3:
        return None
    month = _MONTHS.get(parts[0].casefold())
    if month is None:
        return None
    try:
        return datetime(int(parts[2]), month, int(parts[1]))
    except ValueError:
        return None
