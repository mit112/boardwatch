"""`lane_seeds` — the durable handoff from a discovering lane to a resolving one.

Every assertion here defends a property whose WRONG implementation is silent: a provenance
overwrite reads as a normal upsert, a reset attempt counter reads as a fresh seed, and an
attempt that is charged only on failure reads as a working retry bound right up until a lane
resolves nothing for a week.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine, select

from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import insert_run
from boardwatch.store.seed_queries import (
    record_seed_attempt,
    record_seeds,
    unresolved_seeds,
)
from boardwatch.store.tables import lane_seeds

NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


def _engine(tmp_path: Path) -> Engine:
    engine = get_engine(tmp_path / "seeds.db")
    ensure_schema(engine)
    return engine


def test_a_seed_is_stored_once_and_the_first_discoverer_keeps_the_row(tmp_path: Path) -> None:
    """Re-seeing a URL must not rewrite who found it, and must not look like new reach.

    Both halves fail silently on the plausible wrong implementation (`on_conflict_do_update`):
    the store's account of where a posting came from becomes a lie with no recoverable prior
    value, and a lane re-listing its whole backlog every run reports it as fresh discovery
    forever.
    """
    engine = _engine(tmp_path)
    run = insert_run(engine)
    with engine.begin() as conn:
        first = record_seeds(
            conn, ("https://x.test/a",), discovered_by="github_lists", run_id=run, now=NOW
        )
        second = record_seeds(
            conn, ("https://x.test/a",), discovered_by="indeed", run_id=run, now=LATER
        )
        row = conn.execute(select(lane_seeds)).one()

    assert (first, second) == (1, 0), "the return is rows INSERTED, never len(urls)"
    assert row.discovered_by == "github_lists"
    assert row.first_seen_at.replace(tzinfo=UTC) == NOW


def test_an_empty_batch_and_an_in_batch_duplicate_both_fall_out_of_the_conflict_clause(
    tmp_path: Path,
) -> None:
    """A CONTRACT PIN, not a mutation-caught guard, and it is labelled as one deliberately.

    No mutation of the current implementation makes this fail: both properties are consequences
    of the UNIQUE plus `on_conflict_do_nothing`, which
    `test_a_seed_is_stored_once_and_the_first_discoverer_keeps_the_row` already pins. What it
    defends is a REWRITE — an `executemany` form raises on the empty list and turns the whole
    batch into an unreadable no-op-per-row on the duplicate.
    """
    engine = _engine(tmp_path)
    run = insert_run(engine)
    with engine.begin() as conn:
        assert record_seeds(conn, (), discovered_by="indeed", run_id=run, now=NOW) == 0
        assert conn.execute(select(lane_seeds)).all() == []
        assert record_seeds(
            conn,
            ("https://x.test/a", "https://x.test/b", "https://x.test/a"),
            discovered_by="indeed",
            run_id=run,
            now=NOW,
        ) == 2
        assert sorted(conn.execute(select(lane_seeds.c.url)).scalars().all()) == [
            "https://x.test/a",
            "https://x.test/b",
        ]


def test_the_attempt_ceiling_and_the_limit_both_bind(tmp_path: Path) -> None:
    """A seed at the ceiling leaves the candidate set; the limit bounds the resolver's spend.

    Without the ceiling a permanently unresolvable URL — an expired requisition, a vendor that
    moved its markup — costs one GET every run forever, which is a cost leak with no drain.
    """
    engine = _engine(tmp_path)
    run = insert_run(engine)
    with engine.begin() as conn:
        record_seeds(
            conn,
            ("https://x.test/a", "https://x.test/b", "https://x.test/c"),
            discovered_by="indeed",
            run_id=run,
            now=NOW,
        )
        ids = {s.url: s.id for s in unresolved_seeds(conn, max_attempts=2, limit=99)}
        # `a` is driven to the ceiling; `b` sits one below it.
        record_seed_attempt(conn, ids["https://x.test/a"], run_id=run, now=NOW, resolved=False)
        record_seed_attempt(conn, ids["https://x.test/a"], run_id=run, now=NOW, resolved=False)
        record_seed_attempt(conn, ids["https://x.test/b"], run_id=run, now=NOW, resolved=False)

        under_ceiling = unresolved_seeds(conn, max_attempts=2, limit=99)
        capped = unresolved_seeds(conn, max_attempts=99, limit=1)

    assert [s.url for s in under_ceiling] == ["https://x.test/c", "https://x.test/b"], (
        "never-tried seeds come first, so a small budget still reaches new discoveries"
    )
    assert [s.url for s in capped] == ["https://x.test/c"]


def test_an_attempt_is_charged_on_success_as_well_as_on_failure(tmp_path: Path) -> None:
    """`attempts` is TIMES TRIED, not times failed.

    Charging only failures needs the caller to remember which of two calls to make, and the
    failure mode of forgetting is unbounded retries — the exact thing the column exists to stop.
    """
    engine = _engine(tmp_path)
    run = insert_run(engine)
    with engine.begin() as conn:
        record_seeds(conn, ("https://x.test/a",), discovered_by="indeed", run_id=run, now=NOW)
        seed = unresolved_seeds(conn, max_attempts=9, limit=9)[0]
        record_seed_attempt(conn, seed.id, run_id=run, now=LATER, resolved=True)
        row = conn.execute(select(lane_seeds)).one()

    assert row.attempts == 1
    assert row.resolved_at is not None


def test_a_resolved_seed_leaves_the_candidate_set_but_keeps_its_row(tmp_path: Path) -> None:
    """Set `resolved_at`, never DELETE: draining a bucket must not erase that it held something.

    A delete would also let the same URL be re-seeded and re-resolved next run, producing a
    second posting for one requisition.
    """
    engine = _engine(tmp_path)
    run = insert_run(engine)
    with engine.begin() as conn:
        record_seeds(conn, ("https://x.test/a",), discovered_by="indeed", run_id=run, now=NOW)
        seed = unresolved_seeds(conn, max_attempts=9, limit=9)[0]
        record_seed_attempt(conn, seed.id, run_id=run, now=LATER, resolved=True)

        assert unresolved_seeds(conn, max_attempts=99, limit=99) == ()
        assert conn.execute(select(lane_seeds.c.url)).scalars().all() == ["https://x.test/a"]
        # Re-seeding a resolved URL must not resurrect it.
        assert record_seeds(
            conn, ("https://x.test/a",), discovered_by="indeed", run_id=run, now=LATER
        ) == 0
        assert unresolved_seeds(conn, max_attempts=99, limit=99) == ()


def test_a_failed_attempt_records_which_run_charged_it(tmp_path: Path) -> None:
    """Without the run id a stuck seed cannot be told from one nothing has looked at yet."""
    engine = _engine(tmp_path)
    first, second = insert_run(engine), insert_run(engine)
    with engine.begin() as conn:
        record_seeds(conn, ("https://x.test/a",), discovered_by="indeed", run_id=first, now=NOW)
        seed = unresolved_seeds(conn, max_attempts=9, limit=9)[0]
        record_seed_attempt(conn, seed.id, run_id=second, now=LATER, resolved=False)
        row = conn.execute(select(lane_seeds)).one()

    assert (row.first_seen_run_id, row.last_attempt_run_id) == (first, second)
    assert row.last_attempt_at.replace(tzinfo=UTC) == LATER
    assert row.resolved_at is None
