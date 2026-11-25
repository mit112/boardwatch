"""Workday provider (live-verified 2026-08-04).

The FIRST provider whose board identity is not a single opaque token. A Workday board is a
{host, tenant, site} TRIPLE, carried as the composite slug "{host}/{tenant}/{site}". That
keeps UNIQUE(provider, slug) exactly correct — and load-bearing, because Sony serves three
disjoint sites from one host with one tenant — and needs no migration. The triple never
leaves this module.

Six measured properties drive this design. Each has a regression test; none should be
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

6. THE 2000 CLAMP IS ON `total` ONLY, NOT ON THE FACETS, so a board larger than that is
   enumerated blind and partially. Measured live 2026-09-07: Walmart's true 21,190 postings
   report total=2000 and yield 1,998; Citi's 4,376 report 2000 and yield 1,988; Lowes reports
   its real 12,307 and stops at _MAX_PAGES with 3,000. A slug may therefore name ONE facet
   bucket to fetch instead of the whole board, carried as a FRAGMENT so that the three-part
   slug every live board already uses is untouched:

       host/tenant/site#jobFamilyGroup=Technology

   Sliced, `total` reads the bucket's TRUE size (Citi's Technology bucket answered 1074, not
   2000) and the pager enumerates all of it: 54 pages for every technology posting, against
   the 100 pages a blind scan spends to reach 53% of them. The facet id is an OPAQUE,
   TENANT-SPECIFIC hash, so it is never hardcoded and never cached across boards — ONE
   unfiltered request per sliced board reads the live catalog and resolves descriptor -> id
   at fetch time. Tenants expose DIFFERENT groups (Citi, Target and Lowes offer
   `jobFamilyGroup` and no `jobFamily`), which is why the fragment names both the group and
   the descriptor rather than the descriptor alone.

   A named group or descriptor that is not in the live catalog is a board-level ERROR, NEVER
   an unfiltered fetch. Falling back would restore the blind 2,000-row listing while the
   operator believed the board was sliced — the same trap as an ignored facet parameter. Which
   makes the spelling the operator's whole problem, so `boardwatch companies facets <board>`
   prints the live catalog — every group, every bucket, its posting count and the slug that
   would fetch it — with no store and no watch needed.

Detail fetches are bounded and skip known postings (the SmartRecruiters pattern), so
snapshot.postings is the newly-fetched subset and snapshot.listed_ids carries the FULL live
inventory — otherwise apply_board would close every known-but-unrefreshed posting. The
consequence is that body_text and the captured employment-type fields fill in incrementally
across scans. Salary is never mined (D19).

fetch_board pages the full board (trap 2 above), then fetches details for the unseen
postings only, within the budget.

7. A CENSORED LISTING IS SPLIT BY FACET, INSIDE THE BOARD'S OWN SCOPE (T351). When the
   offset-0 page reports the censor, the root is not paged further: it is listed instead as one
   child query per value of a facet group, each the parent's `appliedFacets` plus that value
   (two groups are an AND, measured on genpt 2026-11-24), and a child still censored is split
   again. Every row joins one inventory, so a split board is still ONE board. It is `complete`
   only on the structural certificate `_run_split` checks at every split; a union that matches
   the facet sum alone never certifies. The whole split stays within `_MAX_PAGES`: a board whose
   plan does not fit is read blind as before, and stays `partial`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, NamedTuple
from urllib.parse import urlsplit

from boardwatch.core.clock import to_naive_utc
from boardwatch.core.html_text import html_to_text
from boardwatch.core.models import BoardRequest, BoardSnapshot, RawPosting, RemotePolicy
from boardwatch.core.politeness import Fetcher, FetchFailure
from boardwatch.providers.base import (
    BoardHealth,
    apply_listing_gate,
    detail_phase_stops,
    head_shadow,
    health_from_failure,
)
from boardwatch.rank.location_gate import resolve_countries

_HOST_SUFFIX = ".myworkdayjobs.com"
_PAGE_LIMIT = 20  # HARD server maximum: limit=21 returns HTTP 400, it is not clamped
# 150 pages x 20 = 3000, comfortably past the server's own 2000 `total` cap. A backstop
# only: normal termination is a short page (trap 2 above).
#
# DO NOT RAISE IT. Lowes is the ONE live board that reaches it — 12,307 postings with no
# server clamp at all — and paging to the end would cost 616 requests to gain 61 technology
# postings. The fix for a board that large is a facet SLICE (property 6 above), which is
# both complete and cheaper; a bigger backstop is neither.
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
# Peeled off the slug BEFORE the triple split, so it cannot be mistaken for a path component.
_FACET_SEPARATOR = "#"
_FACET_FORM = (
    "expected host/tenant/site#{facetGroup}={descriptor}, e.g. "
    "acme.wd5.myworkdayjobs.com/acme/AcmeCareers#jobFamilyGroup=Technology"
)


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


class FacetSlice(NamedTuple):
    """One facet bucket a board is narrowed to (property 6). `parameter` is the tenant's own
    facet group key (`jobFamilyGroup`); `descriptor` is the bucket's human label
    (`Technology`). The bucket's ID is deliberately NOT here: it is an opaque, tenant-specific
    hash and is resolved from the live catalog at fetch time, never stored."""

    parameter: str
    descriptor: str


def split_target(slug: str) -> tuple[str, str, str, FacetSlice | None]:
    """(host, tenant, site, facet slice or None) from a stored slug.

    The slice is a FRAGMENT, peeled off BEFORE the triple split rather than added as a fourth
    path component: `normalize_slug` requires exactly three `/`-delimited parts and every
    stored Workday slug uses that form, so a fourth component would collide with the invariant
    and with 157 live boards at once. A slug with no `#` therefore takes exactly the path it
    always took and produces the same triple, the same `board_url` and the same request body.

        acme.wd5.myworkdayjobs.com/acme/AcmeCareers                             unsliced
        acme.wd5.myworkdayjobs.com/acme/AcmeCareers#jobFamilyGroup=Technology    sliced

    The fragment is `{facetParameter}={descriptor}`, partitioned on the FIRST `=` only,
    because a real descriptor contains spaces, `&` and `,` ("Software Engineering and
    Architecture"). Nothing here decodes the remainder: the descriptor is compared to the live
    catalog verbatim, so decoding it would break the comparison.

    Case is preserved on BOTH halves, and for a stronger reason than `split_slug`'s: the
    parameter is a tenant's own JSON key (`jobFamilyGroup`, `Country_and_Jurisdiction`) and
    the descriptor is matched exactly against the live catalog, so folding either turns a real
    slice into the board-level ERROR that an out-of-catalog descriptor earns.

    `store/queries.py:stored_slug` folds case, so a MISSPELT-case slice is not stored a second
    time alongside a correctly-spelt one — it resolves to the stored spelling. What it cannot
    do is rescue a board whose FIRST insert had the wrong case: that board fails every scan,
    with the descriptor and the group's real values named in the error. That is the intended
    closed-catalog behaviour, not a gap to close by folding here.

    Raises ValueError on anything malformed, which board_urls._normalize_slug turns into
    UnknownBoardURL — the same contract `split_slug` has.
    """
    base, separator, fragment = slug.strip().partition(_FACET_SEPARATOR)
    host, tenant, site = split_slug(base)
    if not separator:
        return host, tenant, site, None
    raw_parameter, equals, raw_descriptor = fragment.partition("=")
    parameter, descriptor = raw_parameter.strip(), raw_descriptor.strip()
    if not equals or not parameter or not descriptor:
        raise ValueError(_FACET_FORM)
    for label, value in (("facet group", parameter), ("facet descriptor", descriptor)):
        if any(ord(c) < 32 for c in value):
            raise ValueError(f"{label} {value!r} contains a control character")
    # A descriptor legitimately contains spaces; a facet group key never does — it is a JSON
    # key the tenant itself names, and whitespace there is a malformed slug, not a real group.
    if any(c.isspace() for c in parameter):
        raise ValueError(f"facet group {parameter!r} contains whitespace")
    return host, tenant, site, FacetSlice(parameter, descriptor)


# The second public host family. Its career-site URLs carry the tenant in the PATH
# (`/recruiting/{tenant}/{site}/job/...`) instead of in the first host label.
_SITE_HOST_SUFFIX = ".myworkdaysite.com"


def cxs_job_url(url: str) -> str | None:
    """The CXS JSON endpoint for one posting's public page, or None if `url` is not one.

    The page itself is useless as a liveness signal: every closed requisition measured still
    answers HTTP 200 on it (0 of 37, D-325). The CXS endpoint does not, so the probe asks it
    instead (`pipeline/liveness.py`). Two page shapes map onto it:

        {tenant}.wdN.myworkdayjobs.com/[{locale}/]{site}/job/{location}/{ref}
        {host}.myworkdaysite.com/[{locale}/]recruiting/{tenant}/{site}/job/{location}/{ref}
            -> https://{host}/wday/cxs/{tenant}/{site}/job/{location}/{ref}

    `{locale}` is `en-US`, or on the first host family also a 2-letter `es`. Exactly that shape
    and nothing looser: anything else (a `/details/` page, an `/apply` tail, a path without the
    location segment) is None and keeps the plain page probe, which strikes only
    when the page itself answers 404/410. A guessed endpoint that 404s would be read as a death.
    """
    parts_url = urlsplit(url)
    host = (parts_url.hostname or "").lower()
    parts = [part for part in parts_url.path.split("/") if part]
    if parts and _is_locale(parts[0]):
        parts = parts[1:]
    if host.endswith(_HOST_SUFFIX):
        tenant, rest = host.split(".", 1)[0], parts
    elif host.endswith(_SITE_HOST_SUFFIX) and len(parts) >= 2 and parts[0].lower() == "recruiting":
        tenant, rest = parts[1], parts[2:]
    else:
        return None
    # site, "job", location, reference: the `externalPath` shape the board scan itself stores
    def is_posting(segments: list[str]) -> bool:
        return len(segments) == 4 and segments[1].lower() == "job"

    # A 2-letter locale (`/es/`) cannot be told from a 2-letter site by shape, so it is peeled
    # only when what remains is a posting and the unpeeled path is not one.
    peelable = host.endswith(_HOST_SUFFIX) and len(rest) == 5 and len(rest[0]) == 2
    if peelable and not is_posting(rest) and is_posting(rest[1:]):
        rest = rest[1:]
    if not is_posting(rest) or not tenant:
        return None
    return f"https://{host}/wday/cxs/{tenant}/{rest[0]}/{'/'.join(rest[1:])}"


def _search_url(host: str, tenant: str, site: str) -> str:
    """The CXS search endpoint. The SAME url for a sliced and an unsliced board: the slice
    lives in the request BODY, and in `board_url`'s fragment, never in the wire target."""
    return f"https://{host}/wday/cxs/{tenant}/{site}/jobs"


def _search_body(
    offset: int, applied: dict[str, list[str]] | None = None, search_text: str = ""
) -> dict[str, Any]:
    """The CXS search body. `limit` is PINNED at _PAGE_LIMIT: 21 returns HTTP 400.

    `applied` defaulting to None and rendering as `{}` is what keeps an UNSLICED board's body
    byte-identical to the one 157 live boards have always sent — the key was already there and
    already empty, so slicing populates a field rather than adding one. `search_text` is the
    same kind of default: only `fetch_posting` sets it."""
    return {
        "appliedFacets": applied or {},
        "limit": _PAGE_LIMIT,
        "offset": offset,
        "searchText": search_text,
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


def _failed(
    url: str, error: str, *, dead: bool = False, board_reported_total: int | None = None,
    board_enumerated: int | None = None, detail_deferred: int | None = None,
    board_total_censored: bool | None = None,
) -> BoardSnapshot:
    """A failed snapshot. A board whose every detail failed also carries its listing counts
    (T252): the cap's verdict for a board its clock cut at the first detail takes the provider's
    counts, and these are all it has. Every other failure happens before there is a listing."""
    return BoardSnapshot(
        status="failed", postings=[], url=url, observed_validators=None, error=error, dead=dead,
        board_reported_total=board_reported_total, board_enumerated=board_enumerated,
        detail_deferred=detail_deferred, board_total_censored=board_total_censored,
    )


# Workday censors `total` at exactly this value and wraps the pager past it. The facets block
# is aggregated server-side by a different path and is NOT capped — measured 2026-08-22:
# Citi total=2000 / facets=4589, NVIDIA total=2000 / facets=2656, while four uncensored boards
# agreed exactly (Adobe 740, Intel 645, Regeneron 592, Fidelity 565). See D-271.
_TOTAL_CENSOR = 2000


def _facet_sum(payload: dict[str, Any], exclude: frozenset[str] = frozenset()) -> int | None:
    """The board's size by the facets' own aggregation path, or None if it yields nothing.

    `exclude` names the groups the request APPLIED. A filtered response re-aggregates every other
    group over the filtered rows but answers an applied group with its UNFILTERED counts
    (measured on genpt 2026-11-24: filtered to one jobFamilyGroup of 393, that group still read
    1,373 for another value), so an applied group would report its parent's size, not this one's.

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
        parameter = facet.get("facetParameter")
        if isinstance(parameter, str) and parameter in exclude:
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


class FacetUnavailable(Exception):
    """The facet slice a slug names is not in the board's live facet catalog.

    A TYPED failure at the raise site, so nothing downstream classifies it by string-matching
    a message. It is caught in exactly one place — `fetch_board` — and turned into a
    board-level `failed` snapshot with ZERO rows. It must never be turned into an unfiltered
    fetch: that would silently restore the blind 2,000-row listing while the operator believed
    the board was sliced, which is the failure this whole mechanism exists to remove.
    """


class FacetBucket(NamedTuple):
    """One bucket of a board's live facet catalog: the descriptor a slug names, the tenant's
    OPAQUE id for it, and how many postings it holds.

    `postings` is the wire's `count`, renamed: `count` is `tuple.count` and a NamedTuple cannot
    shadow it. `int | None` rather than `int` — every bucket measured live carries a count (two
    tenants, 2026-09-07), but a live payload is not schema-validated, and `None` records a
    bucket that answered without a usable one instead of inventing a 0 the board never claimed,
    the same distinction `_uncapped_total` draws between "recovered" and "the server refused".
    """

    descriptor: str
    facet_id: str
    postings: int | None


def facet_buckets(payload: dict[str, Any]) -> dict[str, list[FacetBucket]]:
    """{facetParameter: [FacetBucket, ...]} from an offset=0 payload, in the board's own order.

    THE one walk of the facets block. `_facet_catalog` is a projection of this, so the slicing
    path and `companies facets` cannot disagree about the nesting — which is the part that is
    load-bearing (see `_facet_catalog`).

    A group with no usable bucket of its own gets NO key here, which is what keeps
    `_resolve_facet`'s two failure messages distinct: an absent key is "that group is not
    offered by this board", and an empty one would claim the tenant offers a group with
    nothing in it. Live `locationMainGroup` is exactly that case — three nested groups, no
    bucket of its own — so this is not a hypothetical.

    Walked RECURSIVELY, because a facet group can nest another GROUP inside its `values`
    instead of buckets: live tenants answer a `locationMainGroup` whose values are themselves
    groups (`facetParameter: "locations"`, `"locationCountry"`,
    `"locationRegionStateProvince"`) carrying the buckets. A top-level-only read reports those
    absent, and an absent group is a board-level ERROR here — so that reading would refuse a
    slice the tenant really offers. Re-measured 2026-09-07 on two further tenants: it nests
    THREE such groups, not the one the first probe saw. The planning session's first probe made
    the same class of mistake in the other direction by reading one group and concluding three
    boards had no engineering roles.

    Ragged shapes are skipped rather than raised on, for the reason `_facet_sum` records: a
    live payload is not schema-validated and one odd entry must not fail the whole board.
    """
    catalog: dict[str, list[FacetBucket]] = {}
    raw = payload.get("facets")
    for group in raw if isinstance(raw, list) else []:
        _collect_facet_group(group, catalog)
    return catalog


def _facet_catalog(payload: dict[str, Any]) -> dict[str, dict[str, str]]:
    """{facetParameter: {value descriptor: OPAQUE value id}} — the view `_resolve_facet` and
    `healthcheck` resolve a slug's descriptor against.

    A PROJECTION of `facet_buckets`, not a second walk. The count is dropped here rather than
    never read, because the slicing path has no use for it and `companies facets` does; two
    independent walks would be two chances to disagree about the nesting, and a walk that
    misses the nesting refuses a slice the tenant really offers.

    Duplicate descriptors inside one group resolve LAST-WINS, exactly as the single-pass
    version did — the dict comprehension consumes the buckets in the board's own order.
    """
    return {
        parameter: {bucket.descriptor: bucket.facet_id for bucket in buckets}
        for parameter, buckets in facet_buckets(payload).items()
    }


def _collect_facet_group(group: Any, catalog: dict[str, list[FacetBucket]]) -> None:
    if not isinstance(group, dict):
        return
    values = group.get("values")
    if not isinstance(values, list):
        return
    parameter = group.get("facetParameter")
    for value in values:
        if not isinstance(value, dict):
            continue
        if isinstance(value.get("values"), list):
            _collect_facet_group(value, catalog)  # a nested GROUP, not a bucket
            continue
        descriptor, facet_id = value.get("descriptor"), value.get("id")
        if not (isinstance(parameter, str) and parameter):
            continue
        if isinstance(descriptor, str) and descriptor and isinstance(facet_id, str) and facet_id:
            catalog.setdefault(parameter, []).append(
                FacetBucket(descriptor, facet_id, _posting_count(value.get("count")))
            )


def _posting_count(raw: Any) -> int | None:
    """A bucket's wire `count`, or None when it is absent, null or not a number. `bool` is
    excluded for the reason `_facet_sum` excludes it: `True` is an `int` and would read as 1.
    """
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return int(raw)
    return None


def _named(items: list[str], limit: int = 6) -> str:
    """A BOUNDED rendering of a catalog for an error message. `errors` is persisted into
    board_scans, and one tenant offers 31 job categories and 55 provinces — spelling the whole
    list out would bury the note in the column that has to carry it."""
    if not items:
        return "nothing sliceable at all"
    shown = ", ".join(repr(item) for item in items[:limit])
    return shown if len(items) <= limit else f"{shown} (+{len(items) - limit} more)"


def _resolve_facet(fetcher: Fetcher, url: str, facet: FacetSlice) -> str:
    """The tenant's opaque id for `facet`, read from ONE unfiltered request's facet catalog.

    That request is the whole extra cost of a sliced board — one POST, then the sliced pager.
    Its rows are DISCARDED: they are the unfiltered board's first page and enumerating them
    would put non-slice postings into the slice's inventory.

    The id is resolved on every fetch, from the board being fetched, and is never stored or
    reused: `e32326e1...` is one tenant's id for "Technology" and means nothing on another.

    Raises FacetUnavailable when the group or the descriptor is out of catalog. No fallback.
    """
    # Deliberately NO validators: the ones stored for a sliced board were observed on a
    # FILTERED response, and a 304 here would decide "unchanged" from a request we never made.
    # Inert either way — the CXS POST serves no validators at all (property 3).
    page = fetcher.post_json(url, _search_body(0))
    payload = _payload(page.content)
    if payload is None:
        raise FacetUnavailable(
            f"facet catalog unreadable, cannot slice {facet.parameter}={facet.descriptor!r}"
        )
    catalog = _facet_catalog(payload)
    values = catalog.get(facet.parameter)
    if values is None:
        raise FacetUnavailable(
            f"facet group {facet.parameter!r} (named for descriptor {facet.descriptor!r}) is "
            f"not offered by this board; it offers {_named(sorted(catalog))}"
        )
    facet_id = values.get(facet.descriptor)
    if facet_id is None:
        raise FacetUnavailable(
            f"facet {facet.parameter}={facet.descriptor!r} is not in this board's catalog; "
            f"that group offers {_named(sorted(values))}"
        )
    return facet_id


def read_facet_catalog(
    fetcher: Fetcher, slug: str
) -> tuple[str, dict[str, list[FacetBucket]]]:
    """(the board's slug with any slice fragment dropped, its live facet catalog with counts).

    The read-only half of `_resolve_facet`, for an operator asking what a board offers BEFORE
    deciding to watch it — which is why it takes a slug rather than a stored board, opens no
    store and returns rather than raising on an empty catalog. It makes exactly ONE request,
    the same unfiltered offset=0 POST `_resolve_facet` makes, because `facets` is populated
    only there (trap 2); the page's `jobPostings` rows are discarded and nothing is persisted.

    No validators are sent, for the reason `_resolve_facet` records: a 304 would decide
    "unchanged" from a request we never made, and the CXS POST serves no validators anyway.

    An incoming slug MAY already name a slice; the fragment is DROPPED rather than refused. The
    catalog is a property of the board, and a filtered response re-aggregates its facets over
    the slice — so answering a sliced slug with the slice's own counts would tell an operator
    comparing buckets the wrong numbers.

    Raises ValueError on a malformed slug and FacetUnavailable when the board answers no
    readable payload; FetchFailure propagates to the caller.
    """
    host, tenant, site, _ = split_target(slug)
    page = fetcher.post_json(_search_url(host, tenant, site), _search_body(0))
    payload = _payload(page.content)
    if payload is None:
        raise FacetUnavailable("facet catalog unreadable: the board did not answer JSON")
    return "/".join((host, tenant, site)), facet_buckets(payload)


def _uncapped_total(
    payload: dict[str, Any], exclude: frozenset[str] = frozenset()
) -> tuple[int | None, bool | None]:
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

    `exclude` is the request's applied groups, for the reason `_facet_sum` records.
    """
    total = _stated_total(payload)
    if total is None:
        return None, None
    if total != _TOTAL_CENSOR:
        return total, False
    return _facet_sum(payload, exclude), True


def _stated_total(payload: dict[str, Any]) -> int | None:
    """The page's own `total`, or None when it states none usable."""
    try:
        return max(0, int(payload["total"]))
    except (KeyError, TypeError, ValueError):
        return None


# T351: how many facet groups a censored listing may be split on, one under the other.
_MAX_SPLIT_DEPTH = 3


@dataclass
class _Listing:
    """A board's listing as it is read: every row once by `externalPath`, in request order.

    `requests` counts every listing POST sent, failed ones included, and is what `_MAX_PAGES`
    bounds; `page_ends` has one entry per page READ, which is what `listing_pages` reports."""

    requests: int = 0
    listed: list[dict[str, Any]] = field(default_factory=list)
    seen_paths: set[str] = field(default_factory=set)
    page_ends: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def read(self, rows: list[dict[str, Any]], scope: set[str], offset: int, label: str) -> None:
        """Take one page: into the board's inventory, and into `scope`, the paths the query that
        served it has listed. The two differ only in a split, where a row under two values of a
        multi-valued group is the board's once and each child's own."""
        if dropped := _collect(rows, self.listed, self.seen_paths):
            self.errors.append(
                f"{label}page at offset {offset}: dropped {dropped} rows with no externalPath"
            )
        scope.update(path for row in rows if (path := str(row.get("externalPath") or "")))
        self.page_ends.append(len(self.listed))


def _page_query(
    fetcher: Fetcher,
    post_url: str,
    applied: dict[str, list[str]],
    first_rows: list[dict[str, Any]],
    listing: _Listing,
    *,
    label: str = "",
    watch_deadline: bool = False,
    stated: int | None = None,
) -> tuple[str, set[str]]:
    """Page one query to its end, its offset-0 page (`first_rows`) already requested.

    Returns how it ended and the paths THIS query listed. "short" is the only complete
    ending (trap 2); the others are "wrap", "cap" (`_MAX_PAGES` requests spent across the whole
    board), "failed" and "deadline". The unsplit listing is exactly the pager this module always
    ran, so it sends the same requests and records the same notes; only a split watches the
    board's deadline, because only a split can spend more than a blind read did.

    `stated` is a split child's own uncensored `total`. Workday answers the page past a query's
    last row with page 1 again instead of a short page when the query's size is a multiple of 20
    (the Intel tail; live on genpt's 240-row Production child, 2026-11-24). A repeat at exactly
    `offset == stated`, with that many distinct rows already listed, is therefore the query's
    end. A repeat anywhere else is still the wrap.
    """
    scope: set[str] = set()
    rows, offset = first_rows, 0
    while True:
        before = len(scope)
        listing.read(rows, scope, offset, label)
        if len(rows) < _PAGE_LIMIT:
            # THE termination condition. NOT `offset < total`: total is capped at 2000
            # and offset >= 2000 wraps to page 1, so that loop never terminates.
            return "short", scope
        if len(scope) == before:
            if stated is not None and offset == stated == len(scope) < _TOTAL_CENSOR:
                return "short", scope
            # A FULL page that added no new externalPath is the offset-wrap tail: Workday
            # serves byte-identical full pages past a board's real count (Intel; and every
            # board once offset >= 2000 wraps to page 1) instead of a short page, which
            # would otherwise burn every remaining page up to _MAX_PAGES. Stop, and keep it
            # partial so apply_board does not close the postings we stopped re-listing.
            listing.errors.append(
                f"{label}page at offset {offset} added no new postings; stopping "
                f"({len(scope)} collected, listing may be incomplete)"
            )
            return "wrap", scope
        if listing.requests >= _MAX_PAGES:
            return "cap", scope
        offset += _PAGE_LIMIT
        if watch_deadline and not fetcher.request_fits_board_deadline():
            return "deadline", scope
        listing.requests += 1
        try:
            page = fetcher.post_json(post_url, _search_body(offset, applied))
        except FetchFailure as exc:
            listing.errors.append(f"{label}page at offset {offset}: {exc}")
            return "failed", scope
        next_rows = _postings_list(page.content)
        if next_rows is None:
            listing.errors.append(f"{label}page at offset {offset}: invalid payload")
            return "failed", scope
        rows = next_rows


class _Split(NamedTuple):
    """One facet group a censored query is split on: one child query per value in `buckets`."""

    group: str
    buckets: tuple[FacetBucket, ...]
    covered: int  # the values' counts summed: at least `size` when the group is exhaustive
    size: int  # the parent query's size: the largest count stated for it (`_scope_size`)
    witnesses: int  # how many independent counts state exactly `size`
    pages: int  # the plan's estimated listing requests

    @property
    def exhaustive(self) -> bool:
        return self.covered >= self.size


def _split_pages(count: int) -> int:
    """Listing requests a child of `count` rows costs: its full pages and the short page that ends
    it, plus one for a child still censored, whose offset-0 page is read before it splits again.
    A floor for that child, whose own children are planned only once its facets are read."""
    return count // _PAGE_LIMIT + 1 + (1 if count >= _TOTAL_CENSOR else 0)


def _scope_size(
    payload: dict[str, Any], applied: dict[str, list[str]], parent_count: int | None
) -> tuple[int | None, int]:
    """(a censored query's size, how many independent counts state exactly that size).

    The counts are the sums of the page's top-level groups not applied (`_facet_sum`'s
    reading) and, for a child, its bucket's count on the parent's page. The size is the
    largest. ONE count stating it is not enough to certify on: a group that misses rows sums
    low, and if it is the only group, or the largest, it would pass the exhaustive test against
    its own count while its untagged rows sit in no child."""
    sums: list[int] = []
    raw = payload.get("facets")
    for facet in raw if isinstance(raw, list) else []:
        if not isinstance(facet, dict):
            continue
        parameter = facet.get("facetParameter")
        # a count is a witness only under a real group name: a ragged entry must not corroborate
        if not (isinstance(parameter, str) and parameter) or parameter in applied:
            continue
        if (total := _facet_sum({"facets": [facet]})) is not None:
            sums.append(total)
    if parent_count:
        sums.append(parent_count)
    if not sums:
        return None, 0
    size = max(sums)
    return size, sums.count(size)


def _plan_split(
    payload: dict[str, Any],
    applied: dict[str, list[str]],
    budget: int,
    parent_count: int | None = None,
) -> _Split | str:
    """The facet group to split a censored query on, or why there is none.

    Candidates are the groups of the query's own offset-0 page not already applied, with at least
    two counted values. A group is EXHAUSTIVE when its counts sum to at least `size`: a
    single-valued group that sums lower has rows carrying none of its values, and those rows
    would be in no child. Ranked: exhaustive first; then no child still censored; then, among
    exhaustive groups, the fewest estimated pages (which also prefers a single-valued group, as a
    multi-valued one counts a row under each of its values), and among the rest the most rows
    covered. A non-exhaustive group is used only when it covers more than a blind read reaches,
    and its board can then never certify. Only plans within `budget` requests are considered.
    """
    size, witnesses = _scope_size(payload, applied, parent_count)
    if size is None:
        return "no facet sum to size it by"
    candidates: list[tuple[tuple[bool, bool, int, int], _Split]] = []
    for order, (group, buckets) in enumerate(facet_buckets(payload).items()):
        if group in applied:
            continue
        values = tuple(bucket for bucket in buckets if bucket.postings)
        if len(values) < 2:
            continue
        counts = [bucket.postings or 0 for bucket in values]
        plan = _Split(
            group, values, sum(counts), size, witnesses, sum(_split_pages(c) for c in counts)
        )
        if not plan.exhaustive and plan.covered <= _TOTAL_CENSOR:
            continue
        rank = (
            not plan.exhaustive,
            max(counts) >= _TOTAL_CENSOR,
            plan.pages if plan.exhaustive else -plan.covered,
            order,
        )
        candidates.append((rank, plan))
    if not candidates:
        return f"no facet group can split this listing of {size} postings"
    fitting = [(rank, plan) for rank, plan in candidates if plan.pages <= budget]
    if not fitting:
        cheapest = min(plan.pages for _, plan in candidates)
        return (
            f"no facet split fits the page budget: the cheapest plan needs {cheapest} "
            f"pages, {budget} are left"
        )
    return min(fitting, key=lambda item: item[0])[1]


def _run_split(
    fetcher: Fetcher,
    post_url: str,
    applied: dict[str, list[str]],
    plan: _Split,
    listing: _Listing,
    depth: int,
    label: str,
    first: set[str],
) -> set[str]:
    """List a censored query as `plan`'s children, noting in `errors` every way it falls short,
    and return the paths its children listed. `first` is the query's own first page.

    THE CERTIFICATE IS THAT NO NOTE IS LEFT: any note makes the board `partial`, which closes
    nothing. A child passes when it ended on its own end, states a total under the censor and
    listed at least that many distinct rows itself; a child still censored passes through its
    own split, at most `_MAX_SPLIT_DEPTH` groups deep. At EVERY split, not only the root's, the
    children together must hold the query's size, stated by at least two independent counts
    (`_scope_size`), and every row of its first page: one child's growth between requests must
    not hide another's gap. A non-exhaustive group, a failed child, a payload without a total, a
    censored child with nothing left to split, a spent page budget and a near board deadline
    each leave a note too. Children after a failed one are still read: their rows are new
    postings to fetch even on a board that will close nothing.
    """
    if not plan.exhaustive:
        listing.errors.append(
            f"{label}split on {plan.group} covers {plan.covered} of {plan.size} postings; "
            "listing may be incomplete"
        )
    if plan.witnesses < 2:
        listing.errors.append(
            f"{label}a size of {plan.size} is stated by one count only; listing cannot certify"
        )
    subtree: set[str] = set()
    for bucket in plan.buckets:
        child = {**applied, plan.group: [bucket.facet_id]}
        child_label = f"{label}{plan.group}={bucket.descriptor}: "
        if listing.requests >= _MAX_PAGES:
            listing.errors.append(
                f"{child_label}not read, the page budget of {_MAX_PAGES} is spent"
            )
            return subtree
        if not fetcher.request_fits_board_deadline():
            listing.errors.append(f"{child_label}not read, the board deadline is near")
            return subtree
        listing.requests += 1
        try:
            page = fetcher.post_json(post_url, _search_body(0, child))
        except FetchFailure as exc:
            listing.errors.append(f"{child_label}page at offset 0: {exc}")
            continue
        rows = _postings_list(page.content)
        if rows is None:
            listing.errors.append(f"{child_label}page at offset 0: invalid payload")
            continue
        payload = _payload(page.content) or {}
        total = _stated_total(payload)
        if total == _TOTAL_CENSOR:
            # Its rows past offset 0 are read again in its own children, so it is not paged.
            child_first: set[str] = set()
            listing.read(rows, child_first, 0, child_label)
            subtree |= child_first
            sub = (
                _plan_split(payload, child, _MAX_PAGES - listing.requests, bucket.postings)
                if depth < _MAX_SPLIT_DEPTH
                else f"no facet group left to split, {_MAX_SPLIT_DEPTH} are applied"
            )
            if isinstance(sub, str):
                listing.errors.append(f"{child_label}censored at {_TOTAL_CENSOR}: {sub}")
                continue
            subtree |= _run_split(
                fetcher, post_url, child, sub, listing, depth + 1, child_label, child_first
            )
            continue
        ending, scope = _page_query(
            fetcher, post_url, child, rows, listing, label=child_label, watch_deadline=True,
            stated=total,
        )
        subtree |= scope
        if ending == "cap":
            listing.errors.append(f"{child_label}stopped, the page budget of {_MAX_PAGES} is spent")
        elif ending == "deadline":
            listing.errors.append(f"{child_label}stopped, the board deadline is near")
        elif ending == "short":  # "wrap" and "failed" left their own note
            # Against the larger of its own total and its bucket's count on the parent's page:
            # a row that moved out of this child after the parent was counted, into a child
            # already read, is in neither, and a sibling's growth could otherwise hide it.
            expected = max(total or 0, bucket.postings or 0)
            if total is None:
                listing.errors.append(f"{child_label}states no total")
            elif len(scope) < expected:
                listing.errors.append(
                    f"{child_label}incomplete listing: collected {len(scope)} of {expected} "
                    "postings"
                )
    if missing := len(first - subtree):
        listing.errors.append(f"{label}{missing} rows of the first page are in no child")
    if len(subtree) < plan.size:
        # Checked even when every child passed: rows moved between requests, or the counts
        # overstate the query. A union that MEETS the size is necessary, never sufficient;
        # one that falls short is never complete.
        listing.errors.append(
            f"{label}listed {len(subtree)} distinct postings of {plan.size}; "
            "listing may be incomplete"
        )
    return subtree


class WorkdayProvider:
    name = "workday"
    # Skips the detail read for an id the store holds open (T350): the scan loads the set only
    # for a provider that declares this.
    reads_known_ids = True
    # Discards rows through the listing gate unstored, so its validators are bound to the gate's
    # key (T355).
    gates_listings = True
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
    def employer_name_from_slug(slug: str) -> str | None:
        """The Workday TENANT (T74) — `ngc` out of `ngc.wd1.myworkdayjobs.com/ngc/...`.

        The tenant, not the career-SITE segment. A site is the tenant's own label for a
        candidate experience (`Northrop_Grumman_External_Site`, `External_Career_Site`,
        `Careers`), so reading an employer out of it means stripping generic career words —
        a guess, and a wrong employer name merges two companies' postings.

        The honest cost, stated because it is the one case this does NOT unify: a tenant token
        is not word-separated, so it groups with a single-word employer name (`Qualcomm`,
        `Stripe`) and cannot group with a multi-word one — `ngc` will never normalize equal to
        `northrop grumman`. That is a limit of what a slug carries, not something a heuristic
        here may paper over.
        """
        try:
            _host, tenant, _site, _facet = split_target(slug)
        except ValueError:
            return None
        return tenant.strip().lower() or None

    @staticmethod
    def normalize_slug(slug: str) -> str:
        host, tenant, site, facet = split_target(slug)
        triple = "/".join((host, tenant, site))
        if facet is None:
            return triple
        return f"{triple}{_FACET_SEPARATOR}{facet.parameter}={facet.descriptor}"

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

        A facet slice is NEVER derived here: `urlparse` splits a URL's fragment off before
        `parts` is built, so a pasted career-site URL can only ever name the whole board. A
        slice is asked for through the qualified `workday:host/tenant/site#group=Descriptor`
        form, which is the only form that carries a fragment as far as `normalize_slug`.
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
        stored slug; scan/coordinator.py and scan/health.py guard the call.

        A facet slice is carried here as a FRAGMENT so that two slices of one tenant are two
        distinct cache keys instead of one row they would overwrite in turn. The fragment is
        never sent on the wire — `fetch_board` posts to the part before it — and an UNSLICED
        slug returns exactly the string it always returned, byte for byte."""
        host, tenant, site, facet = split_target(slug)
        url = _search_url(host, tenant, site)
        if facet is None:
            return url
        return f"{url}{_FACET_SEPARATOR}{facet.parameter}={facet.descriptor}"

    def _detail_url(self, host: str, tenant: str, site: str, external_path: str) -> str:
        return f"https://{host}/wday/cxs/{tenant}/{site}{external_path}"

    def fetch_board(self, fetcher: Fetcher, request: BoardRequest) -> BoardSnapshot:
        try:
            host, tenant, site, facet = split_target(request.slug)
        except ValueError as exc:
            return _failed(request.url, f"invalid workday slug: {exc}")

        # The wire target is the url WITHOUT the facet fragment: the slice lives in the request
        # BODY, and the fragment exists only so `board_url` yields distinct cache keys.
        # `request.url` is that cache key, and an unsliced slug has no fragment, so for 157
        # live boards this line is `request.url` unchanged.
        #
        # BELT AND BRACES, deliberately: httpx already drops a fragment when the client builds
        # the request, so no test can distinguish this from posting `request.url` directly.
        # Stripping it here keeps the invariant local instead of resting on that normalization.
        post_url = request.url.partition(_FACET_SEPARATOR)[0]
        applied: dict[str, list[str]] = {}
        if facet is not None:
            # ONE unfiltered POST, and NO fallback on either failure branch: an out-of-catalog
            # descriptor must enumerate zero rows, not the blind unfiltered board.
            try:
                applied = {facet.parameter: [_resolve_facet(fetcher, post_url, facet)]}
            except FetchFailure as exc:
                return _failed(request.url, f"facet catalog: {exc}")
            except FacetUnavailable as exc:
                return _failed(request.url, str(exc))

        # The offset-0 page: the only one that carries `total` and `facets` (trap 2), and the only
        # one that sends validators. Every page POSTs to the SAME url; only the body moves. That
        # url is the cache key for an unsliced board and the key MINUS its fragment for a sliced
        # one, which is why `request.url` — not `post_url` — is what the snapshot echoes back.
        try:
            page = fetcher.post_json(
                post_url, _search_body(0, applied), validators=request.validators
            )
        except FetchFailure as exc:
            return _failed(request.url, str(exc), dead=exc.status_code == 404)
        if page.not_modified:
            return BoardSnapshot(
                status="unchanged", postings=[], url=request.url,
                observed_validators=None, error=None,
            )
        observed = page.observed_validators
        rows = _postings_list(page.content)
        if rows is None:
            return _failed(request.url, "invalid board payload: missing 'jobPostings' list")
        payload = _payload(page.content) or {}
        total = _stated_total(payload)
        board_total, board_censored = _uncapped_total(payload, frozenset(applied))
        listing = _Listing(requests=1)
        errors = listing.errors

        # T351: a censored root is listed by facet instead, when a split fits the page budget.
        plan: _Split | str | None = None
        if board_censored and board_total is not None:
            plan = _plan_split(payload, applied, _MAX_PAGES - 1)
        split = isinstance(plan, _Split)
        if isinstance(plan, _Split):
            # The root's own rows are kept, and not paged further: its children read them again.
            first: set[str] = set()
            listing.read(rows, first, 0, "")
            _run_split(fetcher, post_url, applied, plan, listing, 1, "split ", first)
        else:
            ending, _ = _page_query(fetcher, post_url, applied, rows, listing)
            if ending == "cap":
                errors.append(
                    f"page cap of {_MAX_PAGES} pages reached; listing may be incomplete, "
                    "treating as partial so unseen postings are not closed"
                )
            elif (
                total is not None and len(listing.listed) < total
                and (total < _TOTAL_CENSOR or (board_total is None and facet is not None))
            ):
                # A shortfall against the censor is expected, and the censor note below makes
                # that board partial. A censored SLICE whose facets name only its own group has
                # no recovered size, so no note: this one keeps it partial.
                errors.append(
                    f"incomplete listing: collected {len(listing.listed)} of {total} postings"
                )
            if isinstance(plan, str):
                errors.append(f"board not split: {plan}")
            if board_censored and board_total is not None:
                # human-readable note for the run log ONLY — the typed pair
                # (board_total_censored, board_reported_total) already carries the whole fact,
                # and nothing may ever recover it by grepping `errors`. Keyed on `is not None`,
                # not on `board_total != _TOTAL_CENSOR`: a facet dimension that legitimately sums
                # to 2000 IS a recovery and used to go unnoted, while an unrecovered board used
                # to be indistinguishable from it because both persisted 2000.
                errors.append(
                    f"board total censored at {_TOTAL_CENSOR}; facet sum reports {board_total}"
                )
        listed = listing.listed

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
        unseen, gated = apply_listing_gate(request, unseen, _listing_fields)
        shadow = head_shadow(
            listed, listing.page_ends, {pid for pid, _ in unseen},
            lambda row: _posting_id(str(row.get("externalPath") or "")), _listed_day,
        )
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
        first_failure: str | None = None
        for index, (pid, row) in enumerate(unseen):
            # T243: a board its cap cuts is failed and keeps nothing, so a detail phase longer
            # than the cap re-fetched the same details every scan. Stop starting them here
            # instead; `unseen` becomes what was attempted, the rest deferred.
            if detail_phase_stops(
                fetcher, kept=bool(postings), left=len(unseen) - index, errors=errors
            ):
                unseen = unseen[:index]
                break
            path = str(row["externalPath"])
            try:
                detail_res = fetcher.get(self._detail_url(host, tenant, site, path))
            except FetchFailure as exc:
                detail_failures += 1
                errors.append(f"posting {pid} detail: {exc}")
                first_failure = first_failure or errors[-1]
                continue
            detail = _payload(detail_res.content)
            if detail is None:
                detail_failures += 1
                errors.append(f"posting {pid} detail: malformed payload")
                first_failure = first_failure or errors[-1]
                continue
            try:
                postings.append(parse_posting(host, site, row, detail))
            except Exception as exc:  # per-posting isolation
                errors.append(f"posting {pid}: {exc}")

        if unseen and detail_failures == len(unseen):
            return _failed(
                request.url, f"all {len(unseen)} detail fetches failed; {first_failure}",
                board_reported_total=board_total, board_enumerated=len(listed_ids),
                detail_deferred=len(unseen_before_truncation) - len(unseen),
                board_total_censored=board_censored,
            )

        return BoardSnapshot(
            status="complete" if not errors else "partial",
            postings=postings,
            url=request.url,
            observed_validators=observed,
            error=None if not errors else "; ".join(errors),
            listed_ids=listed_ids,
            board_reported_total=board_total,
            board_enumerated=len(listed_ids),
            detail_deferred=len(unseen_before_truncation) - len(unseen),
            gated_listings=gated,
            board_total_censored=board_censored,
            listing_pages=shadow.listing_pages,
            # A split has no single newest-first order, so no head-scan stop point (T351).
            head_pages=None if split else shadow.head_pages,
            head_missed=None if split else shadow.head_missed,
        )

    def fetch_posting(
        self, fetcher: Fetcher, slug: str, provider_posting_id: str
    ) -> RawPosting | None:
        """One posting re-read from its board (`postings refetch`).

        The detail URL needs the posting's `externalPath`, which the provider_posting_id does
        not determine (it is the path's LAST token). So the board's own search is asked for the
        id first — unfiltered, because a sliced board's posting is on the whole board too — and
        the row whose `externalPath` keys to exactly this id supplies the path and the listed
        half of `parse_posting`, as a scan's page row would. None when no row keys to the id,
        or the detail 404s.
        """
        host, tenant, site, _facet = split_target(slug)
        page = fetcher.post_json(
            _search_url(host, tenant, site), _search_body(0, search_text=provider_posting_id)
        )
        rows = _postings_list(page.content)
        if rows is None:
            raise ValueError("invalid search payload: missing 'jobPostings' list")
        listed = next(
            (
                row for row in rows
                if row.get("externalPath")
                and _posting_id(str(row["externalPath"])) == provider_posting_id
            ),
            None,
        )
        if listed is None:
            return None
        try:
            result = fetcher.get(
                self._detail_url(host, tenant, site, str(listed["externalPath"]))
            )
        except FetchFailure as exc:
            if exc.status_code == 404:
                return None
            raise
        detail = _payload(result.content)
        if detail is None:
            raise ValueError("detail payload is not an object")
        return parse_posting(host, site, listed, detail)

    def healthcheck(self, fetcher: Fetcher, slug: str) -> BoardHealth:
        """404 is the wrong-site-slug signature (errorCode "S21"); 401/403/410 are a gated
        or retired tenant, which is equally DEAD for our purposes.

        A slug naming a facet slice is additionally checked against the board's LIVE catalog,
        which THIS response already carries — so it costs no extra request, and a slice whose
        descriptor the tenant does not offer reads ERROR here instead of looking OK and then
        failing every scan. Live, Workday omits a bucket entirely rather than listing it with
        count 0, so presence in the catalog is the same answer as a non-empty slice."""
        try:
            host, tenant, site, facet = split_target(slug)
        except ValueError:
            return BoardHealth.ERROR
        try:
            result = fetcher.post_json(_search_url(host, tenant, site), _search_body(0))
        except FetchFailure as exc:
            health = health_from_failure(exc)
            if exc.status_code in (401, 403, 410):
                return BoardHealth.DEAD
            return health
        rows = _postings_list(result.content)
        if rows is None:
            return BoardHealth.ERROR
        if facet is not None:
            catalog = _facet_catalog(_payload(result.content) or {})
            return (
                BoardHealth.OK
                if facet.descriptor in catalog.get(facet.parameter, {})
                else BoardHealth.ERROR
            )
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


_POSTED_DAYS_AGO = re.compile(r"Posted (\d+)\+? Days Ago")


def _listed_day(row: dict[str, Any], today: date) -> date | None:
    """The listing's `postedOn`, which is relative English text ("Posted Today", "Posted 3 Days
    Ago", "Posted 30+ Days Ago"), as a date. Anything else is None: unreadable, so fresh."""
    text = str(row.get("postedOn") or "")
    if text == "Posted Today":
        return today
    if text == "Posted Yesterday":
        return today - timedelta(days=1)
    match = _POSTED_DAYS_AGO.fullmatch(text)
    return today - timedelta(days=int(match.group(1))) if match else None


def _listing_fields(item: tuple[str, dict[str, Any]]) -> tuple[str, str, list[str], str]:
    pid, row = item
    location = row.get("locationsText")
    return pid, str(row.get("title") or "").strip(), [str(location)] if location else [], "unknown"


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
    listed_additional = info.get("additionalLocations")
    additional = (
        [a.strip() for a in listed_additional if isinstance(a, str) and a.strip()]
        if isinstance(listed_additional, list)
        else []
    )
    primary = _with_country(location, info.get("country"), additional)
    locations = [primary] if primary else []
    # Only beside a country the primary had to borrow: that is the one place the country can turn
    # a posting with a US site among its additional ones into a confirmed foreign one. Elsewhere
    # the list stays the primary alone, because `cross_host` keys on the whole list and a lane's
    # copy of this posting carries only the primary — 803 open matches lost, live, otherwise.
    if primary != location:
        locations += additional
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
        remote_policy=_remote_policy(
            info.get("remoteType") or listed.get("remoteType"), [location] if location else []
        ),
        posted_at=_iso_to_naive_utc(info.get("startDate")),
        updated_at=None,  # no update timestamp on either endpoint
        body_text=html_to_text(str(info.get("jobDescription") or "")),
        raw_json=raw,
    )


def _with_country(location: str, country: Any, additional: list[str]) -> str:
    """The primary location, with the detail's structured country appended when its text names
    no place of its own.

    `jobPostingInfo.country.descriptor` is the PRIMARY location's country; `additionalLocations`
    carries bare strings and no country anywhere. A tenant's office code ("BUH IV") names no
    place, so without the country a foreign requisition resolves nowhere and the fail-open
    location gate keeps it. The country is a FALLBACK, not an override, because the two disagree
    on live data in both directions: one tenant tags Quezon City and Chihuahua requisitions with
    the USA (an always-appended country would turn those into US postings, since any US location
    wins), while "Bangalore, IN" carries India. Where the text already names a place it keeps
    deciding exactly as before. The adapter only records the country; the profile's target
    countries decide what it means.
    """
    descriptor = country.get("descriptor") if isinstance(country, dict) else None
    if not isinstance(descriptor, str) or not descriptor.strip():
        return location
    if resolve_countries([location]):
        return location
    # The country speaks for the primary ONLY. An additional site the resolver cannot name may be
    # a US one ("Silicon Valley"), and borrowing would then turn a real US job into a confirmed
    # foreign one, which the hard gate drops. Not borrowing leaves the posting `unknown`, kept
    # fail-open exactly as before.
    if not all(resolve_countries([site]) for site in additional):
        return location
    return f"{location}, {descriptor.strip()}" if location else descriptor.strip()


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
