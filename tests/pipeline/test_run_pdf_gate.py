"""The P1a résumé-artifact gate enforced end to end in the pipeline (P1a Task 4).

Task 3 made `run_tailor` raise `RenderToolMissingError` (an environment fault — the binary is
either on PATH or it isn't) and `LeadArtifactError` (a lead has no shippable PDF after the
untailored-master fallback) instead of silently returning a result with `pdf_path=None`. This
proves the pipeline's tailor loop actually reacts to both, and that the two map to different
blast radii: a per-lead failure is dropped like any other tailor failure (the run survives),
while a binary-missing failure aborts the whole tailor stage as a run-level fatal. Before this
change both were swallowed by the loop's generic `except Exception`, so a missing binary only
ever surfaced (if at all) as "every lead failed to tailor" after burning through the entire
shortlist re-discovering the same fault N times.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rich.console import Console
from sqlalchemy import select

from boardwatch.core.settings import load_settings
from boardwatch.pipeline.runner import run_pipeline
from boardwatch.store import tables
from boardwatch.store.db import get_engine
from boardwatch.tailor.render.outcome import CompileOutcome, CompileReason
from tests.pipeline.test_pipeline_run import INIT_INPUT, _cli, _seed_posting


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Defined here rather than imported: importing the fixture would shadow it at every test
    signature, which ruff flags as a redefinition (F811)."""
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _ready(data_dir: Path) -> int:
    posting_id = _seed_posting(data_dir)
    assert _cli(data_dir, ["init"], INIT_INPUT).exit_code == 0
    assert _cli(data_dir, ["tailor", "init"]).exit_code == 0
    return posting_id


def _pipeline(data_dir: Path, out_root: Path, **kw: object):
    settings = load_settings(data_dir=data_dir)
    return run_pipeline(
        get_engine(data_dir),
        settings,
        console=Console(quiet=True),
        out_root=out_root,
        resume_path=settings.config_dir / "resume.yaml",
        skip_scan=True,
        **kw,
    )


def _run_status(data_dir: Path, run_id: int) -> str:
    with get_engine(data_dir).connect() as conn:
        return str(
            conn.execute(
                select(tables.runs.c.status).where(tables.runs.c.id == run_id)
            ).scalar_one()
        )


def _fail(log: str = "boom") -> CompileOutcome:
    return CompileOutcome(CompileReason.COMPILE_FAILED, None, None, log)


def _ok(pdf: Path, pages: int = 1, log: str = "ok") -> CompileOutcome:
    pdf.write_bytes(b"%PDF-1.7\n%stub\n")
    return CompileOutcome(CompileReason.OK, pdf, pages, log)


