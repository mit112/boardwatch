"""Retry-with-backoff for the LLM adapter layer (P3 slice 5a, D-040).

Ports `core/politeness.py`'s tenacity pattern — retry only on a distinguishable
transient failure, honor `Retry-After` when the provider sends one, otherwise
`wait_exponential_jitter` — into a single helper both LLM adapters share, so
the backoff logic exists in exactly one place.

This sits BELOW `tailor/rewrite/lane.py`'s per-call budget metering: the lane
counts one `client.complete()` invocation as one budget unit, and the retry
loop lives entirely inside that call, so N retries of one logical completion
still consume exactly one unit.

Must never import boardwatch.store — mirrors core/politeness.py's fetch-side
boundary; the LLM adapter layer has no business touching persistence.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

import httpx
from tenacity import (
    RetryCallState,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from boardwatch.llm.client import LLMTransientError

DEFAULT_ATTEMPTS = 4

_T = TypeVar("_T")


def parse_retry_after(response: httpx.Response) -> float | None:
    """Parse a `Retry-After` header as seconds; ignore the HTTP-date form
    (exponential backoff still applies in that case)."""
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def request_with_retry(fn: Callable[[], _T], *, attempts: int = DEFAULT_ATTEMPTS) -> _T:
    """Run `fn`, retrying ONLY on `LLMTransientError`.

    Any other exception — a non-transient `LLMError`, an invalid-body error —
    propagates immediately, unretried. Backoff honors the raised error's
    `retry_after` when present; otherwise `wait_exponential_jitter(initial=0.5,
    max=8.0)`. After `attempts` tries are exhausted, the last
    `LLMTransientError` is re-raised.
    """

    def _wait(retry_state: RetryCallState) -> float:
        base = wait_exponential_jitter(initial=0.5, max=8.0)(retry_state)
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        if isinstance(exc, LLMTransientError) and exc.retry_after is not None:
            return max(base, exc.retry_after)
        return base

    for attempt in Retrying(
        retry=retry_if_exception_type(LLMTransientError),
        stop=stop_after_attempt(attempts),
        wait=_wait,
        reraise=True,
    ):
        with attempt:
            return fn()
    raise AssertionError("unreachable: Retrying either returns or raises")
