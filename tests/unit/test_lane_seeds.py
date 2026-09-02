"""`lane_seeds` — the durable handoff from a discovering lane to a resolving one.

Every assertion here defends a property whose WRONG implementation is silent: a provenance
overwrite reads as a normal upsert, a reset attempt counter reads as a fresh seed, and an
attempt that is charged only on failure reads as a working retry bound right up until a lane
resolves nothing for a week.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, select

from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import insert_run
from boardwatch.store.seed_queries import (
    SeedWrite,
    UnroutableSeedURL,
    record_seed_attempt,
    record_seeds,
    seed_host,
    unresolved_seeds,
)
from boardwatch.store.tables import lane_seeds

HOSTS = frozenset({"x.test", "y.test"})
NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


def _engine(tmp_path: Path) -> Engine:
    engine = get_engine(tmp_path / "seeds.db")
    ensure_schema(engine)
    return engine


def test_a_seed_is_stored_once_and_the_first_discoverer_keeps_the_row(tmp_path: Path) -> None:
    """Re-seeing a URL must not rewrite who found it, and must not look like new reach.

    Both halves fail silently on the plausible wrong implementation (`on_conflict_do_update`):
    the store's account of where a posting came from becomes a lie with no recoverable prior
    value, and a lane re-listing its whole backlog every run reports it as fresh discovery
    forever.
    """
    engine = _engine(tmp_path)
    run = insert_run(engine)
    with engine.begin() as conn:
        first = record_seeds(
            conn, ("https://x.test/a",), discovered_by="github_lists", run_id=run, now=NOW
        )
        second = record_seeds(
            conn, ("https://x.test/a",), discovered_by="indeed", run_id=run, now=LATER
        )
        row = conn.execute(select(lane_seeds)).one()

    assert (first.inserted, second.inserted) == (1, 0), (
        "the return is rows INSERTED, never len(urls)"
    )
    assert row.discovered_by == "github_lists"
    assert row.host == "x.test", "the host is DERIVED here, never supplied by the caller"
    assert row.first_seen_at.replace(tzinfo=UTC) == NOW


def test_an_empty_batch_and_an_in_batch_duplicate_both_fall_out_of_the_conflict_clause(
    tmp_path: Path,
) -> None:
    """A CONTRACT PIN, not a mutation-caught guard, and it is labelled as one deliberately.

    No mutation of the current implementation makes this fail: both properties are consequences
    of the UNIQUE plus `on_conflict_do_nothing`, which
    `test_a_seed_is_stored_once_and_the_first_discoverer_keeps_the_row` already pins. What it
    defends is the EMPTY-BATCH half of a rewrite: a straightforward `executemany` form raises on
    an empty parameter list.

    It claimed a second thing until review checked it, and that claim was FALSE — `executemany`
    with `a, b, a` was probed and returns `rowcount == 2`, preserving the behaviour asserted
    here. The duplicate assertion below is therefore kept only because it is one line and
    documents the batch shape, NOT because any rewrite is known to break it.
    """
    engine = _engine(tmp_path)
    run = insert_run(engine)
    with engine.begin() as conn:
        assert record_seeds(
            conn, (), discovered_by="indeed", run_id=run, now=NOW
        ) == SeedWrite(inserted=0, unroutable=())
        assert conn.execute(select(lane_seeds)).all() == []
        assert record_seeds(
            conn,
            ("https://x.test/a", "https://x.test/b", "https://x.test/a"),
            discovered_by="indeed",
            run_id=run,
            now=NOW,
        ).inserted == 2
        assert sorted(conn.execute(select(lane_seeds.c.url)).scalars().all()) == [
            "https://x.test/a",
            "https://x.test/b",
        ]


def test_the_attempt_ceiling_and_the_limit_both_bind(tmp_path: Path) -> None:
    """A seed at the ceiling leaves the candidate set; the limit bounds the resolver's spend.

    Without the ceiling a permanently unresolvable URL — an expired requisition, a vendor that
    moved its markup — costs one GET every run forever, which is a cost leak with no drain.
    """
    engine = _engine(tmp_path)
    run = insert_run(engine)
    with engine.begin() as conn:
        record_seeds(
            conn,
            ("https://x.test/a", "https://x.test/b", "https://x.test/c"),
            discovered_by="indeed",
            run_id=run,
            now=NOW,
        )
        ids = {s.url: s.id for s in unresolved_seeds(conn, hosts=HOSTS, max_attempts=2, limit=99)}
        # `a` is driven to the ceiling; `b` sits one below it.
        record_seed_attempt(conn, ids["https://x.test/a"], run_id=run, now=NOW, resolved=False)
        record_seed_attempt(conn, ids["https://x.test/a"], run_id=run, now=NOW, resolved=False)
        record_seed_attempt(conn, ids["https://x.test/b"], run_id=run, now=NOW, resolved=False)

        under_ceiling = unresolved_seeds(conn, hosts=HOSTS, max_attempts=2, limit=99)
        capped = unresolved_seeds(conn, hosts=HOSTS, max_attempts=99, limit=1)

    assert [s.url for s in under_ceiling] == ["https://x.test/c", "https://x.test/b"], (
        "never-tried seeds come first, so a small budget still reaches new discoveries"
    )
    assert [s.url for s in capped] == ["https://x.test/c"]


def test_an_attempt_is_charged_on_success_as_well_as_on_failure(tmp_path: Path) -> None:
    """`attempts` is TIMES TRIED, not times failed.

    Charging only failures needs the caller to remember which of two calls to make, and the
    failure mode of forgetting is unbounded retries — the exact thing the column exists to stop.
    """
    engine = _engine(tmp_path)
    run = insert_run(engine)
    with engine.begin() as conn:
        record_seeds(conn, ("https://x.test/a",), discovered_by="indeed", run_id=run, now=NOW)
        seed = unresolved_seeds(conn, hosts=HOSTS, max_attempts=9, limit=9)[0]
        record_seed_attempt(conn, seed.id, run_id=run, now=LATER, resolved=True)
        row = conn.execute(select(lane_seeds)).one()

    assert row.attempts == 1
    assert row.resolved_at is not None


def test_a_resolved_seed_leaves_the_candidate_set_but_keeps_its_row(tmp_path: Path) -> None:
    """Set `resolved_at`, never DELETE: draining a bucket must not erase that it held something.

    A delete would also let the same URL be re-seeded and re-resolved next run, producing a
    second posting for one requisition.
    """
    engine = _engine(tmp_path)
    run = insert_run(engine)
    with engine.begin() as conn:
        record_seeds(conn, ("https://x.test/a",), discovered_by="indeed", run_id=run, now=NOW)
        seed = unresolved_seeds(conn, hosts=HOSTS, max_attempts=9, limit=9)[0]
        record_seed_attempt(conn, seed.id, run_id=run, now=LATER, resolved=True)

        assert unresolved_seeds(conn, hosts=HOSTS, max_attempts=99, limit=99) == ()
        assert conn.execute(select(lane_seeds.c.url)).scalars().all() == ["https://x.test/a"]
        # Re-seeding a resolved URL must not resurrect it.
        assert record_seeds(
            conn, ("https://x.test/a",), discovered_by="indeed", run_id=run, now=LATER
        ).inserted == 0
        assert unresolved_seeds(conn, hosts=HOSTS, max_attempts=99, limit=99) == ()


def test_a_failed_attempt_records_which_run_charged_it(tmp_path: Path) -> None:
    """Without the run id a stuck seed cannot be told from one nothing has looked at yet."""
    engine = _engine(tmp_path)
    first, second = insert_run(engine), insert_run(engine)
    with engine.begin() as conn:
        record_seeds(conn, ("https://x.test/a",), discovered_by="indeed", run_id=first, now=NOW)
        seed = unresolved_seeds(conn, hosts=HOSTS, max_attempts=9, limit=9)[0]
        record_seed_attempt(conn, seed.id, run_id=second, now=LATER, resolved=False)
        row = conn.execute(select(lane_seeds)).one()

    assert (row.first_seen_run_id, row.last_attempt_run_id) == (first, second)
    assert row.last_attempt_at.replace(tzinfo=UTC) == LATER
    assert row.resolved_at is None


def test_a_resolver_never_sees_a_seed_on_a_host_it_cannot_handle(tmp_path: Path) -> None:
    """The routing half, and it is the whole reason `host` exists.

    With one undifferentiated pool a resolver taking a bounded number of seeds is handed
    whatever is OLDEST. So a resolver that can parse `y.test` and not `x.test`, asking for one
    seed a run, draws the `x.test` row forever: either it skips it and `y.test` starves for good,
    or it charges an attempt against a budget that belongs to a resolver nobody has written yet.
    """
    engine = _engine(tmp_path)
    run = insert_run(engine)
    with engine.begin() as conn:
        record_seeds(
            conn,
            ("https://x.test/older", "https://y.test/newer"),
            discovered_by="indeed",
            run_id=run,
            now=NOW,
        )
        mine = unresolved_seeds(
            conn, hosts=frozenset({"y.test"}), max_attempts=9, limit=1
        )
        none_of_mine = unresolved_seeds(
            conn, hosts=frozenset({"z.test"}), max_attempts=9, limit=9
        )

    assert [s.url for s in mine] == ["https://y.test/newer"]
    assert mine[0].host == "y.test"
    assert none_of_mine == (), "a host no resolver claims is not silently handed to one that did"


def test_the_host_is_normalised_so_a_strategy_table_can_match_it(tmp_path: Path) -> None:
    """A seed recorded as `WWW.X.TEST` that no `hosts` filter matches can never be drained and
    never reports itself as stuck — it is simply invisible work."""
    engine = _engine(tmp_path)
    run = insert_run(engine)
    with engine.begin() as conn:
        record_seeds(
            conn, ("https://WWW.X.TEST/a",), discovered_by="indeed", run_id=run, now=NOW
        )
        found = unresolved_seeds(conn, hosts=frozenset({"x.test"}), max_attempts=9, limit=9)

    assert [s.host for s in found] == ["x.test"]


def test_a_root_dot_or_explicit_port_is_normalised_so_the_seed_stays_drainable(
    tmp_path: Path,
) -> None:
    """A DNS root dot or an explicit port must not strand a seed on a host no resolver can name.

    `newco.applytojob.com.` and `other.applytojob.com:443` name the SAME tenant space as
    `*.applytojob.com`, but stored verbatim off `parsed.netloc` neither matches the resolver's
    exact/suffix route — the trailing dot and the `:443` both break the `%.applytojob.com` LIKE —
    so the row is never attempted and never ages out: a bucket with no drain. Routing off validated
    `parsed.hostname` (which drops the port) and stripping one root dot fixes both. The stored
    `url` stays the original — only the routing `host` is normalised.
    """
    engine = _engine(tmp_path)
    run = insert_run(engine)
    with engine.begin() as conn:
        record_seeds(
            conn,
            (
                "https://newco.applytojob.com./apply/ABC",
                "https://other.applytojob.com:443/apply/DEF",
            ),
            discovered_by="indeed",
            run_id=run,
            now=NOW,
        )
        drainable = unresolved_seeds(
            conn,
            hosts=frozenset(),
            host_suffixes=frozenset({"applytojob.com"}),
            max_attempts=9,
            limit=9,
        )

    assert sorted(s.host for s in drainable) == [
        "newco.applytojob.com",
        "other.applytojob.com",
    ], "the root dot and the :443 are both normalised away, so the suffix route reaches them"
    assert {s.url for s in drainable} == {
        "https://newco.applytojob.com./apply/ABC",
        "https://other.applytojob.com:443/apply/DEF",
    }, "the stored url is the original; only the routing host is normalised"


def test_a_negative_limit_is_refused_rather_than_read_as_no_limit(tmp_path: Path) -> None:
    """SQLite spells "no bound" as `LIMIT -1`, so the one thing this argument promises would be
    silently defeated by a caller whose budget arithmetic went negative — and the failure is a
    resolver draining its entire backlog in one run against a host nobody here operates."""
    engine = _engine(tmp_path)
    run = insert_run(engine)
    with engine.begin() as conn:
        record_seeds(
            conn,
            ("https://x.test/a", "https://x.test/b", "https://x.test/c"),
            discovered_by="indeed",
            run_id=run,
            now=NOW,
        )
        with pytest.raises(ValueError, match="non-negative"):
            unresolved_seeds(conn, hosts=HOSTS, max_attempts=9, limit=-1)
        with pytest.raises(ValueError, match="non-negative"):
            unresolved_seeds(conn, hosts=HOSTS, max_attempts=-1, limit=9)


def test_an_unseedable_url_costs_that_url_and_nothing_else(
    tmp_path: Path,
) -> None:
    """One malformed value from an aggregator must not roll back the batch beside it.

    `record_seeds` is the single write point, so it applies `is_seedable_url` to every URL and
    refuses the ones a resolver could never GET: an unbalanced bracket (`urlparse` raises a BARE
    `ValueError`) AND a scheme-less value (`notaurl`). Raising instead would abort every valid seed
    in the same statement AND, via `_run_lanes`' broad per-lane `except`, cost the lane its entire
    report — so a single bad string would delete a whole lane's run from the record. Each bad value
    is skipped, named in `unroutable`, and the valid seeds beside it are written.
    """
    engine = _engine(tmp_path)
    run = insert_run(engine)
    with engine.begin() as conn:
        written = record_seeds(
            conn,
            ("https://x.test/good", "https://[broken", "notaurl", "https://y.test/also-good"),
            discovered_by="indeed",
            run_id=run,
            now=NOW,
        )
        stored = sorted(conn.execute(select(lane_seeds.c.url)).scalars().all())

    # TWO refused, in input order. `notaurl` is now refused too: it has no `://`, so it is not a URL
    # a resolver could GET. An earlier version stored it as a host no filter would ever name -- a
    # bucket with no drain -- rather than paper over it; the shared seed-URL gate closes that gap
    # by refusing it outright and REPORTING it, which is stricter and visible rather than silent.
    assert written.unroutable == ("https://[broken", "notaurl")
    assert written.inserted == 2
    assert stored == ["https://x.test/good", "https://y.test/also-good"]


def test_the_write_point_refuses_every_unseedable_shape_from_any_lane(
    tmp_path: Path,
) -> None:
    """`record_seeds` is the SINGLE write point, so it validates every lane's seeds once.

    The blocker that closed the tier-D URL boundary was a lane reaching `lane_seeds` by a path
    (`match_vendor` → persist) that did NOT validate: `seed_host` drops the port and cleans up
    control chars, so a bad-port / scheme-less / NUL / DEL JazzHR-shaped URL routed to a valid
    host and was stored, then HTTPX rejected it at fetch as undrainable dead weight. Enforcing the
    shared gate HERE means any lane's bad seed is refused AND reported through `unroutable`, while
    a valid `:443` and a valid root-dot URL still normalize to a drainable host and ARE selected.
    """
    engine = _engine(tmp_path)
    run = insert_run(engine)
    invalid = (
        "https://newco.applytojob.com:99999/apply/ABC/Title",  # port outside 0-65535
        "newco.applytojob.com/apply/ABC/Title",                # no scheme
        "https://newco.applytojob.com/apply/ABC/\x00Title",    # NUL in the path
        "https://newco.applytojob.com/apply/ABC/\x7fTitle",    # DEL in the path
    )
    valid = (
        "https://other.applytojob.com:443/apply/DEF/Title",    # explicit :443
        "https://newco.applytojob.com./apply/GHI/Title",       # trailing DNS root dot
    )
    with engine.begin() as conn:
        written = record_seeds(
            conn, invalid + valid, discovered_by="jsonld", run_id=run, now=NOW
        )
        drainable = unresolved_seeds(
            conn,
            hosts=frozenset(),
            host_suffixes=frozenset({"applytojob.com"}),
            max_attempts=9,
            limit=9,
        )

    # Every invalid shape is refused, in input order, and REPORTED -- never a silent drop.
    assert written.unroutable == invalid
    assert written.inserted == 2
    # The two valid URLs seed, normalize to a routing host the JazzHR suffix reaches, and drain.
    assert sorted(s.host for s in drainable) == [
        "newco.applytojob.com",
        "other.applytojob.com",
    ]
    assert {s.url for s in drainable} == set(valid)


def test_a_url_with_no_host_is_refused_rather_than_stored_with_an_empty_one(
    tmp_path: Path,
) -> None:
    """An empty `host` matches no resolver's filter, so the row would sit unresolved and
    unattempted forever and report itself as nothing at all — invisible work, which is worse
    than a refusal."""
    with pytest.raises(UnroutableSeedURL, match="no host"):
        seed_host("")

    engine = _engine(tmp_path)
    run = insert_run(engine)
    with engine.begin() as conn:
        written = record_seeds(conn, ("",), discovered_by="indeed", run_id=run, now=NOW)
        assert conn.execute(select(lane_seeds)).all() == []
    assert written == SeedWrite(inserted=0, unroutable=("",))


def test_a_suffix_route_reaches_a_tenant_subdomain_no_resolver_has_ever_seen(
    tmp_path: Path,
) -> None:
    """The wildcard-tenant case, which exact hosts CANNOT express.

    JazzHR is `<tenant>.applytojob.com` and the tenants cannot be enumerated in advance. With
    exact hosts alone, a seed another lane discovered on a tenant this resolver has never seen is
    invisible: nothing selects it, so nothing attempts it, so the attempt bound never ages it out
    and no report ever names it — a bucket with no drain.
    """
    engine = _engine(tmp_path)
    run = insert_run(engine)
    with engine.begin() as conn:
        record_seeds(
            conn,
            (
                "https://brandnew.applytojob.com/apply/AAA",
                "https://applytojob.com/apply/BBB",
                "https://notapplytojob.com/apply/CCC",
                "https://other.test/1",
            ),
            discovered_by="indeed",
            run_id=run,
            now=NOW,
        )
        by_suffix = unresolved_seeds(
            conn,
            hosts=frozenset(),
            host_suffixes=frozenset({"applytojob.com"}),
            max_attempts=9,
            limit=9,
        )
        exact_only = unresolved_seeds(
            conn, hosts=frozenset({"applytojob.com"}), max_attempts=9, limit=9
        )

    assert sorted(s.host for s in by_suffix) == ["applytojob.com", "brandnew.applytojob.com"], (
        "a suffix matches the bare host AND any subdomain of it"
    )
    assert "notapplytojob.com" not in {s.host for s in by_suffix}, (
        "a different registrable domain that merely ENDS in the same characters is not this "
        "vendor's tenant space"
    )
    assert [s.host for s in exact_only] == ["applytojob.com"], (
        "the exact-host arm is unchanged and does not silently widen"
    )


def test_a_resolver_that_claims_no_route_at_all_gets_nothing(tmp_path: Path) -> None:
    """Empty on BOTH arms returns nothing rather than everything.

    The dangerous wrong implementation is an `or_()` over an empty predicate list, which SQLAlchemy
    renders as a tautology — every unresolved seed in the table, handed to a resolver that claimed
    none of them.
    """
    engine = _engine(tmp_path)
    run = insert_run(engine)
    with engine.begin() as conn:
        record_seeds(conn, ("https://x.test/a",), discovered_by="indeed", run_id=run, now=NOW)
        assert unresolved_seeds(
            conn, hosts=frozenset(), host_suffixes=frozenset(), max_attempts=9, limit=9
        ) == ()
