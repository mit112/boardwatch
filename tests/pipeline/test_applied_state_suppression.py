"""P6 item 5 — a job you have already applied to must never be served as a lead again.

There is no live population to validate against: `applications` and `application_events` are
both 0 rows on the live store (measured 2026-08-10), because `track` has never been used. So
these tests ARE the evidence for this item, and they are written against the boundary that
decides it — which statuses count as "applied" — rather than against the happy path alone.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rich.console import Console
from sqlalchemy import insert, select

from boardwatch.cli.top_cmd import rank_open_postings
from boardwatch.core.clock import utcnow
from boardwatch.core.settings import load_settings
from boardwatch.store import tables
from boardwatch.store.applications import create_application, set_application_status
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.ledger_queries import load_dispositions, record_disposition

runner_input = "3\nacme\nBackend engineer: Python, Go, PostgreSQL.\n\n\n\nn\nn\n"
BODY = "We are hiring a backend engineer to work on Python and PostgreSQL services."


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _seed_posting(data_dir: Path, n: int) -> tuple[int, int]:
    """One posting on its own company and its own job — the live 1:1 shape."""
    engine = get_engine(data_dir)
    ensure_schema(engine)
    now = utcnow()
    with engine.begin() as conn:
        company_id = int(
            conn.execute(
                insert(tables.companies).values(
                    name=f"Acme{n}", provider="greenhouse", slug=f"acme{n}",
                    source="user", watched=False,
                )
            ).inserted_primary_key[0]
        )
        job_id = int(
            conn.execute(insert(tables.jobs).values(created_at=now)).inserted_primary_key[0]
        )
        posting_id = int(
            conn.execute(
                insert(tables.postings).values(
                    company_id=company_id, provider_posting_id=f"p-{n}", job_id=job_id,
                    title="Backend Engineer", normalized_title="backend engineer",
                    url=f"https://example.test/j/{n}", locations_json=["Remote"],
                    remote_policy="remote", first_seen_at=now, last_seen_at=now,
                    status="open", consecutive_missing=0, content_hash=f"h-{n}",
                    body_text=BODY,
                )
            ).inserted_primary_key[0]
        )
        conn.execute(
            insert(tables.posting_versions).values(
                posting_id=posting_id, content_hash=f"h-{n}", body_text=BODY,
                captured_at=now, capture_reason="new",
            )
        )
    return posting_id, job_id


def _ready(data_dir: Path, count: int) -> list[tuple[int, int]]:
    from typer.testing import CliRunner

    from boardwatch.cli.app import app

    cli = CliRunner()
    seeded = [_seed_posting(data_dir, n) for n in range(count)]
    assert cli.invoke(app, ["--data-dir", str(data_dir), "init"], input=runner_input).exit_code == 0
    return seeded


def _rank(data_dir: Path, **kwargs: object):
    settings = load_settings(data_dir=data_dir)
    return rank_open_postings(
        get_engine(data_dir),
        settings,
        limit=10,
        output_console=Console(quiet=True),
        record_surfaced=False,
        **kwargs,  # type: ignore[arg-type]
    )


def _apply(data_dir: Path, job_id: int, status: str) -> int:
    engine = get_engine(data_dir)
    with engine.begin() as conn:
        return create_application(conn, job_id=job_id, status=status)  # type: ignore[arg-type]


def test_a_job_already_applied_to_is_not_served_again(env: Path) -> None:
    """The headline claim. It fails without the filter: the posting is otherwise a clean lead."""
    seeded = _ready(env, 2)
    _apply(env, seeded[0][1], "applied")

    results = _rank(env)

    assert results.hidden_applied == 1
    assert [p.posting_id for p in results.visible] == [seeded[1][0]]


@pytest.mark.parametrize("status", ["applied", "interviewing", "offer", "rejected"])
def test_every_submitted_status_suppresses(env: Path, status: str) -> None:
    """The whole catalog, one case each — a status silently dropped from `APPLIED_STATUSES`
    would otherwise re-serve a job the operator is mid-interview for."""
    seeded = _ready(env, 1)
    _apply(env, seeded[0][1], status)

    assert _rank(env).hidden_applied == 1


@pytest.mark.parametrize("status", ["interested", "withdrawn"])
def test_merely_interested_or_withdrawn_does_not_suppress(env: Path, status: str) -> None:
    """The boundary that decides the item. `interested` is `track add`'s DEFAULT, so suppressing
    it would mean tracking a lead hid it — the opposite of what tracking is for. `withdrawn` is
    the drain: it must put the job back in the queue, not keep it out."""
    seeded = _ready(env, 1)
    _apply(env, seeded[0][1], status)

    results = _rank(env)

    assert results.hidden_applied == 0
    assert [p.posting_id for p in results.visible] == [seeded[0][0]]


def test_withdrawing_an_application_releases_the_job(env: Path) -> None:
    """The drain, exercised on both sides of the gate rather than asserted in a docstring."""
    seeded = _ready(env, 1)
    application_id = _apply(env, seeded[0][1], "applied")
    assert _rank(env).hidden_applied == 1

    engine = get_engine(env)
    with engine.begin() as conn:
        set_application_status(
            conn, application_id=application_id, to_status="withdrawn", source="user"
        )

    results = _rank(env)
    assert results.hidden_applied == 0
    assert [p.posting_id for p in results.visible] == [seeded[0][0]]


def test_the_drain_shows_the_row_and_names_the_status(env: Path) -> None:
    seeded = _ready(env, 1)
    _apply(env, seeded[0][1], "interviewing")

    results = _rank(env, include_applied=True)

    assert results.hidden_applied == 0
    assert [p.posting_id for p in results.visible] == [seeded[0][0]]
    assert results.visible[0].applied_as == "interviewing"


def test_an_applied_job_is_never_surfaced_so_it_cannot_be_recorded_seen(env: Path) -> None:
    """`surfaced_job_ids` is what the pipeline turns into ledger writes after tailoring. A job
    filtered here must not appear in it, or the pipeline would record a `seen` decision about a
    lead it never showed anybody."""
    seeded = _ready(env, 2)
    _apply(env, seeded[0][1], "applied")

    results = _rank(env)

    assert seeded[0][1] not in results.surfaced_job_ids
    assert results.surfaced_job_ids == (seeded[1][1],)


def test_applied_state_outranks_a_live_ledger_disposition(env: Path) -> None:
    """A job that is both applied-to and `built` is counted as applied, not as handled.

    Not cosmetic. `ledger reopen --job` releases the `built` row, and a reader of the funnel
    deciding whether to drain needs the count that will still be there afterwards.
    """
    seeded = _ready(env, 1)
    posting_id, job_id = seeded[0]
    _apply(env, job_id, "applied")
    engine = get_engine(env)
    now = utcnow()
    with engine.begin() as conn:
        record_disposition(
            conn, job_id, disposition="built", reason="lead_built",
            policy_version="pv-1", now=now,
        )

    results = _rank(env)

    assert results.hidden_applied == 1
    assert results.hidden_handled == 0
    # And the ledger row is untouched — suppression reads it, never rewrites it.
    with engine.connect() as conn:
        assert load_dispositions(conn)[job_id].disposition == "built"
    assert posting_id not in [p.posting_id for p in results.visible]


def test_the_ranker_asks_the_applications_table_not_the_ledger(env: Path) -> None:
    """One fact, one home. Suppressing must not mirror the application into a disposition —
    two rows for one fact can disagree, and only one of them has a drain the operator knows."""
    seeded = _ready(env, 1)
    _apply(env, seeded[0][1], "applied")

    _rank(env)

    engine = get_engine(env)
    with engine.connect() as conn:
        assert load_dispositions(conn) == {}
        assert conn.execute(select(tables.job_dispositions)).all() == []
