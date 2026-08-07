"""The résumé compile gate + untailored-master fallback inside run_tailor (P1a Task 3).

Uses an injected TypstRunner scripted by filename (the tailored vs. untailored vs. Tier-B
.typ files run_tailor writes are named distinctly), so "tailored fails, untailored ok" and
friends are directly expressible without a real typst binary. Mirrors
tests/unit/test_reports_tailor.py's `_settings`/`_engine`/`_seed`/`_resume_yaml` fixtures.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert

from boardwatch.core.settings import Settings
from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.reports.resume_gate import LeadArtifactError, TypstUnavailableError
from boardwatch.reports.tailor import run_tailor
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import save_profile
from boardwatch.store.tables import (
    artifacts,
    companies,
    extractions,
    jobs,
    posting_versions,
    postings,
)
from boardwatch.tailor.load import scaffold_template
from boardwatch.tailor.plan import Rewrite
from boardwatch.tailor.render.outcome import CompileOutcome, CompileReason
from boardwatch.tailor.rewrite.lane import TierBResult

NOW = datetime(2026, 8, 2, 12, 0, 0)

Runner = Callable[[Path, Path], CompileOutcome]


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


def _empty_bullets_resume_yaml(tmp_path: Path) -> Path:
    """An entry with every bullet deleted — validate_slots must reject this before render."""
    path = tmp_path / "empty-entry-resume.yaml"
    path.write_text(
        "header:\n"
        '  - "Ada Lovelace"\n'
        "education:\n"
        '  - "BSc Mathematics — Example University — 2018"\n'
        "skill_groups:\n"
        '  - label: "Languages"\n'
        '    items: ["Python"]\n'
        "entries:\n"
        '  - entry_id: "acme-sre"\n'
        '    heading: "Senior Engineer — Acme — 2021–2024 — Remote"\n'
        "    bullets: []\n",
        encoding="utf-8",
    )
    return path


def _seed(
    engine: Engine,
    settings: Settings,
    *,
    status: str = "open",
    content_hash: str = "h1",
    body: str = "Python JavaScript backend services",
    skills: tuple[str, ...] = (),
    slug: str = "acme",
) -> int:
    """Insert company+job+posting+version+extraction; return posting_id.

    Default skills=() so build_plan's `if not jd_skills: return TailorPlan(ops=())` fires —
    the tailored résumé is then an identity copy of the master, which is what lets the
    empty-bullets-entry fixture above reach validate_slots unchanged.
    """
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


def _ok(pdf: Path, pages: int, log: str = "ok") -> CompileOutcome:
    pdf.write_bytes(b"%PDF-1.7\n%stub\n")
    return CompileOutcome(CompileReason.OK, pdf, pages, log)


def _fail(log: str = "boom") -> CompileOutcome:
    return CompileOutcome(CompileReason.COMPILE_FAILED, None, None, log)


def _artifact_rows(engine: Engine) -> list[object]:
    with engine.connect() as conn:
        return list(conn.execute(artifacts.select()).fetchall())


def test_tailored_compile_failed_falls_back_to_untailored_degraded(tmp_path: Path) -> None:
    def runner(typ: Path, pdf: Path) -> CompileOutcome:
        if "untailored" in typ.name:
            return _ok(pdf, 1)
        return _fail("tailored compile boom")

    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    out = tmp_path / "day" / "acme-lead"
    res = run_tailor(
        engine, settings, pid, resume_path=_resume_yaml(tmp_path), out_dir=out, typst_runner=runner,
    )
    rows = _artifact_rows(engine)
    tailored = next(r for r in rows if r.kind == "resume_tailored")
    assert tailored.meta_json["degraded"] is True
    assert tailored.meta_json["degrade_reason"] == "compile_failed"
    assert tailored.meta_json["typst_pdf_built"] is True
    pdf_uri = Path(tailored.meta_json["pdf_uri"])
    assert pdf_uri.exists()
    log_uri = Path(tailored.meta_json["compile_log_uri"])
    assert log_uri.exists()
    assert res.pdf_path == pdf_uri


def test_tailored_over_page_limit_falls_back_to_untailored_degraded(tmp_path: Path) -> None:
    def runner(typ: Path, pdf: Path) -> CompileOutcome:
        pages = 1 if "untailored" in typ.name else 2
        return _ok(pdf, pages)

    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    out = tmp_path / "day" / "acme-lead"
    run_tailor(
        engine, settings, pid, resume_path=_resume_yaml(tmp_path), out_dir=out, typst_runner=runner,
    )
    rows = _artifact_rows(engine)
    tailored = next(r for r in rows if r.kind == "resume_tailored")
    assert tailored.meta_json["degraded"] is True
    assert tailored.meta_json["degrade_reason"] == "page_limit_exceeded"
    assert Path(tailored.meta_json["compile_log_uri"]).exists()


def test_both_unshippable_drops_lead_no_artifact_no_folder(tmp_path: Path) -> None:
    def runner(typ: Path, pdf: Path) -> CompileOutcome:
        return _fail(f"boom:{typ.name}")

    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    day_dir = tmp_path / "day"
    out = day_dir / "acme-lead"
    out.mkdir(parents=True)
    with pytest.raises(LeadArtifactError):
        run_tailor(
            engine, settings, pid, resume_path=_resume_yaml(tmp_path), out_dir=out, typst_runner=runner,
        )
    assert _artifact_rows(engine) == []
    assert not out.exists()
    failed_log = day_dir / "_failed" / "acme-lead.log"
    assert failed_log.exists()
    assert failed_log.read_text(encoding="utf-8")


def test_binary_missing_raises_typst_unavailable(tmp_path: Path) -> None:
    def runner(typ: Path, pdf: Path) -> CompileOutcome:
        return CompileOutcome(CompileReason.BINARY_MISSING, None, None, "")

    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    out = tmp_path / "out"
    with pytest.raises(TypstUnavailableError):
        run_tailor(
            engine, settings, pid, resume_path=_resume_yaml(tmp_path), out_dir=out, typst_runner=runner,
        )


def test_tier_b_binary_missing_raises_typst_unavailable(tmp_path: Path) -> None:
    def runner(typ: Path, pdf: Path) -> CompileOutcome:
        if "-llm" in typ.name:
            return CompileOutcome(CompileReason.BINARY_MISSING, None, None, "")
        return _ok(pdf, 1)

    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    out = tmp_path / "out"
    with pytest.raises(TypstUnavailableError):
        run_tailor(
            engine, settings, pid, resume_path=_resume_yaml(tmp_path), out_dir=out, typst_runner=runner,
            tb_override=TierBResult(accepted=[], rows=[], calls_made=0),
        )


def test_tailored_ok_within_limit_is_not_degraded(tmp_path: Path) -> None:
    def runner(typ: Path, pdf: Path) -> CompileOutcome:
        return _ok(pdf, 1)

    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    out = tmp_path / "out"
    res = run_tailor(
        engine, settings, pid, resume_path=_resume_yaml(tmp_path), out_dir=out, typst_runner=runner,
    )
    rows = _artifact_rows(engine)
    tailored = next(r for r in rows if r.kind == "resume_tailored")
    assert not tailored.meta_json.get("degraded")
    assert tailored.meta_json["typst_pdf_built"] is True
    assert Path(tailored.meta_json["pdf_uri"]).exists()
    assert Path(tailored.meta_json["compile_log_uri"]).exists()
    assert res.pdf_path is not None and res.pdf_path.exists()


def test_max_pages_honors_saved_profile_value(tmp_path: Path) -> None:
    """A saved profile's resume_max_pages=2 must actually be read, not floored to 1.

    The injected runner reports 2 pages for every compile (tailored and, were it reached,
    untailored). With max_pages correctly read as 2, the tailored render is within limit and
    ships un-degraded. If the profile_row branch were broken (e.g. hardcoded to 1), 2 pages
    would exceed a limit of 1 and this would either degrade or — since the untailored
    fallback would also report 2 pages — drop the lead entirely.
    """

    def runner(typ: Path, pdf: Path) -> CompileOutcome:
        return _ok(pdf, 2)

    settings = _settings(tmp_path)
    engine = _engine(settings)
    with engine.begin() as conn:
        save_profile(
            conn, text="t", target_titles=[], exclude_titles=[], locations=[],
            remote_only=False, skills=[], taxonomy_version="v1", resume_max_pages=2,
        )
    pid = _seed(engine, settings)
    out = tmp_path / "out"
    res = run_tailor(
        engine, settings, pid, resume_path=_resume_yaml(tmp_path), out_dir=out, typst_runner=runner,
    )
    rows = _artifact_rows(engine)
    tailored = next(r for r in rows if r.kind == "resume_tailored")
    assert not tailored.meta_json.get("degraded")
    assert tailored.meta_json["typst_pdf_built"] is True
    assert res.pdf_path is not None and res.pdf_path.exists()


def test_slot_validation_failure_falls_back_like_compile_failed(tmp_path: Path) -> None:
    def runner(typ: Path, pdf: Path) -> CompileOutcome:
        assert "untailored" in typ.name  # the tailored side must never reach the runner
        return _ok(pdf, 1)

    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)  # skills=() -> tailored is an identity copy of master
    out = tmp_path / "day" / "acme-lead"
    run_tailor(
        engine, settings, pid, resume_path=_empty_bullets_resume_yaml(tmp_path), out_dir=out,
        typst_runner=runner,
    )
    rows = _artifact_rows(engine)
    tailored = next(r for r in rows if r.kind == "resume_tailored")
    assert tailored.meta_json["degraded"] is True
    assert tailored.meta_json["degrade_reason"] == "compile_failed"


# --- P4 item 5a: the per-lead layout gate --------------------------------------------


def _degrade_layout_resume_yaml(tmp_path: Path) -> Path:
    """One entry, one bullet, within the length band as authored. The JD skill match
    "JavaScript" triggers Tier A's OWN JS->JavaScript equivalence swap (build_plan/apply.py),
    growing the bullet past BULLET_MAX_LENGTH in the tailored résumé while the untailored
    master (pre-swap) stays within band — a genuine per-lead risk the gate must catch, not
    an injected fixture."""
    filler = "a" * 150
    path = tmp_path / "degrade-layout-resume.yaml"
    path.write_text(
        "header:\n"
        '  - "Ada Lovelace"\n'
        "education:\n"
        '  - "BSc Mathematics — Example University — 2018"\n'
        "skill_groups:\n"
        '  - label: "Languages"\n'
        '    items: ["Python"]\n'
        "entries:\n"
        '  - entry_id: "acme-sre"\n'
        '    heading: "Senior Engineer — Acme — 2021–2024 — Remote"\n'
        "    bullets:\n"
        '      - bullet_id: "acme-1"\n'
        f'        text: "Shipped the {filler} dashboard rollout using the JS build '
        'pipeline reliably"\n',
        encoding="utf-8",
    )
    return path


def _seven_bullets_resume_yaml(tmp_path: Path) -> Path:
    """7 bullets in one entry, no JD skill matches: build_plan's `if not jd_skills` short-
    circuit emits no trimming ops at all, so both the tailored (an identity copy of master)
    and the untailored master exceed MAX_BULLETS_PER_ENTRY identically. This is the real gap
    item 5a closes — a zero-skill JD ships an untrimmed entry unless the layout gate catches
    it (design doc, §3)."""
    path = tmp_path / "seven-bullets-resume.yaml"
    path.write_text(
        "header:\n"
        '  - "Ada Lovelace"\n'
        "education:\n"
        '  - "BSc Mathematics — Example University — 2018"\n'
        "skill_groups:\n"
        '  - label: "Languages"\n'
        '    items: ["Python"]\n'
        "entries:\n"
        '  - entry_id: "acme-sre"\n'
        '    heading: "Senior Engineer — Acme — 2021–2024 — Remote"\n'
        "    bullets:\n"
        '      - bullet_id: "b1"\n'
        '        text: "Wrote onboarding docs and runbooks for the on-call rotation"\n'
        '      - bullet_id: "b2"\n'
        '        text: "Built a Python service for billing reconciliation nightly"\n'
        '      - bullet_id: "b3"\n'
        '        text: "Shipped a dashboard used daily by the operations team"\n'
        '      - bullet_id: "b4"\n'
        '        text: "Mentored two interns through their first shipped change"\n'
        '      - bullet_id: "b5"\n'
        '        text: "Ran the quarterly incident review with every stakeholder"\n'
        '      - bullet_id: "b6"\n'
        '        text: "Negotiated the vendor contract renewal with procurement"\n'
        '      - bullet_id: "b7"\n'
        '        text: "Organised the internal engineering reading group sessions"\n',
        encoding="utf-8",
    )
    return path


def test_layout_violation_falls_back_to_untailored_degraded(tmp_path: Path) -> None:
    def runner(typ: Path, pdf: Path) -> CompileOutcome:
        assert "untailored" in typ.name  # the tailored side must never reach the runner
        return _ok(pdf, 1)

    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings, skills=("JavaScript",))
    out = tmp_path / "day" / "acme-lead"
    run_tailor(
        engine, settings, pid, resume_path=_degrade_layout_resume_yaml(tmp_path), out_dir=out,
        typst_runner=runner,
    )
    rows = _artifact_rows(engine)
    tailored = next(r for r in rows if r.kind == "resume_tailored")
    assert tailored.meta_json["degraded"] is True
    assert tailored.meta_json["degrade_reason"] == "bullet_too_long"
    assert tailored.meta_json["typst_pdf_built"] is True


def test_zero_skill_seven_bullet_lead_ships_untailored_master_not_dropped(
    tmp_path: Path,
) -> None:
    """P4 checkpoint fix (was `test_layout_violation_on_both_sides_drops_lead`, which this
    behavior supersedes): the untailored MASTER fallback must never be gated by
    `validate_layout`. It is the unconditionally-shippable safety net (P1a — never silently
    delete a real job) -- Mit's authored, already page-valid résumé.

    `TOO_MANY_BULLETS` reuses `MAX_BULLETS_PER_ENTRY`, a *selection* cap `build_plan` trims
    entries TO. With no JD skills, `build_plan` returns empty ops, so the tailored résumé is
    an identity copy of the (untrimmed) authored master -- a 7-bullet entry that legitimately
    exceeds the 6-bullet ceiling. Before the fix, the tailored side failed the layout gate,
    degraded to the master, and the SAME gate then failed the master too, dropping a lead
    pre-checkpoint-fix shipped as Mit's real résumé. The fix removes the master-side gate, so
    both attempts reach the untailored render, which the runner below compiles successfully."""

    def runner(typ: Path, pdf: Path) -> CompileOutcome:
        # The tailored side still fails layout pre-render and must never reach the runner;
        # the untailored master, no longer gated, does reach it and compiles cleanly.
        assert "untailored" in typ.name
        return _ok(pdf, 1)

    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)  # skills=() -> tailored is an identity copy of master
    day_dir = tmp_path / "day"
    out = day_dir / "acme-lead"
    res = run_tailor(
        engine, settings, pid, resume_path=_seven_bullets_resume_yaml(tmp_path), out_dir=out,
        typst_runner=runner,
    )
    rows = _artifact_rows(engine)
    tailored = next(r for r in rows if r.kind == "resume_tailored")
    assert tailored.meta_json["degraded"] is True
    assert tailored.meta_json["degrade_reason"] == "too_many_bullets"
    assert tailored.meta_json["typst_pdf_built"] is True
    assert res.pdf_path is not None and res.pdf_path.exists()
    failed_log = day_dir / "_failed" / "acme-lead.log"
    assert not failed_log.exists()


def test_tier_b_layout_violation_is_skipped_tier_a_ships(tmp_path: Path) -> None:
    """A layout-violating Tier B rewrite must never reach typst; Tier A's own PDF (already
    gated above) remains the lead's sole deliverable -- fail-soft, not fail-drop."""

    def runner(typ: Path, pdf: Path) -> CompileOutcome:
        assert "-llm" not in typ.name  # the layout-violating Tier B .typ must never compile
        return _ok(pdf, 1)

    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)  # skills=() -> scaffold's tailored is an identity copy
    out = tmp_path / "out"
    res = run_tailor(
        engine, settings, pid, resume_path=_resume_yaml(tmp_path), out_dir=out,
        typst_runner=runner,
        tb_override=TierBResult(
            accepted=[Rewrite(bullet_id="acme-1", text="a" * 221)], rows=[], calls_made=0,
        ),
    )
    assert res.pdf_path is not None and res.pdf_path.exists()
    rows = _artifact_rows(engine)
    assert {r.kind for r in rows} == {"resume_master", "resume_tailored"}  # no *_llm artifact
    tailored = next(r for r in rows if r.kind == "resume_tailored")
    assert not tailored.meta_json.get("degraded")


