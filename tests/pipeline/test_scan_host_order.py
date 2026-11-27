"""T360: the scan dispatches hosts by the busy time the last complete pipeline scan recorded.

Run through the real scan and a fake transport (respx), one worker, so the request order IS the
dispatch order. Six boards on three hosts: Greenhouse 3, Ashby 2, Lever 1, so today's order is
Greenhouse, Ashby, Lever. The Lever board stands for a one-board host whose chain is long.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from rich.console import Console
from sqlalchemy import event, insert, select
from sqlalchemy.exc import OperationalError

from boardwatch.core.clock import utcnow
from boardwatch.core.politeness import Fetcher, HostCost
from boardwatch.core.settings import Settings, load_settings
from boardwatch.providers.registry import build_providers
from boardwatch.scan import apply as apply_module  # noqa: F401  (patched through coordinator)
from boardwatch.scan import coordinator
from boardwatch.scan.coordinator import run_scan
from boardwatch.store import tables
from boardwatch.store.app_state import get_host_busy, set_host_busy
from boardwatch.store.db import ensure_schema, get_engine

pytestmark = pytest.mark.usefixtures("no_real_sleep")

_PROVIDERS = build_providers()
BOARDS = (
    ("gh-a", "greenhouse"), ("gh-b", "greenhouse"), ("gh-c", "greenhouse"),
    ("ab-a", "ashby"), ("ab-b", "ashby"),
    ("lv-a", "lever"),
)
GH, AB, LV = "boards-api.greenhouse.io", "api.ashbyhq.com", "api.lever.co"
#: Another run's id, planted with a record so a scan that does NOT write leaves it standing.
PRIOR_RUN = 4242


def _body(provider: str, slug: str) -> bytes:
    ids = [f"{slug}-1", f"{slug}-2"]
    if provider == "lever":
        return json.dumps([
            {"id": i, "text": f"Backend Engineer {i}", "hostedUrl": f"https://x.test/{i}",
             "descriptionPlain": "Python services."} for i in ids
        ]).encode()
    return json.dumps({"jobs": [
        {"id": i, "title": f"Backend Engineer {i}", "absolute_url": f"https://x.test/{i}",
         "jobUrl": f"https://x.test/{i}", "content": "Python services.",
         "descriptionHtml": "<p>Python services.</p>"} for i in ids
    ]}).encode()


@contextmanager
def _transport(log: list[str], *, status: int = 200) -> Iterator[None]:
    def recorder(slug: str, content: bytes) -> Callable[[httpx.Request], httpx.Response]:
        def respond(_: httpx.Request) -> httpx.Response:
            log.append(slug)
            return httpx.Response(status, content=content if status == 200 else b"")
        return respond

    with respx.mock(assert_all_called=False) as mock:
        for slug, provider in BOARDS:
            mock.get(_PROVIDERS[provider].board_url(slug)).mock(
                side_effect=recorder(slug, _body(provider, slug))
            )
        yield


def _settings(data: Path) -> Settings:
    return load_settings(data_dir=data).model_copy(update={"scan_workers": 1})


def _store(data: Path, *, record: dict[str, float] | None = None) -> Any:
    engine = get_engine(data)
    ensure_schema(engine)
    with engine.begin() as conn:
        for slug, provider in BOARDS:
            conn.execute(insert(tables.companies).values(
                name=slug, provider=provider, slug=slug, source="user", watched=True
            ))
        conn.execute(insert(tables.profile).values(
            text="Backend engineer.", exclude_titles_json=[], updated_at=utcnow()
        ))
        if record is not None:
            set_host_busy(conn, PRIOR_RUN, record)
    return engine


def _outcome(engine: Any) -> list[tuple[Any, ...]]:
    """What each board's scan produced: its status and the postings it stored."""
    with engine.connect() as conn:
        boards = conn.execute(
            select(tables.companies.c.slug, tables.board_scans.c.status)
            .join(tables.companies, tables.companies.c.id == tables.board_scans.c.company_id)
            .order_by(tables.companies.c.slug)
        ).all()
        stored = conn.execute(
            select(tables.companies.c.slug, tables.postings.c.provider_posting_id,
                   tables.postings.c.title)
            .join(tables.companies, tables.companies.c.id == tables.postings.c.company_id)
            .order_by(tables.companies.c.slug, tables.postings.c.provider_posting_id)
        ).all()
    return [tuple(r) for r in boards] + [tuple(r) for r in stored]


