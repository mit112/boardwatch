"""Orchestration tests for Tier B lane wiring in boardwatch.reports.tailor.run_tailor.

Tier B is opt-in: passing `client` (+ `cache`) runs the rewrite lane after Tier A and,
unless this is a dry run, emits a SECOND artifact (`resume_tailored_llm`) and a
`rewritten_from` lineage edge back to the Tier A artifact — in the same closing
engine.begin() as the Tier A write, per reports/tailor.py's transaction discipline.

Fixtures are seeded directly through the store (no invented conftest fixtures), mirroring
tests/unit/test_reports_tailor.py's _settings/_engine/_seed/_resume_yaml helpers.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine, insert

from boardwatch.core.settings import Settings
from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.llm.cache import ResponseCache
from boardwatch.reports.tailor import run_tailor
from boardwatch.store.artifacts import get_derivations
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.tables import (
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
    content_hash: str = "h1",
    body: str = "Python JavaScript backend services",
    skills: tuple[str, ...] = ("Python", "JavaScript"),
    slug: str = "acme",
) -> int:
    """Insert company+job+posting+version+extraction; return posting_id."""
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


class ScriptedClient:
    """Returns canned completions in order; never raises (a real client can, but the
    lane's own containment boundary is exercised by boardwatch.tailor.rewrite tests)."""

    def __init__(self, bodies: list[str]) -> None:
        self.bodies = list(bodies)
        self.calls = 0

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.calls += 1
        return self.bodies.pop(0) if self.bodies else ""


def test_tier_b_emits_second_artifact_and_edge(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    out = tmp_path / "out"
    # scaffold_template() has two bullets -> propose+judge each = up to 4 bodies; both
    # rewrites are short and entity/number-free, so the overmatch filter passes both, and
    # the scripted judge marks both ENTAILED.
    client = ScriptedClient(["Shipped it", "ENTAILED", "Led it", "ENTAILED"])
    res = run_tailor(
        engine, settings, pid, resume_path=_resume_yaml(tmp_path), out_dir=out,
        typst_runner=_runner_ok, client=client, cache=ResponseCache(tmp_path / "c"),
    )
    assert res.tailored_artifact_id is not None  # Tier A artifact still recorded
    assert res.llm_artifact_id is not None  # Tier B artifact recorded
    assert res.rewrites is not None
    assert len(res.rewrites) == 2
    assert all(r["kept"] for r in res.rewrites)
    # both source files written
    assert (out / f"tailored-{pid}.typ").exists()
    assert (out / f"tailored-{pid}-llm.typ").exists()
    with engine.connect() as conn:
        edges = get_derivations(conn, res.llm_artifact_id)
        rows = conn.execute(artifacts.select()).fetchall()
    assert any(e.relation == "rewritten_from" for e in edges)
    assert any(e.parent_artifact_id == res.tailored_artifact_id for e in edges)
    llm_artifact = next(r for r in rows if r.id == res.llm_artifact_id)
    assert llm_artifact.kind == "resume_tailored_llm"
    assert llm_artifact.meta_json["calls_made"] == 4
    assert llm_artifact.meta_json["tier_a_artifact_id"] == res.tailored_artifact_id


def test_tier_b_off_is_tier_a_identical(tmp_path: Path) -> None:
    """No client -> Tier A output, artifacts, and files are exactly what Task 5 found them."""
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    out = tmp_path / "out"
    resume = _resume_yaml(tmp_path)
    res = run_tailor(engine, settings, pid, resume_path=resume, out_dir=out, typst_runner=_runner_ok)
    assert res.llm_artifact_id is None
    assert res.rewrites is None
    assert res.llm_source is None
    assert res.llm_pdf_path is None
    assert not (out / f"tailored-{pid}-llm.typ").exists()
    with engine.connect() as conn:
        rows = conn.execute(artifacts.select()).fetchall()
    assert {r.kind for r in rows} == {"resume_master", "resume_tailored"}


def test_tier_b_dry_run_writes_nothing(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    out = tmp_path / "out"
    client = ScriptedClient(["Shipped it", "ENTAILED", "Led it", "ENTAILED"])
    res = run_tailor(
        engine, settings, pid, resume_path=_resume_yaml(tmp_path), out_dir=out,
        typst_runner=_runner_ok, client=client, cache=ResponseCache(tmp_path / "c"), dry_run=True,
    )
    assert res.llm_artifact_id is None
    assert res.llm_source is not None  # preview computed in-memory
    assert not out.exists() or list(out.glob("*.typ")) == []
    with engine.connect() as conn:
        assert conn.execute(artifacts.select()).first() is None


def test_tier_b_zero_accepted_rewrites_still_emits_second_artifact(tmp_path: Path) -> None:
    """The common case: every candidate is dropped. Tier B must still emit its artifact,
    file, and edge (locked decision: always emit the separate variant) — with a row per
    bullet, all `kept=False`, and no divide-by-zero / crash on the empty-accept path."""
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    out = tmp_path / "out"
    # Both candidates invent a number not present in the source bullet -> overmatch filter
    # rejects both before any judge call is made.
    client = ScriptedClient(["Shipped 999 things", "Led 888 things"])
    res = run_tailor(
        engine, settings, pid, resume_path=_resume_yaml(tmp_path), out_dir=out,
        typst_runner=_runner_ok, client=client, cache=ResponseCache(tmp_path / "c"),
    )
    assert res.llm_artifact_id is not None
    assert res.rewrites is not None
    assert len(res.rewrites) == 2
    assert all(r["kept"] is False for r in res.rewrites)
    assert all(r["drop_reason"] == "filter" for r in res.rewrites)
    assert (out / f"tailored-{pid}-llm.typ").exists()
    # zero accepted rewrites -> Tier B render is byte-identical to Tier A's
    assert res.llm_source == res.source
