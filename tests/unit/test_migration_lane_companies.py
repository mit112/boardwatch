"""D-285 migration: `companies.source` gains `'lane'`, `board_scans` gains `scan_kind`.

Both are CHECK-constraint changes, so both need a SQLite table rebuild, and a rebuild is where
data quietly goes missing. Proven on a POPULATED DB in both directions: every pre-existing row
survives byte-identical (PK included), the widened value inserts, an off-catalog value is still
rejected on BOTH sides, and the downgrade genuinely re-narrows rather than just dropping the
constraint.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, OperationalError

BASE = "p_board_coverage"  # the head this revision stacks on
HEAD = "p_lane_companies"
MIGRATIONS = Path("src/boardwatch/store/migrations")

_COMPANY_COLS = "name, provider, slug, tags_json, source, watched, last_health, last_ok_at"
_COMPANY_SNAP = "id, " + _COMPANY_COLS


def _cfg(db_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _insert_company(engine, *, slug: str, source: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                f"INSERT INTO companies ({_COMPANY_COLS}) VALUES "
                "(:n, 'greenhouse', :s, NULL, :src, 1, 'ok', '2026-01-01 00:00:00')"
            ),
            {"n": slug.title(), "s": slug, "src": source},
        )


def _company_snapshot(engine) -> dict[str, tuple]:
    with engine.connect() as conn:
        rows = conn.execute(text(f"SELECT {_COMPANY_SNAP} FROM companies ORDER BY slug")).all()
    return {r.slug: tuple(r) for r in rows}


def _seed_run(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO runs (id, started_at, boards_attempted) VALUES (1, :t, 0)"),
            {"t": "2026-01-01 00:00:00"},
        )


def _insert_scan(engine, *, company_slug: str, scan_kind: str | None = None) -> None:
    """`scan_kind=None` writes the pre-migration row shape — no such column mentioned."""
    cols = "run_id, company_id, started_at, finished_at, status, postings_listed"
    vals = "1, (SELECT id FROM companies WHERE slug = :s), :t, :t, 'complete', 0"
    if scan_kind is not None:
        cols += ", scan_kind"
        vals += ", :k"
    with engine.begin() as conn:
        conn.execute(
            text(f"INSERT INTO board_scans ({cols}) VALUES ({vals})"),
            {"s": company_slug, "t": "2026-01-01 00:00:00", "k": scan_kind},
        )


def _scan_kinds(engine) -> list[str]:
    with engine.connect() as conn:
        return [r[0] for r in conn.execute(text("SELECT scan_kind FROM board_scans ORDER BY id"))]


def test_lane_source_and_scan_kind_round_trip(tmp_path: Path) -> None:
    db = tmp_path / "rt.db"
    url = f"sqlite:///{db}"
    cfg = _cfg(url)
    engine = create_engine(url)

    # base: the two legacy sources insert, 'lane' is rejected, and scan_kind does not exist yet
    command.upgrade(cfg, BASE)
    _seed_run(engine)
    for source in ("registry", "user"):
        _insert_company(engine, slug=f"slug-{source}", source=source)
    with pytest.raises(IntegrityError):
        _insert_company(engine, slug="slug-lane", source="lane")
    _insert_scan(engine, company_slug="slug-registry")
    with pytest.raises(OperationalError):  # no such column
        _scan_kinds(engine)
    legacy = _company_snapshot(engine)

    # head: legacy rows byte-identical, 'lane' now insertable, a bogus source still rejected
    command.upgrade(cfg, HEAD)
    assert _company_snapshot(engine) == legacy
    _insert_company(engine, slug="slug-lane", source="lane")
    with pytest.raises(IntegrityError):
        _insert_company(engine, slug="slug-bogus", source="aggregator")

    # the pre-existing scan row defaults to 'board' — every row written before this migration
    # WAS a board scan, so the default states a fact rather than guessing one
    assert _scan_kinds(engine) == ["board"]
    _insert_scan(engine, company_slug="slug-lane", scan_kind="lane")
    assert _scan_kinds(engine) == ["board", "lane"]
    with pytest.raises(IntegrityError):
        _insert_scan(engine, company_slug="slug-registry", scan_kind="aggregator")

    # downgrade: the column is gone, the CHECK genuinely re-narrows (not merely dropped), and
    # the two legacy companies are still byte-identical
    command.downgrade(cfg, BASE)
    with pytest.raises(OperationalError):
        _scan_kinds(engine)
    with pytest.raises(IntegrityError):
        _insert_company(engine, slug="slug-lane-again", source="lane")
    after_down = _company_snapshot(engine)
    for slug, row in legacy.items():
        assert after_down[slug] == row, f"{slug} changed across the round trip"

    # the widened schema's rows cannot survive the narrowing as silently illegal data
    assert "slug-lane" not in after_down
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM board_scans")).scalar_one() == 1

    # re-upgrade succeeds and the legacy rows are STILL byte-identical
    command.upgrade(cfg, HEAD)
    for slug, row in legacy.items():
        assert _company_snapshot(engine)[slug] == row
