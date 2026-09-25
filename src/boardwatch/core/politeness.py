"""Politeness Fetcher (§3.4, D22): identifying UA, per-host serial pacing
(default 1.0 s, floor 0.25 s), tenacity backoff + jitter honoring Retry-After,
conditional GETs, and a JSON POST for providers with no GET form (Workday).

Persistence-free and DB-free in BOTH directions: it sends the validators it is
handed (BoardRequest.validators) and returns the validators it observes; the
coordinator alone persists them, transactionally, on complete applies only
(D22). This module must never import boardwatch.store (lint-enforced).
"""

from __future__ import annotations

import socket
import ssl
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from importlib.metadata import version as package_version
from typing import Any, TypeVar

import httpcore
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


#: A `Retry-After` longer than this is not a wait, it is an outage, and is reported as one.
#: The header was honoured uncapped INSIDE the per-host lock, so one 429 carrying
#: `Retry-After: 3600` parked every board on that host for an hour — and the shared-host
#: providers are exactly where it bites: Greenhouse, Lever and SmartRecruiters each serve
#: their whole fleet from one host, so one tenant's rate limit stalled the scan. A minute is
#: the longest pause a run whose scan already takes ~3 hours can absorb without the board
#: budget becoming a fiction.
RETRY_AFTER_CAP_SECONDS = 60.0


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


class HostPacing:
    """Per-host lock and last-request-time state, shared by every `Fetcher` in the process.

    T41 (D-475): this used to live on the `Fetcher` instance, so the scan's `Fetcher` and the
    lane stage's own instance (`pipeline/runner.py::_lane_fetcher`) paced a host they both
    reach independently of each other — up to 2 in flight and 2 req/s where the promise to
    that third party is 1. The pacing contract (`per_host_delay_seconds`) is per PROCESS, not
    per instance, so this state must be too.
    """

    def __init__(self) -> None:
        self.guard = threading.Lock()
        self.host_locks: dict[str, threading.Lock] = {}
        self.last_request_at: dict[str, float] = {}


#: The default every `Fetcher` shares unless a caller injects its own registry.
_PROCESS_PACING = HostPacing()


@dataclass
class BoardClock:
    """One board's deadline on the thread running it, as `Fetcher.under_deadline` yields it.

    `tripped` is set when this clock refuses or cuts a request (T228). The thread then ends
    within a request of the cap, the same instant the coordinator fails the board at, so the
    worker reads this to give the cap's verdict itself rather than the provider's account of
    the clock's failures — whichever of the two sees the cap first then records the same thing.
    """

    at: float
    seconds: float
    tripped: bool = False


_T = TypeVar("_T")

#: The instant (`time.monotonic()`) the request running on THIS thread must be done by, set by
#: `Fetcher` around each send and body read; absent outside one. Thread-local because the
#: `ConnectionPool` runs a request on its caller's thread, so a pooled connection reads the
#: deadline of the request currently using it, never the one that opened it.
_REQUEST_DEADLINE = threading.local()


class DeadlineExceeded(httpcore.TimeoutException):
    """The backend's own timeout (T209): the socket op had no time left before the deadline."""


def _bounded(op: Callable[[float | None], _T], timeout: float | None) -> _T:
    """Run one socket op with `min(timeout, seconds left)`, re-read on EVERY call.

    This is what a per-request timeout cannot do (T205): httpcore reads that value once per
    phase and each `recv` restarts it, so a host sending a byte every 0.1s never trips it. Here
    each `recv` gets only what is left, so the trickle ends at the deadline however it is paced.
    A timeout that fired on the clamp rather than on the caller's own value is the deadline's.
    """
    at: float | None = getattr(_REQUEST_DEADLINE, "at", None)
    if at is None:
        return op(timeout)
    left = at - time.monotonic()
    if left <= 0:
        raise DeadlineExceeded("no time left before the deadline")
    clamped = timeout is None or left < timeout
    try:
        return op(left if clamped else timeout)
    except httpcore.TimeoutException as exc:
        if clamped:
            raise DeadlineExceeded("the deadline passed during a socket operation") from exc
        raise


