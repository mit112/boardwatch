"""D-669: use pipeline scan evidence, collapse dead alerts, and follow moves only by opt-in."""

from __future__ import annotations

import json
from pathlib import Path
from shlex import join, split

import httpx
import pytest
import respx
from rich.console import Console
from sqlalchemy import Engine, insert, select
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.clock import utcnow
from boardwatch.core.models import BoardSnapshot
from boardwatch.core.settings import Settings, load_settings
from boardwatch.pipeline.death_probe import unreachable_by_the_scanner
from boardwatch.pipeline.runner import PipelineSummary, run_pipeline
from boardwatch.providers.registry import build_providers
from boardwatch.scan.apply import apply_board
from boardwatch.scan.coordinator import run_scan
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import upsert_watch

pytestmark = pytest.mark.usefixtures("no_real_sleep")
_PROVIDERS = build_providers()


@pytest.fixture()
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Engine, Settings]:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    settings = load_settings(data_dir=tmp_path / "data").model_copy(update={"retry_attempts": 1})
    engine = get_engine(settings.data_dir)
    ensure_schema(engine)
    return engine, settings


def _watch(engine: Engine, slug: str, provider: str = "greenhouse") -> None:
    with engine.begin() as conn:
        upsert_watch(conn, provider=provider, slug=slug, name=f"Name {slug}", source="user")


def _run(engine: Engine, settings: Settings, *, skip_scan: bool = False) -> PipelineSummary:
    return run_pipeline(
        engine, settings, console=Console(quiet=True), out_root=settings.data_dir / "out",
        resume_path=settings.config_dir / "resume.yaml", skip_scan=skip_scan,
    )


def _dead_alerts(summary: PipelineSummary) -> list[str]:
    return [e for e in summary.errors if "boards dead for 3+ scans:" in e]


def test_collapse_is_bounded_but_funnel_has_every_dead_board(setup: tuple[Engine, Settings]) -> None:
    engine, settings = setup
    for i in range(12):
        _watch(engine, f"board{i:02}")
    with respx.mock as routes:
        routes.get().respond(404)
        first, second, third = [_run(engine, settings) for _ in range(3)]
        assert len(routes.calls) == 36, "default-off must not probe migration targets"
    assert len(_dead_alerts(third)) == 1
    alert = _dead_alerts(third)[0]
    assert alert == (
        "12 boards dead for 3+ scans: "
        + ", ".join(f"Name board{i:02} (greenhouse:board{i:02})" for i in range(10))
        + "; 2 more; full list in the funnel"
    )
    for summary in (first, second):
        assert not _dead_alerts(summary)
        assert all(any(e.startswith(f"board{i:02}:") for e in summary.errors) for i in range(12))
    assert not any(e.startswith("board") for e in third.errors)
    assert third.scan_boards_failed == 12
    assert third.funnel is not None and third.morning is not None
    funnel = json.loads(third.funnel.json_path.read_text())
    assert funnel["scan"]["dead_boards"] == [
        f"Name board{i:02} (greenhouse:board{i:02})" for i in range(12)
    ]
    rendered = third.funnel.markdown_path.read_text()
    assert all(f"greenhouse:board{i:02}" in rendered for i in range(12))
    assert third.morning.markdown_path.read_text().count(alert) == 1
    with engine.connect() as conn:
        row = conn.execute(select(tables.runs).where(tables.runs.c.id == third.run_id)).one()
    assert row.boards_failed == 12
    assert row.errors_json.count(alert) == 1


@pytest.mark.parametrize("interruption", ["ok", "lane", "standalone", "company", "provider"])
def test_only_pipeline_board_scans_define_the_streak(
    setup: tuple[Engine, Settings], interruption: str,
) -> None:
    engine, settings = setup
    _watch(engine, "acme")
    with respx.mock as routes:
        route = routes.get().respond(404)
        _run(engine, settings)
        second = _run(engine, settings)
        with engine.connect() as conn:
            company_id = conn.execute(select(tables.companies.c.id)).scalar_one()
        if interruption == "lane":
            apply_board(engine, BoardSnapshot(status="partial", postings=[], url="https://test"),
                        company_id, second.run_id, scan_kind="lane", lane="test")
        else:
            route.respond(200, json={"jobs": []})
            if interruption == "ok":
                _run(engine, settings)
            else:
                filters = {"company": "acme"} if interruption == "company" else (
                    {"provider": "greenhouse"} if interruption == "provider" else {}
                )
                run_scan(engine, settings, **filters)
        route.respond(404)
        third = _run(engine, settings)
        if interruption == "ok":
            assert not _dead_alerts(third)
            assert not _dead_alerts(_run(engine, settings))
            third = _run(engine, settings)
        assert len(_dead_alerts(third)) == 1


@pytest.mark.parametrize("failure", [405, 500, None])
def test_other_failures_never_collapse(setup: tuple[Engine, Settings], failure: int | None) -> None:
    engine, settings = setup
    _watch(engine, "dead")
    _watch(engine, "other")
    with respx.mock as routes:
        routes.get(_PROVIDERS["greenhouse"].board_url("dead")).respond(404)
        other = routes.get(_PROVIDERS["greenhouse"].board_url("other"))
        if failure is None:
            other.mock(side_effect=httpx.ReadTimeout("HTTP 404 is only message text"))
        else:
            other.respond(failure)
        summary = [_run(engine, settings) for _ in range(3)][-1]
    assert len(_dead_alerts(summary)) == 1
    assert "Name other" not in _dead_alerts(summary)[0]
    assert any(e.startswith("other:") for e in summary.errors)
    assert summary.scan_boards_failed == 2


