"""Orchestration tests for boardwatch.reports.tailor.run_tailor (P7, Task 7).

run_tailor mirrors reports/notify.py's transaction discipline: it must never hold a DB
write lock across render/PDF I/O. It reads JD skills + resolves the current open version
under a short read connection, does all pure planning/rendering with no lock, and writes
every artifact + lineage edge in one closing engine.begin().

Fixtures are seeded directly through the store (no invented conftest fixtures), mirroring
tests/unit/test_reports_notify.py's _settings/_engine/_seed helpers.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert

from boardwatch.core.settings import Settings
from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.reports.tailor import NoCurrentVersionError, run_tailor
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import insert_run
from boardwatch.store.tables import (
    artifact_derivations,
    artifacts,
    companies,
    extractions,
    jobs,
    posting_versions,
    postings,
)
from boardwatch.tailor.load import scaffold_template

NOW = datetime(2026, 8, 2, 12, 0, 0)


def _settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data", config_dir=tmp_path / "cfg")


def _engine(settings: Settings) -> Engine:
    engine = get_engine(settings.data_dir)
    ensure_schema(engine)
    return engine


def _resume_yaml(tmp_path: Path) -> Path:
    path = tmp_path / "resume.yaml"
    path.write_text(scaffold_template(), encoding="utf-8")
    return path


def _seed(
    engine: Engine,
    settings: Settings,
    *,
    status: str = "open",
    with_version: bool = True,
    content_hash: str = "h1",
    body: str = "Python JavaScript backend services",
    skills: tuple[str, ...] = ("Python", "JavaScript"),
    slug: str = "acme",
) -> int:
    """Insert company+job+posting (+version+extraction); return posting_id."""
    with engine.begin() as conn:
        company_id = int(
            conn.execute(
                insert(companies).values(
                    name=slug, provider="greenhouse", slug=slug, source="user", watched=True
                )
            ).inserted_primary_key[0]
        )
        job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
        posting_id = int(
            conn.execute(
                insert(postings).values(
                    company_id=company_id, job_id=job_id, provider_posting_id=f"pp-{slug}",
                    title="Backend Engineer", normalized_title="backend engineer",
                    url=f"https://example.test/{slug}", locations_json=["Remote"],
                    remote_policy="remote", posted_at=NOW, first_seen_at=NOW, last_seen_at=NOW,
                    status=status, consecutive_missing=0, content_hash=content_hash, body_text=body,
                )
            ).inserted_primary_key[0]
        )
        if with_version:
            conn.execute(
                insert(posting_versions).values(
                    posting_id=posting_id, content_hash=content_hash, body_text=body,
                    captured_at=NOW, capture_reason="new",
                )
            )
            conn.execute(
                insert(extractions).values(
                    posting_id=posting_id, content_hash=content_hash, kind="taxonomy",
                    engine_version=load_taxonomy(settings.config_dir).version,
                    json={"skills": list(skills)}, created_at=NOW,
                )
            )
    return posting_id


def _runner_ok(typ: Path, pdf: Path) -> bool:
    pdf.write_bytes(b"%PDF")
    return True


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    out = tmp_path / "out"
    res = run_tailor(
        engine, settings, pid, resume_path=_resume_yaml(tmp_path), out_dir=out,
        dry_run=True, typst_runner=_runner_ok,
    )
    assert res.dry_run is True
    assert res.tailored_artifact_id is None
    assert res.pdf_path is None
    assert res.source  # emitted in-memory, never written
    assert not out.exists() or not list(out.glob("*"))
    with engine.connect() as conn:
        assert conn.execute(artifacts.select()).first() is None


def test_real_run_records_artifacts_and_edge(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    out = tmp_path / "out"
    res = run_tailor(
        engine, settings, pid, resume_path=_resume_yaml(tmp_path), out_dir=out,
        typst_runner=_runner_ok,
    )
    assert res.tailored_artifact_id is not None
    assert res.pdf_path is not None and res.pdf_path.exists()
    assert (out / f"tailored-{pid}.typ").exists()
    with engine.connect() as conn:
        rows = conn.execute(artifacts.select()).fetchall()
        kinds = {r.kind for r in rows}
        assert kinds == {"resume_master", "resume_tailored"}
        tailored = next(r for r in rows if r.kind == "resume_tailored")
        assert tailored.uri.endswith(f"tailored-{pid}.typ")  # ref is the deterministic .typ
        assert tailored.media_type == "text/x-typst"
        assert tailored.meta_json["master_content_hash"]
        assert tailored.meta_json["equivalences_version"]
        assert "bullets" in tailored.meta_json
        assert tailored.meta_json["pdf_uri"] and tailored.meta_json["pdf_uri"].endswith(".pdf")
        edge = conn.execute(artifact_derivations.select()).first()
        assert edge is not None
        assert edge.relation == "tailored_from"
        master = next(r for r in rows if r.kind == "resume_master")
        assert edge.parent_artifact_id == master.id
        assert edge.artifact_id == tailored.id
    assert res.bullets and all("action" in b for b in res.bullets)


def test_master_is_reselected_not_duplicated(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    resume = _resume_yaml(tmp_path)
    run_tailor(engine, settings, pid, resume_path=resume, out_dir=tmp_path / "o1",
               typst_runner=_runner_ok)
    run_tailor(engine, settings, pid, resume_path=resume, out_dir=tmp_path / "o2",
               typst_runner=_runner_ok)
    with engine.connect() as conn:
        rows = conn.execute(artifacts.select()).fetchall()
    masters = [r for r in rows if r.kind == "resume_master"]
    tailored = [r for r in rows if r.kind == "resume_tailored"]
    assert len(masters) == 1
    assert len(tailored) == 2


def test_missing_current_version_fails_closed(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings, with_version=False)
    with pytest.raises(NoCurrentVersionError):
        run_tailor(engine, settings, pid, resume_path=_resume_yaml(tmp_path),
                   out_dir=tmp_path / "out", typst_runner=_runner_ok)


def test_non_open_posting_fails_closed(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings, status="closed")
    with pytest.raises(NoCurrentVersionError):
        run_tailor(engine, settings, pid, resume_path=_resume_yaml(tmp_path),
                   out_dir=tmp_path / "out", typst_runner=_runner_ok)


def test_no_write_lock_held_across_render(tmp_path: Path) -> None:
    """The typst runner itself opens a write transaction. If run_tailor held any write
    lock across to_pdf, this second writer would block until busy_timeout and fail. It
    succeeds because rendering happens with no lock held — the whole point of Task 7."""
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)

    def runner(typ: Path, pdf: Path) -> bool:
        insert_run(engine)  # independent engine.begin(): would deadlock under a held lock
        pdf.write_bytes(b"%PDF")
        return True

    res = run_tailor(engine, settings, pid, resume_path=_resume_yaml(tmp_path),
                     out_dir=tmp_path / "out", typst_runner=runner)
    assert res.tailored_artifact_id is not None