#: The most `_DeadlineStream.write` hands one bounded `write` call.
_WRITE_SLICE = 16 * 1024


class _DeadlineStream(httpcore.NetworkStream):
    def __init__(self, stream: httpcore.NetworkStream) -> None:
        self._stream = stream

    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        return _bounded(lambda t: self._stream.read(max_bytes, t), timeout)

    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        # In slices, each bounded on its own: httpcore's `write` loops `send()` and re-arms the
        # timeout on every partial send, so one bounded call lets a slow reader outlast it.
        for start in range(0, len(buffer), _WRITE_SLICE):
            _bounded(partial(self._stream.write, buffer[start:start + _WRITE_SLICE]), timeout)

    def close(self) -> None:
        self._stream.close()

    def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.NetworkStream:
        return _DeadlineStream(
            _bounded(lambda t: self._stream.start_tls(ssl_context, server_hostname, t), timeout)
        )

    def get_extra_info(self, info: str) -> Any:
        return self._stream.get_extra_info(info)


class ResolverSaturated(httpcore.ConnectError):
    """A lookup refused at once, without a thread, because `_MAX_LOOKUPS` are already running.

    A `ConnectError`, not a `DeadlineExceeded` (T227): neither the request's clock nor the
    board's ran out, so it must not be reported as either — the board's would record the board
    `board deadline exceeded` before its cap (T228). As a transport error it is retried and
    ends UNREACHABLE, which a host this process cannot resolve now is.
    """


#: The most `getaddrinfo` threads the process runs at once (T227). A fetching thread waits on at
#: most one lookup, and at most 38 fetch at once: `scan_workers` board threads (32 at the Settings
#: ceiling), one per lane (five registered) and the main thread. The other 26 are room for
#: lookups abandoned at a deadline: a resolver outage holds at most 64 threads, and even a
#: full-width scan is refused a lookup only once 26 are stuck.
_MAX_LOOKUPS = 64


class _Lookup:
    """One `getaddrinfo(host, port)` on a daemon thread, shared by every caller that asks for the
    same (host, port) while it runs; the thread removes it from `_LOOKUPS` as it ends."""

    def __init__(self, host: str, port: int) -> None:
        self.outcome: list[list[tuple[Any, ...]] | Exception] = []
        self.thread = threading.Thread(
            target=self._run, args=(host, port), name=f"resolve {host}", daemon=True
        )

    def _run(self, host: str, port: int) -> None:
        try:
            self.outcome.append(socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM))
        except Exception as exc:
            self.outcome.append(exc)
        finally:
            with _LOOKUPS_GUARD:
                del _LOOKUPS[(host, port)]


_LOOKUPS: dict[tuple[str, int], _Lookup] = {}
_LOOKUPS_GUARD = threading.Lock()


def _resolve(host: str, port: int, timeout: float | None) -> list[tuple[Any, ...]]:
    """`getaddrinfo` as `create_connection` calls it, on a worker thread joined for `timeout`.

    The resolver ignores every socket timeout (T226), and the call itself cannot be cancelled:
    on expiry the daemon thread is left to finish in the background, bounded only by the OS
    resolver's own timeout. So a caller for a (host, port) already being looked up waits on that
    lookup rather than starting another, and past `_MAX_LOOKUPS` none is started (T227). That,
    beside the TLS handshake trickle, is a known limit — the request ends at its deadline, but
    up to `_MAX_LOOKUPS` threads can outlive their requests while a resolver answers nothing.
    """
    with _LOOKUPS_GUARD:
        lookup = _LOOKUPS.get((host, port))
        if lookup is None:
            if len(_LOOKUPS) >= _MAX_LOOKUPS:
                raise ResolverSaturated(f"{len(_LOOKUPS)} lookups running; not resolving {host}")
            lookup = _Lookup(host, port)
            lookup.thread.start()  # under the guard: its own removal waits for the entry below
            _LOOKUPS[(host, port)] = lookup
    lookup.thread.join(timeout)
    if not lookup.outcome:
        raise httpcore.ConnectTimeout(f"resolving {host} timed out")
    result = lookup.outcome[0]
    if isinstance(result, OSError):
        raise httpcore.ConnectError(str(result)) from result
    if isinstance(result, Exception):
        raise result
    return result


