"""OpenAI-compatible HTTP adapter for LLM providers (OpenAI, DeepSeek, Ollama, etc.).

Implements the ModelClient protocol for any provider supporting the OpenAI chat completion API.
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

# This adapter reaches ANY openai-compatible endpoint (settings.provider is a
# free-form string and base_url is arbitrary), so its catalog admits only
# unambiguous signals. Bare 403 is deliberately absent: on an arbitrary proxy
# it does not prove the credential is dead.
#
# Two live tokens for the same exhausted-balance condition: OpenAI's current
# docs lead with `credit_balance_exhausted` as the `error.code` for 429
# credit exhaustion, but real captured bodies (community-quoted and the Azure
# OpenAI TPM/RPM-throttle body alike) still carry `insufficient_quota` in both
# `type` and `code`. This is additive, not a rename -- keep both.
_LANE_DEATH_CODES = {
    "insufficient_quota": LaneDeathReason.CREDIT_EXHAUSTED,
    "credit_balance_exhausted": LaneDeathReason.CREDIT_EXHAUSTED,
}
# The status fallback, consulted only when the body classified nothing. Note the asymmetry
# with `anthropic.py`, which maps ZERO statuses: D-146's reason for keying on the body is that
# the status is a channel an intermediary can rewrite, and that argument is STRONGER here --
# this adapter reaches an arbitrary `base_url`, so an arbitrary proxy is in the path by design,
# while the Anthropic adapter always talks to one fixed endpoint. The asymmetry is deliberate
# anyway: openai-compatible servers are a whole ecosystem of implementations, many of which
# send a bare 401/402 with no machine-readable `error.code` at all, so keying on the body
# alone would leave the commonest dead-credential shape unclassified. 401 and 402 are the two
# statuses unambiguous enough to survive a rewrite -- unlike 403, excluded just above -- and
# the cost of a wrong latch is bounded to one invocation of an advisory lane.
_LANE_DEATH_STATUSES = {
    401: LaneDeathReason.CREDENTIAL_INVALID,
    402: LaneDeathReason.CREDIT_EXHAUSTED,
}


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

        def _do_request() -> str:
            response = client.post(url, json=payload, headers=headers, timeout=_TIMEOUT)

            if response.status_code < 200 or response.status_code >= 300:
                # Body first: OpenAI sends `insufficient_quota` on 429, which is
                # terminal and must not be retried. A 429 WITHOUT it stays
                # transient, so D-040's backoff is narrowed by exactly one case.
                reason = lane_death_reason(safe_json(response), table=_LANE_DEATH_CODES)
                if reason is None:
                    reason = _LANE_DEATH_STATUSES.get(response.status_code)
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

            # Extract the message content from the expected path
            try:
                content = body["choices"][0]["message"]["content"]
                if not isinstance(content, str):
                    raise LLMError("Invalid response body: content is not a string")
                return content
            except (KeyError, IndexError, TypeError) as e:
                raise LLMError("Invalid response body: missing choices[0].message.content") from e

        try:
            return request_with_retry(_do_request)
        finally:
            # Only close the client if we created it
            if self._owned_client:
                client.close()
