"""A provider that raises from board_url() or healthcheck() must cost one board, not the
whole run. Workday is the first provider whose board_url can raise (a malformed stored
host/tenant/site triple), which makes both of these paths live for the first time."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, insert

from boardwatch.core.models import BoardRequest, BoardSnapshot
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.providers.base import BoardHealth
from boardwatch.scan.coordinator import run_scan
from boardwatch.scan.health import probe_health
from boardwatch.store import tables


class _RaisingProvider:
    name = "raisey"
    board_hosts: tuple[str, ...] = ()

    def board_url(self, slug: str) -> str:
        raise ValueError("expected host/tenant/site")

    def fetch_board(self, fetcher: Fetcher, request: BoardRequest) -> BoardSnapshot:
        raise AssertionError("must not be reached")

    def healthcheck(self, fetcher: Fetcher, slug: str) -> BoardHealth:
        raise ValueError("expected host/tenant/site")


class _HealthyProvider:
    """A stand-in for a normal, working provider — no real HTTP involved."""

    name = "greenhouse"
    board_hosts: tuple[str, ...] = ("boards.greenhouse.io",)

    def board_url(self, slug: str) -> str:
        return f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"

    def fetch_board(self, fetcher: Fetcher, request: BoardRequest) -> BoardSnapshot:
        return BoardSnapshot(
            status="complete", postings=[], url=request.url,
            observed_validators=None, error=None,
        )

    def healthcheck(self, fetcher: Fetcher, slug: str) -> BoardHealth:
        return BoardHealth.OK


def _add_company(engine: Engine, slug: str, provider: str) -> int:
    with engine.begin() as conn:
        result = conn.execute(
            insert(tables.companies).values(
                name=slug.title(), provider=provider, slug=slug,
                source="user", watched=True,
            )
        )
        return int(result.inserted_primary_key[0])


def test_board_url_failure_is_one_board_not_the_run(engine: Engine, tmp_path: Path) -> None:
    _add_company(engine, "bad-slug", "raisey")
    _add_company(engine, "acme", "greenhouse")
    settings = Settings(data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1)
    providers = {"raisey": _RaisingProvider(), "greenhouse": _HealthyProvider()}

    summary = run_scan(engine, settings, providers=providers)

    assert summary.failed == 1
    assert any("expected host/tenant/site" in e for e in summary.errors)
    assert summary.complete == 1  # the healthy board still scanned


def test_healthcheck_failure_maps_to_error_not_a_traceback(engine: Engine, tmp_path: Path) -> None:
    _add_company(engine, "bad-slug", "raisey")
    settings = Settings(data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1)

    report = probe_health(engine, settings, providers={"raisey": _RaisingProvider()})

    assert report.board_health["raisey:bad-slug"] is BoardHealth.ERROR
