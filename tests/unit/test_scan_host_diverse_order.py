"""`host_diverse` — the dispatch order the scan submits boards in.

`Fetcher` serializes same-host requests for their full duration, so a worker that picks up a
board whose host is already busy does no work at all until the first one finishes. The stored
order is company rowid, which is the order boards were ADDED, and boards are added in
per-provider batches — and five of the six providers serve every board from ONE API host. On
the run-128 fleet that made the first sixteen boards a single host.

The tests below are written to fail against the two orders that look right and are not: the
identity function (today's order), and grouping by PROVIDER instead of by host.
"""

from __future__ import annotations

from typing import Any

from boardwatch.core.models import BoardRequest
from boardwatch.scan.coordinator import host_diverse


def _work(*urls: str) -> list[tuple[Any, Any, BoardRequest]]:
    """One entry per URL. Only `BoardRequest.url` is read, so the row and provider are the
    index — which is also what makes "is a permutation" checkable by identity below."""
    return [
        (index, index, BoardRequest(provider="p", slug=f"s{index}", url=url))
        for index, url in enumerate(urls)
    ]


_SHARED = "https://boards-api.greenhouse.io/v1/boards/{}/jobs"
_TENANT = "https://{}.wd5.myworkdayjobs.com/wday/cxs/{}/Careers/jobs"


def test_a_run_of_one_host_does_not_open_the_scan() -> None:
    """Rowid order on the real fleet starts with 16 boards on `api.ashbyhq.com`, so a
    four-wide pool spends its first boards with three workers blocked on one lock and an
    eight-wide pool with seven. The head of the order must be as many distinct hosts as the
    fleet can supply — this assertion fails against the identity function."""
    work = _work(
        *[_SHARED.format(i) for i in range(6)],
        *[_TENANT.format(f"t{i}", f"t{i}") for i in range(4)],
    )

    ordered = host_diverse(work)

    heads = [req.url for _, _, req in ordered[:5]]
    assert len({url.split("/")[2] for url in heads}) == 5, f"head repeats a host: {heads}"


def test_grouping_is_by_HOST_not_by_provider() -> None:
    """Workday has one host per tenant and 105 of them on the live fleet; every other provider
    has exactly one host for all its boards. Bucketing by provider name would put those 105
    independent hosts in a single bucket and interleave them with a shared host that can only
    ever run one at a time — spreading the boards that were already parallel and doing nothing
    for the ones that were not. Three distinct-host boards must therefore be able to sit
    consecutively, which a provider-keyed round-robin cannot produce."""
    work = _work(
        _SHARED.format("a"), _SHARED.format("b"), _SHARED.format("c"),
        _TENANT.format("x", "x"), _TENANT.format("y", "y"), _TENANT.format("z", "z"),
    )

    hosts = [req.url.split("/")[2] for _, _, req in host_diverse(work)]

    assert len(set(hosts[:4])) == 4, f"only {len(set(hosts[:4]))} distinct hosts in the head"


def test_the_spread_is_SUSTAINED_not_just_the_first_few_boards() -> None:  # noqa: N802
    """A pool of eight works through the fleet many times over, so an order that front-loads one
    board per host and then dumps every remainder in stored order leaves the whole tail
    clustered — and passes every prefix assertion above. With equal-depth hosts, round-robin
    puts a different host at every position, so NO two adjacent entries may share one."""
    work = _work(
        *[_SHARED.format(i) for i in range(4)],
        *[f"https://api.ashbyhq.com/posting-api/job-board/{i}" for i in range(4)],
        *[f"https://api.lever.co/v0/postings/{i}?mode=json" for i in range(4)],
    )

    hosts = [req.url.split("/")[2] for _, _, req in host_diverse(work)]

    collisions = [(i, hosts[i]) for i in range(1, len(hosts)) if hosts[i] == hosts[i - 1]]
    assert not collisions, f"adjacent boards share a host at {collisions}: {hosts}"


def test_every_board_is_submitted_exactly_once() -> None:
    """A reorder that drops or duplicates a board silently changes what the run scanned. The
    row index is the identity here, so this compares the SET, not the length."""
    work = _work(
        *[_SHARED.format(i) for i in range(9)],
        *[_TENANT.format(f"t{i}", f"t{i}") for i in range(7)],
        "https://api.ashbyhq.com/posting-api/job-board/one",
    )

    ordered = host_diverse(work)

    assert sorted(row for row, _, _ in ordered) == sorted(row for row, _, _ in work)
    assert len(ordered) == len(work)


def test_a_fleet_with_no_host_collision_keeps_its_stored_order() -> None:
    """Nothing to gain, so nothing to change: an order that churned here would make the
    scan's submission sequence unpredictable for no throughput at all."""
    work = _work(*[_TENANT.format(f"t{i}", f"t{i}") for i in range(5)])

    assert [row for row, _, _ in host_diverse(work)] == [0, 1, 2, 3, 4]


def test_boards_on_one_host_keep_their_relative_order() -> None:
    """They serialize anyway, so their order among themselves is the stored one — a shuffle
    would only make a scan harder to compare against the run before it."""
    work = _work(*[_SHARED.format(i) for i in range(4)])

    assert [row for row, _, _ in host_diverse(work)] == [0, 1, 2, 3]


def test_an_empty_fleet_is_not_an_error() -> None:
    """`--company` can select nothing, and `max()` over no queues raises without a default."""
    assert host_diverse([]) == []
