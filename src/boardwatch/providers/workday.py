"""Workday provider (live-verified 2026-08-04).

The FIRST provider whose board identity is not a single opaque token. A Workday board is a
{host, tenant, site} TRIPLE, carried as the composite slug "{host}/{tenant}/{site}". That
keeps UNIQUE(provider, slug) exactly correct — and load-bearing, because Sony serves three
disjoint sites from one host with one tenant — and needs no migration. The triple never
leaves this module.

Five measured properties drive this design. Each has a regression test; none should be
"simplified" away.

1. POST ONLY. GET .../jobs returns 400 with or without query parameters. There is no GET
   form, which is why Fetcher grew post_json. No HTML bootstrap, no cookies and no CSRF
   token are needed: a bare POST with a clean cookie jar returns 200 with real data
   (userAuthenticated: false). job-apps' X-CALYPSO-CSRF-TOKEN path was reimplemented and
   tested against every failing tenant and rescued ZERO of them — those hosts are gated or
   retired (Walmart is 410 Gone), not CSRF-protected.

2. THREE PAGINATION TRAPS. `limit` max is exactly 20 (limit=21 -> HTTP 400, not a silent
   clamp). `total` and `facets` are populated ONLY at offset=0. `total` is capped at 2000
   while offset >= 2000 WRAPS to page 1 byte-identically, so `while offset < total` never
   terminates on a large board. Termination is therefore on a SHORT PAGE, with _MAX_PAGES as
   a hard backstop. `total` is used only for an informational completeness note.

3. NO CONDITIONAL FETCH. The list POST sends no ETag and no Last-Modified and answers
   cache-control: no-store, no-cache, so observed_validators is always None, nothing is
   persisted by the D22 path, no If-None-Match is ever sent, and `unchanged` is unreachable
   against the live service. That is upstream behavior, not a defect. The 304 branch is kept
   for symmetry and covered by a mocked 304.

4. timeType IS NOT AN INTERN SIGNAL. The detail payload's timeType reads "Full time" on a
   real PhD-intern requisition; it is full-time vs part-time and is orthogonal to intern
   status. The real signal is the offset=0 facets block's workerSubType. Its ids are
   tenant-specific Workday WIDs, so buckets are matched on `descriptor` — hardcoding a WID
   would silently break every other tenant. Both fields are captured into raw_json because
   backfilling them means re-scanning every Workday board; nothing reads them yet.
   Because detail fetches skip known postings, a posting already in the DB does not gain
   these fields until it is re-detailed. That is the same incremental fill as body_text, not
   a Workday-specific gap.

5. bulletFields IS VARIABLE-LENGTH (Sony returns 3: req id, country, legal entity), so
   bulletFields[0] is NOT universally the requisition id. The id comes from externalPath.

Detail fetches are bounded and skip known postings (the SmartRecruiters pattern), so
snapshot.postings is the newly-fetched subset and snapshot.listed_ids carries the FULL live
inventory — otherwise apply_board would close every known-but-unrefreshed posting. The
consequence is that body_text and the captured employment-type fields fill in incrementally
across scans. Salary is never mined (D19).

fetch_board pages the full board (trap 2 above), then issues one bounded facet-filtered query
per matched workerSubType bucket (trap 4), then fetches details for the unseen postings only,
within the budget. A failed facet query is an `errors` note, never a failed board.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from boardwatch.core.clock import to_naive_utc
from boardwatch.core.html_text import html_to_text
from boardwatch.core.models import BoardRequest, BoardSnapshot, RawPosting, RemotePolicy
from boardwatch.core.politeness import Fetcher, FetchFailure
from boardwatch.providers.base import BoardHealth, health_from_failure

_HOST_SUFFIX = ".myworkdayjobs.com"
_PAGE_LIMIT = 20  # HARD server maximum: limit=21 returns HTTP 400, it is not clamped
# 150 pages x 20 = 3000, comfortably past the server's own 2000 `total` cap. A backstop
# only: normal termination is a short page (trap 2 above).
_MAX_PAGES = 150
# Anything that would make the composite slug reinterpretable as a URL with a different
# authority, path or query than the triple says.
_HOST_FORBIDDEN = frozenset(":@?#\\%[]")
# Path segments Workday puts around the site slug in a public career-site URL.
_CHROME_SEGMENTS = frozenset({"wday", "cxs", "job", "jobs", "login", "details"})
_SLUG_FORM = "expected host/tenant/site, e.g. acme.wd5.myworkdayjobs.com/acme/AcmeCareers"
# workerSubType descriptors worth one extra paged query each. Facet ids are tenant-specific
# Workday WIDs, so buckets are matched on the human-readable DESCRIPTOR — hardcoding a WID
# would silently break every other tenant. Deliberately conservative: an unmatched
# vocabulary costs zero extra requests.
_SUBTYPE_KEYWORDS = (
    "intern", "co-op", "coop", "new college graduate", "new grad", "apprentice", "trainee",
)
_FACET_MAX_PAGES = 20  # 400 postings per bucket; intern/new-grad buckets are small


def split_slug(slug: str) -> tuple[str, str, str]:
    """(host, tenant, site) from the composite slug, canonicalized: host and tenant
    lowercased, SITE CASE PRESERVED (site slugs are case-sensitive live —
    NVIDIAExternalCareerSite, External_Career_Site and external_experienced are all real).
    Raises ValueError on anything that is not a valid triple; board_urls._normalize_slug
    converts that to UnknownBoardURL so the CLI does not traceback."""
    parts = slug.strip().split("/")
    if len(parts) != 3 or not all(p.strip() for p in parts):
        raise ValueError(_SLUG_FORM)
    host = _validated_host(parts[0].strip().lower())
    tenant, site = parts[1].strip().lower(), parts[2].strip()
    for label, value in (("tenant", tenant), ("site", site)):
        if any(c.isspace() or ord(c) < 32 for c in value):
            raise ValueError(f"{label} {value!r} contains whitespace or a control character")
    return host, tenant, site


def _validated_host(host: str) -> str:
    if any(c.isspace() or ord(c) < 32 for c in host):
        raise ValueError(f"host {host!r} contains whitespace or a control character")
    if any(c in _HOST_FORBIDDEN for c in host):
        raise ValueError(f"host {host!r} contains a forbidden character")
    # endswith on a LEADING-DOT suffix is the label boundary: notmyworkdayjobs.com must not
    # match, and the length test requires at least one tenant label before the suffix.
    if not host.endswith(_HOST_SUFFIX) or len(host) <= len(_HOST_SUFFIX):
        raise ValueError(f"host {host!r} is not a *{_HOST_SUFFIX} hostname")
    return host


def _search_body(
    offset: int, applied_facets: dict[str, list[str]] | None = None
) -> dict[str, Any]:
    """The CXS search body. `limit` is PINNED at _PAGE_LIMIT: 21 returns HTTP 400."""
    return {
        "appliedFacets": applied_facets or {},
        "limit": _PAGE_LIMIT,
        "offset": offset,
        "searchText": "",
    }


def _payload(content: bytes) -> dict[str, Any] | None:
    """Parsed JSON iff it is an object, else None. Never raises — a live Workday host can
    answer 200 with an HTML maintenance page (observed on Walmart)."""
    try:
        obj = json.loads(content)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def _postings_list(content: bytes) -> list[dict[str, Any]] | None:
    """The page's jobPostings rows, or None if the payload is not a usable page."""
    payload = _payload(content)
    if payload is None or not isinstance(payload.get("jobPostings"), list):
        return None
    return [row for row in payload["jobPostings"] if isinstance(row, dict)]


