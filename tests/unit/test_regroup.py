"""P6 slice 2: job regrouping, planner and store (design §3; §8 claims 7, 8, 9)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, insert, select

from boardwatch.core.dedup import Suppression
from boardwatch.core.regroup import REGROUP_REFUSALS, JobMerge, plan_regrouping
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.ledger_queries import (
    live_dispositions,
    load_dispositions,
    record_disposition,
)
from boardwatch.store.queue_state import (
    followup_job_dates,
    mark_job_reported,
    mark_job_skipped,
    reported_job_ids,
    set_job_followup,
    skipped_job_ids,
)
from boardwatch.store.regroup import (
    MergeOutcome,
    apply_merges,
    job_anchors,
    protected_job_ids,
    queue_action_job_ids,
)

NOW = datetime(2026, 8, 10, 12, 0, 0)


def _sup(loser: int, survivor: int) -> Suppression:
    return Suppression(posting_id=loser, survivor_posting_id=survivor, kind="exact_quad")


# ------------------------------------------------------------------ the planner


def test_a_loser_moves_onto_the_survivors_job() -> None:
    plan = plan_regrouping(
        [_sup(2, 1)],
        {1: 10, 2: 20},
        protected_job_ids=frozenset(),
        queue_action_job_ids=frozenset(),
    )
    assert plan.merges == (JobMerge(posting_id=2, from_job_id=20, to_job_id=10),)
    assert plan.refusals == ()


def test_the_canonical_job_is_the_survivors_never_a_second_election() -> None:
    """The survivor is whichever posting `resolve_duplicates` elected — even when it carries the
    HIGHER job id, so no implicit "lowest job wins" rule can creep in."""
    plan = plan_regrouping(
        [_sup(2, 1)], {1: 99, 2: 5},
        protected_job_ids=frozenset(), queue_action_job_ids=frozenset(),
    )
    assert plan.merges == (JobMerge(posting_id=2, from_job_id=5, to_job_id=99),)


def test_a_member_already_on_the_canonical_job_plans_nothing() -> None:
    """Idempotence: a second pass over an unchanged corpus is a no-op."""
    plan = plan_regrouping(
        [_sup(2, 1)], {1: 10, 2: 10},
        protected_job_ids=frozenset(), queue_action_job_ids=frozenset(),
    )
    assert plan.merges == ()
    assert plan.refusals == ()


def test_a_three_member_group_moves_both_losers() -> None:
    plan = plan_regrouping(
        [_sup(2, 1), _sup(3, 1)], {1: 10, 2: 20, 3: 30},
        protected_job_ids=frozenset(), queue_action_job_ids=frozenset(),
    )
    assert plan.merges == (
        JobMerge(posting_id=2, from_job_id=20, to_job_id=10),
        JobMerge(posting_id=3, from_job_id=30, to_job_id=10),
    )


def test_a_tracked_loser_job_refuses_the_WHOLE_group(  # noqa: N802 - emphasis is the point
) -> None:
    """Claim 7. A partially-merged group is a third state nothing downstream understands, and
    merging a job that holds an application silently breaks the applied count."""
    plan = plan_regrouping(
        [_sup(2, 1), _sup(3, 1)],
        {1: 10, 2: 20, 3: 30},
        protected_job_ids=frozenset({20}),
        queue_action_job_ids=frozenset(),
    )
    assert plan.merges == ()
    assert len(plan.refusals) == 1
    refusal = plan.refusals[0]
    assert refusal.reason == "tracked_job"
    assert refusal.survivor_posting_id == 1
    assert refusal.member_posting_ids == (1, 2, 3)


def test_a_tracked_SURVIVOR_job_does_not_refuse_anything(  # noqa: N802 - emphasis
) -> None:
    """Nothing moves off the survivor's job, so its tracking rows are untouched. Refusing here
    would block the common good case: you applied via the posting dedup already elected."""
    plan = plan_regrouping(
        [_sup(2, 1)], {1: 10, 2: 20},
        protected_job_ids=frozenset({10}), queue_action_job_ids=frozenset(),
    )
    assert plan.merges == (JobMerge(posting_id=2, from_job_id=20, to_job_id=10),)


def test_a_missing_job_anchor_is_a_counted_refusal_not_a_silent_skip() -> None:
    plan = plan_regrouping(
        [_sup(2, 1)], {1: 10},
        protected_job_ids=frozenset(), queue_action_job_ids=frozenset(),
    )
    assert plan.merges == ()
    assert plan.refusals[0].reason == "missing_job_anchor"


def test_every_refusal_reason_is_in_the_closed_catalog() -> None:
    reasons = {
        plan_regrouping(
            [_sup(2, 1)], {1: 10, 2: 20},
            protected_job_ids=frozenset({20}), queue_action_job_ids=frozenset(),
        ).refusals[0].reason,
        plan_regrouping(
            [_sup(2, 1)], {1: 10, 2: 20},
            protected_job_ids=frozenset(), queue_action_job_ids=frozenset({20}),
        ).refusals[0].reason,
        plan_regrouping(
            [_sup(2, 1)], {1: 10},
            protected_job_ids=frozenset(), queue_action_job_ids=frozenset(),
        ).refusals[0].reason,
    }
    assert reasons == set(REGROUP_REFUSALS)


# -------------------------------------------------------------------- the store


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def _seed(engine: Engine, count: int) -> list[tuple[int, int]]:
    """`count` postings, one job each — the live 1:1 shape. Returns (posting_id, job_id)."""
    out: list[tuple[int, int]] = []
    with engine.begin() as conn:
        company_id = int(
            conn.execute(
                insert(tables.companies).values(
                    name="Acme", provider="greenhouse", slug="acme", source="user", watched=True
                )
            ).inserted_primary_key[0]
        )
        for n in range(count):
            job_id = int(
                conn.execute(insert(tables.jobs).values(created_at=NOW)).inserted_primary_key[0]
            )
            posting_id = int(
                conn.execute(
                    insert(tables.postings).values(
                        company_id=company_id, job_id=job_id, provider_posting_id=str(n),
                        title="Engineer", normalized_title="engineer",
                        url=f"https://boards.greenhouse.io/acme/jobs/{n}",
                        first_seen_at=NOW, last_seen_at=NOW, status="open",
                        consecutive_missing=0, content_hash="h", body_text="b",
                    )
                ).inserted_primary_key[0]
            )
            out.append((posting_id, job_id))
    return out


def test_apply_merges_writes_the_trail_and_then_the_projection(engine: Engine) -> None:
    """Claim 8."""
    (survivor, canonical), (loser, old_job) = _seed(engine, 2)
    with engine.begin() as conn:
        moved = apply_merges(
            conn,
            [JobMerge(posting_id=loser, from_job_id=old_job, to_job_id=canonical)],
            identity_kind="exact_quad",
            now=NOW,
        ).moved
    assert moved == 1
    with engine.connect() as conn:
        event = conn.execute(select(tables.job_grouping_events)).one()
        anchors = job_anchors(conn, [survivor, loser])
    assert event.posting_id == loser
    assert event.from_job_id == old_job
    assert event.to_job_id == canonical
    assert event.method == "exact_quad"
    assert anchors == {survivor: canonical, loser: canonical}


def test_the_trail_survives_a_second_pass_that_moves_nothing(engine: Engine) -> None:
    """Claim 9 at the store: after the first pass the planner sees the member already canonical,
    so no second event is appended — the trail is one entry per actual move."""
    (survivor, canonical), (loser, old_job) = _seed(engine, 2)
    merge = JobMerge(posting_id=loser, from_job_id=old_job, to_job_id=canonical)
    with engine.begin() as conn:
        apply_merges(conn, [merge], identity_kind="exact_quad", now=NOW)
    with engine.connect() as conn:
        plan = plan_regrouping(
            [_sup(loser, survivor)],
            job_anchors(conn, [survivor, loser]),
            protected_job_ids=protected_job_ids(conn),
            queue_action_job_ids=queue_action_job_ids(conn),
        )
    assert plan.merges == ()
    with engine.connect() as conn:
        events = conn.execute(select(tables.job_grouping_events)).all()
    assert len(events) == 1


def test_apply_merges_will_not_move_a_posting_whose_anchor_already_changed(
    engine: Engine,
) -> None:
    """The UPDATE is guarded on `from_job_id`, so a plan built against a stale read moves
    nothing rather than overwriting an anchor somebody else set.

    `from_job_id` is a real job here — a third seeded one — because the event's own FK already
    rejects a fabricated id, and the property under test is the guard on the projection UPDATE,
    not the FK.
    """
    (_survivor, canonical), (loser, _old_job), (_third, unrelated_job) = _seed(engine, 3)
    with engine.begin() as conn:
        moved = apply_merges(
            conn,
            [JobMerge(posting_id=loser, from_job_id=unrelated_job, to_job_id=canonical)],
            identity_kind="exact_quad",
            now=NOW,
        ).moved
    assert moved == 0
    with engine.connect() as conn:
        assert job_anchors(conn, [loser])[loser] == _old_job  # untouched
        # And no trail entry: `job_grouping_events` is the documented undo path, and D-104 rests
        # the write order on "the projection can be rebuilt from the trail, never the reverse".
        # An event whose guarded UPDATE matched 0 rows breaks precisely that — rebuilding would
        # move a posting nobody moved.
        assert conn.execute(select(tables.job_grouping_events)).all() == []


def test_protected_job_ids_reports_jobs_carrying_an_application(engine: Engine) -> None:
    (posting_id, job_id), _ = _seed(engine, 2)
    assert posting_id
    with engine.begin() as conn:
        conn.execute(
            insert(tables.applications).values(
                job_id=job_id, attempt_no=1, status="interested",
                created_at=NOW, updated_at=NOW,
            )
        )
    with engine.connect() as conn:
        assert protected_job_ids(conn) == frozenset({job_id})


def test_protected_job_ids_reports_jobs_carrying_an_artifact(engine: Engine) -> None:
    """Latent today — measured NULL on all 44 live artifact rows — but reachable, so guarded."""
    (_posting_id, job_id), _ = _seed(engine, 2)
    with engine.begin() as conn:
        conn.execute(
            insert(tables.artifacts).values(
                job_id=job_id, kind="resume", uri="/tmp/r.pdf", created_at=NOW
            )
        )
    with engine.connect() as conn:
        assert protected_job_ids(conn) == frozenset({job_id})


def test_protected_job_ids_is_empty_on_a_store_with_no_tracking(engine: Engine) -> None:
    """The live shape as measured 2026-08-10: 0 applications, all artifact job_ids NULL."""
    _seed(engine, 2)
    with engine.connect() as conn:
        assert protected_job_ids(conn) == frozenset()


# ------------------------------------------- the review's two store-level regressions (D-110)


def test_a_merge_carries_the_losers_live_disposition_onto_the_canonical_job(
    engine: Engine,
) -> None:
    """CLAIM: regrouping must not un-suppress an already-handled group.

    A decision is keyed on a job. Moving the postings off that job onto the survivor's leaves a
    `built` row governing a job nothing anchors, while the canonical job carries nothing — so the
    lead the program already built is surfaced and tailored again, which is the defect this slice
    exists to remove. The decision must travel with the postings, and the emptied row must be
    released rather than left live forever with no re-entry path.
    """
    (survivor, canonical), (loser, old_job) = _seed(engine, 2)
    with engine.begin() as conn:
        assert record_disposition(
            conn, old_job, disposition="built", reason="lead_built",
            policy_version="pol-1", now=NOW,
        )
    with engine.begin() as conn:
        moved = apply_merges(
            conn,
            [JobMerge(posting_id=loser, from_job_id=old_job, to_job_id=canonical)],
            identity_kind="exact_quad",
            now=NOW,
        ).moved
    assert moved == 1
    with engine.connect() as conn:
        live = live_dispositions(conn, now=NOW)
        stored = load_dispositions(conn)
    # The canonical job — the one both postings now anchor — governs.
    assert canonical in live
    assert live[canonical].disposition == "built"
    assert live[canonical].policy_version == "pol-1"
    # The emptied job no longer governs, but its row survives for the audit trail.
    assert old_job not in live
    assert old_job in stored
    assert stored[old_job].reopened_at == NOW


def test_a_merge_does_not_lower_a_disposition_the_canonical_job_already_carries(
    engine: Engine,
) -> None:
    """CLAIM: carrying is monotonic, so the strongest decision in the group wins.

    Written because carrying a `seen` row onto a job already `built` would be a downgrade, and the
    ledger's whole contract is that a permanent decision is never lowered by a weaker one.
    """
    (survivor, canonical), (loser, old_job) = _seed(engine, 2)
    with engine.begin() as conn:
        record_disposition(
            conn, canonical, disposition="built", reason="lead_built",
            policy_version="pol-1", now=NOW,
        )
        record_disposition(
            conn, old_job, disposition="seen", reason="surfaced",
            expires_at=NOW + timedelta(days=7), now=NOW,
        )
    with engine.begin() as conn:
        apply_merges(
            conn,
            [JobMerge(posting_id=loser, from_job_id=old_job, to_job_id=canonical)],
            identity_kind="exact_quad",
            now=NOW,
        )
    with engine.connect() as conn:
        live = live_dispositions(conn, now=NOW)
    assert live[canonical].disposition == "built"  # not lowered to `seen`
    assert live[canonical].expires_at is None


# ------------------------------------- T115A: a regroup must not release a job that still has
#                                              postings, nor drop one of a split source's targets


def test_a_source_that_still_has_postings_keeps_its_decision_and_the_target_gains_none(
    engine: Engine,
) -> None:
    """CLAIM: emptiness is a precondition for carrying, and nothing establishes it for free.

    The planner moves postings one at a time, so a later regrouping can take ONE member off a job
    two postings share. A carries `built`; B joined A's job, then left it again for C's. A never
    moved, so A's decision must still govern A — and C must not acquire a build it never earned
    merely because B once sat beside A.

    Fail-open by construction: B loses suppression and may re-surface, which is the correct
    direction. Un-suppressing A, which never moved, is not.
    """
    (a, job_a), (c, job_c), (b, job_b) = _seed(engine, 3)
    with engine.begin() as conn:
        apply_merges(
            conn,
            [JobMerge(posting_id=b, from_job_id=job_b, to_job_id=job_a)],
            identity_kind="exact_quad",
            now=NOW,
        )
        record_disposition(
            conn, job_a, disposition="built", reason="lead_built",
            policy_version="pol-1", now=NOW,
        )
    with engine.begin() as conn:
        apply_merges(
            conn,
            [JobMerge(posting_id=b, from_job_id=job_a, to_job_id=job_c)],
            identity_kind="exact_quad",
            now=NOW,
        )
    with engine.connect() as conn:
        assert job_anchors(conn, [a, b, c]) == {a: job_a, b: job_c, c: job_c}
        live = live_dispositions(conn, now=NOW)
        stored = load_dispositions(conn)
    # The SOURCE, on its own: A never moved, so the decision about A still governs A.
    assert job_a in live
    assert live[job_a].disposition == "built"
    assert stored[job_a].reopened_at is None
    # The TARGET, on its own: B's move is not evidence about C.
    assert job_c not in live


def test_an_emptied_source_whose_members_split_carries_onto_EVERY_target(  # noqa: N802 - emphasis
    engine: Engine,
) -> None:
    """CLAIM: one source, two targets, and the decision governed both members.

    The source-to-target map used to be a dict comprehension keyed on the source, so the last
    merge in the batch silently won: one target inherited nothing while the source was released
    anyway. Carrying to both is not a widening — `record_disposition` is monotonic and the
    decision genuinely governed every posting that sat on the source.
    """
    (p1, j1), (p2, j2), (p3, j3), (p4, j4) = _seed(engine, 4)
    with engine.begin() as conn:
        apply_merges(
            conn,
            [JobMerge(posting_id=p2, from_job_id=j2, to_job_id=j1)],
            identity_kind="exact_quad",
            now=NOW,
        )
        record_disposition(
            conn, j1, disposition="built", reason="lead_built",
            policy_version="pol-1", now=NOW,
        )
    with engine.begin() as conn:
        apply_merges(
            conn,
            [
                JobMerge(posting_id=p1, from_job_id=j1, to_job_id=j3),
                JobMerge(posting_id=p2, from_job_id=j1, to_job_id=j4),
            ],
            identity_kind="exact_quad",
            now=NOW,
        )
    with engine.connect() as conn:
        assert job_anchors(conn, [p1, p2, p3, p4]) == {p1: j3, p2: j4, p3: j3, p4: j4}
        live = live_dispositions(conn, now=NOW)
        stored = load_dispositions(conn)
    assert live[j3].disposition == "built"
    assert live[j4].disposition == "built"
    # The source emptied, so it is released — with a re-entry path, not a deletion.
    assert j1 not in live
    assert stored[j1].reopened_at == NOW


def test_a_refused_carry_is_counted_so_a_run_can_report_it(engine: Engine) -> None:
    """A refusal nobody can count is a leak, exactly as an unreported planner refusal would be."""
    (_a, job_a), (_c, job_c), (b, job_b) = _seed(engine, 3)
    with engine.begin() as conn:
        apply_merges(
            conn,
            [JobMerge(posting_id=b, from_job_id=job_b, to_job_id=job_a)],
            identity_kind="exact_quad",
            now=NOW,
        )
        record_disposition(
            conn, job_a, disposition="built", reason="lead_built",
            policy_version="pol-1", now=NOW,
        )
    with engine.begin() as conn:
        outcome = apply_merges(
            conn,
            [JobMerge(posting_id=b, from_job_id=job_a, to_job_id=job_c)],
            identity_kind="exact_quad",
            now=NOW,
        )
    assert outcome.moved == 1
    assert outcome.refused_non_empty == 1


def test_the_refusal_count_names_only_sources_that_actually_held_a_decision(
    engine: Engine,
) -> None:
    """A source with nothing live to carry withheld nothing. Counting it would report a decision
    that was never at stake, and the number has to mean "a decision stayed behind" to be acted on.
    """
    (_a, job_a), (_c, job_c), (b, job_b) = _seed(engine, 3)
    with engine.begin() as conn:
        apply_merges(
            conn,
            [JobMerge(posting_id=b, from_job_id=job_b, to_job_id=job_a)],
            identity_kind="exact_quad",
            now=NOW,
        )
    with engine.begin() as conn:
        outcome = apply_merges(
            conn,
            [JobMerge(posting_id=b, from_job_id=job_a, to_job_id=job_c)],
            identity_kind="exact_quad",
            now=NOW,
        )
    assert outcome.moved == 1
    assert outcome.refused_non_empty == 0


def test_the_whole_job_carry_reports_no_refusal(engine: Engine) -> None:
    """Green control for the count: the emptying source is the live shape, and it is not a
    refusal. Pairs with `test_a_merge_carries_the_losers_live_disposition_onto_the_canonical_job`,
    which pins the transfer itself."""
    (_survivor, canonical), (loser, old_job) = _seed(engine, 2)
    with engine.begin() as conn:
        record_disposition(
            conn, old_job, disposition="built", reason="lead_built",
            policy_version="pol-1", now=NOW,
        )
    with engine.begin() as conn:
        outcome = apply_merges(
            conn,
            [JobMerge(posting_id=loser, from_job_id=old_job, to_job_id=canonical)],
            identity_kind="exact_quad",
            now=NOW,
        )
    assert outcome == MergeOutcome(moved=1, refused_non_empty=0)


# ------------------------------- T115B: a regroup must not strand a skip, report or follow-up


def _mark_skip(conn: Connection, job_id: int) -> None:
    mark_job_skipped(conn, job_id=job_id, at=NOW)


def _mark_report(conn: Connection, job_id: int) -> None:
    mark_job_reported(conn, job_id=job_id, at=NOW)


def _mark_followup(conn: Connection, job_id: int) -> None:
    set_job_followup(conn, job_id=job_id, on=NOW.date())


QUEUE_ACTIONS = [
    pytest.param(_mark_skip, skipped_job_ids, id="skip"),
    pytest.param(_mark_report, reported_job_ids, id="report"),
    pytest.param(_mark_followup, followup_job_dates, id="followup"),
]


def test_a_queue_action_on_a_loser_job_refuses_the_WHOLE_group(  # noqa: N802 - emphasis
) -> None:
    """Same shape as the tracked-job refusal: a partially-merged group is a third state nothing
    downstream understands, so one actioned member holds the whole group."""
    plan = plan_regrouping(
        [_sup(2, 1), _sup(3, 1)],
        {1: 10, 2: 20, 3: 30},
        protected_job_ids=frozenset(),
        queue_action_job_ids=frozenset({20}),
    )
    assert plan.merges == ()
    assert len(plan.refusals) == 1
    refusal = plan.refusals[0]
    assert refusal.reason == "queue_action_job"
    assert refusal.survivor_posting_id == 1
    assert refusal.member_posting_ids == (1, 2, 3)


def test_a_queue_actioned_SURVIVOR_job_does_not_refuse_anything(  # noqa: N802 - emphasis
) -> None:
    """Nothing moves off the survivor's job, so its skip stays exactly where its reader looks."""
    plan = plan_regrouping(
        [_sup(2, 1)],
        {1: 10, 2: 20},
        protected_job_ids=frozenset(),
        queue_action_job_ids=frozenset({10}),
    )
    assert plan.merges == (JobMerge(posting_id=2, from_job_id=20, to_job_id=10),)
    assert plan.refusals == ()


