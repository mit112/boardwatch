"""`boardwatch ledger show|reopen` — the drain's write side (P6 slice 2 §6)."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, select
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.ledger_queries import load_dispositions, record_disposition

NOW = datetime(2026, 8, 10, 12, 0, 0)
runner = CliRunner()


@pytest.fixture()
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    target = tmp_path / "data"
    ensure_schema(get_engine(target))
    return target


def _cli(data_dir: Path, args: list[str]):
    return runner.invoke(app, ["--data-dir", str(data_dir), *args])


def _seed_job_with_posting(engine: Engine, n: int) -> int:
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
            conn.execute(insert(tables.jobs).values(created_at=NOW)).inserted_primary_key[0]
        )
        conn.execute(
            insert(tables.postings).values(
                company_id=company_id, job_id=job_id, provider_posting_id=str(n),
                title=f"Engineer {n}", normalized_title="engineer",
                url="https://example.test/j", first_seen_at=NOW, last_seen_at=NOW,
                status="open", consecutive_missing=0, content_hash=f"h{n}", body_text="b",
            )
        )
    return job_id


def test_show_lists_a_live_built_decision_with_the_posting_it_covers(data_dir: Path) -> None:
    engine = get_engine(data_dir)
    job_id = _seed_job_with_posting(engine, 1)
    with engine.begin() as conn:
        record_disposition(
            conn, job_id, disposition="built", reason="lead_built",
            policy_version="stamp-1", now=NOW,
        )
    result = _cli(data_dir, ["ledger", "show"])
    assert result.exit_code == 0, result.output
    assert "built" in result.output
    assert "lead_built" in result.output
    assert "Engineer 1" in result.output


def test_show_says_so_plainly_when_nothing_is_suppressed(data_dir: Path) -> None:
    result = _cli(data_dir, ["ledger", "show"])
    assert result.exit_code == 0
    assert "nothing to show" in result.output


def test_show_omits_a_lapsed_row_unless_expired_is_asked_for(data_dir: Path) -> None:
    """Lazy expiry means the row is still on disk; `show` must not present it as governing."""
    engine = get_engine(data_dir)
    job_id = _seed_job_with_posting(engine, 1)
    with engine.begin() as conn:
        record_disposition(
            conn, job_id, disposition="seen", reason="surfaced",
            expires_at=NOW - timedelta(days=1), now=NOW - timedelta(days=8),
        )
    assert "nothing to show" in _cli(data_dir, ["ledger", "show"]).output
    expired = _cli(data_dir, ["ledger", "show", "--expired"])
    assert "surfaced" in expired.output
    assert "no" in expired.output  # the Governs column


def test_reopen_releases_a_named_job_without_deleting_the_row(data_dir: Path) -> None:
    engine = get_engine(data_dir)
    job_id = _seed_job_with_posting(engine, 1)
    with engine.begin() as conn:
        record_disposition(
            conn, job_id, disposition="built", reason="lead_built",
            policy_version="stamp-1", now=NOW,
        )
    result = _cli(data_dir, ["ledger", "reopen", "--job", str(job_id)])
    assert result.exit_code == 0
    assert "released 1" in result.output
    with engine.connect() as conn:
        stored = load_dispositions(conn)[job_id]
    assert stored.reopened_at is not None
    assert stored.disposition == "built"  # the record survives the drain
    assert "nothing to show" in _cli(data_dir, ["ledger", "show"]).output


def test_reopen_with_no_target_refuses_rather_than_releasing_everything(data_dir: Path) -> None:
    """A bare `reopen` must not be read as "release the whole bucket"."""
    result = _cli(data_dir, ["ledger", "reopen"])
    assert result.exit_code == 2
    assert "nothing to do" in result.output


def test_stale_finds_a_decision_whose_stamp_moved_and_reopen_stale_releases_it(
    data_dir: Path,
) -> None:
    """The policy-drift drain, end to end. The stored stamp is deliberately not the current one,
    which is what a settings or résumé change produces."""
    engine = get_engine(data_dir)
    fresh_job = _seed_job_with_posting(engine, 1)
    with engine.begin() as conn:
        record_disposition(
            conn, fresh_job, disposition="built", reason="lead_built",
            policy_version="a-stamp-from-another-policy", now=NOW,
        )
    listed = _cli(data_dir, ["ledger", "show", "--stale"])
    assert listed.exit_code == 0
    assert str(fresh_job) in listed.output

    released = _cli(data_dir, ["ledger", "reopen", "--stale"])
    assert released.exit_code == 0
    assert "released 1" in released.output
    assert "no stale decisions" in _cli(data_dir, ["ledger", "show", "--stale"]).output


def test_a_current_stamp_is_not_reported_stale(data_dir: Path) -> None:
    """The other direction: `--stale` must not indict every permanent row it can see."""
    engine = get_engine(data_dir)
    job_id = _seed_job_with_posting(engine, 1)
    from boardwatch.core.settings import load_settings
    from boardwatch.pipeline.policy import run_policy_version

    settings = load_settings(data_dir=data_dir)
    with engine.begin() as conn:
        record_disposition(
            conn, job_id, disposition="built", reason="lead_built",
            policy_version=run_policy_version(conn, settings), now=NOW,
        )
    assert "no stale decisions" in _cli(data_dir, ["ledger", "show", "--stale"]).output
    with engine.connect() as conn:
        assert conn.execute(select(tables.job_dispositions.c.job_id)).scalar_one() == job_id
