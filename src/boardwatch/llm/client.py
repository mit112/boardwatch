from __future__ import annotations

from typing import Protocol, runtime_checkable


class LLMError(RuntimeError):
    """A provider call failed or returned an unusable body."""


class LLMTransientError(LLMError):
    """A provider call failed with a retryable condition (429 or 5xx).

    Distinguishes a transient rate-limit/server error from any other provider
    failure, so the retry helper (`llm/retry.py`) can back off and retry only
    this case. `retry_after` carries the provider's `Retry-After` hint in
    seconds, when it sent one; the retry helper honors it over its own
    exponential-jitter backoff.
    """

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


@runtime_checkable
class ModelClient(Protocol):
    """Provider-neutral interface for LLM completion calls.

    Adapters implement this protocol to support provider-specific credential
    injection and request/response handling.
    """

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
        ...
