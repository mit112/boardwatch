"""Phenom People career-site provider (live-verified 2026-09-06 against three sites).

Phenom hosts a career site on the EMPLOYER's own domain and serves the whole board from one
JSON-RPC-ish endpoint: `POST https://{host}/widgets`, where the request body's `ddoKey` names
the widget being asked for. Verified against `jobs.baesystems.com` (`global`/`en_global`),
`www.pgcareers.com` (`us`/`en`) and `jobs.battelle.org` (`us`/`en`): the envelope, the row
fields and the detail widget are identical on all three; only `country` and `lang` differ.

Six measured properties drive this design.

1. IDENTITY IS A TRIPLE, AND THE HOSTNAMES ARE UNBOUNDED. A board is {host, country, lang},
   carried as the composite slug "{host}/{country}/{lang}". The host is the employer's OWN
   domain, so there is no paste host and no host SUFFIX either — the Workday escape hatch does
   not apply. `board_hosts = ()` with no `board_host_suffixes`, which means a pasted Phenom URL
   raises `UnregisteredBoardHost` and a board is added through the qualified
   `phenom:{host}/{country}/{lang}` form only.

2. `board_url` IS A PSEUDO-KEY AND IS NEVER FETCHED. `BoardRequest.url` is the http_cache key
   and must be one stable string per board — but the fetch is a POST to one URL per HOST, and
   the country/lang that distinguish two boards on one host live in the BODY. So `board_url`
   returns `https://{host}/widgets#refineSearch/{country}/{lang}`: the fragment is never sent
   by any HTTP client, exists only to keep the key distinct per board, and NO GET IS EVER MADE
   TO IT. Every request this module issues goes to `_post_url` (`https://{host}/widgets`).

3. NO CONDITIONAL FETCH, SO VALIDATORS ARE IGNORED. The endpoint answers
   `cache-control: no-cache, no-store, must-revalidate` and sends neither `ETag` nor
   `Last-Modified` (measured on the raw response headers). `request.validators` is therefore not
   passed to the fetcher and `observed_validators` is always None: nothing is persisted by the
   D22 path, no `If-None-Match` is ever sent, and `unchanged` is unreachable. There is no 304
   branch because there is no way to reach one.

4. `size` CLAMPS AT 500, SILENTLY. `size=1000` returns 500 rows, not an error. Pagination is
   `from`/`size`; a `from` past the end returns an empty `jobs` list rather than wrapping, so a
   SHORT PAGE is a sound termination condition (`_MAX_PAGES` is a backstop only).

5. DETAIL IS A SECOND WIDGET, AND ITS ddoKey IS `jobDetail` — SINGULAR. `jobDetails` returns
   `{"status":"failure"}` with no widget envelope at all. Detail fetches are bounded by
   `request.detail_budget` and SKIP postings already in `request.known_posting_ids` (the
   SmartRecruiters pattern), so `snapshot.postings` is the newly-fetched subset and
   `snapshot.listed_ids` carries the FULL live inventory — otherwise `apply_board` would close
   every known-but-unrefreshed posting.

6. `applyUrl` USUALLY POINTS SOMEWHERE ELSE. It is the underlying ATS's apply link
   (`sjobs.brassring.com` for one measured site, `pg.wd5.myworkdayjobs.com` for another) and is
   EMPTY on a third. It is used only when it is on the board's own host; otherwise the URL is
   built as `https://{host}/{country}/{lang_short}/job/{jobId}`, which was fetched and returned
   200 with the posting's own title on all three sites. `lang_short` is `lang` up to the first
   underscore, and that is not cosmetic: `jobs.baesystems.com/global/en_global/job/{id}`
   REDIRECTS to the board root while `.../global/en/job/{id}` serves the posting.

THE TEASER FALLBACK IS A KNOWN COMPROMISE, NOT A FEATURE. When a detail fetch fails, the row is
still emitted with `descriptionTeaser` as its body so the posting is not lost, and every such id
is named in the snapshot's error string — never silently. But detail fetches skip known ids, so
a row that lands with a teaser body KEEPS it until something re-details it. `postings
reparse-bodies` cannot repair it either: the stored `raw_json` has no detail to re-read.

`remote_policy` is read from the LOCATION alone: three sites express a remote posting as the
literal city `Remote` (measured: `Remote, GA, United States`), and nothing in the payload
distinguishes hybrid from onsite, so those two are never claimed. Salary is never mined (D19),
though `salaryMin`/`salaryMax`/`payRange` are present on the detail payload.
`fetch_board` must never raise: every JSON level is validated as dict/list before use.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from boardwatch.core.clock import to_naive_utc
from boardwatch.core.html_text import html_to_text
from boardwatch.core.models import BoardRequest, BoardSnapshot, RawPosting, RemotePolicy
from boardwatch.core.politeness import Fetcher, FetchFailure
from boardwatch.providers.base import BoardHealth, health_from_failure

_PAGE_SIZE = 500  # server-side maximum; size=1000 returns 500 rows, it is not an error
# 40 x 500 = 20,000 postings. A backstop only: normal termination is a short page.
_MAX_PAGES = 40
_LIST_DDO = "refineSearch"
_DETAIL_DDO = "jobDetail"  # SINGULAR: "jobDetails" answers {"status":"failure"}
_SLUG_FORM = "expected host/country/lang, e.g. jobs.acme.test/global/en_global"
# Anything that would make the composite slug reinterpretable as a URL with a different
# authority, path or query than the triple says.
_HOST_FORBIDDEN = frozenset(":@?#\\%[]/")
# A location whose CITY is `Remote` (or `Remote - US`, `Remote, US`). Word-anchored so a real
# city that merely starts with those letters cannot match.
_REMOTE_CITY = re.compile(r"^remote\b", re.IGNORECASE)


def split_slug(slug: str) -> tuple[str, str, str]:
    """(host, country, lang) from the composite slug, host lowercased.

    Country and lang keep their stored spelling: they are echoed verbatim into the request body
    and into the posting URL path, and nothing here has measured them to be case-insensitive.
    Raises ValueError on anything that is not a valid triple; `board_urls._normalize_slug`
    converts that to UnknownBoardURL so the CLI does not traceback."""
    parts = slug.strip().split("/")
    if len(parts) != 3 or not all(p.strip() for p in parts):
        raise ValueError(_SLUG_FORM)
    host = parts[0].strip().lower()
    if any(c.isspace() or ord(c) < 32 for c in host) or any(c in _HOST_FORBIDDEN for c in host):
        raise ValueError(f"host {host!r} contains whitespace or a forbidden character")
    country, lang = parts[1].strip(), parts[2].strip()
    for label, value in (("country", country), ("lang", lang)):
        if any(c.isspace() or ord(c) < 32 or c in _HOST_FORBIDDEN for c in value):
            raise ValueError(f"{label} {value!r} contains whitespace or a forbidden character")
    return host, country, lang


def _failed(url: str, error: str) -> BoardSnapshot:
    return BoardSnapshot(
        status="failed", postings=[], url=url, observed_validators=None, error=error,
    )


def _json_object(content: bytes) -> dict[str, Any] | None:
    """Parsed JSON iff it is an object, else None. Never raises."""
    try:
        obj = json.loads(content)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def _widget(content: bytes, ddo_key: str) -> dict[str, Any] | None:
    """The named widget's envelope iff it answered `status: 200`, else None.

    Two distinct refusals collapse to None here and that is deliberate — the caller reports the
    same thing for both: a whole-response `{"status":"failure"}` (what a wrong `ddoKey` gets),
    and a present envelope carrying a non-200 `status`."""
    payload = _json_object(content)
    if payload is None:
        return None
    widget = payload.get(ddo_key)
    if not isinstance(widget, dict) or widget.get("status") != 200:
        return None
    return widget


def _rows(widget: dict[str, Any]) -> list[dict[str, Any]] | None:
    """`data.jobs` as a list of objects, or None when either level is the wrong shape."""
    data = widget.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        return None
    return [row for row in data["jobs"] if isinstance(row, dict)]


class PhenomProvider:
    name = "phenom"
    # The career site is on the EMPLOYER's own domain, so there is neither a paste host nor a
    # bounded host suffix to register. A pasted Phenom URL is not recognized by design.
    board_hosts: tuple[str, ...] = ()
    # The same marker jibe declares, and for the same reason: `board_hosts = ()` alone is
    # indistinguishable from a provider whose hosts nobody got round to declaring, which is
    # exactly what `test_each_provider_declares_public_board_hosts` exists to catch. Nothing
    # consumes it -- it is what makes the emptiness legibly deliberate, and greppable.
    custom_domain_slug = True
    # the slug is a host/country/lang TRIPLE, so board_urls must let "/" through the
    # qualified form for this provider. phenom is the only provider that is BOTH: a custom
    # domain AND a composite slug, because the country/lang that distinguish two boards on one
    # host live in the request BODY and cannot be read off the host.
    composite_slug = True

    @staticmethod
    def normalize_slug(slug: str) -> str:
        """Lowercase the HOST only (property 1). Country and lang are echoed into the request
        body and the posting path verbatim, so folding their case would be a guess."""
        return "/".join(split_slug(slug))

    def board_url(self, slug: str) -> str:
        """The stable per-board cache/identity key. NEVER FETCHED — see property 2. Raises
        ValueError on a malformed stored slug; scan/coordinator.py and scan/health.py guard
        the call."""
        host, country, lang = split_slug(slug)
        return f"https://{host}/widgets#{_LIST_DDO}/{country}/{lang}"

    def _post_url(self, host: str) -> str:
        """The ONLY URL this module ever sends a request to."""
        return f"https://{host}/widgets"

    def _list_body(self, country: str, lang: str, offset: int) -> dict[str, Any]:
        return {
            "lang": lang,
            "deviceType": "desktop",
            "country": country,
            "pageName": "search-results",
            "ddoKey": _LIST_DDO,
            "sortBy": "",
            "subsearch": "",
            "from": offset,
            "jobs": True,
            "counts": True,
            "all_fields": ["category", "country", "state", "city"],
            "size": _PAGE_SIZE,
            "clearAll": False,
            "jdsource": "facets",
            "isSliderEnable": False,
            "pageId": "page12",
            "siteType": "external",
            "keywords": "",
            "global": True,
            "selected_fields": {},
            "locationData": {},
        }

    def _detail_body(self, country: str, lang: str, job_id: str) -> dict[str, Any]:
        return {
            "lang": lang,
            "deviceType": "desktop",
            "country": country,
            "pageName": "job-details",
            "ddoKey": _DETAIL_DDO,
            "jobId": job_id,
            "siteType": "external",
            "pageId": "page12",
        }

    def fetch_board(self, fetcher: Fetcher, request: BoardRequest) -> BoardSnapshot:
        try:
            host, country, lang = split_slug(request.slug)
        except ValueError as exc:
            return _failed(request.url, f"invalid phenom slug: {exc}")
        post_url = self._post_url(host)

        errors: list[str] = []
        listed: list[dict[str, Any]] = []
        total: int | None = None

        for page_index in range(_MAX_PAGES):
            offset = page_index * _PAGE_SIZE
            try:
                # validators are deliberately NOT passed: the endpoint issues none (property 3)
                page = fetcher.post_json(post_url, self._list_body(country, lang, offset))
            except FetchFailure as exc:
                if page_index == 0:
                    return _failed(request.url, str(exc))
                errors.append(f"page at offset {offset}: {exc}")
                break
            widget = _widget(page.content, _LIST_DDO)
            rows = _rows(widget) if widget is not None else None
            if widget is None or rows is None:
                if page_index == 0:
                    return _failed(
                        request.url, f"invalid board payload: no usable {_LIST_DDO} widget"
                    )
                errors.append(f"page at offset {offset}: invalid payload")
                break
            if page_index == 0:
                try:
                    total = max(0, int(widget["totalHits"]))
                except (KeyError, TypeError, ValueError):
                    return _failed(request.url, "invalid board payload: missing 'totalHits'")
            listed.extend(rows)
            if len(rows) < _PAGE_SIZE:
                # THE termination condition. A `from` past the end answers an EMPTY jobs list
                # rather than wrapping, so a short page really is the tail.
                break
        else:
            errors.append(
                f"page cap of {_MAX_PAGES} pages reached; listing may be incomplete, "
                "treating as partial so unseen postings are not closed"
            )

        by_id: dict[str, dict[str, Any]] = {}
        for row in listed:
            job_id = row.get("jobId")
            if job_id is not None and str(job_id).strip():
                by_id.setdefault(str(job_id), row)
        listed_ids = frozenset(by_id)
        if total is not None and len(listed_ids) < total:
            errors.append(
                f"incomplete listing: collected {len(listed_ids)} of {total} postings; "
                "treating as partial so unseen postings are not closed"
            )

        budget = request.detail_budget
        unseen = [(pid, row) for pid, row in by_id.items() if pid not in request.known_posting_ids]
        # Captured BEFORE the detail-budget slice below rebinds `unseen`, so detail_deferred
        # reflects what the budget actually cut, not the post-truncation length (D-271).
        unseen_before_truncation = unseen
        if len(unseen) > budget:
            errors.append(
                f"detail budget of {budget} exceeded ({len(unseen)} unseen postings); "
                "raise detail_fetch_budget or rescan"
            )
            unseen = unseen[:budget]

        postings: list[RawPosting] = []
        teaser_only: list[str] = []
        for pid, row in unseen:
            detail: dict[str, Any] | None = None
            try:
                res = fetcher.post_json(post_url, self._detail_body(country, lang, pid))
            except FetchFailure as exc:
                errors.append(f"posting {pid} detail: {exc}")
            else:
                widget = _widget(res.content, _DETAIL_DDO)
                data = widget.get("data") if widget is not None else None
                job = data.get("job") if isinstance(data, dict) else None
                if isinstance(job, dict):
                    detail = job
                else:
                    errors.append(f"posting {pid} detail: malformed payload")
            if detail is None:
                teaser_only.append(pid)
            try:
                postings.append(parse_posting(row, detail, host, country, lang))
            except Exception as exc:  # per-posting isolation
                errors.append(f"posting {pid}: {exc}")
        if teaser_only:
            # NEVER silent: these rows carry `descriptionTeaser` as their body, and detail
            # fetches skip known ids, so nothing re-details them on its own. FIRST in the list,
            # because `error` keeps only the leading few issues and one per-posting failure line
            # per fallen-back row would otherwise push the summary out of the message entirely.
            errors.insert(
                0,
                f"{len(teaser_only)} posting(s) fell back to descriptionTeaser for body_text: "
                + ", ".join(sorted(teaser_only)[:10]),
            )

        if errors:
            status, error = "partial", f"{len(errors)} issue(s): " + "; ".join(errors[:3])
        else:
            status, error = "complete", None
        return BoardSnapshot(
            status=status,
            postings=postings,
            url=request.url,
            observed_validators=None,  # the endpoint issues none (property 3)
            error=error,
            listed_ids=listed_ids,
            board_reported_total=total,
            # DISTINCT ids, not len(listed): id-less rows and cross-page duplicates must not
            # hide a listing shortfall (D-271).
            board_enumerated=len(listed_ids),
            detail_deferred=max(0, len(unseen_before_truncation) - budget),
        )

    def healthcheck(self, fetcher: Fetcher, slug: str) -> BoardHealth:
        """NOTE: DEAD is only reachable through a transport-level or HTTP failure on the
        employer's own host. A live Phenom site with no matching postings answers 200 with
        `totalHits: 0`, which is EMPTY; `dead_status` is a sentinel no real HTTP status can
        equal so a 404 (a retired site, a WAF blip) classifies as ERROR rather than DEAD."""
        try:
            host, country, lang = split_slug(slug)
        except ValueError:
            return BoardHealth.ERROR
        try:
            result = fetcher.post_json(
                self._post_url(host), self._list_body(country, lang, 0)
            )
        except FetchFailure as exc:
            return health_from_failure(exc, dead_status=-1)
        widget = _widget(result.content, _LIST_DDO)
        rows = _rows(widget) if widget is not None else None
        if rows is None:
            return BoardHealth.ERROR
        return BoardHealth.OK if rows else BoardHealth.EMPTY


def parse_posting(
    listed: dict[str, Any], detail: dict[str, Any] | None, host: str, country: str, lang: str
) -> RawPosting:
    """One posting from its listed row plus its detail payload, which is None when the detail
    fetch failed — the body then falls back to the listed row's `descriptionTeaser`."""
    posting_id = str(listed["jobId"])
    source = detail if detail is not None else {}
    title = str(listed.get("title") or source.get("title") or "").strip()
    if not title:
        raise ValueError("empty title")
    category = str(listed.get("category") or source.get("category") or "").strip()
    body = source.get("description") if detail is not None else listed.get("descriptionTeaser")
    return RawPosting(
        provider_posting_id=posting_id,
        title=title,
        url=_posting_url(listed, posting_id, host, country, lang),
        locations=_locations(listed, source),
        department=category or None,
        remote_policy=_remote_policy(listed, source),
        posted_at=_iso_to_naive_utc(listed.get("postedDate") or source.get("postedDate")),
        # No update timestamp is on the LIST payload, and a detail-only field would be present
        # on the newly-detailed subset alone — an incrementally-filled column nothing reads.
        updated_at=None,
        body_text=html_to_text(str(body or "").strip()),
        raw_json={"listed": listed, "detail": detail or {}},
    )


