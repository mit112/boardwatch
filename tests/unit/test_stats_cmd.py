from pathlib import Path

import pytest
from rich.console import Console
from sqlalchemy import insert
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.cli.profile_cmd import persist_profile
from boardwatch.core.clock import utcnow
from boardwatch.core.settings import load_settings
from boardwatch.reports.stats import StatsReport, compute_stats
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


def _seed_one_posting(data_dir: Path, *, title: str, band: str) -> None:
    """One open posting plus a profile targeting `band` — the smallest stats population."""
    eng = get_engine(data_dir)
    settings = load_settings(data_dir=data_dir)
    persist_profile(
        eng, settings, text="python engineer",
        target_titles=[], exclude_titles=[], locations=[], remote_only=False,
        target_seniority_band=band,
    )
    with eng.begin() as conn:
        c = int(conn.execute(insert(companies).values(
            name="Acme", provider="greenhouse", slug="acme", source="user", watched=True,
        )).inserted_primary_key[0])
        job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
        conn.execute(insert(postings).values(
            company_id=c, job_id=job_id, provider_posting_id="p1", title=title,
            normalized_title=title.lower(), url="https://example.test/p1",
            locations_json=["Remote"], remote_policy="remote", posted_at=NOW,
            first_seen_at=NOW, last_seen_at=NOW, status="open", consecutive_missing=0,
            content_hash="p1", body_text="We hire python engineers.",
        ))


def _report(data_dir: Path) -> StatsReport | None:
    return compute_stats(
        get_engine(data_dir), load_settings(data_dir=data_dir),
        window_days=7, now=NOW, output_console=Console(),
    )


def test_stats_counts_an_above_band_posting(data_dir: Path) -> None:
    """`top` hides it, so a readout that never counted it would disagree with the shortlist."""
    _seed_one_posting(data_dir, title="Staff Software Engineer", band="entry")
    report = _report(data_dir)
    assert report is not None
    assert report.over_seniority == 1
    assert report.passes_filters == 1  # reported alongside the chain, never subtracted from it


def test_stats_does_not_count_an_in_band_posting(data_dir: Path) -> None:
    _seed_one_posting(data_dir, title="Python Engineer", band="entry")
    report = _report(data_dir)
    assert report is not None
    assert report.over_seniority == 0


def test_the_stats_table_renders_the_over_seniority_count(tmp_path, monkeypatch):
    """A counter that is computed and tested but never rendered is invisible to the operator."""
    import inspect

    from boardwatch.cli import stats_cmd

    source = inspect.getsource(stats_cmd)
    assert "over target band" in source, "over_seniority is counted but never shown"
    assert "report.over_seniority" in source
def test_a_posting_that_is_both_non_swe_and_over_band_is_counted_once(data_dir: Path) -> None:
    """`top` gates in ORDER: the role gate `continue`s before the seniority gate ever runs, so
    this posting is `hidden_non_swe` there and nothing else. Counted independently here it
    landed in both buckets, and `stats.over_seniority` read higher than the funnel's
    `hidden_over_seniority` for the same corpus -- two numbers for one gate that could not be
    reconciled, which is the whole discipline this gate was built under."""
    from boardwatch.cli.top_cmd import rank_open_postings

    _seed_one_posting(data_dir, title="Senior Marketing Manager", band="entry")
    report = _report(data_dir)
    assert report is not None
    assert report.non_swe == 1
    assert report.over_seniority == 0

    # Counted a second time through the OTHER path -- the one the funnel writes down -- because
    # a component's self-report is not verification (CLAUDE.md).
    ranked = rank_open_postings(
        get_engine(data_dir), load_settings(data_dir=data_dir),
        limit=50, record_surfaced=False, output_console=Console(),
    )
    assert (ranked.hidden_non_swe, ranked.hidden_over_seniority) == (
        report.non_swe, report.over_seniority
    )
