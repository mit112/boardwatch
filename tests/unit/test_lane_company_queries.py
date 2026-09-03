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
    watched_company_names,
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


def test_a_workday_lane_find_converges_despite_a_different_career_site_case(
    engine: Engine,
) -> None:
    """The composite-slug case, pinned separately from `ashby:Lightfield` because a plausible
    and WRONG reading of the codebase says it does not hold.

    `workday.split_slug` preserves the career site's case, and it used to justify that by
    claiming Workday sites are case-sensitive live. Read together with the case-SENSITIVE
    `UNIQUE(provider, slug)`, that invites the conclusion that a lane find spelling the site
    `NVIDIAExternalCareerSite` mints a duplicate beside a board stored
    `nvidiaexternalcareersite` and converges with nothing. **It does not** — `stored_slug` folds
    case before the insert is ever attempted, and `pipeline/runner.py` takes the company id back
    from the upsert rather than re-selecting on its own spelling, precisely so this works.

    That wrong reading was acted on once: it produced a sized proposal to lowercase every stored
    Workday slug, with a migration and 54 forced refetches, to buy a convergence the store was
    already delivering. This test is what makes the next reader stop at a red bar instead.

    Asserted on the composite form specifically: host and tenant are lowercased by `split_slug`
    while the site is not, so a Workday slug is the one provider where a stored row and a lane
    spelling can differ in exactly one of three components.
    """
    stored = "nvidia.wd5.myworkdayjobs.com/nvidia/nvidiaexternalcareersite"
    lane_spelling = "nvidia.wd5.myworkdayjobs.com/nvidia/NVIDIAExternalCareerSite"
    with engine.begin() as conn:
        upsert_watch(conn, provider="workday", slug=stored, name="NVIDIA", source="user")
    original = _row(engine, provider="workday", slug=stored).id

    with engine.begin() as conn:
        landed = upsert_lane_company(
            conn, provider="workday", slug=lane_spelling, name="Nvidia"
        )

    assert landed == original, "the lane find did not converge onto the watched board"
    with engine.connect() as conn:
        rows = conn.execute(select(companies.c.slug)).scalars().all()
    assert rows == [stored], "a case variant was stored as a second Workday company row"


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


# --------------------------------------------------------------------------------------
# `watch=True` — the tier-1 auto-watch drain (blockers 1 & 2, D-414(a))
# --------------------------------------------------------------------------------------
#
# A tier-1 Indeed convergence lands on a provider the scanner CAN parse, so the lane asks for
# the board to be watched: the next scan then fetches the employer's own JD and drains the
# secondhand body the lane wrote. The flag is MONOTONIC — `False`->`True` only — so it can turn
# watching on for a lane-first company but can never unwatch a board or relabel one.


def test_watch_true_stores_watched_and_a_later_watch_false_never_downgrades(
    engine: Engine,
) -> None:
    """A NEW company inserted with `watch=True` is stored watched, and a subsequent default
    (`watch=False`) find of the SAME company must not turn it back off — the drain is still owed
    until a scan actually runs."""
    with engine.begin() as conn:
        first = upsert_lane_company(
            conn, provider="greenhouse", slug="acme", name="Acme", watch=True
        )
    row = _row(engine, provider="greenhouse", slug="acme")
    assert row.watched is True
    assert row.source == "lane"
    with engine.begin() as conn:
        again = upsert_lane_company(conn, provider="greenhouse", slug="acme", name="Acme")
    assert again == first
    assert _row(engine, provider="greenhouse", slug="acme").watched is True


def test_watch_true_upgrades_an_existing_unwatched_row_including_a_case_variant(
    engine: Engine,
) -> None:
    """A tier-2 (unwatched) lane row that later converges tier-1 UPGRADES in place.

    The upgrade touches `watched` only — `name` and `source` are left alone — and it finds the row
    even when the stored slug differs from the argument only in CASE (`stored_slug`), so a
    convergence never mints a second row for a board the store already holds."""
    with engine.begin() as conn:
        first = upsert_lane_company(conn, provider="ashby", slug="lightfield", name="Lightfield")
    assert _row(engine, provider="ashby", slug="lightfield").watched is False
    with engine.begin() as conn:
        landed = upsert_lane_company(
            conn, provider="ashby", slug="Lightfield", name="Lightfield Inc.", watch=True
        )
    assert landed == first, "the case variant did not converge onto the stored row"
    row = _row(engine, provider="ashby", slug="lightfield")
    assert row.watched is True
    assert row.name == "Lightfield", "the watch upgrade overwrote the stored name"
    assert row.source == "lane"
    with engine.connect() as conn:
        assert len(conn.execute(select(companies)).all()) == 1, "a second row was inserted"