def test_with_no_record_the_scan_dispatches_by_board_count_and_with_one_it_does_not(
    tmp_path: Path,
) -> None:
    ran_blind: list[str] = []
    blind = _store(tmp_path / "blind")
    with _transport(ran_blind):
        run_scan(blind, _settings(tmp_path / "blind"), finish=False)

    ran_ordered: list[str] = []
    ordered = _store(tmp_path / "ordered", record={LV: 500.0, GH: 4.0, AB: 3.0})
    with _transport(ran_ordered):
        run_scan(ordered, _settings(tmp_path / "ordered"), finish=False)

    # today's order: the deepest host on every refill (the literal comes from the fleet above)
    assert ran_blind == ["gh-a", "gh-b", "gh-c", "ab-a", "ab-b", "lv-a"]
    # the host recorded at 500 s goes first and its chain is run back to back
    assert ran_ordered == ["lv-a", "gh-a", "gh-b", "gh-c", "ab-a", "ab-b"]
    # the order moved and nothing else did: the same boards, statuses and postings
    assert _outcome(ordered) == _outcome(blind)
    assert len(_outcome(blind)) == 6 + 12  # six boards, two postings each: not an empty match


def test_the_run_log_says_where_the_order_came_from(tmp_path: Path) -> None:
    quiet = Console(record=True, width=200)
    engine = _store(tmp_path / "d", record={LV: 500.0})
    with _transport([]):
        run_scan(engine, _settings(tmp_path / "d"), finish=False, console=quiet)
    text = quiet.export_text()
    assert f"scan: host order by busy time of run {PRIOR_RUN} (1 of 3 hosts recorded, 2 new)" in text

    fresh = Console(record=True, width=200)
    engine = _store(tmp_path / "e")
    with _transport([]):
        run_scan(engine, _settings(tmp_path / "e"), finish=False, console=fresh)
    assert "scan: host order by boards per host (no busy-time record; 3 hosts)" in fresh.export_text()


class _PlantedCosts(Fetcher):
    """Reports the costs a scan measured, planted: a span far longer than service plus pacing, as
    for a host that sat idle between requests."""

    costs: dict[str, HostCost] = {}

    def host_costs(self) -> dict[str, HostCost]:
        return self.costs or {
            GH: HostCost(requests=3, service_seconds=5.0, pace_seconds=2.0,
                         first_at=100.0, last_at=5000.0),
            LV: HostCost(requests=1, service_seconds=1.0, pace_seconds=0.5,
                         first_at=200.0, last_at=900.0),
        }


def test_a_pipeline_scan_records_each_hosts_service_plus_pacing_seconds(tmp_path: Path) -> None:
    engine = _store(tmp_path / "d", record={AB: 9.0})
    settings = _settings(tmp_path / "d")
    with _transport([]):
        summary = run_scan(engine, settings, finish=False, fetcher=_PlantedCosts(settings))

    with engine.connect() as conn:
        last = get_host_busy(conn)
    assert last is not None
    # 5.0 + 2.0 and 1.0 + 0.5, not the spans (4,900 s and 700 s), and the old record is replaced
    assert (last.run_id, last.seconds) == (summary.run_id, {GH: 7.0, LV: 1.5})


def test_a_host_with_a_request_still_in_flight_keeps_the_larger_of_its_record_and_its_measure(
    tmp_path: Path,
) -> None:
    """GH's last board ran into its deadline with a request running, so this scan saw 3 s of a
    chain that took 1,700 s last night. LV's chain ended, so its measure replaces its record."""
    engine = _store(tmp_path / "d", record={GH: 1700.0, LV: 500.0})
    settings = _settings(tmp_path / "d")
    fetcher = _PlantedCosts(settings)
    fetcher.costs = {
        GH: HostCost(requests=1, service_seconds=2.0, pace_seconds=1.0, in_flight=1),
        LV: HostCost(requests=1, service_seconds=1.0, pace_seconds=0.5),
        AB: HostCost(requests=1, service_seconds=4.0, pace_seconds=1.0, in_flight=1),
    }
    with _transport([]):
        summary = run_scan(engine, settings, finish=False, fetcher=fetcher)

    with engine.connect() as conn:
        last = get_host_busy(conn)
    assert last is not None
    # AB had no record, so the in-flight merge keeps its measure
    assert (last.run_id, last.seconds) == (summary.run_id, {GH: 1700.0, LV: 1.5, AB: 5.0})


def test_the_configured_per_host_delay_prices_a_host_with_no_record(tmp_path: Path) -> None:
    """At 3.0 s Greenhouse's three boards are priced 9 s, above Lever's recorded 7 s; at the
    default 1.0 s they would be 3 s and Lever would go first."""
    ran: list[str] = []
    engine = _store(tmp_path / "d", record={LV: 7.0})
    settings = _settings(tmp_path / "d").model_copy(update={"per_host_delay_seconds": 3.0})
    with _transport(ran):
        run_scan(engine, settings, finish=False)

    assert ran == ["gh-a", "gh-b", "gh-c", "lv-a", "ab-a", "ab-b"]


def _db_error(what: str) -> OperationalError:
    return OperationalError(what, {}, Exception("database is locked"))


