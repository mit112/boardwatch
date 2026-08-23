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

    # The lane company is RELABELLED, not deleted: the narrowed CHECK cannot express 'lane', so
    # a rollback necessarily loses that label — but losing a label is the honest cost of a
    # downgrade, and destroying the postings hanging off it is not. See the migration's own
    # comment; `test_downgrade_does_not_orphan_a_lane_companys_postings` is what pins it.
    assert after_down["slug-lane"][5] == "registry"
    # Both scan rows survive. Once `scan_kind` is dropped a lane row is indistinguishable from a
    # board row by construction, so deleting it would throw away run history to fix a bug the
    # downgraded schema still has.
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM board_scans")).scalar_one() == 2

    # re-upgrade succeeds and the legacy rows are STILL byte-identical
    command.upgrade(cfg, HEAD)
    for slug, row in legacy.items():
        assert _company_snapshot(engine)[slug] == row


def test_downgrade_does_not_orphan_a_lane_companys_postings(tmp_path: Path) -> None:
    """A lane company with postings must survive the rollback with its postings attached.

    This is the case the round-trip above cannot see, because it never inserts a posting — and
    a lane whose whole purpose is to store postings under companies it discovered will always
    have some. `postings.company_id` is a foreign key to `companies.id`, so an earlier
    `DELETE FROM companies WHERE source = 'lane'` orphaned every one of them.

    It would not even have failed loudly. Alembic runs through an engine it builds itself, so
    `store/db.py`'s `PRAGMA foreign_keys=ON` connect listener never fires — the same seam D-269
    records for WAL — and the delete succeeded silently. `PRAGMA foreign_key_check` is asserted
    here rather than a row count, because that is the check that distinguishes "the rows are
    still there" from "the rows are still there and still point at something".
    """
    db = tmp_path / "orphan.db"
    engine = create_engine(f"sqlite:///{db}")
    cfg = _cfg(f"sqlite:///{db}")

    command.upgrade(cfg, HEAD)
    _insert_company(engine, slug="lane-co", source="lane")
    with engine.begin() as conn:
        company_id = conn.execute(
            text("SELECT id FROM companies WHERE slug = 'lane-co'")
        ).scalar_one()
        job_id = conn.execute(
            text("INSERT INTO jobs (created_at) VALUES ('2026-08-23 00:00:00') RETURNING id")
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO postings (company_id, job_id, provider_posting_id, title, "
                "normalized_title, first_seen_at, last_seen_at, status, consecutive_missing, "
                "content_hash, body_text, remote_policy) VALUES (:c, :j, 'p-1', 'Engineer', "
                "'engineer', '2026-08-23 00:00:00', '2026-08-23 00:00:00', 'open', 0, 'h', "
                "'A job.', 'unknown')"
            ),
            {"c": company_id, "j": job_id},
        )

    command.downgrade(cfg, BASE)

    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_key_check")).all() == [], (
            "downgrade left a posting pointing at a company row that no longer exists"
        )
        assert conn.execute(text("SELECT count(*) FROM postings")).scalar_one() == 1
        row = conn.execute(
            text("SELECT source FROM companies WHERE slug = 'lane-co'")
        ).one_or_none()
        assert row is not None, "the lane company was deleted rather than relabelled"
        assert row.source == "registry"