class _DeadlineBackend(httpcore.NetworkBackend):
    """httpcore's own `SyncBackend`, with every stream it opens bounded by `_bounded`."""

    def __init__(self) -> None:
        self._backend = httpcore.SyncBackend()

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.NetworkStream:
        """`socket.create_connection`'s address loop, run here so each attempt is `_bounded`.

        Handed the time left once, `create_connection` applied it to EACH resolved address in
        turn, so a host with n black-holed addresses held the call (n-1)×left past its deadline
        (T226). Each attempt goes to `SyncBackend` by numeric address, which keeps its socket
        options, `TCP_NODELAY` and exception mapping; as there, an attempt that fails on the
        caller's own timeout moves on, and all failing raises the last attempt's error.
        """
        addresses = _bounded(partial(_resolve, host, port), timeout)
        if not addresses:
            raise httpcore.ConnectError("getaddrinfo returns an empty list")
        failure: httpcore.ConnectError | httpcore.ConnectTimeout
        for *_, sockaddr in addresses:
            try:
                return _DeadlineStream(_bounded(partial(
                    self._backend.connect_tcp, str(sockaddr[0]), port,
                    local_address=local_address, socket_options=socket_options,
                ), timeout))
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                failure = exc
        raise failure

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.NetworkStream:
        return _DeadlineStream(_bounded(
            lambda t: self._backend.connect_unix_socket(path, t, socket_options), timeout
        ))

    def sleep(self, seconds: float) -> None:
        self._backend.sleep(seconds)


#: httpcore → httpx, as `httpx.HTTPTransport` maps them (its table is private). Looked up along
#: the raised exception's MRO, so the most specific class wins: `DeadlineExceeded` becomes an
#: `httpx.TimeoutException` whose `__cause__` is still the backend's own exception.
_HTTPCORE_TO_HTTPX: dict[type[Exception], type[httpx.TransportError]] = {
    httpcore.TimeoutException: httpx.TimeoutException,
    httpcore.ConnectTimeout: httpx.ConnectTimeout,
    httpcore.ReadTimeout: httpx.ReadTimeout,
    httpcore.WriteTimeout: httpx.WriteTimeout,
    httpcore.PoolTimeout: httpx.PoolTimeout,
    httpcore.NetworkError: httpx.NetworkError,
    httpcore.ConnectError: httpx.ConnectError,
    httpcore.ReadError: httpx.ReadError,
    httpcore.WriteError: httpx.WriteError,
    httpcore.ProxyError: httpx.ProxyError,
    httpcore.UnsupportedProtocol: httpx.UnsupportedProtocol,
    httpcore.ProtocolError: httpx.ProtocolError,
    httpcore.LocalProtocolError: httpx.LocalProtocolError,
    httpcore.RemoteProtocolError: httpx.RemoteProtocolError,
}


@contextmanager
def _httpx_errors() -> Iterator[None]:
    try:
        yield
    except Exception as exc:
        mapped = next(
            (_HTTPCORE_TO_HTTPX[c] for c in type(exc).__mro__ if c in _HTTPCORE_TO_HTTPX), None
        )
        if mapped is None:
            raise
        raise mapped(str(exc)) from exc


class _ResponseStream(httpx.SyncByteStream):
    def __init__(self, stream: Iterable[bytes]) -> None:
        self._stream = stream

    def __iter__(self) -> Iterator[bytes]:
        with _httpx_errors():
            yield from self._stream

    def close(self) -> None:
        close = getattr(self._stream, "close", None)
        if close is not None:
            close()


