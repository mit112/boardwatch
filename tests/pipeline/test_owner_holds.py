"""Owner holds survive invocations and cannot be bypassed by a build boundary."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import insert, select, update

from boardwatch.core.settings import load_settings
from boardwatch.pipeline import runner
from boardwatch.store import tables
from boardwatch.store.db import get_engine
from tests.pipeline.test_execution_barrier import isolated as isolated
from tests.pipeline.test_ledger_advances_the_queue import _ready
from tests.pipeline.test_pipeline_projection_leads import _projected_env


def _hold(engine: Any, pid: int, *, released: bool = False) -> int:
    with engine.begin() as conn:
        job = conn.execute(select(tables.postings.c.job_id).where(tables.postings.c.id == pid)).scalar_one()
        value = json.dumps({"version": 1, "reason": "Owner decision pending", "held_at": "2026-11-08T12:00:00", "released_at": "2026-11-08T13:00:00" if released else None})
        conn.execute(insert(tables.app_state).values(key=f"queue.held.{job}", value=value)
                     .prefix_with("OR REPLACE"))
    return int(job)


def test_hold_refills_slate_without_consuming_job_and_release_restores_admission(
    isolated: Path, tmp_path: Path,
) -> None:
    held, control = _ready(isolated, 2)
    engine = get_engine(isolated)
    job = _hold(engine, held)
    settings = load_settings(data_dir=isolated)
    args = dict(out_root=tmp_path / "apps", queue_root=tmp_path / "queue",
                resume_path=settings.config_dir / "resume.yaml", skip_scan=True, top_n=1)
    first = runner.run_pipeline(engine, settings, **args)
    assert first.fatal is None, first.fatal
    assert {p.posting_id for p in first.tailored} == {control}
    with engine.connect() as conn:
        assert conn.execute(select(tables.job_dispositions).where(tables.job_dispositions.c.job_id == job)).all() == []
    _hold(engine, held, released=True)
    second = runner.run_pipeline(engine, settings, **args)
    assert second.fatal is None, second.fatal
    assert {p.posting_id for p in second.tailored} == {held}


@pytest.mark.parametrize("boundary", ["admission", "tailor", "projection_start", "tailor_start"])
def test_hold_added_after_selection_defers_without_artifact_or_disposition(
    isolated: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boundary: str,
) -> None:
    pid = _ready(isolated, 1)[0]
    _projected_env(isolated)
    engine = get_engine(isolated)
    name = ("_lead_lanes" if boundary == "admission" else
            "run_tailor" if boundary == "tailor_start" else "project_for_posting")
    original = getattr(runner, name)

    def intervene(*args: Any, **kwargs: Any) -> Any:
        if boundary in ("projection_start", "tailor_start"):
            _hold(engine, pid)
            return original(*args, **kwargs)
        result = original(*args, **kwargs)
        _hold(engine, pid)
        return result

    monkeypatch.setattr(runner, name, intervene)
    settings = load_settings(data_dir=isolated)
    summary = runner.run_pipeline(engine, settings, out_root=tmp_path / "apps",
                                  queue_root=tmp_path / "queue", project=True,
                                  resume_path=settings.config_dir / "resume.yaml", skip_scan=True)
    assert not summary.tailored
    assert summary.fatal is None, summary.fatal
    assert summary.tailor_failed == 0
    assert json.loads(summary.funnel.json_path.read_text())["reconciles"] is True
    with engine.connect() as conn:
        assert conn.execute(select(tables.job_dispositions)).all() == []
        assert conn.execute(select(tables.artifacts).where(tables.artifacts.c.kind == "resume_tailored")).all() == []


def test_active_hold_survives_changed_posting_evidence(isolated: Path, tmp_path: Path) -> None:
    pid = _ready(isolated, 1)[0]
    engine = get_engine(isolated)
    _hold(engine, pid)
    with engine.begin() as conn:
        conn.execute(update(tables.postings).where(tables.postings.c.id == pid).values(title="Backend Software Engineer"))
    settings = load_settings(data_dir=isolated)
    result = runner.run_pipeline(engine, settings, out_root=tmp_path / "apps",
                                 queue_root=tmp_path / "queue", skip_scan=True,
                                 resume_path=settings.config_dir / "resume.yaml")
    assert not result.tailored
    assert result.fatal is None, result.fatal


def test_direct_projection_and_tailoring_refuse_owner_held_job(isolated: Path, tmp_path: Path) -> None:
    from boardwatch.extract.taxonomy import load_taxonomy
    from boardwatch.projection.posting import posting_context
    from boardwatch.store.owner_holds import OwnerHoldError

    pid = _ready(isolated, 1)[0]
    engine = get_engine(isolated)
    _hold(engine, pid)
    settings = load_settings(data_dir=isolated)
    with pytest.raises(OwnerHoldError):
        posting_context(engine, settings, pid, taxonomy=load_taxonomy(settings.config_dir))
    with pytest.raises(OwnerHoldError):
        runner.run_tailor(engine, settings, pid, resume_path=settings.config_dir / "resume.yaml",
                          out_dir=tmp_path / "apps")
    assert not (tmp_path / "apps").exists()


def test_inspection_flags_cannot_admit_owner_held_job(isolated: Path) -> None:
    from boardwatch.cli.top_cmd import rank_open_postings

    pid = _ready(isolated, 1)[0]
    engine = get_engine(isolated)
    _hold(engine, pid)
    ranked = rank_open_postings(engine, load_settings(data_dir=isolated), include_handled=True)
    assert not ranked.visible
    assert ranked.hidden_handled == 1
