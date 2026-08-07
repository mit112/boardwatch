"""Unit tests for the shared LLM retry-with-backoff helper (P3 slice 5a, D-040).

No network calls and no real sleeps: `time.sleep` is monkeypatched throughout,
either to a no-op or to a recorder, so these run instantly and deterministically.
"""

from __future__ import annotations

import time

import pytest

from boardwatch.llm.client import LLMError, LLMTransientError
from boardwatch.llm.retry import request_with_retry


def test_retries_transient_error_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        if calls["n"] < 2:
            raise LLMTransientError("HTTP 429: rate limited")
        return "ok"

    assert request_with_retry(fn) == "ok"
    assert calls["n"] == 2


def test_honors_retry_after_over_exponential_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    slept: list[float] = []
    monkeypatch.setattr(time, "sleep", slept.append)
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        if calls["n"] < 2:
            raise LLMTransientError("HTTP 429: rate limited", retry_after=5.0)
        return "ok"

    request_with_retry(fn)
    assert slept and slept[0] >= 5.0


def test_attempts_exhausted_reraises_transient_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        raise LLMTransientError("HTTP 503: down")

    with pytest.raises(LLMTransientError):
        request_with_retry(fn, attempts=3)
    assert calls["n"] == 3


def test_non_transient_error_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        raise LLMError("HTTP 400: bad request")

    with pytest.raises(LLMError):
        request_with_retry(fn)
    assert calls["n"] == 1
