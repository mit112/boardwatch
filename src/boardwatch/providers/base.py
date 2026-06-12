"""Provider protocol (§3.3, amended by D22)."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from boardwatch.core.models import BoardRequest, BoardSnapshot
from boardwatch.core.politeness import Fetcher


class BoardHealth(StrEnum):
    OK = "ok"
    EMPTY = "empty"
    DEAD = "dead"
    ERROR = "error"


class Provider(Protocol):
    name: str

    def board_url(self, slug: str) -> str:
        """Canonical fetch URL == the http_cache key; stable parameter order."""
        ...

    def fetch_board(self, fetcher: Fetcher, request: BoardRequest) -> BoardSnapshot: ...

    def healthcheck(self, fetcher: Fetcher, slug: str) -> BoardHealth: ...
