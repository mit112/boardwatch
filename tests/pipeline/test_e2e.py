"""Hermetic P0 e2e (§8 DoD): init -> scan -> top -> show on recorded fixtures,
including a fixture-driven second scan exercising 304 -> unchanged. This test
is the 304 gate; the live second scan in the PR transcript is informational
only (the upstream board may legitimately change between scans)."""

import json
from pathlib import Path

import httpx
import pytest
import respx
from gh_fixtures import BOARD_URL, FIXTURES
from sqlalchemy import select
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.store import tables
from boardwatch.store.db import get_engine

runner = CliRunner()

INIT_INPUT = (
    "acme\n"
    "Backend engineer: Python, Go, PostgreSQL, Kubernetes, AWS.\n"
    "Backend Engineer\n"
    "\n"
    "\n"
    "n\n"
)


def test_e2e_vertical_slice_with_304_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    data_dir = tmp_path / "data"
    headers = json.loads((FIXTURES / "normal_response_headers.json").read_text())
    base = ["--data-dir", str(data_dir)]

    assert runner.invoke(app, [*base, "init"], input=INIT_INPUT).exit_code == 0

    with respx.mock:
        respx.get(BOARD_URL).mock(
            return_value=httpx.Response(
                200,
                content=(FIXTURES / "normal.json").read_bytes(),
                headers={"ETag": headers["etag"], "Last-Modified": headers["last_modified"]},
            )
        )
        scan1 = runner.invoke(app, [*base, "scan"])
    assert scan1.exit_code == 0
    assert "complete 1" in scan1.stdout

    top_result = runner.invoke(app, [*base, "top"])
    assert top_result.exit_code == 0

    engine = get_engine(data_dir)
    with engine.connect() as conn:
        posting_id = conn.execute(
            select(tables.postings.c.id).where(tables.postings.c.status == "open")
        ).scalars().first()
    assert posting_id is not None
    show_result = runner.invoke(app, [*base, "show", str(posting_id)])
    assert show_result.exit_code == 0
    # an explainable, multi-component breakdown:
    assert "skill_coverage" in show_result.stdout
    assert "recency" in show_result.stdout
    assert "Score" in show_result.stdout

    # ---- second scan: the 304 -> unchanged gate ----
    with respx.mock:
        route = respx.get(BOARD_URL).mock(return_value=httpx.Response(304))
        scan2 = runner.invoke(app, [*base, "scan"])
    assert scan2.exit_code == 0
    assert route.calls[0].request.headers["If-None-Match"] == headers["etag"]
    assert "unchanged 1" in scan2.stdout
    with engine.connect() as conn:
        statuses = list(
            conn.execute(
                select(tables.board_scans.c.status).order_by(tables.board_scans.c.id)
            ).scalars()
        )
    assert statuses == ["complete", "unchanged"]
