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

from collections import Counter, deque
from itertools import pairwise
from typing import Any

from boardwatch.core.models import BoardRequest
from boardwatch.core.politeness import host_key
from boardwatch.providers.registry import PROVIDER_CLASSES
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


def test_a_hosts_boards_are_DISPATCHED_in_their_stored_order_not_just_QUEUED_in_it() -> None:  # noqa: N802
    """The one above asserts what `host_queues` BUILDS; this asserts what `take_ready` HANDS OUT.

    They are not the same claim, and only this one is load-bearing. `take_ready` pops from a
    queue, so the queue being in stored order says nothing about which END it is served from —
    with the other tests alone, changing `queue.pop(0)` to `queue.pop()` leaves every one of them
    green while the deepest chain runs newest-rowid-first. That silently breaks the "stable
    within a host, so a scan stays comparable with the run before it" claim `host_queues`' own
    docstring makes, and changes which subset an interrupted run leaves applied.

    Drained the way `_scan_body` drains it: take, then release the host as its future completes.
    """
    work = _work(*[_SHARED.format(i) for i in range(4)])
    queues = host_queues(work)
    busy: set[str] = set()

    dispatched: list[int] = []
    while any(queues):
        taken = take_ready(queues, busy, 8)
        assert taken, "the drain stalled with boards still queued"
        for row, _, request in taken:
            dispatched.append(row)
            busy.discard(host_key(request.url))  # the future completed

    assert dispatched == [0, 1, 2, 3], (
        f"one host's boards were dispatched as {dispatched}, not in their stored order"
    )


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


# --- T323: a provider's own cap on boards in flight, across all of its hosts -------------------


class _Capped:
    """Stands in for a provider that declares `max_boards_in_flight` (Eightfold's shape)."""

    def __init__(self, cap: int) -> None:
        self.max_boards_in_flight = cap


_EIGHTFOLD = "https://{}.eightfold.example/api/pcsx/search"  # one HOST per board, like a tenant
_CAP = 2


def _capped_work(
    capped: int, uncapped: int = 0, *, cap: int = _CAP
) -> list[tuple[Any, Any, BoardRequest]]:
    """`capped` boards of provider `ef` (one host each) FIRST in stored order, then `uncapped`
    boards of provider `wd` (also one host each, no cap). Row = a label, so a test can say WHICH
    board was handed out."""
    limited, free = _Capped(cap), object()
    return [
        *[
            (f"ef{i}", limited, BoardRequest(provider="ef", slug=f"ef{i}", url=_EIGHTFOLD.format(i)))
            for i in range(capped)
        ],
        *[
            (f"wd{i}", free, BoardRequest(
                provider="wd", slug=f"wd{i}", url=_TENANT.format(f"t{i}", f"t{i}"),
            ))
            for i in range(uncapped)
        ],
    ]


def test_a_capped_provider_is_handed_out_at_most_its_cap_however_many_slots_are_free() -> None:
    """THE T323 defect, in one call. Nine Eightfold boards sit on nine DIFFERENT hosts, so `busy`
    sees no collision and sixteen free slots took all nine at once — five 2,000-listing boards
    hitting one backend whose throttle spans tenants. The cap is per PROVIDER, which no host key
    can express."""
    taken = take_ready(host_queues(_capped_work(9)), set(), 16)

    assert [row for row, _, _ in taken] == ["ef0", "ef1"], "more boards than the cap, or the wrong two"


def test_a_capped_provider_never_exceeds_its_cap_across_refills_and_every_board_still_runs() -> None:
    """Drained the way `_scan_body` drains it: take, then release the oldest board's host AND its
    provider count as its future completes. The peak is asserted EQUAL to the cap, not just below
    it, so a cap that quietly collapsed to one lane would also fail. Every board is submitted
    exactly once, which is the termination claim: a count that was never released would strand the
    capped boards in their queues and the scan would end with them unscanned."""
    work = _capped_work(9, 7)
    queues = host_queues(work)
    busy: set[str] = set()
    in_flight: Counter[str] = Counter()
    running: deque[tuple[Any, str, str]] = deque()
    submitted: list[Any] = []
    peak = 0
    while True:
        for row, _, request in take_ready(queues, busy, 16 - len(running), in_flight):
            submitted.append(row)
            running.append((row, host_key(request.url), request.provider))
        peak = max(peak, sum(1 for _, _, provider in running if provider == "ef"))
        if not running:
            break
        _, host, provider = running.popleft()
        busy.discard(host)
        in_flight[provider] -= 1

    assert peak == _CAP, f"eightfold boards peaked at {peak} in flight, not {_CAP}"
    assert sorted(submitted) == sorted(row for row, _, _ in work), "a board was dropped or repeated"


def test_a_provider_without_a_cap_is_not_held_back_by_anothers() -> None:
    """The cap must not leak. The capped provider's boards come FIRST in stored order and are
    skipped, and the uncapped boards behind them must still all be handed out in the same call —
    a skip that stopped scanning, or a cap that bled across providers, would hold them back."""
    taken = take_ready(host_queues(_capped_work(9, 7)), set(), 16)

    rows = [row for row, _, _ in taken]
    assert [r for r in rows if r.startswith("wd")] == [f"wd{i}" for i in range(7)]
    assert [r for r in rows if r.startswith("ef")] == ["ef0", "ef1"]


def test_a_skipped_capped_board_keeps_its_place_and_is_offered_next_when_a_slot_frees() -> None:
    """`exactly like a busy host`: the capped head is passed over, not discarded and not moved to
    the back. When one of its provider's boards is released it is offered AHEAD of the uncapped
    boards queued behind it — otherwise the Eightfold chain would start only after the rest of the
    fleet had been dispatched, which is the whole of the scan's tail."""
    work = _capped_work(3, 2, cap=1)
    queues = host_queues(work)
    busy: set[str] = set()
    in_flight: Counter[str] = Counter()

    first = take_ready(queues, busy, 2, in_flight)
    assert [row for row, _, _ in first] == ["ef0", "wd0"], "ef1 should be skipped, not taken"

    ef0 = first[0][2]
    busy.discard(host_key(ef0.url))  # ef0's future completed ...
    in_flight[ef0.provider] -= 1  # ... and so does its provider's count

    second = take_ready(queues, busy, 1, in_flight)
    assert [row for row, _, _ in second] == ["ef1"], "the skipped board lost its place"


def test_only_eightfold_declares_a_cap_and_every_declared_cap_can_be_met() -> None:
    """Pins both halves of "other providers unchanged": the declared set is exactly Eightfold's,
    written out literally because comparing against the constant itself would pass for any value.
    A cap below 1 can never be satisfied, so the ready queue would skip that provider's boards
    forever and the scan would finish without them — silently."""
    declared = {
        cls.name: getattr(cls, "max_boards_in_flight")  # noqa: B009 - an optional attribute
        for cls in PROVIDER_CLASSES
        if hasattr(cls, "max_boards_in_flight")
    }

    assert declared == {"eightfold": 2}
    assert all(isinstance(cap, int) and cap >= 1 for cap in declared.values())
