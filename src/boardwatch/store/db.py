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

DB_FILENAME = "boardwatch.db"
_MIGRATIONS = Path(__file__).parent / "migrations"


def get_engine(data_dir: Path, busy_timeout_ms: int = 5000) -> Engine:
    data_dir.mkdir(parents=True, exist_ok=True)
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
    """Apply all migrations to head (idempotent)."""
    command.upgrade(_alembic_config(engine), "head")


def schema_revision() -> str:
    """Head revision of the bundled migration scripts; needs no database."""
    script = ScriptDirectory(str(_MIGRATIONS))
    return script.get_current_head() or "unknown"
