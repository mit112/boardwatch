"""Coordinator round-trip, state test d, failure isolation, CLI smoke."""

from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from provider_cases import ProviderCase
from sqlalchemy import Engine, insert, select
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.settings import Settings
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
