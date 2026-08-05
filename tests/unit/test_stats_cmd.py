from pathlib import Path

import pytest
from rich.console import Console
from sqlalchemy import insert
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.cli.profile_cmd import persist_profile
from boardwatch.core.clock import utcnow
from boardwatch.core.settings import load_settings
from boardwatch.reports.stats import compute_stats
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.tables import companies, jobs, postings

NOW = utcnow()
runner = CliRunner()


@pytest.fixture()
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    data = tmp_path / "data"
    eng = get_engine(data)
    ensure_schema(eng)
    return data


def test_stats_without_profile_reports_no_profile(data_dir: Path) -> None:
    result = runner.invoke(app, ["--data-dir", str(data_dir), "stats"])
    assert "no profile" in result.stdout.lower()


def test_stats_with_profile_but_no_evals_reports_unevaluated(data_dir: Path) -> None:
    eng = get_engine(data_dir)
    settings = load_settings(data_dir=data_dir)  # matches build_context's construction
    persist_profile(
        eng, settings, text="python engineer",
        target_titles=[], exclude_titles=[], locations=[], remote_only=False,
    )
    with eng.begin() as conn:
        c = int(conn.execute(insert(companies).values(
            name="Acme", provider="greenhouse", slug="acme", source="user", watched=True,
        )).inserted_primary_key[0])
        job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
        conn.execute(insert(postings).values(
            company_id=c, job_id=job_id, provider_posting_id="p1", title="Python Engineer",
            normalized_title="python engineer", url="https://example.test/p1",
            locations_json=["Remote"], remote_policy="remote", posted_at=NOW,
            first_seen_at=NOW, last_seen_at=NOW, status="open", consecutive_missing=0,
            content_hash="p1", body_text="We hire python engineers.",
        ))
    result = runner.invoke(app, ["--data-dir", str(data_dir), "stats"])
    assert result.exit_code == 0
    out = result.stdout.lower()
    assert "unevaluated" in out
    assert "seen" in out

    report = compute_stats(
        eng, settings, window_days=7, now=NOW, output_console=Console()
    )
    assert report is not None
    assert report.unevaluated == 1
    assert report.qualified == 0
