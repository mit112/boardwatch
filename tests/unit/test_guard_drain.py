"""T334 (D-705): a board the empty-complete guard keeps refusing hands its postings to the probe.

The guard (`scan/apply.py::_empty_complete_is_evidence_of_nothing`) counts no miss on an empty
`complete` answer, so a board that never lists again kept its postings open for good: all 73 such
boards were `watched = 1`, which put them outside the death probe, and `follow_board_moves` needs a
typed 404 that Lever, Greenhouse and Ashby never send for a departed tenant. The owner's ruling
(2026-11-23, option 2): after `GUARD_DRAIN_NIGHTS` consecutive guarded nights the board's open
postings go to the URL probe; each closes ONLY on its own two-strike proof, the board stays watched,
a relist resumes ordinary miss counting, and nothing closes on a timer.

What these tests defend is the NARROWNESS of that, from both sides: the typed flag is what the
guard wrote (never `postings_listed = 0`, which matches 1,224 boards against the 73 real ones), the
streak is 14 DISTINCT pipeline nights ending in tonight's scan, anything that is not a guarded scan
breaks it, and the probe's own evidence rules are untouched.

No network: the prober is injected, as in `test_death_probe.py`, whose fixtures this reuses.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, select, update

from boardwatch.core.models import BoardSnapshot, RawPosting
from boardwatch.pipeline.death_probe import (
    GUARD_DRAIN_NIGHTS,
    GUARD_DRAIN_RESERVE_DIVISOR,
    URL_PROBE_BLIND_PROVIDERS,
    guarded_for_the_drain,
    sweep_unwatched_deaths,
)
from boardwatch.scan.apply import apply_board
from boardwatch.store import tables
from boardwatch.store.ledger_queries import record_disposition
from boardwatch.store.queries import insert_run
from tests.unit.test_death_probe import (
    BODY,
    _age_the_probe,
    _alive,
    _company,
    _deliver_lead,
    _error,
    _events,
    _gone,
    _held_rows,
    _job_id,
    _posting,
    _row,
    _store,
    _url_prober_that_records,
)

TONIGHT = date(2026, 11, 23)

# The owner's ruling (2026-11-23), written out rather than read from the module: a boundary test
# that builds its history from `GUARD_DRAIN_NIGHTS` moves with a changed constant and still passes.
NIGHTS = 14


def _scan(
    engine: Engine,
    company_id: int,
    day: date,
    *,
    flag: bool | None,
    status: str = "complete",
    listed: int = 0,
    pipeline: bool = True,
    kind: str = "board",
    run_id: int | None = None,
) -> int:
    """One `board_scans` row dated `day`, on a run row of its own unless `run_id` names one (two
    boards scanned by the same run); returns that run's id."""
    run_id = insert_run(engine) if run_id is None else run_id
    started = datetime.combine(day, time(10, 0))
    with engine.begin() as conn:
        conn.execute(
            insert(tables.board_scans).values(
                run_id=run_id,
                company_id=company_id,
                started_at=started,
                finished_at=started + timedelta(seconds=3),
                status=status,
                postings_listed=listed,
                dead=False,
                pipeline_scan=pipeline,
                scan_kind=kind,
                empty_guarded=flag,
            )
        )
    return run_id


# One letter a night, oldest first; the last is tonight. `g` is a guarded scan; every other letter
# is a scan that is NOT, and each must break a streak: `r` a relist (complete, 1 listed), `f` a
# failed board, `u` an unchanged one (304), `p` a partial, `n` a complete/empty row written before
# the column existed (NULL, which is not evidence either way).
_NIGHT = {
    "g": dict(flag=True),
    "r": dict(flag=False, listed=1),
    "f": dict(flag=False, status="failed"),
    "u": dict(flag=False, status="unchanged"),
    "p": dict(flag=False, status="partial", listed=1),
    "n": dict(flag=None),
    # Not nights: a standalone `boardwatch scan` (not a pipeline scan, so `pipeline_scan` is
    # false) and a lane's row, each on its own run, on the day of the night before them.
    "s": dict(flag=False, listed=9, pipeline=False),
    "l": dict(flag=False, status="partial", pipeline=False, kind="lane"),
}


