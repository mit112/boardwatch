"""`boardwatch verify` end to end (P0 item 5).

The unit tests pin the core and the queries in isolation. What only a real run can show is that
verify locates the artifact a pipeline actually wrote, agrees with it when the store and disk are
intact, and fails with the right typed kind when a deliverable is missing or the artifact is
malformed. Reuses the pipeline harness so the store + disk are seeded the way production seeds
them.
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
from tests.pipeline.test_pipeline_run import INIT_INPUT, _cli, _seed_posting


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _ready(data_dir: Path) -> None:
    _seed_posting(data_dir)
    assert _cli(data_dir, ["init"], INIT_INPUT).exit_code == 0
    assert _cli(data_dir, ["tailor", "init"]).exit_code == 0


def _run_once(data_dir: Path, out_root: Path) -> int:
    settings = load_settings(data_dir=data_dir)
    summary = run_pipeline(
        get_engine(data_dir), settings, console=Console(quiet=True),
        out_root=out_root, resume_path=settings.config_dir / "resume.yaml", skip_scan=True,
    )
    return summary.run_id


def test_verify_run_passes_on_intact_store_and_disk(env: Path, tmp_path: Path) -> None:
    _ready(env)
    out_root = tmp_path / "apps"
    run_id = _run_once(env, out_root)
    result = _cli(env, ["verify", "--run", str(run_id), "--out-root", str(out_root)])
    assert result.exit_code == 0, result.stdout
    assert "RECONCILES" in result.stdout


def test_verify_run_fails_when_a_pdf_is_deleted(env: Path, tmp_path: Path) -> None:
    _ready(env)
    out_root = tmp_path / "apps"
    run_id = _run_once(env, out_root)
    engine = get_engine(env)
    with engine.connect() as conn:
        rows = conn.execute(
            select(tables.artifacts.c.meta_json).where(
                tables.artifacts.c.run_id == run_id,
                tables.artifacts.c.kind == "resume_tailored",
            )
        ).all()
    # Pick a row whose PDF actually landed on disk, not merely the first row — otherwise the
    # test could vacuously skip while a later row's PDF was available to delete.
    pdf_paths = [
        Path(r.meta_json["pdf_uri"])
        for r in rows
        if r.meta_json.get("pdf_uri") and Path(r.meta_json["pdf_uri"]).exists()
    ]
    if not pdf_paths:
        pytest.skip("this run produced no PDF to delete (typst unavailable)")
    pdf_paths[0].unlink()
    result = _cli(env, ["verify", "--run", str(run_id), "--out-root", str(out_root)])
    assert result.exit_code == 1
    assert "missing_pdf_file" in result.stdout


def test_verify_run_reports_no_artifact_for_unknown_run(env: Path, tmp_path: Path) -> None:
    _ready(env)
    out_root = tmp_path / "apps"
    _run_once(env, out_root)
    result = _cli(env, ["verify", "--run", "9999", "--out-root", str(out_root)])
    assert result.exit_code == 1
    assert "no_artifact" in result.stdout


def test_verify_reports_malformed_funnel(env: Path, tmp_path: Path) -> None:
    _ready(env)
    out_root = tmp_path / "apps"
    run_id = _run_once(env, out_root)
    funnel = next(out_root.glob(f"*/funnel-{run_id}.json"))
    funnel.write_text("{ this is not json", encoding="utf-8")
    result = _cli(env, ["verify", "--run", str(run_id), "--out-root", str(out_root)])
    assert result.exit_code == 1
    assert "malformed_funnel" in result.stdout


def test_verify_sweep_checks_every_artifact_on_disk(env: Path, tmp_path: Path) -> None:
    # Two runs so the test can distinguish "checks every artifact" from "checks the first glob
    # match": an implementation that verified only one would report `runs checked: 1` and fail.
    _ready(env)
    out_root = tmp_path / "apps"
    _run_once(env, out_root)
    _run_once(env, out_root)
    result = _cli(env, ["verify", "--out-root", str(out_root)])
    assert result.exit_code == 0, result.stdout
    assert "runs checked:** 2" in result.stdout
