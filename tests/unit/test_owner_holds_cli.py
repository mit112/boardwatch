"""Persisted owner intent has an independent explicit drain."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import insert, select
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.clock import utcnow
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.tables import app_state, jobs


def test_cli_hold_persists_and_release_keeps_unrelated_decisions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "config"))
    data = tmp_path / "data"
    engine = get_engine(data)
    ensure_schema(engine)
    with engine.begin() as conn:
        job = int(conn.execute(insert(jobs).values(created_at=utcnow())).inserted_primary_key[0])
        conn.execute(insert(app_state).values(key=f"queue.skipped.{job}", value="original"))
    cli = CliRunner()
    prefix = ["--data-dir", str(data), "ledger"]
    held = cli.invoke(app, [*prefix, "hold", "--job", str(job), "--reason", "Await owner choice"])
    assert held.exit_code == 0, held.output
    listed = cli.invoke(app, [*prefix, "holds", "--json"])
    assert listed.exit_code == 0, listed.output
    assert json.loads(listed.output)["holds"][0]["reason"] == "Await owner choice"
    released = cli.invoke(app, [*prefix, "release-hold", "--job", str(job)])
    assert released.exit_code == 0, released.output
    assert json.loads(cli.invoke(app, [*prefix, "holds", "--json"]).output)["holds"] == []
    with engine.connect() as conn:
        state = dict(conn.execute(select(app_state.c.key, app_state.c.value)).all())
        assert state[f"queue.skipped.{job}"] == "original"
        assert json.loads(state[f"queue.held.{job}"])["released_at"] is not None


def test_cli_refuses_missing_job_and_blank_reason(tmp_path: Path) -> None:
    prefix = ["--data-dir", str(tmp_path), "ledger", "hold", "--job", "999"]
    cli = CliRunner()
    assert cli.invoke(app, [*prefix, "--reason", "Pending"]).exit_code != 0
    assert cli.invoke(app, [*prefix, "--reason", " "]).exit_code != 0


def test_hold_protects_regrouping_until_explicit_release(tmp_path: Path) -> None:
    from boardwatch.store.owner_holds import hold_job, release_job_hold
    from boardwatch.store.regroup import queue_action_job_ids

    engine = get_engine(tmp_path)
    ensure_schema(engine)
    with engine.begin() as conn:
        job = int(conn.execute(insert(jobs).values(created_at=utcnow())).inserted_primary_key[0])
        hold_job(conn, job_id=job, reason="Pending", at=utcnow())
        assert job in queue_action_job_ids(conn)
        release_job_hold(conn, job_id=job, at=utcnow())
        assert job not in queue_action_job_ids(conn)


@pytest.mark.parametrize("value", ["broken", '{"version":2}', '{"version":1,"reason":"x","held_at":"bad"}'])
def test_malformed_hold_cannot_silently_authorize_work(tmp_path: Path, value: str) -> None:
    from boardwatch.store.owner_holds import OwnerHoldError, owner_holds

    engine = get_engine(tmp_path)
    ensure_schema(engine)
    with engine.begin() as conn:
        conn.execute(insert(app_state).values(key="queue.held.1", value=value))
    with engine.connect() as conn, pytest.raises(OwnerHoldError):
        owner_holds(conn)


def test_hold_command_serializes_its_read_then_write_against_another_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from types import SimpleNamespace

    from boardwatch.cli import ledger_cmd

    engine = get_engine(tmp_path)
    ensure_schema(engine)
    with engine.begin() as conn:
        job = int(conn.execute(insert(jobs).values(created_at=utcnow())).inserted_primary_key[0])
    entered, second_started, second_done = Event(), Event(), Event()
    native = ledger_cmd.hold_job

    def pause_after_job_read(*args: object, **kwargs: object) -> None:
        entered.set()
        assert second_started.wait(5)
        second_done.wait(0.1)
        native(*args, **kwargs)

    monkeypatch.setattr(ledger_cmd, "build_context", lambda _: SimpleNamespace(engine=engine))
    monkeypatch.setattr(ledger_cmd, "hold_job", pause_after_job_read)

    def other_writer() -> None:
        assert entered.wait(5)
        second_started.set()
        with engine.begin() as conn:
            conn.execute(insert(app_state).values(key="independent.writer", value="preserved"))
        second_done.set()

    with ThreadPoolExecutor(max_workers=2) as workers:
        other = workers.submit(other_writer)
        # No CliRunner global stdout/context mutation across threads.
        ledger_cmd.hold(SimpleNamespace(obj=tmp_path), job=job, reason="Pending")
        other.result(timeout=5)
    with engine.connect() as conn:
        state = dict(conn.execute(select(app_state.c.key, app_state.c.value)).all())
    assert json.loads(state[f"queue.held.{job}"])["reason"] == "Pending"
    assert state["independent.writer"] == "preserved"
