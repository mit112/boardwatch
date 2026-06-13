"""D27 migration: last_health_enum widens to five values; downgrade remaps
unreachable -> error before re-narrowing. Proven on a POPULATED DB in both
directions (the P0 suite only has a metadata-comparison test)."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

BASE = "8df3b3809bba"  # schema v1 baseline
HEAD = "b7e41c0a9f23"  # this migration
MIGRATIONS = Path("src/boardwatch/store/migrations")


def _cfg(db_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


# INSERT omits id (autoincrement); SNAPSHOT includes id so "every column" / byte-identity
# is proven across the batch table-recreate (PK survival included)
_INSERT_COLS = "name, provider, slug, tags_json, source, watched, last_health, last_ok_at"
_SNAP_COLS = "id, " + _INSERT_COLS  # 9 cols; last_health at index 7, last_ok_at at index 8
# distinct last_ok_at per legacy row so the "untouched on downgrade" claim is real
_OK_AT = {"ok": "2026-01-01 00:00:00", "empty": "2026-02-02 00:00:00",
          "dead": "2026-03-03 00:00:00", "error": "2026-04-04 00:00:00",
          "unreachable": "2026-05-05 00:00:00"}


def _insert(engine, health: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                f"INSERT INTO companies ({_INSERT_COLS}) VALUES "
                "(:n, 'greenhouse', :s, NULL, 'user', 1, :h, :ok)"
            ),
            {"n": health.title(), "s": f"slug-{health}", "h": health, "ok": _OK_AT[health]},
        )


def _snapshot(engine) -> dict[str, tuple]:
    with engine.connect() as conn:
        rows = conn.execute(text(f"SELECT {_SNAP_COLS} FROM companies ORDER BY slug")).all()
    return {r.slug: tuple(r) for r in rows}  # tuple includes id — PK survival is proven


def test_last_health_round_trip(tmp_path: Path) -> None:
    db = tmp_path / "rt.db"
    url = f"sqlite:///{db}"
    cfg = _cfg(url)
    engine = create_engine(url)

    # base: the four legacy values insert; unreachable is rejected
    command.upgrade(cfg, BASE)
    for value in ("ok", "empty", "dead", "error"):
        _insert(engine, value)
    with pytest.raises(IntegrityError):
        _insert(engine, "unreachable")
    legacy = _snapshot(engine)  # every column of all four seeded rows

    # (a) head: all four legacy rows byte-identical (every column), unreachable now insertable
    command.upgrade(cfg, HEAD)
    assert _snapshot(engine) == legacy  # full-row equality, not just slug/health
    _insert(engine, "unreachable")  # last_ok_at = _OK_AT['unreachable']

    # (b)(c) downgrade: the four legacy rows still byte-identical (last_ok_at untouched);
    #        the seeded unreachable row became 'error'; the narrowed schema rejects unreachable
    command.downgrade(cfg, BASE)
    after_down = _snapshot(engine)
    for slug, row in legacy.items():
        assert after_down[slug] == row, f"{slug} changed across the round trip"
    assert after_down["slug-unreachable"][7] == "error"      # last_health remapped (index 7 w/ id)
    assert after_down["slug-unreachable"][8] == "2026-05-05 00:00:00"  # last_ok_at preserved
    with pytest.raises(IntegrityError):
        _insert(engine, "unreachable")

    # (d) re-upgrade succeeds and the legacy rows are still byte-identical
    command.upgrade(cfg, HEAD)
    for slug, row in legacy.items():
        assert _snapshot(engine)[slug] == row