def _worker_subtype_buckets(facets: list[Any]) -> list[tuple[str, str]]:
    """(descriptor, facet id) for the intern/new-grad-shaped workerSubType buckets."""
    out: list[tuple[str, str]] = []
    for group in facets:
        if not isinstance(group, dict) or group.get("facetParameter") != "workerSubType":
            continue
        values = group.get("values")
        for value in values if isinstance(values, list) else ():
            if not isinstance(value, dict):
                continue
            descriptor = str(value.get("descriptor") or "")
            facet_id = str(value.get("id") or "")
            lowered = descriptor.casefold()
            if descriptor and facet_id and any(k in lowered for k in _SUBTYPE_KEYWORDS):
                out.append((descriptor, facet_id))
    return out


def _subtypes_by_path(
    fetcher: Fetcher, url: str, facets: list[Any], errors: list[str]
) -> dict[str, str]:
    """externalPath -> workerSubType descriptor, from one paged facet-filtered query per
    matched bucket. Bounded and cheap: NVIDIA's 11 interns + 80 new grads is ~6 requests."""
    out: dict[str, str] = {}
    for descriptor, facet_id in _worker_subtype_buckets(facets):
        for page_index in range(_FACET_MAX_PAGES):
            body = _search_body(page_index * _PAGE_LIMIT, {"workerSubType": [facet_id]})
            try:
                page = fetcher.post_json(url, body)
            except FetchFailure as exc:
                errors.append(f"workerSubType {descriptor!r}: {exc}")
                break
            rows = _postings_list(page.content)
            if rows is None:
                errors.append(f"workerSubType {descriptor!r}: invalid payload")
                break
            for row in rows:
                path = str(row.get("externalPath") or "")
                if path:
                    out[path] = descriptor
            if len(rows) < _PAGE_LIMIT:
                break
    return out


