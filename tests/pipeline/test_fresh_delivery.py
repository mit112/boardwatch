"""D-670: a same-day pass cannot consume the nightly corpus or its health signal."""

from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
import respx
from gh_fixtures import gh_jobs
from sqlalchemy import insert, select, update
from typer.testing import CliRunner

from boardwatch.cli import run_cmd
from boardwatch.cli.app import app
from boardwatch.core.clock import utcnow
from boardwatch.core.liveness import verdict_for_status
from boardwatch.core.settings import load_settings
from boardwatch.pipeline import runner
from boardwatch.store import tables
from boardwatch.store.db import get_engine
from tests.pipeline.test_gate_stage import (  # noqa: F401
    _arm_gate,
    _needs_an_executable_fake,
    fake_claude,
)
from tests.pipeline.test_pipeline_run import _GH, _pipeline, _ready, _seed_posting

cli = CliRunner()


@pytest.fixture()
def data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("BOARDWATCH_ALERT_URL", raising=False)
    monkeypatch.setenv("BOARDWATCH_HEARTBEAT_URL", "https://monitor.test/success")
    return tmp_path / "data"


def test_repeated_provider_scans_one_union_and_leaves_other_boards_alone(data: Path) -> None:
    gh = _ready(data)
    other = _seed_posting(data, slug="other")
    engine = get_engine(data)
    with engine.begin() as conn:
        conn.execute(
            update(tables.companies)
            .where(tables.companies.c.slug == "other")
            .values(provider="lever")
        )
        conn.execute(
            insert(tables.companies).values(
                name="Ash", provider="ashby", slug="ash", source="user", watched=True
            )
        )
        # An empty COMPLETE response normally has a safeguard; one previous miss also proves
        # unselected boards cannot have their absence counter advanced by this scan.
        conn.execute(update(tables.postings).values(consecutive_missing=1))
    with respx.mock:
        respx.get(_GH.board_url("acme")).mock(return_value=httpx.Response(200, json={"jobs": []}))
        respx.get(_GH.board_url("acme2")).mock(
            return_value=httpx.Response(200, json={"jobs": gh_jobs()[:1]})
        )
        respx.get("https://api.ashbyhq.com/posting-api/job-board/ash").mock(
            return_value=httpx.Response(200, json={"jobs": []})
        )
        result = cli.invoke(
            app,
            [
                "--data-dir",
                str(data),
                "scan",
                "--provider",
                "greenhouse",
                "--provider",
                "ashby",
                "--provider",
                "greenhouse",
            ],
        )
    assert result.exit_code == 0, result.output
    with engine.connect() as conn:
        row = conn.execute(select(tables.runs)).one()
        assert row.boards_attempted == 3
        assert row.incremental is True
        scanned = set(conn.execute(select(tables.board_scans.c.company_id)).scalars())
        selected = set(
            conn.execute(
                select(tables.companies.c.id).where(
                    tables.companies.c.provider.in_(["greenhouse", "ashby"])
                )
            ).scalars()
        )
        assert scanned == selected
        assert (
            conn.execute(
                select(tables.postings.c.consecutive_missing).where(tables.postings.c.id == other)
            ).scalar_one()
            == 1
        )
        assert (
            conn.execute(
                select(tables.postings.c.status).where(tables.postings.c.id == gh)
            ).scalar_one()
            == "closed"
        )


@pytest.mark.parametrize(
    "args",
    [
        ("--fresh-hours", "8"),
        ("--no-scan", "--fresh-hours", "0"),
        ("--no-scan", "--fresh-hours", "-1"),
        ("--no-scan", "--fresh-hours", "1.5"),
    ],
)
def test_fresh_usage_is_rejected_before_context(
    data: Path, monkeypatch: pytest.MonkeyPatch, args: tuple[str, ...]
) -> None:
    build = Mock(side_effect=AssertionError("usage error touched the store"))
    monkeypatch.setattr(run_cmd, "build_context", build)
    result = cli.invoke(app, ["--data-dir", str(data), "run", *args])
    assert result.exit_code == 2
    assert "--fresh-hours" in result.output
    if args == ("--fresh-hours", "8"):
        assert "--no-scan" in result.output
    else:
        assert "1" in result.output
    build.assert_not_called()