def test_a_job_that_is_both_tracked_and_actioned_is_reported_as_tracked() -> None:
    """The two sets stay separate because the refusal is read by the owner and the remedies
    differ. When both apply, the larger consequence — a silently wrong applied count — names it.
    """
    plan = plan_regrouping(
        [_sup(2, 1)],
        {1: 10, 2: 20},
        protected_job_ids=frozenset({20}),
        queue_action_job_ids=frozenset({20}),
    )
    assert plan.refusals[0].reason == "tracked_job"


def test_queue_action_job_ids_reports_each_family_and_nothing_else(engine: Engine) -> None:
    """All three families, and no bleed into `protected_job_ids` — they are different refusals."""
    (_p1, j1), (_p2, j2), (_p3, j3), (_p4, _j4) = _seed(engine, 4)
    with engine.connect() as conn:
        assert queue_action_job_ids(conn) == frozenset()
    with engine.begin() as conn:
        mark_job_skipped(conn, job_id=j1, at=NOW)
        mark_job_reported(conn, job_id=j2, at=NOW)
        set_job_followup(conn, job_id=j3, on=date(2026, 9, 1))
    with engine.connect() as conn:
        assert queue_action_job_ids(conn) == frozenset({j1, j2, j3})
        assert protected_job_ids(conn) == frozenset()