def _failed(url: str, error: str) -> BoardSnapshot:
    return BoardSnapshot(
        status="failed", postings=[], url=url, observed_validators=None, error=error,
    )


class WorkdayProvider:
    name = "workday"
    # Workday hostnames are UNBOUNDED ({tenant}.wd{N}.myworkdayjobs.com; wd1..wd12 observed),
    # so identity is a SUFFIX and there are no exact paste hosts.
    board_hosts: tuple[str, ...] = ()
    board_host_suffixes: tuple[str, ...] = (_HOST_SUFFIX,)
    slug_help = (
        "a Workday board needs the career-site path: paste "
        "tenant.wdN.myworkdayjobs.com/<CareerSite> or use "
        "workday:<host>/<tenant>/<CareerSite>."
    )

    @staticmethod
    def normalize_slug(slug: str) -> str:
        return "/".join(split_slug(slug))

    @staticmethod
    def slug_from_path(host: str, parts: list[str]) -> str | None:
        """Composite slug from a pasted career-site URL. The tenant is the first host label;
        the site is the first path segment that is neither a locale (en-US) nor Workday
        chrome (wday/job/jobs/login/...)."""
        tenant = host.split(".", 1)[0]
        for part in parts:
            if part.lower() in _CHROME_SEGMENTS:
                continue
            if len(part) == 5 and part[2] == "-":  # locale segment, e.g. en-US
                continue
            return f"{host}/{tenant}/{part}"
        return None

    def board_url(self, slug: str) -> str:
        """Canonical fetch URL == the http_cache key. Raises ValueError on a malformed
        stored slug; scan/coordinator.py and scan/health.py guard the call."""
        host, tenant, site = split_slug(slug)
        return f"https://{host}/wday/cxs/{tenant}/{site}/jobs"

    def _detail_url(self, host: str, tenant: str, site: str, external_path: str) -> str:
        return f"https://{host}/wday/cxs/{tenant}/{site}{external_path}"

    def fetch_board(self, fetcher: Fetcher, request: BoardRequest) -> BoardSnapshot:
        try:
            host, tenant, site = split_slug(request.slug)
        except ValueError as exc:
            return _failed(request.url, f"invalid workday slug: {exc}")

        errors: list[str] = []
        listed: list[dict[str, Any]] = []
        seen_paths: set[str] = set()
        total: int | None = None
        # Declared BEFORE the loop on purpose: the loop body's `payload` local is only bound
        # if the loop ran AND took the page_index == 0 branch, and the empty-list default is
        # exactly the "tenant serves no facets block" case.
        facets: list[Any] = []
        observed = None
        capped = True

        for page_index in range(_MAX_PAGES):
            offset = page_index * _PAGE_LIMIT
            # every page POSTs to the SAME url (the cache key); only the body's offset moves
            try:
                page = fetcher.post_json(
                    request.url,
                    _search_body(offset),
                    validators=request.validators if page_index == 0 else None,
                )
            except FetchFailure as exc:
                if page_index == 0:
                    return _failed(request.url, str(exc))
                errors.append(f"page at offset {offset}: {exc}")
                capped = False
                break
            if page_index == 0:
                if page.not_modified:
                    return BoardSnapshot(
                        status="unchanged", postings=[], url=request.url,
                        observed_validators=None, error=None,
                    )
                observed = page.observed_validators
            rows = _postings_list(page.content)
            if rows is None:
                if page_index == 0:
                    return _failed(
                        request.url, "invalid board payload: missing 'jobPostings' list"
                    )
                errors.append(f"page at offset {offset}: invalid payload")
                capped = False
                break
            if page_index == 0:
                # total and facets are populated ONLY here; offset>0 answers total=0/facets=[]
                payload = _payload(page.content) or {}
                try:
                    total = max(0, int(payload["total"]))
                except (KeyError, TypeError, ValueError):
                    total = None
                raw_facets = payload.get("facets")
                facets = raw_facets if isinstance(raw_facets, list) else []
            _collect(rows, listed, seen_paths)
            if len(rows) < _PAGE_LIMIT:
                # THE termination condition. NOT `offset < total`: total is capped at 2000
                # and offset >= 2000 wraps to page 1, so that loop never terminates.
                capped = False
                break

        if capped:
            errors.append(
                f"page cap of {_MAX_PAGES} pages reached; listing may be incomplete, "
                "treating as partial so unseen postings are not closed"
            )
        elif total is not None and len(listed) < total and total < 2000:
            # 2000 is the server's own reported cap, so a shortfall against it is expected
            errors.append(f"incomplete listing: collected {len(listed)} of {total} postings")

        subtypes = _subtypes_by_path(fetcher, request.url, facets, errors)

        # The FULL live inventory, computed BEFORE the detail phase: known and
        # budget-skipped postings must stay in it or apply_board's _process_missing closes
        # them (C1, the SmartRecruiters pattern).
        by_id: dict[str, dict[str, Any]] = {}
        for row in listed:
            path = str(row.get("externalPath") or "")
            if path:
                by_id[_posting_id(path)] = row
        listed_ids = frozenset(by_id)

        unseen = [
            (pid, row) for pid, row in by_id.items() if pid not in request.known_posting_ids
        ]
        if len(unseen) > request.detail_budget:
            errors.append(
                f"detail budget of {request.detail_budget} exceeded "
                f"({len(unseen)} unseen postings); raise detail_fetch_budget or rescan"
            )
            unseen = unseen[: request.detail_budget]

        # PER-ROW ISOLATION, as every sibling provider does (greenhouse.py, ashby.py,
        # smartrecruiters.py): parse_posting raises on a row with no title, and one bad row
        # must not fail the whole board. This is what `errors` is for — a bare list
        # comprehension here lets a ValueError escape fetch_board.
        postings: list[RawPosting] = []
        detail_failures = 0
        for pid, row in unseen:
            path = str(row["externalPath"])
            try:
                detail_res = fetcher.get(self._detail_url(host, tenant, site, path))
            except FetchFailure as exc:
                detail_failures += 1
                errors.append(f"posting {pid} detail: {exc}")
                continue
            detail = _payload(detail_res.content)
            if detail is None:
                detail_failures += 1
                errors.append(f"posting {pid} detail: malformed payload")
                continue
            try:
                postings.append(
                    parse_posting(host, site, row, detail, subtypes.get(path))
                )
            except Exception as exc:  # per-posting isolation
                errors.append(f"posting {pid}: {exc}")

        if unseen and detail_failures == len(unseen):
            return _failed(request.url, f"all {len(unseen)} detail fetches failed")

        return BoardSnapshot(
            status="complete" if not errors else "partial",
            postings=postings,
            url=request.url,
            observed_validators=observed,
            error=None if not errors else "; ".join(errors[:3]),
            listed_ids=listed_ids,
        )

    def healthcheck(self, fetcher: Fetcher, slug: str) -> BoardHealth:
        """404 is the wrong-site-slug signature (errorCode "S21"); 401/403/410 are a gated
        or retired tenant, which is equally DEAD for our purposes."""
        try:
            url = self.board_url(slug)
        except ValueError:
            return BoardHealth.ERROR
        try:
            result = fetcher.post_json(url, _search_body(0))
        except FetchFailure as exc:
            health = health_from_failure(exc)
            if exc.status_code in (401, 403, 410):
                return BoardHealth.DEAD
            return health
        rows = _postings_list(result.content)
        if rows is None:
            return BoardHealth.ERROR
        return BoardHealth.OK if rows else BoardHealth.EMPTY


