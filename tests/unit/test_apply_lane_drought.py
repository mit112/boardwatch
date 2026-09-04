"""Apply-lane drought detector. Each firing test names the wrong-version it rejects.

A real schema on `tmp_path`, seeded through the FK chain out to a tailored artifact, because
`apply_lane_placements` reads `delivered_unapplied` — which joins FROM `artifacts` outward, so a
lead with no artifact is not delivered and this detector cannot see it.

The lane is steered by LOCATION alone here, and deliberately: `Boston, MA` classifies `us` and
routes to the apply queue, `Berlin, Germany` classifies `non_us` and routes to `_review`. Both
were confirmed against the real `review_gate.classify` before these tests were written. Every
lead carries a real evaluation of `JD` under a real stored profile, which is what leaves location
as the only thing deciding: since A3 an unevaluated lead, and an evaluated one whose JD states no
requirement, are BOTH held for review, so a fixture that seeded no verdict would put every lead
in `_review` and no location assertion here could fail. That covers the `closed` exclusion and
both lanes through the real store path. The one exclusion the real path cannot reach cheaply is
`ineligible`, and the last test says why and injects instead.

`BOARDWATCH_CONFIG_DIR` is forced onto `tmp_path` for the reason `test_delivery_queries.py` gives:
`delivered_unapplied` resolves the eligibility identity through `load_settings()`, and without it
the read would run against whatever `rules.yaml` override sits in the developer's config dir.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Connection, Engine, insert

from boardwatch.core.settings import load_settings
from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.engine import evaluate, write_evaluation
from boardwatch.eligibility.facts import Facts, Policy
from boardwatch.eligibility.hashing import build_identity
from boardwatch.eligibility.resolve import declared_fields
from boardwatch.notify.apply_lane_drought import (
    APPLY_LANE_DROUGHT_MIN_PLACEABLE,
    APPLY_LANE_DROUGHT_WINDOW,
    check_apply_lane_drought,
)
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import RUN_OK, save_profile
from boardwatch.store.tables import artifacts, companies, jobs, posting_versions, postings, runs

NOW = datetime(2026, 8, 31, 4, 0, 0)

APPLY_LOCATION = ["Boston, MA"]
REVIEW_LOCATION = ["Berlin, Germany"]
#: A body the catalog reads ONE requirement out of, from a family the default policy leaves a
#: `preference` — so the evaluation is `eligible` with a row, and neither A3's zero-row hold nor
#: either older requirement hold fires. A content-free body would be held for review on its own
#: and the location split below would stop being observable.
JD = "Bachelor's degree in Computer Science required."
#: A body the catalog matches NOTHING in, so its evaluation produces zero requirement rows. Such a
#: lead is US and software and still not blindly appliable (A3), which is the third way a run's
#: work can fail to reach the apply lane — and the one `apply_lane_placements` would miss if its
#: `lane(...)` call dropped the argument.
SILENT_JD = "Join our team. We build delightful things and we value curiosity."


@pytest.fixture(autouse=True)
def _scratch_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(tmp_path / "data"))


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path / "data")
    ensure_schema(eng)
    return eng


_counter = iter(range(1, 10_000))


def _lead(
    conn: Connection,
    *,
    run_id: int,
    locations: list[str],
    status: str = "open",
    delivered_at: datetime = NOW,
    body: str = JD,
) -> None:
    """One delivered lead on its own company and its own canonical job.

    Its own job matters: `delivered_unapplied` collapses to ONE row per job, so two leads sharing
    a job would silently seed one row and a count assertion would be off by the difference.
    """
    key = f"k{next(_counter)}"
    company_id = int(
        conn.execute(
            insert(companies).values(
                name=f"Acme {key}", provider="greenhouse", slug=f"acme-{key}",
                source="user", watched=True,
            )
        ).inserted_primary_key[0]
    )
    job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
    posting_id = int(
        conn.execute(
            insert(postings).values(
                company_id=company_id, job_id=job_id, provider_posting_id=key,
                title="Software Engineer", normalized_title="software engineer",
                url="https://boards.test/apply", locations_json=locations,
                remote_policy="onsite", posted_at=NOW - timedelta(days=2), first_seen_at=NOW,
                last_seen_at=NOW, status=status,
                closed_at=NOW if status == "closed" else None,
                consecutive_missing=0, content_hash=f"hash-{key}", body_text=body,
            )
        ).inserted_primary_key[0]
    )
    version_id = int(
        conn.execute(
            insert(posting_versions).values(
                posting_id=posting_id, content_hash=f"v-{posting_id}", body_text=body,
                captured_at=NOW, run_id=None, capture_reason="new",
            )
        ).inserted_primary_key[0]
    )
    # The profile AND the evaluation: `current_identity` reads the store, so with no profile saved
    # every verdict comes back `None` however many evaluations were written. `save_profile` keys by
    # content, so calling it once per lead stores the same identity every time.
    save_profile(
        conn, text="resume", target_titles=["software engineer"], exclude_titles=[],
        locations=["Boston, MA"], remote_only=False, skills=["python"],
        taxonomy_version="v1", resume_max_pages=1,
    )
    catalog = load_rules(load_settings().config_dir)
    write_evaluation(
        conn,
        posting_version_id=version_id,
        identity=build_identity(
            posting_version_id=version_id, facts=Facts(), policy=Policy(),
            catalog=catalog, declared_fields=declared_fields(),
        ),
        result=evaluate(body, Facts(), Policy(), catalog),
    )
    conn.execute(
        insert(artifacts).values(
            posting_version_id=version_id, kind="resume_tailored",
            uri=f"/out/{key}/tailored-{posting_id}.typ", generator="boardwatch.tailor",
            media_type="text/x-tex", meta_json={"pdf_uri": None},
            created_at=delivered_at, run_id=run_id,
        )
    )


def _run(
    engine: Engine,
    *,
    apply_lane: int = 0,
    review_lane: int = 0,
    silent_lane: int = 0,
    closed: int = 0,
    status: str = RUN_OK,
) -> int:
    """One run plus the leads it delivered, split by the lane each will classify into.

    `silent_lane` leads are US and software like `apply_lane` ones and differ ONLY in their body,
    which states no requirement — so they route to review on A3's gate rather than on location."""
    with engine.begin() as conn:
        run_id = int(
            conn.execute(
                insert(runs).values(
                    started_at=NOW, finished_at=NOW, status=status, boards_attempted=0
                )
            ).inserted_primary_key[0]
        )
        for _ in range(apply_lane):
            _lead(conn, run_id=run_id, locations=APPLY_LOCATION)
        for _ in range(review_lane):
            _lead(conn, run_id=run_id, locations=REVIEW_LOCATION)
        for _ in range(silent_lane):
            _lead(conn, run_id=run_id, locations=APPLY_LOCATION, body=SILENT_JD)
        for _ in range(closed):
            _lead(conn, run_id=run_id, locations=APPLY_LOCATION, status="closed")
    return run_id


