"""T360: the scan orders hosts by how long each held the last complete scan, not by board count.

Depth cannot see a one-board host whose chain is its detail fetches (`jobs.apple.com`: 489
requests, 1,705 s on run 2910), so it sorted among ~1,100 single-board Workday hosts and started at
33 minutes. The tests below plant that shape. Expected values come from the planted fleet and the
ticket's wording, never from calling `host_queues` to decide them.
"""

from __future__ import annotations

import heapq
from collections import Counter
from typing import Any

from boardwatch.core.models import BoardRequest
from boardwatch.core.politeness import host_key
from boardwatch.reports.run_funnel import HostFetchCost, _host_cost_markdown
from boardwatch.scan.coordinator import host_queues, take_ready
from boardwatch.store.app_state import HOST_BUSY_KEY, get_host_busy, set_host_busy, set_state

_Work = list[tuple[Any, Any, BoardRequest]]

_BIG = "https://jobs.bigcorp.example/api/jobs"  # one board, a long chain: the Apple shape
_SHARED = "https://boards-api.greenhouse.io/v1/boards/{}/jobs"
_SHARED_HOST = "boards-api.greenhouse.io"
_TENANT = "https://{0}.wd5.myworkdayjobs.com/wday/cxs/{0}/Careers/jobs"
_WORKERS = 4


def _work(*urls: str) -> _Work:
    return [
        (i, i, BoardRequest(provider="p", slug=f"s{i}", url=url)) for i, url in enumerate(urls)
    ]


def _fleet() -> _Work:
    """Stored order: a 12-board shared host, 200 single-board tenants, and the one big board LAST.

    Today's depth order puts the 12-board host first and the big board among the 200 singletons
    in stored order, i.e. last.
    """
    return _work(
        *[_SHARED.format(i) for i in range(12)],
        *[_TENANT.format(f"t{i}") for i in range(200)],
        _BIG,
    )


def _hosts_in_order(queues: list[list[Any]]) -> list[str]:
    return [host_key(queue[0][2].url) for queue in queues]


def _todays_order(work: _Work) -> list[str]:
    """The pre-T360 rule from first principles: most boards first, ties in stored order."""
    depth = Counter(host_key(item[2].url) for item in work)
    first_seen: dict[str, int] = {}
    for i, item in enumerate(work):
        first_seen.setdefault(host_key(item[2].url), i)
    return sorted(depth, key=lambda host: (-depth[host], first_seen[host]))


def test_with_no_record_the_order_is_todays_exactly() -> None:
    # Stored order is NOT depth order here, so only a real depth sort can pass.
    work = _work(
        *[_TENANT.format(f"t{i}") for i in range(5)],
        *[f"https://api.lever.co/v0/postings/{i}?mode=json" for i in range(3)],
        *[_SHARED.format(i) for i in range(12)],
        _BIG,
    )
    expected = _todays_order(work)
    assert expected[:2] == [_SHARED_HOST, "api.lever.co"]  # the premise: depth moves hosts
    assert expected[-2:] == ["t4.wd5.myworkdayjobs.com", "jobs.bigcorp.example"]

    assert _hosts_in_order(host_queues(work)) == expected
    assert _hosts_in_order(host_queues(work, {})) == expected
    assert _hosts_in_order(host_queues(work, None, 2.5)) == expected  # the floor's size is moot


def test_a_host_recorded_at_ten_times_any_other_starts_in_the_first_worker_wave() -> None:
    work = _fleet()
    single = 10.0
    last_night = {host_key(item[2].url): single for item in work}
    last_night[_SHARED_HOST] = 12 * single
    last_night["jobs.bigcorp.example"] = 10 * 12 * single  # 10x the busiest other host

    queues = host_queues(work, last_night)

    first_wave = _hosts_in_order(queues)[:_WORKERS]
    assert "jobs.bigcorp.example" in first_wave
    # and the dispatcher really hands it out in the first wave, not just queues it there
    taken = take_ready(queues, set(), _WORKERS)
    assert "jobs.bigcorp.example" in [host_key(item[2].url) for item in taken]


def test_a_recorded_host_is_priced_by_busy_time_not_by_its_board_count() -> None:
    work = _work(_BIG, *[_SHARED.format(i) for i in range(5)])

    by_depth = _hosts_in_order(host_queues(work))
    by_busy = _hosts_in_order(host_queues(work, {"jobs.bigcorp.example": 900.0}))

    assert by_depth == [_SHARED_HOST, "jobs.bigcorp.example"]
    assert by_busy == ["jobs.bigcorp.example", _SHARED_HOST]


