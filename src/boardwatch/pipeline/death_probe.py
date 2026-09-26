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
2. **Only `companies.watched = 0`.** Exactly the rows for which the scanner cannot produce a
   signal. A watched board enumerates itself and closes its own postings correctly; adding a
   second, weaker path over it would be a regression, not a fix. The predicate is the honest
   one — it covers unwatched `source='user'` companies too, which have the identical defect.
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
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import quote

from sqlalchemy import ColumnElement, Engine, and_, case, func, or_, select, update

from boardwatch.core.clock import utcnow
from boardwatch.core.politeness import Fetcher, FetchFailure
from boardwatch.core.settings import Settings
from boardwatch.pipeline.liveness import LivenessProber
from boardwatch.reports.run_funnel import DeathProbeReport
from boardwatch.scan.apply import CLOSE_AFTER_MISSES
from boardwatch.store.db import write_connection
from boardwatch.store.delivery_queries import standing_lead_job_ids
from boardwatch.store.events import append_event
from boardwatch.store.tables import companies, postings

# The ONE liveness signal permitted to close a posting on the URL path, compared as a catalog
# member rather than re-derived from a status code: `core/liveness.py` owns what "gone" means,
# including the redirect rule, and a second derivation here would let the two drift.
CLOSING_SIGNAL = "refetch_gone"

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
    """
    return and_(postings.c.status == "open", companies.c.watched.is_(False))


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
            .where(and_(due_predicate, on_url_path))
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
        candidates = conn.execute(
            select(postings.c.id, postings.c.url, postings.c.death_strikes)
            .select_from(board)
            .where(and_(due_predicate, has_url, on_url_path))
            .order_by(
                held_by_a_standing_lead.asc(),
                postings.c.last_death_probe_at.asc(),
                postings.c.id.asc(),
            )
            .limit(budget)
        ).all()
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

    gone = unknown = alive = closed_by_url = strikes_cleared = 0
    for row in candidates:
        result = prober(int(row.id), str(row.url))
        strikes = int(row.death_strikes)
        if result.signal == CLOSING_SIGNAL:
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
        # One transaction per posting, mirroring `apply_board`'s per-board atomicity: the row
        # update and its event commit or vanish together, and a probe that raises mid-sweep
        # leaves every earlier decision durable instead of rolling the whole sweep back.
        with engine.begin() as write:
            write.execute(update(postings).where(postings.c.id == row.id).values(**values))
            if closing:
                append_event(write, int(row.id), "closed", run_id)

    listing_absent = listing_present = listing_unknown = closed_by_listing = 0
    if listing_prober is not None:
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
                        # The planner hint `scan/apply._process_missing` explains.
                        func.likely(postings.c.status == "open"),
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
    )


__all__ = [
    "CLOSING_SIGNAL",
    "LISTING_ENDPOINTS",
    "LISTING_SIGNALS",
    "Listing",
    "ListingProber",
    "UnlistableProvider",
    "build_listing_prober",
    "parse_listing",
    "sweep_unwatched_deaths",
    "unreachable_by_the_scanner",
]