def _posting_url(
    listed: dict[str, Any], posting_id: str, host: str, country: str, lang: str
) -> str:
    """`applyUrl` when it lives on the board's own host, else the career site's own job page.

    `applyUrl` is the UNDERLYING ATS's apply link on every site measured (brassring, workday) and
    is empty on a third, so the fallback is the normal path rather than the exception. The path
    takes `lang` up to the first underscore: `/global/en_global/job/{id}` redirects to the board
    root, `/global/en/job/{id}` serves the posting."""
    apply_url = str(listed.get("applyUrl") or "").strip()
    if apply_url.startswith((f"https://{host}/", f"http://{host}/")):
        return apply_url
    return f"https://{host}/{country}/{lang.split('_', 1)[0]}/job/{posting_id}"


def _locations(listed: dict[str, Any], detail: dict[str, Any]) -> list[str]:
    label = str(listed.get("cityStateCountry") or detail.get("cityStateCountry") or "").strip()
    if label:
        return [label]
    parts = [listed.get(key) or detail.get(key) for key in ("city", "state", "country")]
    joined = ", ".join(str(p).strip() for p in parts if p and str(p).strip())
    return [joined] if joined else []


def _remote_policy(listed: dict[str, Any], detail: dict[str, Any]) -> RemotePolicy:
    """Remote is expressed as the literal CITY `Remote` and nothing else in the payload
    separates hybrid from onsite, so those two are never claimed."""
    city = str(listed.get("city") or detail.get("city") or "").strip()
    return "remote" if _REMOTE_CITY.match(city) else "unknown"


def _iso_to_naive_utc(value: Any) -> datetime | None:
    """`2026-09-03T15:02:59.985+0000` is what both payloads carry; `fromisoformat` reads the
    compact offset natively on the supported Pythons."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return to_naive_utc(datetime.fromisoformat(value.strip().replace("Z", "+00:00")))
    except ValueError:
        return None
