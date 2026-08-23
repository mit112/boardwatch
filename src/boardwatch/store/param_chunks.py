"""Chunking for `IN` lists whose length scales with the corpus.

SQLite refuses any statement binding more than `SQLITE_LIMIT_VARIABLE_NUMBER` parameters —
32766 on the bundled 3.50, and only 999 before 3.32 — so an `.in_()` over a list sized by the
open-posting corpus is a *dated* time bomb rather than a bug: it works on every run until
ordinary discovery growth crosses the constant, and then fails on every run forever. It
crossed on 2026-08-23 at 32,771 open postings, which took the whole daily driver down.

Two fixes exist and they are not interchangeable. Where the caller's scope is expressible as a
SQL predicate, drop the id list entirely — that is what `identity_queries.load_identities` and
`ledger_queries` do, and it is strictly better because it issues one statement. This module is
for the reads where it is NOT expressible: the eligibility ledger reads take an arbitrary
caller-chosen set (the ranker passes every open posting, the export passes open PLUS
closed-but-tracked), so there is no predicate to write and they keep the list, chunked.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence

# Deliberately well under the 999 SQLite allowed before 3.32, so the size is safe on any
# SQLite this could be run against, and so a statement binding its own scalars (profile_hash,
# rules_hash, engine_kind, engine_version) alongside the ids still has room. At the current
# corpus this is ~66 statements per read, against a run that takes ~26 minutes.
ID_CHUNK_SIZE = 500


def id_chunks(ids: Sequence[int]) -> Iterator[list[int]]:
    """`ids` in `ID_CHUNK_SIZE`-sized pieces, in order. Empty input yields nothing.

    Splitting an `IN` list across statements is only sound when the chunked column is the
    query's grouping or partition key, so that every group lies wholly inside one chunk. It
    holds for both callers here: each groups by the very column it filters on, so a
    `max(id) per posting_version` is the same answer chunked or not. A query that aggregated
    ACROSS the chunked column would need a different fix.
    """
    for start in range(0, len(ids), ID_CHUNK_SIZE):
        yield list(ids[start : start + ID_CHUNK_SIZE])
