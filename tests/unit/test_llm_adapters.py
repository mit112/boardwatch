import httpx
import pytest
import respx

from boardwatch.llm.client import LLMError
from boardwatch.llm.openai_compat import OpenAICompatClient


@respx.mock
def test_openai_compat_returns_message_content():
    respx.post("https://api.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": "[]"}}]})
    )
    c = OpenAICompatClient("https://api.example.com/v1", "m", "k")
    assert c.complete("hi", system="s") == "[]"


@respx.mock
def test_openai_compat_raises_llmerror_on_5xx():
    respx.post("https://api.example.com/v1/chat/completions").mock(return_value=httpx.Response(500))
    with pytest.raises(LLMError):
        OpenAICompatClient("https://api.example.com/v1", "m", "k").complete("hi")


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

    respx.post("https://api.anthropic.com/v1/messages").mock(return_value=httpx.Response(500))
    with pytest.raises(LLMError):
        AnthropicClient("claude-x", "k").complete("hi")
