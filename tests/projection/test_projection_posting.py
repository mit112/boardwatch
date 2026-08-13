"""The posting-context seam (Task 17): `(jd_skills, page_budget)` for one posting, plus
`posting_version_id` — the single route projection uses instead of `plan_tier_a`, which
requires a `resume_path` and builds a whole Tier A plan projection has no use for.

Seeded directly through the store, mirroring tests/unit/test_reports_tailor.py's
`_settings`/`_engine`/`_seed` helpers — this module has nothing to do with the bundle, so
the `materialised_bundle`/`context_over` fixtures in tests/projection/conftest.py do not
apply here.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert

from boardwatch.core.settings import Settings
from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.projection.errors import ProjectionError, ProjectionIssue
from boardwatch.projection.posting import PostingContext, posting_context
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import save_profile
from boardwatch.store.tables import companies, extractions, jobs, posting_versions, postings

NOW = datetime(2026, 8, 2, 12, 0, 0)


def _settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data", config_dir=tmp_path / "cfg")


def _engine(settings: Settings) -> Engine:
    engine = get_engine(settings.data_dir)
    ensure_schema(engine)
    return engine


def _seed(
    engine: Engine,
    settings: Settings,
    *,
    status: str = "open",
    with_version: bool = True,
    with_extraction: bool = True,
    content_hash: str = "h1",
    body: str = "Python JavaScript backend services",
    skills: tuple[str, ...] = ("Python", "JavaScript"),
    slug: str = "acme",
) -> int:
    """Insert company+job+posting(+version+extraction); return posting_id. Mirrors
    tests/unit/test_reports_tailor.py's `_seed`, with independent control over whether
    the version and extraction rows exist, since this seam's own guards depend on both."""
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
            if with_extraction:
                conn.execute(
                    insert(extractions).values(
                        posting_id=posting_id, content_hash=content_hash, kind="taxonomy",
                        engine_version=load_taxonomy(settings.config_dir).version,
                        json={"skills": list(skills)}, created_at=NOW,
                    )
                )
    return posting_id


# -- happy path -----------------------------------------------------------------------


def test_jd_skills_and_version_come_back_correctly(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = _engine(settings)
    posting_id = _seed(engine, settings, skills=("Python", "Go"))
    ctx = posting_context(engine, settings, posting_id)
    assert isinstance(ctx, PostingContext)
    assert ctx.posting_id == posting_id
    assert ctx.jd_skills == frozenset({"Python", "Go"})


def test_an_extraction_row_with_no_skills_is_not_a_miss(tmp_path: Path) -> None:
    """The None-vs-empty distinction Task 16 named must survive through this seam: a JD
    that genuinely matched nothing still resolves, with an empty jd_skills — it must not
    be treated the same as a missing extraction row (NO_JD_EXTRACTION)."""
    settings = _settings(tmp_path)
    engine = _engine(settings)
    posting_id = _seed(engine, settings, skills=())
    ctx = posting_context(engine, settings, posting_id)
    assert ctx.jd_skills == frozenset()


# -- page budget ------------------------------------------------------------------------


def test_budget_floors_a_stored_zero_to_one(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = _engine(settings)
    with engine.begin() as conn:
        save_profile(
            conn, text="t", target_titles=[], exclude_titles=[], locations=[],
            remote_only=False, skills=[], taxonomy_version="v1", resume_max_pages=0,
        )
    posting_id = _seed(engine, settings)
    ctx = posting_context(engine, settings, posting_id)
    assert ctx.page_budget == 1


def test_budget_honors_a_stored_value_above_one(tmp_path: Path) -> None:
    """Mirrors tests/unit/test_run_tailor_gate.py:262 — a saved resume_max_pages=2 must
    actually be read, not floored to 1."""
    settings = _settings(tmp_path)
    engine = _engine(settings)
    with engine.begin() as conn:
        save_profile(
            conn, text="t", target_titles=[], exclude_titles=[], locations=[],
            remote_only=False, skills=[], taxonomy_version="v1", resume_max_pages=2,
        )
    posting_id = _seed(engine, settings)
    ctx = posting_context(engine, settings, posting_id)
    assert ctx.page_budget == 2


def test_budget_defaults_to_one_with_no_profile_row(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = _engine(settings)
    posting_id = _seed(engine, settings)  # no save_profile call at all
    ctx = posting_context(engine, settings, posting_id)
    assert ctx.page_budget == 1


# -- refusals -----------------------------------------------------------------------


def test_a_closed_posting_refuses(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = _engine(settings)
    posting_id = _seed(engine, settings, status="closed")
    try:
        posting_context(engine, settings, posting_id)
    except ProjectionError as exc:
        assert exc.violation.issue is ProjectionIssue.POSTING_NOT_OPEN
    else:
        raise AssertionError("expected ProjectionError(POSTING_NOT_OPEN)")


def test_a_posting_with_no_current_version_refuses(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = _engine(settings)
    posting_id = _seed(engine, settings, with_version=False)
    try:
        posting_context(engine, settings, posting_id)
    except ProjectionError as exc:
        assert exc.violation.issue is ProjectionIssue.POSTING_NO_CURRENT_VERSION
    else:
        raise AssertionError("expected ProjectionError(POSTING_NO_CURRENT_VERSION)")


def test_a_missing_extraction_raises_no_jd_extraction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`run_preflight` backfills every OPEN posting's extraction row before this seam's
    own `jd_skills_for` lookup runs, so an open posting can never genuinely reach a miss
    in practice — preflight itself is the drain for exactly this bucket. To exercise the
    guard this seam owns for whatever preflight does not catch, preflight is stubbed to a
    no-op here so the extraction row this test omits stays missing."""
    monkeypatch.setattr("boardwatch.projection.posting.run_preflight", lambda engine, settings: None)
    settings = _settings(tmp_path)
    engine = _engine(settings)
    posting_id = _seed(engine, settings, with_extraction=False)
    try:
        posting_context(engine, settings, posting_id)
    except ProjectionError as exc:
        assert exc.violation.issue is ProjectionIssue.NO_JD_EXTRACTION
    else:
        raise AssertionError("expected ProjectionError(NO_JD_EXTRACTION)")
