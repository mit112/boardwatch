"""`run_tailor` validating and recording a PROJECTED résumé's lineage (P5a task 6).

A projected master's provenance has to be *detected*, not merely inspectable: the pipeline hands
`run_tailor` a file plus the `ResumeSourceLineage` the projection recorded, and this module pins
that (a) a lineage that does not describe the handed-over file refuses the lead before anything is
rendered, and (b) a lineage that does describe it lands on the `resume_tailored` row, in the same
transaction as the artifact.

Fixtures are seeded directly through the store, mirroring tests/unit/test_reports_tailor.py's
_settings/_engine/_seed helpers rather than inventing a conftest fixture.
"""

from __future__ import annotations

import dataclasses
import hashlib
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, select

from boardwatch.core.lineage import ResumeSourceLineage
from boardwatch.core.settings import Settings
from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.reports.tailor import ResumeLineageMismatch, run_tailor
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.tables import (
    artifacts,
    companies,
    extractions,
    jobs,
    posting_versions,
    postings,
)
from boardwatch.tailor.load import load_resume, scaffold_template
from boardwatch.tailor.render.outcome import CompileOutcome, CompileReason

NOW = datetime(2026, 8, 17, 12, 0, 0)


def _settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data", config_dir=tmp_path / "cfg")


def _engine(settings: Settings) -> Engine:
    engine = get_engine(settings.data_dir)
    ensure_schema(engine)
    return engine


def _seed(engine: Engine, settings: Settings, *, slug: str = "acme") -> int:
    """Insert company+job+posting+version+extraction; return posting_id."""
    body = "Python JavaScript backend services"
    content_hash = "h1"
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
                    status="open", consecutive_missing=0, content_hash=content_hash,
                    body_text=body,
                )
            ).inserted_primary_key[0]
        )
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
                json={"skills": ["Python", "JavaScript"]}, created_at=NOW,
            )
        )
    return posting_id


def _version_id(engine: Engine, posting_id: int) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                select(posting_versions.c.id).where(posting_versions.c.posting_id == posting_id)
            ).scalar_one()
        )


class _Runner:
    """A compile runner that records every invocation, so "refused before rendering" is asserted
    on an observed absence of compiles rather than inferred from the exception alone."""

    def __init__(self) -> None:
        self.calls: list[Path] = []

    def __call__(self, typ: Path, pdf: Path) -> CompileOutcome:
        self.calls.append(typ)
        pdf.write_bytes(b"%PDF")
        return CompileOutcome(CompileReason.OK, pdf, 1, "ok")


def _projected(tmp_path: Path) -> Path:
    """Stands in for `resume.projected.yaml`: bytes published by the projection, which the
    tailor is handed rather than authoring."""
    path = tmp_path / "resume.projected.yaml"
    path.write_text(scaffold_template(), encoding="utf-8")
    return path


def _lineage(path: Path, posting_version_id: int) -> ResumeSourceLineage:
    """The lineage the projection would have recorded for `path`. Both hashes are computed the
    way `boardwatch.projection.run` computes them — sha256 over the published bytes, and sha256
    over `model_dump_json()` of the model those bytes parse to."""
    return ResumeSourceLineage(
        kind="projection",
        bundle_revision="21",
        bundle_digest="b" * 64,
        projection_digest="p" * 64,
        posting_version_id=posting_version_id,
        as_of="2026-08-17T12:00:00",
        scorer_id="mean_per_bullet",
        taxonomy_version="tax-1",
        equivalence_version="eq-1",
        persona_registry_version="pr-1",
        resume_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        resume_model_sha256=hashlib.sha256(
            load_resume(path).model_dump_json().encode("utf-8")
        ).hexdigest(),
        manifest_schema=1,
    )


def test_lineage_lands_on_the_tailored_row(tmp_path: Path) -> None:
    """Not on resume_master: that node is content-addressed and reused, and its metadata is
    written only on first creation, so lineage there would be attributed to whichever run
    happened to create the master first."""
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    projected = _projected(tmp_path)
    lineage = _lineage(projected, _version_id(engine, pid))

    res = run_tailor(
        engine, settings, pid, resume_path=projected, out_dir=tmp_path / "out",
        typst_runner=_Runner(), source_lineage=lineage,
    )

    assert res.tailored_artifact_id is not None
    with engine.connect() as conn:
        rows = conn.execute(artifacts.select()).fetchall()
    tailored = next(r for r in rows if r.kind == "resume_tailored")
    meta = tailored.meta_json
    assert meta["projection_bundle_revision"] == "21"
    assert meta["projection_kind"] == "projection"
    assert meta["projection_posting_version_id"] == lineage.posting_version_id
    assert meta["projection_resume_sha256"] == lineage.resume_sha256
    # Every field, not a sample: a lineage that dropped a transformation version on the way to
    # the row would still satisfy the four assertions above.
    assert lineage.as_meta().items() <= meta.items()
    # The pre-existing tailoring keys survive the merge.
    assert meta["master_content_hash"] and meta["posting_version_id"] == lineage.posting_version_id


