from __future__ import annotations

from typing import Protocol, runtime_checkable


class LLMError(RuntimeError):
    """A provider call failed or returned an unusable body."""


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
