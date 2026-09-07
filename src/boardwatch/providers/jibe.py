"""Jibe provider: the iCIMS "Career Sites" front end (live-verified 2026-09-06).

An employer running Jibe serves its OWN careers host -- careers.acme.test, jobs.acme.test --
and that host exposes a public listing API at `GET /api/jobs?page={n}&limit={k}`. The
identity is therefore the HOST itself, not a tenant token issued by a vendor domain, which is
what makes this the first provider that can declare neither an exact paste host nor a host
suffix. See `custom_domain_slug` below.

Shape: `{"jobs": [{"data": {...}}], "totalCount": N, "count": N, "locations", "filter", ...}`.
Each posting's fields live one level down under `data`; that dict is what `raw_json` keeps.

MEASURED PAGINATION. `limit` maxes at exactly 100 -- 101, 150 and 200 all return HTTP 422
with `{"data": {"error": "An unexpected error occurred"}}`, a hard error rather than a silent
clamp, so the page size is PINNED and never negotiated. `page` is 1-based, and paging past the
last page answers HTTP 200 with an empty `jobs` array and a still-correct `totalCount` -- it
neither 4xx's nor wraps to page 1. Termination is on a SHORT PAGE, with `_MAX_PAGES` as a
backstop; `totalCount` is reported, never used as the loop bound.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from boardwatch.core.clock import to_naive_utc
from boardwatch.core.html_text import html_to_text
from boardwatch.core.models import BoardRequest, BoardSnapshot, RawPosting, RemotePolicy
from boardwatch.core.politeness import Fetcher, FetchFailure
from boardwatch.providers.base import (
    BoardHealth,
    count_listed_ids,
    employer_label_from_host,
    health_from_failure,
)

_PAGE_LIMIT = 100  # HARD server maximum: limit=101 returns HTTP 422, it is not clamped
_MAX_PAGES = 200  # backstop only (200 x 100 = 20,000); normal termination is a short page
# Anything that would let the slug be reinterpreted as a URL with a different authority,
# path or query than the host it claims to be.
_HOST_FORBIDDEN = frozenset(":@?#/\\%[]")
_SECTIONS = ("description", "qualifications", "responsibilities")


class JibeProvider:
    name = "jibe"
    # A Jibe board lives on the EMPLOYER'S OWN hostname, so there is neither a finite paste-host
    # list nor a shared vendor suffix to key one off -- careers.amd.com, jobs.statefarm.com and
    # careers.jhuapl.edu have nothing in common but the `/api/jobs` route. Both host maps are
    # therefore empty ON PURPOSE, and this attribute is what says so: `board_hosts = ()` alone is
    # indistinguishable from a provider whose hosts nobody got round to declaring, which is
    # exactly what `test_each_provider_declares_public_board_hosts` exists to catch.
    board_hosts: tuple[str, ...] = ()
    custom_domain_slug = True

    @staticmethod
    def employer_name_from_slug(slug: str) -> str | None:
        """The employer's own token out of the careers host (T74). No vendor suffix: every Jibe
        board sits on the employer's own domain, which is why `board_hosts` is empty."""
        try:
            host = JibeProvider.normalize_slug(slug)
        except ValueError:
            return None
        return employer_label_from_host(host)

    @staticmethod
    def normalize_slug(slug: str) -> str:
        """The careers host, lowercased. Raises ValueError on anything that is not one --
        `board_urls._normalize_slug` turns that into UnknownBoardURL so the CLI does not
        traceback. The guard is load-bearing rather than cosmetic: `board_url` interpolates
        this straight into a URL, so a slug carrying `@` or `?` would redirect every fetch to
        an authority the stored slug does not name."""
        host = slug.strip().lower().removesuffix(".")
        if not host or "." not in host:
            raise ValueError(f"expected a careers hostname, got {slug!r}")
        if any(c.isspace() or ord(c) < 32 for c in host):
            raise ValueError(f"host {host!r} contains whitespace or a control character")
        if any(c in _HOST_FORBIDDEN for c in host):
            raise ValueError(f"host {host!r} contains a forbidden character")
        return host

    def board_url(self, slug: str) -> str:
        """Page 1 == the http_cache key; stable parameter order."""
        return f"https://{self.normalize_slug(slug)}/api/jobs?page=1&limit={_PAGE_LIMIT}"

    def _page_url(self, host: str, page: int) -> str:
        return f"https://{host}/api/jobs?page={page}&limit={_PAGE_LIMIT}"

    def fetch_board(self, fetcher: Fetcher, request: BoardRequest) -> BoardSnapshot:
        try:
            host = self.normalize_slug(request.slug)
        except ValueError as exc:
            return _failed(request.url, f"invalid jibe slug: {exc}")

        errors: list[str] = []
        rows: list[dict[str, Any]] = []
        reported_total: int | None = None
        observed = None

        for number in range(1, _MAX_PAGES + 1):
            first = number == 1
            # Page 1 is request.url (the cache key) verbatim; every later page is the same
            # route with its own `page`, so a conditional GET is only ever sent for page 1.
            url = request.url if first else self._page_url(host, number)
            try:
                page = fetcher.get(url, validators=request.validators if first else None)
            except FetchFailure as exc:
                if first:
                    return _failed(request.url, str(exc))
                errors.append(f"page {number}: {exc}")
                break
            if first:
                if page.not_modified:
                    return BoardSnapshot(
                        status="unchanged", postings=[], url=request.url,
                        observed_validators=None, error=None,
                    )
                observed = page.observed_validators
            payload = _payload(page.content)
            if payload is None:
                if first:
                    return _failed(request.url, "invalid board payload: missing 'jobs' list")
                errors.append(f"page {number}: invalid payload")
                break
            if first:
                # `totalCount` is stated on every page; page 1's is the one that is reported,
                # so a board that changes size mid-walk does not rewrite its own denominator.
                reported_total = _reported_total(payload)
            page_rows, dropped = _data_rows(payload)
            if dropped:
                # NEVER silent. An entry we cannot read is a posting we cannot key, and
                # dropping it quietly shrinks the listing while `status` stays "complete" --
                # the one status that authorizes apply_board to close everything it no longer
                # sees (the same reason workday._collect counts its own drops).
                errors.append(f"page {number}: dropped {dropped} entries with no 'data' object")
            rows.extend(page_rows)
            if len(page_rows) < _PAGE_LIMIT:
                # THE termination condition. NOT `len(rows) < totalCount`: the loop bound must
                # be what the server actually served, not what it claims to hold.
                break
        else:
            errors.append(
                f"page cap of {_MAX_PAGES} pages reached; listing may be incomplete"
            )

        postings: list[RawPosting] = []
        row_errors: list[str] = []
        for row in rows:
            try:
                postings.append(parse_job(row, host))
            except Exception as exc:  # per-row isolation: one bad row never fails the board
                row_errors.append(f"job {row.get('req_id', '?')}: {exc}")

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
            # DISTINCT req_ids across EVERY page, off the raw rows -- before the per-row
            # parse failures above dropped any (D-271). `len(postings)` would make this a
            # parse-failure count while the paged providers mean a listing census by it, and
            # the column is persisted, so the two readings could never be told apart again.
            board_enumerated=count_listed_ids(rows, "req_id"),
            detail_deferred=0,
        )

    def healthcheck(self, fetcher: Fetcher, slug: str) -> BoardHealth:
        try:
            host = self.normalize_slug(slug)
        except ValueError:
            return BoardHealth.ERROR
        try:
            result = fetcher.get(f"https://{host}/api/jobs?page=1&limit=1")
        except FetchFailure as exc:
            return health_from_failure(exc)
        payload = _payload(result.content)
        if payload is None:
            return BoardHealth.ERROR
        return BoardHealth.OK if payload["jobs"] else BoardHealth.EMPTY


