"""T118: multi-posting jobs whose recorded grouping evidence no longer holds.

Read-only detection. Nothing here asserts that anything is repaired — there is no split path
in the tree — only that the detector separates the four standings the report has to keep apart.
"""

from datetime import datetime, timedelta

from sqlalchemy import delete, update

from boardwatch.core.regroup import JobMerge
from boardwatch.store.applications import mark_job_applied
from boardwatch.store.identity_queries import (
    MembershipStanding,
    load_job_memberships,
)
from boardwatch.store.ledger_queries import record_disposition, reopen_jobs
from boardwatch.store.regroup import apply_merges, job_anchors
from boardwatch.store.tables import posting_identities, postings

NOW = datetime(2026, 9, 20, 12, 0, 0)


def _merge_all(seed) -> int:
    """Merge every seeded posting onto the first one's job, the way `regroup` does.

    Returns the canonical job id.
    """
    with seed.engine.begin() as conn:
        anchors = job_anchors(conn, list(seed.posting_ids))
        canonical = anchors[seed.posting_ids[0]]
        apply_merges(
            conn,
            [
                JobMerge(posting_id=pid, from_job_id=anchors[pid], to_job_id=canonical)
                for pid in seed.posting_ids[1:]
            ],
            identity_kind="exact_quad",
            now=seed.now,
        )
    return canonical


def _memberships(seed, now: datetime = NOW):
    with seed.engine.connect() as conn:
        return load_job_memberships(conn, now=now)


def _revise_body(seed, posting_id: int, body: str, content_hash: str) -> None:
    """A real revision: the body changed, so `content_hash` moved with it."""
    with seed.engine.begin() as conn:
        conn.execute(
            update(postings)
            .where(postings.c.id == posting_id)
            .values(body_text=body, content_hash=content_hash)
        )


def _retitle(seed, posting_id: int, title: str) -> None:
    """Metadata only: the body and its hash are untouched, so no revision is minted."""
    with seed.engine.begin() as conn:
        conn.execute(
            update(postings)
            .where(postings.c.id == posting_id)
            .values(title=title, normalized_title=title.casefold())
        )


def test_members_that_still_share_their_recorded_key_are_justified(
    seed_dedup, backfill_identities
):
    """The control, and the whole live population: 383 of 383 multi-posting jobs on
    2026-09-20 are this case, so a detector that reports them reports nothing usable."""
    seed = seed_dedup(count=2, identical=True)
    backfill_identities(seed)
    job_id = _merge_all(seed)

    rows = _memberships(seed)

    assert [r.job_id for r in rows] == [job_id]
    assert rows[0].standing is MembershipStanding.JUSTIFIED
    assert rows[0].posting_ids == seed.posting_ids
    assert rows[0].methods == ("exact_quad",)


def test_a_single_posting_job_is_never_reported(seed_dedup, backfill_identities):
    """Two postings, each on its own job, merged into nothing. Membership only exists where
    a job anchors more than one posting."""
    seed = seed_dedup(count=2, identical=True)
    backfill_identities(seed)

    assert _memberships(seed) == ()


def test_a_body_revision_that_splits_the_key_is_reported_as_diverged(
    seed_dedup, backfill_identities
):
    seed = seed_dedup(count=2, identical=True)
    backfill_identities(seed)
    job_id = _merge_all(seed)
    _revise_body(seed, seed.posting_ids[1], "We are hiring an embedded firmware engineer.", "hh-2")
    backfill_identities(seed)

    rows = _memberships(seed)

    assert [(r.job_id, r.standing) for r in rows] == [(job_id, MembershipStanding.DIVERGED)]


def test_a_title_change_with_no_revision_is_reported_as_diverged(
    seed_dedup, backfill_identities
):
    """The case a content-hash-shaped check misses. `scan/apply.py` refreshes title and
    locations on every observation while gating a revision on `content_hash` alone, so the
    two members still share `content_hash_only` and no longer share `exact_quad`."""
    seed = seed_dedup(count=2, identical=True)
    backfill_identities(seed)
    job_id = _merge_all(seed)
    _retitle(seed, seed.posting_ids[1], "Embedded Firmware Engineer")
    backfill_identities(seed)

    rows = _memberships(seed)

    assert [(r.job_id, r.standing) for r in rows] == [(job_id, MembershipStanding.DIVERGED)]


def test_a_divergence_says_it_carries_a_live_disposition(seed_dedup, backfill_identities):
    seed = seed_dedup(count=2, identical=True)
    backfill_identities(seed)
    job_id = _merge_all(seed)
    _retitle(seed, seed.posting_ids[1], "Embedded Firmware Engineer")
    backfill_identities(seed)
    with seed.engine.begin() as conn:
        record_disposition(
            conn, job_id, disposition="built", reason="lead_built",
            policy_version="p1", now=seed.now,
        )

    rows = _memberships(seed)

    assert rows[0].standing is MembershipStanding.DIVERGED
    assert rows[0].has_live_disposition is True
    assert rows[0].has_application is False


