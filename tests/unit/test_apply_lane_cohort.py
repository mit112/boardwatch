"""B8's volume cohort: the leads a run delivered that SURVIVE to the apply lane (T110).

The defect these pin is an ORDERING one, so every test here goes through the real
`collect_run_funnel` rather than the pure builder: `pending_tailor` — which the funnel's `pdf`
stage enters at — is stamped before the tailor loop, and `runner`'s application-form sweep runs
after the render and before the artifact is written. Only a test that builds the artifact from a
store carrying BOTH facts can show the two numbers coming apart.

The store fixtures are `test_apply_lane_drought.py`'s, imported rather than copied: they already
seed the whole FK chain out to a delivered artifact under a real profile and a real evaluation,
which is what `delivered_unapplied` needs before a lane decision means anything. The lane is
steered by LOCATION there, and by the application form here.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, insert

from boardwatch.core.settings import load_settings
from boardwatch.notify.apply_lane_drought import check_apply_lane_drought
from boardwatch.notify.apply_lane_volume import (
    APPLY_LANE_VOLUME_BAR,
    check_apply_lane_volume,
)
from boardwatch.pipeline.funnel_writer import collect_run_funnel
from boardwatch.reports.run_funnel import (
    ApplyLaneCohort,
    RunFunnel,
    ScanContext,
    Stage,
    funnel_to_dict,
    funnel_to_markdown,
)
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.delivery_queries import (
    LanePlacement,
    apply_lane_cohort,
    apply_lane_placements,
    delivered_unapplied,
    lane_decision,
    review_job_ids,
)
from boardwatch.store.tables import jobs, posting_form_questions, runs
from tests.conftest import write_bundled_role_taxonomy
from tests.unit.test_apply_lane_drought import (
    APPLY_LOCATION,
    NOW,
    REVIEW_LOCATION,
    _lead,
)

#: A Greenhouse form question `delivery/form_questions.CATALOG`'s `citizenship_required` surface
#: matches. It is the T91 hard stop: the JD says nothing about citizenship, so this lead reads
#: apply-lane on every signal the render was decided on and is only held once the form is known.
CITIZENSHIP_QUESTION = "Are you a U.S. citizen?"


@pytest.fixture(autouse=True)
def _scratch_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(tmp_path / "data"))
    # A software user (T184b): the lane reads the role gate from the user's taxonomy.
    write_bundled_role_taxonomy(tmp_path / "config")


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path / "data")
    ensure_schema(eng)
    return eng


def _hard_stop(conn: Connection, version_id: int) -> None:
    """The application-form sweep's result for one version, as the sweep itself stores it.

    Written straight to `posting_form_questions` rather than through the sweep: the sweep is a
    network pass and the catalog is applied fresh on every READ, so the stored payload is the
    whole of what it leaves behind.
    """
    conn.execute(
        insert(posting_form_questions).values(
            posting_version_id=version_id,
            questions_json=[
                {"label": CITIZENSHIP_QUESTION, "description": None, "options": []}
            ],
            fetched_at=NOW,
        )
    )


def _funnel(engine: Engine, run_id: int, rendered: list[int]) -> RunFunnel:
    """The artifact for `run_id`, with `rendered` presented as APPLY-lane leads the tailor
    rendered — `pending_tailor=False`, a PDF built — which is what `pdf.entered` counts."""
    settings = load_settings()
    return collect_run_funnel(
        engine,
        settings,
        run_id=run_id,
        scan=ScanContext(ran=False),
        shortlist=None,
        tailored=[
            (posting_id, "Acme", "Software Engineer", Path("/out"), True, False)
            for posting_id in rendered
        ],
        tailor_failed=0,
        projection_ran=False,
        rewrite_rows=[],
        lanes=[],
        stage_durations=None,
        errors=[],
        fatal=None,
    )


def _cohort(engine: Engine, run_id: int) -> tuple[LanePlacement, ...]:
    with engine.connect() as conn:
        return apply_lane_cohort(conn, run_ids={run_id})[run_id]


def _stage(funnel: RunFunnel, name: str) -> Stage:
    return next(stage for stage in funnel.stages if stage.name == name)


def _run(engine: Engine) -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(
                insert(runs).values(
                    started_at=NOW, finished_at=NOW, status="ok", boards_attempted=0
                )
            ).inserted_primary_key[0]
        )


# ------------------------------------------------------------------- the defect and its control


def test_a_lead_form_hard_stopped_after_its_render_leaves_the_cohort_but_not_the_pdf_stage(
    engine: Engine,
) -> None:
    """**The T110 defect.** This lead was rendered into the apply lane — `pending_tailor` was
    stamped False before the tailor loop and a PDF was built — and the form sweep, which runs
    after the render and before this artifact is written, then hard-stopped it. It can never be
    applied to.

    Both assertions are here deliberately: the point is not that the cohort is a new name for
    `pdf.entered`, it is that the two SPLIT. `pdf.entered` is right about rendering and keeps its
    1; the cohort is B8's volume reading and is 0.
    """
    run_id = _run(engine)
    with engine.begin() as conn:
        posting_id, version_id = _lead(conn, run_id=run_id, locations=APPLY_LOCATION)
        _hard_stop(conn, version_id)

    funnel = _funnel(engine, run_id, [posting_id])

    assert _stage(funnel, "pdf").entered == 1
    assert funnel.apply_lane is not None
    assert funnel.apply_lane.in_apply == 0
    assert funnel.apply_lane.placements == (
        LanePlacement(
            posting_id=posting_id,
            job_id=funnel.apply_lane.placements[0].job_id,
            lane="_review",
            review_reason="form_question_hard_stop",
        ),
    )


def test_with_no_hard_stop_the_two_numbers_agree(engine: Engine) -> None:
    """**The null control.** The same run, the same lead, no form row — so nothing downstream of
    the render moved it and the cohort must equal `pdf.entered`.

    Without this, a cohort that is always smaller than the render count (an off-by-one, a
    dropped row, an exclusion that is too wide) would pass the test above for the wrong reason.
    """
    run_id = _run(engine)
    with engine.begin() as conn:
        posting_id, _ = _lead(conn, run_id=run_id, locations=APPLY_LOCATION)

    funnel = _funnel(engine, run_id, [posting_id])

    assert funnel.apply_lane is not None
    assert _stage(funnel, "pdf").entered == funnel.apply_lane.in_apply == 1
    assert funnel.apply_lane.placements[0].lane == ""
    assert funnel.apply_lane.placements[0].review_reason is None


# -------------------------------------------------------------------------------- the round-trip


def test_the_recorded_ids_are_exactly_what_the_lane_classifier_places_in_apply(
    engine: Engine,
) -> None:
    """The cohort's ids round-trip against the lane classifier reached through a DIFFERENT
    function: `review_job_ids`, the standing read the folder tree and the page use.

    An id list that is merely plausible is worth nothing to an audit — the whole reason the
    cohort is named rather than summed is that a sample has to be drawn from the population the
    number came from, so the population has to be the right one.
    """
    run_id = _run(engine)
    with engine.begin() as conn:
        # Both tables autoincrement from 1, so a lead's `posting_id` and `job_id` would otherwise
        # be the SAME integer and every id assertion below would hold against the wrong column.
        # Offsetting the job sequence is what makes the two distinguishable.
        conn.execute(insert(jobs).values(created_at=NOW))
        apply_ids = [_lead(conn, run_id=run_id, locations=APPLY_LOCATION)[0] for _ in range(3)]
        held_ids = [_lead(conn, run_id=run_id, locations=REVIEW_LOCATION)[0] for _ in range(2)]
    assert all(p.job_id != p.posting_id for p in _cohort(engine, run_id))

    with engine.connect() as conn:
        cohort = apply_lane_cohort(conn, run_ids={run_id})[run_id]
        held_jobs = review_job_ids(conn)
        by_posting = {
            row.posting_id: row.job_id for row in delivered_unapplied(conn, skipped=set())
        }

    assert {p.posting_id for p in cohort if p.lane == ""} == set(apply_ids)
    assert {p.posting_id for p in cohort if p.lane != ""} == set(held_ids)
    # The same split, asserted through the OTHER standing reader of the same lane decision.
    assert {by_posting[p.posting_id] for p in cohort if p.lane == ""}.isdisjoint(held_jobs)
    assert {by_posting[p.posting_id] for p in cohort if p.lane != ""} <= held_jobs
    assert all(p.job_id == by_posting[p.posting_id] for p in cohort)


def test_the_counts_the_drought_detector_reads_are_a_fold_of_this_cohort(engine: Engine) -> None:
    """The drought detector's two counts are the cohort, folded — same placeable set, same
    arrivals.

    Scope, stated because it bounds what this can catch: it pins the NUMBERS and the fold, not
    the structure. That `apply_lane_placements` keeps no lane call of its own is a property of
    the source, and a re-added second call would be equivalent today and pass here; what this
    rejects is a fold that counts the wrong side (inverting the lane test reads `(3, 1)`) or an
    exclusion that moves under one caller and not the other.
    """
    run_id = _run(engine)
    with engine.begin() as conn:
        for _ in range(2):
            _lead(conn, run_id=run_id, locations=APPLY_LOCATION)
        _lead(conn, run_id=run_id, locations=REVIEW_LOCATION)

    with engine.connect() as conn:
        cohort = apply_lane_cohort(conn, run_ids={run_id})[run_id]
        placed = apply_lane_placements(conn, run_ids={run_id})
        direct = [
            lane_decision(row).lane
            for row in delivered_unapplied(conn, skipped=set())
            if row.delivered_run_id == run_id
        ]

    assert placed[run_id] == (3, 2)
    assert (len(cohort), sum(1 for p in cohort if p.lane == "")) == placed[run_id]
    assert sorted(p.lane for p in cohort) == sorted(direct)


# ------------------------------------------------------------------------------ absent, not zero


def test_a_funnel_built_without_a_store_reports_the_cohort_unmeasured(engine: Engine) -> None:
    """`None` means NOT READ. A block of zeros would read as a run that placed nothing, which is
    a failed B8 gate rather than an unasked question — the same absent-not-zero direction
    `death_probe`, `form_questions` and `gate` already hold."""
    funnel = _funnel(engine, _run(engine), [])
    stripped = ApplyLaneCohort(placements=())

    assert funnel_to_dict(funnel)["apply_lane"] == {
        "instrumented": True,
        "placeable": 0,
        "in_apply": 0,
        "leads": [],
    }
    assert stripped.placeable == 0
    unread = funnel_to_dict(
        RunFunnel(**{**funnel.__dict__, "apply_lane": None})  # type: ignore[arg-type]
    )["apply_lane"]
    assert unread == {
        "instrumented": False,
        "placeable": None,
        "in_apply": None,
        "leads": [],
    }
    assert "NOT READ" in funnel_to_markdown(
        RunFunnel(**{**funnel.__dict__, "apply_lane": None})  # type: ignore[arg-type]
    )


# ----------------------------------------------------------------------- the volume diagnostic


def test_the_volume_alert_sees_a_shortfall_the_drought_detector_cannot(engine: Engine) -> None:
    """The reason this is a SECOND detector and not a parameter on the first.

    `check_apply_lane_drought` is a zero-detector: it fires only when a window of runs each
    delivered placeable leads and NOT ONE reached the apply lane. A run one lead under B8's bar
    is invisible to it, and it is right to stay quiet — nothing is broken. B8 is a bar, so the
    bar needs its own instrument.
    """
    run_id = _run(engine)
    under_bar = APPLY_LANE_VOLUME_BAR - 1
    with engine.begin() as conn:
        rendered = [
            _lead(conn, run_id=run_id, locations=APPLY_LOCATION)[0] for _ in range(under_bar)
        ]

    funnel = _funnel(engine, run_id, rendered)

    assert check_apply_lane_drought(engine, window=1, min_placeable=1) is None
    alert = check_apply_lane_volume(funnel.apply_lane)
    assert alert is not None
    assert f"{under_bar} lead(s) reached the blind-apply queue" in alert
    assert f"bar of {APPLY_LANE_VOLUME_BAR}" in alert


def test_the_volume_alert_abstains_at_the_bar_and_when_the_cohort_is_absent_or_empty() -> None:
    """Three abstains, and each one would be a false alarm without it: a run that MET the bar, a
    funnel that was never collected (silence, not zero), and a run that delivered nothing
    placeable — which is `check_delivery_drought`'s story and must not get a second diagnosis."""
    at_bar = ApplyLaneCohort(
        placements=tuple(
            LanePlacement(posting_id=i, job_id=i, lane="", review_reason=None)
            for i in range(APPLY_LANE_VOLUME_BAR)
        )
    )

    assert check_apply_lane_volume(at_bar) is None
    assert check_apply_lane_volume(None) is None
    assert check_apply_lane_volume(ApplyLaneCohort(placements=())) is None


def test_the_volume_alert_names_the_gates_holding_the_lane_back() -> None:
    """A bare count says the gate failed; the breakdown says which gate to look at. It is in the
    ALERT and not only the artifact because an unattended owner reads the run log first."""
    cohort = ApplyLaneCohort(
        placements=(
            LanePlacement(posting_id=1, job_id=1, lane="", review_reason=None),
            LanePlacement(
                posting_id=2, job_id=2, lane="_review", review_reason="no_requirements_found"
            ),
            LanePlacement(
                posting_id=3, job_id=3, lane="_review", review_reason="no_requirements_found"
            ),
            LanePlacement(
                posting_id=4, job_id=4, lane="_review", review_reason="form_question_hard_stop"
            ),
        )
    )

    alert = check_apply_lane_volume(cohort, bar=2)

    assert alert is not None
    assert "1 lead(s) reached" in alert
    assert "4 placeable, 3 held for review" in alert
    assert "no_requirements_found 2" in alert
    assert "form_question_hard_stop 1" in alert