def test_a_record_cannot_price_a_host_below_what_its_boards_now_need() -> None:
    """A host recorded when it had one board, now with fifty, is at least fifty paced requests."""
    work = _work(*[_SHARED.format(i) for i in range(50)], _BIG)

    order = _hosts_in_order(host_queues(work, {_SHARED_HOST: 3.0, "jobs.bigcorp.example": 40.0}))

    assert order == [_SHARED_HOST, "jobs.bigcorp.example"]  # 50 x 1.0 s beats the stale 3 s record


def test_a_host_with_no_record_is_priced_at_its_paced_floor_among_recorded_ones() -> None:
    work = _work(
        *[_SHARED.format(i) for i in range(5)],  # unrecorded: 5 boards x 1.0 s = 5 s
        _TENANT.format("quick"),  # recorded 2 s
        _TENANT.format("slow"),  # recorded 100 s
    )
    last_night = {"quick.wd5.myworkdayjobs.com": 2.0, "slow.wd5.myworkdayjobs.com": 100.0}

    order = _hosts_in_order(host_queues(work, last_night))

    assert order == ["slow.wd5.myworkdayjobs.com", _SHARED_HOST, "quick.wd5.myworkdayjobs.com"]


def test_equal_estimates_keep_the_stored_order() -> None:
    work = _work(*[_TENANT.format(f"t{i}") for i in range(6)])
    last_night = {f"t{i}.wd5.myworkdayjobs.com": 7.0 for i in range(6)}

    assert [q[0][0] for q in host_queues(work, last_night)] == [0, 1, 2, 3, 4, 5]


def test_equal_estimates_fall_back_to_the_deeper_host_not_the_stored_first() -> None:
    """A one-board host stored first, recorded at 5 s, ties a five-board host priced at its floor
    (5 x 1.0 s). Today's order puts the deeper host first and a tie must not reverse that."""
    work = _work(_TENANT.format("solo"), *[_SHARED.format(i) for i in range(5)])

    order = _hosts_in_order(host_queues(work, {"solo.wd5.myworkdayjobs.com": 5.0}))

    assert order == [_SHARED_HOST, "solo.wd5.myworkdayjobs.com"]


def test_the_queues_partition_the_same_boards_with_and_without_a_record() -> None:
    work = _fleet()
    last_night = {"jobs.bigcorp.example": 1200.0, _SHARED_HOST: 120.0}

    for record in (None, last_night):
        queues = host_queues(work, record)
        assert sorted(row for q in queues for row, _, _ in q) == sorted(r for r, _, _ in work)
        for queue in queues:  # one host per queue, boards in their stored order
            assert len({host_key(item[2].url) for item in queue}) == 1
            assert [row for row, _, _ in queue] == sorted(row for row, _, _ in queue)


# --- the fleet-time criterion: a deterministic simulation of the real queues ---------------------


def _makespan(work: _Work, service: dict[int, float], workers: int, queues: list[Any]) -> float:
    """Simulated seconds to finish the fleet under the real `take_ready`, `workers` wide.

    Boards run for their planted service time; a host is released when its board completes, as
    `_scan_body` releases it on collecting the future. No sleeps: time is the event heap's.
    """
    busy: set[str] = set()
    running: list[tuple[float, int, str]] = []  # (finishes at, row, host)
    now = 0.0
    while True:
        for row, _, request in take_ready(queues, busy, workers - len(running)):
            heapq.heappush(running, (now + service[row], row, host_key(request.url)))
        if not running:
            return now
        now, _, host = heapq.heappop(running)
        busy.discard(host)


def _planted() -> tuple[_Work, dict[int, float], dict[str, float]]:
    """The 213-board fleet: the big board takes 600 s, the 12 shared ones 10 s each, singletons 10 s."""
    work = _fleet()
    service = {row: 10.0 for row, _, _ in work}
    service[len(work) - 1] = 600.0
    record: dict[str, float] = {}
    for row, _, request in work:  # last night's busy time: the sum of each host's own boards
        record[host_key(request.url)] = record.get(host_key(request.url), 0.0) + service[row]
    return work, service, record


