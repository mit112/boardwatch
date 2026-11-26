"""TikTok provider: the lifeattiktok.com careers search API (live-verified 2026-11-25).

`POST https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts` with a JSON body
`{"keyword": "", "limit": k, "offset": n, ...}` and ONE required header, `website-path: tiktok`,
which names the tenant site the API answers for. Unauthenticated: no cookie, no token. Without
the header the API answers HTTP 400 with the plain-text body `invalid request`; `Origin` and
`Referer` are not needed (both measured 2026-11-25, one request each).

Shape: `{"code": 0, "message": "ok", "error": null, "data": {"job_post_list": [ {...} ],
"count": N, "BaseResp": {...}}}`. `count` is the board's stated size (4,141 worldwide on
2026-11-25).

BODIES ARE INLINE AND THERE IS NO DETAIL ENDPOINT. `description` and `requirement` are full
plain text on the listing row, so `detail_deferred` is always 0. The whole board is five
requests at the page size below.

MEASURED LIMITS (2026-11-25):

1. `limit` 1, 200 and 1000 were all served in full (1000 rows from one request), so the page
   size is pinned at 1000, the largest value measured. A larger one was not tried.
2. An offset past the tail serves a short page (offset 4,139, limit 5: 2 rows), which is the
   walk's end.
3. A search that matches nothing answers `code: 0`, `count: 0` and an empty list, so an empty
   board is reachable and is reported as one, never as a failure.
4. The listing carries NO posting date: every date-like key under `job_post_info` was null on
   every row read, so `posted_at` is NULL by measurement, not by omission.

THE SLUG IS THE TENANT SITE, and the catalog is closed. `website-path` is the API's own tenant
key; only `tiktok` was measured, and `bytedance` answered non-JSON on both this host and
`api.joinbytedance.com`, so it is NOT a slug here. An out-of-catalog token is a failure, never a
new board: an unknown tenant is a request this API was never seen to answer, and a board that
reads empty is the one status that would close every posting it holds.

PAGINATION IS NOT ASSUMED STABLE. No sort parameter was found, so rows are deduped by `id`
across pages and a walk that collects fewer distinct ids than `count` is `partial`.
"""

from __future__ import annotations

import json
from typing import Any

from boardwatch.core.models import BoardRequest, BoardSnapshot, RawPosting
from boardwatch.core.politeness import Fetcher, FetchFailure
from boardwatch.providers.base import BoardHealth, count_listed_ids, health_from_failure

_API_HOST = "api.lifeattiktok.com"
_SEARCH_URL = f"https://{_API_HOST}/api/v1/public/supplier/search/job/posts"
_SITE_HOST = "lifeattiktok.com"
_PAGE_LIMIT = 1000  # the largest page size measured to be served in full
# 20 x 1000 = 20,000 rows, about five times the measured board. The real termination is always a
# short page; this bound only stops a server that keeps serving full pages forever.
_MAX_PAGES = 20
# Tenant site -> the employer it is. Closed: see the module docstring.
_SITES: dict[str, str] = {"tiktok": "TikTok"}
# Paste host -> tenant site, so a pasted careers URL names its board.
_HOST_SITE: dict[str, str] = {_SITE_HOST: "tiktok", f"www.{_SITE_HOST}": "tiktok"}


