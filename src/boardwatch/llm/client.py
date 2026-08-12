from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
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


class LaneDeathReason(StrEnum):
    """Why the LLM lane is dead for the rest of this invocation.

    A closed catalog (CLAUDE.md): a provider signal outside it is an ordinary
    `LLMError`, never a new member. All three mean the same operationally --
    every remaining call will fail identically -- and differ only in cause,
    which is why they share one exception type rather than three (D-146).
    """

    CREDIT_EXHAUSTED = "credit_exhausted"
    CREDENTIAL_INVALID = "credential_invalid"
    MODEL_FORBIDDEN = "model_forbidden"


class LLMLaneDeadError(LLMError):
    """The credential cannot serve any further call in this invocation.

    Distinct from `LLMTransientError` (retry helps) and from a bare `LLMError`
    (this one call failed; the next may succeed). Raised at the adapter, from
    the provider's error body -- never by string-matching a message downstream.
    """

    def __init__(self, message: str, *, reason: LaneDeathReason) -> None:
        super().__init__(message)
        self.reason = reason


def lane_death_reason(
    body: object, *, table: Mapping[str, LaneDeathReason]
) -> LaneDeathReason | None:
    """Classify a provider error body, or None when it is not a lane death.

    Deliberately total: every malformed shape returns None rather than raising.
    A `TypeError` escaping here would be caught by `extract_llm.py`'s blanket
    `except` and reported as a successful skip -- the precise defect this slice
    exists to remove -- so the shape checks are load-bearing, not defensive
    padding. `type` is checked before `code`; providers use one or the other.
    """
    if not isinstance(body, dict):
        return None
    error = body.get("error")
    if not isinstance(error, dict):
        return None
    for field in ("type", "code"):
        value = error.get(field)
        if isinstance(value, str) and value in table:
            return table[value]
    return None


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