# ------------------------------------------------------------------------------------- the alarm


def test_fires_when_every_run_placed_leads_and_none_reached_the_apply_lane(
    engine: Engine,
) -> None:
    """The fault this detector exists for: leads keep being delivered — so `delivery_drought`
    abstains and the heartbeat stays green — and every one is routed to review."""
    ids = [_run(engine, review_lane=2) for _ in range(3)]
    alert = check_apply_lane_drought(engine, window=3, min_placeable=1)
    assert alert is not None
    assert "0 of 6 placeable lead(s)" in alert
    for run_id in ids:
        assert str(run_id) in alert


def test_fires_when_every_lead_was_held_for_stating_no_requirement(engine: Engine) -> None:
    """The same drought reached through A3's gate instead of the location gate.

    These leads are US, software, and evaluated — the only thing wrong with them is that the
    catalog found no requirement in the body, which is 521 of 646 apply-lane leads on the live
    store. `apply_lane_placements` must count them PLACEABLE (they are real delivered work, not
    ineligible and not closed) and NOT in the apply lane; the control below is the identical shape
    with a body that states a requirement, which does reach it. Rejects dropping the new argument
    from `apply_lane_placements`' `lane(...)` call, which no other test in this file can see.
    """
    ids = [_run(engine, silent_lane=2) for _ in range(3)]
    alert = check_apply_lane_drought(engine, window=3, min_placeable=1)
    assert alert is not None
    assert "0 of 6 placeable lead(s)" in alert
    for run_id in ids:
        assert str(run_id) in alert


def test_the_same_leads_with_a_stated_requirement_DO_reach_the_apply_lane(
    engine: Engine,
) -> None:
    """The control for the test above: same location, same title, only the body differs."""
    _run(engine, apply_lane=2)
    assert check_apply_lane_drought(engine, window=3, min_placeable=1) is None


