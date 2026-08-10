"""The behavioural claim P6 slice 2 makes, end to end (design §7).

Measured on the live store 2026-08-10, BEFORE this slice: postings 2011, 2012, 10947, 15498 and
15499 each carry a `resume_tailored` artifact from four separate runs (5, 6, 7, 9). Nothing
suppressed an already-built lead, so the top-N served the same rows every run and the queue never
advanced. These tests are that defect turned into something a regression can trip over.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from rich.console import Console
from sqlalchemy import insert, select

from boardwatch.cli.top_cmd import rank_open_postings
from boardwatch.core.clock import utcnow
from boardwatch.core.settings import load_settings
from boardwatch.pipeline.runner import _zero_output_guard, run_pipeline
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.ledger_queries import live_dispositions, reopen_jobs

runner_input = "3\nacme\nBackend engineer: Python, Go, PostgreSQL.\n\n\n\nn\nn\n"
BODY = "We are hiring a backend engineer to work on Python and PostgreSQL services."


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _seed_posting(data_dir: Path, n: int) -> int:
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
    return posting_id


def _ready(data_dir: Path, count: int) -> list[int]:
    from typer.testing import CliRunner

    from boardwatch.cli.app import app

    cli = CliRunner()
    ids = [_seed_posting(data_dir, n) for n in range(count)]
    assert cli.invoke(app, ["--data-dir", str(data_dir), "init"], input=runner_input).exit_code == 0
    assert cli.invoke(app, ["--data-dir", str(data_dir), "tailor", "init"]).exit_code == 0
    return ids


def _pipeline(data_dir: Path, out_root: Path, top_n: int):
    settings = load_settings(data_dir=data_dir)
    return run_pipeline(
        get_engine(data_dir),
        settings,
        console=Console(quiet=True),
        out_root=out_root,
        resume_path=settings.config_dir / "resume.yaml",
        skip_scan=True,
        top_n=top_n,
    )


def test_a_second_run_builds_a_DISJOINT_set_of_leads(  # noqa: N802 - the claim is the name
    env: Path, tmp_path: Path
) -> None:
    """The headline claim, and it can fail: before this slice the two sets were identical.

    Four candidates, two per run. Run 2 must reach the OTHER two, because run 1's leads carry a
    permanent `built` disposition.
    """
    _ready(env, 4)
    out_root = tmp_path / "apps"

    first = _pipeline(env, out_root, top_n=2)
    second = _pipeline(env, out_root, top_n=2)

    first_leads = {lead.posting_id for lead in first.tailored}
    second_leads = {lead.posting_id for lead in second.tailored}
    assert len(first_leads) == 2, first.errors
    assert len(second_leads) == 2, second.errors
    assert first_leads.isdisjoint(second_leads)
    assert second.shortlist is not None
    assert second.shortlist.hidden_handled == 2


def test_built_leads_are_counted_through_the_filesystem_not_just_the_ledger(
    env: Path, tmp_path: Path
) -> None:
    """Count the deliverable through a different path (CLAUDE.md / D-028).

    A SQL recount of `job_dispositions` grouped a second way would be the tautology this program
    has already shipped and deleted once. The lead FOLDERS on disk are a genuinely different
    path: they are written by the tailor stage, not by the ledger writer.
    """
    _ready(env, 4)
    out_root = tmp_path / "apps"

    first = _pipeline(env, out_root, top_n=2)
    _pipeline(env, out_root, top_n=2)

    day_dir = out_root / utcnow().date().isoformat()
    folders = {p.name for p in day_dir.iterdir() if p.is_dir()}
    with get_engine(env).connect() as conn:
        built = {
            job_id
            for job_id, row in live_dispositions(conn, now=utcnow()).items()
            if row.disposition == "built"
        }
    assert len(folders) == 4, sorted(folders)
    assert len(built) == 4
    assert first.shortlist is not None


def test_a_third_run_with_nothing_left_is_an_honest_empty_day_not_a_fatal(
    env: Path, tmp_path: Path
) -> None:
    """The zero-output guard's ledger clause (design §5.4). Without it the daily driver's exit
    status would be 1 every day once the queue is caught up."""
    _ready(env, 2)
    out_root = tmp_path / "apps"

    _pipeline(env, out_root, top_n=2)
    exhausted = _pipeline(env, out_root, top_n=2)

    assert exhausted.tailored == []
    assert exhausted.shortlist is not None
    assert exhausted.shortlist.hidden_handled == 2
    assert exhausted.fatal is None, exhausted.fatal


def test_the_zero_output_guard_still_fires_when_nothing_was_handled() -> None:
    """The other direction, which is what keeps the widening from being a weakening: a run that
    judged new eligible work, produced no leads, and had NO handled candidates cannot explain
    itself and is still fatal."""
    assert _zero_output_guard(5, 0) is not None
    assert _zero_output_guard(5, 3) is None
    assert _zero_output_guard(0, 0) is None


def test_reopening_a_built_job_brings_it_back_to_the_shortlist(
    env: Path, tmp_path: Path
) -> None:
    """The drain's write side, through the ranker rather than through the store alone."""
    _ready(env, 2)
    out_root = tmp_path / "apps"
    first = _pipeline(env, out_root, top_n=2)
    built_ids = {lead.posting_id for lead in first.tailored}
    assert built_ids

    engine = get_engine(env)
    settings = load_settings(data_dir=env)
    after = rank_open_postings(engine, settings, limit=5, output_console=Console(quiet=True))
    assert after.hidden_handled == 2
    assert after.visible == []

    with engine.begin() as conn:
        job_ids = [
            int(row.job_id)
            for row in conn.execute(
                select(tables.postings.c.job_id).where(
                    tables.postings.c.id.in_(sorted(built_ids))
                )
            ).all()
        ]
        assert reopen_jobs(conn, job_ids, now=utcnow()) == 2

    drained = rank_open_postings(engine, settings, limit=5, output_console=Console(quiet=True))
    assert {p.posting_id for p in drained.visible} == built_ids
    assert drained.hidden_handled == 0


def test_a_seen_row_lapses_on_its_own_and_the_job_re_enters(env: Path, tmp_path: Path) -> None:
    """The TTL is itself a drain. `top` surfaces without building, so the rows are `seen`; past
    `seen_ttl_days` they govern nothing, with no operator action."""
    _ready(env, 2)
    engine = get_engine(env)
    settings = load_settings(data_dir=env)
    now = utcnow()

    shown = rank_open_postings(
        engine, settings, limit=2, now=now, output_console=Console(quiet=True)
    )
    assert len(shown.visible) == 2

    inside_ttl = rank_open_postings(
        engine, settings, limit=2, now=now + timedelta(days=1),
        output_console=Console(quiet=True),
    )
    assert inside_ttl.visible == []
    assert inside_ttl.hidden_handled == 2

    past_ttl = rank_open_postings(
        engine, settings, limit=2,
        now=now + timedelta(days=settings.seen_ttl_days + 1),
        output_console=Console(quiet=True),
    )
    assert len(past_ttl.visible) == 2
    assert past_ttl.hidden_handled == 0
