"""Fetch-only worker job (D16): workers have no DB access in either direction.

This module must never import boardwatch.store (lint-enforced). The thread
pool runs exactly this function; everything stateful happens in the
coordinator, serially.
"""

from __future__ import annotations

from boardwatch.core.models import BoardRequest, BoardSnapshot
from boardwatch.core.politeness import Fetcher
from boardwatch.providers.base import Provider


def fetch_board_job(provider: Provider, fetcher: Fetcher, request: BoardRequest) -> BoardSnapshot:
    return provider.fetch_board(fetcher, request)