def test_silent_when_a_run_in_the_window_reached_the_apply_lane(engine: Engine) -> None:
    # Rejects dropping the apply-arrivals check: ONE lead in the blind-apply list proves the
    # location, role and requirement gates still pass something, which is the whole claim.
    _run(engine, review_lane=2)
    _run(engine, review_lane=2)
    _run(engine, review_lane=2, apply_lane=1)  # newest placed one
    assert check_apply_lane_drought(engine, window=3, min_placeable=1) is None


def test_silent_when_a_run_placed_nothing(engine: Engine) -> None:
    # The false-positive guard, and the anti-double-report guard in one. A run that delivered no
    # placeable lead is `check_delivery_drought`'s story; firing here too would state two
    # diagnoses for one cause. Rejects dropping the placeable>0 abstain, which would fire on
    # every quiet day and on a fresh store.
    _run(engine, review_lane=2)
    _run(engine, review_lane=2)
    _run(engine)  # delivered nothing at all
    assert check_apply_lane_drought(engine, window=3, min_placeable=1) is None


def test_closed_leads_are_not_placeable(engine: Engine) -> None:
    """A run whose every lead has since come down is a LIVENESS story with its own drain
    (D-383), not evidence about the lane gates.

    Rejects removing the `row.closed` exclusion from `apply_lane_placements`: without it these
    leads count as placeable, `lane` routes them to `_closed` rather than `""`, and the detector
    fires — naming the location/role/requirement gates for a fault that is entirely liveness.
    The control below proves the seeding really does produce leads this detector can see.
    """
    for _ in range(3):
        _run(engine, closed=2)
    assert check_apply_lane_drought(engine, window=3, min_placeable=1) is None
    # Control: the same shape with OPEN postings in the review lane does fire, so the abstain
    # above is attributable to `closed` and not to leads the detector never saw. These three
    # become the newest clean runs, so they are the window.
    for _ in range(3):
        _run(engine, review_lane=2)
    assert check_apply_lane_drought(engine, window=3, min_placeable=1) is not None


def test_abstains_below_the_window(engine: Engine) -> None:
    _run(engine, review_lane=2)
    _run(engine, review_lane=2)
    assert check_apply_lane_drought(engine, window=3, min_placeable=1) is None


def test_only_clean_runs_count(engine: Engine) -> None:
    # A later non-ok run (crashed or in-flight) is excluded, so the three clean starvations still
    # fire, and its apply-lane delivery must not rescue the window. Rejects dropping the status
    # filter.
    for _ in range(3):
        _run(engine, review_lane=2)
    _run(engine, apply_lane=5, status="running")  # newest, not ok
    assert check_apply_lane_drought(engine, window=3, min_placeable=1) is not None


def test_default_window_is_three(engine: Engine) -> None:
    assert APPLY_LANE_DROUGHT_WINDOW == 3
    _run(engine, review_lane=2)
    _run(engine, review_lane=2)
    assert check_apply_lane_drought(engine, min_placeable=1) is None
    _run(engine, review_lane=2)
    assert check_apply_lane_drought(engine, min_placeable=1) is not None


# ----------------------------------------------------------------------- the placeable-set fold


