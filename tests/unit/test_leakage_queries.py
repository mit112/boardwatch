"""Store-side read for Gate P6's leakage report (`identity_queries.load_surfaced_exact_quad`).

Every test below cross-checks the query's result against a SECOND path: a plain Python
reconstruction built from independent `SELECT`s over `postings` / `posting_identities` /
`job_dispositions`, rather than by re-running (a copy of) the query under test. That is the
same "count the deliverable through a different path than the one that produced it" rule
`identities verify` already applies to identities themselves (CLAUDE.md).
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from boardwatch.core.dedup import resolve_duplicates
from boardwatch.core.regroup import plan_regrouping
from boardwatch.store.identity_queries import (
    SurfacedJob,
    load_identities,
    load_identity_inputs,
    load_surfaced_exact_quad,
)
from boardwatch.store.ledger_queries import record_disposition
from boardwatch.store.regroup import apply_merges, job_anchors, protected_job_ids
from boardwatch.store.tables import job_dispositions, posting_identities, postings


def _independent_reconstruction(engine) -> dict[int, str | None]:
    """Path B: job_id -> identity_key, built without touching `load_surfaced_exact_quad`.

    Walks the tables directly with plain Python dict joins instead of the query's own SQL
    join-and-aggregate, so a bug in that SQL (wrong join column, wrong aggregate) cannot also
    be baked into what this test expects.
    """
    with engine.connect() as conn:
        job_ids = {int(r[0]) for r in conn.execute(select(job_dispositions.c.job_id)).all()}
        posting_job = {
            int(r.id): int(r.job_id)
            for r in conn.execute(
                select(postings.c.id, postings.c.job_id).where(postings.c.job_id.is_not(None))
            ).all()
        }
        posting_identity = {
            int(r.posting_id): str(r.identity_key)
            for r in conn.execute(
                select(posting_identities.c.posting_id, posting_identities.c.identity_key).where(
                    posting_identities.c.kind == "exact_quad"
                )
            ).all()
        }
    by_job: dict[int, set[str]] = {}
    anchored_jobs: set[int] = set()
    for posting_id, job_id in posting_job.items():
        anchored_jobs.add(job_id)
        key = posting_identity.get(posting_id)
        if key is not None:
            by_job.setdefault(job_id, set()).add(key)
    # Mirrors the query's INNER JOIN through postings: a job with a disposition row but ZERO
    # currently-anchored postings (drained after a merge moved them all away) is excluded
    # entirely, not reported as "unidentified".
    return {
        job_id: (next(iter(by_job[job_id])) if job_id in by_job else None)
        for job_id in job_ids & anchored_jobs
    }


def test_two_independently_surfaced_duplicates_share_one_identity_key(
    seed_dedup, backfill_identities
):
    """The leak shape: two postings with identical content, each on its OWN job (as
    `seed_dedup` seeds them), both `record_disposition`'d before any regroup ran. Both jobs
    must come back, both carrying the SAME exact_quad identity_key.
    """
    seed = seed_dedup(count=2, identical=True)
    backfill_identities(seed)
    with seed.engine.connect() as conn:
        job_a, job_b = job_anchors(conn, seed.posting_ids).values()
    with seed.engine.begin() as conn:
        record_disposition(
            conn, job_a, disposition="built", reason="lead_built",
            policy_version="p1", now=seed.now,
        )
        record_disposition(
            conn, job_b, disposition="built", reason="lead_built",
            policy_version="p1", now=seed.now,
        )
    with seed.engine.connect() as conn:
        rows = {r.job_id: r for r in load_surfaced_exact_quad(conn)}
    assert set(rows) == {job_a, job_b}
    assert rows[job_a].identity_key is not None
    assert rows[job_a].identity_key == rows[job_b].identity_key

    expected = _independent_reconstruction(seed.engine)
    assert {jid: rows[jid].identity_key for jid in rows} == expected


def test_a_single_surfaced_job_is_not_treated_as_a_collision(seed_dedup, backfill_identities):
    """Only one job ever reached `job_dispositions` for this identity — nothing to compare it
    against. The query must report exactly one row, not synthesize a second."""
    seed = seed_dedup(count=1, identical=True)
    backfill_identities(seed)
    with seed.engine.connect() as conn:
        (job_id,) = job_anchors(conn, seed.posting_ids).values()
    with seed.engine.begin() as conn:
        record_disposition(
            conn, job_id, disposition="seen", reason="surfaced",
            expires_at=seed.now + timedelta(days=7), now=seed.now,
        )
    with seed.engine.connect() as conn:
        rows = load_surfaced_exact_quad(conn)
    assert [r.job_id for r in rows] == [job_id]
    assert rows[0].identity_key is not None

    expected = _independent_reconstruction(seed.engine)
    assert expected == {job_id: rows[0].identity_key}


def test_a_body_less_surfaced_job_carries_no_identity(seed_dedup, backfill_identities):
    """A whitespace-only body withholds `exact_quad` entirely (D-132) — the surfaced job must
    come back with `identity_key=None`, not with a stray hash-of-empty-string key."""
    seed = seed_dedup(count=1, body="   ")
    backfill_identities(seed)
    with seed.engine.connect() as conn:
        (job_id,) = job_anchors(conn, seed.posting_ids).values()
    with seed.engine.begin() as conn:
        record_disposition(
            conn, job_id, disposition="seen", reason="surfaced",
            expires_at=seed.now + timedelta(days=7), now=seed.now,
        )
    with seed.engine.connect() as conn:
        rows = load_surfaced_exact_quad(conn)
    assert rows == (SurfacedJob(job_id=job_id, first_decided_at=seed.now, identity_key=None),)

    expected = _independent_reconstruction(seed.engine)
    assert expected == {job_id: None}


def test_a_leak_that_regroup_later_reconciles_stops_appearing_twice(
    seed_dedup, backfill_identities
):
    """The corrected-leak case this report deliberately does NOT keep counting forever: once
    `identities regroup`'s merge moves the loser posting onto the survivor's job, the
    loser's now-empty job disappears from this read (join is through CURRENT postings.job_id),
    leaving exactly the survivor's job — one identity, one surfaced job.
    """
    seed = seed_dedup(count=2, identical=True)
    backfill_identities(seed)
    with seed.engine.connect() as conn:
        rows = load_identity_inputs(conn)
        stored = load_identities(conn)
    suppressions = resolve_duplicates(rows, stored)
    assert len(suppressions) == 1  # sanity: the seeded pair really is one exact_quad group
    with seed.engine.connect() as conn:
        anchors_before = job_anchors(conn, seed.posting_ids)
    with seed.engine.begin() as conn:
        for job_id in set(anchors_before.values()):
            record_disposition(
                conn, job_id, disposition="built", reason="lead_built",
                policy_version="p1", now=seed.now,
            )
    with seed.engine.begin() as conn:
        plan = plan_regrouping(
            suppressions, anchors_before, protected_job_ids=protected_job_ids(conn)
        )
        apply_merges(conn, plan.merges, identity_kind="exact_quad", now=seed.now)
    with seed.engine.connect() as conn:
        rows_after = load_surfaced_exact_quad(conn)
    survivor_job = plan.merges[0].to_job_id
    assert [r.job_id for r in rows_after] == [survivor_job]

    expected = _independent_reconstruction(seed.engine)
    assert expected == {survivor_job: rows_after[0].identity_key}
