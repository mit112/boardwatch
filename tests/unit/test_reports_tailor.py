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
from boardwatch.reports.tailor import (
    NoCurrentVersionError,
    UnsupportedFormatError,
    run_tailor,
)
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
from boardwatch.tailor.plan import MAX_BULLETS_PER_ENTRY
from boardwatch.tailor.rewrite.lane import TierBResult

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


def _resume_same_render_different_ids(tmp_path: Path, name: str, *, prefix: str) -> Path:
    """Two of these render byte-identically but are different authored documents.

    TypstRenderer.emit drops entry_id/bullet_id/tech_tags, so hashing the *render* made
    these collide onto one resume_master; only hashing the model tells them apart.
    """
    path = tmp_path / name
    path.write_text(
        "header:\n"
        '  - "Ada Lovelace"\n'
        "education:\n"
        '  - "BSc Mathematics — Example University — 2018"\n'
        "skill_groups:\n"
        '  - label: "Languages"\n'
        '    items: ["Python", "Rust"]\n'
        "entries:\n"
        f'  - entry_id: "{prefix}-entry"\n'
        '    heading: "Senior Engineer — Acme — 2021–2024 — Remote"\n'
        "    bullets:\n"
        f'      - bullet_id: "{prefix}-1"\n'
        '        text: "Built a Python service handling 2M requests/day on Kubernetes"\n'
        f'      - bullet_id: "{prefix}-2"\n'
        '        text: "Cut p99 latency 40% by rewriting the hot path in Rust"\n',
        encoding="utf-8",
    )
    return path


# 8 bullets in one entry, > MAX_BULLETS_PER_ENTRY, engineered against build_plan's
# `sorted(..., key=(-coverage, author_index))` so that with jd_skills={Python, JavaScript}:
#   coverage 1: b2 (Python), b3 (JS -> JavaScript swap), b5 (Python)
#   coverage 0: b1, b4, b6, b7, b8
# kept order  -> b2 b3 b5 b1 b4 b6 ; dropped -> b7 b8
# vs author order among survivors (b1..b6) only b6 lands on its own index, so b6 is the
# lone "kept" row, b3 is "swapped" (and reordered), b1/b2/b4/b5 are "reordered".
_AUDIT_RESUME = """\
header:
  - "Grace Hopper"
education:
  - "BSc Mathematics — Example University — 2016"
skill_groups:
  - label: "Languages"
    items: ["Python", "JavaScript"]
entries:
  - entry_id: "e1"
    heading: "Engineer — Example — 2020–2024 — Remote"
    bullets:
      - bullet_id: "b1"
        text: "Wrote the onboarding guide for new hires"
      - bullet_id: "b2"
        text: "Built a Python service handling millions of requests"
      - bullet_id: "b3"
        text: "Shipped JS tooling for the release process"
      - bullet_id: "b4"
        text: "Mentored two interns through their first quarter"
      - bullet_id: "b5"
        text: "Migrated the Python worker fleet off legacy hosts"
      - bullet_id: "b6"
        text: "Ran the weekly incident meeting"
      - bullet_id: "b7"
        text: "Drafted the on-call rotation policy"
      - bullet_id: "b8"
        text: "Organised the internal tooling summit"
"""


def _audit_resume_yaml(tmp_path: Path) -> Path:
    path = tmp_path / "audit-resume.yaml"
    path.write_text(_AUDIT_RESUME, encoding="utf-8")
    return path


def _audit_rows(tmp_path: Path) -> tuple[list[dict[str, object]], list[str]]:
    """Run the audit-trace résumé end to end; return meta_json's bullets + dropped."""
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    run_tailor(
        engine, settings, pid, resume_path=_audit_resume_yaml(tmp_path),
        out_dir=tmp_path / "out", typst_runner=_runner_ok,
    )
    with engine.connect() as conn:
        rows = conn.execute(artifacts.select()).fetchall()
    meta = next(r for r in rows if r.kind == "resume_tailored").meta_json
    return meta["bullets"], meta["dropped"]


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
    assert res.bullets and all("op" in b for b in res.bullets)


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


def test_distinct_masters_with_identical_render_are_not_collapsed(tmp_path: Path) -> None:
    """Two different authored résumés that *render* the same must stay two masters.

    The render drops bullet_id/entry_id/tech_tags, so hashing it content-addressed both
    documents to one resume_master and silently handed the second run the first one's
    file as its lineage parent. master_hash is over master.model_dump_json() instead.
    """
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    r_a = _resume_same_render_different_ids(tmp_path, "resume-a.yaml", prefix="alpha")
    r_b = _resume_same_render_different_ids(tmp_path, "resume-b.yaml", prefix="beta")
    assert r_a.read_text(encoding="utf-8") != r_b.read_text(encoding="utf-8")

    res_a = run_tailor(engine, settings, pid, resume_path=r_a, out_dir=tmp_path / "oa",
                       typst_runner=_runner_ok)
    res_b = run_tailor(engine, settings, pid, resume_path=r_b, out_dir=tmp_path / "ob",
                       typst_runner=_runner_ok)
    assert res_a.source == res_b.source  # identical visible text — the pre-fix collision

    with engine.connect() as conn:
        rows = conn.execute(artifacts.select()).fetchall()
        edges = conn.execute(artifact_derivations.select()).fetchall()
    masters = [r for r in rows if r.kind == "resume_master"]
    assert len(masters) == 2
    assert {m.uri for m in masters} == {str(r_a), str(r_b)}  # each master points at its own file
    assert len({m.content_hash for m in masters}) == 2

    by_uri = {m.uri: m for m in masters}
    parent_of = {e.artifact_id: e.parent_artifact_id for e in edges if e.relation == "tailored_from"}
    assert parent_of[res_a.tailored_artifact_id] == by_uri[str(r_a)].id
    assert parent_of[res_b.tailored_artifact_id] == by_uri[str(r_b)].id

    tailored = {r.id: r for r in rows if r.kind == "resume_tailored"}
    assert len(tailored) == 2
    meta_a = tailored[res_a.tailored_artifact_id].meta_json
    meta_b = tailored[res_b.tailored_artifact_id].meta_json
    assert meta_a["master_content_hash"] != meta_b["master_content_hash"]
    assert meta_a["master_artifact_id"] == by_uri[str(r_a)].id
    assert meta_b["master_artifact_id"] == by_uri[str(r_b)].id


