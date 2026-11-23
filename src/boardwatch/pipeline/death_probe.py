"""Let a MEASURED death close a posting the scanner structurally cannot reach (D-325).

**The population, and why it needs its own mechanism.** `_process_missing` (`scan/apply.py`) is
the only writer of `status='closed'`, it runs on `complete` snapshots only, `lane_snapshot` is
always `partial`, and lane companies are inserted `watched=False` so the coordinator never
revisits them (D-314). A lane re-acquires by SEARCH, not by enumerating a board, so a posting
that drops out of the result set is simply never seen again — **absence can never be evidence**
for these rows, armed or disarmed. Age-based and missed-run closing were both measured and
REJECTED: when the role facet changed, 0 of 290 prior postings were re-seen, yet 40 of 45 probed
were still alive.

What is left is a POSITIVE observation. Two of them are available, and this module runs both
over disjoint halves of the class: the stored URL answering gone, and — for the three providers
that publish a whole-board list endpoint — the posting's id being **absent from its own
company's listing**.

**The four narrowings, each of which is the whole safety argument.**

1. **Only `refetch_gone`.** A non-redirect 404/410 from the URL asked about. Never
   `refetch_gone_after_redirect` — `Fetcher` follows redirects, so an employer migrating ATS
   answers 404 from a host that was never asked about, and closing on it would retire live
   requisitions one employer at a time. Never `refetch_error`: a timeout, a 403 from a
   bot-blocker or a 5xx says nothing about the requisition. `core/liveness.py` owns that
   classification and this module reads its typed signal, never a status code or a message.
2. **Only `companies.watched = 0`** — with ONE stated exception, T334 (D-705). A watched board
   enumerates itself and closes its own postings correctly; adding a second, weaker path over
   it would be a regression, not a fix. The predicate is the honest one — it covers unwatched
   `source='user'` companies too, which have the identical defect. The exception is a watched
   board the empty-complete guard has refused for `GUARD_DRAIN_NIGHTS` consecutive pipeline
   nights: the scanner counts no miss on an empty answer, so for that board it cannot produce a
   signal either, and the guard's own comment named "a board that genuinely empties never closes"
   as a residual. Its open postings join the URL path as a second population, each closing only
   on its own two-strike proof; the board stays watched, and a relist resumes ordinary miss
   counting with no special handling.
3. **Two consecutive strikes in different runs**, mirroring `CLOSE_AFTER_MISSES = 2`. An
   `unknown` probe neither increments nor resets, which mirrors the board path exactly: there a
   `failed` snapshot leaves `consecutive_missing` alone and only a POSITIVE observation resets
   it (D23). The alternative — unknown resets — disarms the check against any host that
   intermittently 403s.
4. **Its own column.** `death_strikes`, never `consecutive_missing`. One counter fed by two
   different signals could close a posting on one board absence plus one 404, and no report
   could then say which evidence closed it.

**The drain, on both sides of the gate.** An `alive` probe or a present listing clears the
counter here; a positive board or lane sighting clears it in `_apply_listed`, alongside the
`consecutive_missing` reset it has always done. A posting this closes is reopened by the
ordinary re-sighting path, which runs on `partial` snapshots — verified in source: `apply_board`
calls `_apply_listed` for every non-failed, non-unchanged snapshot, and only `_process_missing`
and `_persist_validators` are gated on `complete`.

**What the URL half is worth, stated plainly because it will otherwise be trusted.** Measured
against a control of postings the scanner PROVED closed (n=60) it detects **4 — 6.7%**, Wilson
95% CI 2.6%–15.9%. By provider: greenhouse 4/21, **workday 0/37** — every closed Workday
requisition still answers HTTP 200. Against 90 live lane postings it returned **0 false
deaths**. It almost never lies and it almost never fires.

**D-647: a Workday row is now asked through its CXS endpoint, not its page.** The page answers
200 for a closed requisition, and an `alive` here RESETS earned strikes, so the page probe was
worse than blind on Workday too. The endpoint answers an unposted requisition 403 naming `S22`
(`workday_unposted`) and a removed one 404 (`refetch_gone`); both strike. Re-measured 2026-10-27
on the same kind of control, scanner-proven-closed Workday postings closed in the last 30 days:
the page probe **0 of 80**, the CXS probe **80 of 80** (Wilson 95% CI 95.4%–100%). Of 80 postings
their own board had listed that morning, 76 answered alive and 4 answered S22. All 4 were absent
from their board's live search an hour later, and the same search found the alive ones, so they
were real closures the scanner had not reached yet. That makes **0 false deaths in 76**. The
class it covers is small: 284 open unwatched rows carried a Workday URL that day.

**D-648: an Oracle HCM row is asked through its requisition detail resource.** The page is a
client-rendered shell; the resource answers an unposted requisition with an empty `items`
(`oracle_unposted`), which strikes. 33 of 40 scanner-proven closures, 0 false deaths in 38 open.

**T89: on a registry ATS the URL half is worse than blind — it DISARMS the counter.** Probed
live 2026-09-17 against five postings a hand pre-flight had found dead: `jobs.ashbyhq.com`
answers **HTTP 200** with a 9,144-byte empty shell (live controls: 200, 42–78 KB) and
`job-boards.greenhouse.io` answers **302 → `<board>?error=true` → 200**. `verdict_for_status`
maps every 200 to `refetch_ok → alive`, and a redirect ending in 200 is `alive` too, so probing
a dead Ashby or Greenhouse row does not merely fail to strike it — it takes the `alive` branch
and **zeroes the strikes it had already earned**. Two providers holding 2,592 of the 13,101 open
rows in this class were therefore paying a probe each and getting their counter reset.

**The list endpoints are authoritative, and cost one GET per COMPANY.** Measured the same day,
read-only, over 30 unwatched ashby and 30 unwatched greenhouse companies: 59 of 60 answered 200
(one ashby board 404'd, which is `unknown` here), none answered an empty listing, and of the 246
open rows they held **31 were absent — 12.6%** (ashby 11/108, greenhouse 20/138). One GET
covered 4.1 postings on average, against one posting per GET for a URL probe whose answer is
wrong for both providers. So the listing half is both cheaper per row and the only half that can
fire at all on the two providers it covers.

Hence the split, and why it is a SPLIT rather than a second opinion: a row under `ashby`,
`greenhouse` or `lever` leaves the URL candidate set entirely. Exactly one signal feeds each
row's `death_strikes`, so narrowing 4 holds unchanged, with no second column and no migration.

**Cost.** A URL probe costs ~0.97 s and the class grows ~182/day, so an unbounded sweep would
exceed the run itself within a month. Hence a per-run budget and a TTL, both configurable, and
both sides of both budgets reported: a sweep that refuses work must read as refused work, never
as a clean corpus. The listing path gets its OWN budget because its unit is the company, and a
budget of 100 companies buys roughly 410 rows of coverage at today's density.

**T90: the budget goes to the rows the owner is looking at, first.** Run 433 logged `death
probe: 50 of 13101 due probed … 13051 refused by budget`. Under a plain
`last_death_probe_at ASC NULLS FIRST, id ASC` the sweep walks the oldest ids first, so a row a
lane delivered this week is reached in roughly **260 runs** — and of the 400 leads in the apply
lane that day, **393 had never been probed and 300 sat on unwatched companies**, with two of the
six genuine apply-lane misses in the owner's pre-flight being dead rows the sweep had never
reached. So both paths sort a row whose job carries a **standing lead** ahead of the rest of the
due set (on the listing path the unit is the COMPANY: any standing lead among its open rows
promotes the whole board's GET). The delivery queue drains `_closed` on its own (D-383), so
closing a held row is the one close the owner FEELS.

The priority **reorders the due set; it never widens it**, and that is what stops it becoming
"always the same 300 leads": a probed row leaves the due set for `ttl_hours`, so the next run's
budget flows to the rest of the class. The D-325 round-robin property therefore holds unchanged.
The sort key is SQL and the budget's `LIMIT` is applied **after** it — re-sorting a `LIMIT`ed
result would rank only the rows the limit had already admitted, and a lead one place past the
budget's edge would be cut before the priority ever saw it.

**And the listing path gets a per-row TTL, which the URL path always had.** A COMPANY is due
when ANY of its open rows is due, so the rows it holds are not all due. One row a lane added
today re-asks the board inside the TTL, and every other open row was then struck and stamped
again — an older row that struck an hour ago could take its second strike the same day: two
strikes in different runs, but not 24 h apart, which is weaker than the URL path enforces for
the same evidence. A row inside its own TTL is now neither struck nor stamped. A
`listing_present` still clears it, because a drain runs on both sides of its gate and
withholding a POSITIVE observation is the one direction this may never take.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote

from rich.console import Console
from sqlalchemy import (
    ColumnElement,
    Connection,
    Engine,
    and_,
    case,
    distinct,
    func,
    or_,
    select,
    union,
    update,
)

from boardwatch.core.clock import utcnow
from boardwatch.core.liveness import Liveness
from boardwatch.core.politeness import Fetcher, FetchFailure
from boardwatch.core.settings import Settings
from boardwatch.lanes.linkedin import LANE_PROVIDER as LINKEDIN_PROVIDER
from boardwatch.pipeline.liveness import LivenessProber
from boardwatch.pipeline.progress import StageProgress
from boardwatch.reports.run_funnel import DeathProbeReport
from boardwatch.scan.apply import CLOSE_AFTER_MISSES
from boardwatch.store.db import write_connection
from boardwatch.store.delivery_queries import standing_lead_job_ids
from boardwatch.store.events import append_event
from boardwatch.store.queries import open_as_filter
from boardwatch.store.tables import board_scans, companies, postings, runs

# The liveness signals permitted to strike a posting on the URL path, compared as catalog
# members rather than re-derived from a status code: `core/liveness.py` owns what "gone" means,
# including the redirect rule, and a second derivation here would let the two drift.
# `workday_unposted` is the CXS 403/S22 answer; a Workday 404 there is already `refetch_gone`.
# `oracle_unposted` is an Oracle HCM detail resource answering an empty `items` (D-648).
# `linkedin_closed` is LinkedIn's guest top card marked closed (D-653).
# `smartrecruiters_inactive`, `eightfold_unposted` and `adp_unposted` are the three D-684 added,
# each read from the provider's own resource for the EXACT posting; the close below is still by
# `postings.id` alone, so a sibling posting of the same job is never touched.
CLOSING_SIGNALS: frozenset[str] = frozenset(
    {
        "refetch_gone",
        "workday_unposted",
        "oracle_unposted",
        "linkedin_closed",
        "smartrecruiters_inactive",
        "eightfold_unposted",
        "adp_unposted",
    }
)

# T89. The closed catalog of providers whose whole board is readable in ONE request, with the
# JSON key the job array sits under (`None` = the payload IS the array). These are the bare
# MEMBERSHIP endpoints, deliberately not each provider's `board_url`: those carry
# `?includeCompensation=true` (ashby) and `?content=true&pay_transparency=true` (greenhouse),
# which fetch every JD body on the board — Ramp-scale ashby payloads reach 1.7 MB (D26) and a
# membership test needs none of it. The ids are compared and the payload is dropped; nothing
# here is persisted and no `BoardSnapshot` is built from it.
#
# Out-of-catalog is a FAILURE, not a new bucket (CLAUDE.md): `UnlistableProvider` below, raised
# at the lookup. Membership in this dict is also what removes a row from the URL candidate set,
# so adding a provider here without a working endpoint would silently strand its rows.
LISTING_ENDPOINTS: dict[str, tuple[str, str | None]] = {
    "ashby": ("https://api.ashbyhq.com/posting-api/job-board/{slug}", "jobs"),
    "greenhouse": ("https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", "jobs"),
    "lever": ("https://api.lever.co/v0/postings/{slug}?mode=json", None),
}

# The closed catalog of what a listing said about ONE posting, compared by name at the decision
# site so nothing downstream classifies a listing outcome by string-matching a message.
#
# **Deliberately NOT added to `core/liveness.py`'s `SIGNALS`.** That catalog is paired one-to-one
# with `SIGNAL_VERDICTS`, and every member of it is a judgement about what an HTTP status for
# ONE url MEANS — which is why `Liveness.__post_init__` can enforce the pair. A listing signal
# has no status of its own (one response answers every row on the board) and no `dead`/`alive`
# verdict to carry: it never withholds a lead, because `check_leads` cannot produce it. Putting
# it there would make `Liveness(1, "dead", "listing_absent")` constructible at the shortlist
# probe, where nothing can emit it — and that module's docstring already forbids exactly this:
# "a catalog entry nothing emits is a bucket that cannot be audited". So the owner is this
# module, which owns the mechanism that emits them.
LISTING_SIGNALS: tuple[str, ...] = ("listing_absent", "listing_present", "listing_unknown")

# Providers whose job-view page the URL probe cannot close, asked only after every other due row
# unless the run says it can (`linkedin_can_close`). LinkedIn: 0 of 7,106 open `linkedin` rows ever
# closed through the page as of 2026-09-26, because the page answers 200 for a closed job. The
# guest endpoint can close them (D-653), and the prober asks it only when the user enabled the
# LinkedIn lane; with the lane off the page probe is all there is, and the lead priority (T90)
# would spend the capped budget on rows that cannot close every run. Still probed when budget is
# left over -- the order moves, the set does not.
PROBED_LAST_PROVIDERS: frozenset[str] = frozenset({LINKEDIN_PROVIDER})


class UnlistableProvider(Exception):
    """A provider was routed to the listing path with no endpoint in the catalog.

    Typed, and raised at the lookup rather than recovered from a `KeyError` message: the two
    facts a caller needs are which provider and which catalog, and a bare mapping error carries
    only the first.
    """

    def __init__(self, provider: str) -> None:
        super().__init__(f"provider {provider!r} has no listing endpoint in LISTING_ENDPOINTS")
        self.provider = provider


@dataclass(frozen=True)
class Listing:
    """What one company's list endpoint said, reduced to the only thing this needs: the set of
    posting ids it published.

    `ids is None` is `unknown` — a non-200, a transport fault, or a body that would not parse.
    An EMPTY set is also unknown at the decision site (see `_listing_signal`), but it is kept
    distinct here rather than collapsed into `None`, because "the board answered, and answered
    nothing" is a different operational fact from "the board did not answer" and `detail` is
    the only place a human reading a traceback can tell them apart.

    Carries no payload and no timestamp on purpose: a payload invites somebody to persist it,
    and a persisted board listing is a snapshot, which this is explicitly not (D-329 — these
    companies stay unwatched).
    """

    company_id: int
    ids: frozenset[str] | None
    detail: str = ""


# One listing read for one company: (company_id, provider, slug) -> Listing. Injectable for the
# same two reasons the URL prober is: tests never touch the network, and the sweep does not have
# to know how a board is fetched.
ListingProber = Callable[[int, str, str], Listing]


def parse_listing(company_id: int, content: bytes, *, root: str | None) -> Listing:
    """The ids a list payload published, or `unknown` if it did not parse.

    Ids are stringified exactly as every provider's `parse_job` stringifies them
    (`str(job["id"])`), because the comparison downstream is against
    `postings.provider_posting_id`, which is what that call wrote. An id-less row is skipped
    rather than counted, mirroring `providers/base.py::count_listed_ids`: a row we cannot key
    is a row we could never have stored, so it can neither confirm nor deny anything.
    """
    try:
        payload = json.loads(content)
        rows = payload[root] if root is not None else payload
        if not isinstance(rows, list):
            raise TypeError(f"{root or 'payload'} is not a list")
    except (ValueError, KeyError, TypeError) as exc:
        return Listing(company_id, None, f"invalid listing payload: {exc}")
    ids = frozenset(
        str(row["id"])
        for row in rows
        if isinstance(row, dict) and row.get("id") is not None
    )
    return Listing(company_id, ids, "empty listing" if not ids else f"{len(ids)} listed")


def build_listing_prober(settings: Settings) -> ListingProber:
    """The production listing prober: one GET of a board's list endpoint through the politeness
    `Fetcher`.

    The same construction `build_prober` uses, for the same reasons — `retry_attempts=1`,
    because an unknown answer is already the safe one and a retry only spends the operator's
    morning; and the `Fetcher` rather than a bare `httpx` call, because that is what carries the
    identifying user agent and the per-host serial pacing. Pacing matters MORE here than on the
    URL path: these three providers each serve their whole fleet from one host, and the board
    scan hits the same hosts earlier in the same run. `HostPacing` is process-shared (D-475), so
    a second `Fetcher` instance still queues behind the scan's on that host rather than beside
    it.
    """
    fetcher = Fetcher(settings.model_copy(update={"retry_attempts": 1}))

    def probe(company_id: int, provider: str, slug: str) -> Listing:
        try:
            template, root = LISTING_ENDPOINTS[provider]
        except KeyError:
            raise UnlistableProvider(provider) from None
        # The slug reaches this from the store, where a lane wrote it; percent-encoding it keeps
        # a slug carrying a slash from silently addressing a different board's listing.
        url = template.format(slug=quote(slug, safe=""))
        try:
            result = fetcher.get(url)
        except FetchFailure as exc:
            # Every non-200 is `unknown`, a board-level 404 included. That is the same fail-open
            # direction narrowing 1 takes on the URL path and it is deliberately conservative
            # here too: a 404 from a list endpoint is evidence about the BOARD, and treating it
            # as evidence about each posting would retire a whole employer on one bad answer.
            return Listing(company_id, None, str(exc))
        except Exception as exc:  # noqa: BLE001 - any transport fault is `unknown`, never gone
            return Listing(company_id, None, f"{type(exc).__name__}: {exc}")
        return parse_listing(company_id, result.content, root=root)

    return probe


def unreachable_by_the_scanner() -> ColumnElement[bool]:
    """Open postings under a company nothing enumerates — the D-314 defect predicate.

    `watched = 0` rather than `companies.source = 'lane'`: the defect is that no board scan
    covers the company, and 274 unwatched `source='user'` companies have it too. Naming the lane
    would have fixed the symptom for one acquirer and left the identical rows untouched under
    another.

    The `IN` restates the join on purpose. Without it SQLite walks every open posting's row to find
    the 5% under an unwatched company (~100 s, three times a sweep); with it, it seeks them.
    """
    unwatched = companies.alias("unwatched")
    return and_(
        postings.c.status == "open",
        companies.c.watched.is_(False),
        postings.c.company_id.in_(select(unwatched.c.id).where(unwatched.c.watched.is_(False))),
    )


@dataclass(frozen=True)
class GuardedBoard:
    """A watched board on its `GUARD_DRAIN_NIGHTS`th consecutive guarded pipeline night."""

    company_id: int
    provider: str


def guarded_for_the_drain(conn: Connection, run_id: int) -> list[GuardedBoard]:
    """Watched boards whose latest pipeline scans, back to a break, were ALL refused by the guard
    on at least `GUARD_DRAIN_NIGHTS` distinct days, the newest of them this run's (T334, D-705).

    Read from the typed `board_scans.empty_guarded`, never from `postings_listed = 0`: that
    proxy matches 1,224 boards against the 73 the guard fired on. The filter is D-669's
    (`scan/board_moves.dead_for_three_scans`) and for its reason: `pipeline_scan` rows only, so
    a lane row or a standalone `boardwatch scan` neither counts nor interrupts a streak.

    A break is anything that is not a guarded scan: a relist, a `failed` or `unchanged` or
    `partial` night, an ordinary `complete` one, and a row written before the column existed
    (NULL). A failed night is a break on purpose, as it is for a dead board: it observed nothing,
    so the streak must be made of consecutive observations of an empty board, and the cost of
    the rule is a delay, never a close.

    Requiring the newest row to be THIS run's means a board the run did not scan (a `--project`
    pass, `--no-scan`) hands nothing over: the evidence is that the board answered empty tonight.
    """
    history = (
        select(
            board_scans.c.company_id,
            board_scans.c.run_id,
            board_scans.c.started_at,
            # Newest first; the running count of non-guarded rows is 0 exactly on the leading
            # guarded streak. A NULL flag is a break: `IS 1` is false for it.
            func.sum(case((board_scans.c.empty_guarded.is_(True), 0), else_=1))
            .over(partition_by=board_scans.c.company_id, order_by=board_scans.c.id.desc())
            .label("breaks"),
        )
        .where(
            board_scans.c.scan_kind == "board",
            board_scans.c.pipeline_scan.is_(True),
            board_scans.c.run_id <= run_id,
        )
        .subquery()
    )
    streaking = (
        select(history.c.company_id)
        .where(history.c.breaks == 0)
        .group_by(history.c.company_id)
        .having(
            func.count(distinct(func.date(history.c.started_at))) >= GUARD_DRAIN_NIGHTS,
            func.max(history.c.run_id) == run_id,
        )
    )
    rows = conn.execute(
        select(companies.c.id, companies.c.provider)
        .where(companies.c.id.in_(streaking), companies.c.watched.is_(True))
        .order_by(companies.c.id)
    )
    return [GuardedBoard(int(r.id), str(r.provider)) for r in rows]


def _listing_signal(listing: Listing, provider_posting_id: str) -> str:
    """Which `LISTING_SIGNALS` member this row's id earned from its company's listing.

    An empty listing is `unknown`, not 'every row absent'. This mirrors
    `scan/apply.py::_empty_complete_is_evidence_of_nothing` exactly: the sweep only ever asks
    about companies that HOLD open rows, so a board publishing nothing is a board whose answer
    is broken, not a board that emptied. Collapsing that into `absent` would close entire
    employers on one bad deploy at the provider — and on the listing path there is no board
    enumeration to correct it afterwards, which is the same argument that rejected a single
    strike.
    """
    if not listing.ids:
        return "listing_unknown"
    return "listing_present" if provider_posting_id in listing.ids else "listing_absent"


def _past_ttl(cutoff: datetime) -> ColumnElement[bool]:
    """One row's own TTL: never asked, or last asked before the cutoff.

    Factored out because the listing path has to evaluate it a SECOND time, per row, inside the
    company it already decided to ask about — and the two must be the same predicate against the
    same cutoff or a row could be admitted by one and struck by the other.
    """
    return or_(
        postings.c.last_death_probe_at.is_(None),
        postings.c.last_death_probe_at < cutoff,
    )


# T284 (D-696): `budget // 5` of the URL budget goes to never-asked rows no standing lead holds.
NEVER_ASKED_RESERVE_DIVISOR = 5

# T334 (D-705). A watched board is handed to the URL probe after this many CONSECUTIVE nights on
# which the empty-complete guard refused its scan (`board_scans.empty_guarded`). Distinct
# calendar days, not scans: a manual run on the same day is the same night. Measured on four
# providers over 80 days, 7 of 42 empty runs that later relisted did so after 15 days or more
# (longest 49), so the line is a delay before asking, and nothing closes on the count: the close
# still needs two strikes of the posting's own URL. A named constant, not a Settings field.
GUARD_DRAIN_NIGHTS = 14

# T334 (D-705): up to `budget // 10` of the URL budget goes to the handed-over rows no standing
# lead holds, ordered least-recently-probed first. A held row rides the main order, which already
# puts it first. Taken from the main order only when such rows exist, so with none the budget
# splits exactly as T284 left it (a fifth never-asked, four fifths main).
GUARD_DRAIN_RESERVE_DIVISOR = 10

# T89: providers whose own dead-posting URL answers ALIVE (Ashby 200 with an empty shell,
# Greenhouse 302 to `<board>?error=true` then 200), so a URL probe can never strike their rows
# and an `alive` answer would only spend a probe. A guarded board on one of them is counted and
# reported, never asked: its listing is empty, which the listing half reads as `listing_unknown`.
# Lever is deliberately absent. Its dead URL answers 404 (the liveness probe found a genuinely
# dead open Lever posting by URL, METRICS P6 item 6), and a guarded Lever board is exactly the
# case the listing half cannot answer.
URL_PROBE_BLIND_PROVIDERS: frozenset[str] = frozenset({"ashby", "greenhouse"})


def _due_predicate(cutoff: datetime) -> ColumnElement[bool]:
    return and_(unreachable_by_the_scanner(), _past_ttl(cutoff))


def sweep_unwatched_deaths(
    engine: Engine,
    *,
    prober: LivenessProber,
    listing_prober: ListingProber | None,
    run_id: int,
    budget: int,
    company_budget: int,
    ttl_hours: int,
    linkedin_can_close: bool = False,
    priority_ids: frozenset[int] = frozenset(),
    console: Console | None = None,
) -> DeathProbeReport:
    """Probe the unreachable-by-the-scanner class two ways and close the proven-dead postings.

    Writes, unlike `pipeline/liveness.py::check_leads` — that one probes the SHORTLIST and its
    "reads URLs; writes nothing, ever" contract is what stops a flaky CDN retiring a live lead.
    This is a different question over a different population, and that difference is the whole
    of D-325.

    The class is partitioned by `companies.provider`: rows under `LISTING_ENDPOINTS` are asked
    about through their company's list endpoint, everything else through its own URL. `budget`
    counts postings and bounds the URL half; `company_budget` counts COMPANIES and bounds the
    listing half, because one GET there answers every open row a company holds.

    `listing_prober=None` leaves the listing half unasked and reports its whole due set as
    `companies_refused`, the same direction `budget=0` takes on the URL path: a half that did
    not run must read as refused work, never as a clean corpus.

    Both budgets go to the rows carrying a STANDING LEAD first (T90). The priority reorders the
    due set and never widens it, so it cannot become "always the same leads": a probed row leaves
    the due set for `ttl_hours`, and the next run's budget flows to the rest of the class.
    That holds only while the held rows are fewer than the budget, so a fifth of the URL budget
    is reserved for never-asked rows no lead holds (T284, D-696).

    T334 (D-705) adds a second URL population: the open postings of WATCHED boards the guard has
    refused for `GUARD_DRAIN_NIGHTS` consecutive pipeline nights (`guarded_for_the_drain`),
    except on a provider in `URL_PROBE_BLIND_PROVIDERS`, whose rows are counted and left open.
    They share the URL budget and the same two-strike rule; `due`, `attempted`, `gone`,
    `closed_by_url` and the rest keep covering the whole URL path, and the `guard_*` fields are
    the part of them that came from this population. Up to `budget // 10` is reserved for them
    (those no standing lead holds, least-recently-probed first), so the leads and the never-asked
    reserve cannot starve the drain and it cannot starve either of them: with none handed over
    the split is T284's, and with some the leads' share is `budget - budget // 5 - budget // 10`.

    `priority_ids` (D-691) is a second, prior reordering inside the same budget: a layer wrapper
    whose only employer twin is closed is asked about before the rest of the due set. It is a
    suspicion, not a close — the probe's own answer decides — and the due set is untouched, so a
    priority row that comes back alive leaves for `ttl_hours` like any other.

    `linkedin_can_close` says whether `prober` asks a LinkedIn job-view URL through the guest
    endpoint (D-653). Without it those rows go last (`PROBED_LAST_PROVIDERS`).
    """
    now = utcnow()
    cutoff = now - timedelta(hours=ttl_hours)
    due_predicate = _due_predicate(cutoff)
    has_url = and_(postings.c.url.is_not(None), postings.c.url != "")
    # Rows fed by the listing signal are REMOVED from the URL candidate set rather than probed
    # twice. Two signals into one `death_strikes` column would make a close unattributable —
    # the defect narrowing 4 exists to prevent — and on these two providers the URL answer is
    # not merely weaker but actively wrong: a dead Ashby row answers 200 and would RESET the
    # strike the listing had just earned.
    on_url_path = companies.c.provider.notin_(tuple(LISTING_ENDPOINTS))
    on_listing_path = companies.c.provider.in_(tuple(LISTING_ENDPOINTS))
    board = postings.join(companies, companies.c.id == postings.c.company_id)
    # T334. The watched boards handed over tonight, read before any candidate query because the
    # URL population is defined by them. A bound `IN` is not the corpus-scaled one D-287 forbids:
    # it is bounded by the boards the guard fired on, ~73 today.
    with engine.connect() as probe_conn:
        guarded = guarded_for_the_drain(probe_conn, run_id)
    guarded_ids = [g.company_id for g in guarded]
    judgeable_ids = [g.company_id for g in guarded if g.provider not in URL_PROBE_BLIND_PROVIDERS]
    # ONE company-id set, never an `OR` of two joined predicates: the OR plans as
    # `ix_postings_status_posted_at (status=?)`, the walk of every open posting that
    # `unreachable_by_the_scanner` exists to avoid, while an `IN` over this union keeps
    # `ix_postings_corpus (status=? AND company_id=?)`. The first arm is that predicate's own
    # company set; the second is the handed-over boards, which are watched.
    url_companies = union(
        select(companies.c.id).where(companies.c.watched.is_(False), on_url_path),
        select(companies.c.id).where(companies.c.id.in_(judgeable_ids)),
    )
    url_due = and_(
        postings.c.status == "open",
        postings.c.company_id.in_(url_companies),
        _past_ttl(cutoff),
    )
    # A candidate row of a WATCHED company is, by construction of `url_companies`, a handed-over
    # one. Selected with each row so the loop can attribute without a second query.
    guard_row = companies.c.watched.is_(True)
    # Some open row of this company has never been asked. `func.min` cannot express it —
    # SQL `min()` SKIPS nulls, so a company with one never-probed row and one probed yesterday
    # would sort by yesterday and lose its place at the head of the queue.
    never_asked = func.count() > func.count(postings.c.last_death_probe_at)
    oldest_probe = func.min(postings.c.last_death_probe_at)

    with engine.connect() as conn:
        # T90. Which rows the owner is actually looking at. Read ONCE per sweep, from the queue's
        # own reader — `delivered_unapplied` — so the sweep cannot disagree with the queue page
        # about which leads are standing. `delivered_unapplied` is keyed by canonical `job_id`
        # and this sweep is keyed by `posting_id`, so the sort key joins through `postings.job_id`
        # rather than comparing ids that mean different things. Bounded by the DELIVERED corpus
        # (670 leads measured 2026-09-14), not by the 13,101-row open class, so binding it is not
        # the corpus-scaled `IN (...)` D-287 forbids.
        standing = standing_lead_job_ids(conn)
        # ONE membership test, read by both paths' sort keys. A posting whose job has a standing
        # lead is the one whose death the owner FEELS: the delivery queue drains `_closed` on its
        # own (D-383), so closing it removes a dead row from the apply lane, while closing an
        # unheld row only tidies the store.
        has_a_standing_lead = postings.c.job_id.in_(standing)
        held_by_a_standing_lead = case((has_a_standing_lead, 0), else_=1)  # 0 sorts first
        # Only while the URL is still the LinkedIn page the measurement was about: a row resolved
        # to an employer URL (a Workday one the CXS probe can close) keeps its priority.
        linkedin_job_view = and_(
            companies.c.provider.in_(tuple(PROBED_LAST_PROVIDERS)),
            postings.c.url.like("%linkedin.com/%"),
        )
        probed_last = case((linkedin_job_view, 1), else_=0)
        # Ahead of the standing-lead key: a row that cannot close is not worth a probe before one
        # that can, whoever holds it.
        url_order: list[ColumnElement[Any]] = [
            held_by_a_standing_lead.asc(),
            postings.c.last_death_probe_at.asc(),
            postings.c.id.asc(),
        ]
        if not linkedin_can_close:
            url_order.insert(0, probed_last.asc())
        if priority_ids:
            # ALL of them, not the first `budget` by id: slicing before the order would drop a row
            # that is due now in favour of a smaller id that is not, and the rows past the budget
            # are ranked by the ordinary keys below rather than by id. The caller's set is bounded
            # by the standing queue (delivery-sized), so this `IN` stays small.
            # AFTER `probed_last`: when the LinkedIn guest check is off, those rows cannot close,
            # and the existing invariant is that a row which cannot close never takes a budget slot
            # from one that can. The priority reorders within that population.
            url_order.insert(
                0 if linkedin_can_close else 1,
                case((postings.c.id.in_(sorted(priority_ids)), 0), else_=1),
            )
        company_holds_a_standing_lead = func.max(case((has_a_standing_lead, 1), else_=0))
        # One pass for both URL denominators. `unprobeable` is a row this mechanism can never
        # reach by any future refinement — `postings.url` is nullable — so it is reported rather
        # than filtered away, which would hide a permanently stuck slice inside a sweep claiming
        # to be complete.
        counts = conn.execute(
            select(
                func.coalesce(func.sum(case((has_url, 1), else_=0)), 0).label("due"),
                func.coalesce(func.sum(case((has_url, 0), else_=1)), 0).label("unprobeable"),
            )
            .select_from(board)
            .where(url_due)
        ).one()
        # Standing leads first, then least-recently-probed, NULL (never asked) ahead of
        # everything. Ordering by `id` alone would probe the same head every run for ever and
        # never reach the tail, while `attempted` reported a busy sweep — that property (D-325)
        # is preserved, because the priority only reorders the DUE set and a probed row leaves it
        # for `ttl_hours`. So the priority can never become "always the same leads": next run's
        # budget flows to the rest of the class.
        #
        # The sort key is SQL, and the `LIMIT` is applied AFTER it, deliberately. Re-sorting a
        # `LIMIT`ed result in Python would rank only the rows the limit had already admitted, and
        # a lead past the budget's edge would be cut before the priority ever saw it. `LIMIT` IS
        # the budget, so this is still bounded by construction.
        #
        # T284 (D-696): a fifth of the budget is held for rows NEVER asked that no standing lead
        # holds. Without it the lead priority spent ~80% of the probes on 2,215 held rows while
        # 48,665 never-asked rows waited behind them. A held row is left out of the reserve, not
        # because it matters less, but because the main order already puts it first. A LinkedIn
        # job-view row is left out while the guest check is off: it cannot close, so a reserved
        # slot spent on it is a slot the tail never gets. `budget` stays the total.
        reserve_where = [
            due_predicate,
            has_url,
            on_url_path,
            postings.c.last_death_probe_at.is_(None),
            ~has_a_standing_lead,
        ]
        if not linkedin_can_close:
            reserve_where.append(~linkedin_job_view)
        row_columns = (
            postings.c.id,
            postings.c.url,
            postings.c.death_strikes,
            guard_row.label("guarded"),
        )
        reserved = conn.execute(
            select(*row_columns)
            .select_from(board)
            .where(and_(*reserve_where))
            .order_by(postings.c.id.asc())
            .limit(budget // NEVER_ASKED_RESERVE_DIVISOR)
        ).all()
        # T334 (D-705): the handed-over rows no standing lead holds, round-robin by last ask.
        # `company_id IN` the judgeable boards restates what `url_due` and `guard_row` already
        # say; it gives the planner a direct company seek instead of the union.
        guard_reserved = conn.execute(
            select(*row_columns)
            .select_from(board)
            .where(
                and_(
                    url_due,
                    guard_row,
                    has_url,
                    postings.c.company_id.in_(judgeable_ids),
                    ~has_a_standing_lead,
                )
            )
            .order_by(postings.c.last_death_probe_at.asc(), postings.c.id.asc())
            .limit(budget // GUARD_DRAIN_RESERVE_DIVISOR)
        ).all()
        ordered = conn.execute(
            select(*row_columns)
            .select_from(board)
            .where(
                and_(
                    url_due,
                    has_url,
                    postings.c.id.notin_([row.id for row in (*reserved, *guard_reserved)]),
                )
            )
            .order_by(*url_order)
            .limit(budget - len(reserved) - len(guard_reserved))
        ).all()
        candidates = [*ordered, *reserved, *guard_reserved]
        # What the drain did NOT hand to the URL probe, and what it did: one pass over the open
        # rows of the boards past the threshold. The blind providers' rows are counted here and
        # nowhere else, because they never become candidates.
        if guarded_ids:
            guard_open = conn.execute(
                select(
                    func.count().label("open_rows"),
                    func.coalesce(
                        func.sum(
                            case(
                                (companies.c.provider.in_(tuple(URL_PROBE_BLIND_PROVIDERS)), 1),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("blind"),
                )
                .select_from(board)
                .where(postings.c.status == "open", postings.c.company_id.in_(guarded_ids))
            ).one()
            guard_rows = int(guard_open.open_rows) - int(guard_open.blind)
            guard_rows_unjudgeable = int(guard_open.blind)
        else:
            guard_rows = guard_rows_unjudgeable = 0
        # The listing half's queue, one row per COMPANY. A company is due when any of its open
        # rows is: a posting a lane added since the last ask has never been answered about, and
        # the listing that answers it answers the whole board anyway.
        due_companies = conn.execute(
            select(
                companies.c.id,
                companies.c.provider,
                companies.c.slug,
            )
            .select_from(board)
            .where(and_(unreachable_by_the_scanner(), on_listing_path))
            .group_by(companies.c.id)
            .having(or_(never_asked, oldest_probe < cutoff))
            # The unit here is the COMPANY, so the priority is too: a company holding ANY
            # standing lead among its open rows sorts first, because one GET answers all of
            # them. `max` over the per-row key rather than a second query — the rows are already
            # grouped by company here.
            .order_by(
                company_holds_a_standing_lead.desc(),
                never_asked.desc(),
                oldest_probe.asc(),
                companies.c.id.asc(),
            )
        ).all()

    asked_companies = due_companies[:company_budget] if listing_prober is not None else []
    url_progress = StageProgress("death probe URLs", len(candidates), console=console)

    gone = unknown = alive = closed_by_url = strikes_cleared = 0
    guard_attempted = guard_closed = 0
    linkedin_guest: dict[str, int] | None = None
    for row in candidates:
        guard_attempted += 1 if row.guarded else 0
        result = prober(int(row.id), str(row.url))
        if result.linkedin_guest is not None:
            if linkedin_guest is None:
                linkedin_guest = dict.fromkeys(
                    ("attempted", "http_200", "http_404", "other_non_200", "no_response"), 0
                )
            status = result.linkedin_guest.status_code
            if status is None:
                bucket = "no_response"
            elif status in (200, 404):
                bucket = f"http_{status}"
            else:
                bucket = "other_non_200"
            linkedin_guest["attempted"] += 1
            linkedin_guest[bucket] += 1
        strikes = int(row.death_strikes)
        if result.signal in CLOSING_SIGNALS:
            gone += 1
            strikes += 1
        elif result.verdict == "alive":
            alive += 1
            # The drain. A strike is a suspicion, not a sentence.
            strikes_cleared += 1 if strikes else 0
            strikes = 0
        else:
            # Every remaining outcome, `refetch_gone_after_redirect` included. Counted, never
            # silently absorbed: that bucket is the one that can disarm this check with no other
            # number moving, exactly as it can for the shortlist probe (D-113).
            unknown += 1

        values: dict[str, object] = {
            "death_strikes": strikes,
            # Written on EVERY outcome, so one permanently-unreachable host cannot consume the
            # whole budget each run and starve the rest of the class — a failure indistinguishable
            # from a healthy sweep if only `attempted` is read.
            "last_death_probe_at": now,
        }
        closing = strikes >= CLOSE_AFTER_MISSES
        if closing:
            values["status"] = "closed"
            values["closed_at"] = now
            closed_by_url += 1
            guard_closed += 1 if row.guarded else 0
        # One transaction per posting, mirroring `apply_board`'s per-board atomicity: the row
        # update and its event commit or vanish together, and a probe that raises mid-sweep
        # leaves every earlier decision durable instead of rolling the whole sweep back.
        with engine.begin() as write:
            write.execute(update(postings).where(postings.c.id == row.id).values(**values))
            if closing:
                append_event(write, int(row.id), "closed", run_id)
        url_progress.advance(item=str(row.id))

    url_progress.finish()
    listing_absent = listing_present = listing_unknown = closed_by_listing = 0
    if listing_prober is not None:
        listing_progress = StageProgress(
            "death probe listings", len(asked_companies), console=console
        )
        for company in asked_companies:
            listing = listing_prober(
                int(company.id), str(company.provider), str(company.slug)
            )
            # One transaction per COMPANY — the unit that was actually asked about, mirroring
            # `apply_board`'s per-board atomicity. The open rows are re-read inside it so the
            # membership test runs against the same snapshot the writes land on.
            # T134: the re-read below and the writes that follow it are one read-then-write,
            # so IMMEDIATE at BEGIN — a DEFERRED snapshot taken at that SELECT cannot be
            # upgraded once any other writer commits.
            with write_connection(engine) as write, write.begin():
                open_rows = write.execute(
                    select(
                        postings.c.id,
                        postings.c.provider_posting_id,
                        postings.c.death_strikes,
                        # T90. The company is due when ANY of its open rows is, so the rows it
                        # holds are not all due: one row a lane added today re-asks the board
                        # inside the TTL, and every OTHER open row would then be struck and
                        # stamped again. An older row that struck an hour ago could take its
                        # second strike the same day — two strikes in different runs, but not
                        # 24 h apart, which is weaker than the URL path enforces for the same
                        # evidence. Evaluated by `_past_ttl`, the same predicate and the same
                        # cutoff that admitted the company, so the two cannot drift.
                        _past_ttl(cutoff).label("past_ttl"),
                    ).where(
                        postings.c.company_id == company.id,
                        # The index choice `scan/apply._process_missing` explains.
                        open_as_filter(),
                    )
                ).all()
                for row in open_rows:
                    signal = _listing_signal(listing, str(row.provider_posting_id))
                    strikes = int(row.death_strikes)
                    past_ttl = bool(row.past_ttl)
                    if signal == "listing_absent":
                        # Counted whatever the row's own TTL says: the board DID answer about it
                        # and did not list it. The per-row guard withholds the STRIKE, not the
                        # observation, and there is no report field that could carry a
                        # third state without going unread.
                        listing_absent += 1
                        if past_ttl:
                            strikes += 1
                    elif signal == "listing_present":
                        listing_present += 1
                        # The drain, and the stronger half of it: a board that LISTS the posting
                        # is the same positive evidence `_apply_listed` acts on. Allowed inside
                        # the per-row TTL as well — every quarantine's drain runs on both sides
                        # of its gate, and withholding a POSITIVE observation is the one
                        # direction this mechanism may never take.
                        strikes_cleared += 1 if strikes else 0
                        strikes = 0
                    else:
                        # Neither increments nor resets, exactly as an `unknown` URL probe does
                        # not.
                        listing_unknown += 1

                    values = {"death_strikes": strikes}
                    if past_ttl:
                        # Stamped on every outcome, including `unknown`, so a board that is
                        # permanently broken spends its TTL instead of consuming the company
                        # budget every run and starving the rest of the class. NOT stamped for a
                        # row inside its own TTL: re-stamping would slide that row's next
                        # legitimate ask a further TTL into the future on every sweep its
                        # company was asked about for some other row's sake.
                        values["last_death_probe_at"] = now
                    closing = strikes >= CLOSE_AFTER_MISSES
                    if closing:
                        values["status"] = "closed"
                        values["closed_at"] = now
                        closed_by_listing += 1
                    write.execute(
                        update(postings).where(postings.c.id == row.id).values(**values)
                    )
                    if closing:
                        append_event(write, int(row.id), "closed", run_id)
            listing_progress.advance(item=str(company.slug))

        listing_progress.finish()
    return DeathProbeReport(
        due=int(counts.due),
        unprobeable=int(counts.unprobeable),
        attempted=len(candidates),
        budget_refused=int(counts.due) - len(candidates),
        gone=gone,
        unknown=unknown,
        alive=alive,
        closed_by_url=closed_by_url,
        closed_by_listing=closed_by_listing,
        strikes_cleared=strikes_cleared,
        companies_due=len(due_companies),
        companies_attempted=len(asked_companies),
        companies_refused=len(due_companies) - len(asked_companies),
        listing_absent=listing_absent,
        listing_present=listing_present,
        listing_unknown=listing_unknown,
        linkedin_guest=linkedin_guest,
        guard_boards=len(guarded_ids),
        guard_rows=guard_rows,
        guard_rows_unjudgeable=guard_rows_unjudgeable,
        guard_attempted=guard_attempted,
        guard_closed=guard_closed,
    )


@dataclass(frozen=True)
class ShortlistStrikes:
    """What this run's shortlist probe did to `death_strikes` (D-665)."""

    struck: int
    closed: int
    cleared: int