def _history(engine: Engine, company_id: int | list[int], nights: str) -> int:
    """Seed one scan per letter on consecutive days ending TONIGHT; return tonight's run id.

    One run per night, shared by every board named: run ids ascend with time, as the drain's
    `run_id <= tonight` bound assumes, and two boards scanned by one run share its id.
    """
    boards = [company_id] if isinstance(company_id, int) else company_id
    total = len([letter for letter in nights if letter not in "sl"])
    run_id = night = 0
    day = TONIGHT - timedelta(days=total)
    for letter in nights:
        if letter not in "sl":
            night += 1
            day = TONIGHT - timedelta(days=total - night)
        run_id = insert_run(engine) if letter not in "sl" else run_id
        for board in boards:
            _scan(
                engine, board, day,
                run_id=insert_run(engine) if letter in "sl" else run_id,
                **_NIGHT[letter],  # type: ignore[arg-type]
            )
    return run_id


def _lever_board(engine: Engine, slug: str = "shieldai", rows: int = 1) -> tuple[int, list[int]]:
    """A WATCHED Lever board holding `rows` open postings, each with its own URL."""
    company_id = _company(
        engine, slug=slug, watched=True, source="registry", provider="lever"
    )
    ids = [
        _posting(
            engine, company_id, pid=f"{slug}-{n}",
            url=f"https://jobs.lever.co/{slug}/{n}",
        )
        for n in range(rows)
    ]
    return company_id, ids


def _sweep(engine: Engine, prober, run_id: int, *, budget: int = 10):  # type: ignore[no-untyped-def]
    return sweep_unwatched_deaths(
        engine,
        prober=prober,
        listing_prober=None,
        run_id=run_id,
        budget=budget,
        company_budget=10,
        ttl_hours=24,
    )


# --- the typed flag, written where the guard fires ----------------------------------------


def _listing(url: str, *ids: str) -> BoardSnapshot:
    postings = [
        RawPosting(
            provider_posting_id=pid, title=f"Job {pid}", url=f"https://x/{pid}",
            locations=[], body_text=BODY, raw_json={"id": pid},
        )
        for pid in ids
    ]
    return BoardSnapshot(
        status="complete", postings=postings, url=url, observed_validators=None, error=None,
        listed_ids=frozenset(),
    )


def _flags(engine: Engine, company_id: int) -> list[tuple[str, int, bool | None]]:
    with engine.connect() as conn:
        return [
            (r.status, r.postings_listed, r.empty_guarded)
            for r in conn.execute(
                select(
                    tables.board_scans.c.status,
                    tables.board_scans.c.postings_listed,
                    tables.board_scans.c.empty_guarded,
                )
                .where(tables.board_scans.c.company_id == company_id)
                .order_by(tables.board_scans.c.id)
            )
        ]


def test_the_guard_writes_the_flag_on_the_scan_it_refused(tmp_path: Path) -> None:
    engine = _store(tmp_path)
    company_id = _company(engine, slug="acme", watched=True, provider="lever")
    url = "https://api.lever.co/v0/postings/acme?mode=json"

    first = apply_board(engine, _listing(url, "a", "b"), company_id, insert_run(engine))
    empty = apply_board(
        engine, _listing(url), company_id, insert_run(engine), pipeline_scan=True
    )

    assert not first.empty_complete_guarded
    assert empty.empty_complete_guarded, "the fixture did not trip the guard; nothing below counts"
    assert _flags(engine, company_id) == [("complete", 2, False), ("complete", 0, True)]


def test_an_empty_scan_of_a_board_holding_no_open_rows_is_not_flagged(tmp_path: Path) -> None:
    """The null control for the flag: the same empty `complete` answer, `postings_listed = 0`,
    but nothing for the guard to refuse. Inferring "guarded" from the count would flag it."""
    engine = _store(tmp_path)
    company_id = _company(engine, slug="acme", watched=True, provider="lever")

    result = apply_board(
        engine, _listing("https://x/acme"), company_id, insert_run(engine), pipeline_scan=True
    )

    assert result.status == "complete" and not result.empty_complete_guarded
    assert _flags(engine, company_id) == [("complete", 0, False)]


