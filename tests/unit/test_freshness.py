"""Freshness, not existence (P3 item 2).

`check_run_freshness` reads a real `runs` row and a real filesystem folder — it needs a schema
and a temp directory, so this is not the fully pure style of `test_run_funnel.py`/
`test_morning.py`, but it takes no pipeline dependency and asserts each of the three clauses
(`funnel_present`, terminal status + same-day, folder/artifact reconciliation) independently, so
a failure names WHICH one broke rather than only that the combined verdict flipped.

The folder/artifact reconciliation is deliberately scoped to run_id's own `resume_tailored`
rows (via each row's `uri` -> its parent lead folder), never to "every directory under
`day_dir`" — two `boardwatch run`s can legitimately share one calendar date (it is WHY every
artifact is suffixed by run_id), and `test_two_same_day_runs_each_reconcile_independently`
below is the regression test for the bug a day-scoped folder count would reintroduce: it would
count the OTHER run's lead folder too and report BOTH runs as unreconciled.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, update

from boardwatch.pipeline.freshness import check_run_freshness
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import RUN_FAILED, RUN_OK, RUN_RUNNING, insert_run
from boardwatch.store.tables import artifacts, jobs, runs

DATE = "2026-08-07"
SAME_DAY = datetime(2026, 8, 7, 9, 0, 0)
OTHER_DAY = datetime(2026, 8, 6, 23, 59, 0)


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path / "data")
    ensure_schema(eng)
    return eng


def _set_run(engine: Engine, run_id: int, **values: object) -> None:
    with engine.begin() as conn:
        conn.execute(update(runs).where(runs.c.id == run_id).values(**values))


def _day_dir(tmp_path: Path, date: str = DATE) -> Path:
    d = tmp_path / date
    d.mkdir(parents=True, exist_ok=True)
    return d


def _touch_funnel(day_dir: Path, run_id: int) -> None:
    (day_dir / f"funnel-{run_id}.md").write_text("stub\n", encoding="utf-8")


def _lead_folder(day_dir: Path, name: str) -> Path:
    folder = day_dir / name
    folder.mkdir()
    return folder


def _tailored_artifact_row(engine: Engine, run_id: int, day_dir: Path, folder: str) -> None:
    """One `resume_tailored` artifact row for `run_id`, whose `uri` names the `.typ` path under
    `day_dir/<folder>/` — the store side of the reconciliation. Does NOT create the folder;
    callers that want the row's folder to exist call `_lead_folder` themselves.
    """
    with engine.begin() as conn:
        job_id = int(
            conn.execute(insert(jobs).values(created_at=SAME_DAY)).inserted_primary_key[0]
        )
        conn.execute(
            insert(artifacts).values(
                job_id=job_id,
                kind="resume_tailored",
                uri=str(day_dir / folder / "resume.typ"),
                created_at=SAME_DAY,
                run_id=run_id,
            )
        )


def test_fresh_when_terminal_same_day_and_folders_reconcile(
    engine: Engine, tmp_path: Path
) -> None:
    run_id = insert_run(engine)
    _set_run(engine, run_id, started_at=SAME_DAY, finished_at=SAME_DAY, status=RUN_OK)
    day_dir = _day_dir(tmp_path)
    _touch_funnel(day_dir, run_id)
    _lead_folder(day_dir, "acme-1")
    _tailored_artifact_row(engine, run_id, day_dir, "acme-1")

    result = check_run_freshness(engine, run_id, day_dir)

    assert result.fresh is True
    assert result.reasons == ()
    assert result.folder_count == result.artifact_rows == 1


def test_two_same_day_runs_each_reconcile_independently(
    engine: Engine, tmp_path: Path
) -> None:
    """The exact gap fix-round-1 caught: two runs sharing one `<date>/` folder must each be
    checked against ONLY their own lead folder, not the other run's. A day-scoped folder count
    (`sum(1 for p in day_dir.iterdir() if p.is_dir())`) would see 2 folders for either run_id's
    1 artifact row and report BOTH as unreconciled — which is what the mutation below confirms.
    """
    run_id_1 = insert_run(engine)
    _set_run(engine, run_id_1, started_at=SAME_DAY, finished_at=SAME_DAY, status=RUN_OK)
    run_id_2 = insert_run(engine)
    _set_run(engine, run_id_2, started_at=SAME_DAY, finished_at=SAME_DAY, status=RUN_OK)

    day_dir = _day_dir(tmp_path)  # shared by both runs
    _touch_funnel(day_dir, run_id_1)
    _touch_funnel(day_dir, run_id_2)
    _lead_folder(day_dir, "acme-1")
    _tailored_artifact_row(engine, run_id_1, day_dir, "acme-1")
    _lead_folder(day_dir, "beta-2")
    _tailored_artifact_row(engine, run_id_2, day_dir, "beta-2")

    result_1 = check_run_freshness(engine, run_id_1, day_dir)
    result_2 = check_run_freshness(engine, run_id_2, day_dir)

    assert result_1.fresh is True, result_1.reasons
    assert result_1.folder_count == result_1.artifact_rows == 1
    assert result_2.fresh is True, result_2.reasons
    assert result_2.folder_count == result_2.artifact_rows == 1


def test_flagged_when_run_is_still_running(engine: Engine, tmp_path: Path) -> None:
    """`running` + no terminal status must never read as fresh — D-029/RUN_CONTRACT.md name
    that state as covering an in-flight run, a SIGKILL, and an unhandled crash alike."""
    run_id = insert_run(engine)
    _set_run(engine, run_id, started_at=SAME_DAY, status=RUN_RUNNING)
    day_dir = _day_dir(tmp_path)
    _touch_funnel(day_dir, run_id)

    result = check_run_freshness(engine, run_id, day_dir)

    assert result.fresh is False
    assert any("not terminal" in reason for reason in result.reasons)


def test_flagged_when_the_run_started_on_a_different_day(
    engine: Engine, tmp_path: Path
) -> None:
    """A terminal run whose `started_at`/`finished_at` do not fall on the folder's own date is
    a stale-day feed — the exact condition Gate P3 counts as 0 tolerated."""
    run_id = insert_run(engine)
    _set_run(engine, run_id, started_at=OTHER_DAY, finished_at=OTHER_DAY, status=RUN_OK)
    day_dir = _day_dir(tmp_path)  # named 2026-08-07, but the run started 2026-08-06
    _touch_funnel(day_dir, run_id)

    result = check_run_freshness(engine, run_id, day_dir)

    assert result.fresh is False
    assert any("not started AND finished on" in reason for reason in result.reasons)


def test_flagged_when_no_funnel_artifact_is_present(engine: Engine, tmp_path: Path) -> None:
    run_id = insert_run(engine)
    _set_run(engine, run_id, started_at=SAME_DAY, finished_at=SAME_DAY, status=RUN_OK)
    day_dir = _day_dir(tmp_path)  # no funnel file written

    result = check_run_freshness(engine, run_id, day_dir)

    assert result.fresh is False
    assert result.funnel_present is False
    assert any(f"no funnel-{run_id}.md" in reason for reason in result.reasons)


def test_flagged_when_lead_folders_do_not_reconcile_with_the_store(
    engine: Engine, tmp_path: Path
) -> None:
    """A folder deleted (or never written) after the store recorded the artifact must fail
    this — `count_tailored_artifacts` vs a real filesystem check of each row's own folder, not
    the pipeline's own in-memory count of what it wrote."""
    run_id = insert_run(engine)
    _set_run(engine, run_id, started_at=SAME_DAY, finished_at=SAME_DAY, status=RUN_OK)
    day_dir = _day_dir(tmp_path)
    _touch_funnel(day_dir, run_id)
    _tailored_artifact_row(engine, run_id, day_dir, "acme-1")  # store says 1 tailored row
    # ...but no lead folder was left on disk.

    result = check_run_freshness(engine, run_id, day_dir)

    assert result.fresh is False
    assert result.reconciles is False
    assert result.folder_count == 0
    assert result.artifact_rows == 1


