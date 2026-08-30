"""Coordinator round-trip, state test d, failure isolation, CLI smoke."""

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from gh_fixtures import BOARD_URL, gh_jobs, snapshot_for
from provider_cases import ProviderCase
from sqlalchemy import Engine, insert, select
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.clock import utcnow
from boardwatch.core.settings import Settings
from boardwatch.providers.base import BoardHealth
from boardwatch.scan.coordinator import run_scan
from boardwatch.store import tables

runner = CliRunner()


def _settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1)


def _add_company(engine: Engine, slug: str, provider: str = "greenhouse") -> int:
    with engine.begin() as conn:
        result = conn.execute(
            insert(tables.companies).values(
                name=slug.title(), provider=provider, slug=slug,
                source="user", watched=True,
            )
        )
        return int(result.inserted_primary_key[0])


def _scan_rows(engine: Engine, company_id: int) -> list[Any]:
    with engine.connect() as conn:
        return list(
            conn.execute(
                select(tables.board_scans)
                .where(tables.board_scans.c.company_id == company_id)
                .order_by(tables.board_scans.c.id)
            ).all()
        )


def _posting(engine: Engine, company_id: int) -> Any:
    with engine.connect() as conn:
        return conn.execute(
            select(tables.postings).where(tables.postings.c.company_id == company_id)
        ).one()


def test_validator_round_trip_across_scans(
    engine: Engine, tmp_path: Path, case: ProviderCase
) -> None:
    _add_company(engine, "acme", case.name)
    url = case.board_url()
    settings = _settings(tmp_path)
    with respx.mock:
        respx.get(url).mock(
            return_value=httpx.Response(
                200, content=case.wrap(case.jobs()[:2]), headers={"ETag": 'W/"rt1"'}
            )
        )
        first = run_scan(engine, settings)
    assert first.complete == 1
    with respx.mock:
        route = respx.get(url).mock(return_value=httpx.Response(304))
        second = run_scan(engine, settings)
    # the validators persisted by the complete apply are attached to the NEXT
    # scan's BoardRequest for the same canonical URL (D22 round trip)
    assert route.calls[0].request.headers["If-None-Match"] == 'W/"rt1"'
    assert second.unchanged == 1


def test_stale_validator_triggers_unconditional_refetch(
    engine: Engine, tmp_path: Path, case: ProviderCase
) -> None:
    """A validator older than validator_max_age_hours is dropped: the next scan refetches
    unconditionally (no If-None-Match) rather than trusting a possibly-stale upstream ETag
    forever, which would otherwise yield silent 304s and permanently frozen postings."""
    _add_company(engine, "acme", case.name)
    url = case.board_url()
    settings = _settings(tmp_path)
    with respx.mock:
        respx.get(url).mock(
            return_value=httpx.Response(
                200, content=case.wrap(case.jobs()[:2]), headers={"ETag": 'W/"rt1"'}
            )
        )
        first = run_scan(engine, settings)
    assert first.complete == 1
    # Age the stored validator just past the TTL, then rescan.
    with engine.begin() as conn:
        conn.execute(
            tables.http_cache.update()
            .where(tables.http_cache.c.url == url)
            .values(fetched_at=utcnow() - timedelta(hours=settings.validator_max_age_hours + 1))
        )
    with respx.mock:
        route = respx.get(url).mock(
            return_value=httpx.Response(
                200, content=case.wrap(case.jobs()[:2]), headers={"ETag": 'W/"rt2"'}
            )
        )
        second = run_scan(engine, settings)
    assert "If-None-Match" not in route.calls[0].request.headers
    assert second.complete == 1  # refetched as a full inventory, not `unchanged`


