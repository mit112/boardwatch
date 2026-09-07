"""Eightfold provider (live-verified 2026-09-06).

Eightfold hosts each employer's career site on the employer's OWN domain as often as on
`{tenant}.eightfold.ai`, so the board identity is the HOST — `careers.qualcomm.com`,
`jobs.northropgrumman.com`, `bostonscientific.eightfold.ai`. That is the slug, and the
identity consequence is spelled out in `board_hosts` below.

Seven measured properties drive this design. Each has a regression test; none should be
"simplified" away.

1. THE LISTING NEEDS A `domain` THAT THE HOST DOES NOT CARRY, so a board scan starts with an
   HTML BOOTSTRAP. `/api/pcsx/search` without `domain` is HTTP 422
   (`{"messages": {"domain": ["Missing data for required field."]}}`) and with a wrong one
   answers the SPA's HTML shell with HTTP 200 — a silent, un-parseable success. The value is
   NOT derivable from the host: `jobs.northropgrumman.com` is `ngc.com` and
   `bostonscientific.eightfold.ai` is `bostonscientific.com`. Every tenant page carries it in
   a `<code id="pcsx-data">` element holding HTML-escaped JSON, so `fetch_board` reads it from
   `board_url(slug)` — the career page — and only then pages the API. Making the domain half of
   a composite slug was rejected: it puts a value the user cannot see on the paste path, and
   the page states it on every load.

2. THE OLD `/api/apply/v2/jobs` ENDPOINT IS CLOSED. It answers HTTP 200 with
   `{"message": "Not authorized for PCSX"}` on the eightfold.ai tenants and the SPA HTML on the
   custom domains. `/api/pcsx/search` is what the shipped bundle actually calls, and it needs no
   token, no cookie, no `Referer` and no `X-Requested-With` — a bare GET with a clean jar
   returns real rows.

3. PAGE SIZE IS FIXED AT 10 AND `num` IS IGNORED. `num=50` returns ten rows, not fifty; the
   client bundle hardcodes `num: 10`. Paging is `start`, and `start` past the end returns an
   EMPTY `positions` list rather than wrapping, so termination is on a SHORT PAGE with
   `_MAX_PAGES` as a hard backstop. `count` is used only for an informational completeness
   note. The cost is real and is the reason this provider is last in the github-lists tier
   order: a 1,958-posting board is 196 list requests before a single detail fetch.

4. NO VALIDATORS ANYWHERE. Neither the career page nor `/api/pcsx/search` sends an `ETag` or a
   `Last-Modified`; both answer `cache-control: private, max-age=0, no-cache, no-store`. So
   `observed_validators` is always None, nothing is persisted by the D22 path, no
   `If-None-Match` is ever sent, and `unchanged` is unreachable against the live service. The
   304 branch is kept for symmetry and covered by a mocked 304.

5. `workLocationOption` IS A CLOSED CATALOG AND ITS REMOTE MEMBER IS `remote_local`, NOT
   `"remote"`. Measured: 80 unfiltered rows across three tenants gave `onsite` (72) and
   `hybrid` (8) and nothing else; a `location=remote` search gave 34 rows, every one
   `remote_local`. `"remote"` appears in the bundle only as a LOCATION keyword. An
   out-of-catalog value resolves to `unknown` rather than minting a bucket, and there is no
   location-text fallback — `locations[0]` is literally `"Remote"` on those rows, which would
   make the heuristic look right for the wrong reason and hide the day the catalog changes.

6. A DETAIL 404 IS A FETCH FAILURE, NOT A CLOSE SIGNAL. `position_details` for an unknown id
   answers HTTP 404 `{"status": 404, "error": {"message": "Position not found"}, "data": {}}`.
   Unlike SmartRecruiters' `active: false` — an explicit flag inside a 200 — a 404 is
   indistinguishable from an edge blip, so the id STAYS in `listed_ids` and the posting is
   simply not materialised this run. The cost is that a permanently-404 id is retried every
   scan out of `detail_budget`; the alternative is closing a live requisition on a CDN hiccup.

7. HTTP 405 IS A TRANSIENT THROTTLE, NOT A STRUCTURAL REFUSAL. Measured: the exact search URL
   that answered 405 answered HTTP 200 on four consecutive re-probes minutes later, with no
   change to the request. Untreated it cost run 10 ~2,150 postings across four boards — 76% of
   one of them — and run 11 enumerated 2,440 of a board's 3,803 that had enumerated 3,817 of
   3,817 the run before, same code, same slug. So a 405 is RETRIED (`_get` below), bounded by
   `_THROTTLE_RETRIES` per request and `_THROTTLE_BOARD_BUDGET` per board, with the backoff
   expressed as a raised per-host pace so `core/politeness.Fetcher` stays the only rate limiter.
   Retries and abandonments are COUNTED onto the snapshot, and a single abandonment forces
   `partial`: `apply_board` closes postings only on `complete`, so a board that lost rows to a
   throttle reporting `complete` would hand `CLOSE_AFTER_MISSES` every posting it failed to
   fetch. 405 is deliberately NOT added to `politeness._RETRYABLE_STATUSES`: on every other
   provider a 405 is a genuine method refusal, and the measurement that makes it transient is
   this service's alone.

Detail fetches are bounded and skip known postings (the SmartRecruiters pattern), so
`snapshot.postings` is the newly-fetched subset and `snapshot.listed_ids` carries the FULL live
inventory — otherwise `apply_board` would close every known-but-unrefreshed posting. The
listing carries no description at all, so `body_text` exists only via the detail call and fills
in incrementally across scans. Salary is never mined (D19).

`fetch_board` must never raise: every JSON level is validated as dict/list before use.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from boardwatch.core.clock import to_naive_utc
from boardwatch.core.html_text import html_to_text
from boardwatch.core.models import (
    BoardRequest,
    BoardSnapshot,
    RawPosting,
    RemotePolicy,
    ResponseValidators,
)
from boardwatch.core.politeness import Fetcher, FetchFailure, FetchResult
from boardwatch.providers.base import BoardHealth, health_from_failure

_HOST_SUFFIX = ".eightfold.ai"
_PAGE_SIZE = 10  # server-fixed: `num=50` AND `num=8` both return 10 rows — ignored, not clamped
# 600 pages x 10 = 6000 postings, ~1.5x the largest board measured (3,817 on one tenant,
# 2026-09-06, live in a scratch store: a 300-page backstop cut it at 3,000 and reported the
# shortfall). A backstop only: normal termination is a short page, and a short page is only
# ever the LAST page — measured at start = 0/10/20/100/500 (10 rows each) against start = 1950
# (2 rows, count 1952) on a second board. A board past the backstop reports the shortfall
# through the completeness note in fetch_board rather than closing the postings it never saw.
_MAX_PAGES = 600
# Anything that would make the host slug reinterpretable as a URL with a different authority,
# path or query than the slug says.
_HOST_FORBIDDEN = frozenset(":@?#\\%[]")
# The SPA's boot blob: HTML-escaped JSON in a <code id="pcsx-data"> element. Non-greedy to the
# first closing tag, which is correct because the payload is escaped and cannot contain one.
_PCSX_DATA = re.compile(rb'<code[^>]*id="pcsx-data"[^>]*>(.*?)</code>', re.DOTALL)
# The `domain` value is interpolated into a query string, so it is validated as the
# hostname-shaped token every measured tenant reports rather than trusted and quoted.
_LABEL = r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?"
_DOMAIN_RE = re.compile(rf"^{_LABEL}(\.{_LABEL})+$")
# CLOSED catalog, measured (property 5). Out-of-catalog is `unknown`, never a new bucket.
_WORK_LOCATION: dict[str, RemotePolicy] = {
    "onsite": "onsite",
    "hybrid": "hybrid",
    "remote_local": "remote",
}
_SLUG_FORM = "expected a career-site host, e.g. careers.acme.test or acme.eightfold.ai"
# Property 7. The status this service uses for a throttle. A bare int rather than a set: one
# status has been measured transient here, and a set would invite the next one to be added
# without the re-probe evidence that makes the retry safe.
_THROTTLE_STATUS = 405
# TWO ceilings, bounding two different things. Both are needed and neither substitutes for the
# other.
#
# `_THROTTLE_RETRIES` bounds ONE REQUEST. Two is small because the measurement says the throttle
# clears immediately — the re-probes were 200 on the FIRST retry, four times out of four — so a
# third retry would buy a case never observed and pay for it on every genuinely-405 endpoint.
# With no ceiling at all a permanently-405 host is a hang, which is worse than the lost rows.
#
# `_THROTTLE_BOARD_BUDGET` bounds ONE BOARD, and it is what makes the WALL CLOCK bounded rather
# than only the request count. A per-request ceiling alone leaves the detail loop free to spend
# a full retry chain on each of `detail_fetch_budget` postings (default 50), which at this
# backoff is ~6 minutes added to one board; the listing loop is already bounded to one chain
# because it BREAKS on the first failed page. 12 retries caps the added wall clock at ~60 s per
# board, and a board that needs more than 12 is not being throttled, it is refusing.
_THROTTLE_RETRIES = 2
_THROTTLE_BOARD_BUDGET = 12
# Applied as `Fetcher.get(min_host_delay=...)`, which RAISES this host's pace for the next
# physical attempt and can never lower it. That is the whole reason there is no `sleep` here:
# `Fetcher` already owns this host's clock and its lock, and a second limiter beside it would
# pace against a different notion of "last request" than the one the politeness contract is
# written in. One entry per retry, so the tuple's length and `_THROTTLE_RETRIES` cannot drift.
_THROTTLE_BACKOFF_SECONDS = (2.0, 5.0)


@dataclass
class _ThrottleLedger:
    """What the throttle cost ONE board: retries spent, and requests abandoned to it.

    Mutable and threaded through the whole fetch — bootstrap, listing and details — because
    the per-board budget is a property of the board, not of any one request. `exhausted` is
    the load-bearing one: `fetch_board` reads it, not the error text, to refuse `complete`.
    """

    retries: int = 0
    exhausted: int = 0


def _get(
    fetcher: Fetcher,
    url: str,
    ledger: _ThrottleLedger,
    validators: ResponseValidators | None = None,
) -> FetchResult:
    """One GET, retrying a throttle (property 7) within both ceilings.

    Every non-throttle `FetchFailure` propagates untouched on the FIRST attempt, so a 404, a
    500 or a transport error reaches the caller exactly as it did before this existed — the
    404-is-not-a-close-signal contract (property 6) is unchanged.

    Raises the original `FetchFailure` on exhaustion rather than returning a sentinel. A
    sentinel is precisely how a retry goes silent: the listing pager reads a failure as "stop
    here" and a `None` as "no more pages", and the second one ends the board `complete`.
    """
    for attempt in range(_THROTTLE_RETRIES + 1):
        try:
            return fetcher.get(
                url,
                validators=validators,
                # None on the first attempt: the board's normal pace already applies, and
                # passing 0.0 would read as an override that happens to be inert.
                min_host_delay=None if attempt == 0 else _THROTTLE_BACKOFF_SECONDS[attempt - 1],
            )
        except FetchFailure as exc:
            if exc.status_code != _THROTTLE_STATUS:
                raise
            if attempt == _THROTTLE_RETRIES or ledger.retries >= _THROTTLE_BOARD_BUDGET:
                ledger.exhausted += 1
                raise
            ledger.retries += 1
    raise AssertionError("unreachable: the loop either returns or raises")


def _failed(url: str, error: str, ledger: _ThrottleLedger | None = None) -> BoardSnapshot:
    """A failed snapshot, still carrying the throttle counters.

    `failed` closes nothing, so the counters change no behaviour on this path — they are
    reported because a board the throttle killed at its bootstrap or first page is exactly the
    board whose loss is largest, and a run that could not say so would show it as an ordinary
    failure.
    """
    return BoardSnapshot(
        status="failed", postings=[], url=url, observed_validators=None, error=error,
        throttle_retries=None if ledger is None else ledger.retries,
        throttle_exhausted=None if ledger is None else ledger.exhausted,
    )


def _json_object(content: bytes) -> dict[str, Any] | None:
    """Parsed JSON iff it is an object, else None. Never raises."""
    try:
        obj = json.loads(content)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def _envelope_data(content: bytes) -> dict[str, Any] | None:
    """The `data` object out of the `{status, error, data, metadata}` envelope both API
    endpoints share, or None. The envelope's own `status` is NOT read: a 404 arrives with
    `status: 404` in the body AND as the HTTP status, and the transport-level one is the
    single signal `FetchFailure` already carries."""
    payload = _json_object(content)
    if payload is None:
        return None
    data = payload.get("data")
    return data if isinstance(data, dict) else None


def board_domain(content: bytes) -> str:
    """The tenant's `domain` out of a career page's `pcsx-data` blob.

    Raises ValueError when the element is absent, unparseable, or carries a value that is not
    a plain hostname — every one of which means "this host is not serving an Eightfold career
    site we can page", and none of which may be papered over with a guess: a wrong `domain` is
    a 200 that returns HTML, so an unvalidated value would fail as a parse error one request
    later with nothing pointing back here.
    """
    match = _PCSX_DATA.search(content)
    if match is None:
        raise ValueError("no <code id=\"pcsx-data\"> element: not an Eightfold career page")
    try:
        blob = json.loads(html.unescape(match.group(1).decode("utf-8", "replace")))
    except ValueError as exc:
        raise ValueError(f"pcsx-data is not JSON: {exc}") from exc
    if not isinstance(blob, dict):
        raise ValueError("pcsx-data is not a JSON object")
    domain = blob.get("domain")
    if not isinstance(domain, str) or not _DOMAIN_RE.match(domain.strip().lower()):
        raise ValueError(f"pcsx-data carries no usable domain (got {domain!r})")
    return domain.strip().lower()


def validated_host(slug: str) -> str:
    """The slug as a canonical lowercase hostname, or ValueError.

    board_urls._normalize_slug converts that to UnknownBoardURL so the CLI does not traceback.
    """
    host = slug.strip().lower()
    if not host:
        raise ValueError(_SLUG_FORM)
    if any(c.isspace() or ord(c) < 32 for c in host):
        raise ValueError(f"host {host!r} contains whitespace or a control character")
    if any(c in _HOST_FORBIDDEN for c in host):
        raise ValueError(f"host {host!r} contains a forbidden character")
    if "." not in host or host.startswith(".") or host.endswith("."):
        raise ValueError(f"host {host!r} is not a hostname; {_SLUG_FORM}")
    return host


class EightfoldProvider:
    name = "eightfold"
    # Unbounded like Workday's, and for a stronger reason: an Eightfold tenant is usually on
    # the EMPLOYER's own domain (careers.qualcomm.com, jobs.northropgrumman.com), which no
    # suffix can enumerate. Only the vendor-hosted form is claimable, so `board_hosts` is
    # empty and `.eightfold.ai` is the suffix. THE ACCOMMODATION THIS FORCES, stated so it is
    # not read as a gap: a custom-domain board cannot be added by pasting its URL — nothing
    # tells `parse_board_target` that `careers.qualcomm.com` is Eightfold rather than the
    # employer's own site — and must be added as `eightfold:careers.qualcomm.com`. That is
    # also why `test_each_provider_declares_public_board_hosts` cannot assert a host tuple
    # here, and why an unpasteable custom domain is a REFUSAL (UnregisteredBoardHost) rather
    # than a guess: probing every unknown host for a `pcsx-data` blob is exactly the
    # open-ended classification this repo refuses everywhere else.
    board_hosts: tuple[str, ...] = ()
    board_host_suffixes: tuple[str, ...] = (_HOST_SUFFIX,)
    slug_help = (
        "an Eightfold board is identified by its HOST; paste the career-site root "
        "(https://acme.eightfold.ai/careers), or for an employer-owned domain use "
        "eightfold:careers.acme.test"
    )

    @staticmethod
    def normalize_slug(slug: str) -> str:
        return validated_host(slug)

    @staticmethod
    def slug_from_path(host: str, parts: list[str]) -> str | None:
        """The slug is the HOST, not a path segment. Registered against the `.eightfold.ai`
        suffix, so `acme.eightfold.ai/careers` and `acme.eightfold.ai/careers/job/1` both
        resolve to the one board `acme.eightfold.ai` instead of to boards named `careers`."""
        return host

    def board_url(self, slug: str) -> str:
        """The career PAGE, not the search API: the API cannot be addressed until this page
        has yielded the tenant's `domain` (property 1)."""
        return f"https://{validated_host(slug)}/careers"

    def _search_url(self, host: str, domain: str, start: int) -> str:
        return f"https://{host}/api/pcsx/search?domain={domain}&start={start}"

    def _detail_url(self, host: str, domain: str, posting_id: str) -> str:
        return (
            f"https://{host}/api/pcsx/position_details"
            f"?domain={domain}&position_id={posting_id}"
        )

    def fetch_board(self, fetcher: Fetcher, request: BoardRequest) -> BoardSnapshot:
        ledger = _ThrottleLedger()
        try:
            host = validated_host(request.slug)
        except ValueError as exc:
            return _failed(request.url, f"invalid eightfold slug: {exc}", ledger)
        try:
            boot = _get(fetcher, request.url, ledger, validators=request.validators)
        except FetchFailure as exc:
            return _failed(request.url, str(exc), ledger)
        if boot.not_modified:
            return BoardSnapshot(
                status="unchanged", postings=[], url=request.url,
                observed_validators=None, error=None,
                throttle_retries=ledger.retries, throttle_exhausted=ledger.exhausted,
            )
        try:
            domain = board_domain(boot.content)
        except ValueError as exc:
            return _failed(request.url, f"career page bootstrap: {exc}", ledger)

        listed, total, errors = self._page_listing(fetcher, host, domain, ledger)
        if listed is None:
            return _failed(request.url, errors[0], ledger)

        listed_ids = {str(row["id"]) for row in listed if row.get("id") is not None}
        if total is not None and len(listed_ids) < total:
            errors.append(
                f"incomplete listing: collected {len(listed_ids)} of {total} postings; "
                "treating as partial so unseen postings are not closed"
            )

        budget = request.detail_budget
        # An id-less row is skipped here for the same reason it is kept out of `listed_ids`:
        # it cannot be fetched, deduped or closed. Without the `is not None` test its id
        # stringifies to the literal "None", which would spend a detail request on
        # `position_id=None` and, on any 200, mint a posting keyed "None" — colliding with
        # every other id-less row under `UNIQUE(company_id, provider_posting_id)` and absent
        # from `listed_ids`, so `apply_board` would close it the instant it was written.
        unseen = [
            r for r in listed
            if r.get("id") is not None and str(r["id"]) not in request.known_posting_ids
        ]
        # Captured BEFORE the detail-budget slice rebinds `unseen`, so detail_deferred
        # reflects what the budget actually cut, not the post-truncation length (D-271).
        unseen_before_truncation = unseen
        if len(unseen) > budget:
            errors.append(
                f"detail budget of {budget} exceeded ({len(unseen)} unseen postings); "
                "raise detail_fetch_budget or rescan"
            )
            unseen = unseen[:budget]

        postings: list[RawPosting] = []
        detail_failures = 0
        for row in unseen:
            posting_id = str(row.get("id"))
            try:
                detail_res = _get(fetcher, self._detail_url(host, domain, posting_id), ledger)
            except FetchFailure as exc:
                # Includes the 404 "Position not found" signature: a FAILURE, never a close
                # signal (property 6). The id stays in listed_ids.
                detail_failures += 1
                errors.append(f"posting {posting_id} detail: {exc}")
                continue
            detail = _envelope_data(detail_res.content)
            if not detail:
                detail_failures += 1
                errors.append(f"posting {posting_id} detail: malformed payload")
                continue
            try:
                postings.append(parse_posting(host, row, detail))
            except Exception as exc:  # per-posting isolation
                errors.append(f"posting {posting_id}: {exc}")

        if unseen and detail_failures == len(unseen):
            return _failed(request.url, f"all {len(unseen)} detail fetches failed", ledger)

        if ledger.exhausted:
            errors.append(
                f"throttled: {ledger.exhausted} request(s) still HTTP {_THROTTLE_STATUS} after "
                f"{_THROTTLE_RETRIES} retries; treating as partial so unseen postings are "
                "not closed"
            )
        # NEVER `complete` while a request was abandoned to the throttle, whatever else
        # happened. The condition reads the TYPED counter, not the message above it, so a
        # future edit that reworded or dropped that line cannot silently re-arm the closure —
        # and `apply_board` closes only on `complete`, so re-arming it would hand
        # CLOSE_AFTER_MISSES every posting this board was throttled out of listing.
        if errors or ledger.exhausted:
            status, error = "partial", f"{len(errors)} issue(s): " + "; ".join(errors[:3])
        else:
            status, error = "complete", None
        return BoardSnapshot(
            status=status,
            postings=postings,
            url=request.url,
            # Never populated by this provider: neither endpoint sends a validator
            # (property 4). Echoed rather than hardcoded None so a future service that
            # starts sending one is picked up without a code change.
            observed_validators=boot.observed_validators,
            error=error,
            listed_ids=frozenset(listed_ids),
            board_reported_total=total,
            # DISTINCT ids, not len(listed): an id-less row is a posting we cannot fetch,
            # dedupe or close, and `total - board_enumerated` exists to expose exactly that.
            board_enumerated=len(listed_ids),
            detail_deferred=max(0, len(unseen_before_truncation) - budget),
            throttle_retries=ledger.retries,
            throttle_exhausted=ledger.exhausted,
        )

    def _page_listing(
        self, fetcher: Fetcher, host: str, domain: str, ledger: _ThrottleLedger
    ) -> tuple[list[dict[str, Any]] | None, int | None, list[str]]:
        """(rows, the board's reported count, errors). rows is None iff the FIRST page failed,
        which is the one condition that makes the whole scan `failed` rather than partial —
        a later page failing still leaves a real, if short, inventory."""
        rows: list[dict[str, Any]] = []
        total: int | None = None
        errors: list[str] = []
        for page in range(_MAX_PAGES):
            start = page * _PAGE_SIZE
            try:
                result = _get(fetcher, self._search_url(host, domain, start), ledger)
            except FetchFailure as exc:
                if page == 0:
                    return None, None, [f"listing at start 0: {exc}"]
                errors.append(f"listing at start {start}: {exc}")
                break
            data = _envelope_data(result.content)
            if data is None or not isinstance(data.get("positions"), list):
                message = f"listing at start {start}: invalid payload"
                if page == 0:
                    return None, None, [message]
                errors.append(message)
                break
            if page == 0:
                count = data.get("count")
                total = max(0, int(count)) if isinstance(count, int) else None
            positions = [p for p in data["positions"] if isinstance(p, dict)]
            rows.extend(positions)
            if len(data["positions"]) < _PAGE_SIZE:
                break
        else:
            errors.append(
                f"page backstop of {_MAX_PAGES} reached; listing may be truncated"
            )
        return rows, total, errors

    def healthcheck(self, fetcher: Fetcher, slug: str) -> BoardHealth:
        """DEAD is the career page answering 404. A tenant host that does not resolve at all —
        the shape a mistyped `*.eightfold.ai` subdomain takes, measured — is a transport
        failure and classifies UNREACHABLE, which is the honest answer: nothing was served."""
        try:
            host = validated_host(slug)
        except ValueError:
            return BoardHealth.ERROR
        ledger = _ThrottleLedger()
        try:
            boot = _get(fetcher, self.board_url(slug), ledger)
        except FetchFailure as exc:
            return health_from_failure(exc)
        try:
            domain = board_domain(boot.content)
        except ValueError:
            return BoardHealth.ERROR
        try:
            result = _get(fetcher, self._search_url(host, domain, 0), ledger)
        except FetchFailure as exc:
            return health_from_failure(exc)
        data = _envelope_data(result.content)
        if data is None or not isinstance(data.get("positions"), list):
            return BoardHealth.ERROR
        return BoardHealth.OK if data["positions"] else BoardHealth.EMPTY


