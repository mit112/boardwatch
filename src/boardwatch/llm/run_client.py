"""Invocation-scoped LLM client: one credential death stops the whole lane.

A dead credential (out of credit, revoked, or lacking model access) fails every
remaining call identically, so continuing to call it burns real quota to learn
the same fact once per posting. This wrapper latches on the first
`LLMLaneDeadError` and refuses subsequent calls without touching the network.

It is installed by `llm.factory.build_client`, which both consumers call exactly
once per invocation -- so "invocation-scoped" is a property of that call site,
not of this class.
"""

from __future__ import annotations

from boardwatch.llm.client import LaneDeathReason, LLMLaneDeadError, ModelClient


class RunScopedClient:
    """Wrap a `ModelClient`, latching dead on the first lane death.

    Implements `ModelClient`, so it is a drop-in for the real adapters and no
    caller signature changes.
    """

    def __init__(self, inner: ModelClient) -> None:
        self._inner = inner
        self._dead: LaneDeathReason | None = None
        self.calls_attempted = 0

    @property
    def dead_reason(self) -> LaneDeathReason | None:
        """The reason the lane died, or None while it is healthy."""
        return self._dead

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        if self._dead is not None:
            raise LLMLaneDeadError(
                f"LLM lane already dead ({self._dead}); not calling the provider",
                reason=self._dead,
            )
        self.calls_attempted += 1
        try:
            return self._inner.complete(prompt, system=system)
        except LLMLaneDeadError as exc:
            self._dead = exc.reason
            raise
