"""Execution changes must withdraw work, without earning a disposition or render failure."""
from __future__ import annotations

import json
import socket
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, event, insert, select, update

from boardwatch.core.clock import utcnow
from boardwatch.core.settings import load_settings
from boardwatch.pipeline import runner
from boardwatch.store import tables
from boardwatch.store.db import get_engine
from boardwatch.store.queue_state import mark_job_reported, mark_job_skipped
from tests.pipeline.test_lane_split_before_tailor import _fake_ok, _seed_review_posting
from tests.pipeline.test_ledger_advances_the_queue import _ready
from tests.pipeline.test_pipeline_projection_leads import _projected_env, _SelectRunner


@pytest.fixture()
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Refuse external processes/network and non-temporary stores BEFORE exercising old code."""
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))

    def deny(*args: object, **kwargs: object) -> None:
        raise AssertionError("unexpected external access")

    def local_store(dialect: object, record: object, args: list[object], kw: object) -> None:
        assert args and Path(str(args[0])).resolve().is_relative_to(Path(tempfile.gettempdir()).resolve())

    event.listen(Engine, "do_connect", local_store)
    monkeypatch.setattr(subprocess, "Popen", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr("boardwatch.reports.tailor._default_runner", _fake_ok)
    monkeypatch.setattr(runner, "default_compile_runner", lambda: _SelectRunner())
    try:
        yield tmp_path / "data"
    finally:
        event.remove(Engine, "do_connect", local_store)


def change(engine: Engine, pid: int, kind: str) -> None:
    with engine.begin() as conn:
        job = int(conn.execute(select(tables.postings.c.job_id).where(
            tables.postings.c.id == pid
        )).scalar_one())
        if kind == "skip":
            mark_job_skipped(conn, job_id=job, at=utcnow())
        elif kind == "report":
            mark_job_reported(conn, job_id=job, at=utcnow())
        elif kind == "applied_twin":
            copied = dict(conn.execute(select(tables.postings).where(
                tables.postings.c.id == pid)).mappings().one())
            copied.pop("id")
            copied.update(job_id=int(conn.execute(insert(tables.jobs).values(
                created_at=utcnow())).inserted_primary_key[0]), status="closed",
                provider_posting_id=f"closed-twin-{pid}")
            conn.execute(insert(tables.postings).values(**copied))
            conn.execute(insert(tables.applications).values(
                job_id=copied["job_id"], attempt_no=1, status="applied", created_at=utcnow(),
                updated_at=utcnow(), submitted_at=utcnow(),
            ))
        elif kind == "applied":
            conn.execute(insert(tables.applications).values(
                job_id=job, attempt_no=1, status="applied", created_at=utcnow(),
                updated_at=utcnow(), submitted_at=utcnow(),
            ))
        elif kind == "verdict":
            from boardwatch.eligibility.catalog import load_rules
            from boardwatch.eligibility.facts import Policy
            from boardwatch.eligibility.final_gate import record_gate_verdict
            from boardwatch.eligibility.oracle import OracleVerdict
            from boardwatch.eligibility.preflight import current_judge_inputs
            from boardwatch.store.queries import current_posting_versions
            settings = load_settings()
            facts, band = current_judge_inputs(conn, settings)
            cv = current_posting_versions(conn, [pid])[pid]
            record_gate_verdict(
                conn, posting_version_id=cv.posting_version_id, jd_text=cv.body_text,
                facts=facts, policy=Policy(families={}), catalog=load_rules(settings.config_dir),
                verdict=OracleVerdict(label="1", decision="ineligible", reason="work_auth",
                                      evidence=cv.body_text, confidence="high"),
                model=settings.gate.model, effort=settings.gate.effort, target_band=band,
            )
        elif kind == "manual":
            from boardwatch.store.queue_state import mark_job_manual
            mark_job_manual(conn, job_id=job, at=utcnow())
        elif kind == "peer":
            conn.execute(update(tables.postings).where(tables.postings.c.status == "closed")
                         .values(status="open"))
        elif kind == "closed":
            conn.execute(update(tables.postings).where(tables.postings.c.id == pid)
                         .values(status="closed"))
        elif kind == "destination":
            conn.execute(update(tables.postings).where(tables.postings.c.id == pid)
                         .values(url="https://example.test/replaced"))
        elif kind == "version":
            conn.execute(insert(tables.posting_versions).values(
                posting_id=pid, content_hash="changed", body_text="New frozen JD",
                captured_at=utcnow(), capture_reason="revised",
            ))
        else:
            raise AssertionError(kind)


@pytest.mark.parametrize("kind", ["skip", "report", "closed", "destination", "version", "applied", "verdict", "manual", "applied_twin", "unavailable", "peer"])
@pytest.mark.parametrize("top_n", [1, 2])
@pytest.mark.parametrize("project", [False, True])
def test_change_after_admission_never_delivers_or_consumes(
    isolated: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str, project: bool, top_n: int
) -> None:
    ids = _ready(isolated, 2)
    if project:
        _projected_env(isolated)
    engine = get_engine(isolated)
    if kind == "applied_twin":
        with engine.begin() as conn:
            for pid in ids:
                conn.execute(update(tables.postings).where(tables.postings.c.id == pid)
                             .values(url=f"https://www.amazon.jobs/en/jobs/{pid}"))
    if kind == "peer":
        from boardwatch.core.posting_identity import compute_identities
        from boardwatch.store.identity_queries import load_identity_inputs, write_identities
        with engine.begin() as conn:
            conn.execute(update(tables.postings).where(tables.postings.c.id.in_(ids))
                         .values(locations_json=["Chicago, IL"], content_hash="identical-body"))
            company = conn.execute(select(tables.postings.c.company_id).where(
                tables.postings.c.id == ids[0])).scalar_one()
            conn.execute(update(tables.postings).where(tables.postings.c.id == ids[1])
                         .values(company_id=company, status="closed"))
            for raw in load_identity_inputs(conn, ids, open_only=False):
                write_identities(conn, raw.posting_id, compute_identities(raw), now=utcnow())
        ids = ids[:1]
    original = runner._lead_lanes
    changed = False

    def lanes(*args: Any, **kwargs: Any) -> Any:
        nonlocal changed
        result = original(*args, **kwargs)
        if not changed:
            changed = True
            if kind == "unavailable":
                def unavailable(*a: Any, **kw: Any) -> None:
                    raise OSError("synthetic unavailable read")
                monkeypatch.setattr(runner, "_execution_inputs", unavailable, raising=False)
            else:
                for lead in args[2]:
                    change(engine, lead.posting_id, kind)
        return result

    monkeypatch.setattr(runner, "_lead_lanes", lanes)
    settings = load_settings(data_dir=isolated)
    summary = runner.run_pipeline(
        engine, settings, out_root=tmp_path / "apps", queue_root=tmp_path / "queue",
        resume_path=settings.config_dir / "resume.yaml", skip_scan=True, project=project,
        top_n=top_n,
    )
    assert not summary.tailored, "changed leads must never be delivered"
    assert summary.fatal is None, summary.fatal
    assert summary.tailor_failed == 0
    with engine.connect() as conn:
        assert conn.execute(select(tables.artifacts.c.id).where(
            tables.artifacts.c.run_id == summary.run_id,
            tables.artifacts.c.kind == "resume_tailored",
        )).all() == []
        assert conn.execute(select(tables.job_dispositions.c.disposition)).all() == []
    funnel = json.loads(summary.funnel.json_path.read_text())
    stages = {s["name"]: s for s in funnel["stages"]}
    stage = stages["projection" if project else "tailor"]
    assert any(d["reason"] == "execution_deferred" and d["count"] == min(top_n, len(ids)) for d in stage["drops"])


def test_projection_completion_does_not_bypass_second_barrier(
    isolated: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = _ready(isolated, 2)
    _projected_env(isolated)
    engine = get_engine(isolated)
    original = runner.project_for_posting

    def project(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        change(engine, int(args[3]), "skip")
        return result

    monkeypatch.setattr(runner, "project_for_posting", project)
    settings = load_settings(data_dir=isolated)
    summary = runner.run_pipeline(
        engine, settings, out_root=tmp_path / "apps", queue_root=tmp_path / "queue",
        resume_path=settings.config_dir / "resume.yaml", skip_scan=True, project=True,
    )
    assert summary.tailored == []
    assert summary.fatal is None, summary.fatal
    assert summary.tailor_failed == 0
    assert summary.funnel is not None
    stages = json.loads(summary.funnel.json_path.read_text())["stages"]
    assert all(s["reconciled"] is not False for s in stages)
    with engine.connect() as conn:
        assert conn.execute(select(tables.job_dispositions.c.disposition)).all() == []
        versions = select(tables.posting_versions.c.id).where(
            tables.posting_versions.c.posting_id.in_(ids))
        assert conn.execute(select(tables.artifacts.c.id).where(
            tables.artifacts.c.posting_version_id.in_(versions),
            tables.artifacts.c.kind == "resume_tailored",
        )).all() == []


def test_unchanged_apply_and_review_still_deliver(
    isolated: Path, tmp_path: Path
) -> None:
    apply = _ready(isolated, 1)[0]
    review = _seed_review_posting(isolated, slug="review-control")
    settings = load_settings(data_dir=isolated)
    summary = runner.run_pipeline(
        get_engine(isolated), settings, out_root=tmp_path / "apps",
        queue_root=tmp_path / "queue", resume_path=settings.config_dir / "resume.yaml",
        skip_scan=True,
    )
    assert summary.fatal is None, summary.fatal
    assert {p.posting_id for p in summary.tailored if p.pdf_built} == {apply}
    assert {p.posting_id for p in summary.tailored if p.pending_tailor} == {review}


def test_later_lead_is_withdrawn_while_first_build_runs(
    isolated: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from threading import Event, Thread
    ids = _ready(isolated, 2)
    engine = get_engine(isolated)
    started, changed = Event(), Event()
    original = runner.run_tailor
    built: list[int] = []

    def build(*args: Any, **kwargs: Any) -> Any:
        built.append(int(args[2]))
        started.set()
        assert changed.wait(5)
        return original(*args, **kwargs)

    def withdraw() -> None:
        assert started.wait(5)
        change(engine, next(pid for pid in ids if pid != built[0]), "skip")
        changed.set()

    monkeypatch.setattr(runner, "run_tailor", build)
    worker = Thread(target=withdraw)
    worker.start()
    settings = load_settings(data_dir=isolated)
    try:
        summary = runner.run_pipeline(
            engine, settings, out_root=tmp_path / "apps", queue_root=tmp_path / "queue",
            resume_path=settings.config_dir / "resume.yaml", skip_scan=True,
        )
    finally:
        worker.join(6)
    assert not worker.is_alive()
    assert {p.posting_id for p in summary.tailored} == {built[0]}
    assert len(built) == 1
    assert summary.fatal is None, summary.fatal
