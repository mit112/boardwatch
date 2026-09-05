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
   status. It is captured into raw_json anyway because backfilling it means re-scanning
   every Workday board; nothing reads it yet. Because detail fetches skip known postings, a
   posting already in the DB does not gain this field until it is re-detailed. That is the
   same incremental fill as body_text, not a Workday-specific gap. (A workerSubType
   facet-filtered probe used to run alongside this to recover an actual intern signal; the
   owner ruled DELETE — up to 20 extra POSTs per matched bucket for a field nothing read —
   see T14.)

5. bulletFields IS VARIABLE-LENGTH (Sony returns 3: req id, country, legal entity), so
   bulletFields[0] is NOT universally the requisition id. The id comes from externalPath.

Detail fetches are bounded and skip known postings (the SmartRecruiters pattern), so
snapshot.postings is the newly-fetched subset and snapshot.listed_ids carries the FULL live
inventory — otherwise apply_board would close every known-but-unrefreshed posting. The
consequence is that body_text and the captured employment-type fields fill in incrementally
across scans. Salary is never mined (D19).

fetch_board pages the full board (trap 2 above), then fetches details for the unseen
postings only, within the budget.
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


def _is_locale(segment: str) -> bool:
    """`en-US`, `en-us`, `fr-CA`. Shape-based rather than a list, which is what lets an
    unlisted locale still be skipped; the cost is that a 5-character site with a hyphen in
    the third position would be read as one, and none exists in 113,074 measured URLs."""
    return len(segment) == 5 and segment[2] == "-"
_SLUG_FORM = "expected host/tenant/site, e.g. acme.wd5.myworkdayjobs.com/acme/AcmeCareers"


