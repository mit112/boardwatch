"""Provider protocol (§3.3, amended by D22; BoardHealth amended by D27)."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from boardwatch.core.models import BoardRequest, BoardSnapshot
from boardwatch.core.politeness import Fetcher, FetchFailure


class BoardHealth(StrEnum):
    OK = "ok"
    EMPTY = "empty"
    DEAD = "dead"
    ERROR = "error"
    UNREACHABLE = "unreachable"  # D27: no HTTP response received (transport-level, after retries)


def health_from_failure(exc: FetchFailure, *, dead_status: int = 404) -> BoardHealth:
    """D27 mapping for a FetchFailure: status_code is None (transport) → UNREACHABLE;
    the provider dead signature → DEAD; any other HTTP error → ERROR. Parse failure of
    a 200 body is the provider's own concern (it maps to ERROR there), not this helper."""
    if exc.status_code is None:
        return BoardHealth.UNREACHABLE
    if exc.status_code == dead_status:
        return BoardHealth.DEAD
    return BoardHealth.ERROR


class Provider(Protocol):
    name: str

    def board_url(self, slug: str) -> str:
        """Canonical fetch URL == the http_cache key; stable parameter order."""
        ...

    def fetch_board(self, fetcher: Fetcher, request: BoardRequest) -> BoardSnapshot: ...

    def healthcheck(self, fetcher: Fetcher, slug: str) -> BoardHealth: ...