class TikTokProvider:
    name = "tiktok"
    board_hosts: tuple[str, ...] = tuple(_HOST_SITE)
    slug_help = "a TikTok careers board is one tenant site; add it as tiktok:tiktok"

    @staticmethod
    def employer_name_from_slug(slug: str) -> str | None:
        """The employer the tenant site belongs to. The slug is a site token, not an employer
        spelling, so the default rule (the slug is the employer) would name it `tiktok`."""
        return _SITES.get(slug.strip().lower())

    @staticmethod
    def slug_from_path(host: str, parts: list[str]) -> str | None:
        """Every page of a careers site belongs to its one tenant, whatever the path."""
        return _HOST_SITE.get(host.lower())

    @staticmethod
    def normalize_slug(slug: str) -> str:
        """The lowercased site token. Raises ValueError outside `_SITES`, which
        `board_urls._normalize_slug` turns into UnknownBoardURL."""
        token = slug.strip().lower()
        if token not in _SITES:
            raise ValueError(f"expected one of {', '.join(sorted(_SITES))}, got {slug!r}")
        return token

    def board_url(self, slug: str) -> str:
        """The http_cache key. Every request is a POST to `_SEARCH_URL`; the site lives in a
        header, so it is carried in a fragment, which is never sent, to keep one key per board."""
        return f"{_SEARCH_URL}#site={self.normalize_slug(slug)}"

    def fetch_board(self, fetcher: Fetcher, request: BoardRequest) -> BoardSnapshot:
        try:
            site = self.normalize_slug(request.slug)
        except ValueError as exc:
            return _failed(request.url, f"invalid tiktok slug: {exc}")

        errors: list[str] = []
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        idless = 0
        reported_total: int | None = None

        for page in range(_MAX_PAGES):
            offset = page * _PAGE_LIMIT
            first = page == 0
            try:
                result = fetcher.post_json(
                    _SEARCH_URL, _body(offset, _PAGE_LIMIT), headers={"website-path": site}
                )
            except FetchFailure as exc:
                if first:
                    return _failed(request.url, str(exc))
                errors.append(f"offset {offset}: {exc}")
                break
            data, message = _data(result.content)
            if data is None:
                # A refusal on the FIRST page means nothing was read; on a later page it is a
                # `partial`. Classified by which page, never by the message text.
                if first:
                    return _failed(request.url, f"board refused the request: {message}")
                errors.append(f"offset {offset}: {message}")
                break
            listed = data.get("job_post_list")
            if not isinstance(listed, list):
                if first:
                    return _failed(request.url, "invalid board payload: missing 'job_post_list'")
                errors.append(f"offset {offset}: missing 'job_post_list'")
                break
            if first:
                reported_total = _stated_total(data)
            page_rows = [job for job in listed if isinstance(job, dict)]
            if len(page_rows) < len(listed):
                # Never silent: an entry we cannot read is a posting we cannot key, and a
                # quietly shorter listing under `complete` would close it.
                errors.append(
                    f"offset {offset}: dropped {len(listed) - len(page_rows)} entries "
                    "that are not objects"
                )
            for row in page_rows:
                identifier = str(row.get("id") or "").strip()
                if not identifier:
                    idless += 1
                    continue
                if identifier in seen:
                    continue
                seen.add(identifier)
                rows.append(row)
            if len(listed) < _PAGE_LIMIT:
                # Counted off the RAW list, so an unreadable entry still fills its slot.
                break
        else:
            errors.append(f"page cap of {_MAX_PAGES} pages reached; listing may be incomplete")

        enumerated = count_listed_ids(rows, "id")
        if idless:
            errors.append(f"skipped {idless} rows with no id")
        if reported_total is not None and enumerated < reported_total:
            # A short page is not proof the board ended; `complete` would close the rest.
            errors.append(
                f"incomplete listing: collected {enumerated} of {reported_total} postings; "
                "treating as partial so unseen postings are not closed"
            )

        postings: list[RawPosting] = []
        row_errors: list[str] = []
        for row in rows:
            try:
                postings.append(parse_job(row))
            except Exception as exc:  # per-row isolation: one bad row never fails the board
                row_errors.append(f"job {row.get('id', '?')}: {exc}")
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
            observed_validators=None,
            error=None if not errors else "; ".join(errors),
            board_reported_total=reported_total,
            board_enumerated=enumerated,
            # No detail endpoint, so nothing can be deferred: measured zero, not unmeasured.
            detail_deferred=0,
        )

    def healthcheck(self, fetcher: Fetcher, slug: str) -> BoardHealth:
        try:
            site = self.normalize_slug(slug)
        except ValueError:
            return BoardHealth.ERROR
        try:
            result = fetcher.post_json(_SEARCH_URL, _body(0, 1), headers={"website-path": site})
        except FetchFailure as exc:
            return health_from_failure(exc)
        data, _message = _data(result.content)
        listed = data.get("job_post_list") if data is not None else None
        if not isinstance(listed, list):
            return BoardHealth.ERROR
        return BoardHealth.OK if listed else BoardHealth.EMPTY


