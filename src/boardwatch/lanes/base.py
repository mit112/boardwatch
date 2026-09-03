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
from dataclasses import dataclass, field
from typing import Protocol

from boardwatch.core.models import BoardSnapshot, RawPosting
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.lanes.facets import LaneFacets
from boardwatch.lanes.outcomes import AcquisitionTally
from boardwatch.store.seed_queries import LaneSeed, SeedReader


def lane_snapshot(postings: list[RawPosting], url: str) -> BoardSnapshot:
    """The only sanctioned way to build a lane's snapshot. Always `partial`.

    **THE INGEST PRECONDITION: a lane body must be the EMPLOYER's own text** (D-406). Not the
    aggregator's rendered page, not its site chrome, and above all not its own derived labels.
    job-apps' jobright records stored jobright's PAGE — page title, `SIGN IN JOIN NOW`,
    `Apply on Employer Site` and jobright's own `H1B Sponsor Likely` verdict — inside what
    boardwatch then freezes as the JD. `work_auth` is a blocker family and `INELIGIBLE` must
    carry a quoted span from the frozen JD, so an `ineligible(work_auth)` quoting that label
    would present a third party's GUESS as the employer's stated requirement: a keystone
    violation with a real span behind it, which is the one shape the evidence chain cannot
    detect after the fact. Every control in `lanes/quality.py` above the precondition passes
    such a body — it is long, structured, and its declared role family matches the listing.

    The precondition is `lanes.quality.require_employer_body`, and it is ENFORCED at
    `eligibility.preflight`, the seam where a stored body actually becomes an eligibility
    input. Deliberately not enforced HERE, and the reason is the standing quarantine rule: a
    body refused at ingest is never written, and a posting that was never written cannot
    re-enter — that is a drop, not a quarantine, and a false positive would cost a real job
    with no way back. What a lane owes this function is a body it can attribute to the
    employer; what the store owes the lane is that a body it cannot is HELD rather than judged
    or discarded (`store/quarantine_queries.py`).

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
    # Turn watching ON for this company when the lane applies it. Default OFF, which is what
    # every lane but a secondhand one wants: `queries.upsert_lane_company` stores a lane company
    # `watched=False` (D-285) because `scan/coordinator` appends `unknown provider` for a watched
    # row whose provider it cannot scan. A lane sets this True ONLY for a company on a provider the
    # scanner DOES know — an Indeed tier-1 convergence onto a supported board — so the scan then
    # fetches the employer's real JD and drains the secondhand body this lane wrote (D-414(a)).
    # A True here can only turn watching on; `upsert_lane_company` never unwatches on this flag.
    watch: bool = False


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
    # Posting URLs this lane FOUND and cannot resolve itself, for `lane_seeds`. RETURNED rather
    # than written, and that is the whole point: `collect` runs in a fetch worker while
    # `apply_board` is the pipeline's single writer, so a lane that wrote its own seeds would be
    # a second writer on one SQLite store — the exact thing the fetch/apply split exists to
    # prevent. The runner persists these in the serial apply phase, where the `run_id` they are
    # attributed to is already in hand.
    #
    # Empty — never absent — for a lane that discovers no seeds, which is most of them.
    discovered_seeds: tuple[str, ...] = ()
    # `(seed id, resolved)` for every seed this lane TRIED, for the same reason and by the same
    # route. Whether each entry MOVES the retirement ceiling is the runner's call, not a property
    # of this list: a resolved-but-unapplied seed and a redundant alias (`uncharged_resolved`) are
    # recorded here yet NOT charged. When it is charged, the counter answers "how much work has this
    # seed cost", which is the question its cost bound is about.
    #
    # A resolver that returns seeds it consumed but forgets to list them here retries them
    # forever at one request each, so this is the drain, and it is not optional for a lane that
    # reads `LaneContext.pending_seeds`.
    seed_attempts: tuple[tuple[int, bool], ...] = ()
    # Seed ids in `seed_attempts` that RESOLVED WITHOUT A PHYSICAL GET, so the runner must close
    # them (`resolved_at`) WITHOUT charging the retirement ceiling. The one producer today is a
    # redundant alias: two seed URLs naming one posting, where the first resolved and the rest name
    # a posting this run already produced. Separate from `seed_attempts` because "did it resolve"
    # and "did it cost a request" are two independent facts about one seed; folding a redundant
    # alias's free closure into a charged attempt is the leak this field exists to stop. Empty --
    # never absent -- for a lane that spends a request on everything it resolves.
    uncharged_resolved: tuple[int, ...] = ()
    # Seed url + short repr for every seed whose resolver raised an UNEXPECTED exception -- a real
    # code defect (KeyError/TypeError/`RawPosting` validation/...), NOT a content outcome and NOT a
    # typed fetch failure, both of which are already classified into the acquisition tally. Carried
    # out rather than swallowed so the runner can report them as a VISIBLE lane error: recording
    # such a crash as `extracted_empty` would disguise the defect and age a real seed out on a
    # false claim. Empty -- never absent -- for a run in which nothing crashed the resolver.
    resolver_errors: tuple[str, ...] = ()
    # Seed URLs a PRODUCER dropped as MALFORMED before they could become a `discovered_seeds` entry:
    # a value that failed `is_seedable_url` (bad scheme/host/port, a control char, an IP literal, a
    # multi-dot host). Distinct from `resolver_errors` (a resolver CRASH) and from the write point's
    # `unroutable` refusal (a malformed URL that DID reach `record_seeds`): a producer that silently
    # `continue`s past a malformed candidate makes that defect invisible past the write path -- the
    # absent-versus-zero confusion the acquisition tally exists to prevent -- so it is carried out
    # for the runner to surface. The ORDINARY "resolves to a known board / names no vendor this lane
    # resolves" case is NOT carried here -- only a malformed URL -- so this never turns a quiet
    # no-vendor day into noise. Empty -- never absent -- for a run whose producers emitted none.
    refused_seeds: tuple[str, ...] = ()


def _no_seeds(
    *,
    hosts: frozenset[str],
    host_suffixes: frozenset[str] = frozenset(),
    max_attempts: int,
    limit: int,
) -> tuple[LaneSeed, ...]:
    """The default `SeedReader`: no backlog, for a lane that resolves no seeds.

    A module-level function rather than a lambda so the default is importable and a test can
    assert a lane got THE default rather than something that merely behaved like it.
    """
    return ()


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


@dataclass(frozen=True)
class LaneContext:
    """Everything one run can hand a lane factory, so the registry stays one row per lane.

    This exists to remove a named wart. Before it, `LaneFactory` was `Callable[..., Lane]` —
    `...`, so mypy checked no call site at all — and `_run_lanes` carried
    `if name == LinkedInLane.name:` to pass that one factory a `rotation_index` keyword nothing
    else took. Every lane that needed a value the previous ones did not would widen the signature
    again and add a branch beside it, which is a shared registration surface that every
    concurrent lane build has to edit and therefore conflict on.

    A frozen dataclass instead: a new lane that needs a new per-run value adds a FIELD here and
    reads it, and no existing FACTORY moves. `LaneFactory` becomes `Callable[[LaneContext],
    Lane]`, which mypy can actually check.

    **Not "nothing moves".** `_run_lanes` constructs the context and must supply any field
    without a default, so it is edited once per such field — one line in one place, against a
    keyword added to one factory signature plus an `if name == ...` branch beside it, which is
    what the registry had before and what every concurrent lane build had to conflict on.

    `rotation_index` is required and has NO DEFAULT, carried over verbatim from
    `_linkedin_lane`'s own reasoning: a default of 0 is a silent-zero path — every caller that
    forgot to pass one would draw the same cells of the hub matrix forever, the rotation would
    never advance, and no test would go red, because the lane would still fetch, still report and
    still look correct. Required means the one caller with a run row to derive it from has to
    produce it.

    **`run_id` is deliberately NOT here.** Every store write a lane causes happens in the serial
    apply phase, which already holds it; carrying a second copy into the fetch workers would
    invite a lane to write directly, which is what `discovered_seeds` and `seed_attempts` exist
    to make unnecessary.

    Frozen only against REBINDING — `Settings` is a pydantic model with mutable container fields,
    so this is not a defence against a factory that reaches into `settings` and mutates a dict.
    Nothing does, and the honest statement of what freezing buys is: registry ORDER cannot change
    which context object a later factory receives.
    """

    settings: Settings
    facets: LaneFacets
    rotation_index: int
    # The watched companies a per-company search cell may name, in the store's own order
    # (`queries.watched_company_names`). Here for the same reason `facets` is: it comes from the
    # STORE, and a lane that reached in for its own employer list would be both untestable and
    # the one place a hardcoded company could hide.
    #
    # Defaulted to EMPTY, which yields no cells at all, so the four lanes that build none are
    # unaffected and no test of them had to move. Empty is also the honest reading for a store
    # with no watched boards: ask nothing, rather than fail.
    watched_companies: tuple[str, ...] = ()
    # How a lane READS `lane_seeds`, without ever holding a `Connection`. The runner owns the
    # connection and supplies this closure, exactly as it supplies `CompanyAdmission` — and for
    # the same recorded reason: the decision needs store access, and a lane opening its own
    # engine would be a second writer's worth of risk taken for a read.
    #
    # Defaulted to a reader that returns nothing, so the three lanes that resolve no seeds are
    # unaffected and no test of them had to move. The default is EMPTY rather than raising:
    # a lane is additive breadth, and a resolver handed no backlog must report that it found
    # nothing, not fail the run.
    pending_seeds: SeedReader = field(default=_no_seeds)
