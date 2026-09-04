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

from sqlalchemy import Engine, insert, select

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
from boardwatch.tailor.render.outcome import CompileOutcome, CompileReason
from tests.conftest import write_test_resume_template

NOW = datetime(2026, 8, 2, 12, 0, 0)


def _settings(tmp_path: Path) -> Settings:
    config_dir = tmp_path / "cfg"
    config_dir.mkdir(parents=True, exist_ok=True)
    # T2: `resolve_template` no longer falls back to the bundled default for a real config
    # dir missing `resume_template.tex`, and rendering here goes through the real
    # `LatexRenderer(config_dir=settings.config_dir)` — so this environment needs one on
    # disk, as a properly set-up user's config dir would.
    write_test_resume_template(config_dir)
    return Settings(data_dir=tmp_path / "data", config_dir=config_dir)


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


def _runner_ok(typ: Path, pdf: Path) -> CompileOutcome:
    pdf.write_bytes(b"%PDF")
    return CompileOutcome(CompileReason.OK, pdf, 1, "ok")


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
    # rewrites are entity/number-free and provenanced (only a connective swapped), so the
    # overmatch filter and the provenance check both pass, and the scripted judge marks
    # both ENTAILED.
    client = ScriptedClient(
        [
            "Built the Python service handling 2M requests/day on Kubernetes",
            "ENTAILED",
            "Cut p99 latency 40% by rewriting the hot path with Rust",
            "ENTAILED",
        ]
    )
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
    assert res.pdf_path is not None
    assert (out / f"{res.pdf_path.stem}.tex").exists()
    assert len(list(out.glob("*_llm.tex"))) == 1
    with engine.connect() as conn:
        edges = get_derivations(conn, res.llm_artifact_id)
        rows = conn.execute(artifacts.select()).fetchall()
    assert any(e.relation == "rewritten_from" for e in edges)
    assert any(e.parent_artifact_id == res.tailored_artifact_id for e in edges)
    llm_artifact = next(r for r in rows if r.id == res.llm_artifact_id)
    assert llm_artifact.kind == "resume_tailored_llm"
    assert llm_artifact.meta_json["calls_made"] == 4
    assert llm_artifact.meta_json["tier_a_artifact_id"] == res.tailored_artifact_id


def _tier_a_row(engine: Engine, art_id: int) -> object:
    with engine.connect() as conn:
        return conn.execute(
            select(artifacts.c.kind, artifacts.c.content_hash, artifacts.c.meta_json).where(
                artifacts.c.id == art_id
            )
        ).one()


def test_tier_b_off_is_tier_a_identical(tmp_path: Path) -> None:
    """Tier A's source, content hash, and meta_json must not shift when Tier B runs.

    Differential, not hardcoded: run the SAME authored résumé twice, once with no client
    (Tier B off) and once with a client whose rewrites are genuinely accepted (Tier B on),
    and prove the Tier A halves — source, kept/dropped/bullets, recorded content_hash and
    meta_json — are byte-for-byte identical either way. A hardcoded expected value would
    rot silently as Tier A's own fixtures/logic evolve; this proves the invariant directly.
    """
    resume = _resume_yaml(tmp_path)
    # Same out_dir for both runs: each engine is an independent, freshly seeded database,
    # so pid_a == pid_b == 1 and both plan the SAME name, with byte-identical content —
    # sharing the directory means pdf_uri/tex_uri are identical too, not just the content,
    # so meta_json can be compared with zero exclusions below.
    out = tmp_path / "out"

    # Run 1: Tier A only.
    s_a = _settings(tmp_path / "a")
    e_a = _engine(s_a)
    pid_a = _seed(e_a, s_a)
    res_a = run_tailor(e_a, s_a, pid_a, resume_path=resume, out_dir=out, typst_runner=_runner_ok)

    # Tier B left no trace in this no-client run — checked now, before run 2 writes into
    # the same shared directory below.
    assert res_a.llm_artifact_id is None
    assert res_a.rewrites is None
    assert res_a.llm_source is None
    assert res_a.llm_pdf_path is None
    assert not list(out.glob("*_llm.tex"))
    with e_a.connect() as conn:
        rows = conn.execute(artifacts.select()).fetchall()
    assert {r.kind for r in rows} == {"resume_master", "resume_tailored"}

    # Run 2: same input, Tier B enabled with rewrites that are actually accepted (filter
    # passes, judge says ENTAILED) — the case most likely to perturb Tier A if anything did.
    s_b = _settings(tmp_path / "b")
    e_b = _engine(s_b)
    pid_b = _seed(e_b, s_b)
    client = ScriptedClient(["Shipped it", "ENTAILED", "Led it", "ENTAILED"])
    res_b = run_tailor(
        e_b, s_b, pid_b, resume_path=resume, out_dir=out, typst_runner=_runner_ok,
        client=client, cache=ResponseCache(tmp_path / "cache"),
    )
    assert res_b.llm_artifact_id is not None  # Tier B really did run, not a no-op

    # Tier A halves are byte-identical regardless of whether Tier B ran alongside them.
    assert res_b.source == res_a.source
    assert res_b.kept == res_a.kept
    assert res_b.dropped == res_a.dropped
    assert res_b.bullets == res_a.bullets

    # ...and so is the recorded Tier A artifact: same content_hash and same meta_json.
    # Both engines are independent, freshly seeded databases with identical insert order,
    # so ids (posting/master/etc.) coincide too — the two dicts compare equal with zero
    # exclusions, which is stricter proof than filtering keys out would have been.
    row_a = _tier_a_row(e_a, res_a.tailored_artifact_id)
    row_b = _tier_a_row(e_b, res_b.tailored_artifact_id)
    assert row_b.kind == row_a.kind == "resume_tailored"
    assert row_b.content_hash == row_a.content_hash
    assert row_b.meta_json == row_a.meta_json


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
    assert not out.exists() or list(out.glob("*.tex")) == []
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
    # Both candidates invent a number the source bullet doesn't have -> the filter's
    # specific reason ("added_number") is carried, not the flat "filter".
    assert all(r["drop_reason"] == "filter:added_number" for r in res.rewrites)
    assert len(list(out.glob("*_llm.tex"))) == 1
    # zero accepted rewrites -> Tier B render is byte-identical to Tier A's
    assert res.llm_source == res.source
