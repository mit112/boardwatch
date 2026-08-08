"""P4 item 7: persona selection wired into the tailor flow.

Reuses tests/unit/test_run_tailor_gate.py's fixture shape (company+job+posting+version+
extraction seed, an injected compile runner scripted by filename) so an iOS JD vs a SWE JD is
directly expressible without a real tectonic binary.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from rich.console import Console
from sqlalchemy import Engine, insert

from boardwatch.core.settings import Settings, load_settings
from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.pipeline.runner import run_pipeline
from boardwatch.reports.tailor import run_tailor
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.tables import (
    artifacts,
    companies,
    extractions,
    jobs,
    posting_versions,
    postings,
)
from boardwatch.tailor.render.outcome import CompileOutcome, CompileReason
from tests.pipeline.test_pipeline_run import INIT_INPUT, _cli, _seed_posting

NOW = datetime(2026, 8, 2, 12, 0, 0)


def _settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data", config_dir=tmp_path / "cfg")


def _engine(settings: Settings) -> Engine:
    engine = get_engine(settings.data_dir)
    ensure_schema(engine)
    return engine


def _resume_yaml(tmp_path: Path) -> Path:
    """A master with two skill groups in a deliberately non-persona order so a reorder is
    observable, plus the scaffold's entries."""
    path = tmp_path / "resume.yaml"
    path.write_text(
        "header:\n"
        '  - "Ada Lovelace"\n'
        '  - "ada@example.com"\n'
        "education:\n"
        '  - "BSc — Example University — 2018"\n'
        "skill_groups:\n"
        '  - label: "iOS / Mobile"\n'
        '    items: ["Swift", "SwiftUI"]\n'
        '  - label: "Languages"\n'
        '    items: ["Python", "Swift"]\n'
        '  - label: "Backend"\n'
        '    items: ["Django"]\n'
        "entries:\n"
        '  - entry_id: "acme"\n'
        '    heading: "Engineer — Acme — 2021"\n'
        "    bullets:\n"
        '      - bullet_id: "b1"\n'
        '        text: "Shipped an iOS app in Swift used by thousands"\n',
        encoding="utf-8",
    )
    return path


def _seed(engine: Engine, settings: Settings, *, title: str, slug: str) -> int:
    body = "Swift iOS mobile engineer"
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
                    title=title, normalized_title=title.lower(),
                    url=f"https://example.test/{slug}", locations_json=["Remote"],
                    remote_policy="remote", posted_at=NOW, first_seen_at=NOW, last_seen_at=NOW,
                    status="open", consecutive_missing=0, content_hash=f"h-{slug}", body_text=body,
                )
            ).inserted_primary_key[0]
        )
        conn.execute(
            insert(posting_versions).values(
                posting_id=posting_id, content_hash=f"h-{slug}", body_text=body,
                captured_at=NOW, capture_reason="new",
            )
        )
        conn.execute(
            insert(extractions).values(
                posting_id=posting_id, content_hash=f"h-{slug}", kind="taxonomy",
                engine_version=load_taxonomy(settings.config_dir).version,
                json={"skills": []}, created_at=NOW,
            )
        )
    return posting_id


def _ok(pdf: Path, pages: int = 1) -> CompileOutcome:
    pdf.write_bytes(b"%PDF-1.7\n%stub\n")
    return CompileOutcome(CompileReason.OK, pdf, pages, "ok")


def _runner(typ: Path, pdf: Path) -> CompileOutcome:
    return _ok(pdf)


def _tailored_meta(engine: Engine) -> dict[str, object]:
    with engine.connect() as conn:
        rows = list(conn.execute(artifacts.select()).fetchall())
    tailored = next(r for r in rows if r.kind == "resume_tailored")
    return dict(tailored.meta_json)


def test_ios_jd_selects_ios_persona_reorders_skills_and_records_meta(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings, title="Senior iOS Engineer", slug="acme")
    res = run_tailor(
        engine, settings, pid, resume_path=_resume_yaml(tmp_path),
        out_dir=tmp_path / "out", typst_runner=_runner,
    )
    assert res.persona_id == "ios"
    meta = _tailored_meta(engine)
    assert meta["persona_id"] == "ios"
    # de-senioritized headline, in-family, kept
    assert meta["resolved_title"] == "iOS Engineer"
    # ios persona skill_group_order is [Languages, "iOS / Mobile", Backend]; the shaped render
    # must place Languages before iOS/Mobile before Backend.
    src = res.source
    assert (
        src.index(r"\textbf{Languages}")
        < src.index(r"\textbf{iOS / Mobile}")
        < src.index(r"\textbf{Backend}")
    )
    # the resolved title flows into the rendered TITLE slot
    assert "iOS Engineer" in src


def test_normal_swe_jd_uses_general_swe_persona(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings, title="Backend Engineer", slug="beco")
    res = run_tailor(
        engine, settings, pid, resume_path=_resume_yaml(tmp_path),
        out_dir=tmp_path / "out", typst_runner=_runner,
    )
    assert res.persona_id == "general_swe"
    meta = _tailored_meta(engine)
    assert meta["persona_id"] == "general_swe"
    assert meta["resolved_title"] == "Backend Engineer"


@pytest.fixture()
def pipeline_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _ready(data_dir: Path) -> int:
    posting_id = _seed_posting(data_dir)
    assert _cli(data_dir, ["init"], INIT_INPUT).exit_code == 0
    assert _cli(data_dir, ["tailor", "init"]).exit_code == 0
    return posting_id


def test_broken_registry_aborts_the_run_loudly_not_a_silent_per_lead_drop(
    pipeline_env: Path, tmp_path: Path
) -> None:
    """A malformed {config_dir}/personas.yaml override must be a run-level FATAL surfaced
    loudly (like a broken master résumé), not a per-lead drop rediscovered lead by lead."""
    data_dir = pipeline_env
    _ready(data_dir)
    settings = load_settings(data_dir=data_dir)
    # Two defaults => malformed registry.
    (settings.config_dir / "personas.yaml").write_text(
        "personas:\n"
        "  - id: a\n"
        '    title: "A"\n'
        "    default: true\n"
        "    role_families: [general_swe]\n"
        "    skill_group_order: []\n"
        "    entries: null\n"
        "  - id: b\n"
        '    title: "B"\n'
        "    default: true\n"
        "    role_families: [backend]\n"
        "    skill_group_order: []\n"
        "    entries: null\n",
        encoding="utf-8",
    )
    summary = run_pipeline(
        get_engine(data_dir),
        settings,
        console=Console(quiet=True),
        out_root=tmp_path / "apps",
        resume_path=settings.config_dir / "resume.yaml",
        skip_scan=True,
    )
    assert summary.fatal is not None
    assert "persona registry invalid" in summary.fatal
    assert summary.tailor_failed == 0  # not counted as a per-lead tailor failure
    assert summary.tailored == []