def _body(offset: int, limit: int) -> dict[str, Any]:
    """The search the careers site itself sends for an unfiltered listing."""
    return {
        "recruitment_id_list": [], "job_category_id_list": [], "subject_id_list": [],
        "location_code_list": [], "keyword": "", "limit": limit, "offset": offset,
    }


def _failed(url: str, error: str) -> BoardSnapshot:
    return BoardSnapshot(
        status="failed", postings=[], url=url, observed_validators=None, error=error,
    )


def _data(content: bytes) -> tuple[dict[str, Any] | None, str]:
    """(`data`, "") for an accepted answer, else (None, the reason). An answer is accepted only
    when it is a JSON object whose `code` is 0 and whose `data` is an object. Never raises."""
    try:
        payload = json.loads(content)
    except ValueError:
        return None, "not JSON"
    if not isinstance(payload, dict):
        return None, "not a JSON object"
    code = payload.get("code")
    if code != 0 or isinstance(code, bool):
        return None, f"code {code!r}: {str(payload.get('message') or '').strip() or 'no message'}"
    data = payload.get("data")
    if not isinstance(data, dict):
        return None, "missing 'data' object"
    return data, ""


def _stated_total(data: dict[str, Any]) -> int | None:
    """`count`, or None when the board states none (never 0 for an absent value)."""
    raw = data.get("count")
    if raw is None or isinstance(raw, bool) or not isinstance(raw, int):
        return None
    return max(0, raw)


def parse_job(job: dict[str, Any]) -> RawPosting:
    """One listing row -> RawPosting. Raises for a row that cannot be keyed or titled;
    `fetch_board` isolates the failure to that row.

    `id` is the posting id the public URL carries (`lifeattiktok.com/search/{id}`, the form the
    store's application links already hold); `code` (`A15293`) is a requisition code and stays in
    `raw_json`. No salary keys carry values (`job_post_info.min_salary` and friends were null on
    every row read), so the salary scalars keep their NULL defaults.
    """
    posting_id = str(job["id"]).strip()
    if not posting_id:
        raise ValueError("empty id")
    title = str(job.get("title") or "").strip()
    if not title:
        raise ValueError("empty title")
    category = job.get("job_category")
    department = (
        str(category.get("en_name") or "").strip() or None if isinstance(category, dict) else None
    )
    return RawPosting(
        provider_posting_id=posting_id,
        title=title,
        url=f"https://{_SITE_HOST}/search/{posting_id}",
        locations=_locations(job),
        department=department,
        remote_policy="unknown",
        posted_at=None,
        updated_at=None,
        body_text=_body_text(job),
        raw_json=job,
    )


def _body_text(job: dict[str, Any]) -> str:
    """`description`, then `requirement` (the qualifications), as the careers page shows them."""
    sections = [text for key in ("description", "requirement")
                if (text := str(job.get(key) or "").strip())]
    return "\n\n".join(sections)


def _locations(job: dict[str, Any]) -> list[str]:
    """`city_info` is a city -> state -> country chain of `en_name`s ("Seattle", "Washington",
    "United States of America"), joined most specific first. A link with no name is skipped, so
    a city without a state still reads "Singapore, Singapore"."""
    names: list[str] = []
    node = job.get("city_info")
    depth = 0
    while isinstance(node, dict) and depth < 8:  # a bounded walk: the chain is three deep
        name = str(node.get("en_name") or "").strip()
        if name:
            names.append(name)
        node = node.get("parent")
        depth += 1
    return [", ".join(names)] if names else []