@pytest.mark.parametrize(("mark", "read"), QUEUE_ACTIONS)
def test_a_queue_action_survives_a_regroup_because_the_regroup_is_refused(
    engine: Engine,
    mark: Callable[[Connection, int], None],
    read: Callable[[Connection], dict[int, str]],
) -> None:
    """CLAIM: skip, report and follow-up are keyed on the job, and every reader resolves through
    the posting's CURRENT job id — so a merge would strand the owner's own statement on a job
    nothing anchors, with nothing left to recover the intent from.

    The pre-regroup assertion is the positive control: it proves the reader really does see the
    action through the posting's anchor, so the post-regroup one is about the merge and not about
    a reader that never worked.
    """
    (survivor, _canonical), (loser, old_job) = _seed(engine, 2)
    with engine.begin() as conn:
        mark(conn, old_job)
    with engine.connect() as conn:
        assert job_anchors(conn, [loser])[loser] in read(conn)  # positive control
    with engine.begin() as conn:
        plan = plan_regrouping(
            [_sup(loser, survivor)],
            job_anchors(conn, [survivor, loser]),
            protected_job_ids=protected_job_ids(conn),
            queue_action_job_ids=queue_action_job_ids(conn),
        )
        outcome = apply_merges(conn, plan.merges, identity_kind="exact_quad", now=NOW)
    assert plan.merges == ()
    assert [refusal.reason for refusal in plan.refusals] == ["queue_action_job"]
    assert outcome.moved == 0
    with engine.connect() as conn:
        assert job_anchors(conn, [loser])[loser] == old_job
        assert job_anchors(conn, [loser])[loser] in read(conn)
        assert conn.execute(select(tables.job_grouping_events)).all() == []