def test_audit_rows_follow_spec_schema(tmp_path: Path) -> None:
    rows, dropped = _audit_rows(tmp_path)
    assert rows
    base = {"bullet_id", "entry_id", "op", "jd_skills_covered", "source_text_sha256",
            "output_text_sha256"}
    for row in rows:
        assert base <= set(row), row
        assert isinstance(row["jd_skills_covered"], list)
        assert row["op"] in {"kept", "reordered", "swapped", "dropped"}
        assert isinstance(row["source_text_sha256"], str) and len(row["source_text_sha256"]) == 64
        if row["op"] == "dropped":
            assert row["output_text_sha256"] is None
        else:
            assert "reordered" in row and isinstance(row["reordered"], bool)
            assert isinstance(row["output_text_sha256"], str)
            assert len(row["output_text_sha256"]) == 64
    # every authored bullet is accounted for exactly once
    ids = [r["bullet_id"] for r in rows]
    assert sorted(ids) == [f"b{i}" for i in range(1, 9)]
    assert len(ids) == len(set(ids))
    assert {r["entry_id"] for r in rows} == {"e1"}
    assert len(rows) - len(dropped) == MAX_BULLETS_PER_ENTRY


def test_audit_rows_classify_swap_reorder_and_keep(tmp_path: Path) -> None:
    rows, _ = _audit_rows(tmp_path)
    by_id = {r["bullet_id"]: r for r in rows}

    swapped = by_id["b3"]  # "Shipped JS tooling ..." with JavaScript in the JD skills
    assert swapped["op"] == "swapped"
    assert swapped["from"] == "JS"
    assert swapped["to"] == "JavaScript"
    assert swapped["swaps"] == [{"from": "JS", "to": "JavaScript"}]
    assert swapped["source_text_sha256"] != swapped["output_text_sha256"]
    assert swapped["jd_skills_covered"] == ["JavaScript"]  # covered only after the swap
    assert swapped["reordered"] is True  # b3 also moved; the swap is just the headline op

    for bid in ("b1", "b2", "b4", "b5"):  # moved relative to author order among survivors
        row = by_id[bid]
        assert row["op"] == "reordered", (bid, row)
        assert row["reordered"] is True
        assert row["source_text_sha256"] == row["output_text_sha256"]  # text untouched
        assert "from" not in row and "swaps" not in row

    untouched = by_id["b6"]  # same index in the author's surviving order as in the output
    assert untouched["op"] == "kept"
    assert untouched["reordered"] is False
    assert untouched["source_text_sha256"] == untouched["output_text_sha256"]
    assert untouched["jd_skills_covered"] == []


def test_dropped_bullets_have_matching_audit_rows(tmp_path: Path) -> None:
    rows, dropped = _audit_rows(tmp_path)
    assert sorted(dropped) == ["b7", "b8"]  # overflow past MAX_BULLETS_PER_ENTRY
    by_id = {r["bullet_id"]: r for r in rows}
    for bid in dropped:
        row = by_id[bid]
        assert row["op"] == "dropped"
        assert row["output_text_sha256"] is None
        assert row["source_text_sha256"]
        assert row["entry_id"] == "e1"
    assert {r["bullet_id"] for r in rows if r["op"] == "dropped"} == set(dropped)


def test_unsupported_format_raises_before_any_write(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    out = tmp_path / "out"
    with pytest.raises(UnsupportedFormatError):
        run_tailor(engine, settings, pid, resume_path=_resume_yaml(tmp_path), out_dir=out,
                   fmt="latex", typst_runner=_runner_ok)
    assert not out.exists()
    with engine.connect() as conn:
        assert conn.execute(artifacts.select()).first() is None
        assert conn.execute(artifact_derivations.select()).first() is None


class _NeverCalledClient:
    """A ModelClient whose complete() must never fire — the mutual-exclusion guard
    rejects the call before any Tier B work, so touching the provider is a bug."""

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        raise AssertionError("client.complete must not be called")


def test_client_and_tb_override_are_mutually_exclusive(tmp_path: Path) -> None:
    # The API lane (live client) and the subscription agent lane (precomputed
    # tb_override) are two disjoint ways to populate Tier B; passing both is a caller
    # bug and must fail closed before any planning, render, or write happens.
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="either client or tb_override"):
        run_tailor(
            engine, settings, pid, resume_path=_resume_yaml(tmp_path), out_dir=out,
            typst_runner=_runner_ok,
            client=_NeverCalledClient(),
            tb_override=TierBResult(accepted=[], rows=[], calls_made=0),
        )
    assert not out.exists()
    with engine.connect() as conn:
        assert conn.execute(artifacts.select()).first() is None
        assert conn.execute(artifact_derivations.select()).first() is None


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
