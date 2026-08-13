"""Lane-death classification, latching, and factory wiring (P3 slice 5, D-146)."""

import time
from pathlib import Path

import httpx
import pytest
import respx

from boardwatch.core.secrets import LLM_API_KEY_ENV
from boardwatch.core.settings import LLMTier, Settings
from boardwatch.llm.anthropic import AnthropicClient
from boardwatch.llm.client import (
    LaneDeathReason,
    LLMError,
    LLMLaneDeadError,
    lane_death_reason,
)
from boardwatch.llm.factory import build_client
from boardwatch.llm.openai_compat import OpenAICompatClient
from boardwatch.llm.retry import DEFAULT_ATTEMPTS, safe_json
from boardwatch.llm.run_client import RunScopedClient

_TABLE = {
    "billing_error": LaneDeathReason.CREDIT_EXHAUSTED,
    "authentication_error": LaneDeathReason.CREDENTIAL_INVALID,
}


def test_lane_dead_error_carries_a_typed_reason():
    exc = LLMLaneDeadError("HTTP 403", reason=LaneDeathReason.CREDIT_EXHAUSTED)
    assert exc.reason is LaneDeathReason.CREDIT_EXHAUSTED
    # It must remain catchable as the existing base class, so every current
    # `except LLMError` site keeps working unchanged.
    assert isinstance(exc, LLMError)


def test_classifier_maps_a_catalogued_type():
    body = {"error": {"type": "billing_error", "message": "credit balance too low"}}
    assert lane_death_reason(body, table=_TABLE) is LaneDeathReason.CREDIT_EXHAUSTED


def test_classifier_reads_the_code_field_too():
    # OpenAI-compatible providers put the token in `code`, not `type`.
    body = {"error": {"code": "authentication_error"}}
    assert lane_death_reason(body, table=_TABLE) is LaneDeathReason.CREDENTIAL_INVALID


@pytest.mark.parametrize(
    "body",
    [
        None,                                  # unparseable body
        [],                                     # non-object root
        "forbidden",                            # string root
        {},                                     # empty object
        {"error": "forbidden"},                 # error is a string, not an object
        {"error": {}},                          # no type/code at all
        {"error": {"type": 7}},                 # non-string type
        {"error": {"type": "unknown_error"}},   # out of catalog
        {"error": {"code": None}},              # null code
    ],
)
def test_classifier_never_raises_and_returns_none_for_unclassifiable(body):
    # A classifier that raises would land in extract_llm.py's blanket `except`
    # and reproduce the exact silent success this slice removes.
    assert lane_death_reason(body, table=_TABLE) is None


def test_safe_json_returns_none_instead_of_raising():
    assert safe_json(httpx.Response(403, text="not json")) is None
    assert safe_json(httpx.Response(403, json={"error": {"type": "x"}})) == {
        "error": {"type": "x"}
    }


@pytest.fixture(autouse=True)
def _no_real_sleeps(monkeypatch: pytest.MonkeyPatch) -> None:
    # Retry backoff must never cost real wall-clock time in tests (D-040).
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)


_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

# Hand-written from Anthropic's documented error bodies -- NOT generated from
# the mapping under test, which would agree with itself (spec §7.1 test 1).
_ANTHROPIC_CASES = [
    (402, "billing_error", LaneDeathReason.CREDIT_EXHAUSTED),
    (401, "authentication_error", LaneDeathReason.CREDENTIAL_INVALID),
    (403, "permission_error", LaneDeathReason.MODEL_FORBIDDEN),
]


@pytest.mark.parametrize(("status", "error_type", "expected"), _ANTHROPIC_CASES)
@respx.mock
def test_anthropic_classifies_lane_death(status, error_type, expected):
    route = respx.post(_ANTHROPIC_URL).mock(
        return_value=httpx.Response(status, json={"error": {"type": error_type}})
    )
    with pytest.raises(LLMLaneDeadError) as caught:
        AnthropicClient("m", "k").complete("hi")
    assert caught.value.reason is expected
    # Terminal, so it must not be retried.
    assert route.call_count == 1


