"""SQLite engine factory and migration runner.

Every connection runs WAL journal mode, a busy_timeout, and
PRAGMA foreign_keys=ON (D20 + round-1 finding 4) via a connect-event hook.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, event

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


def get_engine(data_dir: Path, busy_timeout_ms: int = 5000) -> Engine:
    data_dir.mkdir(parents=True, exist_ok=True)
    if (fstype := unsafe_wal_filesystem(data_dir)) is not None:
        raise WalUnsafeFilesystemError(data_dir, fstype)
    engine = create_engine(f"sqlite:///{data_dir / DB_FILENAME}")

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

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
    command.upgrade(_alembic_config(engine), "head")


def schema_revision() -> str:
    """Head revision of the bundled migration scripts; needs no database."""
    script = ScriptDirectory(str(_MIGRATIONS))
    return script.get_current_head() or "unknown"