def test_flagged_when_the_run_id_has_no_runs_row(engine: Engine, tmp_path: Path) -> None:
    """A funnel file naming a run_id the store has never heard of — e.g. a copied/forged
    folder — must not be treated as fresh just because the file exists."""
    day_dir = _day_dir(tmp_path)
    missing_run_id = 999_999
    _touch_funnel(day_dir, missing_run_id)

    result = check_run_freshness(engine, missing_run_id, day_dir)

    assert result.fresh is False
    assert result.status is None
    assert any("has no runs row" in reason for reason in result.reasons)


def test_flagged_when_the_day_dir_does_not_exist_on_disk(engine: Engine, tmp_path: Path) -> None:
    run_id = insert_run(engine)
    _set_run(engine, run_id, started_at=SAME_DAY, finished_at=SAME_DAY, status=RUN_OK)
    missing_dir = tmp_path / DATE  # never created

    result = check_run_freshness(engine, run_id, missing_dir)

    assert result.fresh is False
    assert result.funnel_present is False
    assert result.folder_count == 0


def test_a_failed_run_is_still_a_valid_terminal_status(engine: Engine, tmp_path: Path) -> None:
    """`failed` is terminal too — a run that finished with a fatal error still produced a real,
    dated funnel, and reporting it as stale would be as wrong as reporting `running` as fresh."""
    run_id = insert_run(engine)
    _set_run(engine, run_id, started_at=SAME_DAY, finished_at=SAME_DAY, status=RUN_FAILED)
    day_dir = _day_dir(tmp_path)
    _touch_funnel(day_dir, run_id)

    result = check_run_freshness(engine, run_id, day_dir)

    assert result.status == RUN_FAILED
    assert result.dated_to_folder is True
    assert result.fresh is True  # no leads, no folders, 0 == 0 reconciles
