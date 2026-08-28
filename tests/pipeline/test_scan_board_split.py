"""The scan block's four-way board split, as a REAL `boardwatch run` writes it.

`ScanSummary` sorts every attempted board into exactly one of `complete | partial | failed |
unchanged`, and the funnel published three of them. Live run 126 read "346 boards attempted ·
166 complete · 1 failed", which invites the reading that 179 boards silently did nothing; they
were 39 `partial` (a detail budget truncated them) and 140 `unchanged` (HTTP 304). Two buckets
dropped, so the published numbers could not be reconciled to the total by any reader of the
artifact — the same collapse the keystone invariant forbids elsewhere.

Pinned END TO END rather than on the pure builder, because the buckets were dropped at the
WIRING: `ScanSummary` carried all four the whole time and `runner._emit_funnel` forwarded two.
A test that hands `ScanContext` its own numbers would go green against a pipeline that never
populates them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from rich.console import Console
from sqlalchemy import insert, select

from boardwatch.core.settings import load_settings
from boardwatch.pipeline.runner import run_pipeline
from boardwatch.providers.registry import build_providers
from boardwatch.scan.coordinator import run_scan
from boardwatch.store import tables
from boardwatch.store.db import get_engine
from tests.pipeline.test_pipeline_run import SEEDED_BOARDS, _ready

_GH = build_providers()["greenhouse"]

# One board per outcome. `acme`/`acme2` are the two boards `_ready` leaves watched.
_COMPLETE, _FAILED = SEEDED_BOARDS
_PARTIAL = "half"
_UNCHANGED = "same"

_GOOD_JOB: dict[str, Any] = {
    "id": 1,
    "title": "Backend Engineer",
    "absolute_url": "https://example.test/j/1",
    "content": "&lt;p&gt;Python and PostgreSQL services.&lt;/p&gt;",
}
# `parse_job` raises on an empty title, so this job fails to parse while the one above does
# not — which is exactly the `partial` branch: some postings survived, some did not.
_BAD_JOB: dict[str, Any] = {"id": 2, "title": ""}


def _body(*jobs: dict[str, Any]) -> bytes:
    return json.dumps({"jobs": list(jobs)}).encode()


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _watch(data_dir: Path, slug: str) -> None:
    with get_engine(data_dir).begin() as conn:
        conn.execute(
            insert(tables.companies).values(
                name=slug.title(), provider="greenhouse", slug=slug, source="user", watched=True
            )
        )


def test_the_funnel_publishes_all_four_board_outcomes_and_they_sum_to_the_total(
    env: Path, tmp_path: Path
) -> None:
    """One board per outcome, so no bucket can hide inside another's count.

    Against the three-way artifact this fails twice over: `boards_partial` and
    `boards_unchanged` are absent entirely, and 1 complete + 1 failed cannot be reconciled
    against 4 attempted by anything a reader of the artifact can do.
    """
    _ready(env)
    _watch(env, _PARTIAL)
    _watch(env, _UNCHANGED)
    settings = load_settings(data_dir=env)

    # Prime the unchanged board's validator with a cheap company-filtered scan, so the run
    # under test sends `If-None-Match` and earns a real 304 rather than a simulated one.
    with respx.mock:
        respx.get(_GH.board_url(_UNCHANGED)).mock(
            return_value=httpx.Response(200, content=_body(), headers={"ETag": 'W/"v1"'})
        )
        assert run_scan(get_engine(env), settings, company=_UNCHANGED).complete == 1

    with respx.mock:
        respx.get(_GH.board_url(_COMPLETE)).mock(
            return_value=httpx.Response(200, content=_body(_GOOD_JOB))
        )
        respx.get(_GH.board_url(_FAILED)).mock(return_value=httpx.Response(500))
        respx.get(_GH.board_url(_PARTIAL)).mock(
            return_value=httpx.Response(200, content=_body(_GOOD_JOB, _BAD_JOB))
        )
        respx.get(_GH.board_url(_UNCHANGED)).mock(return_value=httpx.Response(304))
        summary = run_pipeline(
            get_engine(env),
            settings,
            console=Console(quiet=True),
            out_root=tmp_path / "apps",
            resume_path=settings.config_dir / "resume.yaml",
        )

    assert summary.funnel is not None
    scan = json.loads(summary.funnel.json_path.read_text(encoding="utf-8"))["scan"]

    assert scan["boards_attempted"] == 4
    assert scan["boards_complete"] == 1
    assert scan["boards_partial"] == 1
    assert scan["boards_unchanged"] == 1
    assert scan["boards_failed"] == 1
    total = (
        scan["boards_complete"]
        + scan["boards_partial"]
        + scan["boards_unchanged"]
        + scan["boards_failed"]
    )
    assert total == scan["boards_attempted"]
    assert scan["boards_reconciled"] is True

    rendered = summary.funnel.markdown_path.read_text(encoding="utf-8")
    assert "4 boards attempted · 1 complete · 1 partial · 1 unchanged · 1 failed" in rendered

    # The same split must reach the STORE, not only the artifact: the runs row carried just
    # complete/attempted, so /api/runs and the web run list inherited the identical fold. This
    # is the latest run (the priming company-filtered scan is an earlier, smaller row).
    with get_engine(env).connect() as conn:
        run_row = conn.execute(
            select(tables.runs).order_by(tables.runs.c.id.desc()).limit(1)
        ).one()
    assert run_row.boards_attempted == 4
    assert run_row.boards_complete == 1
    assert run_row.boards_partial == 1
    assert run_row.boards_unchanged == 1
    assert run_row.boards_failed == 1
