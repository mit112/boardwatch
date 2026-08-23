"""The Lane protocol (JD-acquisition spec §4.1, §4.2).

A lane is NOT a seventh Provider, for two verified reasons: the provider registry test
asserts set EQUALITY against the six names, and fixture rule R13 requires a flat pinned
fixture dir per registered provider in both directions. A lane also does not fit the
protocol — `Provider` declares board_url / fetch_board / healthcheck and no fetch_posting,
and `registry` duck-types five further undeclared members.

What a lane does instead is return the same `BoardSnapshot` that a provider returns, so it
reuses `scan.apply.apply_board` and inherits every persistence invariant rather than
restating them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from boardwatch.core.models import BoardSnapshot, RawPosting
from boardwatch.core.politeness import Fetcher
from boardwatch.lanes.outcomes import AcquisitionTally


def lane_snapshot(postings: list[RawPosting], url: str) -> BoardSnapshot:
    """The only sanctioned way to build a lane's snapshot. Always `partial`.

    `partial` rather than `complete` is load-bearing, not conservative: `_process_missing`
    runs on `complete` only, and `BoardSnapshot` permits an EMPTY `complete`, which sets
    `effective = frozenset()` and marks every open posting of that company missing — two
    consecutive such scans close them all (`CLOSE_AFTER_MISSES = 2`). A lane never
    enumerates a whole board, so it can never make that claim truthfully.

    `listed_ids` stays empty for the same reason. `_reset_listed_but_unrefreshed` returns
    immediately on an empty set, which is the correct behaviour here; a non-empty set would
    assert an enumeration the lane did not perform.

    The coverage fields stay None. `board_reported_total` must never be backfilled from
    `len(postings)` — D-271 records that an unfailable ratio is worse than no ratio.
    """
    return BoardSnapshot(status="partial", postings=postings, url=url)


@dataclass(frozen=True)
class LaneCompanySnapshot:
    """One company's postings from this lane. `apply_board` is per-company."""

    company_name: str
    snapshot: BoardSnapshot


@dataclass(frozen=True)
class LaneResult:
    snapshots: tuple[LaneCompanySnapshot, ...]
    tally: AcquisitionTally


class Lane(Protocol):
    name: str

    def collect(self, fetcher: Fetcher) -> LaneResult: ...