def _collect(
    rows: list[dict[str, Any]], listed: list[dict[str, Any]], seen_paths: set[str]
) -> None:
    """Append rows, deduping on externalPath. Dedupe is NOT on the city path segment:
    job-apps learned that distinct roles share it."""
    for row in rows:
        path = str(row.get("externalPath") or "")
        if not path or path in seen_paths:
            continue
        seen_paths.add(path)
        listed.append(row)


def parse_posting(
    host: str,
    site: str,
    listed: dict[str, Any],
    detail: dict[str, Any] | None,
    subtype: str | None,
) -> RawPosting:
    info = (detail or {}).get("jobPostingInfo")
    info = info if isinstance(info, dict) else {}
    external_path = str(listed.get("externalPath") or "")
    if not external_path:
        raise ValueError("posting has no externalPath")
    title = str(listed.get("title") or info.get("title") or "").strip()
    if not title:
        raise ValueError("empty title")
    location = str(info.get("location") or listed.get("locationsText") or "").strip()
    locations = [location] if location else []
    raw: dict[str, Any] = {"listed": listed}
    if detail is not None:
        raw["detail"] = detail
        raw["timeType"] = info.get("timeType")
    if subtype is not None:
        raw["workerSubType"] = subtype
    return RawPosting(
        provider_posting_id=_posting_id(external_path),
        title=title,
        url=str(info.get("externalUrl") or f"https://{host}/{site}{external_path}"),
        locations=locations,
        department=None,  # CXS exposes no department on either endpoint
        remote_policy=_remote_policy(info.get("remoteType") or listed.get("remoteType"), locations),
        posted_at=_iso_to_naive_utc(info.get("startDate")),
        updated_at=None,  # no update timestamp on either endpoint
        body_text=html_to_text(str(info.get("jobDescription") or "")),
        raw_json=raw,
    )