def test_a_fully_known_multi_request_board_lists_zero_and_is_not_flagged(tmp_path: Path) -> None:
    """`postings_listed = 0` is what a Workday board writes whenever every id is already known.
    The proxy matched 1,224 boards for exactly this reason, and the guard exempts it through
    `listed_ids`."""
    engine = _store(tmp_path)
    company_id = _company(engine, slug="acme", watched=True, provider="workday")
    url = "https://acme.wd1.example/wday/cxs/acme/jobs"
    apply_board(engine, _listing(url, "a", "b"), company_id, insert_run(engine))
    known = BoardSnapshot(
        status="complete", postings=[], url=url, observed_validators=None, error=None,
        listed_ids=frozenset({"a", "b"}),
    )

    apply_board(engine, known, company_id, insert_run(engine), pipeline_scan=True)

    assert _flags(engine, company_id)[-1] == ("complete", 0, False)


def test_a_failed_and_an_unchanged_scan_write_an_explicit_false(tmp_path: Path) -> None:
    engine = _store(tmp_path)
    company_id = _company(engine, slug="acme", watched=True, provider="lever")
    url = "https://api.lever.co/v0/postings/acme?mode=json"
    apply_board(engine, _listing(url, "a"), company_id, insert_run(engine))
    failed = BoardSnapshot(status="failed", postings=[], url=url, error="HTTP 500")
    unchanged = BoardSnapshot(status="unchanged", postings=[], url=url)

    apply_board(engine, failed, company_id, insert_run(engine), pipeline_scan=True)
    apply_board(engine, unchanged, company_id, insert_run(engine), pipeline_scan=True)

    assert [flag for _, _, flag in _flags(engine, company_id)] == [False, False, False]


# --- the streak ----------------------------------------------------------------------------


def test_the_threshold_is_fourteen_nights() -> None:
    assert GUARD_DRAIN_NIGHTS == NIGHTS == 14


@pytest.mark.parametrize(
    ("nights", "handed"), [(NIGHTS - 1, False), (NIGHTS, True)]
)
def test_a_board_guarded_fourteen_nights_hands_its_open_postings_to_the_probe(
    tmp_path: Path, nights: int, handed: bool
) -> None:
    engine = _store(tmp_path)
    company_id, rows = _lever_board(engine, rows=3)
    tonight = _history(engine, company_id, "g" * nights)

    url = _url_prober_that_records(_error)
    report = _sweep(engine, url, tonight)

    assert sorted(url.asked) == (rows if handed else [])  # type: ignore[attr-defined]
    assert report.guard_boards == (1 if handed else 0)
    assert report.guard_rows == (3 if handed else 0)
    assert report.guard_attempted == (3 if handed else 0)
    assert (report.due, report.attempted) == ((3, 3) if handed else (0, 0))


@pytest.mark.parametrize("breaker", list("rfupn"))
def test_anything_that_is_not_a_guarded_scan_breaks_the_streak(
    tmp_path: Path, breaker: str
) -> None:
    """Thirteen guarded nights after the breaker, however long the streak before it. The control
    below runs the identical 20 nights with the breaker replaced by a guarded one."""
    engine = _store(tmp_path)
    company_id, _ = _lever_board(engine)
    tonight = _history(engine, company_id, "g" * 6 + breaker + "g" * (NIGHTS - 1))

    url = _url_prober_that_records(_error)
    report = _sweep(engine, url, tonight)

    assert url.asked == [] and report.guard_boards == 0  # type: ignore[attr-defined]


def test_the_breaker_is_what_blocked_the_hand_over(tmp_path: Path) -> None:
    """The control for the parametrized test above: same length, no breaker."""
    engine = _store(tmp_path)
    company_id, rows = _lever_board(engine)
    tonight = _history(engine, company_id, "g" * (6 + NIGHTS))

    url = _url_prober_that_records(_error)
    _sweep(engine, url, tonight)

    assert sorted(url.asked) == rows  # type: ignore[attr-defined]


def test_a_relist_breaks_the_streak_and_a_fresh_one_must_be_built_from_scratch(
    tmp_path: Path,
) -> None:
    engine = _store(tmp_path)
    company_id, _ = _lever_board(engine)
    tonight = _history(engine, company_id, "g" * 30 + "r" + "g" * (NIGHTS - 1))

    url = _url_prober_that_records(_error)
    _sweep(engine, url, tonight)
    assert url.asked == []  # type: ignore[attr-defined]

    # One more guarded night and the new streak is 14: handed over again, on its own merit.
    tonight = _scan(engine, company_id, TONIGHT + timedelta(days=1), flag=True)
    _sweep(engine, url, tonight)
    assert len(url.asked) == 1  # type: ignore[attr-defined]


