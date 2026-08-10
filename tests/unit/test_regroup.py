"""P6 slice 2: job regrouping, planner and store (design §3; §8 claims 7, 8, 9)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, select

from boardwatch.core.dedup import Suppression
from boardwatch.core.regroup import REGROUP_REFUSALS, JobMerge, plan_regrouping
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.regroup import apply_merges, job_anchors, protected_job_ids

NOW = datetime(2026, 8, 10, 12, 0, 0)


def _sup(loser: int, survivor: int) -> Suppression:
    return Suppression(posting_id=loser, survivor_posting_id=survivor, kind="exact_quad")


# ------------------------------------------------------------------ the planner


def test_a_loser_moves_onto_the_survivors_job() -> None:
    plan = plan_regrouping(
        [_sup(2, 1)], {1: 10, 2: 20}, protected_job_ids=frozenset()
    )
    assert plan.merges == (JobMerge(posting_id=2, from_job_id=20, to_job_id=10),)
    assert plan.refusals == ()


def test_the_canonical_job_is_the_survivors_never_a_second_election() -> None:
    """The survivor is whichever posting `resolve_duplicates` elected — even when it carries the
    HIGHER job id, so no implicit "lowest job wins" rule can creep in."""
    plan = plan_regrouping([_sup(2, 1)], {1: 99, 2: 5}, protected_job_ids=frozenset())
    assert plan.merges == (JobMerge(posting_id=2, from_job_id=5, to_job_id=99),)


def test_a_member_already_on_the_canonical_job_plans_nothing() -> None:
    """Idempotence: a second pass over an unchanged corpus is a no-op."""
    plan = plan_regrouping([_sup(2, 1)], {1: 10, 2: 10}, protected_job_ids=frozenset())
    assert plan.merges == ()
    assert plan.refusals == ()


def test_a_three_member_group_moves_both_losers() -> None:
    plan = plan_regrouping(
        [_sup(2, 1), _sup(3, 1)], {1: 10, 2: 20, 3: 30}, protected_job_ids=frozenset()
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
        [_sup(2, 1)], {1: 10, 2: 20}, protected_job_ids=frozenset({10})
    )
    assert plan.merges == (JobMerge(posting_id=2, from_job_id=20, to_job_id=10),)


def test_a_missing_job_anchor_is_a_counted_refusal_not_a_silent_skip() -> None:
    plan = plan_regrouping([_sup(2, 1)], {1: 10}, protected_job_ids=frozenset())
    assert plan.merges == ()
    assert plan.refusals[0].reason == "missing_job_anchor"


def test_every_refusal_reason_is_in_the_closed_catalog() -> None:
    reasons = {
        plan_regrouping(
            [_sup(2, 1)], {1: 10, 2: 20}, protected_job_ids=frozenset({20})
        ).refusals[0].reason,
        plan_regrouping([_sup(2, 1)], {1: 10}, protected_job_ids=frozenset()).refusals[0].reason,
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
        )
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
        )
    assert moved == 0
    with engine.connect() as conn:
        assert job_anchors(conn, [loser])[loser] == _old_job  # untouched


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
