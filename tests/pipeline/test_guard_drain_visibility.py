"""T334 (D-705) through `run_pipeline` and `boardwatch run`: the drain is reached and observable.

`tests/unit/test_guard_drain.py` pins what the streak and the budget decide. What it cannot see is
whether a REAL scan writes the flag the sweep reads, whether the sweep is handed tonight's run, and
whether the numbers reach the funnel artifact and the run log beside the guard's own line, which
is where an operator reading the nightly output looks. So this runs the real scan, the real
sweep and the real CLI, with thirteen guarded nights already on the board's record: tonight's scan
is the fourteenth.

Never the network: every route is mocked (the posting's URL included), and the URL prober asks it
exactly as production would.
"""

from __future__ import annotations

import json
from datetime import datetime, time, timedelta
from pathlib import Path

import httpx
import pytest
import respx
from rich.console import Console
from sqlalchemy import insert, select, update

from boardwatch.core.clock import utcnow
from boardwatch.core.settings import load_settings
from boardwatch.pipeline.liveness import build_prober
from boardwatch.pipeline.runner import run_pipeline
from boardwatch.providers.registry import build_providers
from boardwatch.store import tables
from boardwatch.store.db import get_engine
from tests.pipeline.test_pipeline_run import _GH, _cli, _ready

_LEVER = build_providers()["lever"]
_POSTING_URL = "https://example.test/j"

# The owner's ruling, written out so a changed constant cannot move the boundary with it.
NIGHTS = 14


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _make_acme2_a_lever_board_guarded_for(data_dir: Path, nights: int) -> int:
    """`_ready` seeds `acme2` as a watched Greenhouse board with one open posting. Moves it to
    Lever (a provider the URL probe can judge) and gives it `nights` earlier guarded pipeline
    scans, one a day, on runs that finished OK."""
    engine = get_engine(data_dir)
    with engine.begin() as conn:
        company_id = int(
            conn.execute(
                select(tables.companies.c.id).where(tables.companies.c.slug == "acme2")
            ).scalar_one()
        )
        conn.execute(
            update(tables.companies)
            .where(tables.companies.c.id == company_id)
            .values(provider="lever")
        )
        for ago in range(nights, 0, -1):
            started = datetime.combine(utcnow().date() - timedelta(days=ago), time(10, 0))
            run_id = int(
                conn.execute(
                    insert(tables.runs).values(
                        started_at=started, finished_at=started + timedelta(minutes=5),
                        status="ok", boards_attempted=1,
                    )
                ).inserted_primary_key[0]
            )
            conn.execute(
                insert(tables.board_scans).values(
                    run_id=run_id, company_id=company_id, started_at=started,
                    finished_at=started, status="complete", postings_listed=0,
                    pipeline_scan=True, scan_kind="board", empty_guarded=True,
                )
            )
    return company_id


def _mock_the_boards() -> None:
    respx.get(_GH.board_url("acme")).mock(
        return_value=httpx.Response(200, content=b'{"jobs": []}')
    )
    respx.get(_LEVER.board_url("acme2")).mock(return_value=httpx.Response(200, content=b"[]"))
    respx.get(_POSTING_URL).mock(return_value=httpx.Response(200, text="ok"))


@pytest.mark.usefixtures("no_real_sleep")
def test_a_real_scan_writes_the_flag_and_the_fourteenth_night_hands_the_posting_over(
    env: Path, tmp_path: Path
) -> None:
    _ready(env)
    company_id = _make_acme2_a_lever_board_guarded_for(env, NIGHTS - 1)
    settings = load_settings(data_dir=env)
    with respx.mock:
        _mock_the_boards()
        summary = run_pipeline(
            get_engine(env),
            settings,
            console=Console(quiet=True),
            out_root=tmp_path / "apps",
            resume_path=settings.config_dir / "resume.yaml",
            liveness_prober=build_prober(settings),
            listing_prober=None,
        )

    assert summary.scan_empty_complete_guarded == ["acme2"], "the guard did not fire tonight"
    with get_engine(env).connect() as conn:
        tonight = conn.execute(
            select(tables.board_scans.c.empty_guarded, tables.board_scans.c.pipeline_scan)
            .where(
                tables.board_scans.c.company_id == company_id,
                tables.board_scans.c.run_id == summary.run_id,
            )
        ).one()
    assert tuple(tonight) == (True, True)

    probe = summary.death_probe
    assert probe is not None
    assert (probe.guard_boards, probe.guard_rows, probe.guard_attempted) == (1, 1, 1)
    assert (probe.guard_rows_unjudgeable, probe.guard_closed) == (0, 0)
    assert summary.funnel is not None
    # Read off the WRITTEN artifact, not `summary` again.
    block = json.loads(summary.funnel.json_path.read_text(encoding="utf-8"))["death_probe"]
    assert (block["guard_boards"], block["guard_rows"], block["guard_attempted"]) == (1, 1, 1)
    assert "guard drain: 1 watched board(s)" in summary.funnel.markdown_path.read_text(
        encoding="utf-8"
    )


@pytest.mark.usefixtures("no_real_sleep")
def test_the_thirteenth_night_hands_nothing_over(env: Path, tmp_path: Path) -> None:
    """The boundary, through the real scan: one earlier guarded night fewer, so tonight is 13th."""
    _ready(env)
    _make_acme2_a_lever_board_guarded_for(env, NIGHTS - 2)
    settings = load_settings(data_dir=env)
    with respx.mock:
        _mock_the_boards()
        summary = run_pipeline(
            get_engine(env),
            settings,
            console=Console(quiet=True),
            out_root=tmp_path / "apps",
            resume_path=settings.config_dir / "resume.yaml",
            liveness_prober=build_prober(settings),
            listing_prober=None,
        )

    assert summary.scan_empty_complete_guarded == ["acme2"]
    assert summary.death_probe is not None
    assert (summary.death_probe.guard_boards, summary.death_probe.guard_attempted) == (0, 0)


@pytest.mark.usefixtures("no_real_sleep")
def test_the_run_log_prints_the_drain_beside_the_guard_line(env: Path, tmp_path: Path) -> None:
    _ready(env)
    _make_acme2_a_lever_board_guarded_for(env, NIGHTS - 1)
    with respx.mock:
        _mock_the_boards()
        result = _cli(env, ["run", "--out", str(tmp_path / "apps")])

    assert result.exit_code == 0, result.output
    # The console wraps at its own width, so compare the flattened text: what is pinned is that
    # the drain's line FOLLOWS the guard's own, not where the terminal breaks it.
    flat = " ".join(result.output.split())
    assert (
        "! 1 empty-complete guarded (acme2) "
        f"drain: 1 past {NIGHTS} nights · 1 open rows handed to the death probe "
        "(1 asked, 0 closed) · 0 Ashby/Greenhouse rows stay open"
    ) in flat, result.output
