from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, select, text
from sqlalchemy.exc import IntegrityError

from boardwatch.store import tables
from boardwatch.store.db import DB_FILENAME, ensure_schema, get_engine, schema_revision


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def _seed_company(engine: Engine) -> int:
    with engine.begin() as conn:
        result = conn.execute(
            insert(tables.companies).values(
                name="Acme", provider="greenhouse", slug="acme", source="user", watched=True
            )
        )
        return int(result.inserted_primary_key[0])


def _seed_posting(engine: Engine, company_id: int) -> int:
    with engine.begin() as conn:
        result = conn.execute(
            insert(tables.postings).values(
                company_id=company_id,
                provider_posting_id="1",
                title="Engineer",
                normalized_title="engineer",
                url="https://example.com/1",
                first_seen_at=datetime(2026, 1, 1),
                last_seen_at=datetime(2026, 1, 1),
                status="open",
                consecutive_missing=0,
                content_hash="h1",
                body_text="b",
            )
        )
        return int(result.inserted_primary_key[0])


def test_pragmas_active_on_new_connections(engine: Engine) -> None:
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert conn.execute(text("PRAGMA busy_timeout")).scalar() == 5000


def test_data_dir_override_respected(tmp_path: Path) -> None:
    target = tmp_path / "elsewhere"
    eng = get_engine(target)
    ensure_schema(eng)
    assert (target / DB_FILENAME).is_file()


def test_migrations_match_metadata(engine: Engine) -> None:
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        diff = compare_metadata(ctx, tables.metadata)
    assert diff == []


def test_schema_revision_is_nonempty() -> None:
    assert schema_revision() not in ("", "unknown")


def test_fk_enforced_dangling_posting_event(engine: Engine) -> None:
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                insert(tables.posting_events).values(
                    posting_id=99999, kind="new", run_id=99999, created_at=datetime(2026, 1, 1)
                )
            )


def test_fk_enforced_dangling_board_scan_run(engine: Engine) -> None:
    company_id = _seed_company(engine)
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                insert(tables.board_scans).values(
                    run_id=99999,
                    company_id=company_id,
                    started_at=datetime(2026, 1, 1),
                    finished_at=datetime(2026, 1, 1),
                    status="complete",
                    postings_listed=0,
                )
            )


@pytest.mark.parametrize(
    ("table_name", "bad_values"),
    [
        ("postings", {"status": "zombie"}),
        ("board_scans", {"status": "meh"}),
        ("posting_events", {"kind": "poked"}),
    ],
)
def test_named_check_constraints_reject_out_of_enum(
    engine: Engine, table_name: str, bad_values: dict[str, str]
) -> None:
    company_id = _seed_company(engine)
    with engine.begin() as conn:
        run_id = int(
            conn.execute(
                insert(tables.runs).values(started_at=datetime(2026, 1, 1), boards_attempted=0)
            ).inserted_primary_key[0]
        )
    posting_id = _seed_posting(engine, company_id)
    base: dict[str, dict[str, object]] = {
        "postings": {
            "company_id": company_id,
            "provider_posting_id": "x",
            "title": "t",
            "normalized_title": "t",
            "first_seen_at": datetime(2026, 1, 1),
            "last_seen_at": datetime(2026, 1, 1),
            "consecutive_missing": 0,
            "content_hash": "h",
            "body_text": "b",
        },
        "board_scans": {
            "run_id": run_id,
            "company_id": company_id,
            "started_at": datetime(2026, 1, 1),
            "finished_at": datetime(2026, 1, 1),
            "postings_listed": 0,
        },
        "posting_events": {
            "posting_id": posting_id,
            "kind": "poked",
            "run_id": run_id,
            "created_at": datetime(2026, 1, 1),
        },
    }
    table_map = {
        "postings": tables.postings,
        "board_scans": tables.board_scans,
        "posting_events": tables.posting_events,
    }
    row = base[table_name].copy()
    row.update(bad_values)
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(insert(table_map[table_name]).values(**row))


def _seed_run(engine: Engine) -> int:
    with engine.begin() as conn:
        result = conn.execute(
            insert(tables.runs).values(started_at=datetime(2026, 1, 1), boards_attempted=0)
        )
        return int(result.inserted_primary_key[0])


def test_posting_events_id_is_monotonic_autoincrement(engine: Engine) -> None:
    """autoincrement=True guarantees ids never reuse (D18)."""
    cid = _seed_company(engine)
    run_id = _seed_run(engine)

    def _make(pid: str) -> int:
        with engine.begin() as conn:
            r = conn.execute(
                insert(tables.postings).values(
                    company_id=cid,
                    provider_posting_id=pid,
                    title="t",
                    normalized_title="t",
                    first_seen_at=datetime(2026, 1, 1),
                    last_seen_at=datetime(2026, 1, 1),
                    consecutive_missing=0,
                    content_hash="h",
                    body_text="b",
                )
            )
            return int(r.inserted_primary_key[0])

    pid1 = _make("p1")
    pid2 = _make("p2")
    with engine.begin() as conn:
        conn.execute(
            insert(tables.posting_events).values(
                posting_id=pid1, kind="new", run_id=run_id, created_at=datetime(2026, 1, 1)
            )
        )
        conn.execute(
            insert(tables.posting_events).values(
                posting_id=pid2, kind="new", run_id=run_id, created_at=datetime(2026, 1, 1)
            )
        )
    with engine.connect() as conn:
        ids_before = sorted(
            row[0]
            for row in conn.execute(select(tables.posting_events.c.id)).fetchall()
        )
    # Simulate deletion of the first event
    with engine.begin() as conn:
        conn.execute(tables.posting_events.delete().where(tables.posting_events.c.id == ids_before[0]))
    # Insert a new event
    with engine.begin() as conn:
        conn.execute(
            insert(tables.posting_events).values(
                posting_id=pid1, kind="reopened", run_id=run_id, created_at=datetime(2026, 1, 2)
            )
        )
    with engine.connect() as conn:
        ids_after = sorted(
            row[0]
            for row in conn.execute(select(tables.posting_events.c.id)).fetchall()
        )
    assert ids_after[-1] not in ids_before  # no reuse, so new id > all previous


def test_profile_is_singleton(engine: Engine) -> None:
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                insert(tables.profile).values(
                    id=2, text="x", remote_only=False, updated_at=datetime(2026, 1, 1)
                )
            )


def test_no_scores_table_no_flags_column(engine: Engine) -> None:
    assert "scores" not in tables.metadata.tables  # D17
    assert "flags_json" not in tables.postings.c  # D19
    with engine.connect() as conn:
        names = conn.execute(
            select(text("name")).select_from(text("sqlite_master")).where(text("type='table'"))
        ).scalars().all()
    assert "scores" not in names