def test_anthropic_cases_cover_every_reason():
    # Read the catalog at RUN TIME. A hard-coded list would let the mapping
    # silently cover a subset and still pass (D-142: a 4-class list passed
    # 98/98 while covering 5 of 13).
    assert {expected for _, _, expected in _ANTHROPIC_CASES} == set(LaneDeathReason)


@respx.mock
def test_anthropic_unknown_error_type_is_not_lane_death():
    respx.post(_ANTHROPIC_URL).mock(
        return_value=httpx.Response(400, json={"error": {"type": "invalid_request_error"}})
    )
    with pytest.raises(LLMError) as caught:
        AnthropicClient("m", "k").complete("hi")
    assert not isinstance(caught.value, LLMLaneDeadError)


@respx.mock
def test_anthropic_429_without_a_death_token_still_retries():
    route = respx.post(_ANTHROPIC_URL).mock(return_value=httpx.Response(429))
    with pytest.raises(LLMError):
        AnthropicClient("m", "k").complete("hi")
    assert route.call_count == DEFAULT_ATTEMPTS


@respx.mock
def test_anthropic_lane_death_on_a_retryable_status_is_not_retried():
    # Deliberately synthetic: Anthropic does not document `billing_error` on a
    # 429 (429 isn't in _ANTHROPIC_CASES for that reason). This pairing exists
    # only to lock the ORDER of the two checks -- lane death must be read
    # before the retryable-status branch, even when the status is one that
    # would otherwise be retried. Do not "correct" this back to 403.
    route = respx.post(_ANTHROPIC_URL).mock(
        return_value=httpx.Response(429, json={"error": {"type": "billing_error"}})
    )
    with pytest.raises(LLMLaneDeadError) as caught:
        AnthropicClient("m", "k").complete("hi")
    assert caught.value.reason is LaneDeathReason.CREDIT_EXHAUSTED
    assert route.call_count == 1


_OPENAI_URL = "https://api.example.com/v1/chat/completions"


def _openai() -> OpenAICompatClient:
    return OpenAICompatClient("https://api.example.com/v1", "m", "k")


@respx.mock
def test_openai_compat_401_is_credential_death():
    route = respx.post(_OPENAI_URL).mock(return_value=httpx.Response(401))
    with pytest.raises(LLMLaneDeadError) as caught:
        _openai().complete("hi")
    assert caught.value.reason is LaneDeathReason.CREDENTIAL_INVALID
    assert route.call_count == 1


@respx.mock
def test_openai_compat_402_is_credit_exhausted():
    # DeepSeek signals an exhausted balance as HTTP 402.
    respx.post(_OPENAI_URL).mock(return_value=httpx.Response(402))
    with pytest.raises(LLMLaneDeadError) as caught:
        _openai().complete("hi")
    assert caught.value.reason is LaneDeathReason.CREDIT_EXHAUSTED


@respx.mock
def test_openai_compat_429_with_insufficient_quota_is_terminal_not_retried():
    # OpenAI signals an exhausted balance as 429 + code `insufficient_quota`.
    # Left to the status check alone this is retried 4x per posting and then
    # swallowed -- the silent-success defect at 4x the call volume.
    route = respx.post(_OPENAI_URL).mock(
        return_value=httpx.Response(429, json={"error": {"code": "insufficient_quota"}})
    )
    with pytest.raises(LLMLaneDeadError) as caught:
        _openai().complete("hi")
    assert caught.value.reason is LaneDeathReason.CREDIT_EXHAUSTED
    assert route.call_count == 1


@respx.mock
def test_openai_compat_429_with_credit_balance_exhausted_is_terminal_not_retried():
    # OpenAI's current docs lead with `error.code == "credit_balance_exhausted"`
    # for exhausted balance, additive alongside the older `insufficient_quota`
    # token real bodies still carry.
    route = respx.post(_OPENAI_URL).mock(
        return_value=httpx.Response(
            429, json={"error": {"code": "credit_balance_exhausted"}}
        )
    )
    with pytest.raises(LLMLaneDeadError) as caught:
        _openai().complete("hi")
    assert caught.value.reason is LaneDeathReason.CREDIT_EXHAUSTED
    assert route.call_count == 1


