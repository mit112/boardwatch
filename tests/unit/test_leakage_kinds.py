"""`load_surfaced_identities` reads the kind it is ASKED for.

`store/identity_queries.py` used to hardcode `kind == "exact_quad"`. The consequence was not
a wrong number but an unreadable one: a job whose only identity is `company_title_location`
landed in the `unidentified` bucket and could never be counted redundant, so Gate P6's
duplicate-leakage clause reported 0.00% for a STRUCTURAL reason rather than because dedup
works. CLAUDE.md: a rule that cannot fire is a monitoring failure.

Like `test_leakage_queries.py`, every assertion here is cross-checked against a SECOND path —
the `posting_identities` rows read directly — rather than by re-running the query under test.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, update

from boardwatch.core.identity_kinds import IDENTITY_ALGORITHM_VERSION, UnknownIdentityKind
from boardwatch.store.identity_queries import load_surfaced_identities, load_surfaced_keys
from boardwatch.store.ledger_queries import record_disposition
from boardwatch.store.regroup import job_anchors
from boardwatch.store.tables import posting_identities, postings


def test_the_surfaced_loader_reads_the_kind_it_is_asked_for(seed_dedup, backfill_identities):
    """Asking for the wider kind must return the wider kind's key — a DIFFERENT key, not the
    same one under a new name. A loader that ignored its argument would pass a test that only
    checked "some key came back"."""
    seed = seed_dedup(count=1, identical=True)
    backfill_identities(seed)
    with seed.engine.connect() as conn:
        (job_id,) = job_anchors(conn, seed.posting_ids).values()
    with seed.engine.begin() as conn:
        record_disposition(
            conn,
            job_id,
            disposition="built",
            reason="lead_built",
            policy_version="p1",
            now=seed.now,
        )
    with seed.engine.connect() as conn:
        quad = {r.job_id: r.identity_key for r in load_surfaced_identities(conn, kind="exact_quad")}
        ctl = {
            r.job_id: r.identity_key
            for r in load_surfaced_identities(conn, kind="company_title_location")
        }
        stored = {
            str(r.kind): str(r.identity_key)
            for r in conn.execute(
                select(posting_identities.c.kind, posting_identities.c.identity_key).where(
                    posting_identities.c.posting_id == seed.posting_ids[0],
                    posting_identities.c.algorithm_version == IDENTITY_ALGORITHM_VERSION,
                )
            ).all()
        }
    assert set(quad) == set(ctl) == {job_id}
    assert quad[job_id] != ctl[job_id]
    assert quad[job_id] == stored["exact_quad"]
    assert ctl[job_id] == stored["company_title_location"]


def test_an_out_of_catalog_kind_is_a_typed_refusal_not_an_empty_result(seed_dedup):
    """Out-of-catalog is a failure, never a new bucket. An unknown kind returning zero rows
    would read as "no leakage" — the direction that makes the gate easier to pass."""
    seed = seed_dedup(count=1)
    with seed.engine.connect() as conn:
        with pytest.raises(UnknownIdentityKind) as excinfo:
            load_surfaced_identities(conn, kind="body_bag")
    assert excinfo.value.name == "body_bag"


def test_a_job_holding_two_keys_of_one_kind_appears_under_both(seed_dedup, backfill_identities):
    """`load_surfaced_identities` collapses a job's keys with `func.max`, keeping only the
    lexicographically largest. Discarding the other hides a redundancy and makes leakage read
    LOWER than it is — the one direction a gate metric must not fail in. `load_surfaced_keys`
    exists so the candidate bound does not inherit that: one row per key means an ambiguous
    job inflates the bound instead of shrinking it.

    Both halves are asserted, because the contrast IS the point: a single loader that behaved
    the same way for both callers would make one of the two wrong."""
    seed = seed_dedup(count=2, identical=False)
    backfill_identities(seed)
    with seed.engine.connect() as conn:
        anchors = job_anchors(conn, seed.posting_ids)
    survivor = min(anchors.values())
    with seed.engine.begin() as conn:
        # Both postings anchored to one job while still carrying two different ctl keys —
        # exactly what an IDENTITY_ALGORITHM_VERSION bump can leave behind after a merge.
        for posting_id in seed.posting_ids:
            conn.execute(
                update(postings).where(postings.c.id == posting_id).values(job_id=survivor)
            )
        record_disposition(
            conn,
            survivor,
            disposition="built",
            reason="lead_built",
            policy_version="p1",
            now=seed.now,
        )
    with seed.engine.connect() as conn:
        rows = load_surfaced_keys(conn, kind="company_title_location")
        collapsed = load_surfaced_identities(conn, kind="company_title_location")
        stored = {
            str(r.identity_key)
            for r in conn.execute(
                select(posting_identities.c.identity_key).where(
                    posting_identities.c.posting_id.in_(seed.posting_ids),
                    posting_identities.c.kind == "company_title_location",
                    posting_identities.c.algorithm_version == IDENTITY_ALGORITHM_VERSION,
                )
            ).all()
        }
    assert len(stored) == 2, "the fixture must seed two DIFFERENT ctl keys for this to bite"
    assert [r.job_id for r in rows] == [survivor, survivor]
    assert {r.identity_key for r in rows} == stored
    # The collapsing loader keeps ONE of the two and drops the other. Pinned, not fixed:
    # `compute_leakage`'s exact_quad half is unchanged by this work.
    assert len(collapsed) == 1
    assert collapsed[0].identity_key == max(stored)