def split_slug(slug: str) -> tuple[str, str, str]:
    """(host, tenant, site) from the composite slug, canonicalized: host and tenant
    lowercased, SITE CASE PRESERVED.

    The reason recorded here until 2026-09-01 was that "site slugs are case-sensitive live".
    **That is false and was measured false**: an A/B of the CXS endpoint across three casing
    styles returned identical totals for the stored casing and a lowercased one — nvidia
    `NVIDIAExternalCareerSite` 2000/2000, bdx `EXTERNAL_CAREER_SITE_USA` 576/576, roche
    `ROG-A2O-GENE` 224/224 — and 60 of 133 watched Workday companies were already STORED
    lowercased against the provider's own casing, holding 31,395 postings scanned clean.

    Case is still preserved, on a different and smaller reason: nothing requires lowering it.
    Identity does not depend on it, because `store/queries.py:stored_slug` folds case and is
    what stops one board being stored twice; lowering it would re-key 54 stored slugs and
    orphan their `http_cache` validators to buy nothing. Preserving the provider's own spelling
    is the cheaper default, NOT a correctness requirement — do not re-derive the old reason
    from the varied casing of real sites, which is what produced it the first time.

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


def _search_body(offset: int) -> dict[str, Any]:
    """The CXS search body. `limit` is PINNED at _PAGE_LIMIT: 21 returns HTTP 400."""
    return {
        "appliedFacets": {},
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


def _failed(url: str, error: str) -> BoardSnapshot:
    return BoardSnapshot(
        status="failed", postings=[], url=url, observed_validators=None, error=error,
    )


# Workday censors `total` at exactly this value and wraps the pager past it. The facets block
# is aggregated server-side by a different path and is NOT capped — measured 2026-08-22:
# Citi total=2000 / facets=4589, NVIDIA total=2000 / facets=2656, while four uncensored boards
# agreed exactly (Adobe 740, Intel 645, Regeneron 592, Fidelity 565). See D-271.
_TOTAL_CENSOR = 2000


def _facet_sum(payload: dict[str, Any]) -> int | None:
    """The board's size by the facets' own aggregation path, or None if it yields nothing.

    Every facet dimension partitions the same corpus, so they agree; the largest non-zero one
    is taken because `locationMainGroup` can sum to 0 on some tenants and would otherwise drag
    the maximum down. This runs on EVERY payload, censored or not, so the known-positive
    control (`_facet_sum(payload) == payload["total"]` on an uncensored board) exercises the
    same arithmetic the censored path depends on — Adobe 740/740, Intel 645/645,
    Regeneron 592/592 and Fidelity 565/565 live on 2026-08-22.

    Live payloads are not schema-validated, so every shape is walked defensively: a non-list
    `facets`, a non-dict facet or facet value, and a null `count` (`.get(key, default)` only
    substitutes for an ABSENT key, never for a present `null`) must never raise past this
    function and turn the whole board `status="failed"` — precisely for the large, censored
    tenants this exists to measure.
    """
    raw_facets = payload.get("facets")
    facets = raw_facets if isinstance(raw_facets, list) else []
    sums: list[int] = []
    for facet in facets:
        if not isinstance(facet, dict):
            continue
        values = facet.get("values")
        if not isinstance(values, list):
            continue
        facet_sum = 0
        for value in values:
            if not isinstance(value, dict):
                continue
            count = value.get("count")
            if isinstance(count, (int, float)) and not isinstance(count, bool):
                facet_sum += int(count)
        sums.append(facet_sum)
    non_zero = [s for s in sums if s > 0]
    return max(non_zero) if non_zero else None


def _uncapped_total(payload: dict[str, Any]) -> tuple[int | None, bool | None]:
    """Return (board_total, censored). None means the board stated no total — never 0, and
    censored is itself None in that case: with no total there is nothing to have censored, so
    False (a claim of "not censored") would be a claim this function cannot support.

    When `total` reads exactly _TOTAL_CENSOR the real size is unknown and >= it, so the facet
    sum is taken instead. If the facets yield nothing the answer is `(None, True)`, NOT
    `(2000, True)`: the censor value is the server refusing to answer, and returning it as a
    total would collapse two different epistemic states into one persisted row —
    "4,589, recovered by a second path" and "at least 2,000, floor only" both reading
    `censored=1`. With None, `censored and board_reported_total is not None` means
    "facet-recovered" and nothing downstream has to parse a message to learn it (D-271).
    """
    raw = payload.get("total")
    if raw is None:
        return None, None
    try:
        total = max(0, int(raw))
    except (TypeError, ValueError):
        return None, None
    if total != _TOTAL_CENSOR:
        return total, False
    return _facet_sum(payload), True


class WorkdayProvider:
    name = "workday"
    # Workday hostnames are UNBOUNDED ({tenant}.wd{N}.myworkdayjobs.com; wd1..wd12 observed),
    # so identity is a SUFFIX and there are no exact paste hosts.
    board_hosts: tuple[str, ...] = ()
    board_host_suffixes: tuple[str, ...] = (_HOST_SUFFIX,)
    # the slug is a host/tenant/site TRIPLE, so board_urls must let "/" through the
    # qualified form for this provider (and only for providers that opt in here)
    composite_slug = True
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
        """Composite slug from a pasted career-site URL, read by GRAMMAR rather than by
        skipping chrome. The tenant is the first host label.

        Workday serves two path shapes and each names the career site at a fixed position:
        the CXS API form `/wday/cxs/{tenant}/{site}/jobs`, and the public form
        `[{locale}/]{site}[/job/{location}/{ref}]`. So the site is the first segment that is
        not a locale — full stop.

        WHY NOT THE OLD SKIP-LOOP. It took the first segment that was neither a locale nor in
        `_CHROME_SEGMENTS`, and `_CHROME_SEGMENTS` contains `jobs`. A tenant whose career site
        is literally named `Jobs` therefore had its site SKIPPED and the next segment — the
        job's CITY — returned as the site. Red Hat's
        `redhat.wd5.myworkdayjobs.com/Jobs/job/Canberra/...` derived site `Canberra`, minting a
        company row for a board that does not exist, a different one per city; and
        `redhat.wd5.myworkdayjobs.com/jobs` pasted as a board URL returned None, so the two
        boards in this class (`redhat/jobs` and `paypal/jobs`, 325 postings, both watched)
        could only ever be added through the explicit `workday:host/tenant/site` form.
        `store/queries.py:stored_slug` does NOT rescue it — that folds CASE, and `canberra` is
        not a case variant of `jobs`.

        Measured over 113,074 real Workday URLs (93,044 from this store's own scans plus 4,521
        from an independent ledger, and every board URL in both): the first segment is `job` or
        `details` in **zero** of them, and the grammar above resolves every remaining one. It
        fixes 157 live posting URLs that derived a city.

        A path whose first non-locale segment IS `job`/`details` carries no career site at all,
        so it returns None rather than reading the location. `/wday/cxs` with nothing after it
        is likewise not a board.
        """
        tenant = host.split(".", 1)[0]
        lowered = [part.lower() for part in parts]
        if lowered[:2] == ["wday", "cxs"]:
            return f"{host}/{tenant}/{parts[3]}" if len(parts) >= 4 else None
        index = 1 if parts and _is_locale(parts[0]) else 0
        if index >= len(parts) or lowered[index] in ("job", "details"):
            return None
        return f"{host}/{tenant}/{parts[index]}"

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
        board_total: int | None = None
        # None, not False: `_uncapped_total`'s own contract is that with no total there is
        # nothing to have censored, so False would be a claim this initializer cannot support.
        board_censored: bool | None = None
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
                board_total, board_censored = _uncapped_total(payload)
            before = len(listed)
            if dropped := _collect(rows, listed, seen_paths):
                errors.append(
                    f"page at offset {offset}: dropped {dropped} rows with no externalPath"
                )
            if len(rows) < _PAGE_LIMIT:
                # THE termination condition. NOT `offset < total`: total is capped at 2000
                # and offset >= 2000 wraps to page 1, so that loop never terminates.
                capped = False
                break
            if len(listed) == before:
                # A FULL page that added no new externalPath is the offset-wrap tail: Workday
                # serves byte-identical full pages past a board's real count (Intel; and every
                # board once offset >= 2000 wraps to page 1) instead of a short page, which
                # would otherwise burn every remaining page up to _MAX_PAGES. Stop, and keep it
                # partial so apply_board does not close the postings we stopped re-listing.
                errors.append(
                    f"page at offset {offset} added no new postings; stopping "
                    f"({len(listed)} collected, listing may be incomplete)"
                )
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

        if board_censored and board_total is not None:
            # human-readable note for the run log ONLY — the typed pair
            # (board_total_censored, board_reported_total) already carries the whole fact, and
            # nothing may ever recover it by grepping `errors`. Keyed on `is not None`, not on
            # `board_total != _TOTAL_CENSOR`: a facet dimension that legitimately sums to 2000
            # IS a recovery and used to go unnoted, while an unrecovered board used to be
            # indistinguishable from it because both persisted 2000.
            errors.append(
                f"board total censored at {_TOTAL_CENSOR}; facet sum reports {board_total}"
            )

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
        # Captured BEFORE the detail-budget slice below rebinds `unseen`, so detail_deferred
        # reflects what the budget actually cut, not the post-truncation length (D-271).
        unseen_before_truncation = unseen
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
                postings.append(parse_posting(host, site, row, detail))
            except Exception as exc:  # per-posting isolation
                errors.append(f"posting {pid}: {exc}")

        if unseen and detail_failures == len(unseen):
            return _failed(request.url, f"all {len(unseen)} detail fetches failed")

        return BoardSnapshot(
            status="complete" if not errors else "partial",
            postings=postings,
            url=request.url,
            observed_validators=observed,
            error=None if not errors else "; ".join(errors),
            listed_ids=listed_ids,
            board_reported_total=board_total,
            board_enumerated=len(listed_ids),
            detail_deferred=max(0, len(unseen_before_truncation) - request.detail_budget),
            board_total_censored=board_censored,
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
) -> int:
    """Append rows, deduping on externalPath. Dedupe is NOT on the city path segment:
    job-apps learned that distinct roles share it.

    Returns the number of rows dropped for a MISSING externalPath, which the caller turns
    into an `errors` note. A dedupe drop is expected and is not counted; an id-less row is
    not, and dropping it silently would shrink listed_ids while status stayed "complete" —
    the one status that authorizes apply_board to close everything it no longer sees."""
    dropped = 0
    for row in rows:
        path = str(row.get("externalPath") or "")
        if not path:
            dropped += 1
            continue
        if path in seen_paths:
            continue
        seen_paths.add(path)
        listed.append(row)
    return dropped


def parse_posting(
    host: str,
    site: str,
    listed: dict[str, Any],
    detail: dict[str, Any] | None,
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