def test_lineage_is_not_written_to_the_master_row(tmp_path: Path) -> None:
    """The master row is shared across runs and postings; a projection_* key there would claim
    one posting's projection describes every later tailoring of the same master."""
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    projected = _projected(tmp_path)

    run_tailor(
        engine, settings, pid, resume_path=projected, out_dir=tmp_path / "out",
        typst_runner=_Runner(), source_lineage=_lineage(projected, _version_id(engine, pid)),
    )

    with engine.connect() as conn:
        rows = conn.execute(artifacts.select()).fetchall()
    master = next(r for r in rows if r.kind == "resume_master")
    assert [k for k in master.meta_json if k.startswith("projection_")] == []


def test_a_hash_mismatch_refuses_before_rendering(tmp_path: Path) -> None:
    """The check must be able to fail. A lineage whose hash does not match the file handed over
    is exactly the manifest-B-with-resume-A case."""
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    projected = _projected(tmp_path)
    wrong = dataclasses.replace(
        _lineage(projected, _version_id(engine, pid)), resume_sha256="0" * 64
    )
    runner = _Runner()

    with pytest.raises(ResumeLineageMismatch):
        run_tailor(
            engine, settings, pid, resume_path=projected, out_dir=tmp_path / "out",
            typst_runner=runner, source_lineage=wrong,
        )

    assert runner.calls == []  # refused before any render
    with engine.connect() as conn:
        assert conn.execute(artifacts.select()).first() is None


def test_a_swapped_file_is_refused_even_though_it_loads(tmp_path: Path) -> None:
    """The realistic shape of the byte check: the lineage is honest, the file underneath it moved.
    A perfectly valid résumé that is not the projected one must still be refused."""
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    projected = _projected(tmp_path)
    lineage = _lineage(projected, _version_id(engine, pid))
    projected.write_text(
        scaffold_template().replace("Ada Lovelace", "Grace Hopper"), encoding="utf-8"
    )
    assert load_resume(projected).header[0] == "Grace Hopper"  # still a loadable master

    with pytest.raises(ResumeLineageMismatch):
        run_tailor(
            engine, settings, pid, resume_path=projected, out_dir=tmp_path / "out",
            typst_runner=_Runner(), source_lineage=lineage,
        )


def test_a_posting_version_change_refuses(tmp_path: Path) -> None:
    """Selection ran against version A; if tailoring resolves version B the lead is refused."""
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    projected = _projected(tmp_path)
    lineage = _lineage(projected, _version_id(engine, pid))
    stale = dataclasses.replace(lineage, posting_version_id=lineage.posting_version_id - 1)
    runner = _Runner()

    with pytest.raises(ResumeLineageMismatch):
        run_tailor(
            engine, settings, pid, resume_path=projected, out_dir=tmp_path / "out",
            typst_runner=runner, source_lineage=stale,
        )

    assert runner.calls == []
    with engine.connect() as conn:
        assert conn.execute(artifacts.select()).first() is None


def test_a_model_hash_mismatch_refuses(tmp_path: Path) -> None:
    """The second hash is not redundant with the first: matching bytes that parse to a different
    model than the projection recorded means the two ends disagree about the document, which is a
    loader/schema divergence, not a swapped file."""
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    projected = _projected(tmp_path)
    wrong = dataclasses.replace(
        _lineage(projected, _version_id(engine, pid)), resume_model_sha256="1" * 64
    )

    with pytest.raises(ResumeLineageMismatch):
        run_tailor(
            engine, settings, pid, resume_path=projected, out_dir=tmp_path / "out",
            typst_runner=_Runner(), source_lineage=wrong,
        )

    with engine.connect() as conn:
        assert conn.execute(artifacts.select()).first() is None


def test_existing_callers_are_unaffected(tmp_path: Path) -> None:
    """Every current caller passes no lineage and must behave exactly as before: an authored
    résumé still ships a PDF, and the tailored row carries no projection_* keys to be
    misread as provenance."""
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    authored = tmp_path / "resume.yaml"
    authored.write_text(scaffold_template(), encoding="utf-8")

    before = run_tailor(
        engine, settings, pid, resume_path=authored, out_dir=tmp_path / "out",
        typst_runner=_Runner(),
    )

    assert before.pdf_path is not None
    with engine.connect() as conn:
        rows = conn.execute(artifacts.select()).fetchall()
    tailored = next(r for r in rows if r.kind == "resume_tailored")
    assert [k for k in tailored.meta_json if k.startswith("projection_")] == []
