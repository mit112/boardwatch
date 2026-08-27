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

from datetime import timedelta
from pathlib import Path

from sqlalchemy import Engine, insert, select, update

from boardwatch.core.clock import utcnow
from boardwatch.core.liveness import Liveness
from boardwatch.core.models import BoardSnapshot, RawPosting
from boardwatch.core.normalize import content_hash
from boardwatch.pipeline.death_probe import sweep_unwatched_deaths
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


def _company(engine: Engine, *, slug: str, watched: bool, source: str = "lane") -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(
                insert(tables.companies).values(
                    name=slug.title(),
                    provider="greenhouse",
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


def _sweep(engine: Engine, prober, *, budget: int = 10, ttl_hours: int = 24):
    """One sweep under its OWN `runs` row — `posting_events.run_id` is a real foreign key, so a
    synthetic id would make the `closed` event unwritable and the close silently fail."""
    return sweep_unwatched_deaths(
        engine, prober=prober, run_id=insert_run(engine), budget=budget, ttl_hours=ttl_hours
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