def test_fresh_filter_precedes_rank_depth_and_scopes_preflights(
    data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _ready(data)
    # A prior nightly already cleared the old lead: it competes in the same rank tier.
    from boardwatch.eligibility.preflight import run_eligibility

    run_eligibility(get_engine(data), load_settings(data_dir=data))
    fresh = _seed_posting(data, slug="fresh")
    cutoff = utcnow() - timedelta(hours=8)
    with get_engine(data).begin() as conn:
        conn.execute(
            update(tables.postings)
            .where(tables.postings.c.id == old)
            .values(first_seen_at=cutoff - timedelta(seconds=1))
        )
        conn.execute(
            update(tables.postings)
            .where(tables.postings.c.id == fresh)
            .values(first_seen_at=cutoff)
        )
    # Pin the boundary and make the old, otherwise equal lead win ties if loaded at all.
    monkeypatch.setattr(runner, "utcnow", lambda: cutoff + timedelta(hours=8))
    summary = _pipeline(data, tmp_path / "apps", fresh_hours=8, top_n=1)
    assert summary.fatal is None
    assert [lead.posting_id for lead in summary.tailored] == [fresh]
    assert summary.shortlist.considered == 1
    with get_engine(data).connect() as conn:
        assert set(conn.execute(select(tables.extractions.c.posting_id)).scalars()) == {fresh}
        assert set(
            conn.execute(
                select(tables.posting_versions.c.posting_id)
                .join(
                    tables.eligibility_inputs,
                    tables.eligibility_inputs.c.posting_version_id == tables.posting_versions.c.id,
                )
                .join(
                    tables.eligibility_evaluations,
                    tables.eligibility_evaluations.c.input_id == tables.eligibility_inputs.c.id,
                )
                .where(tables.eligibility_evaluations.c.run_id == summary.run_id)
            ).scalars()
        ) == {fresh}
        assert (
            conn.execute(
                select(tables.runs.c.incremental).where(tables.runs.c.id == summary.run_id)
            ).scalar_one()
            is True
        )
    assert summary.funnel is not None and summary.morning is not None


@pytest.mark.usefixtures("fake_claude")
# The judged-lead assertions (`empty=False`) need the fake `claude`, which Windows cannot spawn.
@pytest.mark.parametrize("empty", [pytest.param(False, marks=_needs_an_executable_fake), True])
def test_fresh_skips_nightly_work_and_heartbeat(
    data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, empty: bool
) -> None:
    posting = _ready(data)
    if empty:
        with get_engine(data).begin() as conn:
            conn.execute(
                update(tables.postings)
                .where(tables.postings.c.id == posting)
                .values(first_seen_at=utcnow() - timedelta(days=2))
            )
    _arm_gate(data, refresh_budget=10, backlog_budget=10)
    settings = load_settings(data_dir=data)
    skipped = [
        "sweep_unwatched_deaths",
        "run_gate_refresh",
        "run_gate_backlog",
        "_sweep_form_questions",
        "check_intake_death",
        "check_delivery_drought",
        "check_apply_lane_drought",
        "check_apply_lane_volume",
        "check_buried_good_lead",
        "check_corpus_regression",
        "send_heartbeat",
    ]
    spies = {name: Mock(side_effect=AssertionError(f"fresh run called {name}")) for name in skipped}
    for name, spy in spies.items():
        monkeypatch.setattr(runner, name, spy)
    # Use the real pipeline but leave its existing gate fail-open transport fixture in control.
    summary = runner.run_pipeline(
        get_engine(data),
        settings,
        out_root=tmp_path / "apps",
        resume_path=settings.config_dir / "resume.yaml",
        skip_scan=True,
        fresh_hours=8,
        liveness_prober=lambda pid, url: verdict_for_status(pid, 200),
    )
    assert summary.fatal is None
    assert summary.death_probe is None
    assert summary.gate_refresh_candidates is None
    assert summary.gate_backlog_candidates is None
    assert summary.funnel is not None and summary.morning is not None
    report = summary.funnel.markdown_path.read_text()
    assert "standing-queue refresh not run (fresh delivery)" in report
    assert "backlog not run (fresh delivery)" in report
    if not empty:
        assert summary.gate_judged == 1
        assert summary.liveness_checked == 1
        assert len(summary.tailored) == 1
        assert summary.errors == []
    for spy in spies.values():
        spy.assert_not_called()


def test_empty_fresh_cli_is_one_line_and_does_not_ping(data: Path, tmp_path: Path) -> None:
    posting = _ready(data)
    with get_engine(data).begin() as conn:
        conn.execute(
            update(tables.postings)
            .where(tables.postings.c.id == posting)
            .values(first_seen_at=utcnow() - timedelta(days=2))
        )
    with respx.mock:
        ping = respx.get("https://monitor.test/success").mock(return_value=httpx.Response(200))
        result = cli.invoke(
            app,
            [
                "--data-dir",
                str(data),
                "run",
                "--no-scan",
                "--fresh-hours",
                "8",
                "--out",
                str(tmp_path / "apps"),
            ],
        )
    assert result.exit_code == 0, result.output
    assert result.output.strip().splitlines() == ["no fresh postings"]
    assert not ping.called


def test_real_tailor_failure_still_fails_fresh_run(
    data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ready(data)
    monkeypatch.setattr(runner, "run_tailor", Mock(side_effect=RuntimeError("broken render")))
    summary = _pipeline(data, tmp_path / "apps", fresh_hours=8)
    assert summary.fatal is not None
    with get_engine(data).connect() as conn:
        assert (
            conn.execute(
                select(tables.runs.c.status).where(tables.runs.c.id == summary.run_id)
            ).scalar_one()
            == "failed"
        )


def test_fresh_rejected_postings_do_not_trigger_empty_day_alarm(data: Path, tmp_path: Path) -> None:
    posting = _ready(data)
    with get_engine(data).begin() as conn:
        conn.execute(
            update(tables.postings)
            .where(tables.postings.c.id == posting)
            .values(title="Senior Accountant", normalized_title="senior accountant")
        )
    summary = _pipeline(data, tmp_path / "apps", fresh_hours=8)
    assert summary.fatal is None
    assert not summary.tailored
    assert summary.errors == []


def test_fresh_project_run_keeps_projection_and_delivery(
    data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.pipeline.test_pipeline_projection_leads import _projected_env, _SelectRunner, _use

    posting = _ready(data)
    _projected_env(data)
    _use(monkeypatch, _SelectRunner())
    summary = _pipeline(data, tmp_path / "apps", fresh_hours=8, project=True)
    assert summary.fatal is None
    assert [lead.posting_id for lead in summary.tailored] == [posting]
    assert summary.funnel is not None and summary.morning is not None
    assert summary.leads_with_pdf == 1


def test_a_lead_that_fails_to_build_on_a_fresh_pass_stays_open_for_the_nightly_run(
    data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    good, bad = _ready(data), _seed_posting(data, slug="bad")
    real = runner.run_tailor

    def flaky(*args: object, **kwargs: object) -> object:
        posting_id = next(
            (a for a in (*args, *kwargs.values()) if a == bad or getattr(a, "id", None) == bad),
            None,
        )
        if posting_id is not None:
            raise RuntimeError("transient render failure")
        return real(*args, **kwargs)

    monkeypatch.setattr(runner, "run_tailor", flaky)
    summary = _pipeline(data, tmp_path / "apps", fresh_hours=8, top_n=2)
    assert summary.fatal is None
    assert [lead.posting_id for lead in summary.tailored] == [good]
    assert summary.tailor_failed_ids == [bad]
    with get_engine(data).connect() as conn:
        bad_job = conn.execute(
            select(tables.postings.c.job_id).where(tables.postings.c.id == bad)
        ).scalar_one()
        assert conn.execute(
            select(tables.job_dispositions.c.disposition).where(
                tables.job_dispositions.c.job_id == bad_job
            )
        ).first() is None


def test_the_fresh_cut_uses_the_newest_older_posting_not_the_oldest(data: Path) -> None:
    from boardwatch.store.queries import first_seen_since_clause

    first, second = _ready(data), _seed_posting(data, slug="second")
    third = _seed_posting(data, slug="third")
    now = utcnow()
    with get_engine(data).begin() as conn:
        for posting, hours in ((first, 50), (second, 40), (third, 1)):
            conn.execute(
                update(tables.postings).where(tables.postings.c.id == posting)
                .values(first_seen_at=now - timedelta(hours=hours))
            )
    with get_engine(data).connect() as conn:
        got = conn.execute(
            select(tables.postings.c.id).where(first_seen_since_clause(now - timedelta(hours=8)))
        ).scalars().all()
    assert got == [third]
