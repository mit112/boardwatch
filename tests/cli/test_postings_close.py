"""`boardwatch postings close` / `reopen` — the owner's closing path (D-630).

WHAT THESE DEFEND. Each test fails against a plausible wrong implementation: one that writes
without `--apply`; one that borrows the latest run's id for its `closed` event, which made a daily
run claim 28 closures it never observed on 2026-10-11; one that closes without evidence or records
none; one that re-stamps a posting already closed; one whose undo leaves the evidence behind; and
one that writes while a scan holds the lease.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, func, insert, select
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.normalize import normalize_title
from boardwatch.core.settings import load_settings
from boardwatch.scan.coordinator import scan_lease
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.tables import app_state, companies, jobs, posting_events, postings, runs

NOW = datetime(2026, 10, 1, 12, 0, 0)
EVIDENCE = "LinkedIn: No longer accepting applications"


def _invoke(data_dir: Path, command: str, *args: str) -> Any:
    return CliRunner().invoke(app, ["--data-dir", str(data_dir), "postings", command, *args])


def _seed(data_dir: Path) -> tuple[Engine, int, int, int]:
    """Two postings — one open, one already closed — and a FINISHED daily run that a lazy
    implementation could borrow."""
    engine = get_engine(data_dir)
    ensure_schema(engine)
    with engine.begin() as conn:
        company_id = int(
            conn.execute(
                insert(companies).values(
                    name="Acme", provider="linkedin", slug="acme", source="user", watched=True
                )
            ).inserted_primary_key[0]
        )
        ids = []
        for n, status in enumerate(("open", "closed")):
            job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
            ids.append(
                int(
                    conn.execute(
                        insert(postings).values(
                            company_id=company_id, job_id=job_id, provider_posting_id=f"li{n}",
                            title="Engineer", normalized_title=normalize_title("Engineer"),
                            url=f"https://www.linkedin.com/jobs/view/{n}", locations_json=[],
                            remote_policy="unknown", first_seen_at=NOW, last_seen_at=NOW,
                            status=status, closed_at=NOW if status == "closed" else None,
                            consecutive_missing=0, death_strikes=0, content_hash="h",
                            body_text="Engineer", raw_json={},
                        )
                    ).inserted_primary_key[0]
                )
            )
        daily = int(
            conn.execute(
                insert(runs).values(
                    started_at=NOW, finished_at=NOW, boards_attempted=0, status="ok"
                )
            ).inserted_primary_key[0]
        )
    return engine, ids[0], ids[1], daily


def _snapshot(engine: Engine) -> dict[str, list[tuple[Any, ...]]]:
    with engine.connect() as conn:
        return {
            table.name: [tuple(row) for row in conn.execute(select(table).order_by(*table.primary_key))]
            for table in (postings, posting_events, app_state, runs)
        }


def test_without_apply_it_reports_and_writes_nothing(tmp_path: Path) -> None:
    engine, open_id, closed_id, _ = _seed(tmp_path)
    before = _snapshot(engine)

    result = _invoke(tmp_path, "close", "--ids", f"{open_id},{closed_id},999999", "--evidence", EVIDENCE)

    assert result.exit_code == 0, result.output
    assert f"{open_id}\tclosed" in result.output
    assert f"{closed_id}\tunchanged" in result.output
    assert "999999\tmissing" in result.output
    assert "would apply" in result.output
    assert _snapshot(engine) == before


def test_apply_closes_in_the_native_shape_under_a_run_of_its_own(tmp_path: Path) -> None:
    engine, open_id, closed_id, daily = _seed(tmp_path)

    result = _invoke(tmp_path, "close", "--ids", f"{open_id},{closed_id}", "--evidence", EVIDENCE, "--apply")

    assert result.exit_code == 0, result.output
    with engine.connect() as conn:
        row = conn.execute(select(postings).where(postings.c.id == open_id)).one()
        assert (row.status, row.closed_at is not None) == ("closed", True)
        events = conn.execute(select(posting_events)).all()
        # Exactly one event: the already-closed posting is not re-stamped.
        assert [(e.posting_id, e.kind) for e in events] == [(open_id, "closed")]
        run_id = events[0].run_id
        # NEVER the daily run: that run did not observe this closure.
        assert run_id != daily
        run = conn.execute(select(runs).where(runs.c.id == run_id)).one()
        assert run.finished_at is not None and run.status == "ok"
        note = json.loads(
            conn.execute(
                select(app_state.c.value).where(app_state.c.key == f"posting.ownerclosed.{open_id}")
            ).scalar_one()
        )
        assert (note["evidence"], note["run_id"]) == (EVIDENCE, run_id)
        # Nothing recorded for the posting that was already closed.
        assert conn.execute(
            select(func.count()).select_from(app_state).where(
                app_state.c.key == f"posting.ownerclosed.{closed_id}"
            )
        ).scalar_one() == 0
    assert f"under run {run_id}" in result.output


def test_a_close_with_no_evidence_is_refused_and_writes_nothing(tmp_path: Path) -> None:
    engine, open_id, _, _ = _seed(tmp_path)
    before = _snapshot(engine)

    blank = _invoke(tmp_path, "close", "--ids", str(open_id), "--evidence", "   ", "--apply")
    absent = _invoke(tmp_path, "close", "--ids", str(open_id), "--apply")

    assert blank.exit_code != 0 and absent.exit_code != 0
    assert _snapshot(engine) == before


def test_reopen_is_the_undo_and_drops_the_evidence(tmp_path: Path) -> None:
    engine, open_id, _, _ = _seed(tmp_path)
    _invoke(tmp_path, "close", "--ids", str(open_id), "--evidence", EVIDENCE, "--apply")

    result = _invoke(tmp_path, "reopen", "--ids", str(open_id), "--apply")

    assert result.exit_code == 0, result.output
    assert f"{open_id}\treopened" in result.output
    with engine.connect() as conn:
        row = conn.execute(select(postings).where(postings.c.id == open_id)).one()
        assert (row.status, row.closed_at) == ("open", None)
        kinds = [e.kind for e in conn.execute(select(posting_events).order_by(posting_events.c.id))]
        assert kinds == ["closed", "reopened"]
        assert conn.execute(
            select(func.count()).select_from(app_state).where(
                app_state.c.key.like("posting.ownerclosed.%")
            )
        ).scalar_one() == 0
    # Idempotent: a second undo changes nothing.
    again = _invoke(tmp_path, "reopen", "--ids", str(open_id), "--apply")
    assert f"{open_id}\tunchanged" in again.output


def test_apply_is_refused_while_a_scan_holds_the_lease(tmp_path: Path, monkeypatch: Any) -> None:
    engine, open_id, _, _ = _seed(tmp_path)
    before = _snapshot(engine)
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(tmp_path))

    with scan_lease(load_settings()):
        result = _invoke(tmp_path, "close", "--ids", str(open_id), "--evidence", EVIDENCE, "--apply")

    assert result.exit_code == 2, result.output
    assert "refused" in result.output
    assert _snapshot(engine) == before