def test_ineligible_leads_are_not_placeable(monkeypatch: pytest.MonkeyPatch) -> None:
    """A run whose delivered leads have all since read `ineligible` is an eligibility COLLAPSE,
    which `check_corpus_regression` owns. Counting them placeable here would fire a second
    detector on one cause and name the lane gates for a fault in the rules or the facts.

    The rows are INJECTED rather than seeded, and only here. Producing a genuine `ineligible`
    through the store needs a profile whose work-auth and clearance facts resolve against the
    live catalog — three probes against the real engine returned `uncertain`, because with no
    resolvable fact every hard-family rule correctly ABSTAINS (the keystone invariant). The fold
    under test takes `QueueRow`s and returns counts, so its inputs are exactly what is injected;
    the real store path is covered end to end by every other test in this file.
    """
    from boardwatch.store import delivery_queries
    from boardwatch.store.delivery_queries import QueueRow, apply_lane_placements

    # `delivered_unapplied` is replaced below, so the connection is never touched; the fold
    # takes it only to pass it on. `cast` rather than a live connection keeps the test to the
    # fold and off the schema.
    conn = cast(Connection, None)

    def _row(posting_id: int, verdict: str | None, locations: tuple[str, ...]) -> QueueRow:
        return QueueRow(
            posting_id=posting_id, job_id=posting_id, title="Software Engineer",
            company="Acme", location=", ".join(locations), locations=locations,
            remote_policy="onsite", posted_days=2, first_seen=NOW, status="open",
            verdict=verdict, apply_url="https://boards.test/apply", delivered_run_id=7,
            tex_uri="/out/t.typ", pdf_uri=None, target_flag=None,
        )

    injected = [_row(1, "ineligible", ("Boston, MA",))]
    monkeypatch.setattr(
        delivery_queries, "delivered_unapplied", lambda conn, *, skipped: injected
    )
    # Both rows would route to `_review` — the ineligible one for its verdict, the foreign one
    # for its location — so a fold that did not exclude ineligible would report them alike.
    assert apply_lane_placements(conn, run_ids={7}) == {7: (0, 0)}

    # Control: the SAME shape with the verdict `uncertain` IS placeable, so the zero above is
    # attributable to the `ineligible` exclusion and not to the row being invisible to the fold.
    #
    # `uncertain`, not `None`: since A3 an unevaluated lead is held for review on its own, so a
    # `None` control would be placeable-but-never-in-the-apply-lane and the last line could not
    # distinguish the exclusion from the hold. `_row` leaves `requirement_flags` at its all-False
    # default, which for an `uncertain` verdict means "rows exist, none unconfirmed".
    injected[:] = [_row(1, "uncertain", ("Berlin, Germany",))]
    assert apply_lane_placements(conn, run_ids={7}) == {7: (1, 0)}
    injected[:] = [_row(1, "uncertain", ("Boston, MA",))]
    assert apply_lane_placements(conn, run_ids={7}) == {7: (1, 1)}


# ------------------------------------------------------- the window population floor (D-458 fallout)


def test_min_placeable_default_is_pinned_literally() -> None:
    """Pinned as a LITERAL, not compared against an import of itself, which would assert nothing.

    101 is `ceil(log(0.001) / log(1 - 0.0666))` at the measured post-D-458 apply rate — the
    smallest window population whose all-zero outcome stays <= 0.1% likely on a healthy lane.
    """
    assert APPLY_LANE_DROUGHT_MIN_PLACEABLE == 101


def test_a_starved_window_below_the_floor_stays_quiet(engine: Engine) -> None:
    """THE regression this change exists for.

    Three clean runs, every lead routed to review, zero arrivals — the exact shape the detector
    fires on. At 2 placeable leads per run the window holds 6, and at a 6.66% conversion rate a
    HEALTHY lane produces that zero about two times in three. Firing here is a false alarm.

    This test FAILS against the unfloored implementation, which returns an alert.
    """
    for _ in range(3):
        _run(engine, review_lane=2)
    assert check_apply_lane_drought(engine, window=3) is None


def test_it_still_fires_once_the_window_clears_the_floor(engine: Engine) -> None:
    """The floor must not be a blanket mute: given a real population, the alarm still works.

    Paired with the test above, this is what proves the floor SIZES the alarm rather than
    disabling it — a mutation that returned `None` unconditionally would pass that one and fail
    this one.
    """
    for _ in range(3):
        _run(engine, review_lane=40)  # 120 placeable across the window, over the 101 floor
    alert = check_apply_lane_drought(engine, window=3)
    assert alert is not None
    assert "0 of 120 placeable lead(s)" in alert


def test_the_floor_is_exclusive_at_its_boundary(engine: Engine) -> None:
    """`placeable < min_placeable` abstains; equality fires. Rejects a `<=` off-by-one, which
    would silence the alarm on exactly the population it was sized to be trustworthy at."""
    for _ in range(3):
        _run(engine, review_lane=3)  # 9 placeable
    assert check_apply_lane_drought(engine, window=3, min_placeable=10) is None
    assert check_apply_lane_drought(engine, window=3, min_placeable=9) is not None


def test_one_arrival_anywhere_in_the_window_keeps_it_quiet(engine: Engine) -> None:
    """Arrivals are summed over the window too. A single lead reaching the apply lane in ANY run
    of the window proves the gates still pass something, so the window is not a drought — even
    when the other two runs are fully starved and the population is well over the floor."""
    _run(engine, review_lane=40)
    _run(engine, apply_lane=1, review_lane=39)
    _run(engine, review_lane=40)
    assert check_apply_lane_drought(engine, window=3, min_placeable=10) is None