class DeadlineTransport(httpx.BaseTransport):
    """`httpx.HTTPTransport`'s default configuration over a pool on `_DeadlineBackend` (T209).

    Built from public extension points only: httpx 0.28's `HTTPTransport` takes no network
    backend, and reaching its pool would mean a private attribute. What this gives up is
    `HTTPTransport`'s proxy support — see `Fetcher.__init__`.
    """

    def __init__(self) -> None:
        limits = httpx.Limits()
        self._pool = httpcore.ConnectionPool(
            ssl_context=httpx.create_ssl_context(),
            max_connections=limits.max_connections,
            max_keepalive_connections=limits.max_keepalive_connections,
            keepalive_expiry=limits.keepalive_expiry,
            network_backend=_DeadlineBackend(),
        )

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        assert isinstance(request.stream, httpx.SyncByteStream)
        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )
        with _httpx_errors():
            response = self._pool.handle_request(core_request)
        assert isinstance(response.stream, Iterable)
        return httpx.Response(
            status_code=response.status,
            headers=response.headers,
            stream=_ResponseStream(response.stream),
            extensions=response.extensions,
        )

    def close(self) -> None:
        self._pool.close()


class Fetcher:
    def __init__(
        self,
        settings: Settings,
        client: httpx.Client | None = None,
        *,
        pacing: HostPacing | None = None,
        user_agent: str | None = None,
    ) -> None:
        # The ONE place a production `Fetcher` client is built (T209): every caller that does
        # not inject a test client gets `DeadlineTransport`, and `user_agent` is how the lane
        # stage gets its browser UA without building a client of its own. `trust_env=False`
        # because httpx routes an environment proxy through its OWN `HTTPTransport`, which would
        # bypass the deadline backend silently; a proxy is therefore not honoured.
        self._client = client or httpx.Client(
            headers={"User-Agent": user_agent or identifying_user_agent()},
            timeout=30.0,
            follow_redirects=True,
            transport=DeadlineTransport(),
            trust_env=False,
        )
        self._delay = max(settings.per_host_delay_seconds, PER_HOST_DELAY_FLOOR)
        self._pace_from_start = settings.pace_from_request_start
        self._retry_attempts = settings.retry_attempts
        self._deadline = settings.fetch_deadline_seconds
        self._pacing = pacing if pacing is not None else _PROCESS_PACING
        self._board = threading.local()  # `.deadline`: the `BoardClock` while a board runs

    @contextmanager
    def under_deadline(self, at: float, seconds: float) -> Iterator[BoardClock]:
        """Bound every request this THREAD makes, until the block exits, by the instant `at`
        (T192c). The coordinator gives up on a board at `board_deadline_seconds`, but it cannot
        interrupt the thread, and a provider that catches each failed detail fetch and moves on
        would keep the worker — and its host — for up to `detail_budget` more fresh fetch
        deadlines. Under this scope each request's deadline is `min(its own, at)`, and one that
        starts past `at` fails at once, so the thread ends within one request of the cap.
        `seconds` is only the budget the failure names. The yielded clock says whether it
        ended any request (T228)."""
        clock = self._board.deadline = BoardClock(at, seconds)
        try:
            yield clock
        finally:
            del self._board.deadline

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
        self._check_board_deadline(url)  # past the board cap: no lock, no pacing, no send
        with self._host_lock(host):  # same-host requests serialize for their full duration
            self._pace(host, min_host_delay)
            # Stamping BEFORE the send makes the delay an interval between request STARTS;
            # stamping in the `finally` makes it a gap between the previous END and the next
            # start, which is the shipped default. The stamp is written in both arms and the
            # lock is held across the whole block, so the two cannot race and a raising request
            # still advances the clock — a failing host must not be retried faster than a
            # healthy one.
            if self._pace_from_start:
                self._pacing.last_request_at[host] = time.monotonic()
            try:
                return self._send_with_retries(
                    method, url, validators, json_body, headers, min_host_delay
                )
            finally:
                if not self._pace_from_start:
                    self._pacing.last_request_at[host] = time.monotonic()

    def _host_lock(self, host: str) -> threading.Lock:
        with self._pacing.guard:
            return self._pacing.host_locks.setdefault(host, threading.Lock())

    def _pace(self, host: str, min_host_delay: float | None = None) -> None:
        # `max`, never a replacement: an override may only make this client MORE polite. A caller
        # passing a smaller number than the configured floor gets the floor.
        delay = max(self._delay, min_host_delay or 0.0)
        last = self._pacing.last_request_at.get(host)
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
        # ONE clock for the whole call, every attempt and backoff included (T192). The thing this
        # bounds is how long the per-host lock is held, and `_dispatch` holds it across all of
        # them; a per-attempt budget would multiply by `retry_attempts`, and a retry is exactly
        # what reconnected to the trickling host and stalled again in run 473.
        deadline = time.monotonic() + self._deadline

        def _wait(retry_state: RetryCallState) -> float:
            base = wait_exponential_jitter(initial=0.5, max=8.0)(retry_state)
            exc = retry_state.outcome.exception() if retry_state.outcome else None
            if isinstance(exc, _RetryableStatus) and exc.retry_after is not None:
                # Bounded by construction: `_send_once` refuses anything over
                # RETRY_AFTER_CAP_SECONDS before it can become a `_RetryableStatus`.
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
                    return self._send_once(
                        method, url, validators, json_body, headers, deadline
                    )
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
        deadline: float,
    ) -> FetchResult:
        self._check_deadline(url, deadline)  # a backoff can spend the budget before an attempt
        headers: dict[str, str] = dict(extra_headers or {})
        if validators is not None:
            if validators.etag:
                headers["If-None-Match"] = validators.etag
            if validators.last_modified:
                headers["If-Modified-Since"] = validators.last_modified
        request = self._client.build_request(method, url, headers=headers, json=json_body)
        return self._classify(self._read_response(request, url, deadline), url)

    def _read_response(self, request: httpx.Request, url: str, deadline: float) -> httpx.Response:
        """Send `request` and read its body in a loop that can look at the clock.

        httpx has no total deadline — its timeout is per OPERATION, and a host trickling a byte
        every few seconds never trips it. The clock is checked per RAW network chunk (T192b): a
        compressed body can trickle for minutes while decoding to nothing, so a check per
        DECODED chunk is never reached. The raw bytes are then rebuilt into a response whose
        `.read()` decodes its `Content-Encoding` exactly as the eager read did. `stream=`, not
        `content=`: `content=` adds a `Content-Length` to a chunked response's headers.

        Redirects are followed HERE, not by httpx: with `follow_redirects=True` httpx reads each
        redirect's body itself before the stream is handed back, outside this clock. Each hop is
        sent unfollowed and read under the same deadline, up to the client's `max_redirects`,
        exactly where httpx's own loop would stop. A hop to another host stays under the caller's
        per-host lock and this request's deadline, as it always did.
        """
        history: list[httpx.Response] = []
        while True:
            self._check_deadline(url, deadline)  # every hop, not only the first
            if len(history) > self._client.max_redirects:
                raise httpx.TooManyRedirects("Exceeded maximum allowed redirects.", request=request)
            # The HEADER phase is bounded by httpx's per-operation timeout alone (T205): each
            # operation gets `min(its own, seconds left)`, so a host that goes SILENT mid-headers
            # times out at the deadline, re-raised as the deadline's `FetchFailure`, which the
            # retry predicate does not match. It cannot stop a header TRICKLE on its own: httpcore
            # reads the timeout once per phase and each byte restarts it.
            request.extensions["timeout"] = self._timeout_within(deadline)
            # Underneath it, `DeadlineTransport`'s backend reads this instant on every socket op
            # (T209), which is what bounds a TRICKLE, on a fresh or a reused pooled connection.
            # A client injected without that transport keeps only the two clocks above.
            _REQUEST_DEADLINE.at = self._effective_deadline(deadline)
            try:
                streamed = self._client.send(request, stream=True, follow_redirects=False)
                response = self._read_body(streamed, url, deadline)
            except httpx.TimeoutException as exc:
                if isinstance(exc.__cause__, DeadlineExceeded):
                    raise self._deadline_failure(url, deadline)  # noqa: B904 — keeps __context__
                self._check_deadline(url, deadline)
                raise
            finally:
                del _REQUEST_DEADLINE.at
            response.history = list(history)
            if not self._client.follow_redirects or streamed.next_request is None:
                return response
            history.append(response)
            request = streamed.next_request

    def _read_body(self, streamed: httpx.Response, url: str, deadline: float) -> httpx.Response:
        try:
            if streamed.is_stream_consumed:
                return streamed  # an in-memory transport handed back a body already read
            raw: list[bytes] = []
            for chunk in streamed.iter_raw():
                raw.append(chunk)
                self._check_deadline(url, deadline)
        finally:
            streamed.close()
        rebuilt = httpx.Response(
            status_code=streamed.status_code, headers=streamed.headers,
            stream=httpx.ByteStream(b"".join(raw)), request=streamed.request,
            extensions=streamed.extensions, default_encoding=streamed.default_encoding,
        )
        rebuilt.read()
        return rebuilt

    def _effective_deadline(self, deadline: float) -> float:
        board: BoardClock | None = getattr(self._board, "deadline", None)
        return deadline if board is None else min(deadline, board.at)

    def _timeout_within(self, deadline: float) -> dict[str, float | None]:
        at = self._effective_deadline(deadline)
        # Floored above zero: a zero socket timeout is non-blocking, not "already expired". An
        # operation starting at or after this instant cannot time out before `at`.
        left = max(at - time.monotonic(), 0.001)
        return {
            op: left if limit is None else min(limit, left)
            for op, limit in self._client.timeout.as_dict().items()
        }

    def _deadline_failure(self, url: str, deadline: float) -> FetchFailure:
        """The failure `_check_deadline` raises for whichever deadline bound this request —
        decided by which instant is earlier, not by the clock, since the backend's timeout can
        fire a hair before `time.monotonic()` reaches the instant it was clamped to."""
        board: BoardClock | None = getattr(self._board, "deadline", None)
        if board is not None and board.at <= deadline:
            return self._board_failure(board, url)
        return FetchFailure(
            f"fetch deadline {self._deadline:g}s exceeded for {url}", status_code=None
        )

    def _check_board_deadline(self, url: str) -> None:
        board: BoardClock | None = getattr(self._board, "deadline", None)
        if board is not None and time.monotonic() >= board.at:
            raise self._board_failure(board, url)

    @staticmethod
    def _board_failure(board: BoardClock, url: str) -> FetchFailure:
        board.tripped = True  # T228: every failure the board's clock raises passes through here
        return FetchFailure(
            f"board deadline {board.seconds:g}s exceeded for {url}", status_code=None
        )

    def _check_deadline(self, url: str, deadline: float) -> None:
        self._check_board_deadline(url)  # the effective deadline is min(request, board)
        # A `FetchFailure`, not an httpx timeout: the retry predicate does not match it, so it is
        # never retried, and it is the one exception every provider already maps to `failed`.
        # `status_code=None` is the transport-level shape `health_from_failure` reads as
        # UNREACHABLE — which a host that trickled for the whole budget is.
        if time.monotonic() >= deadline:
            raise FetchFailure(
                f"fetch deadline {self._deadline:g}s exceeded for {url}", status_code=None
            )

    def _classify(self, response: httpx.Response, url: str) -> FetchResult:
        # EVERY body has been read before the status is looked at, as the eager read did
        # (T192b): a transport error mid-body is then a transport error — retried, and
        # UNREACHABLE on exhaustion — whatever the status, rather than a 404 classified DEAD
        # from its headers.
        if response.status_code == 304:
            return FetchResult(304, b"", True, None)
        if response.status_code in _RETRYABLE_STATUSES:
            retry_after = _parse_retry_after(response)
            if retry_after is not None and retry_after > RETRY_AFTER_CAP_SECONDS:
                # Refused HERE rather than capped in `_wait`, so the over-cap value never
                # reaches the retry machinery at all and no sleep of any length is taken for
                # it. `status_code=None` is not a loss of information: it is the transport-
                # level shape `providers.base.health_from_failure` already maps to
                # `BoardHealth.UNREACHABLE`, which is precisely what this host is for the
                # rest of the run. Reusing it keeps that catalog closed.
                raise FetchFailure(
                    f"HTTP {response.status_code} for {url} with Retry-After: {retry_after:g}s, "
                    f"beyond the {RETRY_AFTER_CAP_SECONDS:g}s cap — treating the host as "
                    "unreachable for this run rather than holding its lock",
                    status_code=None,
                    final_url=str(response.url),
                )
            raise _RetryableStatus(response.status_code, retry_after)
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