def test_a_store_that_cannot_give_the_record_does_not_stop_the_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def locked(_: Any) -> Any:
        raise _db_error("read host busy")

    monkeypatch.setattr(coordinator, "get_host_busy", locked)
    ran: list[str] = []
    console = Console(record=True, width=200)
    engine = _store(tmp_path / "d", record={LV: 500.0})
    with _transport(ran):
        summary = run_scan(engine, _settings(tmp_path / "d"), finish=False, console=console)

    assert summary.complete == len(BOARDS)
    assert ran == ["gh-a", "gh-b", "gh-c", "ab-a", "ab-b", "lv-a"]  # depth order, the record unread
    assert "host busy-time record not read" in console.export_text()


@pytest.mark.parametrize("where", ["statement", "commit"])
def test_a_store_that_cannot_take_the_record_leaves_the_prior_one_and_the_scan_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, where: str
) -> None:
    engine = _store(tmp_path / "d", record={LV: 500.0})
    real_set = coordinator.set_host_busy
    armed = False

    @event.listens_for(engine, "commit")
    def refuse(_: Any) -> None:
        if armed:
            raise _db_error("commit")

    def failing_set(conn: Any, run_id: int, seconds: Any) -> None:
        nonlocal armed
        if where == "statement":
            raise _db_error("write host busy")
        real_set(conn, run_id, seconds)
        armed = True  # the record's own transaction refuses to commit

    monkeypatch.setattr(coordinator, "set_host_busy", failing_set)
    console = Console(record=True, width=200)
    with _transport([]):
        summary = run_scan(engine, _settings(tmp_path / "d"), finish=False, console=console)

    armed = False
    with engine.connect() as conn:
        last = get_host_busy(conn)
        status = conn.execute(
            select(tables.runs.c.status).where(tables.runs.c.id == summary.run_id)
        ).scalar_one()
    assert last is not None and (last.run_id, last.seconds) == (PRIOR_RUN, {LV: 500.0})
    assert status != "failed" and summary.complete == len(BOARDS)
    assert "host busy-time record not written" in console.export_text()


def _abort_on_second_board(monkeypatch: pytest.MonkeyPatch) -> None:
    real_apply = coordinator.apply_board
    calls = 0

    def interrupt(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        return real_apply(*args, **kwargs)

    monkeypatch.setattr(coordinator, "apply_board", interrupt)


@pytest.mark.parametrize(
    "case", ["standalone", "one provider", "one board", "systemic outage", "continued"]
)
def test_a_scan_that_is_not_a_complete_pipeline_scan_leaves_the_record_standing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    engine = _store(tmp_path / "d", record={LV: 500.0})
    settings = _settings(tmp_path / "d")
    with _transport([], status=500 if case == "systemic outage" else 200):
        if case == "standalone":
            run_scan(engine, settings, finish=True)
        elif case == "one provider":
            run_scan(engine, settings, finish=False, provider="greenhouse")
        elif case == "one board":
            run_scan(engine, settings, finish=False, company="gh-a")
        elif case == "systemic outage":
            run_scan(engine, settings, finish=False)
        else:
            with monkeypatch.context() as patch, pytest.raises(KeyboardInterrupt):
                _abort_on_second_board(patch)
                run_scan(engine, settings, finish=False)
            run_scan(engine, settings, finish=False, continue_scan=True)

    with engine.connect() as conn:
        last = get_host_busy(conn)
    assert last is not None
    assert (last.run_id, last.seconds) == (PRIOR_RUN, {LV: 500.0}), case


def test_the_pipeline_orders_by_the_last_scan_and_the_funnel_shows_when_hosts_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.pipeline.test_pipeline_run import SEEDED_BOARDS, _ready

    data = tmp_path / "data"
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    _ready(data)
    settings = load_settings(data_dir=data).model_copy(update={"scan_workers": 1})
    engine = get_engine(data)
    gh = _PROVIDERS["greenhouse"]

    def night() -> tuple[Any, str]:
        from boardwatch.pipeline.runner import run_pipeline

        console = Console(record=True, width=200)
        with respx.mock:
            for slug in SEEDED_BOARDS:
                respx.get(gh.board_url(slug)).mock(
                    return_value=httpx.Response(200, content=b'{"jobs": []}')
                )
            summary = run_pipeline(
                engine, settings, console=console, out_root=tmp_path / "apps",
                resume_path=settings.config_dir / "resume.yaml",
            )
        return summary, console.export_text()

    first, first_log = night()
    second, second_log = night()

    assert "host order by boards per host (no busy-time record" in first_log
    assert f"host order by busy time of run {first.run_id} " in second_log
    with engine.connect() as conn:
        last = get_host_busy(conn)
    assert last is not None and last.run_id == second.run_id
    assert list(last.seconds) == [GH]
    funnel = json.loads(
        (tmp_path / "apps" / utcnow().date().isoformat() / f"funnel-{second.run_id}.json")
        .read_text()
    )
    (row,) = funnel["scan"]["host_cost"]["rows"]
    assert row["host"] == GH
    assert row["first_request_seconds"] is not None and 0 <= row["first_request_seconds"] < 60  # exact offsets: unit test
