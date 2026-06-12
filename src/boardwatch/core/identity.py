"""Posting identity (D10): a posting IS (company_id, provider_posting_id), full stop.

Nothing merges across identities; cross-ID heuristics may only annotate and are
deferred entirely (§5.4). content_hash drives revision detection, never identity.
"""

from __future__ import annotations

from typing import NamedTuple


class PostingKey(NamedTuple):
    company_id: int
    provider_posting_id: str


def posting_key(company_id: int, provider_posting_id: str) -> PostingKey:
    return PostingKey(company_id=company_id, provider_posting_id=provider_posting_id)