@pytest.mark.parametrize("target", ["new", "watched", "absent", "error", "no-scan"])
def test_opt_in_moves_are_reversible_and_fail_open(
    setup: tuple[Engine, Settings], target: str,
) -> None:
    engine, settings = setup
    _watch(engine, "acme")
    if target == "watched":
        _watch(engine, "acme", "lever")
    with engine.begin() as conn:
        company_id = conn.execute(select(tables.companies.c.id).where(
            tables.companies.c.provider == "greenhouse"
        )).scalar_one()
        job_id = conn.execute(insert(tables.jobs).values(created_at=utcnow())).inserted_primary_key[0]
        conn.execute(insert(tables.postings).values(
            job_id=job_id, company_id=company_id, provider_posting_id="old", title="Old job",
            normalized_title="old job", url="https://test/old", locations_json=[],
            remote_policy="unknown", first_seen_at=utcnow(), last_seen_at=utcnow(),
            status="open", consecutive_missing=0, content_hash="old", body_text="Old job",
        ))
    with respx.mock as routes:
        routes.get(_PROVIDERS["greenhouse"].board_url("acme")).respond(404)
        routes.get(_PROVIDERS["lever"].board_url("acme")).respond(200, json=[])
        _run(engine, settings)
        _run(engine, settings)
        if target == "no-scan":
            assert len(_dead_alerts(_run(engine, settings))) == 1
        settings = settings.model_copy(update={"follow_board_moves": True})
        routes.get(_PROVIDERS["lever"].board_url("acme")).respond(
            200, json=[{"id": "new"}] if target == "new" else []
        )
        if target == "error":
            routes.get(_PROVIDERS["lever"].board_url("acme")).mock(
                side_effect=httpx.ReadTimeout("probe timed out")
            )
        routes.get(_PROVIDERS["ashby"].board_url("acme")).respond(404)
        routes.get(_PROVIDERS["workable"].board_url("acme")).respond(404)
        before = len(routes.calls)
        summary = _run(engine, settings, skip_scan=target == "no-scan")
        calls = len(routes.calls) - before
    if target != "no-scan":
        assert len(_dead_alerts(summary)) == 1
    with engine.connect() as conn:
        rows = conn.execute(select(tables.companies).order_by(tables.companies.c.provider)).all()
        assert conn.execute(select(tables.postings.c.status)).scalar_one() == "open"
    old = next(r for r in rows if r.provider == "greenhouse")
    if target in ("new", "watched"):
        assert not old.watched
        new = next(r for r in rows if r.provider == "lever")
        assert new.watched and new.name == "Name acme"
        if target == "new":
            assert new.source == "user"
        undo = join(["boardwatch", "--data-dir", str(settings.data_dir),
                     "companies", "add", "greenhouse:acme"])
        if target == "new":
            undo += " && " + join(["boardwatch", "--data-dir", str(settings.data_dir),
                                   "companies", "remove", "lever:acme"])
        assert summary.funnel is not None and summary.morning is not None
        for artifact in (summary.funnel, summary.morning):
            assert artifact.markdown_path.read_text().count(undo) == 1
            assert len(json.loads(artifact.json_path.read_text())["board_moves"]) == 1
        if target == "watched":
            assert calls == 2, "already covered: only the two watched boards are fetched"
        with engine.connect() as conn:
            due = conn.execute(select(tables.postings.c.provider_posting_id).join(
                tables.companies, tables.companies.c.id == tables.postings.c.company_id,
            ).where(unreachable_by_the_scanner())).scalars().all()
        assert due == ["old"], "unwatch hands old postings to the existing death sweep"
        for command in undo.split(" && "):
            assert CliRunner().invoke(app, split(command)[1:]).exit_code == 0
        with engine.connect() as conn:
            watched = conn.execute(select(tables.companies.c.provider).where(
                tables.companies.c.watched.is_(True)
            )).scalars().all()
        assert sorted(watched) == (["greenhouse", "lever"] if target == "watched" else ["greenhouse"])
    else:
        assert old.watched and len(rows) == 1
        if target == "error":
            assert sum(e.startswith("board moves:") for e in summary.errors) == 1
            assert summary.morning is not None and summary.funnel is not None
            note = next(e for e in summary.errors if e.startswith("board moves:"))
            assert note in summary.morning.markdown_path.read_text()
            assert note in summary.funnel.markdown_path.read_text()
        if target == "no-scan":
            assert calls == 0


def test_a_board_that_is_itself_dead_does_not_cover_another(
    setup: tuple[Engine, Settings],
) -> None:
    engine, settings = setup
    _watch(engine, "acme")
    _watch(engine, "acme", "lever")
    settings = settings.model_copy(update={"follow_board_moves": True})
    with respx.mock as routes:
        routes.get().respond(404)
        for _ in range(3):
            _run(engine, settings)
    with engine.connect() as conn:
        watched = conn.execute(select(tables.companies.c.watched)).scalars().all()
    assert watched == [True, True]
