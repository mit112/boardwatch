"""Provider protocol (§3.3, amended by D22; BoardHealth amended by D27)."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Any, Protocol

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


def count_listed_ids(rows: Iterable[Any], id_key: str) -> int:
    """`BoardSnapshot.board_enumerated` for a single-request provider: the number of DISTINCT
    posting ids the board listed this run.

    Counted off the RAW rows — before the detail budget truncates anything and before a
    per-row parse failure drops one — because the column exists so that
    `board_reported_total - board_enumerated` is a *listing* shortfall. `len(postings)` would
    make it a parse-failure count instead, and every provider would mean something different
    by the same persisted column (D-271).

    A row with no usable id is excluded rather than counted, which is what makes the live
    Mastercard case visible: SmartRecruiters reported 1129 and could only key 1128, and an
    id-less row is precisely a posting we cannot fetch, dedupe, or close.
    """
    return len(
        {
            str(row[id_key])
            for row in rows
            if isinstance(row, dict) and row.get(id_key) is not None
        }
    )


class Provider(Protocol):
    name: str
    # public paste hostnames a user would enter; distinct from board_url()'s API host
    board_hosts: tuple[str, ...]

    def board_url(self, slug: str) -> str:
        """Canonical fetch URL == the http_cache key; stable parameter order."""
        ...

    def fetch_board(self, fetcher: Fetcher, request: BoardRequest) -> BoardSnapshot: ...

    def healthcheck(self, fetcher: Fetcher, slug: str) -> BoardHealth: ...
