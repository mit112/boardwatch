import time

import httpx
import pytest
import respx

from boardwatch.llm.client import LLMError, LLMTransientError
from boardwatch.llm.openai_compat import OpenAICompatClient
from boardwatch.llm.retry import DEFAULT_ATTEMPTS


@pytest.fixture(autouse=True)
def _no_real_sleeps(monkeypatch: pytest.MonkeyPatch) -> None:
    # Retry backoff must never cost real wall-clock time in tests (D-040).
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)


@respx.mock
def test_openai_compat_returns_message_content():
    respx.post("https://api.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": "[]"}}]})
    )
    c = OpenAICompatClient("https://api.example.com/v1", "m", "k")
    assert c.complete("hi", system="s") == "[]"


@respx.mock
def test_openai_compat_raises_llmerror_on_5xx():
    # Persistent 5xx: retried up to the attempt cap, then surfaces as an
    # LLMError (LLMTransientError is-a LLMError, so this contract is unchanged).
    route = respx.post("https://api.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(500)
    )
    with pytest.raises(LLMError):
        OpenAICompatClient("https://api.example.com/v1", "m", "k").complete("hi")
    assert route.call_count == DEFAULT_ATTEMPTS


@respx.mock
def test_openai_compat_raises_llmerror_on_non_json_200():
    route = respx.post("https://api.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, text="not json")
    )
    with pytest.raises(LLMError):
        OpenAICompatClient("https://api.example.com/v1", "m", "k").complete("hi")
    assert route.call_count == 1  # an invalid body is not a transient failure


@respx.mock
def test_openai_compat_retries_429_then_succeeds():
    route = respx.post("https://api.example.com/v1/chat/completions").mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]}),
        ]
    )
    result = OpenAICompatClient("https://api.example.com/v1", "m", "k").complete("hi")
    assert result == "ok"
    assert route.call_count == 2


@pytest.mark.parametrize("status", [500, 502, 503, 504])
@respx.mock
def test_openai_compat_retries_5xx_variants_then_succeeds(status: int):
    respx.post("https://api.example.com/v1/chat/completions").mock(
        side_effect=[
            httpx.Response(status),
            httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]}),
        ]
    )
    result = OpenAICompatClient("https://api.example.com/v1", "m", "k").complete("hi")
    assert result == "ok"


@respx.mock
def test_openai_compat_honors_retry_after(monkeypatch: pytest.MonkeyPatch):
    slept: list[float] = []
    monkeypatch.setattr(time, "sleep", slept.append)
    respx.post("https://api.example.com/v1/chat/completions").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "3"}),
            httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]}),
        ]
    )
    OpenAICompatClient("https://api.example.com/v1", "m", "k").complete("hi")
    assert slept and slept[0] >= 3.0


@respx.mock
def test_openai_compat_retries_exhausted_raises_transient():
    route = respx.post("https://api.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(429)
    )
    with pytest.raises(LLMTransientError):
        OpenAICompatClient("https://api.example.com/v1", "m", "k").complete("hi")
    assert route.call_count == DEFAULT_ATTEMPTS


@respx.mock
def test_openai_compat_non_retryable_400_fails_fast():
    route = respx.post("https://api.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(400)
    )
    with pytest.raises(LLMError) as excinfo:
        OpenAICompatClient("https://api.example.com/v1", "m", "k").complete("hi")
    assert not isinstance(excinfo.value, LLMTransientError)
    assert route.call_count == 1


@respx.mock
def test_anthropic_returns_text_block():
    from boardwatch.llm.anthropic import AnthropicClient

    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, json={"content": [{"type": "text", "text": "[]"}]})
    )
    result = AnthropicClient("claude-x", "k").complete("hi", system="s")
    assert result == "[]"

    # Verify request shape
    request = route.calls.last.request
    body: dict = httpx.Response(200, content=request.content).json()
    assert body["system"] == "s"
    assert body["messages"] == [{"role": "user", "content": "hi"}]
    assert request.headers["x-api-key"] == "k"
    assert request.headers["anthropic-version"] == "2023-06-01"


@respx.mock
def test_anthropic_omits_system_when_none():
    from boardwatch.llm.anthropic import AnthropicClient

    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, json={"content": [{"type": "text", "text": "[]"}]})
    )
    AnthropicClient("claude-x", "k").complete("hi")

    # Verify system key is absent, not null
    request = route.calls.last.request
    body: dict = httpx.Response(200, content=request.content).json()
    assert "system" not in body
    assert body["messages"] == [{"role": "user", "content": "hi"}]


@respx.mock
def test_anthropic_raises_llmerror_on_5xx():
    from boardwatch.llm.anthropic import AnthropicClient

    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(500)
    )
    with pytest.raises(LLMError):
        AnthropicClient("claude-x", "k").complete("hi")
    assert route.call_count == DEFAULT_ATTEMPTS


@respx.mock
def test_anthropic_raises_llmerror_on_non_json_200():
    from boardwatch.llm.anthropic import AnthropicClient

    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, text="not json")
    )
    with pytest.raises(LLMError):
        AnthropicClient("claude-x", "k").complete("hi")
    assert route.call_count == 1  # an invalid body is not a transient failure


@respx.mock
def test_anthropic_retries_429_then_succeeds():
    from boardwatch.llm.anthropic import AnthropicClient

    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}]}),
        ]
    )
    result = AnthropicClient("claude-x", "k").complete("hi")
    assert result == "ok"
    assert route.call_count == 2


@pytest.mark.parametrize("status", [500, 502, 503, 504])
@respx.mock
def test_anthropic_retries_5xx_variants_then_succeeds(status: int):
    from boardwatch.llm.anthropic import AnthropicClient

    respx.post("https://api.anthropic.com/v1/messages").mock(
        side_effect=[
            httpx.Response(status),
            httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}]}),
        ]
    )
    result = AnthropicClient("claude-x", "k").complete("hi")
    assert result == "ok"


@respx.mock
def test_anthropic_honors_retry_after(monkeypatch: pytest.MonkeyPatch):
    from boardwatch.llm.anthropic import AnthropicClient

    slept: list[float] = []
    monkeypatch.setattr(time, "sleep", slept.append)
    respx.post("https://api.anthropic.com/v1/messages").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "3"}),
            httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}]}),
        ]
    )
    AnthropicClient("claude-x", "k").complete("hi")
    assert slept and slept[0] >= 3.0


@respx.mock
def test_anthropic_retries_exhausted_raises_transient():
    from boardwatch.llm.anthropic import AnthropicClient

    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(429)
    )
    with pytest.raises(LLMTransientError):
        AnthropicClient("claude-x", "k").complete("hi")
    assert route.call_count == DEFAULT_ATTEMPTS


@respx.mock
def test_anthropic_non_retryable_400_fails_fast():
    from boardwatch.llm.anthropic import AnthropicClient

    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(400)
    )
    with pytest.raises(LLMError) as excinfo:
        AnthropicClient("claude-x", "k").complete("hi")
    assert not isinstance(excinfo.value, LLMTransientError)
    assert route.call_count == 1