def parse_posting(host: str, listed: dict[str, Any], detail: dict[str, Any]) -> RawPosting:
    posting_id = str(listed["id"])
    title = str(listed.get("name") or detail.get("name") or "").strip()
    if not title:
        raise ValueError("empty title")
    department = detail.get("department") or listed.get("department")
    path = str(detail.get("positionUrl") or listed.get("positionUrl") or "")
    url = str(detail.get("publicUrl") or "") or f"https://{host}{path}"
    return RawPosting(
        provider_posting_id=posting_id,
        title=title,
        url=url,
        locations=_locations(detail, listed),
        department=str(department) if department else None,
        remote_policy=_remote_policy(detail, listed),
        posted_at=_epoch_to_naive_utc(listed.get("postedTs") or detail.get("postedTs")),
        # `creationTs` is when the requisition was CREATED, which is earlier than postedTs on
        # every measured row; neither endpoint carries a modification time.
        updated_at=None,
        body_text=html_to_text(str(detail.get("jobDescription") or "").strip()),
        raw_json={"listed": listed, "detail": detail},
    )


def _locations(detail: dict[str, Any], listed: dict[str, Any]) -> list[str]:
    """`locations` is a list on BOTH endpoints; the detail payload additionally carries a
    scalar `location`. `standardizedLocations` is deliberately not preferred — it is
    Eightfold's own normalization ("Bengaluru, KA, IN"), and the employer's own spelling is
    what this repo stores."""
    for source in (detail, listed):
        values = source.get("locations")
        if isinstance(values, list):
            labels = [str(v).strip() for v in values if str(v).strip()]
            if labels:
                return labels
    single = detail.get("location")
    return [str(single).strip()] if single and str(single).strip() else []


def _remote_policy(detail: dict[str, Any], listed: dict[str, Any]) -> RemotePolicy:
    """Closed catalog, no location-text fallback (property 5)."""
    for source in (detail, listed):
        value = source.get("workLocationOption")
        if isinstance(value, str) and value in _WORK_LOCATION:
            return _WORK_LOCATION[value]
    return "unknown"


def _epoch_to_naive_utc(value: Any) -> datetime | None:
    """`postedTs` is epoch SECONDS (measured: 1788652800 -> 2026-09-06). A bool is rejected
    explicitly — `isinstance(True, int)` is True and would date a posting to 1970."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        return to_naive_utc(datetime.fromtimestamp(value, UTC))
    except (OverflowError, OSError, ValueError):
        return None
