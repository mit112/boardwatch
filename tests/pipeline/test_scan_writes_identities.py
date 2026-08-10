"""The scan path keeps posting identities current (P6 slice 2 §4, closing D-098).

D-098 recorded the defect these tests invert: `write_identities` had exactly one caller in
`src/` — the manual `boardwatch identities backfill` — so any run that discovered a posting left
it uncovered, `identities_complete()` went False, and duplicate suppression silently switched
off corpus-wide. `hidden_duplicate == 0` then meant "not measured", not "none", and the second
reading was the common case rather than the corner.
"""

from __future__ import annotations

from copy import deepcopy

from sqlalchemy import Engine, select

from boardwatch.core.posting_identity import compute_identities
from boardwatch.scan.apply import apply_board
from boardwatch.store import tables
from boardwatch.store.identity_queries import (
    identities_complete,
    load_identities,
    load_identity_inputs,
)


def test_a_discovered_posting_is_covered_without_a_manual_backfill(
    engine: Engine, case, company_id: int, run_id: int
) -> None:
    """The D-098 defect, inverted: a scan that discovers a posting must leave suppression ON."""
    apply_board(engine, case.snapshot_for(case.jobs()[:1]), company_id, run_id)
    with engine.connect() as conn:
        posting_id = conn.execute(select(tables.postings.c.id)).scalar_one()
        assert load_identities(conn, [int(posting_id)])
        assert identities_complete(conn) is True


def test_the_stored_identity_matches_what_the_recount_would_compute(
    engine: Engine, case, company_id: int, run_id: int
) -> None:
    """`identities verify`'s Path A == Path B straight out of a scan, with no backfill between.

    Not a tautology: the scan writes from `RawPosting` while the recount reads back the
    persisted `postings` row, so a coercion that differs between the two paths (locations in
    particular) fails here.
    """
    apply_board(engine, case.snapshot_for(case.jobs()[:1]), company_id, run_id)
    with engine.connect() as conn:
        inputs = load_identity_inputs(conn)
        stored = load_identities(conn)
    assert len(inputs) == 1
    row = inputs[0]
    assert set(stored[row.posting_id]) == set(compute_identities(row))


def test_a_retitle_with_an_unchanged_body_moves_the_stored_identity(
    engine: Engine, case, company_id: int, run_id: int
) -> None:
    """The stale-key half of D-098.

    `_apply_listed` refreshes title and locations on every positive observation while gating a
    *revision* on `content_hash` alone (the D25 rule), so a retitle moves an identity key
    without producing a posting version. If identities were written only on insert, the stored
    `exact_quad` would keep suppressing on the OLD title forever.
    """
    original = case.jobs()[0]
    apply_board(engine, case.snapshot_for([original]), company_id, run_id)
    with engine.connect() as conn:
        before = load_identities(conn)

    # A deep copy, so the same provider_posting_id is re-observed with a new title — the
    # update branch of `_apply_listed`, not the insert branch.
    retitled = case.set_title(deepcopy(original), " II")
    apply_board(engine, case.snapshot_for([retitled]), company_id, run_id)
    with engine.connect() as conn:
        after = load_identities(conn)
        inputs = load_identity_inputs(conn)
        versions = conn.execute(
            select(tables.posting_versions.c.id).where(
                tables.posting_versions.c.capture_reason == "revised"
            )
        ).all()

    posting_id = inputs[0].posting_id
    quad_before = {i.identity_key for i in before[posting_id] if i.kind == "exact_quad"}
    quad_after = {i.identity_key for i in after[posting_id] if i.kind == "exact_quad"}
    assert versions == []  # no revision: the body never changed
    assert quad_before and quad_after and quad_before != quad_after
    assert set(after[posting_id]) == set(compute_identities(inputs[0]))
