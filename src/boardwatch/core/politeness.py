"""Politeness Fetcher (§3.4, D22): identifying UA, per-host serial pacing
(default 1.0 s, floor 0.25 s), tenacity backoff + jitter honoring Retry-After,
conditional GETs, and a JSON POST for providers with no GET form (Workday).

Persistence-free and DB-free in BOTH directions: it sends the validators it is
handed (BoardRequest.validators) and returns the validators it observes; the
coordinator alone persists them, transactionally, on complete applies only
(D22). This module must never import boardwatch.store (lint-enforced).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.metadata import version as package_version
from typing import Any

import httpx
from tenacity import (
    RetryCallState,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from boardwatch.core.models import ResponseValidators
from boardwatch.core.settings import Settings

PER_HOST_DELAY_FLOOR = 0.25
_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


def host_key(url: str) -> str:
    """The key `Fetcher` serializes and paces on.

    Exported so the scan coordinator can order its work by the SAME key the lock uses. A
    scheduler that keyed on its own spelling of the host — `urlsplit().hostname`, the provider
    name, the board slug — would optimize for a partition the lock does not share, and would
    silently stop helping the first time the two disagreed.
    """
    return httpx.URL(url).host or ""


class FetchFailure(Exception):
    """A fetch that produced no usable 200/304; providers map this to a failed snapshot.

    `redirected` records whether the status came from the URL that was requested or from one it
    was sent to — this client follows redirects, so the two are indistinguishable in the status
    alone. Providers ignore it; the liveness probe cannot, because "gone" from a redirect target
    is not evidence the requested posting is gone (`core/liveness.py`).
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        *,
        redirected: bool = False,
        final_url: str = "",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.redirected = redirected
        # WHERE THE NON-200 CAME FROM, when a response was seen at all. `redirected` says only
        # THAT the client moved; a caller resolving a shortener needs to know WHERE, because a
        # redirect target that 404s has still NAMED the board it 404'd on. Empty when no response
        # exists to read it from — the retry-exhausted path below has only the requested URL.
        self.final_url = final_url


class _RetryableStatus(Exception):
    def __init__(self, status_code: int, retry_after: float | None) -> None:
        super().__init__(f"retryable HTTP {status_code}")
        self.status_code = status_code
        self.retry_after = retry_after


@dataclass(frozen=True)
class FetchResult:
    status_code: int
    content: bytes
    not_modified: bool
    observed_validators: ResponseValidators | None
    # WHERE THE RESPONSE ACTUALLY CAME FROM, after this client followed any redirects. The
    # requested URL is not enough for a caller resolving a SHORTENER: `grnh.se/<token>` names no
    # employer, and only the redirect target does. Defaulted and last so the 304 construction
    # below and the contract probe keep working positionally; empty means "no URL was observed",
    # which is the honest reading for a 304 that carries no response body or URL.
    final_url: str = ""


def identifying_user_agent() -> str:
    """The UA D22 owes any board that answers us honestly: our name, version and repository.

    A function rather than a constant, and exported rather than inlined, because a SECOND
    caller now needs the same string: `pipeline.runner` gives the lane client a browser UA for
    the aggregator it talks to, so a lane that reaches a provider's own host has to restore
    this one per request. Two spellings of it would let them drift apart silently, and the one
    that drifted would be the one nobody reads.
    """
    return f"boardwatch/{package_version('boardwatch')} (+https://github.com/mit112/boardwatch)"