def test_a_drained_disposition_is_not_reported_as_live(seed_dedup, backfill_identities):
    """`has_live_disposition` is the ledger's own liveness, not "a row exists" — a reopened
    row no longer governs, so it no longer makes the divergence consequential."""
    seed = seed_dedup(count=2, identical=True)
    backfill_identities(seed)
    job_id = _merge_all(seed)
    _retitle(seed, seed.posting_ids[1], "Embedded Firmware Engineer")
    backfill_identities(seed)
    with seed.engine.begin() as conn:
        record_disposition(
            conn, job_id, disposition="seen", reason="surfaced",
            expires_at=seed.now + timedelta(days=1), now=seed.now,
        )
        reopen_jobs(conn, [job_id], now=seed.now)

    rows = _memberships(seed)

    assert rows[0].standing is MembershipStanding.DIVERGED
    assert rows[0].has_live_disposition is False


def test_a_divergence_says_it_carries_an_application(seed_dedup, backfill_identities):
    """The consequential case: `applications` keys on `job_id` alone, so one application
    makes every sibling posting read as applied."""
    seed = seed_dedup(count=2, identical=True)
    backfill_identities(seed)
    _merge_all(seed)
    _retitle(seed, seed.posting_ids[1], "Embedded Firmware Engineer")
    backfill_identities(seed)
    with seed.engine.begin() as conn:
        mark_job_applied(conn, posting_id=seed.posting_ids[0], source="test")

    rows = _memberships(seed)

    assert rows[0].standing is MembershipStanding.DIVERGED
    assert rows[0].has_application is True


def test_a_member_with_no_current_version_identity_is_its_own_bucket(
    seed_dedup, backfill_identities
):
    """A version bump degrades to "no identities yet" (`core/identity_kinds.py`), and an
    unmeasurable membership is not a diverged one. Folding it into either neighbour would
    report a bump as a fleet-wide defect, or as a clean bill of health."""
    seed = seed_dedup(count=2, identical=True)
    backfill_identities(seed)
    job_id = _merge_all(seed)
    with seed.engine.begin() as conn:
        conn.execute(
            update(posting_identities)
            .where(
                posting_identities.c.posting_id == seed.posting_ids[1],
                posting_identities.c.kind == "exact_quad",
            )
            .values(algorithm_version="p6.0-retired")
        )

    rows = _memberships(seed)

    assert [(r.job_id, r.standing) for r in rows] == [
        (job_id, MembershipStanding.NO_CURRENT_EVIDENCE)
    ]


def test_a_membership_no_merge_event_explains_is_its_own_bucket(
    seed_dedup, backfill_identities
):
    """Every merge writes its trail before the projection (`store/regroup.py`), so a
    multi-posting job with no suppressing merge event was not built by that writer. There
    is no recorded evidence to re-check, which is neither "agrees" nor "disagrees"."""
    seed = seed_dedup(count=2, identical=True)
    backfill_identities(seed)
    job_id = _merge_all(seed)
    # The events table is append-only by trigger; drop the identities instead so the job is
    # unexplained by anything the check keys on. Removing the trail is not possible by design.
    with seed.engine.begin() as conn:
        conn.exec_driver_sql("DROP TRIGGER job_grouping_events_no_delete")
        conn.exec_driver_sql("DELETE FROM job_grouping_events")

    rows = _memberships(seed)

    assert [(r.job_id, r.standing) for r in rows] == [(job_id, MembershipStanding.UNRECORDED)]
    assert rows[0].methods == ()


def test_the_recorded_method_and_version_are_reported_not_the_current_one(
    seed_dedup, backfill_identities
):
    """The reader needs to know the membership was justified under a version that has since
    been retired — that is what separates an expected divergence from a defect."""
    seed = seed_dedup(count=2, identical=True)
    backfill_identities(seed)
    _merge_all(seed)
    with seed.engine.begin() as conn:
        conn.exec_driver_sql("DROP TRIGGER job_grouping_events_no_update")
        conn.exec_driver_sql("UPDATE job_grouping_events SET algorithm_version = 'p6.0-retired'")

    rows = _memberships(seed)

    assert rows[0].methods == ("exact_quad",)
    assert rows[0].algorithm_versions == ("p6.0-retired",)


def test_an_unidentified_member_outranks_a_divergence(seed_dedup, backfill_identities):
    """Three members, one diverged and one unmeasurable. Reporting this as a divergence
    would claim evidence disagrees when part of it was never read."""
    seed = seed_dedup(count=3, identical=True)
    backfill_identities(seed)
    job_id = _merge_all(seed)
    _retitle(seed, seed.posting_ids[1], "Embedded Firmware Engineer")
    backfill_identities(seed)
    with seed.engine.begin() as conn:
        conn.execute(
            delete(posting_identities).where(
                posting_identities.c.posting_id == seed.posting_ids[2],
                posting_identities.c.kind == "exact_quad",
            )
        )

    rows = _memberships(seed)

    assert [(r.job_id, r.standing) for r in rows] == [
        (job_id, MembershipStanding.NO_CURRENT_EVIDENCE)
    ]
