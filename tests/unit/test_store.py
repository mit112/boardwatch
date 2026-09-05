import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, insert, select, text
from sqlalchemy.exc import IntegrityError, OperationalError

from boardwatch.store import tables
from boardwatch.store.db import (
    BEGIN_MODE_OPTION,
    DB_FILENAME,
    UnknownBeginModeError,
    db_revision,
    ensure_schema,
    get_engine,
    get_readonly_engine,
    schema_revision,
    write_connection,
)


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
        job_id = int(
            conn.execute(
                insert(tables.jobs).values(created_at=datetime(2026, 1, 1))
            ).inserted_primary_key[0]
        )
        result = conn.execute(
            insert(tables.postings).values(
                company_id=company_id,
                job_id=job_id,
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
            job_id = int(
                conn.execute(
                    insert(tables.jobs).values(created_at=datetime(2026, 1, 1))
                ).inserted_primary_key[0]
            )
            r = conn.execute(
                insert(tables.postings).values(
                    company_id=cid,
                    job_id=job_id,
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


def test_a_new_store_is_in_wal_from_the_moment_the_schema_exists(tmp_path: Path) -> None:
    """WAL must be established when the store is CREATED, not on some later connection.

    `get_engine` is lazy, and `ensure_schema` runs alembic through an engine alembic builds
    itself from the URL — so alembic never fires the `connect` listener that sets the pragmas.
    Without a warm connection first, the database is created in `delete` mode and the switch to
    WAL is deferred to whichever connection happens to run first. That deferred switch is a
    CONVERSION, which no lock held by any other connection permits: it returns "database is
    locked" after the busy timeout against a reader, and instantly against a writer. Two
    processes opening a fresh store therefore race, and one of them fails — which is what
    reddens `test_two_writer_concurrency` on macOS and Windows.
    """
    engine = get_engine(tmp_path)
    ensure_schema(engine)
    engine.dispose()
    # Read the persisted header through a plain connection, not the instrumented engine, so the
    # assertion cannot be satisfied by the very pragma whose absence is under test.
    raw = sqlite3.connect(tmp_path / DB_FILENAME)
    try:
        assert raw.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        raw.close()


# --- the engine's own BEGIN (D-426's class, answered at the engine) ------------------------


def _add_company(eng: Engine, slug: str) -> None:
    with eng.begin() as conn:
        conn.execute(
            insert(tables.companies).values(
                name=slug.title(), provider="greenhouse", slug=slug, source="user", watched=True
            )
        )


def test_reads_inside_one_transaction_share_a_snapshot(tmp_path: Path) -> None:
    """Two reads in ONE transaction must answer from ONE snapshot.

    pysqlite opens a transaction on the first DML statement and never on a SELECT, so without
    the `begin` listener each read of a read-then-write sequence runs in autocommit against
    whatever is committed at that instant. D-426 met exactly this: a total and a breakdown read
    inside `conn.begin()` disagreed, and the report published a NEGATIVE claimable count.
    """
    engine_a = get_engine(tmp_path)
    ensure_schema(engine_a)
    _add_company(engine_a, "acme")
    engine_b = get_engine(tmp_path)

    count = select(func.count()).select_from(tables.companies)
    with engine_a.begin() as conn:
        first = conn.execute(count).scalar_one()
        _add_company(engine_b, "beta")  # a concurrent writer lands between the two reads
        second = conn.execute(count).scalar_one()

    assert (first, second) == (1, 1)
    # The positive control: the write really did commit, so the test is not passing because
    # nothing happened between the reads.
    with engine_a.connect() as conn:
        assert conn.execute(count).scalar_one() == 2


def test_write_connection_takes_the_write_lock_at_begin(tmp_path: Path) -> None:
    """`write_connection` must begin IMMEDIATE, so a second writer queues instead of racing.

    Asserted by BEHAVIOUR, not by inspecting the emitted SQL: the second connection's first
    READ is refused, which can only happen if the first connection already holds the write lock
    without having written anything. A deferred transaction would let both reads through and
    fail the loser at COMMIT instead — the upgrade deadlock this exists to prevent.
    """
    engine = get_engine(tmp_path, busy_timeout_ms=100)
    ensure_schema(engine)
    count = select(func.count()).select_from(tables.companies)

    with write_connection(engine) as first:
        first.execute(count)  # autobegins IMMEDIATE
        with write_connection(engine) as second:
            with pytest.raises(OperationalError, match="database is locked"):
                second.execute(count)


def test_a_deferred_reader_does_not_lock_out_a_writer(tmp_path: Path) -> None:
    """The control for the test above: a plain connection must NOT take the write lock.

    Without this, `_install_begin_hook` could emit IMMEDIATE for everything and both tests
    would still pass, at the cost of serialising every read in the program against every write.
    """
    engine = get_engine(tmp_path, busy_timeout_ms=100)
    ensure_schema(engine)
    count = select(func.count()).select_from(tables.companies)

    with engine.connect() as reader:
        reader.execute(count)  # autobegins DEFERRED
        _add_company(engine, "acme")  # must not raise


def test_an_unknown_begin_mode_is_refused(tmp_path: Path) -> None:
    engine = get_engine(tmp_path)
    ensure_schema(engine)
    conn = engine.connect().execution_options(**{BEGIN_MODE_OPTION: "IMMEDIATE; DROP TABLE jobs"})
    with conn, pytest.raises(UnknownBeginModeError):
        conn.execute(select(func.count()).select_from(tables.companies))


def test_the_readonly_engine_ignores_the_immediate_option(tmp_path: Path) -> None:
    """A read-only engine opens `mode=ro` and sets `query_only=ON`, so IMMEDIATE could only
    fail there. The option is not honoured rather than being honoured and failing, so a caller
    handed either engine behaves the same way."""
    engine = get_engine(tmp_path)
    ensure_schema(engine)
    _add_company(engine, "acme")
    engine.dispose()

    ro = get_readonly_engine(tmp_path)
    conn = ro.connect().execution_options(**{BEGIN_MODE_OPTION: "IMMEDIATE"})
    with conn:
        assert conn.execute(select(func.count()).select_from(tables.companies)).scalar_one() == 1


def test_the_fast_schema_path_produces_the_same_schema_as_the_migration_chain(
    tmp_path: Path,
) -> None:
    """T16. The shortcut is only safe if it produces the SAME schema, and
    `test_migrations_match_metadata` cannot establish that: alembic's `compare_metadata`
    compares tables, columns, indexes and types, and does not see TRIGGERS at all. This schema
    has 20 of them — the ten append-only `RAISE(ABORT)` pairs the eligibility keystone rests on,
    and both `postings_job_required_*`. That gap is why the shortcut replays the migrated
    schema's own DDL rather than `metadata.create_all`, which was measured to emit zero of the 20.

    Triggers and indexes are compared as EXACT DDL TEXT, because that text is the whole of their
    behaviour and there is no PRAGMA that reflects a trigger body. Tables are compared through
    PRAGMA plus an ORDER-INSENSITIVE constraint-name set, because the migration chain itself is
    not byte-deterministic: two `command.upgrade` runs in one process emit `companies` and
    `board_scans` with their CONSTRAINT clauses in different orders (alembic's batch rebuild
    reflects them into an unordered collection). Asserting on the text there would pin alembic's
    iteration order, not this repository's schema.
    """
    import os
    import re

    from boardwatch.store.db import FAST_SCHEMA_ENV

    def _schema(path: Path, fast: bool) -> dict[str, object]:
        previous = os.environ.get(FAST_SCHEMA_ENV)
        if fast:
            os.environ[FAST_SCHEMA_ENV] = "1"
        else:
            os.environ.pop(FAST_SCHEMA_ENV, None)
        try:
            eng = get_engine(path)
            ensure_schema(eng)
            with eng.connect() as conn:
                rows = conn.execute(
                    text(
                        "SELECT type, name, sql FROM sqlite_master "
                        "WHERE name NOT LIKE 'sqlite_%'"
                    )
                ).all()
                names = {(str(r[0]), str(r[1])) for r in rows}
                ddl = {
                    (str(r[0]), str(r[1])): " ".join(str(r[2]).split())
                    for r in rows
                    if r[2] is not None and str(r[0]) in ("trigger", "index")
                }
                constraints = {}
                columns = {}
                foreign_keys = {}
                for kind, name, sql in rows:
                    if kind != "table":
                        continue
                    constraints[name] = frozenset(
                        re.findall(r"CONSTRAINT (\w+)", " ".join(str(sql).split()))
                    )
                    columns[name] = tuple(
                        (r[1], r[2], r[3], r[5])  # name, type, notnull, pk
                        for r in conn.execute(text(f'PRAGMA table_info("{name}")'))
                    )
                    foreign_keys[name] = frozenset(
                        (r[2], r[3], r[4])  # referenced table, from, to
                        for r in conn.execute(text(f'PRAGMA foreign_key_list("{name}")'))
                    )
                revision = db_revision(conn)
            return {
                "names": names, "ddl": ddl, "constraints": constraints,
                "columns": columns, "foreign_keys": foreign_keys, "revision": revision,
            }
        finally:
            if previous is None:
                os.environ.pop(FAST_SCHEMA_ENV, None)
            else:
                os.environ[FAST_SCHEMA_ENV] = previous

    migrated = _schema(tmp_path / "migrated", fast=False)
    fast = _schema(tmp_path / "fast", fast=True)

    triggers = {name for kind, name in migrated["names"] if kind == "trigger"}  # type: ignore[union-attr]
    assert len(triggers) == 20, sorted(triggers)
    assert fast["names"] == migrated["names"]
    assert fast["ddl"] == migrated["ddl"]  # every trigger BODY and every index, verbatim
    assert fast["constraints"] == migrated["constraints"]
    assert fast["columns"] == migrated["columns"]
    assert fast["foreign_keys"] == migrated["foreign_keys"]
    assert fast["revision"] == migrated["revision"] == schema_revision()


def test_the_fast_schema_path_refuses_a_database_that_is_not_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second guard, and the one that makes a leaked environment variable harmless: the
    shortcut only ever applies to a file with nothing in it, so a real store migrates."""
    from boardwatch.store.db import FAST_SCHEMA_ENV, _is_empty_database

    monkeypatch.setenv(FAST_SCHEMA_ENV, "1")
    eng = get_engine(tmp_path / "store")
    assert _is_empty_database(eng) is True
    ensure_schema(eng)
    assert _is_empty_database(eng) is False
    ensure_schema(eng)  # idempotent, and now goes through alembic
    with eng.connect() as conn:
        assert db_revision(conn) == schema_revision()