def _posting_id(external_path: str) -> str:
    """Requisition id = the final '_'-delimited token of externalPath's last segment, when
    it contains a digit (.../Senior-Platform-Engineer_JR1000001 -> JR1000001). Falls back to
    the whole externalPath, which is unique within a board. Req ids are NOT globally unique
    across tenants (job-apps hit Blue Origin R66615 == Motorola R66615), but boardwatch
    scopes provider_posting_id per company row, so the tenant is already implied."""
    last = external_path.rstrip("/").rsplit("/", 1)[-1]
    token = last.rsplit("_", 1)[-1]
    return token if token and any(c.isdigit() for c in token) else external_path


def _remote_policy(remote_type: Any, locations: list[str]) -> RemotePolicy:
    """Workday exposes a STRUCTURED remoteType on both the list row and the detail info
    ("Fully Remote" / "Partially Remote"), which is preferred the same way Ashby prefers its
    isRemote boolean over text mining. Not every tenant sets it (Etsy does, NVIDIA does not),
    so the location-text heuristic every other provider uses is the fallback."""
    if isinstance(remote_type, str) and remote_type.strip():
        lowered = remote_type.casefold()
        if "partial" in lowered or "hybrid" in lowered:
            return "hybrid"
        if "remote" in lowered:
            return "remote"
        if "on-site" in lowered or "onsite" in lowered:
            return "onsite"
    return "remote" if any("remote" in loc.casefold() for loc in locations) else "unknown"


def _iso_to_naive_utc(value: Any) -> datetime | None:
    """startDate is the posting date, evidenced by a requisition reporting
    postedOn: "Posted Today" whose startDate equalled the probe date exactly. `postedOn`
    itself is a human string and is never parsed. Date-only values become UTC midnight."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return to_naive_utc(parsed)
