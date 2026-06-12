"""Coordinator round-trip, state test d, failure isolation, CLI smoke."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from gh_fixtures import FIXTURES, gh_jobs
from sqlalchemy import Engine, insert, select
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.settings import Settings
from boardwatch.providers.greenhouse import GreenhouseProvider
from boardwatch.scan.coordinator import run_scan
from boardwatch.store import tables

runner = CliRunner()
ACME_URL = GreenhouseProvider().board_url("acme")
GLOBEX_URL = GreenhouseProvider().board_url("globex")
EMPTY = (FIXTURES / "empty.json").read_bytes()


def _settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1)


def _add_company(engine: Engine, slug: str) -> int:
    with engine.begin() as conn:
        result = conn.execute(
            insert(tables.companies).values(
                name=slug.title(), provider="greenhouse", slug=slug,
                source="user", watched=True,
            )
        )
        return int(result.inserted_primary_key[0])


def _board_payload(n_jobs: int) -> bytes:
    return json.dumps({"jobs": gh_jobs()[:n_jobs]}).encode()


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


def test_validator_round_trip_across_scans(engine: Engine, tmp_path: Path) -> None:
    _add_company(engine, "acme")
    settings = _settings(tmp_path)
    with respx.mock:
        respx.get(ACME_URL).mock(
            return_value=httpx.Response(
                200, content=_board_payload(2), headers={"ETag": 'W/"rt1"'}
            )
        )
        first = run_scan(engine, settings)
    assert first.complete == 1
    with respx.mock:
        route = respx.get(ACME_URL).mock(return_value=httpx.Response(304))
        second = run_scan(engine, settings)
    # the validators persisted by the complete apply are attached to the NEXT
    # scan's BoardRequest for the same canonical URL (D22 round trip)
    assert route.calls[0].request.headers["If-None-Match"] == 'W/"rt1"'
    assert second.unchanged == 1


def test_d_company_filtered_scan_touches_only_that_board(
    engine: Engine, tmp_path: Path
) -> None:
    acme_id = _add_company(engine, "acme")
    globex_id = _add_company(engine, "globex")
    settings = _settings(tmp_path)
    with respx.mock:  # scan 1: one posting on each board
        respx.get(ACME_URL).mock(return_value=httpx.Response(200, content=_board_payload(1)))
        respx.get(GLOBEX_URL).mock(return_value=httpx.Response(200, content=_board_payload(1)))
        run_scan(engine, settings)
    with respx.mock:  # scan 2: both boards empty -> both postings at miss 1
        respx.get(ACME_URL).mock(return_value=httpx.Response(200, content=EMPTY))
        respx.get(GLOBEX_URL).mock(return_value=httpx.Response(200, content=EMPTY))
        run_scan(engine, settings)
    assert _posting(engine, acme_id).consecutive_missing == 1
    assert _posting(engine, globex_id).consecutive_missing == 1

    with respx.mock:  # scan 3: --company acme ONLY; globex route unmocked on purpose:
        respx.get(ACME_URL).mock(return_value=httpx.Response(200, content=EMPTY))
        summary = run_scan(engine, settings, company="acme")
        # respx raises on any unmocked request, so touching globex fails loudly

    assert summary.companies == 1
    assert _posting(engine, acme_id).status == "closed"
    globex_posting = _posting(engine, globex_id)
    assert globex_posting.status == "open"  # no closure side effects on other boards
    assert globex_posting.consecutive_missing == 1  # no counter side effects either
    assert len(_scan_rows(engine, globex_id)) == 2  # no third scan row for globex


def test_failure_isolation_one_failed_board_never_blocks_others(
    engine: Engine, tmp_path: Path
) -> None:
    acme_id = _add_company(engine, "acme")
    globex_id = _add_company(engine, "globex")
    with respx.mock:
        respx.get(ACME_URL).mock(return_value=httpx.Response(500))
        respx.get(GLOBEX_URL).mock(return_value=httpx.Response(200, content=_board_payload(2)))
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


def test_scan_cli_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    _add_company(engine, "acme")
    with respx.mock:
        respx.get(ACME_URL).mock(return_value=httpx.Response(200, content=_board_payload(2)))
        result = runner.invoke(app, ["--data-dir", str(data_dir), "scan"])
    assert result.exit_code == 0
    assert "Scanned 1 companies" in result.stdout
    assert "open postings" in result.stdout
