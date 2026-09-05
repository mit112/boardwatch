"""The order the scan submits boards in — now a ready queue, not a static permutation.

`Fetcher` serializes same-host requests for their full duration, so a worker that picks up a
board whose host is already busy does no work at all until the first one finishes, and a host's
boards can only ever run one after another. The stored order is company rowid, which is the
order boards were ADDED, and boards are added in per-provider batches — and five of the six
providers serve every board from ONE API host. On the run-128 fleet that made the first sixteen
boards a single host.

The static round-robin that fixed THAT gave every host one slot per round, so on the live
288-board fleet — 131 hosts — a ten-board host's second board sat at position 134 and its chain
ran alone for the last 27.6 minutes of run 3. The tests below are written to fail against that
order, and against the two that look right and are not: the identity function (rowid order) and
grouping by PROVIDER instead of by host.
"""

from __future__ import annotations

from collections import deque
from itertools import pairwise
from typing import Any

from boardwatch.core.models import BoardRequest
from boardwatch.core.politeness import host_key
from boardwatch.scan.coordinator import host_queues, take_ready


def _work(*urls: str) -> list[tuple[Any, Any, BoardRequest]]:
    """One entry per URL. Only `BoardRequest.url` is read, so the row and provider are the
    index — which is also what makes "is a permutation" checkable by identity below."""
    return [
        (index, index, BoardRequest(provider="p", slug=f"s{index}", url=url))
        for index, url in enumerate(urls)
    ]


def _drain(work: list[tuple[Any, Any, BoardRequest]], slots: int) -> list[str]:
    """The host of every board, in the order the coordinator submits it.

    Reproduces `_scan_body`'s loop: fill `slots`, then collect the oldest board in flight,
    release its host and refill. Equal-cost boards (oldest-first) is the HARSHEST case for a
    ready queue — the real deep host is the slow one, and a chain whose boards outlast everyone
    else's only reaches its next board sooner than this.
    """
    queues = host_queues(work)
    busy: set[str] = set()
    inflight: deque[str] = deque()
    submitted: list[str] = []
    while True:
        taken = [host_key(item[2].url) for item in take_ready(queues, busy, slots - len(inflight))]
        submitted.extend(taken)
        inflight.extend(taken)
        if not inflight:
            return submitted
        busy.discard(inflight.popleft())


def _positions(hosts: list[str], host: str) -> list[int]:
    return [index for index, value in enumerate(hosts) if value == host]


_SHARED = "https://boards-api.greenhouse.io/v1/boards/{}/jobs"
_SHARED_HOST = "boards-api.greenhouse.io"
_TENANT = "https://{}.wd5.myworkdayjobs.com/wday/cxs/{}/Careers/jobs"


def test_a_deep_hosts_next_board_is_offered_on_the_very_next_refill() -> None:
    """THE reason the scan ends on one host. A host's boards are a serial chain, so the chain is
    the critical path and every slot it does not get is a slot the run ends late by. Giving each
    host one board per ROUND put the ten smartrecruiters boards at positions 3, 134, 147 … of
    288, so board 2 was not reached until ~72 minutes in and the chain finished 27.6 minutes
    after every other provider. Once the host is free again its next board must be the next
    thing submitted — which pins the gap at the pool width, not the fleet width."""
    work = _work(
        *[_SHARED.format(i) for i in range(10)],
        *[_TENANT.format(f"t{i}", f"t{i}") for i in range(130)],
    )

    hosts = _drain(work, slots=8)

    at = _positions(hosts, _SHARED_HOST)
    gaps = [b - a for a, b in pairwise(at)]
    assert max(gaps) <= 8, f"the chain waits {max(gaps)} boards between its own: {at}"


def test_a_host_never_has_two_boards_in_flight() -> None:
    """A second worker on a busy host is not slow work, it is NO work: it holds a pool slot and
    a live connection while the lock makes it wait out the first board in full. Submitting the
    whole fleet up front could not prevent that — the pool takes whatever is next. Refusing to
    hand out a busy host is the only thing that can, and it is why pulling a chain forward is
    safe now and was not before."""
    work = _work(
        *[_SHARED.format(i) for i in range(5)],
        *[f"https://api.ashbyhq.com/posting-api/job-board/{i}" for i in range(5)],
        *[f"https://api.lever.co/v0/postings/{i}?mode=json" for i in range(5)],
    )

    queues = host_queues(work)
    busy: set[str] = set()
    taken = take_ready(queues, busy, 8)

    hosts = [host_key(item[2].url) for item in taken]
    assert len(hosts) == len(set(hosts)) == 3, f"{len(hosts)} boards over {len(set(hosts))} hosts"
    assert take_ready(queues, busy, 8) == [], "a host still in flight was offered again"