class Fetcher:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            headers={"User-Agent": identifying_user_agent()}, timeout=30.0, follow_redirects=True
        )
        self._delay = max(settings.per_host_delay_seconds, PER_HOST_DELAY_FLOOR)
        self._pace_from_start = settings.pace_from_request_start
        self._retry_attempts = settings.retry_attempts
        self._guard = threading.Lock()
        self._host_locks: dict[str, threading.Lock] = {}
        self._last_request_at: dict[str, float] = {}

    @property
    def effective_delay(self) -> float:
        return self._delay

    @property
    def retry_attempts(self) -> int:
        return self._retry_attempts

    def get(
        self,
        url: str,
        validators: ResponseValidators | None = None,
        *,
        headers: Mapping[str, str] | None = None,
        min_host_delay: float | None = None,
    ) -> FetchResult:
        """One GET, optionally carrying caller-supplied request headers.

        `min_host_delay` RAISES this host's pace for this call and can never lower it: the
        effective delay is `max(settings.per_host_delay_seconds, min_host_delay)`. It exists for
        a host that DECLARES a `crawl-delay` stricter than the client's own floor, and it is
        honoured before EVERY PHYSICAL ATTEMPT rather than once per call. That distinction is the
        whole point -- `_send_with_retries` makes up to `retry_attempts` real requests with a
        backoff starting at 0.5s, so a caller that paced once and then hit a 503 would issue its
        retries half a second apart against a host that asked for five seconds, and the pacing
        the caller believed it had applied would be silently absent exactly when the host was
        under stress.

        `headers` exists for THREE callers, and each is documented here so a fourth has to justify
        itself. TWO are in the hiring.cafe lane. Its SEARCH route needs the header set a browser
        sends for a top-level navigation, and that set must not leak onto the other lane sharing
        this client (D-369). Its BOARD route is the opposite direction: the lane client carries
        a browser UA for the aggregator, and a request this lane makes to an ATS provider's own
        host has to restore `identifying_user_agent()` — D22 is owed to a board that answers us
        honestly, whatever the aggregator's edge behaviour made necessary elsewhere. The THIRD is
        the JSON-LD resolver lane, which restores `identifying_user_agent()` for the same reason on
        the ATS posting pages it fetches. Client-level headers could express none of them.

        They are merged UNDER the conditional-GET validators, so a caller cannot suppress an
        `If-None-Match` by passing one of its own — the validator half is this client's
        contract with the coordinator, not the caller's to override.
        """
        return self._dispatch("GET", url, validators, None, headers, min_host_delay)

    def post_json(
        self,
        url: str,
        body: dict[str, Any],
        validators: ResponseValidators | None = None,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> FetchResult:
        """A JSON POST through the SAME per-host lock, pacing, backoff and status
        classification as get(). Workday's CXS search endpoint has no GET form (a GET
        returns 400), and a 2000-posting board is 100+ requests to one host, so routing
        POST through the existing per-host serialization is the point, not a formality.

        `headers` is the same escape hatch `get()` documents, and it has ONE caller: the Indeed
        lane, whose endpoint answers only to that vendor's own app headers. It cannot be a
        client-level header set for the reason `get()`'s own note gives — one `Fetcher` serves
        every lane, and those headers must not leak onto a request to any other host. Merged
        UNDER the conditional-GET validators, exactly as `get()` merges them."""
        return self._dispatch("POST", url, validators, body, headers, None)

    def _dispatch(
        self,
        method: str,
        url: str,
        validators: ResponseValidators | None,
        json_body: dict[str, Any] | None,
        headers: Mapping[str, str] | None,
        min_host_delay: float | None = None,
    ) -> FetchResult:
        host = host_key(url)
        with self._host_lock(host):  # same-host requests serialize for their full duration
            self._pace(host, min_host_delay)
            # Stamping BEFORE the send makes the delay an interval between request STARTS;
            # stamping in the `finally` makes it a gap between the previous END and the next
            # start, which is the shipped default. The stamp is written in both arms and the
            # lock is held across the whole block, so the two cannot race and a raising request
            # still advances the clock — a failing host must not be retried faster than a
            # healthy one.
            if self._pace_from_start:
                self._last_request_at[host] = time.monotonic()
            try:
                return self._send_with_retries(
                    method, url, validators, json_body, headers, min_host_delay
                )
            finally:
                if not self._pace_from_start:
                    self._last_request_at[host] = time.monotonic()

    def _host_lock(self, host: str) -> threading.Lock:
        with self._guard:
            return self._host_locks.setdefault(host, threading.Lock())

    def _pace(self, host: str, min_host_delay: float | None = None) -> None:
        # `max`, never a replacement: an override may only make this client MORE polite. A caller
        # passing a smaller number than the configured floor gets the floor.
        delay = max(self._delay, min_host_delay or 0.0)
        last = self._last_request_at.get(host)
        if last is not None:
            remaining = delay - (time.monotonic() - last)
            if remaining > 0:
                time.sleep(remaining)

    def _send_with_retries(
        self,
        method: str,
        url: str,
        validators: ResponseValidators | None,
        json_body: dict[str, Any] | None,
        headers: Mapping[str, str] | None,
        min_host_delay: float | None = None,
    ) -> FetchResult:
        floor = max(min_host_delay or 0.0, 0.0)

        def _wait(retry_state: RetryCallState) -> float:
            base = wait_exponential_jitter(initial=0.5, max=8.0)(retry_state)
            exc = retry_state.outcome.exception() if retry_state.outcome else None
            if isinstance(exc, _RetryableStatus) and exc.retry_after is not None:
                return max(base, exc.retry_after, floor)
            # A host that declares a crawl-delay is owed it between PHYSICAL attempts too, not
            # only between calls. Without this term the backoff starts at 0.5s and a declared
            # five-second delay is honoured on the first request of a run and on no retry of it.
            return max(base, floor)

        try:
            for attempt in Retrying(
                # deliberately NOT widened to RequestError: a redirect loop or a corrupt
                # body will not fix itself, so it must fail fast rather than be retried.
                retry=retry_if_exception_type((httpx.TransportError, _RetryableStatus)),
                stop=stop_after_attempt(self._retry_attempts),
                wait=_wait,
                reraise=True,
            ):
                with attempt:
                    return self._send_once(method, url, validators, json_body, headers)
        except _RetryableStatus as exc:
            raise FetchFailure(
                f"HTTP {exc.status_code} after {self._retry_attempts} attempts for {url}",
                status_code=exc.status_code,
            ) from exc
        except httpx.TransportError as exc:
            raise FetchFailure(
                f"transport error after {self._retry_attempts} attempts for {url}: {exc}"
            ) from exc
        except httpx.RequestError as exc:
            # TransportError is a RequestError, so it MUST be caught above this clause.
            # What lands here is TooManyRedirects / DecodingError etc. — not retried, but
            # still converted, so providers' `except FetchFailure` and scan/health.py's
            # probe_health cover them instead of tracebacking.
            raise FetchFailure(f"request error for {url}: {exc}") from exc
        raise AssertionError("unreachable: Retrying either returns or raises")

    def _send_once(
        self,
        method: str,
        url: str,
        validators: ResponseValidators | None,
        json_body: dict[str, Any] | None,
        extra_headers: Mapping[str, str] | None,
    ) -> FetchResult:
        headers: dict[str, str] = dict(extra_headers or {})
        if validators is not None:
            if validators.etag:
                headers["If-None-Match"] = validators.etag
            if validators.last_modified:
                headers["If-Modified-Since"] = validators.last_modified
        response = self._client.request(method, url, headers=headers, json=json_body)
        if response.status_code == 304:
            return FetchResult(304, b"", True, None)
        if response.status_code in _RETRYABLE_STATUSES:
            raise _RetryableStatus(response.status_code, _parse_retry_after(response))
        if response.status_code != 200:
            raise FetchFailure(
                f"HTTP {response.status_code} for {url}",
                status_code=response.status_code,
                redirected=bool(response.history),
                final_url=str(response.url),
            )
        etag = response.headers.get("ETag")
        last_modified = response.headers.get("Last-Modified")
        observed = (
            ResponseValidators(etag=etag, last_modified=last_modified)
            if etag or last_modified
            else None
        )
        return FetchResult(200, response.content, False, observed, str(response.url))


def _parse_retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None  # HTTP-date form: ignore; exponential backoff still applies