@respx.mock
def test_openai_compat_429_without_the_token_still_retries():
    # The narrowing must remove exactly one terminal case from the retryable
    # set -- ordinary rate limiting keeps D-040's backoff.
    route = respx.post(_OPENAI_URL).mock(return_value=httpx.Response(429))
    with pytest.raises(LLMError) as caught:
        _openai().complete("hi")
    assert not isinstance(caught.value, LLMLaneDeadError)
    assert route.call_count == DEFAULT_ATTEMPTS


@respx.mock
def test_openai_compat_bare_403_is_not_lane_death():
    # Deliberate: on an arbitrary proxy a 403 does not prove credential death,
    # and mis-latching would suppress a lane that is merely misrouted.
    respx.post(_OPENAI_URL).mock(return_value=httpx.Response(403))
    with pytest.raises(LLMError) as caught:
        _openai().complete("hi")
    assert not isinstance(caught.value, LLMLaneDeadError)


class _CountingClient:
    """Records how many calls reached the underlying adapter."""

    def __init__(self, exc: Exception | None = None) -> None:
        self.calls = 0
        self._exc = exc

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.calls += 1
        if self._exc is not None:
            raise self._exc
        return "ok"


def test_wrapper_delegates_while_healthy():
    inner = _CountingClient()
    client = RunScopedClient(inner)
    assert client.complete("hi") == "ok"
    assert inner.calls == 1
    assert client.dead_reason is None


def test_wrapper_latches_and_stops_touching_the_network():
    inner = _CountingClient(
        LLMLaneDeadError("dead", reason=LaneDeathReason.CREDIT_EXHAUSTED)
    )
    client = RunScopedClient(inner)
    for _ in range(5):
        with pytest.raises(LLMLaneDeadError) as caught:
            client.complete("hi")
        assert caught.value.reason is LaneDeathReason.CREDIT_EXHAUSTED
    # Asserted on the INNER counter, never the wrapper's self-report: a
    # component's self-report is not verification (CLAUDE.md).
    assert inner.calls == 1
    assert client.dead_reason is LaneDeathReason.CREDIT_EXHAUSTED
    assert client.calls_attempted == 1


def test_wrapper_does_not_latch_on_ordinary_failures():
    inner = _CountingClient(LLMError("boom"))
    client = RunScopedClient(inner)
    for _ in range(3):
        with pytest.raises(LLMError):
            client.complete("hi")
    assert inner.calls == 3
    assert client.dead_reason is None


def _settings(tmp_path: Path, **llm) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "cfg",
        llm=LLMTier(enabled=True, model="m", **llm),
    )


@pytest.mark.parametrize(
    ("provider", "base_url", "url"),
    [
        ("anthropic", None, _ANTHROPIC_URL),
        ("openai", "https://api.example.com/v1", _OPENAI_URL),
    ],
)
@respx.mock
def test_build_client_wraps_every_adapter_branch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, provider, base_url, url
):
    # Routed through the REAL build_client with the HTTP layer stubbed. Do NOT
    # monkeypatch build_client here: doing so is what lets the whole wrapper be
    # reverted with every other test still green (spec §7.0).
    monkeypatch.setenv(LLM_API_KEY_ENV, "a-real-key")
    route = respx.post(url).mock(
        return_value=httpx.Response(401, json={"error": {"type": "authentication_error"}})
    )
    kwargs = {"provider": provider}
    if base_url is not None:
        kwargs["base_url"] = base_url
    client = build_client(_settings(tmp_path, **kwargs))
    assert client is not None

    for _ in range(2):
        with pytest.raises(LLMLaneDeadError):
            client.complete("hi")
    # One network call for two completes -- the latch is installed in production.
    assert route.call_count == 1


def test_build_client_still_returns_none_when_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setenv(LLM_API_KEY_ENV, "a-real-key")
    settings = Settings(
        data_dir=tmp_path / "data", config_dir=tmp_path / "cfg", llm=LLMTier(enabled=False)
    )
    assert build_client(settings) is None


def test_build_client_still_returns_none_without_a_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.delenv(LLM_API_KEY_ENV, raising=False)
    assert build_client(_settings(tmp_path, provider="anthropic")) is None