def test_d_company_filtered_scan_touches_only_that_board(
    engine: Engine, tmp_path: Path, case: ProviderCase
) -> None:
    acme_url = case.board_url()
    globex_url = case.provider.board_url("globex")
    acme_id = _add_company(engine, "acme", case.name)
    globex_id = _add_company(engine, "globex", case.name)
    settings = _settings(tmp_path)
    with respx.mock:  # scan 1: one posting on each board
        respx.get(acme_url).mock(return_value=httpx.Response(200, content=case.wrap(case.jobs()[:1])))
        respx.get(globex_url).mock(return_value=httpx.Response(200, content=case.wrap(case.jobs()[:1])))
        run_scan(engine, settings)
    with respx.mock:  # scan 2: both boards empty -> both postings at miss 1
        respx.get(acme_url).mock(return_value=httpx.Response(200, content=case.empty_body()))
        respx.get(globex_url).mock(return_value=httpx.Response(200, content=case.empty_body()))
        run_scan(engine, settings)
    assert _posting(engine, acme_id).consecutive_missing == 1
    assert _posting(engine, globex_id).consecutive_missing == 1

    with respx.mock:  # scan 3: --company acme ONLY; globex route unmocked on purpose:
        respx.get(acme_url).mock(return_value=httpx.Response(200, content=case.empty_body()))
        summary = run_scan(engine, settings, company="acme")
        # respx raises on any unmocked request, so touching globex fails loudly

    assert summary.companies == 1
    assert _posting(engine, acme_id).status == "closed"
    globex_posting = _posting(engine, globex_id)
    assert globex_posting.status == "open"  # no closure side effects on other boards
    assert globex_posting.consecutive_missing == 1  # no counter side effects either
    assert len(_scan_rows(engine, globex_id)) == 2  # no third scan row for globex


def test_failure_isolation_one_failed_board_never_blocks_others(
    engine: Engine, tmp_path: Path, case: ProviderCase
) -> None:
    acme_url = case.board_url()
    globex_url = case.provider.board_url("globex")
    acme_id = _add_company(engine, "acme", case.name)
    globex_id = _add_company(engine, "globex", case.name)
    with respx.mock:
        respx.get(acme_url).mock(return_value=httpx.Response(500))
        respx.get(globex_url).mock(return_value=httpx.Response(200, content=case.wrap(case.jobs()[:2])))
        summary = run_scan(engine, _settings(tmp_path))
    assert summary.failed == 1
    assert summary.complete == 1
    assert summary.errors and "acme" in summary.errors[0]
    assert _scan_rows(engine, acme_id)[-1].status == "failed"
    assert _scan_rows(engine, globex_id)[-1].status == "complete"
    with engine.connect() as conn:
        run_row = conn.execute(select(tables.runs)).one()
    assert run_row.finished_at is not None  # the run still finalizes
    assert run_row.boards_attempted == 2


def test_apply_failure_on_one_board_never_aborts_the_scan(
    engine: Engine, tmp_path: Path, case: ProviderCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A board whose apply_board raises (a data quirk hitting a DB constraint, as the duplicate
    Workable shortcode did) must cost that board its reach and be counted failed — never abort the
    whole run. The fetch path already isolates per board; the apply call did not, so one bad board
    took every other board's results down with it."""
    from boardwatch.scan import coordinator

    acme_url = case.board_url()
    globex_url = case.provider.board_url("globex")
    acme_id = _add_company(engine, "acme", case.name)
    _add_company(engine, "globex", case.name)
    real_apply = coordinator.apply_board

    def flaky_apply(engine_: Engine, snapshot: Any, company_id: int, run_id: int) -> Any:
        if company_id == acme_id:
            raise RuntimeError("boom in apply")
        return real_apply(engine_, snapshot, company_id, run_id)

    monkeypatch.setattr(coordinator, "apply_board", flaky_apply)
    with respx.mock:
        respx.get(acme_url).mock(return_value=httpx.Response(200, content=case.wrap(case.jobs()[:2])))
        respx.get(globex_url).mock(return_value=httpx.Response(200, content=case.wrap(case.jobs()[:2])))
        summary = run_scan(engine, _settings(tmp_path))  # must NOT raise
    assert summary.failed == 1
    assert summary.complete == 1
    assert summary.errors and "acme" in summary.errors[0]
    with engine.connect() as conn:
        run_row = conn.execute(select(tables.runs)).one()
    assert run_row.finished_at is not None  # the run still finalizes despite the apply failure
    assert run_row.boards_attempted == 2


def test_scan_cli_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: ProviderCase) -> None:
    # Rich force-enables terminal rendering when it detects GitHub Actions,
    # injecting ANSI styling that splits the literal option tokens this test
    # asserts on. Neutralize the detection so help renders plainly everywhere.
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    data_dir = tmp_path / "data"
    help_result = runner.invoke(app, ["scan", "--help"])
    assert help_result.exit_code == 0
    assert "--company" in help_result.stdout and "--provider" in help_result.stdout

    from boardwatch.store.db import ensure_schema, get_engine

    engine = get_engine(data_dir)
    ensure_schema(engine)
    _add_company(engine, "acme", case.name)
    with respx.mock:
        respx.get(case.board_url()).mock(return_value=httpx.Response(200, content=case.wrap(case.jobs()[:2])))
        result = runner.invoke(app, ["--data-dir", str(data_dir), "scan"])
    assert result.exit_code == 0
    assert "Scanned 1 companies" in result.stdout
    assert "open postings" in result.stdout
    assert "boardwatch top" in result.stdout


