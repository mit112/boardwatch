"""`upsert_lane_company` / `company_exists` — the two store calls a lane runner needs (D-285).

The load-bearing claim is what the upsert does NOT do. A lane sees hundreds of aggregator hits
per run and many of them are boards the user already watches; if the upsert wrote its own
`watched`/`source`/`name` on conflict it would silently unwatch a watched board, relabel a
shipped registry company as lane-discovered, and re-key that company's posting identities
(`companies.name` is a `cross_host` identity component). None of the three is recoverable from
the store afterwards, because nothing records what the row said before.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError

from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import (
    company_exists,
    get_watched_companies,
    unwatch,
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
    assert row.name == "Acme", "an aggregator's rendering must not overwrite a curated name"


def test_the_name_is_never_overwritten_because_it_keys_posting_identities(
    engine: Engine,
) -> None:
    """`scan/apply.py` feeds `companies.name` into `IdentityInputs.company_name`, a component
    of the `cross_host` posting identity. An upsert that refreshed the name would silently
    re-key every identity that company already has, for a cosmetic gain."""
    with engine.begin() as conn:
        upsert_watch(
            conn, provider="greenhouse", slug="acme", name="Acme Corporation", source="registry"
        )
    with engine.begin() as conn:
        upsert_lane_company(conn, provider="greenhouse", slug="acme", name="acme")
    assert _row(engine, provider="greenhouse", slug="acme").name == "Acme Corporation"


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


# --------------------------------------------------------------------------------------
# Slug case — `UNIQUE(provider, slug)` is case-SENSITIVE, so it is not the guard
# --------------------------------------------------------------------------------------


def test_a_lane_slug_differing_only_in_case_reuses_the_stored_row(engine: Engine) -> None:
    """The live incident. `ashby:Lightfield` and `ashby:lightfield` were ONE board: the same 19
    open postings under the same Ashby posting UUIDs, both rows watched, the board fetched twice
    a run — and no identity kind could suppress the duplicate postings, because every one of them
    is scoped by `company_id` and there were two.

    The id is asserted, not just the row count: the caller applies a board against it, so
    resolving to the stored row but reporting a different id would still split the corpus.
    """
    with engine.begin() as conn:
        upsert_watch(
            conn, provider="ashby", slug="Lightfield", name="Lightfield", source="user"
        )
    original = _row(engine, provider="ashby", slug="Lightfield").id
    with engine.begin() as conn:
        landed = upsert_lane_company(conn, provider="ashby", slug="lightfield", name="Lightfield")
    assert landed == original
    with engine.connect() as conn:
        rows = conn.execute(select(companies.c.slug)).scalars().all()
    assert rows == ["Lightfield"], "the case variant was stored as a second company row"


def test_a_watch_on_a_case_variant_lands_on_the_stored_row_and_says_so(engine: Engine) -> None:
    """`companies add ashby:KAYAK` with `ashby:kayak` already watched. A silent no-op is the
    wrong outcome: the caller has to be able to tell the operator which row the watch hit."""
    with engine.begin() as conn:
        upsert_lane_company(conn, provider="ashby", slug="kayak", name="Kayak")
    with engine.begin() as conn:
        assert upsert_watch(
            conn, provider="ashby", slug="KAYAK", name="KAYAK", source="user"
        ) == "kayak"
    row = _row(engine, provider="ashby", slug="kayak")
    assert row.watched is True, "the existing row was not watched"
    with engine.connect() as conn:
        assert len(conn.execute(select(companies)).all()) == 1


def test_two_slugs_that_differ_by_more_than_case_are_two_companies(engine: Engine) -> None:
    """The guard folds case and NOTHING else. Without this, `stored_slug` could 'fix' the
    duplicate by matching too widely and quietly cost the user a board."""
    with engine.begin() as conn:
        upsert_watch(conn, provider="ashby", slug="Lightfield", name="A", source="user")
        upsert_watch(conn, provider="ashby", slug="lightfields", name="B", source="user")
    with engine.connect() as conn:
        assert set(conn.execute(select(companies.c.slug)).scalars().all()) == {
            "Lightfield", "lightfields",
        }


def test_company_exists_ignores_slug_case(engine: Engine) -> None:
    """The lane budget's is-new check. Answering True here is what stops a company the store
    already holds from spending one of the run's ten new-company slots."""
    with engine.begin() as conn:
        upsert_watch(conn, provider="ashby", slug="Lightfield", name="L", source="user")
        assert company_exists(conn, provider="ashby", slug="lightfield") is True
        assert company_exists(conn, provider="ashby", slug="LIGHTFIELD") is True
        assert company_exists(conn, provider="ashby", slug="lightfields") is False
        assert company_exists(conn, provider="greenhouse", slug="lightfield") is False


def test_get_watched_companies_filters_slug_case_insensitively(engine: Engine) -> None:
    """The `--company` filter reaches the store through this, so `--company KAYAK` must find the
    board stored as `kayak` — otherwise a board added by one case is un-scannable by another
    (D-339 loose end). Case folds and nothing else: `kayaks` stays a different board."""
    with engine.begin() as conn:
        upsert_watch(conn, provider="ashby", slug="kayak", name="Kayak", source="user")
    with engine.connect() as conn:
        assert [r.slug for r in get_watched_companies(conn, slug="KAYAK")] == ["kayak"]
        assert get_watched_companies(conn, slug="kayaks") == []


def test_unwatch_resolves_slug_case_the_same_way_the_watch_did(engine: Engine) -> None:
    """`add` now lands a case variant on the stored row, so `remove` must reach the same row —
    otherwise a board the operator just added by typing `KAYAK` can never be removed by it."""
    with engine.begin() as conn:
        upsert_watch(conn, provider="ashby", slug="kayak", name="Kayak", source="user")
    with engine.begin() as conn:
        assert unwatch(conn, provider="ashby", slug="KAYAK") == 1
    assert _row(engine, provider="ashby", slug="kayak").watched is False


def test_unwatch_still_reports_nothing_for_a_slug_the_store_does_not_hold(
    engine: Engine,
) -> None:
    with engine.begin() as conn:
        upsert_watch(conn, provider="ashby", slug="kayak", name="Kayak", source="user")
        assert unwatch(conn, provider="ashby", slug="kayaks") == 0
