"""OpenAI-compatible HTTP adapter for LLM providers (OpenAI, DeepSeek, Ollama, etc.).

Implements the ModelClient protocol for any provider supporting the OpenAI chat completion API.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from boardwatch.llm.client import LLMError

# Timeout for HTTP requests in seconds
_TIMEOUT = 30.0


class OpenAICompatClient:
    """OpenAI-compatible LLM provider adapter.

    Posts to {base_url}/chat/completions with the standard OpenAI messages format.
    Implements the ModelClient protocol for provider-neutral integration.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        """Initialize the adapter.

        Args:
            base_url: The provider's API base URL (e.g., https://api.openai.com/v1).
            model: The model identifier to request (e.g., gpt-4, deepseek-chat).
            api_key: The bearer token for authentication.
            client: Optional httpx.Client for testing; a new client is created if None.
        """
        self.base_url = base_url
        self.model = model
        self.api_key = api_key
        self._client = client
        self._owned_client = client is None

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        """Execute a completion request.

        Args:
            prompt: The user-facing prompt text.
            system: Optional system instruction.

        Returns:
            The LLM's response text.

        Raises:
            LLMError: If the provider call fails or returns invalid output.
        """
        # Build messages array: optional system + required user
        messages: list[dict[str, str]] = []
        if system is not None:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        # Prepare the request
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": messages,
        }

        # Use the provided client or create a new one
        client = self._client or httpx.Client()
        try:
            response = client.post(url, json=payload, headers=headers, timeout=_TIMEOUT)

            # Check for HTTP errors
            if response.status_code < 200 or response.status_code >= 300:
                raise LLMError(f"HTTP {response.status_code}: {response.text}")

            # Parse and validate the response
            try:
                body: Any = response.json()
            except (ValueError, json.JSONDecodeError) as e:
                raise LLMError(f"Invalid response body: not JSON: {e}") from e

            # Extract the message content from the expected path
            try:
                content = body["choices"][0]["message"]["content"]
                if not isinstance(content, str):
                    raise LLMError("Invalid response body: content is not a string")
                return content
            except (KeyError, IndexError, TypeError) as e:
                raise LLMError("Invalid response body: missing choices[0].message.content") from e
        finally:
            # Only close the client if we created it
            if self._owned_client:
                client.close()