def test_the_deepest_host_outranks_a_shallower_one_on_every_refill() -> None:
    """Depth order is not cosmetic: it is which chain gets the slot when several are free. A
    fleet is mostly singletons — 135 of run 3's 288 boards are Workday tenants with a host each
    — so a queue order that let them win would starve the one chain that decides when the run
    ends, and it would do it on every single refill, not once at the head."""
    work = _work(
        *[_TENANT.format(f"single{i}", f"single{i}") for i in range(20)],
        *[f"https://api.lever.co/v0/postings/{i}?mode=json" for i in range(3)],
        *[_SHARED.format(i) for i in range(6)],
    )

    hosts = _drain(work, slots=3)

    assert _positions(hosts, _SHARED_HOST) == [0, 3, 6, 9, 12, 15], f"deepest starved: {hosts}"
    assert _positions(hosts, "api.lever.co") == [1, 4, 7], f"second deepest starved: {hosts}"


def test_grouping_is_by_HOST_not_by_provider() -> None:  # noqa: N802
    """Workday has one host per tenant and 135 of them on the live fleet; every other provider
    has exactly one host for all its boards. Bucketing by provider name would put those 135
    independent hosts in a single queue and run them one at a time — serializing the only boards
    that were already parallel. Three distinct-host boards must therefore be able to sit in
    flight together, which a provider-keyed queue cannot produce."""
    work = _work(
        _SHARED.format("a"), _SHARED.format("b"), _SHARED.format("c"),
        _TENANT.format("x", "x"), _TENANT.format("y", "y"), _TENANT.format("z", "z"),
    )

    hosts = _drain(work, slots=4)

    assert len(set(hosts[:4])) == 4, f"only {len(set(hosts[:4]))} distinct hosts in flight"


def test_every_board_is_submitted_exactly_once() -> None:
    """A schedule that drops or duplicates a board silently changes what the run scanned, and a
    lazily-filled queue can do both — it stops when nothing is in flight, so a host it refuses
    to offer is a host it never scans. The row index is the identity here, so this compares the
    SET, not the length."""
    work = _work(
        *[_SHARED.format(i) for i in range(9)],
        *[_TENANT.format(f"t{i}", f"t{i}") for i in range(7)],
        "https://api.ashbyhq.com/posting-api/job-board/one",
    )

    queues = host_queues(work)
    busy: set[str] = set()
    submitted: list[Any] = []
    inflight: deque[str] = deque()
    while True:
        taken = take_ready(queues, busy, 4 - len(inflight))
        submitted.extend(row for row, _, _ in taken)
        inflight.extend(host_key(item[2].url) for item in taken)
        if not inflight:
            break
        busy.discard(inflight.popleft())

    assert sorted(submitted) == sorted(row for row, _, _ in work)


def test_a_fleet_with_no_host_collision_keeps_its_stored_order() -> None:
    """Nothing to gain, so nothing to change: equal-depth queues are ordered by `sorted`'s
    stability, so a fleet of singletons is dispatched exactly as it is stored and the scan's
    submission sequence stays comparable with the run before it."""
    work = _work(*[_TENANT.format(f"t{i}", f"t{i}") for i in range(5)])

    assert [q[0][0] for q in host_queues(work)] == [0, 1, 2, 3, 4]


def test_boards_on_one_host_keep_their_relative_order() -> None:
    """They serialize anyway, so their order among themselves is the stored one — a shuffle
    would only make a scan harder to compare against the run before it."""
    work = _work(*[_SHARED.format(i) for i in range(4)])

    assert [row for row, _, _ in host_queues(work)[0]] == [0, 1, 2, 3]


def test_take_ready_never_hands_out_more_than_the_free_slots() -> None:
    """`slots` is `scan_workers` minus what is already in flight. Overshooting would rebuild the
    unbounded backlog the ready queue exists to remove — and with it the Ctrl-C that has to wait
    out the whole fleet, and the workers parked on a locked host."""
    work = _work(*[_TENANT.format(f"t{i}", f"t{i}") for i in range(20)])

    assert len(take_ready(host_queues(work), set(), 3)) == 3
    assert take_ready(host_queues(work), set(), 0) == []


def test_an_empty_fleet_is_not_an_error() -> None:
    """`--company` can select nothing, and the scan must submit nothing rather than block."""
    assert host_queues([]) == []
    assert take_ready([], set(), 8) == []