def test_tier_b_clean_rewrite_still_ships_as_second_artifact(tmp_path: Path) -> None:
    """Regression guard: a layout-clean Tier B rewrite must still ship its own artifact --
    the new gate must not skip Tier B when it has nothing to catch."""

    def runner(typ: Path, pdf: Path) -> CompileOutcome:
        return _ok(pdf, 1)

    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    out = tmp_path / "out"
    run_tailor(
        engine, settings, pid, resume_path=_resume_yaml(tmp_path), out_dir=out,
        typst_runner=runner,
        tb_override=TierBResult(
            accepted=[Rewrite(bullet_id="acme-1", text="Shipped a clean rewrite of the bullet")],
            rows=[], calls_made=0,
        ),
    )
    rows = _artifact_rows(engine)
    assert {r.kind for r in rows} == {"resume_master", "resume_tailored", "resume_tailored_llm"}


def test_tier_b_lineage_references_the_shipped_tier_a_artifact_after_degrade(
    tmp_path: Path,
) -> None:
    """P4 checkpoint fix: when Tier A degrades to the untailored master, Tier B's recorded
    `tier_a_content_hash` must match the content_hash the shipped `resume_tailored` artifact
    actually carries (the untailored source's hash) -- not the rejected tailored render's
    hash, which was never written anywhere. Before the fix, `tier_a_content_hash` pointed at
    a résumé that never shipped while `tier_a_artifact_id` pointed at the row that did."""

    def runner(typ: Path, pdf: Path) -> CompileOutcome:
        if "-llm" in typ.name or "untailored" in typ.name:
            return _ok(pdf, 1)
        return _fail("tailored compile boom")  # forces Tier A to degrade

    settings = _settings(tmp_path)
    engine = _engine(settings)
    # skills=("Rust",) matches only the SECOND scaffold bullet ("...in Rust"), so build_plan
    # reorders it ahead of the first -- the tailored render's bullet order (and therefore its
    # content_hash) genuinely differs from the untailored master's. Without that difference,
    # `tailored_hash` and `chosen_hash` coincide by construction and this test cannot fail for
    # what it claims.
    pid = _seed(engine, settings, skills=("Rust",))
    out = tmp_path / "out"
    res = run_tailor(
        engine, settings, pid, resume_path=_resume_yaml(tmp_path), out_dir=out,
        typst_runner=runner,
        tb_override=TierBResult(
            accepted=[Rewrite(bullet_id="acme-1", text="Shipped a clean rewrite of the bullet")],
            rows=[], calls_made=0,
        ),
    )
    rows = _artifact_rows(engine)
    tier_a = next(r for r in rows if r.kind == "resume_tailored")
    tier_b = next(r for r in rows if r.kind == "resume_tailored_llm")
    assert tier_a.meta_json["degraded"] is True
    assert tier_b.meta_json["tier_a_artifact_id"] == res.tailored_artifact_id
    # The load-bearing assertion: Tier B's lineage hash must equal what Tier A actually
    # shipped, not the rejected tailored render (`tailored_hash` inside run_tailor).
    assert tier_b.meta_json["tier_a_content_hash"] == tier_a.content_hash
