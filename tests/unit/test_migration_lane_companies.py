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
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError

from boardwatch.core.models import BoardSnapshot, RawPosting
from boardwatch.scan.apply import apply_board
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import insert_run, upsert_lane_company
from boardwatch.store.tables import board_scans, companies, postings

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

    # the lane company is RELABELLED, not deleted — the narrowed schema cannot hold the label,
    # but it holds the company, and `postings.company_id` points at it
    assert after_down["slug-lane"][5] == "registry"  # source, index 5 with id prepended
    # and both scan rows survive: after the column is dropped a lane row is indistinguishable
    # from a board row by construction, which is the state being rolled back to
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM board_scans")).scalar_one() == 2

    # re-upgrade succeeds and the legacy rows are STILL byte-identical
    command.upgrade(cfg, HEAD)
    for slug, row in legacy.items():
        assert _company_snapshot(engine)[slug] == row


def test_downgrade_keeps_a_lane_companys_postings(tmp_path: Path) -> None:
    """The rollback must not take the lane's POSTINGS down with the lane's companies.

    `postings.company_id` is a foreign key to `companies.id`, and postings under lane-discovered
    companies are the entire yield of a lane run. Alembic builds its own engine, so `store/db.py`'s
    `PRAGMA foreign_keys=ON` connect listener never fires for a migration (D-269) — measured here:
    a `DELETE FROM companies WHERE source = 'lane'` raises nothing and leaves every posting
    pointing at an id that no longer exists. Silent orphaning, which nothing reports.

    Seeded through the real `apply_board` rather than by hand, so the `jobs`, `posting_versions`,
    `posting_version_sources`, `posting_events` and `posting_identities` rows a lane run actually
    leaves behind are all present and all in the blast radius.
    """
    data_dir = tmp_path / "data"
    engine = get_engine(data_dir)
    ensure_schema(engine)
    cfg = _cfg(f"sqlite:///{data_dir / 'boardwatch.db'}")

    with engine.begin() as conn:
        upsert_lane_company(conn, provider="hiringcafe", slug="greenhouse:acme", name="Acme")
        company_id = int(
            conn.execute(
                select(companies.c.id).where(companies.c.slug == "greenhouse:acme")
            ).scalar_one()
        )
    run_id = insert_run(engine)
    apply_board(
        engine,
        BoardSnapshot(
            status="partial",
            url="https://hiringcafe.example/",
            postings=[
                RawPosting(
                    provider_posting_id="hc-1", title="Software Engineer",
                    url="https://boards.greenhouse.io/acme/jobs/1", locations=["Boston, MA"],
                    body_text="Requirements: build things.", raw_json={},
                )
            ],
        ),
        company_id,
        run_id,
        scan_kind="lane",
    )
    with engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(postings)).scalar_one() == 1

    command.downgrade(cfg, BASE)

    with engine.connect() as conn:
        orphans = conn.execute(
            text(
                "SELECT p.id FROM postings p LEFT JOIN companies c ON c.id = p.company_id "
                "WHERE c.id IS NULL"
            )
        ).all()
        assert orphans == [], "the downgrade orphaned postings under a deleted company"
        assert conn.execute(select(func.count()).select_from(postings)).scalar_one() == 1
        # The narrowed schema cannot EXPRESS lane provenance, so the label is necessarily lost.
        # Losing the label is inherent to the rollback; losing the postings is not.
        assert conn.execute(
            select(companies.c.source).where(companies.c.id == company_id)
        ).scalar_one() == "registry"
        # Run history survives too: after the column is dropped a lane row is indistinguishable
        # from a board row by construction, which is precisely the state being rolled back to.
        assert conn.execute(select(func.count()).select_from(board_scans)).scalar_one() == 1
