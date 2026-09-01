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

from collections.abc import Callable
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
    """One company's postings from this lane, keyed the way `apply_board` can be reached.

    `apply_board(engine, snapshot, company_id, run_id)` takes a `company_id`, and the only
    route to one is `(provider, slug)` — `companies` is UNIQUE(provider, slug), which is
    what `queries.upsert_watch` and `queries.get_watched_companies` both key on. A display
    name cannot get there, so grouping a lane's postings by name is the wrong granularity
    twice over: an employer with two boards yields ONE name-grouped snapshot, which applied
    against one `company_id` writes the other board's postings under the wrong company,
    where they can never converge and close after two misses; and one employer whose name
    varies across aggregator listings yields several snapshots for one row.

    This is the same identity `admission.CompanyBudget` charges against, and the same pair
    `dereference.parse_posting_target` already recovers from a posting URL.

    `name` is the employer's DISPLAY name, and it rides alongside the identity rather than
    standing in for it. It is what `queries.upsert_lane_company` writes into `companies.name`,
    which the funnel's leads table, the morning artifact and every rendered lead read. Required
    rather than defaulted: a lane that cannot name an employer should say so by falling back to
    something it can evidence — hiring.cafe uses `board_token` when
    `enriched_company_data.name` is blank — not by silently inheriting a placeholder from this
    dataclass, where no reader could tell the two apart.
    """

    provider: str
    slug: str
    name: str
    snapshot: BoardSnapshot


@dataclass(frozen=True)
class LaneResult:
    """What one lane collected, plus how deep it read to collect it.

    `search_pages` is `(search url, pages fetched)` per search this lane made, and it exists
    because a posting count cannot tell a facet that RAN OUT of results from one that was
    TRUNCATED by the page ceiling. Both report fewer postings than the ceiling allows; only the
    first is benign, and the second is reach the run silently left on the table. Empty -- never
    absent -- for a lane that makes no search at all, which is honest: the job-apps lane reads a
    local directory, so it has no page count to report rather than a page count of one.
    """

    snapshots: tuple[LaneCompanySnapshot, ...]
    tally: AcquisitionTally
    search_pages: tuple[tuple[str, int], ...] = ()


# (provider, slug) -> may this lane spend requests on that company. The runner supplies it:
# the decision needs a store connection to tell an already-known company from a new one, and
# `admission.CompanyBudget` says in its own docstring that it cannot make that call.
CompanyAdmission = Callable[[str, str], bool]


class Lane(Protocol):
    name: str

    def collect(self, fetcher: Fetcher, admits: CompanyAdmission) -> LaneResult:
        """Collect this lane's postings, asking `admits` before spending on a company.

        `admits` MUST be called exactly once per distinct `(provider, slug)`, never once per
        posting. The per-run cap counts companies, so a per-posting call would charge one
        employer's four listings against four slots; and the answer is a property of the
        company, so re-asking cannot change it, only make the refusal report lie.

        The call also has to come BEFORE the bodies are fetched, which is why the predicate
        is passed in rather than applied to the result: a body costs one request per posting,
        so a runner that filters a finished `LaneResult` has already paid for everything it
        is about to discard.
        """
        ...
