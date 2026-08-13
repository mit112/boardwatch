"""Native Anthropic Messages API adapter for LLM provider integration.

Implements the ModelClient protocol for direct Anthropic API calls without
compatibility layers.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from boardwatch.llm.client import (
    LaneDeathReason,
    LLMError,
    LLMLaneDeadError,
    LLMTransientError,
    lane_death_reason,
)
from boardwatch.llm.retry import parse_retry_after, request_with_retry, safe_json

# Timeout for HTTP requests in seconds
_TIMEOUT = 30.0

# Retryable per D-040: rate limit + server-side transients. Anything else is
# a non-retryable LLMError.
_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})

# Anthropic's documented error types that mean the credential cannot serve any
# further call. Closed catalog: anything else is an ordinary LLMError. Keyed on
# `error.type`, never on HTTP status: `type` is the provider's own typed
# signal, while the status is a coarser channel an intermediary (gateway,
# proxy, load balancer) can rewrite in transit -- the body is the authoritative
# source. Documented status pairings, for reference only (the dispatch below
# does not depend on them): `authentication_error` 401, `billing_error` 402,
# `permission_error` 403.
_LANE_DEATH_TYPES = {
    "billing_error": LaneDeathReason.CREDIT_EXHAUSTED,
    "authentication_error": LaneDeathReason.CREDENTIAL_INVALID,
    "permission_error": LaneDeathReason.MODEL_FORBIDDEN,
}


class AnthropicClient:
    """Anthropic Messages API adapter.

    Posts to {base_url}/v1/messages with Anthropic-specific authentication
    and request/response handling. Implements the ModelClient protocol for
    provider-neutral integration.
    """

    def __init__(
        self,
        model: str,
        api_key: str,
        *,
        base_url: str = "https://api.anthropic.com",
        client: httpx.Client | None = None,
    ) -> None:
        """Initialize the adapter.

        Args:
            model: The model identifier to request (e.g., claude-opus-4-1).
            api_key: The API key for authentication.
            base_url: The Anthropic API base URL.
            client: Optional httpx.Client for testing; a new client is created if None.
        """
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
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
        # Prepare the request
        url = f"{self.base_url}/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system is not None:
            payload["system"] = system

        # Use the provided client or create a new one
        client = self._client or httpx.Client()

        def _do_request() -> str:
            response = client.post(url, json=payload, headers=headers, timeout=_TIMEOUT)

            # Lane death is checked FIRST: it is terminal, so it must not be
            # retried even when it arrives on an otherwise-retryable status.
            if response.status_code < 200 or response.status_code >= 300:
                reason = lane_death_reason(safe_json(response), table=_LANE_DEATH_TYPES)
                if reason is not None:
                    raise LLMLaneDeadError(
                        f"HTTP {response.status_code}: {response.text}", reason=reason
                    )
                if response.status_code in _RETRYABLE_STATUSES:
                    raise LLMTransientError(
                        f"HTTP {response.status_code}: {response.text}",
                        retry_after=parse_retry_after(response),
                    )
                raise LLMError(f"HTTP {response.status_code}: {response.text}")

            # Parse and validate the response
            try:
                body: Any = response.json()
            except (ValueError, json.JSONDecodeError) as e:
                raise LLMError(f"Invalid response body: not JSON: {e}") from e

            # Extract the text content from the expected path
            try:
                content = body["content"][0]["text"]
                if not isinstance(content, str):
                    raise LLMError("Invalid response body: content is not a string")
                return content
            except (KeyError, IndexError, TypeError) as e:
                raise LLMError("Invalid response body: missing content[0].text") from e

        try:
            return request_with_retry(_do_request)
        finally:
            # Only close the client if we created it
            if self._owned_client:
                client.close()
