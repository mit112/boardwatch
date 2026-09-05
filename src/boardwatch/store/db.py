"""SQLite engine factory and migration runner.

Every connection runs WAL journal mode, a busy_timeout, and
PRAGMA foreign_keys=ON (D20 + round-1 finding 4) via a connect-event hook.

Every connection also emits its own BEGIN, via the connect/begin listener pair SQLAlchemy
documents for pysqlite. Left to the driver, pysqlite opens a transaction only on the first DML
statement, so the reads of a read-then-write sequence run in autocommit and each one sees its
own snapshot -- a concurrent writer can land between them and the second read disagrees with the
first. D-426 met that as a wrong number in one report and answered it at that one site; this is
the engine-level answer, and the two hand-written BEGIN IMMEDIATE sites were retired with it.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine, create_engine, event, text
from sqlalchemy.exc import OperationalError

from boardwatch.store.fs_safety import unsafe_wal_filesystem

DB_FILENAME = "boardwatch.db"
_MIGRATIONS = Path(__file__).parent / "migrations"


class WalUnsafeFilesystemError(RuntimeError):
    """The store's directory is on a filesystem where WAL cannot hold its locks (D-241).

    Typed at the raise site so callers never classify it by string-matching the message.
    """

    def __init__(self, data_dir: Path, fstype: str) -> None:
        self.data_dir = data_dir
        self.fstype = fstype
        super().__init__(
            f"the store at {data_dir} is on a {fstype!r} filesystem, where SQLite's WAL "
            "journaling cannot hold its locks and concurrent writers can corrupt the database. "
            "Put the store on local disk, or use a named Docker volume "
            "(docker run -v boardwatch-data:/data …) rather than a host bind-mount."
        )


#: The three modes SQLite's BEGIN accepts, as a closed catalog. The `begin` listener
#: interpolates the chosen one into a statement, so nothing outside this set can reach the
#: driver: an unknown mode is a typed refusal at the raise site, never a new bucket.
BEGIN_MODES = frozenset({"DEFERRED", "IMMEDIATE", "EXCLUSIVE"})

#: Execution-option name through which a caller chooses its transaction's begin mode. An
#: execution option rather than a second engine factory, because the mode is a property of one
#: unit of work and not of the store: the runner reads and writes through the same engine.
BEGIN_MODE_OPTION = "boardwatch_begin_mode"


class UnknownBeginModeError(ValueError):
    """A caller asked for a begin mode outside `BEGIN_MODES`."""

    def __init__(self, mode: object) -> None:
        self.mode = mode
        super().__init__(
            f"{mode!r} is not a SQLite begin mode; expected one of {sorted(BEGIN_MODES)}"
        )


def _install_begin_hook(engine: Engine, *, writable: bool) -> None:
    """Emit BEGIN ourselves on every transaction this engine opens.

    `writable` decides whether the `BEGIN_MODE_OPTION` execution option is honoured at all. A
    read-only engine opens its file with `mode=ro` and sets `query_only=ON`, so BEGIN IMMEDIATE
    -- which takes SQLite's write lock up front -- could only ever fail there; refusing to read
    the option keeps that failure from depending on which engine a caller happened to be handed.
    """

    @event.listens_for(engine, "begin")
    def _emit_begin(conn: Connection) -> None:
        mode = "DEFERRED"
        if writable:
            requested = conn.get_execution_options().get(BEGIN_MODE_OPTION, "DEFERRED")
            if requested not in BEGIN_MODES:
                raise UnknownBeginModeError(requested)
            mode = str(requested)
        conn.exec_driver_sql(f"BEGIN {mode}")


def write_connection(engine: Engine) -> Connection:
    """A connection whose transaction takes SQLite's write lock at BEGIN, not at first write.

    Deferred is right for the common case -- a run's reads must not lock out the CLI or the web
    viewer -- but it is wrong for a read-modify-write of a cursor or a counter: two of those
    interleave their reads, then the second one's COMMIT fails with SQLITE_BUSY instead of
    queueing on `busy_timeout`. Callers that read a value in order to replace it take this
    instead, which is what the two hand-written `BEGIN IMMEDIATE` statements used to buy.
    """
    return engine.connect().execution_options(**{BEGIN_MODE_OPTION: "IMMEDIATE"})


def get_engine(data_dir: Path, busy_timeout_ms: int = 5000) -> Engine:
    data_dir.mkdir(parents=True, exist_ok=True)
    if (fstype := unsafe_wal_filesystem(data_dir)) is not None:
        raise WalUnsafeFilesystemError(data_dir, fstype)
    engine = create_engine(f"sqlite:///{data_dir / DB_FILENAME}")

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection: Any, _record: Any) -> None:
        # Hand the transaction to `_install_begin_hook`. Python's sqlite3 driver otherwise
        # opens one implicitly before DML and never before a SELECT, which is the whole
        # defect; `None` is its "issue no BEGIN of your own" setting, not "never transact".
        # It also makes the WAL pragma below unconditionally safe: a journal-mode change is
        # refused inside a transaction, and with the driver's implicit BEGIN disabled there
        # can never be one open here.
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    _install_begin_hook(engine, writable=True)
    return engine


def _alembic_config(engine: Engine) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", engine.url.render_as_string(hide_password=False))
    return cfg


def ensure_schema(engine: Engine) -> None:
    """Apply all migrations to head (idempotent), with WAL established first."""
    # Open one connection through `engine` before alembic runs, purely so `_set_pragmas` fires
    # while this is still the only connection. Alembic builds its OWN engine from the URL, so it
    # never triggers that listener; without this the database is CREATED in `delete` mode and the
    # switch to WAL is deferred to whichever connection happens to run first.
    #
    # That deferred switch is a journal-mode CONVERSION, and no lock held by any other connection
    # permits one: measured against a competing reader it returns "database is locked" only after
    # the full busy timeout, and against a competing writer it returns instantly, with the busy
    # handler never invoked. So two processes opening a fresh store race, and the loser fails to
    # open it at all. Establishing WAL at creation makes every later `PRAGMA journal_mode=WAL` the
    # cheap no-op it was always assumed to be.
    with engine.connect():
        pass
    # The fresh-schema shortcut (T16). TEST-ONLY, behind an explicit switch, and additionally
    # guarded by the database being completely empty — so a real store migrates whatever the
    # environment says. It replays the DDL a real migration run produced (`_schema_template`),
    # which is 32x faster than the chain (92.9 ms -> 2.9 ms per fresh store, measured) and
    # produces a BYTE-IDENTICAL schema.
    #
    # `metadata.create_all` — the shape the ticket proposed — is NOT used, and the reason is
    # measured rather than argued: it emits ZERO of the schema's 20 triggers, including the ten
    # append-only `RAISE(ABORT)` pairs the eligibility keystone rests on and both
    # `postings_job_required_*` triggers. `test_migrations_match_metadata` cannot catch that:
    # alembic's `compare_metadata` compares tables, columns, indexes and types, and does not
    # see triggers at all. Every test would have run against a schema missing the invariants
    # its fixtures assume, which is the failure mode a fast path must not introduce.
    if os.environ.get(FAST_SCHEMA_ENV) and _is_empty_database(engine):
        statements, revision = _schema_template()
        with engine.begin() as conn:
            for statement in statements:
                conn.exec_driver_sql(statement)
            conn.exec_driver_sql("DELETE FROM alembic_version")
            conn.exec_driver_sql(
                "INSERT INTO alembic_version (version_num) VALUES (?)", (revision,)
            )
        return
    # Alembic's own engine carries neither listener, so migrations keep the driver's default
    # transaction handling. That is deliberate: `command.upgrade` runs alone, one migration at a
    # time, and owns its transactions -- there is no read-then-write to interleave with.
    command.upgrade(_alembic_config(engine), "head")


#: Test-only switch for the fresh-schema shortcut below. Set by `tests/conftest.py` and by
#: nothing else; no CLI path reads or writes it. Even if it leaked into a real environment the
#: shortcut still refuses any database that is not completely empty, so a production store
#: always migrates.
FAST_SCHEMA_ENV = "BOARDWATCH_TEST_FAST_SCHEMA"

#: The migrated schema's own DDL, captured once per process. `None` until first use.
_SCHEMA_TEMPLATE: tuple[tuple[str, ...], str] | None = None


def _schema_template() -> tuple[tuple[str, ...], str]:
    """Every DDL statement of a fully migrated store, plus its alembic revision.

    DERIVED from the migration chain, never restated: this runs the real `command.upgrade` once,
    into a throwaway file, and reads back what SQLite actually holds. So it cannot drift from the
    migrations the way a second hand-written schema would — a new migration changes this the next
    time a process starts, with nothing to remember to update.

    `sqlite_%` names are excluded because SQLite owns them: `sqlite_sequence` is created
    implicitly by AUTOINCREMENT and refuses an explicit CREATE ("object name reserved for
    internal use").
    """
    global _SCHEMA_TEMPLATE
    if _SCHEMA_TEMPLATE is None:
        with tempfile.TemporaryDirectory() as scratch:
            engine = get_engine(Path(scratch))
            with engine.connect():
                pass
            command.upgrade(_alembic_config(engine), "head")
            with engine.connect() as conn:
                statements = tuple(
                    str(row[0])
                    for row in conn.execute(
                        text(
                            "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL "
                            "AND name NOT LIKE 'sqlite_%'"
                        )
                    )
                )
                revision = str(
                    conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                )
            engine.dispose()
        _SCHEMA_TEMPLATE = (statements, revision)
    return _SCHEMA_TEMPLATE


def _is_empty_database(engine: Engine) -> bool:
    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")
        ).scalar_one()
    return int(count) == 0


def schema_revision() -> str:
    """Head revision of the bundled migration scripts; needs no database."""
    script = ScriptDirectory(str(_MIGRATIONS))
    return script.get_current_head() or "unknown"


def db_revision(conn: Connection) -> str | None:
    """The DB's applied Alembic revision, or None if the DB is unversioned/uninitialized.

    Beside `schema_revision()` because the only useful thing to do with either is compare it
    with the other. It was previously private to `cli/doctor_cmd.py`, which forced every other
    caller into a `cli` -> `cli` import of a `_`-prefixed name for what is a plain store probe.
    """
    try:
        result = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    except OperationalError:  # alembic_version table absent -> schema never applied
        return None
    return str(result) if result is not None else None


def get_readonly_engine(data_dir: Path, busy_timeout_ms: int = 5000) -> Engine:
    """Open an EXISTING store read-only, for a caller that must never write it.

    A separate function rather than a flag on `get_engine`, because three of that function's
    four steps are writes — the `mkdir`, the read-write open, and `journal_mode=WAL` — so a
    shared body would be a branch on every line. Every difference from it is deliberate and
    load-bearing, and each is annotated below with what goes wrong without it.
    """
    # KEPT from `get_engine`, not skipped. Reading a WAL database is not a bystander operation:
    # SQLite serves the read through the -shm shared-memory segment and POSIX advisory locks,
    # and creates the -shm itself when it is absent. Those are precisely the primitives that do
    # not hold across the filesystems this guard refuses (D-241), so a read-only opener that
    # cleared the check would silently permit the exact configuration the check exists to catch.
    if (fstype := unsafe_wal_filesystem(data_dir)) is not None:
        raise WalUnsafeFilesystemError(data_dir, fstype)

    # NO `mkdir`. An opener that creates the store it is supposed to only read is a bug: the
    # caller asked to read a store, and a fresh empty directory answers that request with a
    # silence indistinguishable from an empty database. The absence is raised here rather than
    # left to the first connection because SQLite reports a missing file as `unable to open
    # database file`, which reads like a permissions fault and sends the operator the wrong way.
    db_path = (data_dir / DB_FILENAME).resolve()
    if not db_path.is_file():
        raise FileNotFoundError(f"no {DB_FILENAME} at {db_path}: nothing has written a store yet")

    # A read-only SQLite URI, through the DBAPI's `uri=True` — which SQLAlchemy's pysqlite
    # dialect enables from `uri=true` in the query string, and only from there, never from
    # `connect_args`. This is the one route that reads both a live store and a cleanly
    # checkpointed one: the `sqlite3` CLI fails SQLITE_CANTOPEN(14) when the -shm is absent, and
    # `immutable=1` skips the WAL altogether, answering from the last checkpoint — measured,
    # that reports `no such table` for a table whose CREATE is still in the WAL.
    #
    # `mode=ro` belongs in the URL and not in a `creator=` callable, because read-only-ness has
    # to survive a re-parse: `ensure_schema` renders `engine.url` and hands the string to
    # alembic, which builds its OWN engine from it and would migrate the very store this opener
    # promised only to read.
    #
    # `as_uri()` rather than an f-string of the path, because SQLite percent-decodes a URI
    # filename: a raw `#` or `?` anywhere in the data dir truncates it there and opens a
    # DIFFERENT, empty database without complaint. Measured on both characters.
    engine = create_engine(f"sqlite:///{db_path.as_uri()}?mode=ro&uri=true")

    @event.listens_for(engine, "connect")
    def _set_readonly_pragmas(dbapi_connection: Any, _record: Any) -> None:
        # Same reason as `get_engine`: without this the driver issues no BEGIN for a SELECT,
        # so each read of a multi-read request answers from its own snapshot. The viewer reads
        # a run's counts and its rows in one request, and they must agree.
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        # NO `journal_mode=WAL`: that pragma is a write, and against an existing store it can be
        # a journal-mode CONVERSION, which is the one operation no other connection's lock
        # permits to wait (see the note in `ensure_schema`).
        #
        # busy_timeout is treated exactly as `get_engine` treats it: same parameter, same
        # default, set on every connection. A read is not exempt from SQLITE_BUSY — it queues
        # behind a checkpointer or behind a writer holding an exclusive lock. Setting it here is
        # also what makes the parameter mean anything at all: Python's sqlite3 driver applies a
        # 5000 ms timeout of its own, so without this line the argument is silently ignored.
        cursor.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
        cursor.execute("PRAGMA foreign_keys=ON")
        # Inherited unchanged above, so the pragma set differs from `get_engine`'s only by the
        # writes. `query_only` is the addition: `mode=ro` refuses the write at the file, this
        # refuses the statement at the connection, so a stray write fails in the process that
        # issued it instead of depending on how the file happened to be opened.
        cursor.execute("PRAGMA query_only=ON")
        cursor.close()

    _install_begin_hook(engine, writable=False)
    return engine