def _failed(url: str, error: str) -> BoardSnapshot:
    return BoardSnapshot(
        status="failed", postings=[], url=url, observed_validators=None, error=error,
    )


def _payload(content: bytes) -> dict[str, Any] | None:
    """The parsed page iff it is an object carrying a `jobs` LIST, else None. Never raises: a
    live careers host answers 200 with an Angular HTML shell on a path it does not recognize."""
    try:
        obj = json.loads(content)
    except ValueError:
        return None
    if not isinstance(obj, dict) or not isinstance(obj.get("jobs"), list):
        return None
    return obj


def _data_rows(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    """The per-job `data` dicts, plus the number of `jobs` entries that carried none.

    An entry with no `data` object is dropped rather than counted, which keeps it out of the
    enumerated count too -- a row we cannot key is a posting we cannot fetch, dedupe or close
    (see `count_listed_ids`). The COUNT is returned so the caller can say so out loud."""
    rows = [
        job["data"]
        for job in payload["jobs"]
        if isinstance(job, dict) and isinstance(job.get("data"), dict)
    ]
    return rows, len(payload["jobs"]) - len(rows)


def _reported_total(payload: dict[str, Any]) -> int | None:
    """`totalCount`, the board's own stated size. None means the board stated nothing --
    NEVER backfilled from the row count, which would make coverage 100% by arithmetic."""
    raw = payload.get("totalCount")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return max(0, int(raw))


def parse_job(data: dict[str, Any], host: str) -> RawPosting:
    posting_id = str(data["req_id"]).strip()
    if not posting_id:
        raise ValueError("empty req_id")
    title = str(data.get("title") or "").strip()
    if not title:
        raise ValueError("empty title")
    locations = _locations(data)
    department = str(data.get("department") or "").strip() or None
    return RawPosting(
        provider_posting_id=posting_id,
        title=title,
        url=_posting_url(data, host, posting_id),
        locations=locations,
        department=department,
        remote_policy=_remote_policy(data.get("location_type"), locations),
        posted_at=_parse_dt(data.get("posted_date")),
        updated_at=_parse_dt(data.get("update_date")),
        body_text=_body_text(data),
        raw_json=data,
        **_salary(data),
    )


def _body_text(data: dict[str, Any]) -> str:
    """description, then qualifications, then responsibilities. Blank sections are skipped
    rather than contributing an empty block -- two of the three are routinely `""` live."""
    sections = [html for key in _SECTIONS if (html := str(data.get(key) or "").strip())]
    return html_to_text("\n".join(sections))


def _locations(data: dict[str, Any]) -> list[str]:
    """`location_name` when the board sets one, else `city, state, country`. Live payloads
    carry `full_location`/`short_location` too, but both are derived from the same three
    fields, so reading them would add a third spelling of one fact."""
    name = str(data.get("location_name") or "").strip()
    if name:
        return [name]
    parts = [
        value
        for key in ("city", "state", "country")
        if (value := str(data.get(key) or "").strip())
    ]
    return [", ".join(parts)] if parts else []


def _remote_policy(location_type: Any, locations: list[str]) -> RemotePolicy:
    """`location_type` read as a structured signal first, then the location text.

    MEASURED CAVEAT: `location_type` was `"LAT_LNG"` on 228 of 228 postings across four live
    tenants -- it is a GEOCODING MODE, and no probed board used it to say "remote". The rule is
    kept because the field is the only structured candidate the payload has, but the location
    text is what actually fires today. Nothing here infers `hybrid` or `onsite`: the payload
    carries no signal for either, and guessing one would be mining, not reading."""
    if isinstance(location_type, str) and "remote" in location_type.casefold():
        return "remote"
    return "remote" if any("remote" in loc.casefold() for loc in locations) else "unknown"


def _posting_url(data: dict[str, Any], host: str, posting_id: str) -> str:
    """`apply_url` when the board points at ITSELF, else `https://{host}/jobs/{req_id}`.

    The fallback is the path taken in practice and it is MEASURED, not guessed. On all four
    probed tenants `apply_url` pointed at a different host entirely
    (`{site}-{tenant}.icims.com/jobs/{req_id}/login`), and the canonical on-site path varies by
    tenant (`/careers-home/jobs/{id}`, `/main/jobs/{id}`, `/jobs/{id}`). `/jobs/{id}` resolved
    on every one: 200 where it is canonical, 302 to the tenant's own path where it is not."""
    apply_url = str(data.get("apply_url") or "").strip()
    if apply_url and (urlparse(apply_url).hostname or "").lower() == host:
        return apply_url
    return f"https://{host}/jobs/{posting_id}"


def _salary(data: dict[str, Any]) -> dict[str, Any]:
    """D19 structured-only: the two numeric fields, or nothing.

    ZERO IS ABSENT, NOT $0. Every probed tenant reported `salary_min_value` and
    `salary_max_value` as `0` or `null` on every posting, so treating 0 as a figure would write
    a `$0-$0` range onto entire boards. Currency and period are left NULL because the payload
    states NEITHER anywhere -- one tenant carried a display string in `tags2`/`tags3`
    (`"INR ₹2,186,520.00/Yr."`) and D19 forbids mining it."""
    minimum = _positive(data.get("salary_min_value"))
    maximum = _positive(data.get("salary_max_value"))
    if minimum is None and maximum is None:
        return {
            "salary_min": None, "salary_max": None,
            "salary_currency": None, "salary_period": None,
        }
    return {
        "salary_min": minimum, "salary_max": maximum,
        "salary_currency": None, "salary_period": None,
    }


def _positive(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if value > 0 else None


def _parse_dt(value: Any) -> datetime | None:
    """`posted_date` / `update_date` are ISO 8601 with a `+0000` offset."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return to_naive_utc(datetime.fromisoformat(value.strip().replace("Z", "+00:00")))
    except ValueError:
        return None
