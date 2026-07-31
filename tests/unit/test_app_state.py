"""The digest cursor is a single app_state row. Absent means 0, never None."""

from pathlib import Path

from sqlalchemy import Engine

from boardwatch.store.app_state import get_digest_cursor, set_digest_cursor
from boardwatch.store.db import ensure_schema, get_engine


def _engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def test_cursor_defaults_to_zero_when_unset(tmp_path: Path) -> None:
    with _engine(tmp_path).connect() as conn:
        assert get_digest_cursor(conn) == 0


def test_cursor_round_trips(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    with engine.begin() as conn:
        set_digest_cursor(conn, 42)
    with engine.connect() as conn:
        assert get_digest_cursor(conn) == 42


def test_cursor_write_is_idempotent_upsert(tmp_path: Path) -> None:
    """A second write updates the one row rather than failing on the text PK."""
    engine = _engine(tmp_path)
    with engine.begin() as conn:
        set_digest_cursor(conn, 42)
        set_digest_cursor(conn, 99)
    with engine.connect() as conn:
        assert get_digest_cursor(conn) == 99


def test_cursor_is_monotonic_never_lowers(tmp_path: Path) -> None:
    """A1: set_digest_cursor must never lower a stored value. 99 then 42 leaves 99."""
    engine = _engine(tmp_path)
    with engine.begin() as conn:
        set_digest_cursor(conn, 99)
        set_digest_cursor(conn, 42)
    with engine.connect() as conn:
        assert get_digest_cursor(conn) == 99