def test_coordinator_passes_known_posting_ids_after_first_scan(
    engine: Engine, tmp_path: Path
) -> None:
    """Second scan of the same board must carry the ids stored by the first, and the
    configured (non-default) detail_fetch_budget must reach the provider both scans (H6)."""
    seen: list[frozenset[str]] = []
    budgets: list[int] = []

    class _Recorder:
        name = "greenhouse"
        board_hosts = ("boards.greenhouse.io",)

        def board_url(self, slug: str) -> str:
            return (
                f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
                "?content=true&pay_transparency=true"
            )

        def fetch_board(self, fetcher: Any, request: Any) -> Any:
            seen.append(request.known_posting_ids)
            budgets.append(request.detail_budget)
            return snapshot_for(gh_jobs()[:1])

        def healthcheck(self, fetcher: Any, slug: str) -> BoardHealth:
            return BoardHealth.OK

    _add_company(engine, "acme", "greenhouse")
    settings = Settings(
        data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1, detail_fetch_budget=7
    )
    providers = {"greenhouse": _Recorder()}

    run_scan(engine, settings, providers=providers)
    run_scan(engine, settings, providers=providers)

    assert seen[0] == frozenset()
    assert seen[1], "second scan must know the posting stored by the first"
    assert budgets == [7, 7]


def test_a_systemic_outage_records_WHY_the_run_failed(  # noqa: N802
    engine: Engine, tmp_path: Path
) -> None:
    """Run 132's exact shape: one board attempted, it came back `partial`, none completed.

    `partial` is counted neither complete nor failed, so the per-board error line that
    explains an ordinary bad scan is never written — the row was stamped `failed` with
    `errors_json = []`, and the only account of the outage lived in a console log that
    scrolled away. A `failed` run nobody can diagnose two weeks later is the whole failure
    this closes, and this is the standalone caller: it owns the terminal status here, so it
    owns the reason too.
    """
    _add_company(engine, "acme", "greenhouse")
    # One job that parses and one that cannot. Greenhouse reports `partial` for a board that
    # still yielded SOME postings, which is what makes this the empty-error-list case rather
    # than the `failed` one the sibling tests above already cover.
    payload = json.dumps({"jobs": [gh_jobs()[0], {"id": 999}]}).encode()
    with respx.mock:
        respx.get(BOARD_URL).mock(return_value=httpx.Response(200, content=payload))
        summary = run_scan(engine, _settings(tmp_path))

    assert (summary.companies, summary.complete, summary.unchanged) == (1, 0, 0), (
        f"guard: not the outage shape, so this test proves nothing: {summary}"
    )
    assert summary.partial == 1, f"guard: the board did not come back partial: {summary}"
    assert summary.failed == 0, "guard: a failed board would write its own error line"
    with engine.connect() as conn:
        row = conn.execute(select(tables.runs.c.status, tables.runs.c.errors_json)).one()
    assert row.status == "failed", "guard: the outage was not classified fatal"
    assert any("systemic scan outage" in note for note in (row.errors_json or [])), (
        f"the run recorded failed with no reason at all: {row.errors_json}"
    )