def test_two_members_carrying_CONFLICTING_actions_refuse_rather_than_pick_one(  # noqa: N802
    engine: Engine,
) -> None:
    """Combining a skip with a report, or resolving two follow-up dates, is a merge policy nobody
    has specified. Refusing keeps each statement unambiguously the owner's."""
    (survivor, _canonical), (loser_a, job_a), (loser_b, job_b) = _seed(engine, 3)
    with engine.begin() as conn:
        mark_job_skipped(conn, job_id=job_a, at=NOW)
        set_job_followup(conn, job_id=job_a, on=date(2026, 9, 1))
        mark_job_reported(conn, job_id=job_b, at=NOW)
        set_job_followup(conn, job_id=job_b, on=date(2026, 10, 1))
    with engine.begin() as conn:
        plan = plan_regrouping(
            [_sup(loser_a, survivor), _sup(loser_b, survivor)],
            job_anchors(conn, [survivor, loser_a, loser_b]),
            protected_job_ids=protected_job_ids(conn),
            queue_action_job_ids=queue_action_job_ids(conn),
        )
        apply_merges(conn, plan.merges, identity_kind="exact_quad", now=NOW)
    assert [refusal.reason for refusal in plan.refusals] == ["queue_action_job"]
    with engine.connect() as conn:
        assert skipped_job_ids(conn).keys() == {job_a}
        assert reported_job_ids(conn).keys() == {job_b}
        assert followup_job_dates(conn) == {job_a: "2026-09-01", job_b: "2026-10-01"}
        assert job_anchors(conn, [loser_a, loser_b]) == {loser_a: job_a, loser_b: job_b}


def test_one_actioned_member_holds_the_CLEAN_members_back_too(  # noqa: N802 - emphasis
    engine: Engine,
) -> None:
    """A partial move is what T115A refuses to release a source for, so the planner must not
    create one here either: the clean member stays put alongside the actioned one."""
    (survivor, canonical), (clean, clean_job), (skipped, skipped_job) = _seed(engine, 3)
    with engine.begin() as conn:
        mark_job_skipped(conn, job_id=skipped_job, at=NOW)
    with engine.begin() as conn:
        plan = plan_regrouping(
            [_sup(clean, survivor), _sup(skipped, survivor)],
            job_anchors(conn, [survivor, clean, skipped]),
            protected_job_ids=protected_job_ids(conn),
            queue_action_job_ids=queue_action_job_ids(conn),
        )
        apply_merges(conn, plan.merges, identity_kind="exact_quad", now=NOW)
    assert plan.merges == ()
    with engine.connect() as conn:
        assert job_anchors(conn, [survivor, clean, skipped]) == {
            survivor: canonical, clean: clean_job, skipped: skipped_job,
        }
