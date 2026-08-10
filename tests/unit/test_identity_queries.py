"""Storing and loading identities (design §1.2, §2.2, §6.3)."""

from datetime import datetime

from sqlalchemy import insert, update

from boardwatch.core.posting_identity import compute_identities
from boardwatch.store.identity_queries import (
    identities_complete,
    load_identities,
    load_identity_inputs,
    write_identities,
)
from boardwatch.store.tables import posting_identities, postings


def _retitle(engine, posting_id: int, title: str) -> None:
    """A title change with no body change — not a revision, but a new identity key."""
    with engine.begin() as conn:
        conn.execute(
            update(postings)
            .where(postings.c.id == posting_id)
            .values(title=title, normalized_title=title.casefold())
        )


def _clear_locations(engine, posting_id: int) -> None:
    with engine.begin() as conn:
        conn.execute(
            update(postings).where(postings.c.id == posting_id).values(locations_json=None)
        )


def _stale_row(engine, posting_id: int) -> None:
    """An identity written at a previous algorithm version."""
    with engine.begin() as conn:
        conn.execute(
            insert(posting_identities).values(
                posting_id=posting_id,
                kind="exact_quad",
                identity_key="old" + "0" * 61,
                algorithm_version="p6.0-stale",
                created_at=datetime(2026, 1, 1),
            )
        )


def test_write_is_idempotent(seed_dedup):
    seed = seed_dedup()
    with seed.engine.begin() as conn:
        rows = load_identity_inputs(conn)
        identities = compute_identities(rows[0])
        first = write_identities(conn, seed.posting_ids[0], identities, now=seed.now)
        second = write_identities(conn, seed.posting_ids[0], identities, now=seed.now)
    assert first == len(identities)
    assert second == 0


def test_load_filters_to_the_current_algorithm_version(seed_dedup):
    """A version bump must degrade to 'no identities yet', never to a mixed comparison."""
    seed = seed_dedup()
    _stale_row(seed.engine, seed.posting_ids[0])
    with seed.engine.connect() as conn:
        assert load_identities(conn, [seed.posting_ids[0]]) == {}


def test_loaded_inputs_carry_everything_the_resolver_needs(seed_dedup):
    seed = seed_dedup()
    with seed.engine.connect() as conn:
        (row,) = load_identity_inputs(conn)
    assert row.posting_id == seed.posting_ids[0]
    assert row.company_name  # joined from companies, not left as an id
    assert row.first_seen_at is not None


def test_a_posting_with_locations_round_trips_to_an_exact_quad(seed_dedup):
    """The loader must hand `compute_identities` something it can actually use.

    `postings.locations_json` is a JSON column, so a SELECT returns a list. A loader that
    stringifies it does not raise — the identity function simply finds no usable locations,
    returns None, and drops all three location-bearing kinds. Dedup then suppresses nothing,
    forever, with every hand-built unit test still green. Only a real write followed by a
    real read can see this, which is why it lives here and not beside compute_identities.

    `seed_dedup` writes `locations_json=["Remote"]`, so the precondition holds.
    """
    seed = seed_dedup()
    with seed.engine.connect() as conn:
        (row,) = load_identity_inputs(conn)
    assert isinstance(row.locations, list) and row.locations
    assert "exact_quad" in {i.kind for i in compute_identities(row)}


def test_an_explicit_id_list_bounds_the_load(seed_dedup):
    """`None` means all; `[]` means none. An empty list must not silently mean 'everything'."""
    seed = seed_dedup()
    with seed.engine.connect() as conn:
        assert len(load_identity_inputs(conn)) >= 1
        assert load_identity_inputs(conn, []) == ()
        assert [r.posting_id for r in load_identity_inputs(conn, [seed.posting_ids[0]])] == [
            seed.posting_ids[0]
        ]


def test_round_trip_through_the_store_matches_direct_computation(seed_dedup):
    seed = seed_dedup()
    with seed.engine.begin() as conn:
        (row,) = load_identity_inputs(conn)
        write_identities(conn, row.posting_id, compute_identities(row), now=seed.now)
    with seed.engine.connect() as conn:
        stored = load_identities(conn, [seed.posting_ids[0]])[seed.posting_ids[0]]
    assert set(stored) == set(compute_identities(row))


def test_a_retitle_rewrites_the_row_instead_of_leaving_it_stale(seed_dedup):
    """A title change with an unchanged body is not a revision, but it IS a new key.

    scan/apply.py refreshes title on every observation and gates revision on content_hash,
    so this is the ordinary case, not a corner. Insert-if-absent would leave the old key
    stored forever. See the task preamble and design §2.3.
    """
    seed = seed_dedup()
    with seed.engine.begin() as conn:
        (row,) = load_identity_inputs(conn)
        write_identities(conn, row.posting_id, compute_identities(row), now=seed.now)
    _retitle(seed.engine, seed.posting_ids[0], "Staff Platform Engineer")
    with seed.engine.begin() as conn:
        (revised,) = load_identity_inputs(conn)
        rewritten = write_identities(
            conn, revised.posting_id, compute_identities(revised), now=seed.now
        )
    with seed.engine.connect() as conn:
        stored = load_identities(conn, [seed.posting_ids[0]])[seed.posting_ids[0]]
    assert rewritten > 0
    assert set(stored) == set(compute_identities(revised))
    # The point: the superseded key is gone, not sitting beside the new one.
    assert len(stored) == len(compute_identities(revised))


def test_a_kind_that_stops_being_produced_is_deleted_not_orphaned(seed_dedup):
    """Losing location evidence drops three kinds (§2.1). They must not linger.

    An orphaned row would make `identities verify` red forever and would leave a
    suppressing `exact_quad` key in the table for a posting that no longer earns one.
    """
    seed = seed_dedup()
    with seed.engine.begin() as conn:
        (row,) = load_identity_inputs(conn)
        write_identities(conn, row.posting_id, compute_identities(row), now=seed.now)
    _clear_locations(seed.engine, seed.posting_ids[0])
    with seed.engine.begin() as conn:
        (bare,) = load_identity_inputs(conn)
        write_identities(conn, bare.posting_id, compute_identities(bare), now=seed.now)
    with seed.engine.connect() as conn:
        stored = load_identities(conn, [seed.posting_ids[0]])[seed.posting_ids[0]]
    assert {i.kind for i in stored} == {"exact_provider", "content_hash_only"}


def test_completeness_is_false_while_any_open_posting_lacks_an_identity(seed_dedup):
    """Two postings, one backfilled. `if identities:` would say True here.

    That is the whole point of the gate: a partial backfill must report
    `not instrumented`, never a number measured over the subset that happens to
    be present (design §2.2).
    """
    seed = seed_dedup(count=2)
    with seed.engine.connect() as conn:
        assert identities_complete(conn) is False
    with seed.engine.begin() as conn:
        (first, *_) = load_identity_inputs(conn)
        write_identities(conn, first.posting_id, compute_identities(first), now=seed.now)
    with seed.engine.connect() as conn:
        assert identities_complete(conn) is False
    with seed.engine.begin() as conn:
        for row in load_identity_inputs(conn):
            write_identities(conn, row.posting_id, compute_identities(row), now=seed.now)
    with seed.engine.connect() as conn:
        assert identities_complete(conn) is True


def test_completeness_ignores_identities_at_another_version(seed_dedup):
    """A version bump must drop completeness to False, not carry the old rows forward."""
    seed = seed_dedup()
    _stale_row(seed.engine, seed.posting_ids[0])
    with seed.engine.connect() as conn:
        assert identities_complete(conn) is False
