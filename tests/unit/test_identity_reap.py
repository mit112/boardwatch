"""Reaping retired identity generations, and the reopen it must not break."""

from datetime import datetime

from sqlalchemy import insert, select, update

from boardwatch.core.identity_kinds import IDENTITY_ALGORITHM_VERSION
from boardwatch.store.identity_queries import (
    count_stale_identities,
    delete_stale_identities,
    identities_complete,
)
from boardwatch.store.tables import posting_identities, postings


def _generation(engine, posting_id: int, version: str, kind: str = "exact_quad") -> None:
    """One identity row at an arbitrary algorithm version."""
    with engine.begin() as conn:
        conn.execute(
            insert(posting_identities).values(
                posting_id=posting_id,
                kind=kind,
                identity_key=f"{version}-{kind}" + "0" * 40,
                algorithm_version=version,
                created_at=datetime(2026, 1, 1),
            )
        )


def _set_status(engine, posting_id: int, status: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            update(postings).where(postings.c.id == posting_id).values(status=status)
        )


def _rows(engine) -> int:
    with engine.connect() as conn:
        return len(conn.execute(select(posting_identities.c.id)).all())


def test_stale_generations_are_reported_per_version(seed_dedup, backfill_identities):
    seed = seed_dedup(count=2)
    backfill_identities(seed)
    _generation(seed.engine, seed.posting_ids[0], "p6.0")
    _generation(seed.engine, seed.posting_ids[1], "p6.0")
    _generation(seed.engine, seed.posting_ids[0], "p6.1")

    with seed.engine.connect() as conn:
        generations = count_stale_identities(conn)

    assert [(g.algorithm_version, g.rows, g.postings) for g in generations] == [
        ("p6.0", 2, 2),
        ("p6.1", 1, 1),
    ]


def test_a_single_current_generation_is_reported_as_nothing_stale(seed_dedup, backfill_identities):
    """The live store's shape on 2026-08-28: 476,277 rows, all at one version.

    `()` here is "nothing is REAPABLE", which is not the same claim as "the table is small" —
    the command's output says so rather than reporting a reclaim of 0 as a clean bill.
    """
    seed = seed_dedup(count=2)
    backfill_identities(seed)
    with seed.engine.connect() as conn:
        assert count_stale_identities(conn) == ()


def test_reap_deletes_only_the_retired_generation(seed_dedup, backfill_identities):
    seed = seed_dedup(count=2)
    backfill_identities(seed)
    current = _rows(seed.engine)
    _generation(seed.engine, seed.posting_ids[0], "p6.0")
    _generation(seed.engine, seed.posting_ids[1], "p6.0")
    assert _rows(seed.engine) == current + 2

    with seed.engine.begin() as conn:
        deleted = delete_stale_identities(conn)

    assert deleted == 2
    assert _rows(seed.engine) == current
    with seed.engine.connect() as conn:
        versions = {
            row[0]
            for row in conn.execute(select(posting_identities.c.algorithm_version)).all()
        }
    assert versions == {IDENTITY_ALGORITHM_VERSION}


def test_a_reap_then_a_reopen_leaves_suppression_still_armed(seed_dedup, backfill_identities):
    """The reason closed postings are out of scope, pinned as a test.

    A posting closes, the reaper runs, and the posting reopens before anything backfills it.
    `identities_complete()` gates suppression over ALL open postings, so if the reaper had
    taken the closed posting's CURRENT-version rows the corpus would come back incomplete and
    dedup would be silently disarmed store-wide.

    This FAILS against a reaper scoped on posting status instead of on algorithm version:
    delete `posting_id == closed` here and the assertion below goes False.
    """
    seed = seed_dedup(count=2)
    backfill_identities(seed)
    closed = seed.posting_ids[1]
    _generation(seed.engine, closed, "p6.0")
    _set_status(seed.engine, closed, "closed")

    with seed.engine.begin() as conn:
        # `>=`, not `== 1`: a wrongly-scoped reaper deletes MORE, and the assertion that has
        # to catch it is the completeness one below — not an off-by-count here, which would
        # fail first and hide which property actually broke.
        assert delete_stale_identities(conn) >= 1

    _set_status(seed.engine, closed, "open")

    with seed.engine.connect() as conn:
        assert identities_complete(conn) is True
