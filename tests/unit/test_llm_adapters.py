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
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, json={"content": [{"type": "text", "text": "[]"}]})
    )
    from boardwatch.llm.anthropic import AnthropicClient
    assert AnthropicClient("claude-x", "k").complete("hi", system="s") == "[]"
