"""`upsert_lane_company` / `company_exists` — the two store calls a lane runner needs (D-285).

The load-bearing claim is what the upsert does NOT do. A lane sees hundreds of aggregator hits
per run and many of them are boards the user already watches; if the upsert wrote its own
`watched`/`source` on conflict it would silently unwatch a watched board and relabel a shipped
registry company as lane-discovered. Neither is recoverable from the store afterwards, because
nothing records what the row said before.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError

from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import (
    company_exists,
    upsert_lane_company,
    upsert_watch,
)
from boardwatch.store.tables import companies


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def _row(engine: Engine, *, provider: str, slug: str):
    with engine.connect() as conn:
        return conn.execute(
            select(companies).where(companies.c.provider == provider, companies.c.slug == slug)
        ).one()


def test_a_lane_company_is_stored_unwatched_and_sourced_lane(engine: Engine) -> None:
    """Watched would put `hiringcafe` in the scan corpus, where `scan/coordinator` cannot find
    a provider for it and appends an `unknown provider` error to EVERY run, forever."""
    with engine.begin() as conn:
        upsert_lane_company(conn, provider="hiringcafe", slug="greenhouse:acme", name="Acme")
    row = _row(engine, provider="hiringcafe", slug="greenhouse:acme")
    assert row.source == "lane"
    assert row.watched is False
    assert row.name == "Acme"


def test_upserting_over_a_watched_registry_company_changes_neither_flag(engine: Engine) -> None:
    """The convergence case: the lane surfaces a greenhouse board the user already watches."""
    with engine.begin() as conn:
        upsert_watch(
            conn, provider="greenhouse", slug="acme", name="Acme", source="registry"
        )
    with engine.begin() as conn:
        upsert_lane_company(conn, provider="greenhouse", slug="acme", name="Acme Inc.")
    row = _row(engine, provider="greenhouse", slug="acme")
    assert row.watched is True, "a lane must never unwatch a board the user watches"
    assert row.source == "registry", "a lane must never relabel a registry company"
    assert row.name == "Acme Inc.", "the display name carries no provenance and stays current"


def test_upserting_a_lane_company_twice_is_idempotent(engine: Engine) -> None:
    for _ in range(2):
        with engine.begin() as conn:
            upsert_lane_company(conn, provider="hiringcafe", slug="lever:beta", name="Beta")
    with engine.connect() as conn:
        assert len(conn.execute(select(companies)).all()) == 1


def test_the_source_check_constraint_still_rejects_an_unknown_value(engine: Engine) -> None:
    """The catalog widened by exactly one value; it did not open."""
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            upsert_watch(
                conn, provider="greenhouse", slug="gamma", name="Gamma", source="aggregator"
            )


def test_company_exists_sees_unwatched_rows(engine: Engine) -> None:
    """The whole point: `get_watched_companies` would answer False here, so the cap would
    charge a slot to this company on every single run and reach would never widen."""
    with engine.begin() as conn:
        upsert_lane_company(conn, provider="hiringcafe", slug="ashby:delta", name="Delta")
        assert company_exists(conn, provider="hiringcafe", slug="ashby:delta") is True
        assert company_exists(conn, provider="hiringcafe", slug="ashby:absent") is False


def test_company_exists_is_keyed_on_the_pair_not_the_slug(engine: Engine) -> None:
    with engine.begin() as conn:
        upsert_lane_company(conn, provider="hiringcafe", slug="acme", name="Acme")
        assert company_exists(conn, provider="greenhouse", slug="acme") is False