def test_lane_and_standalone_scans_neither_count_nor_interrupt_a_streak(tmp_path: Path) -> None:
    """D-669's filter, for its reason. A standalone scan and a lane row sit in the MIDDLE of the
    streak, each on a run of its own and not guarded: a query that read every `board_scans` row
    would see a break there and hand nothing over. (They sit before tonight's run on purpose: a
    row from a later run is cut by the `run_id <=` bound whether or not the filter is there.)"""
    engine = _store(tmp_path)
    company_id, rows = _lever_board(engine)
    tonight = _history(engine, company_id, "g" * 7 + "sl" + "g" * (NIGHTS - 7))

    url = _url_prober_that_records(_error)
    report = _sweep(engine, url, tonight)

    assert sorted(url.asked) == rows  # type: ignore[attr-defined]
    assert report.guard_boards == 1


def test_a_standalone_scan_that_listed_the_board_is_not_a_relist_for_the_streak(
    tmp_path: Path,
) -> None:
    """The control for the test above: the same two rows, but as PIPELINE scans, do break it."""
    engine = _store(tmp_path)
    company_id, _ = _lever_board(engine)
    tonight = _history(engine, company_id, "g" * 7 + "r" + "g" * (NIGHTS - 7))

    url = _url_prober_that_records(_error)
    _sweep(engine, url, tonight)

    assert url.asked == []  # type: ignore[attr-defined]