def test_a_lead_that_cannot_compile_either_way_is_dropped_not_fatal(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both the tailored and untailored-master render fail for ONE of two leads: that lead is
    dropped, its folder is not left behind, and the run is still `ok`. A second, healthy lead
    is required so this cannot be confused with "every lead failed to tailor", which the
    pipeline treats as fatal on purpose (a broken résumé path, not a few dead leads)."""
    doomed_id = _ready(env)
    _seed_posting(env, slug="acme3")  # a second lead, so one failure != every lead failing
    out_root = tmp_path / "apps"

    def runner(typ: Path, pdf: Path) -> CompileOutcome:
        if typ.stem.endswith(f"-{doomed_id}"):
            return _fail(f"boom:{typ.name}")
        return _ok(pdf)

    monkeypatch.setattr("boardwatch.reports.tailor._default_runner", runner)
    summary = _pipeline(env, out_root)

    tailored_ids = [lead.posting_id for lead in summary.tailored]
    assert doomed_id not in tailored_ids, "the unshippable lead was reported as tailored"
    assert summary.tailor_failed >= 1
    assert summary.tailored, "the healthy second lead never shipped, so this proves nothing"
    # `_failed/<lead>.log` is Task 3's deliberate failure record, not a husk — only a lead
    # folder left behind would mean the deliverable count is inflated.
    lead_dirs = {p.name for p in out_root.glob("*/*") if p.is_dir() and p.name != "_failed"}
    assert not any(name.endswith(f"-{doomed_id}") for name in lead_dirs), (
        f"a folder was left behind for the dropped lead: {lead_dirs}"
    )
    assert summary.fatal is None, "one lead failing to compile should not fail the run"
    assert _run_status(env, summary.run_id) == "ok"


def test_a_lead_that_only_the_untailored_master_compiles_still_ships_degraded(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The untailored-master fallback compiles: the lead ships, degraded, with a real PDF."""
    _ready(env)
    out_root = tmp_path / "apps"

    def runner(typ: Path, pdf: Path) -> CompileOutcome:
        if "untailored" in typ.name:
            return _ok(pdf)
        return _fail("tailored compile boom")

    monkeypatch.setattr("boardwatch.reports.tailor._default_runner", runner)
    summary = _pipeline(env, out_root)

    assert summary.tailored, "the degraded lead never shipped, so this test proves nothing"
    lead = summary.tailored[0]
    assert lead.pdf_built is True
    assert lead.out_dir.is_dir()
    assert summary.fatal is None


def test_binary_missing_is_a_run_level_fatal_not_a_per_lead_drop(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing `typst` binary is an environment fault: it aborts the tailor stage rather than
    being rediscovered lead by lead and reported as "every lead failed to tailor"."""
    _ready(env)
    out_root = tmp_path / "apps"

    monkeypatch.setattr("boardwatch.reports.tailor.shutil.which", lambda name: None)
    summary = _pipeline(env, out_root)

    assert summary.tailored == []
    assert summary.fatal is not None
    assert "tectonic" in summary.fatal.lower()
    assert _run_status(env, summary.run_id) == "failed"


def test_cli_run_exits_nonzero_when_typst_binary_is_missing(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ready(env)
    monkeypatch.setattr("boardwatch.reports.tailor.shutil.which", lambda name: None)

    result = _cli(env, ["run", "--no-scan", "--out", str(tmp_path / "apps")])

    assert result.exit_code != 0, result.output


def test_broken_master_resume_is_a_run_level_fatal_not_a_per_lead_drop(
    env: Path, tmp_path: Path
) -> None:
    """P4 item 5b: a master résumé missing contact info is an authoring fault, exactly like a
    missing `typst` binary — it aborts the tailor stage rather than being rediscovered lead by
    lead and reported as "every lead failed to tailor"."""
    _ready(env)
    settings = load_settings(data_dir=env)
    (settings.config_dir / "resume.yaml").write_text(
        'header:\n  - "Ada Lovelace"\neducation: []\nskill_groups: []\nentries:\n'
        '  - entry_id: "e1"\n    heading: "Senior Engineer"\n    bullets:\n'
        '      - bullet_id: "b1"\n        text: "Did a thing"\n',
        encoding="utf-8",
    )
    out_root = tmp_path / "apps"

    summary = _pipeline(env, out_root)

    assert summary.tailored == []
    assert summary.fatal is not None
    assert "master résumé" in summary.fatal
    assert _run_status(env, summary.run_id) == "failed"


def test_every_tailored_lead_has_a_built_pdf_on_a_normal_run(env: Path, tmp_path: Path) -> None:
    """The gate's headline property (P1a): every lead the pipeline reports carries a PDF, using
    the real `typst` binary rather than an injected runner."""
    _ready(env)
    out_root = tmp_path / "apps"

    summary = _pipeline(env, out_root)

    assert summary.tailored, "nothing was tailored, so this test proves nothing"
    assert all(lead.pdf_built for lead in summary.tailored)


def test_tailored_artifact_row_is_a_real_tex_file_with_pdf_built_meta(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Task 7 end-to-end proof for the LaTeX/tectonic swap: a fake `_default_runner` stands in
    for tectonic, but the assertion reads the persisted `resume_tailored` artifact ROW back from
    the store — a different path than the one that wrote it (never trust a component's own
    self-report) — and confirms the LaTeX-era shape: `.tex` uri, `media_type="text/x-tex"`, and
    the legacy `typst_pdf_built` meta key still True."""
    _ready(env)
    out_root = tmp_path / "apps"

    monkeypatch.setattr("boardwatch.reports.tailor._default_runner", lambda tex, pdf: _ok(pdf))
    summary = _pipeline(env, out_root)

    assert summary.tailored, "nothing was tailored, so this test proves nothing"
    with get_engine(env).connect() as conn:
        rows = conn.execute(
            select(tables.artifacts).where(tables.artifacts.c.kind == "resume_tailored")
        ).fetchall()
    assert rows, "no resume_tailored artifact row was written"
    for row in rows:
        assert row.media_type == "text/x-tex"
        assert row.uri.endswith(".tex")
        assert row.meta_json["typst_pdf_built"] is True
