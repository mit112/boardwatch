"""D-325: a MEASURED death closes a posting the scanner structurally cannot reach.

D-314 established that a lane-acquired posting can never close: `_process_missing` is the only
writer of `status='closed'`, it runs on `complete` snapshots only, `lane_snapshot` is always
`partial`, and lane companies are `watched=False` so the coordinator never revisits them.
Absence can never be evidence for a search-based acquirer, so the only evidence left is a
POSITIVE one — the stored URL itself answering 404/410.

What is under test here is the narrowness, not the closing. Every one of these guards is a way
the mechanism could quietly widen into the age-based close that was measured and rejected:

- only `refetch_gone` — never `refetch_gone_after_redirect`, never `refetch_error`;
- only `companies.watched = 0` — a watched board already has a correct closing path;
- only after TWO probes in different runs, mirroring `CLOSE_AFTER_MISSES = 2`;
- with its own strike column, never `consecutive_missing`, which belongs to the board path;
- with a drain on both sides: an `alive` probe and a positive board sighting each clear it.

Sensitivity is low and stated in D-325: against a control of postings the scanner PROVED closed
(n=60) this detects 4 — 6.7%, Wilson 95% CI 2.6%–15.9% — because a closed Workday requisition
still answers 200 (0/37). It returned 0 false deaths against 90 live lane postings. It almost
never lies and it almost never fires; these tests pin the first half.

No network: the prober is injected, exactly as `run_cmd` injects the real one.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from sqlalchemy import Engine, insert, select, update

from boardwatch.core.clock import utcnow
from boardwatch.core.liveness import SIGNALS, Liveness
from boardwatch.core.models import BoardSnapshot, RawPosting
from boardwatch.core.normalize import content_hash
from boardwatch.pipeline.death_probe import (
    LISTING_ENDPOINTS,
    LISTING_SIGNALS,
    Listing,
    parse_listing,
    sweep_unwatched_deaths,
)
from boardwatch.scan.apply import apply_board
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import insert_run

BODY = "We are hiring a backend engineer to work on Python and PostgreSQL services."


# --- the injected probers, one per liveness signal that matters here ---------------------


def _gone(posting_id: int, url: str) -> Liveness:
    """A 404/410 from the URL ASKED ABOUT. The only signal permitted to close."""
    return Liveness(
        posting_id=posting_id, verdict="dead", signal="refetch_gone", detail="HTTP 404"
    )


def _gone_after_redirect(posting_id: int, url: str) -> Liveness:
    """A 404 reached through a hop — an employer migrating ATS. Never closes."""
    return Liveness(
        posting_id=posting_id,
        verdict="unknown",
        signal="refetch_gone_after_redirect",
        detail="HTTP 404 after redirect",
    )


def _error(posting_id: int, url: str) -> Liveness:
    """A timeout, a 403 from a bot-blocker, a 5xx. Says nothing about the requisition."""
    return Liveness(
        posting_id=posting_id, verdict="unknown", signal="refetch_error", detail="timeout"
    )


def _alive(posting_id: int, url: str) -> Liveness:
    return Liveness(
        posting_id=posting_id, verdict="alive", signal="refetch_ok", detail="HTTP 200"
    )


# --- store fixtures ----------------------------------------------------------------------


def _store(tmp_path: Path) -> Engine:
    engine = get_engine(tmp_path / "data")
    ensure_schema(engine)
    return engine


# T89 split the sweep by `companies.provider`, so the provider a fixture picks now decides WHICH
# mechanism answers for its rows. `jobapps` is the default because it is the URL path's largest
# real population (2,247 of the 13,101 open rows in this class) and, being tier-3 name-keyed rows
# with no ATS behind them, it is the one provider that can never move to a list endpoint. Every
# test below that predates T89 is about the URL path, so it gets that default; the listing tests
# name `ashby` explicitly.
URL_PATH_PROVIDER = "jobapps"


def _company(
    engine: Engine,
    *,
    slug: str,
    watched: bool,
    source: str = "lane",
    provider: str = URL_PATH_PROVIDER,
) -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(
                insert(tables.companies).values(
                    name=slug.title(),
                    provider=provider,
                    slug=slug,
                    source=source,
                    watched=watched,
                )
            ).inserted_primary_key[0]
        )


def _posting(
    engine: Engine,
    company_id: int,
    *,
    pid: str = "p-1",
    url: str | None = "https://boards.example.test/j/1",
    status: str = "open",
    death_strikes: int = 0,
) -> int:
    now = utcnow()
    with engine.begin() as conn:
        job_id = int(
            conn.execute(insert(tables.jobs).values(created_at=now)).inserted_primary_key[0]
        )
        return int(
            conn.execute(
                insert(tables.postings).values(
                    company_id=company_id,
                    job_id=job_id,
                    provider_posting_id=pid,
                    title="Backend Engineer",
                    normalized_title="backend engineer",
                    url=url,
                    locations_json=["Remote"],
                    remote_policy="remote",
                    first_seen_at=now,
                    last_seen_at=now,
                    status=status,
                    consecutive_missing=0,
                    death_strikes=death_strikes,
                    # The REAL hash of the body the re-sighting tests replay, so `_apply_listed`
                    # emits `reopened` without also emitting a spurious `revised`.
                    content_hash=content_hash(BODY),
                    body_text=BODY,
                )
            ).inserted_primary_key[0]
        )


def _row(engine: Engine, posting_id: int) -> tuple[str, int, object]:
    with engine.connect() as conn:
        row = conn.execute(
            select(
                tables.postings.c.status,
                tables.postings.c.death_strikes,
                tables.postings.c.closed_at,
            ).where(tables.postings.c.id == posting_id)
        ).one()
    return str(row.status), int(row.death_strikes), row.closed_at


def _events(engine: Engine, posting_id: int) -> list[str]:
    with engine.connect() as conn:
        return [
            str(r.kind)
            for r in conn.execute(
                select(tables.posting_events.c.kind)
                .where(tables.posting_events.c.posting_id == posting_id)
                .order_by(tables.posting_events.c.id)
            )
        ]


def _age_the_probe(engine: Engine, hours: int = 25) -> None:
    """Pretend `hours` passed since the last sweep, so the TTL admits the row again.

    Rewinding the stored timestamp rather than injecting a clock: the TTL predicate under test
    is the one production evaluates, and a `now` parameter would be a seam only the tests use.
    """
    with engine.begin() as conn:
        conn.execute(
            update(tables.postings)
            # Only rows that WERE probed. A row still carrying NULL has never been asked, and
            # NULL is what puts it at the head of the least-recently-probed order — backdating
            # it would erase the very distinction the round-robin test measures.
            .where(tables.postings.c.last_death_probe_at.is_not(None))
            .values(last_death_probe_at=utcnow() - timedelta(hours=hours))
        )


def _sweep(
    engine: Engine,
    prober,
    *,
    listing_prober=None,
    budget: int = 10,
    company_budget: int = 10,
    ttl_hours: int = 24,
):
    """One sweep under its OWN `runs` row — `posting_events.run_id` is a real foreign key, so a
    synthetic id would make the `closed` event unwritable and the close silently fail.

    `listing_prober` defaults to None, which is what every URL-path test wants: no listing is
    asked for, so a test that accidentally seeded a listing-provider company reads as refused
    work rather than reaching the network.
    """
    return sweep_unwatched_deaths(
        engine,
        prober=prober,
        listing_prober=listing_prober,
        run_id=insert_run(engine),
        budget=budget,
        company_budget=company_budget,
        ttl_hours=ttl_hours,
    )


# --- the two-strike rule ------------------------------------------------------------------


def test_one_measured_death_does_not_close_the_posting(tmp_path: Path) -> None:
    """`CLOSE_AFTER_MISSES = 2` on the board path; one probe is one observation, not two.

    A single 404 from a CDN having a bad minute must not be able to retire a live requisition,
    and for an unwatched company there is no board enumeration to correct it afterwards.
    """
    engine = _store(tmp_path)
    posting_id = _posting(engine, _company(engine, slug="acme", watched=False))

    report = _sweep(engine, _gone)

    assert report.gone == 1
    assert report.closed == 0
    assert _row(engine, posting_id) == ("open", 1, None)
    assert _events(engine, posting_id) == []


def test_two_measured_deaths_in_different_runs_close_the_posting(tmp_path: Path) -> None:
    engine = _store(tmp_path)
    posting_id = _posting(engine, _company(engine, slug="acme", watched=False))

    _sweep(engine, _gone)
    _age_the_probe(engine)
    report = _sweep(engine, _gone)

    assert report.closed == 1
    status, strikes, closed_at = _row(engine, posting_id)
    assert status == "closed"
    assert strikes == 2
    assert closed_at is not None
    assert _events(engine, posting_id) == ["closed"]


def test_a_gone_status_reached_through_a_redirect_never_closes(tmp_path: Path) -> None:
    """`refetch_gone_after_redirect` is the ONE signal that can disarm the whole check while
    every other number holds still: `Fetcher` follows redirects, so an employer migrating ATS
    answers 404 from a host that was never asked about. Closing on it would retire live
    requisitions in bulk, one employer at a time."""
    engine = _store(tmp_path)
    posting_id = _posting(engine, _company(engine, slug="acme", watched=False))

    _sweep(engine, _gone_after_redirect)
    _age_the_probe(engine)
    report = _sweep(engine, _gone_after_redirect)

    assert report.gone == 0
    # Counted as `unknown`, not silently absorbed: a forgiven gone-status is the one bucket
    # that can disarm this check with every other number holding still.
    assert report.unknown == 1
    assert report.closed == 0
    assert _row(engine, posting_id) == ("open", 0, None)


def test_a_transport_error_never_closes_however_often_it_repeats(tmp_path: Path) -> None:
    engine = _store(tmp_path)
    posting_id = _posting(engine, _company(engine, slug="acme", watched=False))

    for _ in range(3):
        _sweep(engine, _error)
        _age_the_probe(engine)

    assert _row(engine, posting_id) == ("open", 0, None)


def test_an_unknown_between_two_deaths_does_not_break_the_streak(tmp_path: Path) -> None:
    """Mirrors the board path exactly. There, a `failed` snapshot neither increments nor resets
    `consecutive_missing` — only a POSITIVE observation resets it (D23). An `unknown` probe is
    the same kind of non-evidence, so it leaves the counter where it stands. The alternative
    (unknown resets) disarms the check against any host that intermittently 403s."""
    engine = _store(tmp_path)
    posting_id = _posting(engine, _company(engine, slug="acme", watched=False))

    _sweep(engine, _gone)
    _age_the_probe(engine)
    _sweep(engine, _error)
    _age_the_probe(engine)
    _sweep(engine, _gone)

    assert _row(engine, posting_id)[0] == "closed"


# --- the watched=0 restriction ------------------------------------------------------------


def test_a_watched_companys_posting_is_never_probed(tmp_path: Path) -> None:
    """The honest defect predicate is `companies.watched = 0` — exactly the rows for which the
    scanner cannot produce a signal. A watched board enumerates itself every run and closes its
    own postings through `_process_missing`; probing it would add a SECOND, weaker closing path
    to a population that already has a correct one."""
    engine = _store(tmp_path)
    watched_id = _posting(
        engine, _company(engine, slug="watched", watched=True, source="registry")
    )
    unwatched_id = _posting(
        engine, _company(engine, slug="unwatched", watched=False), pid="p-2"
    )

    report = _sweep(engine, _gone)
    _age_the_probe(engine)
    _sweep(engine, _gone)

    assert report.attempted == 1
    assert _row(engine, watched_id) == ("open", 0, None)
    assert _row(engine, unwatched_id)[0] == "closed"


def test_a_closed_posting_is_not_probed_again(tmp_path: Path) -> None:
    engine = _store(tmp_path)
    _posting(engine, _company(engine, slug="acme", watched=False), status="closed")

    assert _sweep(engine, _gone).attempted == 0


# --- the drain, on both sides -------------------------------------------------------------


def test_an_alive_probe_clears_the_strike_counter(tmp_path: Path) -> None:
    """The drain this change owes itself: a strike is a suspicion, not a sentence."""
    engine = _store(tmp_path)
    posting_id = _posting(engine, _company(engine, slug="acme", watched=False))

    _sweep(engine, _gone)
    _age_the_probe(engine)
    report = _sweep(engine, _alive)
    _age_the_probe(engine)
    _sweep(engine, _gone)

    assert report.strikes_cleared == 1
    assert _row(engine, posting_id) == ("open", 1, None)  # the third probe is strike ONE again


def test_a_positive_board_sighting_clears_the_strike_counter(tmp_path: Path) -> None:
    """The second half of the drain, and the stronger evidence of the two: a lane that re-finds
    a posting has seen it listed, which outranks any number of probe failures. `_apply_listed`
    already resets `consecutive_missing` on every positive observation (D23); the death strike
    is reset in the same place for the same reason."""
    engine = _store(tmp_path)
    company_id = _company(engine, slug="acme", watched=False)
    posting_id = _posting(engine, company_id)

    _sweep(engine, _gone)
    assert _row(engine, posting_id)[1] == 1

    apply_board(
        engine,
        BoardSnapshot(
            status="partial",
            url="https://hiringcafe.example/",
            postings=[
                RawPosting(
                    provider_posting_id="p-1",
                    title="Backend Engineer",
                    url="https://boards.example.test/j/1",
                    locations=["Remote"],
                    body_text=BODY,
                    raw_json={},
                )
            ],
        ),
        company_id,
        insert_run(engine),
        scan_kind="lane",
    )

    assert _row(engine, posting_id) == ("open", 0, None)


def test_the_re_sighting_reopen_path_still_works_on_a_partial_snapshot(
    tmp_path: Path,
) -> None:
    """`_apply_listed` runs on `partial` as well as `complete` — verified in source and pinned
    here, because it is the ONLY recovery a false death has for an unwatched company. If the
    lane's `partial` snapshot could not reopen, every close this change makes would be
    permanent and the mechanism would be a quarantine with no drain."""
    engine = _store(tmp_path)
    company_id = _company(engine, slug="acme", watched=False)
    posting_id = _posting(engine, company_id)

    _sweep(engine, _gone)
    _age_the_probe(engine)
    _sweep(engine, _gone)
    assert _row(engine, posting_id)[0] == "closed"

    result = apply_board(
        engine,
        BoardSnapshot(
            status="partial",
            url="https://hiringcafe.example/",
            postings=[
                RawPosting(
                    provider_posting_id="p-1",
                    title="Backend Engineer",
                    url="https://boards.example.test/j/1",
                    locations=["Remote"],
                    body_text=BODY,
                    raw_json={},
                )
            ],
        ),
        company_id,
        insert_run(engine),
        scan_kind="lane",
    )

    assert result.reopened == 1
    assert _row(engine, posting_id) == ("open", 0, None)
    assert _events(engine, posting_id) == ["closed", "reopened"]


# --- TTL and budget -----------------------------------------------------------------------


def test_the_ttl_stops_a_row_being_re_probed_within_the_window(tmp_path: Path) -> None:
    """A full sweep costs ~0.97 s per probe. 471 lane rows is ~7.3 minutes of a run today and
    the class grows ~182/day, so an unbounded sweep outgrows the run itself within a month."""
    engine = _store(tmp_path)
    _posting(engine, _company(engine, slug="acme", watched=False))

    assert _sweep(engine, _error).attempted == 1
    second = _sweep(engine, _error)

    assert second.attempted == 0
    assert second.due == 0
    assert second.budget_refused == 0  # nothing was DUE, which is not the budget refusing


def test_the_ttl_admits_the_row_again_once_the_window_passes(tmp_path: Path) -> None:
    engine = _store(tmp_path)
    _posting(engine, _company(engine, slug="acme", watched=False))

    _sweep(engine, _error)
    _age_the_probe(engine, hours=25)

    assert _sweep(engine, _error).attempted == 1


def test_an_unknown_probe_still_spends_the_ttl(tmp_path: Path) -> None:
    """Otherwise one permanently-unreachable host consumes the whole budget every run and the
    rest of the class is never probed at all — a starvation that looks exactly like a healthy
    sweep from the counts alone."""
    engine = _store(tmp_path)
    _posting(engine, _company(engine, slug="acme", watched=False))

    _sweep(engine, _error)

    assert _sweep(engine, _error).attempted == 0


def test_the_budget_bounds_one_run_and_the_refusal_is_reported(tmp_path: Path) -> None:
    engine = _store(tmp_path)
    company_id = _company(engine, slug="acme", watched=False)
    for n in range(3):
        _posting(engine, company_id, pid=f"p-{n}", url=f"https://boards.example.test/j/{n}")

    report = _sweep(engine, _error, budget=2)

    assert (report.due, report.attempted, report.budget_refused) == (3, 2, 1)


def test_the_budget_takes_the_least_recently_probed_first(tmp_path: Path) -> None:
    """Round-robin, not a fixed head. Ordering by `id` would probe the same two rows every run
    for ever and the tail would never be reached, while `attempted` reported a busy sweep."""
    engine = _store(tmp_path)
    company_id = _company(engine, slug="acme", watched=False)
    ids = [
        _posting(engine, company_id, pid=f"p-{n}", url=f"https://boards.example.test/j/{n}")
        for n in range(3)
    ]

    _sweep(engine, _gone, budget=2)
    _age_the_probe(engine)  # every row is due again; the two probed ones carry a strike
    _sweep(engine, _gone, budget=1)

    with engine.connect() as conn:
        strikes = {
            int(r.id): int(r.death_strikes)
            for r in conn.execute(
                select(tables.postings.c.id, tables.postings.c.death_strikes)
            )
        }
    assert strikes[ids[2]] == 1, "the unprobed tail row was skipped a second time"


def test_a_budget_of_zero_reports_the_whole_class_as_refused(tmp_path: Path) -> None:
    """A disarmed sweep must read as refused work, never as a clean corpus."""
    engine = _store(tmp_path)
    _posting(engine, _company(engine, slug="acme", watched=False))

    report = _sweep(engine, _gone, budget=0)

    assert (report.attempted, report.gone, report.budget_refused) == (0, 0, 1)


def test_a_posting_with_no_url_is_counted_rather_than_silently_skipped(
    tmp_path: Path,
) -> None:
    """`postings.url` is nullable, and a row with no URL can never be probed by ANY future
    version of this check. Dropping it from the predicate would hide a permanently unreachable
    slice inside a sweep that reports itself complete."""
    engine = _store(tmp_path)
    company_id = _company(engine, slug="acme", watched=False)
    _posting(engine, company_id, pid="p-none", url=None)
    _posting(engine, company_id, pid="p-empty", url="")

    report = _sweep(engine, _gone)

    assert report.attempted == 0
    assert report.unprobeable == 2


# --- T89: the ATS list-API half -----------------------------------------------------------
#
# The URL half is not merely insensitive on a registry ATS, it is INVERTED. Probed live
# 2026-09-17 against postings a hand pre-flight had found dead: `jobs.ashbyhq.com` answers HTTP
# 200 with a 9,144-byte empty shell, and `job-boards.greenhouse.io` answers 302 -> 200. Both map
# to `refetch_ok` -> `alive`, which takes the drain branch and ZEROES the strikes the row had
# already earned. So the tests below assert two things at once: that membership of the company's
# own listing is asked about, and that the URL prober is not asked at all for those rows.


def _listing(*ids: str):  # type: ignore[no-untyped-def]
    """A stub list endpoint that publishes exactly `ids`, and records who it was asked about."""
    asked: list[tuple[int, str, str]] = []

    def probe(company_id: int, provider: str, slug: str) -> Listing:
        asked.append((company_id, provider, slug))
        return Listing(company_id, frozenset(ids), f"{len(ids)} listed")

    probe.asked = asked  # type: ignore[attr-defined]
    return probe


def _listing_unreachable(detail: str = "HTTP 500"):  # type: ignore[no-untyped-def]
    """A board that did not answer: a 5xx, a transport fault, an unparseable body."""

    def probe(company_id: int, provider: str, slug: str) -> Listing:
        return Listing(company_id, None, detail)

    return probe


def _url_prober_that_records(inner):  # type: ignore[no-untyped-def]
    """Wraps a URL prober so a test can assert which posting ids it was offered."""
    asked: list[int] = []

    def probe(posting_id: int, url: str) -> Liveness:
        asked.append(posting_id)
        return inner(posting_id, url)

    probe.asked = asked  # type: ignore[attr-defined]
    return probe


def test_an_absent_id_strikes_while_a_listed_one_is_cleared(tmp_path: Path) -> None:
    """The mechanism, in one assertion each way. The listing is the positive observation the URL
    can no longer supply for these providers, and it drains as well as it strikes — a row the
    board still publishes has been SEEN listed, which is the same evidence `_apply_listed` acts
    on and it outranks any number of earlier suspicions."""
    engine = _store(tmp_path)
    company_id = _company(engine, slug="acme", watched=False, provider="ashby")
    listed = _posting(engine, company_id, pid="listed", death_strikes=1)
    dropped = _posting(engine, company_id, pid="dropped")

    url = _url_prober_that_records(_gone)
    report = _sweep(engine, url, listing_prober=_listing("listed"))

    assert report.listing_absent == 1
    assert report.listing_present == 1
    assert report.strikes_cleared == 1
    assert _row(engine, dropped) == ("open", 1, None)
    assert _row(engine, listed) == ("open", 0, None)
    # And the URL half never saw them: one row, one signal (D-325 narrowing 4).
    assert url.asked == []  # type: ignore[attr-defined]
    assert (report.due, report.attempted) == (0, 0)


def test_a_second_listing_without_the_id_closes_the_posting(tmp_path: Path) -> None:
    """Two strikes in different runs, `CLOSE_AFTER_MISSES` reused — the same bar the URL half
    and the board path both clear. One absence from one listing is one observation: a provider
    mid-deploy can drop a requisition from its own API for a minute, and for an unwatched
    company there is no board enumeration to correct a premature close afterwards."""
    engine = _store(tmp_path)
    company_id = _company(engine, slug="acme", watched=False, provider="ashby")
    dropped = _posting(engine, company_id, pid="dropped")

    first = _sweep(engine, _gone, listing_prober=_listing("listed"))
    assert first.closed == 0
    _age_the_probe(engine)
    report = _sweep(engine, _gone, listing_prober=_listing("listed"))

    assert (report.closed_by_listing, report.closed_by_url, report.closed) == (1, 0, 1)
    status, strikes, closed_at = _row(engine, dropped)
    assert (status, strikes) == ("closed", 2)
    assert closed_at is not None
    assert _events(engine, dropped) == ["closed"]


def test_a_board_that_does_not_answer_moves_no_counter(tmp_path: Path) -> None:
    """`unknown` neither increments nor resets, mirroring an `unknown` URL probe and the board
    path's `failed` snapshot (D23). A 5xx, a timeout or a rate limit is not evidence about any
    requisition — and if it reset, one flaky hour would disarm the check for the whole fleet
    behind that host, which is every tenant of the provider."""
    engine = _store(tmp_path)
    company_id = _company(engine, slug="acme", watched=False, provider="ashby")
    struck = _posting(engine, company_id, pid="struck", death_strikes=1)
    clean = _posting(engine, company_id, pid="clean")

    for _ in range(3):
        report = _sweep(engine, _gone, listing_prober=_listing_unreachable())
        _age_the_probe(engine)

    assert report.listing_unknown == 2
    assert (report.listing_absent, report.listing_present, report.closed) == (0, 0, 0)
    assert _row(engine, struck) == ("open", 1, None)
    assert _row(engine, clean) == ("open", 0, None)


def test_an_empty_listing_for_a_company_holding_open_rows_is_unknown(tmp_path: Path) -> None:
    """Mirrors `scan/apply.py::_empty_complete_is_evidence_of_nothing` exactly. The sweep only
    asks about companies that HOLD open rows, so a board publishing nothing is a board whose
    answer is broken, not a board that emptied — and reading it as "every row absent" would
    retire an entire employer on one bad deploy at the provider. None of the 60 companies
    measured live answered empty, which is precisely why the case needs a test rather than a
    field observation."""
    engine = _store(tmp_path)
    company_id = _company(engine, slug="acme", watched=False, provider="ashby")
    a = _posting(engine, company_id, pid="a", death_strikes=1)
    b = _posting(engine, company_id, pid="b")

    report = _sweep(engine, _gone, listing_prober=_listing())

    assert report.listing_unknown == 2
    assert report.listing_absent == 0
    assert _row(engine, a) == ("open", 1, None)
    assert _row(engine, b) == ("open", 0, None)


def test_an_unwatched_row_with_no_list_endpoint_is_still_url_probed(tmp_path: Path) -> None:
    """CONTROL. `jobapps` rows are tier-3 name-keyed rows with no ATS behind them — 2,247 of the
    open rows in this class — and there is no list endpoint they could ever move to. They must
    keep the only mechanism they have."""
    engine = _store(tmp_path)
    posting_id = _posting(engine, _company(engine, slug="acme", watched=False))

    listing = _listing("anything")
    report = _sweep(engine, _gone, listing_prober=listing)
    _age_the_probe(engine)
    _sweep(engine, _gone, listing_prober=listing)

    assert (report.due, report.attempted, report.gone) == (1, 1, 1)
    assert report.companies_due == 0
    assert listing.asked == []  # type: ignore[attr-defined]
    assert _row(engine, posting_id)[0] == "closed"


def test_a_watched_companys_listing_is_never_asked(tmp_path: Path) -> None:
    """The listing half of `test_a_watched_companys_posting_is_never_probed`. `watched = 1` is
    precisely the population that already enumerates its own board every run and closes its own
    postings through `_process_missing` — and for these three providers the sweep would be
    reading the SAME endpoint the scan already read, then writing a second, weaker verdict into
    a column the scan owns."""
    engine = _store(tmp_path)
    watched = _posting(
        engine,
        _company(engine, slug="watched", watched=True, source="registry", provider="ashby"),
        pid="dropped",
    )
    unwatched = _posting(
        engine,
        _company(engine, slug="unwatched", watched=False, provider="ashby"),
        pid="dropped",
    )

    listing = _listing("listed")
    report = _sweep(engine, _gone, listing_prober=listing)
    _age_the_probe(engine)
    _sweep(engine, _gone, listing_prober=listing)

    assert report.companies_due == 1
    # Both sweeps share the stub, so the SET is the assertion: the watched slug must never
    # appear, however many times the unwatched one does.
    assert {slug for _, _, slug in listing.asked} == {"unwatched"}  # type: ignore[attr-defined]
    assert _row(engine, watched) == ("open", 0, None)
    assert _row(engine, unwatched)[0] == "closed"


def test_the_company_budget_bounds_one_run_and_the_refusal_is_reported(
    tmp_path: Path,
) -> None:
    """The listing budget counts COMPANIES, because that is what one GET buys. A sweep that
    refuses work must read as refused work, never as a clean corpus."""
    engine = _store(tmp_path)
    for slug in ("one", "two"):
        _posting(
            engine,
            _company(engine, slug=slug, watched=False, provider="ashby"),
            pid=f"{slug}-1",
        )

    listing = _listing("listed")
    report = _sweep(engine, _gone, listing_prober=listing, company_budget=1)

    assert (report.companies_due, report.companies_attempted, report.companies_refused) == (
        2,
        1,
        1,
    )
    assert len(listing.asked) == 1  # type: ignore[attr-defined]


def test_no_listing_prober_reports_the_whole_company_set_as_refused(tmp_path: Path) -> None:
    """The same direction `death_probe_budget = 0` takes on the URL path. A half that did not
    run must not report zero absent rows, which would read as a board that listed everything."""
    engine = _store(tmp_path)
    _posting(engine, _company(engine, slug="acme", watched=False, provider="ashby"), pid="x")

    report = _sweep(engine, _gone, listing_prober=None)

    assert (report.companies_due, report.companies_attempted, report.companies_refused) == (
        1,
        0,
        1,
    )
    assert (report.listing_absent, report.listing_present, report.listing_unknown) == (0, 0, 0)


def _set_probe_age(engine: Engine, company_id: int, hours: int) -> None:
    """Backdate every ALREADY-PROBED row of one company. Rows still carrying NULL keep it —
    that is the distinction the queue test measures."""
    with engine.begin() as conn:
        conn.execute(
            update(tables.postings)
            .where(
                tables.postings.c.company_id == company_id,
                tables.postings.c.last_death_probe_at.is_not(None),
            )
            .values(last_death_probe_at=utcnow() - timedelta(hours=hours))
        )


def test_a_company_holding_a_never_asked_row_is_due_and_sorts_first(tmp_path: Path) -> None:
    """SQL `min()` SKIPS nulls, and that one fact breaks the queue in both directions if it is
    not handled explicitly.

    `fresh` was asked an hour ago and then a lane added a row to it, so it holds one never-asked
    posting; `stale` was asked 100 hours ago and holds nothing new. Ordering or admitting by
    `min(last_death_probe_at)` alone reads `fresh` as "asked an hour ago" — it is neither due nor
    ahead in the queue — and the new posting is never answered about while
    `companies_attempted` reports a busy sweep. Both halves are pinned by one assertion: drop
    the never-asked term from the HAVING and `fresh` is not due at all; drop it from the
    ORDER BY and `stale` takes the single-company budget.
    """
    engine = _store(tmp_path)
    fresh = _company(engine, slug="fresh", watched=False, provider="ashby")
    stale = _company(engine, slug="stale", watched=False, provider="ashby")
    _posting(engine, fresh, pid="fresh-1")
    _posting(engine, stale, pid="stale-1")

    _sweep(engine, _gone, listing_prober=_listing_unreachable())
    _set_probe_age(engine, fresh, hours=1)
    _set_probe_age(engine, stale, hours=100)
    _posting(engine, fresh, pid="fresh-2")  # a lane adds a row: `last_death_probe_at` is NULL

    listing = _listing("fresh-1", "fresh-2")
    report = _sweep(engine, _gone, listing_prober=listing, company_budget=1)

    assert report.companies_due == 2
    assert [slug for _, _, slug in listing.asked] == [  # type: ignore[attr-defined]
        "fresh"
    ], "a company holding a never-asked row must be due and must sort ahead of an older one"


def test_the_listing_signals_are_a_closed_catalog() -> None:
    """Compared by NAME at the decision site, never by string-matching a message, and OWNED
    HERE rather than added to `core/liveness.py`'s `SIGNALS`: that catalog is paired one-to-one
    with a `dead`/`alive`/`unknown` verdict which a listing answer has no way to carry, and
    adding a member nothing on that path can emit is the bucket-that-cannot-be-audited its own
    docstring forbids."""
    assert set(LISTING_SIGNALS) == {"listing_absent", "listing_present", "listing_unknown"}
    assert set(LISTING_SIGNALS).isdisjoint(SIGNALS)


def test_every_listing_provider_declares_a_working_payload_shape() -> None:
    """The catalog decides which rows LEAVE the URL path, so an entry whose shape is wrong
    strands its whole population in `listing_unknown` with nothing else moving. The three
    shapes are two: ashby and greenhouse publish `{"jobs": [...]}`, lever publishes the bare
    array."""
    assert set(LISTING_ENDPOINTS) == {"ashby", "greenhouse", "lever"}
    for provider, (template, root) in LISTING_ENDPOINTS.items():
        assert "{slug}" in template, provider
        body = json.dumps({root: [{"id": 7}]} if root else [{"id": 7}]).encode()
        # `str(...)`, matching what every provider's `parse_job` wrote into
        # `postings.provider_posting_id`: a numeric greenhouse id must still compare equal.
        assert parse_listing(1, body, root=root).ids == frozenset({"7"})


def test_an_unparseable_listing_is_unknown_rather_than_empty() -> None:
    """The distinction the whole fail-safe direction rests on: `None` (no usable answer) is not
    `frozenset()` (answered nothing), and neither may be read as "every row absent"."""
    assert parse_listing(1, b"<html>rate limited</html>", root="jobs").ids is None
    assert parse_listing(1, b'{"postings": []}', root="jobs").ids is None
    assert parse_listing(1, b'{"jobs": "nope"}', root="jobs").ids is None
    assert parse_listing(1, b'{"jobs": []}', root="jobs").ids == frozenset()
    # An id-less row is skipped, not counted, mirroring `providers/base.py::count_listed_ids`:
    # a row we cannot key is one we could never have stored, so it neither confirms nor denies.
    assert parse_listing(1, b'{"jobs": [{"title": "x"}, {"id": 9}]}', root="jobs").ids == (
        frozenset({"9"})
    )



def test_a_board_that_does_not_answer_still_spends_its_TTL(tmp_path: Path) -> None:  # noqa: N802
    """The listing half of `test_an_unknown_probe_still_spends_the_ttl`, and the sharper of the
    two: on this path an unstamped row makes its whole COMPANY due again, because a company is
    due when any of its open rows has never been asked. A board that is permanently broken would
    then consume the company budget every run for ever and the rest of the class would never be
    reached — a starvation indistinguishable from a healthy sweep if only `companies_attempted`
    is read.

    Caught by mutation: setting `last_death_probe_at` to NULL on the listing write left every
    other test in this file green.
    """
    engine = _store(tmp_path)
    broken = _company(engine, slug="broken", watched=False, provider="ashby")
    _posting(engine, broken, pid="broken-1")
    waiting = _company(engine, slug="waiting", watched=False, provider="ashby")
    _posting(engine, waiting, pid="waiting-1")

    listing = _listing_unreachable()
    first = _sweep(engine, _gone, listing_prober=listing, company_budget=1)
    second = _sweep(engine, _gone, listing_prober=listing, company_budget=1)

    assert first.companies_attempted == 1
    # Within the TTL the answered company is no longer due, so the budget reaches the OTHER one
    # instead of re-asking the board that just failed.
    assert second.companies_due == 1
    assert second.companies_attempted == 1
    assert second.listing_unknown == 1
