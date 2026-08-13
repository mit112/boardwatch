"""jd_skills_for: Task 16's extraction of the JD-skills lookup that used to be inline in
`_plan_tier_a` (reports/tailor.py:341-356) and is duplicated across cli/top_cmd.py (x2),
cli/show_cmd.py, and reports/notify.py.

Pins the behaviour the inline query had before extraction, including the distinction the
call site's coalesce depends on: a cache miss (no extraction row) reads as `None`, never
conflated with an extraction row that genuinely matched zero skills.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert

from boardwatch.core.settings import Settings
from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.reports.tailor import jd_skills_for, run_tailor
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.tables import companies, extractions, jobs, posting_versions, postings
from boardwatch.tailor.load import scaffold_template
from boardwatch.tailor.render.outcome import CompileOutcome, CompileReason

NOW = datetime(2026, 8, 2, 12, 0, 0)


def _settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data", config_dir=tmp_path / "cfg")


def _engine(settings: Settings) -> Engine:
    engine = get_engine(settings.data_dir)
    ensure_schema(engine)
    return engine


def _seed_posting(
    engine: Engine,
    *,
    content_hash: str = "h1",
    body: str = "Python JavaScript backend services",
    slug: str = "acme",
) -> int:
    """company + job + posting + posting_version — no extraction row. Each test inserts
    (or deliberately omits) its own extraction row, so the seam under test controls it."""
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
                    status="open", consecutive_missing=0, content_hash=content_hash, body_text=body,
                )
            ).inserted_primary_key[0]
        )
        conn.execute(
            insert(posting_versions).values(
                posting_id=posting_id, content_hash=content_hash, body_text=body,
                captured_at=NOW, capture_reason="new",
            )
        )
    return posting_id


def _insert_extraction(
    engine: Engine, posting_id: int, *, content_hash: str, engine_version: str, skills: list[str]
) -> None:
    with engine.begin() as conn:
        conn.execute(
            insert(extractions).values(
                posting_id=posting_id, content_hash=content_hash, kind="taxonomy",
                engine_version=engine_version, json={"skills": skills}, created_at=NOW,
            )
        )


def test_seeded_extraction_row_returns_its_skills(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = _engine(settings)
    taxonomy = load_taxonomy(settings.config_dir)
    posting_id = _seed_posting(engine)
    _insert_extraction(
        engine, posting_id, content_hash="h1", engine_version=taxonomy.version,
        skills=["Python", "Go"],
    )
    with engine.connect() as conn:
        result = jd_skills_for(conn, posting_id, taxonomy=taxonomy)
    assert result == {"Python", "Go"}


def test_no_extraction_row_returns_none_not_empty_set(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = _engine(settings)
    taxonomy = load_taxonomy(settings.config_dir)
    posting_id = _seed_posting(engine)  # no extraction row inserted at all
    with engine.connect() as conn:
        result = jd_skills_for(conn, posting_id, taxonomy=taxonomy)
    assert result is None


def test_row_with_empty_skills_list_is_a_hit_not_a_miss(tmp_path: Path) -> None:
    """The distinction the call-site coalesce depends on: a genuinely skill-free JD is a
    real row, read back as `set()` — never `None`."""
    settings = _settings(tmp_path)
    engine = _engine(settings)
    taxonomy = load_taxonomy(settings.config_dir)
    posting_id = _seed_posting(engine)
    _insert_extraction(
        engine, posting_id, content_hash="h1", engine_version=taxonomy.version, skills=[],
    )
    with engine.connect() as conn:
        result = jd_skills_for(conn, posting_id, taxonomy=taxonomy)
    assert result is not None
    assert result == set()


def test_row_at_a_different_engine_version_is_a_miss(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = _engine(settings)
    taxonomy = load_taxonomy(settings.config_dir)
    posting_id = _seed_posting(engine)
    _insert_extraction(
        engine, posting_id, content_hash="h1", engine_version="some-other-version",
        skills=["Python"],
    )
    with engine.connect() as conn:
        result = jd_skills_for(conn, posting_id, taxonomy=taxonomy)
    assert result is None


def _resume_yaml(tmp_path: Path) -> Path:
    path = tmp_path / "resume.yaml"
    path.write_text(scaffold_template(), encoding="utf-8")
    return path


def _runner_ok(typ: Path, pdf: Path) -> CompileOutcome:
    pdf.write_bytes(b"%PDF")
    return CompileOutcome(CompileReason.OK, pdf, 1, "ok")


def test_run_tailor_coalesces_a_jd_skills_for_miss_to_empty_skills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The compatibility guarantee: `_plan_tier_a` coalesces a `jd_skills_for` miss
    (`None`) to an empty set, exactly as the pre-extraction inline query did — never a
    raised error, never a bare `None` reaching `build_plan`/`_audit_rows`.

    `run_preflight` backfills every OPEN posting's extraction row before `_plan_tier_a`
    ever calls `jd_skills_for`, so a real miss cannot survive to that point for any
    posting `run_tailor` can reach — this is verified separately by
    `test_no_extraction_row_returns_none_not_empty_set` above, which shows `jd_skills_for`
    itself still reports the miss honestly. What is under test here is `_plan_tier_a`'s
    own coalesce line, isolated with a monkeypatched miss so the assertion is not at the
    mercy of whether preflight happens to backfill in this particular test run.
    """

    def _miss(conn: object, posting_id: int, *, taxonomy: object) -> None:
        return None

    monkeypatch.setattr("boardwatch.reports.tailor.jd_skills_for", _miss)
    settings = _settings(tmp_path)
    engine = _engine(settings)
    posting_id = _seed_posting(engine)
    _insert_extraction(
        engine, posting_id, content_hash="h1",
        engine_version=load_taxonomy(settings.config_dir).version, skills=["Python"],
    )
    res = run_tailor(
        engine, settings, posting_id, resume_path=_resume_yaml(tmp_path),
        out_dir=tmp_path / "out", typst_runner=_runner_ok,
    )
    assert res.jd_skills == []
    assert res.tailored_artifact_id is not None
