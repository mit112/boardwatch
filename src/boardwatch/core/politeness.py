"""Politeness Fetcher (§3.4, D22): identifying UA, per-host serial pacing
(default 1.0 s, floor 0.25 s), tenacity backoff + jitter honoring Retry-After,
conditional GETs.

Persistence-free and DB-free in BOTH directions: it sends the validators it is
handed (BoardRequest.validators) and returns the validators it observes; the
coordinator alone persists them, transactionally, on complete applies only
(D22). This module must never import boardwatch.store (lint-enforced).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from importlib.metadata import version as package_version

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


class FetchFailure(Exception):
    """A fetch that produced no usable 200/304; providers map this to a failed snapshot."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


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


class Fetcher:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        ua = f"boardwatch/{package_version('boardwatch')} (+https://github.com/mit112/boardwatch)"
        self._client = client or httpx.Client(
            headers={"User-Agent": ua}, timeout=30.0, follow_redirects=True
        )
        self._delay = max(settings.per_host_delay_seconds, PER_HOST_DELAY_FLOOR)
        self._retry_attempts = settings.retry_attempts
        self._guard = threading.Lock()
        self._host_locks: dict[str, threading.Lock] = {}
        self._last_request_at: dict[str, float] = {}

    @property
    def effective_delay(self) -> float:
        return self._delay

    def get(self, url: str, validators: ResponseValidators | None = None) -> FetchResult:
        host = httpx.URL(url).host or ""
        with self._host_lock(host):  # same-host requests serialize for their full duration
            self._pace(host)
            try:
                return self._get_with_retries(url, validators)
            finally:
                self._last_request_at[host] = time.monotonic()

    def _host_lock(self, host: str) -> threading.Lock:
        with self._guard:
            return self._host_locks.setdefault(host, threading.Lock())

    def _pace(self, host: str) -> None:
        last = self._last_request_at.get(host)
        if last is not None:
            remaining = self._delay - (time.monotonic() - last)
            if remaining > 0:
                time.sleep(remaining)

    def _get_with_retries(self, url: str, validators: ResponseValidators | None) -> FetchResult:
        def _wait(retry_state: RetryCallState) -> float:
            base = wait_exponential_jitter(initial=0.5, max=8.0)(retry_state)
            exc = retry_state.outcome.exception() if retry_state.outcome else None
            if isinstance(exc, _RetryableStatus) and exc.retry_after is not None:
                return max(base, exc.retry_after)
            return base

        try:
            for attempt in Retrying(
                retry=retry_if_exception_type((httpx.TransportError, _RetryableStatus)),
                stop=stop_after_attempt(self._retry_attempts),
                wait=_wait,
                reraise=True,
            ):
                with attempt:
                    return self._get_once(url, validators)
        except _RetryableStatus as exc:
            raise FetchFailure(
                f"HTTP {exc.status_code} after {self._retry_attempts} attempts for {url}",
                status_code=exc.status_code,
            ) from exc
        except httpx.TransportError as exc:
            raise FetchFailure(
                f"transport error after {self._retry_attempts} attempts for {url}: {exc}"
            ) from exc
        raise AssertionError("unreachable: Retrying either returns or raises")

    def _get_once(self, url: str, validators: ResponseValidators | None) -> FetchResult:
        headers: dict[str, str] = {}
        if validators is not None:
            if validators.etag:
                headers["If-None-Match"] = validators.etag
            if validators.last_modified:
                headers["If-Modified-Since"] = validators.last_modified
        response = self._client.get(url, headers=headers)
        if response.status_code == 304:
            return FetchResult(304, b"", True, None)
        if response.status_code in _RETRYABLE_STATUSES:
            raise _RetryableStatus(response.status_code, _parse_retry_after(response))
        if response.status_code != 200:
            raise FetchFailure(
                f"HTTP {response.status_code} for {url}", status_code=response.status_code
            )
        etag = response.headers.get("ETag")
        last_modified = response.headers.get("Last-Modified")
        observed = (
            ResponseValidators(etag=etag, last_modified=last_modified)
            if etag or last_modified
            else None
        )
        return FetchResult(200, response.content, False, observed)


def _parse_retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None  # HTTP-date form: ignore; exponential backoff still applies