def test_watch_false_default_stores_unwatched_and_touches_nothing_on_conflict(
    engine: Engine,
) -> None:
    """The default every other lane uses is the pre-fix behaviour, unchanged: a new row lands
    `watched=False` and a second unwatched find touches nothing, `watched` and `name` included.
    The null control for blockers 1 & 2 — the `watch` parameter must move nothing unless a caller
    asks. Reddens if the insert default is ever flipped to watched."""
    with engine.begin() as conn:
        upsert_lane_company(conn, provider="hiringcafe", slug="lever:beta", name="Beta")
    assert _row(engine, provider="hiringcafe", slug="lever:beta").watched is False
    with engine.begin() as conn:
        upsert_lane_company(conn, provider="hiringcafe", slug="lever:beta", name="Beta Renamed")
    row = _row(engine, provider="hiringcafe", slug="lever:beta")
    assert row.watched is False
    assert row.name == "Beta"


def test_watch_true_never_downgrades_an_already_watched_registry_board(engine: Engine) -> None:
    """MONOTONIC. A tier-1 convergence onto a board the user ALREADY watches leaves it exactly as
    it was — watched, with its curated `source` and `name` intact. The `watched.is_(False)` guard
    in the upgrade branch is what pins this: turning watching ON for a board already on is a no-op,
    never a relabel and never a toggle back off."""
    with engine.begin() as conn:
        upsert_watch(
            conn, provider="greenhouse", slug="acme", name="Acme Corporation", source="registry"
        )
    with engine.begin() as conn:
        upsert_lane_company(
            conn, provider="greenhouse", slug="acme", name="acme rendering", watch=True
        )
    row = _row(engine, provider="greenhouse", slug="acme")
    assert row.watched is True, "a lane convergence unwatched a board the user watches"
    assert row.source == "registry", "a watch upgrade relabelled a registry company"
    assert row.name == "Acme Corporation", "a watch upgrade overwrote a curated name"


# ------------------------------------------------- the company ring per-company cells rotate


def _add(engine: Engine, *, name: str, provider: str, slug: str, watched: bool) -> None:
    with engine.begin() as conn:
        conn.execute(
            companies.insert().values(
                name=name, provider=provider, slug=slug, source="user", watched=watched
            )
        )


def test_the_company_ring_is_watched_rows_only_in_the_stores_own_order(engine: Engine) -> None:
    """Both halves, because each fails to a different useless ring.

    WATCHED ONLY: an unwatched row is usually a lane PLACEHOLDER (`linkedin:google`), and the
    live store holds 1,369 of them against 443 watched — including them makes a full rotation
    ~26 days instead of ~6, which is the difference between a result that can be read inside the
    measurement window and one that cannot.

    ORDER BY id: the caller slices a rotating window over this list, so an unordered read hands a
    different ring to every run and the rotation revisits and starves arbitrary companies while
    still reporting a full pass. Ordering by id also makes the ring GROW AT THE END, so watching
    a new board appends instead of renumbering an in-flight rotation under itself.
    """
    _add(engine, name="Zeta", provider="greenhouse", slug="zeta", watched=True)
    _add(engine, name="Placeholder", provider="linkedin", slug="ph", watched=False)
    _add(engine, name="Alpha", provider="ashby", slug="alpha", watched=True)

    with engine.connect() as conn:
        assert watched_company_names(conn) == ("Zeta", "Alpha")

    # The ring grows at the END, so an in-flight rotation keeps its coverage.
    _add(engine, name="Mu", provider="lever", slug="mu", watched=True)
    with engine.connect() as conn:
        assert watched_company_names(conn) == ("Zeta", "Alpha", "Mu")


def test_the_company_ring_is_the_NAME_and_never_the_slug(engine: Engine) -> None:
    """A cell is a keyword phrase an employer's own posting has to contain, and `bytedance-inc`
    is not what ByteDance writes on a requisition. The two differ here on purpose: a ring built
    from slugs asks for strings no posting carries and would read as a lane that found nothing."""
    _add(engine, name="ByteDance", provider="greenhouse", slug="bytedance-inc", watched=True)
    with engine.connect() as conn:
        assert watched_company_names(conn) == ("ByteDance",)


def test_a_company_with_a_blank_name_yields_no_ring_entry(engine: Engine) -> None:
    """An empty phrase composes the cell `"" software engineer`, which asks LinkedIn for the
    empty phrase and returns the unfaceted market — a request the run would report as a company
    cell. The watched control beside it is what keeps this from passing on an empty ring."""
    _add(engine, name="   ", provider="greenhouse", slug="blank", watched=True)
    _add(engine, name="Real Co", provider="ashby", slug="real", watched=True)
    with engine.connect() as conn:
        assert watched_company_names(conn) == ("Real Co",)