def strike_from_shortlist(
    engine: Engine,
    results: Mapping[int, Liveness],
    *,
    run_id: int,
    ttl_hours: int,
) -> ShortlistStrikes:
    """Count the shortlist probe's answers toward the same close the sweep earns (D-665).

    A dead posting ranks high every day, so the shortlist asks about it every day, while the sweep
    reaches 300 of about 42,000 due rows a run and most of these were last asked in September: 48
    of run 751's 50 withheld postings were withheld again on 758, each holding a `gate.depth` slot.
    The answer was thrown away. `check_leads` still writes nothing; this is the one place that
    reads its results.

    The evidence and every narrowing are the sweep's own: only `CLOSING_SIGNALS`, only
    `watched = 0`, only the URL path (a listing-path row's URL answer is wrong, T89, and would
    clear the strikes its listing earned), two strikes `ttl_hours` apart and in different runs. A
    row the sweep stamped during this run is refused whatever the TTL says: a slow sweep can outlast
    a short TTL. A positive answer clears on both sides of the TTL, as a present listing does.
    `unknown` neither strikes nor stamps, so it cannot use up the sweep's turn at the row.
    """
    now = utcnow()
    cutoff = now - timedelta(hours=ttl_hours)
    struck = closed = cleared = 0
    # T134: a read-then-write, so IMMEDIATE at BEGIN.
    with write_connection(engine) as write, write.begin():
        run_started_at = write.execute(
            select(runs.c.started_at).where(runs.c.id == run_id)
        ).scalar_one()
        rows = write.execute(
            select(
                postings.c.id,
                postings.c.death_strikes,
                postings.c.last_death_probe_at,
                _past_ttl(cutoff).label("past_ttl"),
            )
            .join_from(postings, companies, companies.c.id == postings.c.company_id)
            .where(
                postings.c.id.in_(list(results)),
                postings.c.status == "open",
                companies.c.watched.is_(False),
                companies.c.provider.notin_(tuple(LISTING_ENDPOINTS)),
            )
        ).all()
        for row in rows:
            result = results[int(row.id)]
            strikes = int(row.death_strikes)
            if result.signal in CLOSING_SIGNALS:
                stamped = row.last_death_probe_at
                if not row.past_ttl or (stamped is not None and stamped >= run_started_at):
                    continue
                struck += 1
                strikes += 1
                values: dict[str, object] = {"death_strikes": strikes, "last_death_probe_at": now}
                if strikes >= CLOSE_AFTER_MISSES:
                    values.update(status="closed", closed_at=now)
                    closed += 1
                    append_event(write, int(row.id), "closed", run_id)
            elif result.verdict == "alive":
                cleared += 1 if strikes else 0
                values = {"death_strikes": 0}
                if row.past_ttl:
                    values["last_death_probe_at"] = now
            else:
                continue
            write.execute(update(postings).where(postings.c.id == row.id).values(**values))
    return ShortlistStrikes(struck=struck, closed=closed, cleared=cleared)


__all__ = [
    "ShortlistStrikes",
    "strike_from_shortlist",
    "CLOSING_SIGNALS",
    "GUARD_DRAIN_NIGHTS",
    "GUARD_DRAIN_RESERVE_DIVISOR",
    "GuardedBoard",
    "LISTING_ENDPOINTS",
    "LISTING_SIGNALS",
    "Listing",
    "ListingProber",
    "URL_PROBE_BLIND_PROVIDERS",
    "UnlistableProvider",
    "build_listing_prober",
    "guarded_for_the_drain",
    "parse_listing",
    "sweep_unwatched_deaths",
    "unreachable_by_the_scanner",
]
