"""Verified application destinations survive source refreshes without changing identity."""

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import select, update

from boardwatch.core.models import BoardSnapshot, RawPosting
from boardwatch.scan.apply import apply_board
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.tables import postings, runs
from tests.unit.test_delivery_queries import _deliver

SOURCE = "https://www.linkedin.com/jobs/view/123"
TARGET = "https://jobs.ashbyhq.com/acme/123"
AT = datetime(2026, 11, 6, 18, 0)


def test_destination_survives_import_close_reopen_and_explicit_clear(tmp_path: Path) -> None:
    from boardwatch.store.application_destinations import (
        clear_application_destination,
        effective_apply_url,
        record_application_destination,
    )

    engine = get_engine(tmp_path)
    ensure_schema(engine)
    with engine.begin() as conn:
        pid, _ = _deliver(conn, "one", url=SOURCE)
        row = conn.execute(select(postings).where(postings.c.id == pid)).one()
        run_id = conn.execute(select(runs.c.id).limit(1)).scalar_one()
        record_application_destination(
            conn,
            posting_id=pid,
            url=TARGET,
            source_url=SOURCE,
            evidence_ref="ledger.json#123",
            verified_at=AT,
        )
    snapshot = BoardSnapshot(
        postings=[
            RawPosting(
                provider_posting_id=row.provider_posting_id,
                title=row.title,
                url=SOURCE + "?refresh=1",
                body_text=row.body_text,
                locations=["Boston, MA"],
                remote_policy="remote",
                raw_json={},
            )
        ],
        status="complete",
        url=SOURCE,
    )
    apply_board(engine, snapshot, row.company_id, run_id, scan_kind="lane")
    with engine.begin() as conn:
        for status in ("closed", "open"):
            conn.execute(update(postings).where(postings.c.id == pid).values(status=status))
            assert (
                conn.execute(select(effective_apply_url()).where(postings.c.id == pid)).scalar_one()
                == TARGET
            )
        after = conn.execute(select(postings).where(postings.c.id == pid)).one()
        assert (after.id, after.job_id, after.url) == (row.id, row.job_id, SOURCE + "?refresh=1")
        clear_application_destination(conn, posting_id=pid)
        assert (
            conn.execute(select(effective_apply_url()).where(postings.c.id == pid)).scalar_one()
            == SOURCE + "?refresh=1"
        )


def test_record_replace_read_and_idempotence(tmp_path: Path) -> None:
    from boardwatch.store.application_destinations import (
        read_application_destinations,
        record_application_destination,
    )

    engine = get_engine(tmp_path)
    ensure_schema(engine)
    with engine.begin() as conn:
        pid, _ = _deliver(conn, "one", url=SOURCE)
        kw = dict(
            posting_id=pid,
            url=TARGET,
            source_url=SOURCE,
            evidence_ref="ledger.json#123",
            verified_at=AT,
        )
        assert record_application_destination(conn, **kw)
        assert not record_application_destination(conn, **kw)
        assert record_application_destination(conn, **{**kw, "url": TARGET + "-new"})
        saved = read_application_destinations(conn, [pid])[pid]
        assert (saved.url, saved.source_url, saved.evidence_ref, saved.verified_at) == (
            TARGET + "-new",
            SOURCE,
            "ledger.json#123",
            AT,
        )


@pytest.mark.parametrize(
    "url",
    ["", "javascript:alert(1)", "file:///tmp/job", "https://", "https://u:p@example.com/job/1"],
)
def test_invalid_destination_cannot_be_recorded(tmp_path: Path, url: str) -> None:
    from boardwatch.store.application_destinations import (
        InvalidApplicationDestinationError,
        record_application_destination,
    )

    engine = get_engine(tmp_path)
    ensure_schema(engine)
    with engine.begin() as conn, pytest.raises(InvalidApplicationDestinationError):
        record_application_destination(
            conn,
            posting_id=1,
            url=url,
            source_url=SOURCE,
            evidence_ref="ledger.json#1",
            verified_at=AT,
        )


def test_migration_adds_empty_destination_table_without_rewriting_sources(tmp_path: Path) -> None:
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    from tests.unit.test_migration_death_probe import _seed_posting

    cfg = Config()
    cfg.set_main_option("script_location", "src/boardwatch/store/migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{tmp_path / 'existing.db'}")
    engine = create_engine(cfg.get_main_option("sqlalchemy.url"))
    command.upgrade(cfg, "p_runs_incremental")
    _seed_posting(engine, pid="existing")
    with engine.connect() as conn:
        before = conn.execute(text("SELECT id, job_id, url FROM postings")).all()
    command.upgrade(cfg, "p_apply_destinations")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT id, job_id, url FROM postings")).all() == before
        assert conn.execute(text("SELECT * FROM application_destinations")).all() == []
        assert conn.execute(text("PRAGMA foreign_key_check")).all() == []
    command.downgrade(cfg, "p_runs_incremental")
    command.upgrade(cfg, "p_apply_destinations")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT id, job_id, url FROM postings")).all() == before
    engine.dispose()