def test_the_planted_fleet_finishes_near_its_floor_with_a_record_and_not_without() -> None:
    work, service, record = _planted()
    total = sum(service.values())  # 600 + 120 + 2000
    longest_chain = 600.0
    floor = max(longest_chain, total / _WORKERS)
    assert floor == 680.0  # the premise: this fleet's floor is the total over the workers

    new = _makespan(work, service, _WORKERS, host_queues(work, record))
    old = _makespan(work, service, _WORKERS, host_queues(work))

    tolerance = 1.10 * floor  # one worker is pinned by the long chain, so a little over the floor
    assert new <= tolerance, f"{new} s with a record, floor {floor} s"
    assert old > tolerance, f"{old} s without one: the red control must be outside the tolerance"


def test_the_simulation_hands_out_every_board_once_in_either_order() -> None:
    work, service, record = _planted()
    for queues in (host_queues(work), host_queues(work, record)):
        seen: list[int] = []
        busy: set[str] = set()
        while any(queues):
            taken = take_ready(queues, busy, _WORKERS)
            assert taken
            seen.extend(row for row, _, _ in taken)
            for _, _, request in taken:
                busy.discard(host_key(request.url))
        assert sorted(seen) == sorted(service)


# --- the record -------------------------------------------------------------------------------


def test_the_record_round_trips_and_a_later_scan_replaces_it(tmp_path: Any) -> None:
    from boardwatch.store.db import ensure_schema, get_engine

    engine = get_engine(tmp_path)
    ensure_schema(engine)
    with engine.begin() as conn:
        assert get_host_busy(conn) is None
        set_host_busy(conn, 7, {"a.example": 1.23456, "b.example": 40.0})
    with engine.connect() as conn:
        last = get_host_busy(conn)
    assert last is not None
    assert (last.run_id, last.seconds) == (7, {"a.example": 1.235, "b.example": 40.0})
    with engine.begin() as conn:
        set_host_busy(conn, 9, {"c.example": 2.0})
    with engine.connect() as conn:
        replaced = get_host_busy(conn)
    assert replaced is not None
    assert (replaced.run_id, replaced.seconds) == (9, {"c.example": 2.0})


def test_a_record_that_does_not_parse_is_no_record(tmp_path: Any) -> None:
    from boardwatch.store.db import ensure_schema, get_engine

    engine = get_engine(tmp_path)
    ensure_schema(engine)
    for bad in ("not json", "[]", '{"run_id": 1}', '{"run_id": 1, "seconds": {"h": "x"}}'):
        with engine.begin() as conn:
            set_state(conn, HOST_BUSY_KEY, bad)
        with engine.connect() as conn:
            assert get_host_busy(conn) is None, bad


def test_a_record_with_a_value_that_is_not_finite_and_non_negative_is_no_record(
    tmp_path: Any,
) -> None:
    from boardwatch.store.db import ensure_schema, get_engine

    engine = get_engine(tmp_path)
    ensure_schema(engine)
    for bad in ("NaN", "Infinity", "-1"):
        with engine.begin() as conn:
            set_state(conn, HOST_BUSY_KEY, f'{{"run_id": 1, "seconds": {{"h": 2.0, "g": {bad}}}}}')
        with engine.connect() as conn:
            assert get_host_busy(conn) is None, bad


# --- the funnel can show when a host's first request was --------------------------------------


def test_a_first_request_is_told_as_seconds_from_the_start_of_dispatch() -> None:
    from boardwatch.pipeline.runner import _first_request_offset

    assert _first_request_offset(104.5, 100.0) == 4.5
    assert _first_request_offset(4.0, 0.0) == 4.0  # a dispatch at monotonic 0.0 is still measured
    assert _first_request_offset(None, 100.0) is None
    assert _first_request_offset(104.5, None) is None


def test_the_funnel_table_names_when_each_host_started() -> None:
    row = HostFetchCost(
        host="jobs.bigcorp.example", requests=489, attempts=489, span_seconds=1705.0,
        service_seconds=1560.0, pace_seconds=140.0, lock_wait_seconds=0.0,
        first_request_seconds=42.4,
    )
    unknown = HostFetchCost(
        host="x.example", requests=1, attempts=1, span_seconds=1.0, service_seconds=1.0,
        pace_seconds=0.0, lock_wait_seconds=0.0,
    )

    lines = _host_cost_markdown((row, unknown))

    header = next(line for line in lines if line.startswith("| host |"))
    assert header.rstrip().endswith("| first request s |")
    assert next(line for line in lines if "jobs.bigcorp" in line).endswith("| 42 |")
    assert next(line for line in lines if "x.example" in line).endswith("|  |")
