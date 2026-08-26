"""The read-only store opener, `get_readonly_engine`.

The local review app reads a store the scan pipeline may be writing at the same moment, so
read-only-ness has to hold on every route a caller can reach the file by — the connection, the
URL, and a re-parse of that URL by somebody else's engine. Each test below is aimed at one way
a plausible implementation gets that wrong, and fails against it:

* a `creator=`-based opener passes the INSERT test and hands alembic a read-WRITE URL;
* an `immutable=1` opener passes both of those and reads stale, pre-checkpoint data;
* an f-string of the path into the URI passes all three and silently opens a different file;
* an opener that drops the WAL-unsafe-filesystem guard passes every one of them.

`tmp_path` throughout. Nothing here may reach a real store.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError

from boardwatch.store.db import (
    DB_FILENAME,
    WalUnsafeFilesystemError,
    ensure_schema,
    get_engine,
    get_readonly_engine,
)


@pytest.fixture()
def writer(tmp_path: Path) -> Iterator[Engine]:
    """A real store, created through the production writer and left OPEN.

    Left open deliberately: SQLite checkpoints and removes the -wal file when the last
    connection closes, so a fixture that disposed its engine would hand every test the
    already-checkpointed case — in which an `immutable=1` opener reads correctly and the
    distinction the tests below rest on disappears.

    A plain `probe` table rather than the real schema: `ensure_schema` costs a full alembic
    run, and nothing here is about the schema. The table is created after `get_engine` has
    established WAL, so its very existence is unreachable without reading the WAL.
    """
    engine = get_engine(tmp_path)
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE probe (v TEXT)")
        conn.exec_driver_sql("INSERT INTO probe VALUES ('first')")
    yield engine
    engine.dispose()


def test_an_insert_through_the_readonly_engine_raises(writer: Engine, tmp_path: Path) -> None:
    engine = get_readonly_engine(tmp_path)
    with engine.connect() as conn, pytest.raises(OperationalError) as excinfo:
        conn.exec_driver_sql("INSERT INTO probe VALUES ('written')")
    assert "readonly" in str(excinfo.value) or "query_only" in str(excinfo.value)
    engine.dispose()
    # The refusal, not merely an exception on the way out: the row must not be there.
    with writer.connect() as conn:
        assert conn.execute(text("SELECT v FROM probe")).scalars().all() == ["first"]


def test_ensure_schema_through_the_readonly_engine_raises(writer: Engine, tmp_path: Path) -> None:
    # `ensure_schema` renders `engine.url` and lets alembic build its OWN engine from the
    # string, so this can only pass if read-only-ness lives in the URL. An opener that got it
    # from a `creator=` callable, or from the connect-time pragma alone, blocks a direct INSERT
    # and still lets alembic migrate the store.
    engine = get_readonly_engine(tmp_path)
    with pytest.raises(OperationalError):
        ensure_schema(engine)
    with engine.connect() as conn:
        tables = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        assert "alembic_version" not in tables.scalars().all()
    engine.dispose()


def test_a_missing_store_raises_a_clear_error_and_creates_no_file(tmp_path: Path) -> None:
    empty = tmp_path / "no-store-here"
    empty.mkdir()
    with pytest.raises(FileNotFoundError) as excinfo:
        get_readonly_engine(empty)
    # Clear means it names the file it wanted, not just "unable to open database file".
    assert DB_FILENAME in str(excinfo.value)
    # A read-only opener that creates the store it is meant to read is the bug this guards.
    assert list(empty.iterdir()) == []

    # And the directory itself is not created either — the half of "no `mkdir`" that an
    # existing-but-empty directory cannot see.
    absent = tmp_path / "not-a-data-dir"
    with pytest.raises(FileNotFoundError):
        get_readonly_engine(absent)
    assert not absent.exists()


def test_a_store_in_another_journal_mode_opens_with_no_journal_mode_pragma(tmp_path: Path) -> None:
    # `PRAGMA journal_mode=WAL` is a write. Against a store already in WAL it is a silent no-op,
    # so only a store in a different journal mode can tell the implementations apart: one that
    # kept `get_engine`'s pragma fails at CONNECT with `attempt to write a readonly database`,
    # before any query runs. `delete` is the default mode, so any client that created the file
    # without asking for WAL leaves a store in this shape.
    with closing(sqlite3.connect(tmp_path / DB_FILENAME)) as raw:
        assert raw.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        raw.execute("CREATE TABLE probe (v TEXT)")
        raw.execute("INSERT INTO probe VALUES ('first')")
        raw.commit()
    engine = get_readonly_engine(tmp_path)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT v FROM probe")).scalars().all() == ["first"]
    engine.dispose()


def test_query_only_is_on_for_every_connection(writer: Engine, tmp_path: Path) -> None:
    engine = get_readonly_engine(tmp_path)
    # Two at once, so the pool really opens two DBAPI connections and the connect hook has to
    # fire for both; sequential `connect()` calls would just check out the same one twice.
    with engine.connect() as first, engine.connect() as second:
        assert first.exec_driver_sql("PRAGMA query_only").scalar() == 1
        assert second.exec_driver_sql("PRAGMA query_only").scalar() == 1
    engine.dispose()
    # Not vacuous: query_only is OFF by default, so the 1s above are this opener's doing.
    with writer.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA query_only").scalar() == 0


def test_the_busy_timeout_is_treated_as_the_writer_treats_it(
    writer: Engine, tmp_path: Path
) -> None:
    # A read is not exempt from SQLITE_BUSY — it queues behind a checkpointer or an exclusive
    # lock — so the timeout is kept rather than dropped as a write-only concern.
    #
    # Asserted through a NON-default value, because Python's sqlite3 driver sets busy_timeout
    # to 5000 all by itself (its `timeout=5.0` connect default). Measured: an assertion on the
    # default value passes byte-for-byte with the pragma deleted, and proves nothing.
    engine = get_readonly_engine(tmp_path, busy_timeout_ms=1234)
    with engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA busy_timeout").scalar() == 1234
    engine.dispose()

    # Same parameter, same default as the writer's.
    default = get_readonly_engine(tmp_path)
    with default.connect() as readonly, writer.connect() as readwrite:
        assert readonly.exec_driver_sql("PRAGMA busy_timeout").scalar() == (
            readwrite.exec_driver_sql("PRAGMA busy_timeout").scalar()
        )
    default.dispose()


def test_the_wal_unsafe_filesystem_guard_still_fires(
    writer: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Mirrors `test_fs_safety.py::test_get_engine_refuses_a_wal_unsafe_filesystem`: the
    # dangerous configuration is a Linux container writing a macOS host bind-mount, which no
    # same-OS test can create, so the detector is patched exactly as it is there.
    #
    # The store EXISTS (the `writer` fixture made it), so the missing-file error cannot stand in
    # for the refusal — only the guard can raise here.
    monkeypatch.setattr("boardwatch.store.db.unsafe_wal_filesystem", lambda _path: "virtiofs")
    with pytest.raises(WalUnsafeFilesystemError) as excinfo:
        get_readonly_engine(tmp_path)
    assert excinfo.value.fstype == "virtiofs"
    assert "virtiofs" in str(excinfo.value)


def test_reads_see_a_commit_made_by_a_separate_writer_engine(
    writer: Engine, tmp_path: Path
) -> None:
    engine = get_readonly_engine(tmp_path)
    # `probe` was created after WAL was established and has never been checkpointed, so an
    # `immutable=1` opener does not merely read stale rows here — it cannot see the table.
    with engine.connect() as conn:
        assert conn.execute(text("SELECT v FROM probe")).scalars().all() == ["first"]
    with writer.begin() as conn:
        conn.exec_driver_sql("INSERT INTO probe VALUES ('second')")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT v FROM probe")).scalars().all() == ["first", "second"]
    engine.dispose()


def test_a_data_dir_that_uri_syntax_would_mangle_still_opens_the_right_store(
    tmp_path: Path,
) -> None:
    # `#` and a space are legal in a directory name and are both URI syntax. An opener that
    # pastes the path into the URI raw stops reading at the `#` and opens a DIFFERENT, empty
    # database — no error, no rows, no way to tell from a genuinely empty store. Percent-
    # encoding the path is what keeps the URI pointed at the real file.
    data_dir = tmp_path / "Application Support #1"
    data_dir.mkdir()
    writer = get_engine(data_dir)
    with writer.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE probe (v TEXT)")
        conn.exec_driver_sql("INSERT INTO probe VALUES ('first')")
    engine = get_readonly_engine(data_dir)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT v FROM probe")).scalars().all() == ["first"]
    engine.dispose()
    writer.dispose()