def test_two_scans_on_one_day_are_one_night(tmp_path: Path) -> None:
    engine = _store(tmp_path)
    company_id, rows = _lever_board(engine)
    for offset in range(NIGHTS // 2):
        day = TONIGHT - timedelta(days=NIGHTS // 2 - 1 - offset)
        _scan(engine, company_id, day, flag=True)
        tonight = _scan(engine, company_id, day, flag=True)

    url = _url_prober_that_records(_error)
    _sweep(engine, url, tonight)
    assert url.asked == []  # type: ignore[attr-defined]  # 14 scans, 7 nights

    # Seven more distinct nights make fourteen.
    for offset in range(1, NIGHTS // 2 + 1):
        tonight = _scan(engine, company_id, TONIGHT + timedelta(days=offset), flag=True)
    _sweep(engine, url, tonight)
    assert sorted(url.asked) == rows  # type: ignore[attr-defined]


def test_a_board_this_run_did_not_scan_hands_nothing_over(tmp_path: Path) -> None:
    """Fourteen guarded nights that ended yesterday are not evidence about tonight: the board may
    have relisted since, and a run that skipped the scan cannot know."""
    engine = _store(tmp_path)
    company_id, _ = _lever_board(engine)
    _history(engine, company_id, "g" * NIGHTS)

    url = _url_prober_that_records(_error)
    report = _sweep(engine, url, insert_run(engine))  # a later run, with no scan row for the board

    assert url.asked == [] and report.guard_boards == 0  # type: ignore[attr-defined]


def test_only_a_watched_board_is_drained_by_the_streak(tmp_path: Path) -> None:
    """An unwatched company is the original population and keeps its own rules; the drain adds
    nothing to it and must not report it as a guarded board."""
    engine = _store(tmp_path)
    company_id, _ = _lever_board(engine)
    tonight = _history(engine, company_id, "g" * NIGHTS)
    with engine.connect() as conn:
        assert [b.company_id for b in guarded_for_the_drain(conn, tonight)] == [company_id]
    with engine.begin() as conn:
        conn.execute(
            update(tables.companies).where(tables.companies.c.id == company_id).values(watched=False)
        )
    with engine.connect() as conn:
        assert guarded_for_the_drain(conn, tonight) == []

    url = _url_prober_that_records(_error)
    report = _sweep(engine, url, tonight)

    # Lever is a listing-path provider, so an unwatched Lever row is not URL-asked at all.
    assert url.asked == [] and report.guard_boards == 0  # type: ignore[attr-defined]


def test_the_flag_the_guard_wrote_is_what_the_drain_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end through `apply_board` on a ticking clock: no seeded flags. A board holding two
    postings goes empty and is scanned fourteen nights running; the thirteenth night hands over
    nothing and the fourteenth hands over both."""
    engine = _store(tmp_path)
    company_id = _company(engine, slug="acme", watched=True, source="registry", provider="lever")
    url = "https://api.lever.co/v0/postings/acme?mode=json"
    clock = [datetime.combine(TONIGHT - timedelta(days=NIGHTS), time(10, 0))]
    monkeypatch.setattr("boardwatch.scan.apply.utcnow", lambda: clock[0])
    apply_board(engine, _listing(url, "a", "b"), company_id, insert_run(engine), pipeline_scan=True)

    asked = _url_prober_that_records(_error)
    handed: list[int] = []
    for _night in range(1, NIGHTS + 1):
        clock[0] += timedelta(days=1)
        run_id = insert_run(engine)
        result = apply_board(
            engine, _listing(url), company_id, run_id, pipeline_scan=True
        )
        assert result.empty_complete_guarded
        before = len(asked.asked)  # type: ignore[attr-defined]
        _sweep(engine, asked, run_id)
        handed.append(len(asked.asked) - before)  # type: ignore[attr-defined]

    assert handed == [0] * (NIGHTS - 1) + [2]


# --- closing: the probe's own evidence rules, unchanged ------------------------------------


def test_a_probe_proven_dead_posting_closes_and_an_unproven_one_stays_open(
    tmp_path: Path,
) -> None:
    engine = _store(tmp_path)
    company_id, (dead, unknown, alive) = _lever_board(engine, rows=3)
    tonight = _history(engine, company_id, "g" * NIGHTS)

    def prober(posting_id: int, url: str):  # type: ignore[no-untyped-def]
        return {dead: _gone, unknown: _error, alive: _alive}[posting_id](posting_id, url)

    first = _sweep(engine, prober, tonight)
    assert first.closed == 0 and _row(engine, dead) == ("open", 1, None)

    _age_the_probe(engine)
    tonight = _scan(engine, company_id, TONIGHT + timedelta(days=1), flag=True)
    second = _sweep(engine, prober, tonight)

    assert second.closed == 1 and second.guard_closed == 1
    assert _row(engine, dead)[:2] == ("closed", 2)
    assert _events(engine, dead) == ["closed"]
    assert _row(engine, unknown) == ("open", 0, None)
    assert _row(engine, alive) == ("open", 0, None)
    with engine.connect() as conn:
        # The board stays watched, and nothing but the one posting changed.
        assert conn.execute(
            select(tables.companies.c.watched).where(tables.companies.c.id == company_id)
        ).scalar_one() is True


def test_one_dead_answer_does_not_close_a_handed_over_posting(tmp_path: Path) -> None:
    engine = _store(tmp_path)
    company_id, (row,) = _lever_board(engine)
    tonight = _history(engine, company_id, "g" * NIGHTS)

    report = _sweep(engine, _gone, tonight)

    assert report.closed == 0 and report.guard_closed == 0
    assert _row(engine, row) == ("open", 1, None)


def test_nothing_ever_closes_on_the_guard_alone(tmp_path: Path) -> None:
    """No timer: sixty nights of the guard, and a probe that can only say `unknown` or `alive`,
    closes nothing, however long the board stays empty."""
    engine = _store(tmp_path)
    company_id, rows = _lever_board(engine, rows=2)
    tonight = _history(engine, company_id, "g" * 60)

    for prober in (_error, _alive, _error):
        _sweep(engine, prober, tonight)
        _age_the_probe(engine)
        tonight = _scan(engine, company_id, TONIGHT + timedelta(days=1), flag=True)

    assert [_row(engine, row)[0] for row in rows] == ["open", "open"]


def test_a_relist_reopens_a_closed_posting_through_the_ordinary_path(tmp_path: Path) -> None:
    """"No special handling": the board lists a posting the probe closed, and `_apply_listed`
    reopens it and clears its strikes, exactly as for any closed posting."""
    engine = _store(tmp_path)
    company_id, (row,) = _lever_board(engine)
    tonight = _history(engine, company_id, "g" * NIGHTS)
    _sweep(engine, _gone, tonight)
    _age_the_probe(engine)
    tonight = _scan(engine, company_id, TONIGHT + timedelta(days=1), flag=True)
    _sweep(engine, _gone, tonight)
    assert _row(engine, row)[0] == "closed"

    relist = BoardSnapshot(
        status="complete", url="https://api.lever.co/v0/postings/shieldai?mode=json",
        postings=[RawPosting(
            provider_posting_id="shieldai-0", title="Job", url="https://jobs.lever.co/shieldai/0",
            locations=[], body_text=BODY, raw_json={"id": "shieldai-0"},
        )],
        observed_validators=None, error=None, listed_ids=frozenset(),
    )
    result = apply_board(engine, relist, company_id, insert_run(engine), pipeline_scan=True)

    assert result.reopened == 1
    assert _row(engine, row)[:2] == ("open", 0)
    assert _events(engine, row) == ["closed", "reopened"]


def test_a_built_lead_is_never_reopened_or_drained_by_the_drain(tmp_path: Path) -> None:
    """D-600. Closing a dead posting retires its row; it never touches the ledger. The `built`
    disposition keeps its policy stamp and no `reopened_at`, through the close AND the relist."""
    engine = _store(tmp_path)
    company_id, (row,) = _lever_board(engine)
    job_id = _job_id(engine, row)
    with engine.begin() as conn:
        record_disposition(
            conn, job_id, disposition="built", reason="lead_built", policy_version="v1",
            now=datetime(2026, 11, 1),
        )

    def disposition() -> tuple[object, ...]:
        with engine.connect() as conn:
            r = conn.execute(
                select(
                    tables.job_dispositions.c.disposition,
                    tables.job_dispositions.c.policy_version,
                    tables.job_dispositions.c.reopened_at,
                    tables.job_dispositions.c.decided_at,
                ).where(tables.job_dispositions.c.job_id == job_id)
            ).one()
        return tuple(r)

    before = disposition()
    assert before[:3] == ("built", "v1", None)
    tonight = _history(engine, company_id, "g" * NIGHTS)
    _sweep(engine, _gone, tonight)
    _age_the_probe(engine)
    tonight = _scan(engine, company_id, TONIGHT + timedelta(days=1), flag=True)
    _sweep(engine, _gone, tonight)
    assert _row(engine, row)[0] == "closed"
    assert disposition() == before

    relist = BoardSnapshot(
        status="complete", url="https://api.lever.co/v0/postings/shieldai?mode=json",
        postings=[RawPosting(
            provider_posting_id="shieldai-0", title="Job", url="https://jobs.lever.co/shieldai/0",
            locations=[], body_text=BODY, raw_json={"id": "shieldai-0"},
        )],
        observed_validators=None, error=None, listed_ids=frozenset(),
    )
    apply_board(engine, relist, company_id, insert_run(engine), pipeline_scan=True)
    assert _row(engine, row)[0] == "open"
    assert disposition() == before


# --- rows the URL probe cannot judge -------------------------------------------------------


def test_the_blind_providers_are_ashby_and_greenhouse_and_not_lever() -> None:
    """T89's measurement, restated as the drain's catalog: their dead URL answers alive."""
    assert URL_PROBE_BLIND_PROVIDERS == {"ashby", "greenhouse"}


@pytest.mark.parametrize("provider", ["ashby", "greenhouse"])
def test_a_guarded_board_the_url_probe_cannot_judge_is_counted_and_never_asked(
    tmp_path: Path, provider: str
) -> None:
    engine = _store(tmp_path)
    blind = _company(engine, slug="blind", watched=True, source="lane", provider=provider)
    blind_rows = [
        _posting(engine, blind, pid=f"b-{n}", url=f"https://example.test/blind/{n}")
        for n in range(4)
    ]
    lever, lever_rows = _lever_board(engine, rows=2)
    tonight = _history(engine, [lever, blind], "g" * NIGHTS)

    url = _url_prober_that_records(_gone)
    report = _sweep(engine, url, tonight)

    assert sorted(url.asked) == lever_rows  # type: ignore[attr-defined]
    assert not set(url.asked) & set(blind_rows)  # type: ignore[attr-defined]
    assert report.guard_boards == 2
    assert (report.guard_rows, report.guard_rows_unjudgeable) == (2, 4)
    assert all(_row(engine, row) == ("open", 0, None) for row in blind_rows)


# --- the budget -----------------------------------------------------------------------------


def _budget_store(
    tmp_path: Path, *, guard_rows: int, nights: int = NIGHTS
) -> tuple[Engine, dict[str, list[int]], int]:
    """Sixteen held rows, six unheld never-asked rows, and `guard_rows` rows under a Lever board
    guarded `nights` nights running."""
    engine = _store(tmp_path)
    unwatched = _company(engine, slug="u", watched=False)
    held = _held_rows(engine, unwatched, 16)
    tail = [
        _posting(engine, unwatched, pid=f"t-{n}", url=f"https://boards.example.test/t/{n}")
        for n in range(6)
    ]
    company_id, guard = _lever_board(engine, rows=guard_rows)
    tonight = _history(engine, company_id, "g" * nights)
    return engine, {"held": held, "tail": tail, "guard": guard}, tonight


def test_the_budget_is_shared_without_starving_the_leads_the_tail_or_the_drain(
    tmp_path: Path,
) -> None:
    """Budget 20: a fifth (4) for never-asked tail rows (T284), a tenth (2) for handed-over rows,
    the other 14 to the standing leads, which still go first. Each class gets its slots even though
    the sixteen leads alone would take all twenty."""
    assert GUARD_DRAIN_RESERVE_DIVISOR == 10
    engine, rows, tonight = _budget_store(tmp_path, guard_rows=5)

    url = _url_prober_that_records(_error)
    report = _sweep(engine, url, tonight, budget=20)

    assert url.asked == [  # type: ignore[attr-defined]
        *rows["held"][:14], *rows["tail"][:4], *rows["guard"][:2]
    ]
    assert (report.attempted, report.guard_attempted) == (20, 2)
    assert report.due == 16 + 6 + 5


def test_with_nothing_handed_over_the_split_is_t284s_exactly(tmp_path: Path) -> None:
    """The control: the board is a night short, so nothing is handed over and the leads keep four
    fifths of the budget as T284 left it (sixteen of twenty)."""
    engine, rows, tonight = _budget_store(
        tmp_path, guard_rows=2, nights=NIGHTS - 1
    )

    url = _url_prober_that_records(_error)
    report = _sweep(engine, url, tonight, budget=20)

    assert url.asked == [*rows["held"][:16], *rows["tail"][:4]]  # type: ignore[attr-defined]
    assert report.guard_boards == 0 and report.guard_attempted == 0


def test_a_short_drain_returns_its_unused_slots_to_the_leads(tmp_path: Path) -> None:
    """One handed-over row against a reserve of two: it takes one slot, the leads keep fifteen."""
    engine, rows, tonight = _budget_store(tmp_path, guard_rows=1)

    url = _url_prober_that_records(_error)
    _sweep(engine, url, tonight, budget=20)

    assert url.asked == [  # type: ignore[attr-defined]
        *rows["held"][:15], *rows["tail"][:4], *rows["guard"]
    ]


def test_a_handed_over_row_that_holds_a_standing_lead_is_probed_with_the_leads(
    tmp_path: Path,
) -> None:
    """The reserve is for rows no lead holds; a held one rides the main order, which puts it
    first. The held row has the LOWEST id, so a reserve that took it would win the slot: budget 10
    reserves one slot, and it must go to the lowest-id UNHELD row instead."""
    engine = _store(tmp_path)
    company_id, (held, plain_a, plain_b) = _lever_board(engine, rows=3)
    _deliver_lead(engine, held)
    tonight = _history(engine, company_id, "g" * NIGHTS)

    url = _url_prober_that_records(_error)
    _sweep(engine, url, tonight, budget=10)

    assert url.asked == [held, plain_b, plain_a]  # type: ignore[attr-defined]


def test_the_reserve_asks_the_least_recently_probed_handed_over_row_first(
    tmp_path: Path,
) -> None:
    """Budget 10 reserves one slot, and the twelve held rows fill the rest, so which handed-over
    row is asked is the reserve's order alone: the one probed longest ago, not the lowest id."""
    engine = _store(tmp_path)
    unwatched = _company(engine, slug="u", watched=False)
    held = _held_rows(engine, unwatched, 12)
    company_id, (g0, g1, g2) = _lever_board(engine, rows=3)
    tonight = _history(engine, company_id, "g" * NIGHTS)
    now = datetime.now()
    with engine.begin() as conn:
        for posting_id, hours in ((g0, 30), (g1, 50), (g2, 40)):
            conn.execute(
                update(tables.postings)
                .where(tables.postings.c.id == posting_id)
                .values(last_death_probe_at=now - timedelta(hours=hours))
            )

    url = _url_prober_that_records(_error)
    _sweep(engine, url, tonight, budget=10)

    assert url.asked == [*held[:9], g1]  # type: ignore[attr-defined]
