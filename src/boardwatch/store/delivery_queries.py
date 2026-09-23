"""Read-only queries behind the delivery queue (design §6.1-§6.4). Every function is a select.

**This module never writes.** No INSERT, UPDATE or DELETE, and no call that performs one — which
rules out `rank_open_postings` and `run_eligibility`, both of which mint a `runs` row on the way to
an answer (design §6.3). A web request must not create a phantom run on every page load.

Four shapes of honesty are load-bearing here, and each of them is a field that could have been
faked with a default instead:

- **`posted_days` is `None`, never 0, when the board publishes no date.** It derives from the
  nullable `postings.posted_at` exactly as `rank/explain.why_summary` does; `first_seen_at` is a
  different quantity (when *we* first saw it, not when the employer posted it) and is returned
  beside it rather than substituted for it.
- **`jd_body` is `None`, never `""`, when the posting has no current version or its current
  version is quarantined.** An empty body and an absent body are different claims, and
  `jd_absent_reason` distinguishes the two absent cases. The two existing callers disagree —
  `eligibility/audit.py` tolerates the case, `projection/posting.py` raises — and this module
  tolerates it, because a detail request that raises would take a whole page down over one missing
  row.
- **`verdict` is `None` when nothing was evaluated.** It comes from
  `eligibility/read.current_verdicts`, the existing identity-scoped read, so a corrected fact or
  policy is reflected the moment its re-evaluation lands. No default is invented for the
  unevaluated case.
- **`status` is `unverifiable`, not `open`, when nothing enumerates the company's board.**
  `postings.status` is a two-valued column and stays one; the third state is derived HERE, at the
  read boundary, and no consumer of the column sees it (D-324).

**Deduplication is by canonical job, not by posting** (design §6.1). Measured on the live store: 227
postings fall into 100 multi-posting job groups, and `applications` keys on `job_id`, so a posting
whose sibling was applied to must not reappear. One entry per job, showing its LIVE posting where
the job has one and the most recently delivered posting otherwise (`_supersedes`).

**No `IN (...)` list is ever built over the corpus.** The delivered set is reached by a JOIN from
`artifacts` (656 rows) outward, never by collecting 48,000+ open posting ids and binding them — the
mistake that hit SQLite's 32,766 bound-parameter cap at six call sites on 2026-08-23 and took the
daily driver down (`store/param_chunks.py`). The only id lists this module binds are the
deduplicated winners, bounded by the artifact count, and they go to `current_posting_versions`
and `current_verdicts`, both of which already chunk internally.

`load_settings()` is called inside these functions rather than taken as a parameter because the
signatures are fixed by the implementation plan and carry no `Settings`. It is a file read, not a
write: `load_settings` creates no directory, and neither does `load_rules`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection, Row, Select, func, null, select
from sqlalchemy.sql import Subquery

from boardwatch.core.clock import utcnow
from boardwatch.core.identity_kinds import IDENTITY_ALGORITHM_VERSION
from boardwatch.core.normalize import content_hash
from boardwatch.core.settings import Settings, load_settings
from boardwatch.eligibility.audit import AuditRequirement, load_audit
from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.preflight import current_facts, current_identity
from boardwatch.eligibility.read import (
    NO_REQUIREMENT_FLAGS,
    RequirementFlags,
    current_gate_seniority,
    current_gate_verdicts,
    current_requirement_flags,
    current_verdicts,
)
from boardwatch.providers.registry import PROVIDER_NAMES
from boardwatch.rank.title_band import TitleBandReader, profile_target_band, title_band_reader
from boardwatch.store.applications import APPLIED_STATUSES, applied_job_ids
from boardwatch.store.ledger_queries import live_dispositions
from boardwatch.store.quarantine_queries import is_quarantined
from boardwatch.store.queries import (
    CurrentVersion,
    current_posting_versions,
    get_profile,
    latest_revision_at,
)
from boardwatch.store.queue_state import reported_job_ids, skipped_job_ids
from boardwatch.store.run_funnel_queries import TAILORED_KIND, lead_provenance
from boardwatch.store.tables import (
    application_events,
    applications,
    artifacts,
    board_scans,
    companies,
    posting_identities,
    posting_versions,
    postings,
)

if TYPE_CHECKING:  # its runtime import is function-local, to break the delivery <-> store cycle
    from boardwatch.delivery.review_gate import LaneDecision, ReviewReason

#: The audit's requirement view, reused rather than re-shaped. `load_audit` already slices each
#: quote from the frozen `posting_versions.body_text` and version-gates the label; a second
#: dataclass here would either copy that logic or drop half of it.
RequirementView = AuditRequirement

#: `postings.remote_policy` is NOT NULL and defaults to this, so it is the column's way of saying
#: nothing is known — not a fourth policy. It maps to `None` so no reader has to know the sentinel.
REMOTE_POLICY_UNKNOWN = "unknown"

#: The third RENDERED posting status, derived here and never stored. `postings.status` is
#: `CHECK (status IN ('open','closed'))` and 29 comparisons across 17 modules read it against
#: those two values; a third enum member would silently drop the rows out of the ranked corpus, the
#: extraction queue and the eligibility queue, which is far worse than a wrong label (D-324).
STATUS_UNVERIFIABLE = "unverifiable"

#: The stored status that means the posting is gone. Named so the delivery drain compares against
#: THIS rather than `!= "open"`, which would sweep `STATUS_UNVERIFIABLE` — a posting that is open
#: and merely unenumerable — into a drain reserved for dead ones.
STATUS_CLOSED = "closed"

#: The one `companies.tags_json` entry this module reads. Nothing in `src/` writes that column
#: today, so `target_flag` is `None` for every company on the live store; it is tri-state so that
#: "this company carries no tags at all" can never render as "this company is not a target".
TARGET_TAG = "target"

#: The digest of an empty JD body. DERIVED from `content_hash("")` rather than written down, so
#: it cannot drift from the normalizer. 245 body-less postings share it, and a slate key built on
#: it would collide every one of them at the same company and title.
EMPTY_BODY_HASH = content_hash("")


@dataclass(frozen=True)
class QueueRow:
    posting_id: int
    job_id: int
    title: str
    company: str
    #: The ATS the posting SITS ON — `companies.provider`, the ROW, never `classify_host` over
    #: `apply_url`. The job-apps lane writes the employer's own apply URL, so URL classification
    #: reads a lane copy as the employer's board; the same fact `standing_board_cross_host_keys`
    #: turns on. A lane row therefore carries its LANE's name (`jobapps`, `linkedin`, `indeed`,
    #: `hiringcafe`, `jsonld`), which is what the owner batching by ATS needs to see.
    provider: str
    location: str | None
    #: Raw location segments from `postings.locations_json`. `location` above is the joined display
    #: string; `classify_location` needs the segments, not the joined string (it splits on nothing).
    locations: tuple[str, ...]
    remote_policy: str | None
    posted_days: int | None
    first_seen: datetime
    #: `open`, `closed` or `unverifiable` — three values where the COLUMN has two. See `_status`.
    status: str
    verdict: str | None
    apply_url: str | None
    delivered_run_id: int | None
    tex_uri: str
    pdf_uri: str | None
    target_flag: bool | None
    #: What the CURRENT evaluation's requirement rows say: which kinds it left unconfirmed, and
    #: whether it produced any row at all. Read from the same evaluation as `verdict` above, in
    #: the same call, so the lane can never hold a lead for a requirement a newer verdict beside
    #: it had already resolved. Defaulted so a row built without it — every test fixture that
    #: predates the lane gates — behaves as before.
    requirement_flags: RequirementFlags = NO_REQUIREMENT_FLAGS
    #: The FINAL GATE's verdict on this lead's current version, read in the same call and under
    #: the same identity as `verdict` and `requirement_flags` above (0-B, D-489). `review_gate`
    #: uses it to release the two requirement holds and nothing else. Defaulted to None -- with
    #: the gate disarmed, or for a fixture built before this field existed, the lane is exactly
    #: what it was.
    judge_verdict: str | None = None
    #: The final gate's SEPARATE `seniority_fit` reading, in {yes, no, unclear}, read in the same
    #: call and under the same identity as everything above it. `"unclear"` is the inert default,
    #: so a row judged before the field existed withholds nothing.
    judge_seniority_fit: str = "unclear"
    #: T91. The QUOTED question from this posting's Greenhouse APPLICATION FORM that states a
    #: citizenship or export-control hard stop, or `None`.
    #:
    #: `None` is three things at once and they are deliberately indistinguishable here: the lead is
    #: not on Greenhouse, its form has not been fetched, or it was fetched and no catalog surface
    #: matched. Only a HIT can move a lead, so an unasked or unanswerable form costs the owner
    #: nothing — the fail-open direction a reading no rule can quote a span for is owed (D-380).
    #:
    #: Derived from the CACHE (`posting_form_questions`) under this row's own current version, in
    #: the same read as everything above it. Nothing here fetches: the network pass is
    #: `delivery/form_questions.sweep_form_questions`, run once per run, and this module never
    #: writes.
    form_question_hit: str | None = None
    #: T92. The provider's own structured `employmentType` for this posting when it states a
    #: NON-full-time engagement, else `None`.
    #:
    #: `None` is three things at once and they are deliberately indistinguishable, exactly as
    #: `form_question_hit` above: the lead is not on Ashby (measured 2026-09-22, no other provider
    #: writes the field), the provider stated nothing, or it stated a full-time value. Only a
    #: non-full-time value can move a lead, so a provider that says nothing costs the owner
    #: nothing.
    #:
    #: It HOLDS for a human read and can never carry a verdict: a provider-authored structured
    #: field is not the frozen JD (D-519 ruling 5), so it cannot satisfy `INELIGIBLE`'s
    #: quoted-span requirement.
    provider_employment_type: str | None = None
    #: T109. Whether this posting's TITLE levels above the operator's `target_seniority_band`,
    #: from `rank.title_band.TitleBandReader` — never from the JD body, which D-477 refused a
    #: deterministic family for.
    #:
    #: **COMPUTED on every read, never persisted**, and that is the whole point of carrying it
    #: here rather than in a column: the case it exists for is a lead delivered while the band was
    #: `any` that must re-route the day the operator narrows it to `entry`. A bit frozen at
    #: delivery would answer for a target that has since moved.
    #:
    #: It rides on the row for the reason `judge_seniority_fit` above does (D-332): the reader is
    #: built ONCE per read, beside the verdict and the requirement summary, so the four standing
    #: consumers cannot each derive their own answer and disagree about one lead. Four of them did
    #: exactly that by omission — they took `classify`'s old `False` default — until T109.
    seniority_above_band: bool = False
    #: T119. Whether this lead's job holds a LIVE `built` disposition, carries no application, and
    #: this posting was `revised` after that build decision — i.e. the JD moved under the résumé
    #: that was tailored for it.
    #:
    #: Derived ONCE per read by `revised_since_build_ids`, beside every other fact on this row and
    #: for the same reason (D-332). Not persisted and not derivable from any column here: it is a
    #: comparison between `job_dispositions.decided_at` and this posting's version history, and
    #: the ledger stamp it would otherwise be read off is content-blind by construction.
    #:
    #: Defaulted `False` so a fixture built before this field existed routes exactly as it did.
    revised_since_build: bool = False

    @property
    def closed(self) -> bool:
        """Whether the posting is gone, as the delivery drain asks it.

        A named predicate rather than a comparison repeated at each call site, so the one thing
        that must never drift — that `STATUS_UNVERIFIABLE` is NOT closed — is stated once. An
        unverifiable posting is open on a board nothing currently enumerates (D-324); draining it
        as dead would bury live work for a fault that is entirely ours.
        """
        return self.status == STATUS_CLOSED


@dataclass(frozen=True)
class AppliedRow:
    """One row of `applications`, with the posting that says what it was applied to.

    Every posting-derived field is NULLABLE, and that is the point: an application imported from
    another tool's history matched a posting the store holds, but nothing tailored a résumé for it,
    so the delivery queue never offered it. `posting_id` is the id the queue delivered and is
    `None` for exactly those rows — never a sibling posting's id, because that id is what the web
    page hands to `/api/pdf/<id>` and `/api/queue/<id>/unapplied`.
    """

    application_id: int
    job_id: int
    #: From the closed `ApplicationStatus` catalog, held there by a CHECK constraint.
    status: str
    #: When boardwatch LEARNED of the application, which is not when it was made.
    created_at: datetime
    #: When the application was MADE. `None` for an attempt that never reached `applied`.
    submitted_at: datetime | None
    #: `application_events.source` for the event that set the current status — "web", "import",
    #: "user". `None` on a row with no event, which no writer in this codebase can produce.
    source: str | None
    posting_id: int | None
    company: str | None
    title: str | None
    location: str | None
    apply_url: str | None
    #: `open`, `closed` or `unverifiable`, from `_status` — the same three the queue renders.
    posting_status: str | None
    closed_at: datetime | None
    pdf_uri: str | None
    #: Whether `mark_job_unapplied` would act on THIS attempt. The write is per JOB — it resolves
    #: posting -> job -> latest attempt — while this page is one row per attempt, so a control
    #: offered on every row promises something the route cannot do. True exactly when this row is
    #: its job's latest attempt, its status still reads as submitted, and a delivered
    #: `posting_id` exists to key the route on.
    can_unmark: bool


#: Why `QueueDetail.jd_body` is absent. A CLOSED set, declared where the value is produced so
#: `delivery/queue.py` consumes it rather than restating it — two spellings of one catalog is
#: how a consumer silently starts treating an unknown reason as a new bucket.
JD_ABSENT_NO_CURRENT_VERSION = "no_current_version"
JD_ABSENT_QUARANTINED = "quarantined_foreign_body"
JD_ABSENT_REASONS = frozenset({JD_ABSENT_NO_CURRENT_VERSION, JD_ABSENT_QUARANTINED})


@dataclass(frozen=True)
class QueueDetail:
    row: QueueRow
    jd_body: str | None
    jd_absent_reason: str | None
    requirements: list[RequirementView]
    board_target: str | None


def _board_ever_complete() -> Subquery:
    """The company ids whose board has EVER recorded a `complete` scan. One pass, grouped.

    Aggregated over `board_scans` and LEFT JOINed to the company, never a correlated
    `EXISTS (...)` per posting row: measured against the live store (260k open postings, 44k scan
    rows, no index on `board_scans.company_id`), the correlated shape did not finish in two
    minutes and this one is a single grouped scan. `watched_boards_never_complete` reaches the
    same fact by the same route for the same reason.

    No `run_id` and no `scan_kind` filter, exactly as that query does: `apply_board` runs the same
    absence closure whatever wrote the snapshot, so a `complete` row of any kind is a real owner.
    """
    return (
        select(board_scans.c.company_id)
        .where(board_scans.c.status == "complete")
        .group_by(board_scans.c.company_id)
        .subquery()
    )


def _delivered_select() -> Select[Any]:
    """One tailored artifact joined out to its posting and company. A local query builder.

    `posting_version_id` is nullable on `artifacts`, so the join to `posting_versions` is INNER: a
    tailored row that names no version cannot be resolved to a posting and is not a queue entry.
    `reports/tailor.py` always supplies it.

    `pdf_uri` is read out of `meta_json` under that exact key. The name is legacy (D-058) and
    load-bearing — `store/reconcile_queries.py` and the funnel both probe `$.pdf_uri` — so it is
    not renamed here. `json_extract` yields NULL both when the key is absent and when the tailor
    stored an explicit null for a résumé that never built a PDF, and both mean the same thing to a
    reader: there is no PDF to open.
    """
    ever_complete = _board_ever_complete()
    return (
        select(
            artifacts.c.id.label("artifact_id"),
            artifacts.c.uri.label("tex_uri"),
            artifacts.c.run_id.label("delivered_run_id"),
            artifacts.c.created_at.label("delivered_at"),
            func.json_extract(artifacts.c.meta_json, "$.pdf_uri").label("pdf_uri"),
            postings.c.id.label("posting_id"),
            postings.c.job_id,
            postings.c.title,
            postings.c.locations_json,
            postings.c.remote_policy,
            postings.c.posted_at,
            postings.c.first_seen_at,
            postings.c.status,
            # Read by `applied_rows` only: the applied page has to say WHEN a posting closed, and
            # nothing else in the queue's own payload asks. Selected here rather than in a second
            # query so both readers resolve the posting through one join.
            postings.c.closed_at,
            postings.c.url,
            companies.c.name.label("company"),
            companies.c.provider,
            # T92. Read out of `raw_json` rather than a `postings` column, deliberately.
            # `posting_versions` carries only `body_text` + `content_hash` and that hash covers
            # the BODY, so a provider flipping `employmentType` mints no new posting version
            # while `build_identity` keys on `{posting_version_id, profile_hash, rules_hash}` --
            # a column would therefore create a stale-verdict class the identity cannot see.
            # Selected here, in the one shared select, for the reason `closed_at` above is.
            func.json_extract(postings.c.raw_json, "$.employmentType").label(
                "provider_employment_type"
            ),
            # T109. `resolve_schemes` keys its per-company level schemes on (provider, slug), so
            # the title band is read against the company's OWN ladder where it has one. Selected
            # here rather than in a second query for the reason `closed_at` above is: one join.
            companies.c.slug,
            companies.c.tags_json,
            companies.c.watched,
            # T122. `watched` alone does not answer "does anything enumerate this board?" — see
            # `_status`. LEFT JOIN, so a board with no `complete` scan on record yields NULL.
            ever_complete.c.company_id.is_not(None).label("board_ever_complete"),
        )
        .join(posting_versions, artifacts.c.posting_version_id == posting_versions.c.id)
        .join(postings, posting_versions.c.posting_id == postings.c.id)
        .join(companies, postings.c.company_id == companies.c.id)
        .outerjoin(ever_complete, ever_complete.c.company_id == companies.c.id)
        .where(artifacts.c.kind == TAILORED_KIND)
    )


def _location(locations: object) -> str | None:
    """`postings.locations_json` rendered the way `show` renders it, or None when there is none.

    An empty list is None, not `""`: a posting that names no place has not named an empty place.
    """
    if not isinstance(locations, list):
        return None
    named = [str(loc) for loc in locations if str(loc).strip()]
    return ", ".join(named) if named else None


def _locations_list(locations: object) -> tuple[str, ...]:
    """The raw location segments for `classify_location`, which needs the list, not the joined
    display string. Empty when the posting names no place."""
    if not isinstance(locations, list):
        return ()
    return tuple(str(loc) for loc in locations if str(loc).strip())


def _target_flag(tags: object) -> bool | None:
    """Tri-state read of `companies.tags_json`. None when the company carries no tags at all."""
    if not isinstance(tags, list) or not tags:
        return None
    return any(isinstance(tag, str) and tag.strip().lower() == TARGET_TAG for tag in tags)


def _posted_days(posted_at: datetime | None, now: datetime) -> int | None:
    """Age in whole days from the NULLABLE `postings.posted_at`, or None when the board publishes
    no date. Never 0 for the absent case — `rank/explain.why_summary` floors at 0 for a posting
    dated in the future, and 0 there means "posted today", which is a measurement.
    """
    if posted_at is None:
        return None
    return max((now - posted_at).days, 0)


def _status(status: object, watched: object, board_ever_complete: object) -> str:
    """`open` only where a board is actually enumerated; otherwise `unverifiable` (D-314).

    `_process_missing` is the sole writer of `closed` and it runs on `complete` snapshots only,
    so `closed` is always a real measurement and passes through untouched — including on a
    company that has since been unwatched. `open`, by contrast, is only ever the ABSENCE of a
    close, and for a company nobody enumerates no scan can ever produce one: the posting was
    never measured as still listed, merely never contradicted. Probing 45 such rows found 40
    alive and 0 dead, so this is not "probably gone" either — it is not known.

    **Two conditions, because `companies.watched` does not by itself answer the question it is
    read for.** It means the board is CONFIGURED for scans; absence closure additionally needs a
    `complete` snapshot, since `scan/apply.py::apply_board` calls `_process_missing` for those
    alone. A watched board whose scans only ever reach `partial` therefore produces no `closed`
    verdict either, and its open postings are exactly as unmeasured as the unwatched class
    D-314/D-324 named. Measured on the live store 2026-09-20 after run 468: **16,510 open
    postings on 8 such boards**, seven of them Workday/oraclehcm — Workday returns `partial` on
    ANY detail error — against 231,749 open postings on 1,792 boards that have completed at least
    once. The three cohorts (this one, unwatched, watched-and-complete) partition the whole
    260,306-posting open corpus exactly, so the predicate discriminates.

    The watched half is NOT keyed on `source='lane'`. Measured on the live store 2026-08-27: 274
    of the 722 affected rows are on `source='user'` companies, and 23 lane-acquired postings sit
    on watched companies where `open` IS a measurement. The source predicate is wrong in both
    directions.

    **Rendered status only.** Nothing is retired, closed or suppressed: `QueueRow.closed` and
    `delivery/review_gate.classify` ask `status == "closed"` and never `!= "open"`, so an
    `unverifiable` lead keeps the lane and the listing it has today.
    """
    if str(status) != "open":
        return str(status)
    return str(status) if watched and board_ever_complete else STATUS_UNVERIFIABLE


def _supersedes(row: Row[Any], incumbent: Row[Any]) -> bool:
    """Whether `row` replaces `incumbent` as its canonical job's one offered posting.

    **Liveness first; delivery recency only breaks its ties** (D-432). Rows arrive ascending by
    delivery, so plain assignment means "the last one wins", and that was the rule until it cost a
    delivery: eBay job 35249 held an open Workday requisition delivered at run 73 and a dead lane
    copy of the same job delivered at run 137. The dead copy won on recency, so `closed_job_ids`
    reported the JOB closed and `reconcile_queue` filed a live lead under `_closed`, which offers
    nothing again. Measured 2026-09-02, joined through the delivered artifacts: one job.

    **The question is "is this posting CLOSED?", never "is it not open?"** — the two differ on
    `STATUS_UNVERIFIABLE`, and a posting on a board nothing enumerates is live work held back by a
    fault that is entirely ours (D-324), so preferring a genuinely dead sibling over it would bury
    the very lead this rule exists to surface. The `unverifiable` arm of the pin catches the
    inverted form. Reading `_status` rather than `postings.status` is not what defends that,
    and cannot be: `_status` passes `closed` through untouched, so the two spellings are
    indistinguishable by any test. It is here to stay in step with the one derivation if a fourth
    rendered status is ever added.

    Both liveness ties — all live, all closed — fall through to recency unchanged, so this narrows
    today's behaviour to the one case that was wrong rather than replacing it.

    **THE INVERSE TRAP THIS CREATES, NAMED AND BOUNDED RATHER THAN LEFT TO BE FOUND.** Nothing can
    ever close an `unverifiable` posting: `_process_missing` writes `closed` only off a `complete`
    snapshot of a watched board. So a job holding BOTH an unverifiable posting and a genuinely
    closed one is now held in the queue permanently, where recency used to drain it whenever the
    closed sibling happened to be the later delivery. Measured on the live store 2026-09-02:
    **2** jobs hold both a live and a closed delivered posting and **both** live sides are a
    genuine `open`, so the trap's population is **0** today.

    Accepted deliberately, and the direction is the one this file already takes everywhere else: a
    dead requisition left in the queue costs the owner one click, while a live requisition filed
    under `_closed` is an application never sent. Fail-open is the correct side of THIS gate even
    though it is the wrong side of others.
    """
    if _status(row.status, row.watched, row.board_ever_complete) != STATUS_CLOSED:
        return True
    return (
        _status(incumbent.status, incumbent.watched, incumbent.board_ever_complete)
        == STATUS_CLOSED
    )


#: The one `employmentType` value that is not a hold. A provider vocabulary, so it lives beside
#: the reader that normalises it rather than in `review_gate`, which stays free of provider terms.
_FULL_TIME_EMPLOYMENT_TYPE = "FullTime"


def _provider_employment_type(value: object) -> str | None:
    """The provider's `employmentType` when it states a NON-full-time engagement, else `None`.

    Normalised HERE so `review_gate.classify` carries no provider vocabulary and so the reason it
    publishes can quote the value the provider actually wrote. `json_extract` yields NULL both
    when the key is absent and when the provider stored an explicit null, and both mean the same
    thing to a reader: nothing was stated.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == _FULL_TIME_EMPLOYMENT_TYPE:
        return None
    return text


def _queue_row(
    row: Row[Any],
    *,
    verdict: str | None,
    now: datetime,
    requirement_flags: RequirementFlags = NO_REQUIREMENT_FLAGS,
    judge_verdict: str | None = None,
    judge_seniority_fit: str = "unclear",
    form_question_hit: str | None = None,
    band: TitleBandReader | None = None,
    revised_since_build: bool = False,
) -> QueueRow:
    return QueueRow(
        posting_id=int(row.posting_id),
        job_id=int(row.job_id),
        title=str(row.title),
        company=str(row.company),
        provider=str(row.provider),
        location=_location(row.locations_json),
        locations=_locations_list(row.locations_json),
        remote_policy=(
            None if row.remote_policy == REMOTE_POLICY_UNKNOWN else str(row.remote_policy)
        ),
        posted_days=_posted_days(row.posted_at, now),
        first_seen=row.first_seen_at,
        status=_status(row.status, row.watched, row.board_ever_complete),
        verdict=verdict,
        apply_url=str(row.url) if row.url is not None else None,
        delivered_run_id=(
            int(row.delivered_run_id) if row.delivered_run_id is not None else None
        ),
        tex_uri=str(row.tex_uri),
        pdf_uri=str(row.pdf_uri) if row.pdf_uri is not None else None,
        target_flag=_target_flag(row.tags_json),
        requirement_flags=requirement_flags,
        judge_verdict=judge_verdict,
        judge_seniority_fit=judge_seniority_fit,
        form_question_hit=form_question_hit,
        provider_employment_type=_provider_employment_type(row.provider_employment_type),
        # `None` means the caller resolved no reader and the gate is therefore inert for this
        # row, which is what a fixture built before T109 gets. The live read paths always pass
        # one; `title_band_reader` itself is what makes an unset target band inert.
        seniority_above_band=(
            False
            if band is None
            else band.above_band(str(row.title), (str(row.provider), str(row.slug)))
        ),
        revised_since_build=revised_since_build,
    )


def _title_band(conn: Connection, settings: Settings) -> TitleBandReader:
    """The title-seniority reader for THIS read, built from the live config and profile.

    Takes the caller's already-bound `Settings` rather than calling `load_settings` again, exactly
    as `queue_detail`'s seniority read does: both read paths have one bound, and a second load
    would be a second chance for the two to disagree about a config dir mid-read.

    Called once per read pass and never per row — `load_leveling` parses YAML on every call.
    """
    return title_band_reader(settings, profile_target_band(get_profile(conn)))


def lane_decision(row: QueueRow) -> LaneDecision:
    """The lane and the reason for ONE standing lead: the single call every standing reader makes.

    The four standing consumers — `delivery/queue.py:sync_queue`'s folder placement, the web
    API's two lists and its detail pane, `review_job_ids` and `apply_lane_placements` — each used
    to spell the arguments out themselves. They drifted, which is the failure D-332 names: all
    four omitted the title band, one also omitted `posting_closed`, and every one of them reduced
    the gate's verdict to `judge_verdict == "eligible"`, so a current `ineligible` could hold
    nothing. Nothing in the suite caught it because each call site has its own fixtures.

    Passing the ROW is what makes `apply_lane_placements`' "the SAME call, with the SAME argument
    shape" true rather than merely intended: there is now one argument list, so a field added to
    `QueueRow` has exactly one place to be wired in and a field dropped is not expressible.

    `classify` rather than `lane`: the folder a lead lands in and the reason the page publishes
    for it are ONE decision, so neither can be re-derived into disagreement with the other.
    """
    from boardwatch.delivery.review_gate import classify  # noqa: PLC0415 - import cycle

    return classify(
        verdict=row.verdict,
        locations=row.locations,
        title=row.title,
        experience_unconfirmed=row.requirement_flags.experience_unconfirmed,
        eligibility_unconfirmed=row.requirement_flags.eligibility_unconfirmed,
        no_requirement_rows=row.requirement_flags.no_requirement_rows,
        posting_closed=row.closed,
        seniority_above_band=row.seniority_above_band,
        judge_verdict=row.judge_verdict,
        judge_seniority_above_band=row.judge_seniority_fit == "no",
        revised_since_build=row.revised_since_build,
        form_question_hit=row.form_question_hit,
        provider_employment_type=row.provider_employment_type,
    )


def _identity(conn: Connection) -> tuple[str | None, str | None]:
    """The live profile's (profile_hash, rules_hash), or (None, None) with no profile.

    `current_verdicts` returns `{}` for the None pair, so every verdict reads as absent on a store
    that has no profile — which is the truth, not a failure.
    """
    identity = current_identity(conn, load_settings())
    return identity if identity is not None else (None, None)


def ineligible_job_ids(conn: Connection) -> dict[int, str]:
    """`job_id` -> its verdict, for every delivered lead the eligibility gate now rejects.

    Derived from `delivered_unapplied` itself rather than from a second query over the same
    tables, so the drain on disk and the page can never disagree about a verdict — the one
    failure this would otherwise invite, because a folder claiming a verdict the page does not
    show is indistinguishable from a stale folder.

    `skipped=set()` is deliberate. An owner's skip is a statement about what they did and it
    outranks a derived verdict, so the precedence lives in `_wanted_location`, not here: this
    reports the verdict for a skipped lead too and lets the caller decide which wins. Hiding
    them here would make a lead that is BOTH skipped and ineligible flip drain whenever the
    caller changed.
    """
    return {
        row.job_id: row.verdict
        for row in delivered_unapplied(conn, skipped=set())
        if row.verdict == "ineligible"
    }


def standing_slate_keys(
    conn: Connection, *, applied: dict[int, str] | None = None
) -> dict[tuple[int, str, str], tuple[int, ...]]:
    """`(company_id, normalized_title, content_hash)` -> posting ids STILL IN FRONT OF THE OWNER.

    The delivery slate cap's key (`top_cmd.SLATE_CAP_PER_KEY`, D-345), read over the leads the owner
    can still act on. It exists because that cap was scoped to one run and the queue is not (D-439):
    the cap DEFERS rather than drops, so a group sharing one byte-identical JD delivered one member
    per run forever. Measured: **49 exact-key groups holding 84 redundant standing leads**, one
    delivering on six consecutive runs, every run respecting the cap.

    **WHICH DRAINS DISQUALIFY A LEAD FROM HOLDING A SLOT, AND WHY THEY DIFFER — the first cut got
    this wrong and it was D-295 by accident.** A slot may only be held by a lead the owner can still
    act on, or the deferral never ends and a distinct posting is suppressed permanently:

    * **`closed` is excluded** — via `postings.status`, not a job set. A closed lead is out of the
      queue and can never be applied to or skipped, so it would hold its slot forever.
    * **`applied` and `skipped` are excluded** — the owner acted, so a second copy is now useful.
    * **`reported` is excluded** — a report says "hold this for investigation"; the owner will by
      definition never apply to it and it is already out of the web queue, so neither release
      condition could ever fire.
    * **`ineligible` is KEPT, and this is the one that looks wrong and is not.** The slate keys on
      the JD hash, so an ineligible lead's byte-identical twin has the same body, therefore the
      same verdict under the same identity, and is ineligible too — **capping it loses nothing.**
      `reconcile` pulls the folder straight back the moment the verdict clears, so this is a
      deferral with a live end condition and not a hole.
    * **`review` is KEPT** for the plainest reason of all: a lead awaiting the owner's look IS in
      front of the owner. It is what the phrase means.
    * **`lane_copy` is EXCLUDED**, and for the opposite reason to `ineligible`. The lead is not in
      front of the owner — its employer-board twin is, and that twin is a delivered lead holding
      the slot itself. Keeping both would let one job hold two slots and suppress a second,
      distinct posting for as long as the pair stood. The release condition is live: the moment
      the board twin stops holding, `lane_copy_job_ids` stops returning the lane copy and it
      ranks again.

    **That list is `delivery.names.DRAIN_DIRS`, and this is the SECOND place the program decides
    what a drain means** — `queue._wanted_location` ranks the same six into folders. Two ladders
    over one catalog drift silently, and a seventh drain added to one of them would be filed by the
    queue and invisible here, holding a slot with no release condition at all. Rather than couple a
    perf-sensitive ranking query to the queue module, the correspondence is pinned as a test:
    `test_delivery_queries.py::test_every_drain_has_a_recorded_answer_on_whether_it_holds_a_slot`
    enumerates `DRAIN_DIRS` and fails on any member this docstring has not decided.

    **The rule underneath: liveness is a property of the POSTING; content is a property of the
    JOB.** That is why `closed` must not hold a slot while `ineligible` may — a closed lead's twin
    may be OPEN, same bytes and different liveness, which is exactly the buried-live-requisition bug
    D-432 fixed, arriving from the other direction.

    `status == 'open'` is the right filter and NOT `derived != closed`: `STATUS_UNVERIFIABLE` is
    derived at the read boundary and the stored column is only `open`/`closed`, so an unverifiable
    posting is stored `open` and correctly keeps its slot — it is live work (D-324).

    **The hash is the FROZEN `posting_versions.content_hash` of the delivered version**, not
    `postings.content_hash`, which `scan/apply.py` rewrites in place. The cap's claim is that a
    byte-identical JD is *already in front of the owner*, and what the owner was given is the frozen
    body; a mutable hash would make the claim about text they never saw.

    An empty body is excluded by comparing against `EMPTY_BODY_HASH`, which is DERIVED from
    `content_hash("")` rather than written down. That is a real guard where `content_hash != ""`
    was a tautology — the column is NOT NULL and a hash is always 64 hex chars, so the earlier
    filter excluded nothing. It is also stricter than `top_cmd`'s SQLite `trim`, which does not
    strip U+00A0: a JD that is only `&nbsp;` after extraction hashes here to the empty digest and is
    correctly refused a slot.

    An empty `normalized_title` is excluded for the reason `top_cmd` excludes it: an empty component
    collides unrelated postings, and the cost of firing wrongly is a real lead nobody ever sees.

    **Ordered by DELIVERY RECENCY, most recent first, and that buys two things.** A posting with
    MORE THAN ONE delivered version resolves to its most recent delivery — without a tie-break
    SQLite may emit either, and the seed would hold a hash the owner no longer has, the exact
    failure the frozen hash is here to prevent. This is the recency half of `_supersedes`; the
    liveness half is the `status == 'open'` filter above.

    And **each key's holder list comes out most-recently-delivered first**, so a caller reporting
    `holders[0]` names the lead the owner saw MOST RECENTLY rather than whichever posting happened
    to carry the lowest row id. `top_cmd` renders that id to the operator as "same JD as <id>", and
    an arbitrary sibling out of a group of six would be untraceable in exactly the case the field
    exists for. **Multi-holder keys are the ordinary case, and the count GROWS until this ships**:
    49 exact-key groups when D-439 measured it, 53 a day later, because the mechanism it fixes is
    still running. Do not re-pin the number here — it is a moving target by construction, and what
    the ordering has to be right about is that the case exists at all.

    **`ineligible` IS a releasable quarantine, and naming its drain is what keeps this inside the
    rule that every quarantine needs one.** `applied`/`skipped`/`reported` can indeed never fire for
    an ineligible lead — it is stripped from every surface the owner can act on. **Its drain is the
    VERDICT CLEARING**: `reconcile_queue` pulls the folder back out of `_ineligible` the moment a
    re-evaluation says so, and the lead returns to the queue where the owner can act on it. That is
    the same re-entry path the `_ineligible` bucket relies on generally.

    The residual exposure is an UNEVALUATED twin: `rank_open_postings` filters `ineligible`
    *before* the cap, so an evaluated twin of an ineligible lead never reaches it at all, but a twin
    with `verdict is None` would. **Measured on the live store 2026-09-03: 86 of 138,676 open
    postings (0.1%) carry no verdict, and ZERO of them share a slate key with an ineligible
    standing lead.** Bounded, not assumed.
    """
    # `applied` is accepted rather than read when the caller already holds it. `rank_open_postings`
    # reads it for its own suppression, and two reads on SQLite are two snapshots — an application
    # landing between them would leave this seed holding a slot the rest of the run has already
    # released. One read, one snapshot, and one fewer full-table scan on the ranking path.
    applied_ids = applied if applied is not None else applied_job_ids(conn)
    skipped = skipped_job_ids(conn)
    reported = reported_job_ids(conn)
    rows = conn.execute(
        select(
            postings.c.id,
            postings.c.job_id,
            postings.c.company_id,
            postings.c.normalized_title,
            posting_versions.c.content_hash,
        )
        .join(posting_versions, posting_versions.c.posting_id == postings.c.id)
        .join(artifacts, artifacts.c.posting_version_id == posting_versions.c.id)
        .where(
            artifacts.c.kind == TAILORED_KIND,
            postings.c.job_id.is_not(None),
            postings.c.status == "open",
            postings.c.normalized_title != "",
            posting_versions.c.content_hash != EMPTY_BODY_HASH,
        )
        .order_by(artifacts.c.created_at.desc(), artifacts.c.id.desc(), postings.c.id)
    ).all()
    held: dict[tuple[int, str, str], list[int]] = {}
    emitted: set[int] = set()
    for row in rows:
        job_id = int(row.job_id)
        if job_id in applied_ids or job_id in skipped or job_id in reported:
            continue
        if int(row.id) in emitted:
            continue
        emitted.add(int(row.id))
        key = (int(row.company_id), str(row.normalized_title), str(row.content_hash))
        held.setdefault(key, []).append(int(row.id))
    return {key: tuple(ids) for key, ids in held.items()}


def standing_board_cross_host_keys(
    conn: Connection, *, skipped: set[int]
) -> dict[str, tuple[int, ...]]:
    """`cross_host` identity key -> the EMPLOYER-BOARD posting ids standing in the owner's queue.

    The seed for D-498 rule (a): a lane's copy of a posting is redundant when the employer's OWN
    board copy of the same job is already in front of the owner. Measured 2026-09-13 over the
    standing 209 apply + 380 review leads: 34 `cross_host` groups with more than one member, of
    which rule (a) resolves 17.

    **`cross_host` GROUPS AND NEVER SUPPRESSES (§3.1, D-494), and nothing here changes that.**
    `cross_host.suppresses` stays False and `core/dedup.py` stays unreachable from
    `resolve_duplicates`; this is a DELIVERY policy that reads the same grouping to decide which
    of two already-grouped leads to put in front of the owner. No identity claim is made and no
    posting is suppressed in the store — which is why it is safe here and would not be there:
    the counterexample §3.1 refuses is Microsoft's four same-title Redmond requisitions, and they
    are all EMPLOYER-BOARD rows, so rule (a) cannot touch them.

    **The employer-board test is `companies.provider in PROVIDER_NAMES`, not the URL host class.**
    `core/host_class.classify_host` reads the URL, and the job-apps lane writes the employer's own
    apply URL — so URL classification calls a lane copy `ats` and elects nothing. Which ROW a
    posting sits on is the fact that decides this, and the provider registry is the closed catalog
    that names it.

    **Only OPEN standing leads hold, and that is the drain.** The same ladder `standing_slate_keys`
    had to settle: `applied`, `skipped` and `reported` mean the owner has acted, and `closed` means
    the requisition is gone — in every one of those cases the board copy stops holding and the lane
    copy ranks again on the very next run. `status == 'open'` is the right filter for the same
    reason it is there: `STATUS_UNVERIFIABLE` is derived at the read boundary, so an unverifiable
    posting is stored `open` and correctly keeps holding (D-324).

    **The CURRENT `algorithm_version` only.** Identity rows are written beside history — the
    UNIQUE key includes the version — and `identities reap` is manual with no scheduler behind it,
    so a retired generation sits on disk indefinitely. A board copy elected on a key the identity
    subsystem has withdrawn would hold a lane copy back on evidence that no longer speaks for
    either row; no current key means no holder, which is the fail-open direction here.

    **Reached by a JOIN outward from `artifacts`, never by collecting ids and binding them.** This
    module binds no id list at all — that shape hit SQLite's 32,766 bound-parameter cap at six call
    sites on 2026-08-23 and killed every scheduled run from that day on — so the drain sets and the
    provider test are applied in Python over the joined rows.
    """
    applied = applied_job_ids(conn)
    reported = reported_job_ids(conn)
    rows = conn.execute(
        _delivered_select()
        .add_columns(posting_identities.c.identity_key)
        .join(
            posting_identities,
            (posting_identities.c.posting_id == postings.c.id)
            & (posting_identities.c.kind == "cross_host")
            & (posting_identities.c.algorithm_version == IDENTITY_ALGORITHM_VERSION),
        )
        .where(postings.c.status == "open", postings.c.job_id.is_not(None))
    ).all()
    held: dict[str, list[int]] = {}
    for row in rows:
        job_id = int(row.job_id)
        if job_id in applied or job_id in skipped or job_id in reported:
            continue
        # Which ROW the posting sits on, never the URL host class: the job-apps lane writes the
        # employer's own apply URL, so `classify_host` reads a lane copy as `ats`.
        if str(row.provider) not in PROVIDER_NAMES:
            continue
        key = str(row.identity_key)
        posting_id = int(row.posting_id)
        if posting_id not in held.setdefault(key, []):
            held[key].append(posting_id)
    return {key: tuple(ids) for key, ids in held.items()}


def lane_copy_job_ids(conn: Connection, *, skipped: set[int]) -> set[int]:
    """`job_id` for every delivered LANE copy whose employer-board twin is also standing.

    D-498 rule (a)'s missing half. That rule drops a lane's copy of a posting when the employer's
    own board copy is on the slate or standing in the queue — but it runs in the RANKER, so it
    stops a redundant copy being delivered and does nothing about the ones delivered before it
    shipped. Measured 2026-09-14 over 670 standing leads: **17 lane copies whose employer-board
    twin is also standing**, every one of them a `jobapps` row beside a greenhouse / eightfold /
    oraclehcm row. A quarantine with no drain on the standing side is the gap this closes.

    **The seed is `standing_board_cross_host_keys`, reused rather than restated**, so the ranker
    and the queue answer "is the employer's own copy already in front of the owner?" from ONE
    definition. Everything that docstring settles holds here unchanged: the employer-board test is
    `companies.provider in PROVIDER_NAMES` and never the URL host class, because the job-apps lane
    writes the employer's own apply URL and `classify_host` therefore reads a lane copy as `ats`.

    **`cross_host` still suppresses nothing (§3.1, D-494).** No identity claim is made and no
    posting is suppressed in the store; this reads the same grouping to decide which of two
    already-grouped leads to put in front of the owner. §3.1's counterexample — Microsoft's four
    same-title Redmond requisitions — is four EMPLOYER-BOARD rows, and the provider test excludes
    every one of them, so this can no more collapse them than rule (a) can.

    **The CURRENT `algorithm_version` only, on both sides.** The seed carries the filter and so
    does the read below it: matching a delivered lane row's RETIRED key against a current holder
    would file a standing lead under `_lane_copy` on a generation nothing else reads.

    **It self-heals in both directions with no extra machinery**, which is the property that makes
    it a deferral and not a hole. The set is recomputed every reconcile from
    `standing_board_cross_host_keys`, whose own ladder stops a board copy holding once the owner
    applies, skips or reports it, or the requisition closes. When the board copy stops holding, the
    lane copy is drawn straight back out of `_lane_copy` on the next pass — the same shape
    `closed_job_ids` has.

    A bare set, like `closed_job_ids` and `review_job_ids`: `_wanted_location` asks only whether
    the job is in it. Naming WHICH lead supersedes this one would be better for a reader auditing
    the drain folder, but that needs a `details.json` field and `DETAILS_SCHEMA` is versioned, so
    it is left for whoever wants it rather than carried unused here.
    """
    held = standing_board_cross_host_keys(conn, skipped=skipped)
    if not held:
        return set()
    holder_of: dict[str, int] = {key: ids[0] for key, ids in held.items() if ids}
    # Joined outward from the delivered rows, binding no id list: this module hit SQLite's
    # 32,766 bound-parameter cap at six call sites on 2026-08-23 and the drain sets have been
    # applied in Python over joined rows ever since.
    rows = conn.execute(
        _delivered_select()
        .add_columns(posting_identities.c.identity_key)
        .join(
            posting_identities,
            (posting_identities.c.posting_id == postings.c.id)
            & (posting_identities.c.kind == "cross_host")
            & (posting_identities.c.algorithm_version == IDENTITY_ALGORITHM_VERSION),
        )
        .where(postings.c.status == "open", postings.c.job_id.is_not(None))
    ).all()
    out: set[int] = set()
    for row in rows:
        if str(row.provider) in PROVIDER_NAMES:
            continue
        holder = holder_of.get(str(row.identity_key))
        if holder is None or holder == int(row.posting_id):
            continue
        out.add(int(row.job_id))
    return out


def closed_job_ids(conn: Connection) -> set[int]:
    """`job_id` for every delivered lead whose posting the store now reports closed.

    Derived from `delivered_unapplied` for the same reason `ineligible_job_ids` is: the drain on
    disk and the page cannot then disagree about the same lead. `skipped=set()` is deliberate too,
    so the applied/skipped precedence stays in `_wanted_location` — an owner who already applied
    keeps that record even after the requisition comes down.

    This drain self-heals in both directions with no extra machinery: the set is recomputed every
    reconcile, so a posting the liveness check reopens is drawn straight back out of `_closed`.
    """
    return {row.job_id for row in delivered_unapplied(conn, skipped=set()) if row.closed}


def standing_lead_job_ids(conn: Connection) -> set[int]:
    """`job_id` for every lead still standing in front of the owner.

    One name for the set `delivery/server.py::_skip_batch` already calls "the standing set", so
    a reader outside this module — `pipeline/death_probe.py` is the first — asks the question
    once rather than re-deriving it from `job_dispositions` or from `applications`. Derived from
    `delivered_unapplied` for the same reason `closed_job_ids` and `review_job_ids` are: nothing
    may disagree with the queue page about which leads exist. `skipped=set()` matches those two,
    so the applied/skipped precedence stays in `_wanted_location`.

    **It is the union of every lane, not just apply plus review**, and that width is deliberate
    rather than unnoticed: the drained leads (`ineligible`, `_closed`, `_lane_copy`) are still
    delivered rows this set names. Narrowing it would mint a fifth caller of
    :func:`boardwatch.delivery.review_gate.lane` to answer a question no caller has yet needed —
    and the one caller there is uses this only as a PRIORITY, where over-inclusion costs a
    handful of places in a queue and under-inclusion costs a lead.
    """
    return {row.job_id for row in delivered_unapplied(conn, skipped=set())}


def review_job_ids(conn: Connection) -> set[int]:
    """`job_id` for every delivered lead the verified-uncertain check routes to the review lane.

    An `uncertain` lead reached the queue by failing open at a ranker gate; it is
    blindly-appliable only when confirmed US and confirmed software. Everything else — foreign or
    unknown location, non-software title, or an unevaluated (`None`) verdict — belongs in review.

    Derived from `delivered_unapplied` for the same reason `ineligible_job_ids` is: the drain on
    disk and the page cannot then disagree about a classification. `ineligible` is excluded here —
    it has its own drain — and `skipped=set()` is deliberate, so the applied/skipped precedence
    lives in `_wanted_location`, not here.

    `posting_closed` is passed so this set means what its name says. A closed lead is NOT routed to
    review, so including it would make the function state something false about that lead. No test
    can currently observe the difference — `_wanted_location` ranks `closed` above `review`, so the
    wrong answer is masked downstream — and that mask is precisely why the honesty has to live
    here: the day the precedence changes, this function must already be right.
    """
    from boardwatch.delivery.review_gate import REVIEW_DIR  # noqa: PLC0415 - import cycle

    return {
        row.job_id
        for row in delivered_unapplied(conn, skipped=set())
        if row.verdict != "ineligible" and lane_decision(row).lane == REVIEW_DIR
    }


@dataclass(frozen=True)
class LanePlacement:
    """Where ONE placeable lead of a run finally landed, and the reason that put it there.

    The NAMED form of what `apply_lane_placements` below counts. It exists because a count cannot
    be audited: B8's volume half is read off this cohort (T110), and a sampled audit of that
    reading has to draw from the same population the number came from, which means the population
    has to be written down rather than summed away.

    `lane` is `""` for the blind-apply queue and `REVIEW_DIR` for a held lead. Never `CLOSED_DIR`:
    a closed posting is not placeable and never reaches this list.

    `review_reason` is carried straight off the SAME `LaneDecision` that produced `lane` — never
    re-derived — so the pair cannot disagree, which is the property `lane_decision` exists for
    (D-332). It is non-`None` exactly when `lane` is `REVIEW_DIR`.
    """

    posting_id: int
    job_id: int
    lane: str
    review_reason: ReviewReason | None


def apply_lane_cohort(
    conn: Connection, *, run_ids: set[int]
) -> dict[int, tuple[LanePlacement, ...]]:
    """Per delivering run: every PLACEABLE lead it delivered, NAMED, with its FINAL lane.

    The one derivation of this cohort. `apply_lane_placements` below folds it to two counts and
    the funnel's apply-lane section publishes it in full, so the alert, the artifact and any later
    audit are reading one population rather than three that agree today.

    FINAL is the whole point for T110. The funnel's `pdf` stage enters at the leads the tailor
    RENDERED, which is a pre-sweep cohort: `pending_tailor` is written once, before the tailor
    loop, and `runner`'s application-form sweep runs afterwards — so a lead that was rendered into
    the apply lane and then form-hard-stopped in the same run is still inside `pdf.entered`, and
    was inside B8's reading with it. This re-runs `review_gate.lane` over the state that exists
    when the funnel is written, so that lead is here as `_review` with
    `form_question_hard_stop` instead.

    The exclusions and the whole-corpus attribution are `apply_lane_placements`' — see it for why
    `ineligible` and `closed` are not placeable, and for why an OLDER run's cohort is what
    survives to today rather than what it shipped on the day.
    """
    cohort: dict[int, list[LanePlacement]] = {rid: [] for rid in run_ids}
    for row in delivered_unapplied(conn, skipped=set()):
        if row.delivered_run_id not in run_ids:
            continue
        if row.verdict == "ineligible" or row.closed:
            continue
        decision = lane_decision(row)
        cohort[row.delivered_run_id].append(
            LanePlacement(
                posting_id=row.posting_id,
                job_id=row.job_id,
                lane=decision.lane,
                review_reason=decision.reason,
            )
        )
    return {rid: tuple(rows) for rid, rows in cohort.items()}


def apply_lane_placements(
    conn: Connection, *, run_ids: set[int]
) -> dict[int, tuple[int, int]]:
    """Per delivering run: how many of its leads were PLACEABLE, and how many reached the apply
    lane. Keyed by `delivered_run_id`; a run in `run_ids` that delivered nothing is absent.

    Exists so the apply-lane drought detector can ask "did this run's work reach the blind-apply
    list?" without a second opinion about what the apply lane is. The lane call below is the SAME
    call, with the SAME argument shape, that `review_job_ids` above and `delivery/queue.py` and
    `delivery/api.py` make (D-332) — the whole reason this lives here rather than in `notify/` is
    that this module already holds one, so the lane decision gains a reader and not a fourth site
    that could drift. Since T109 that is enforced rather than intended: all four go through
    `lane_decision`, so there is one argument list and nothing to hand-copy.

    PLACEABLE is narrower than delivered, and each exclusion is what stops the detector naming the
    wrong gate:

    * `ineligible` is excluded because it has its own drain and was never apply-lane work.
    * `closed` is excluded because a dead requisition is a LIVENESS story with its own drain
      (D-383). A run whose every lead has since come down would otherwise read as lane starvation,
      which is a claim about the location/role/requirement gates that the evidence does not
      support.

    So a run with zero placeable leads reports `(0, 0)` and the detector abstains on it, rather
    than firing on a fault it cannot see. `skipped=set()` matches the two sibling functions above:
    the applied/skipped precedence belongs to `_wanted_location`, not to a read.

    Whole-corpus, not per-run, is `delivered_unapplied`'s contract — it returns one row per
    canonical job across ALL runs — so an OLDER run's count here is what survives to today, not
    what it shipped on the day. That is the right quantity for this question (the detector asks
    whether apply-lane work EXISTS, not what was once created) and it is why the counts must never
    be read as a delivery-day record.

    A FOLD of `apply_lane_cohort` above rather than a second sweep of its own (T110). The two
    numbers this returns and the named cohort the funnel publishes therefore cannot disagree about
    which leads are placeable or which of them reached the lane — there is one lane call, not two.
    """
    return {
        rid: (len(rows), sum(1 for row in rows if row.lane == ""))
        for rid, rows in apply_lane_cohort(conn, run_ids=run_ids).items()
    }


def delivered_unapplied(conn: Connection, *, skipped: set[int]) -> list[QueueRow]:
    """Every delivered, unapplied, unskipped lead across ALL runs, one row per canonical job.

    Not "the latest run's leads": a run that delivered nothing would then silently present an
    older run as current (design §6.1). "Latest run" is a filter a caller applies to this list,
    never its definition.

    Exclusion is by `job_id` on both sides — `applied_job_ids` keys on the job, and `skipped` is
    the caller's job-keyed set — so applying to one posting retires every sibling posting of the
    same job. A posting whose `job_id` is NULL is dropped rather than shown: it could be neither
    excluded by an application nor marked applied, so it would sit in the queue forever. The
    `postings_job_required_*` triggers make that unreachable for any row the scanner wrote.

    Which of a job's postings is shown is `_supersedes`: a live one, and the most recently
    delivered only among equally live ones. That choice decides the job's `closed` and `verdict`
    for every derived reader below, so it is not a display detail.

    Ordered most recently delivered first. Callers that want it ranked re-rank it; the store does
    not recompute a score (design §6.2 — score and coverage are recomputed live, never persisted).
    """
    applied = applied_job_ids(conn)
    settings = load_settings()
    # Ascending, so `_supersedes` reads a later delivery as the incumbent's challenger and its
    # liveness tie falls through to the most recent one.
    rows = conn.execute(
        _delivered_select().order_by(artifacts.c.created_at, artifacts.c.id)
    ).all()
    winners: dict[int, Row[Any]] = {}
    for row in rows:
        if row.job_id is None:
            continue
        job_id = int(row.job_id)
        if job_id in applied or job_id in skipped:
            continue
        incumbent = winners.get(job_id)
        if incumbent is None or _supersedes(row, incumbent):
            winners[job_id] = row

    ordered = sorted(
        winners.values(), key=lambda row: (row.delivered_at, int(row.artifact_id)), reverse=True
    )
    # Both reads chunk internally past the bound-parameter cap, and the list handed to them is
    # bounded by the artifact count rather than by the open corpus.
    versions = current_posting_versions(conn, [int(row.posting_id) for row in ordered])
    profile_hash, rules_hash = _identity(conn)
    version_ids = [version.posting_version_id for version in versions.values()]
    verdicts = current_verdicts(conn, version_ids, profile_hash, rules_hash)
    # Same identity and same version list as the verdicts above, so each row's summary and its
    # verdict come from ONE evaluation. Absent posting -> the all-False default.
    flags = current_requirement_flags(conn, version_ids, profile_hash, rules_hash)
    # The same version list, but NOT the same identity (T161): the judge's verdict is keyed on
    # what it was reached on (body, facts, judge, prompt), none of which a rules-only re-key moves.
    # The requirement summary it releases stays identity-scoped and is the CURRENT reading, so
    # pairing it with a verdict whose inputs are unchanged is as coherent as pairing it with a
    # fresh re-judge of them. The same-VERSION half is what stops a verdict about an old body
    # releasing a new body's flags, and it is kept.
    facts = current_facts(conn)
    gate = current_gate_verdicts(
        conn, version_ids, facts, load_rules(settings.config_dir), model=settings.gate.model
    )
    # Gated HERE and nowhere else on this side. Every consumer below reads
    # `row.judge_seniority_fit == "no"`, so leaving the column at its inert `"unclear"` when the
    # hold is disarmed is what keeps `sync_queue`, the web page and both drains agreeing — the
    # alternative, each call site checking the flag itself, is exactly the second opinion
    # `_review` exists to prevent (D-332). It also skips the query entirely when off.
    seniority = (
        current_gate_seniority(conn, version_ids, facts, model=settings.gate.model)
        if settings.gate.seniority_hold
        else {}
    )
    # T91. NOT identity-scoped, and that is the difference from every read above it: the
    # application form is a fact about the REQUISITION, not about this user's profile or the rules
    # catalog, so it is keyed on the frozen version alone. It cannot disagree with the verdict
    # beside it for the same reason — it is not an opinion about the same question.
    form_questions = form_question_hits(conn, versions)
    # T109. Built ONCE for the whole read, beside every identity-scoped fact above it and for the
    # same reason (D-332): the title band is config- and profile-dependent, and four standing
    # consumers of this list used to take `classify`'s `False` default rather than derive it — so
    # a senior title delivered under `target_seniority_band: any` stayed in the blind-apply lane
    # forever after the operator narrowed the band. Not identity-scoped like the verdict reads:
    # the band depends on the leveling catalog and the profile's TARGET, neither of which is part
    # of `profile_hash`, which is exactly why it must be recomputed here rather than stored.
    band = _title_band(conn, settings)
    now = utcnow()
    # T119. Bounded by the same winner list as every read above it, and read here rather than
    # per row: the ledger and the version history are two more tables, and a per-row derivation
    # would be one query per lead against both.
    revised = revised_since_build_ids(
        conn, {int(row.posting_id): int(row.job_id) for row in ordered}, now=now
    )
    return [
        _queue_row(
            row,
            verdict=verdicts.get(int(row.posting_id)),
            now=now,
            requirement_flags=flags.get(int(row.posting_id), NO_REQUIREMENT_FLAGS),
            judge_verdict=gate.get(int(row.posting_id)),
            judge_seniority_fit=seniority.get(int(row.posting_id), "unclear"),
            form_question_hit=form_questions.get(int(row.posting_id)),
            band=band,
            revised_since_build=int(row.posting_id) in revised,
        )
        for row in ordered
    ]


def revised_since_build_ids(
    conn: Connection, job_of: Mapping[int, int], *, now: datetime
) -> set[int]:
    """Which of `job_of`'s postings are BUILT, UNAPPLIED leads whose posting has moved since (T119).

    `job_of` is `posting_id -> job_id`, supplied by the caller rather than looked up here, for
    the reason this module binds no id list of its own: both callers already hold the pairing —
    `delivered_unapplied` off its own winner rows, `_lead_lanes` off the select it already issues
    for locations — and re-reading it would be a third query for a fact twice in hand.

    PUBLIC because it has two readers and they must not each have their own, exactly as
    `form_question_hits` below does: `delivered_unapplied` (the standing queue, the folder tree
    and the page) and `pipeline.runner._lead_lanes` (the run's pre-tailor split). Two derivations
    of "did this posting move after we built for it" would be the second opinion `_review` exists
    to prevent (D-332), and they would disagree the first time either one was touched.

    **The fact this answers, and why nothing else already reports it.** A `built` disposition
    governs its job permanently, and `pipeline/policy.run_policy_version` hashes the five
    run-manifest components and NOT posting content — so a body change moves no stamp and D-103's
    stale-policy drain (`ledger reopen --stale`) never fires for it. Measured on the live store
    read-only, 2026-09-20: of 887 built-but-unapplied jobs, 34 (3.8%) carry a `posting_versions`
    row captured after `job_dispositions.decided_at`. Inverting the date comparison returns the
    full 887, so the comparison discriminates rather than passing by construction.

    **Three filters, and the hold is wrong without any one of them.**

    * **A live `built` only.** Read through `ledger_queries.live_dispositions`, so
      `core.ledger.is_live` decides and no liveness predicate is written in SQL here — the
      reader/writer disagreement that module exists to prevent. A row the drain has already
      REOPENED is therefore not `built` here: that lead is back in front of the owner by the
      ordinary path and has nothing to re-enter. `disposition == "built"` is a plain catalog
      comparison and not a liveness one, exactly as `facet_queries._built_job_ids` reads it.
    * **Unapplied only.** An applied lead is done, and re-routing it would put finished work back
      in front of the owner. Keyed on the canonical `job_id` through `applied_job_ids`, as every
      other suppression is, so applying to one posting retires every sibling. Filtered HERE and
      not left to the caller because `_lead_lanes` holds no applied set, and a fact that is true
      at only one of two call sites is the drift T109 was written to stop.
    * **A `revised` capture only** — see `queries.REVISION_CAPTURE_REASON`.

    This function WRITES NOTHING and reads no ledger decision back into one. The `built` row keeps
    governing: the lead is routed, never reopened.
    """
    if not job_of:
        return set()
    applied = applied_job_ids(conn)
    built = {
        job_id: row.decided_at
        for job_id, row in live_dispositions(
            conn,
            now=now,
            job_ids=sorted({job_id for job_id in job_of.values() if job_id not in applied}),
        ).items()
        if row.disposition == "built"
    }
    if not built:
        return set()
    revised = latest_revision_at(
        conn, [posting_id for posting_id, job_id in job_of.items() if job_id in built]
    )
    return {
        posting_id
        for posting_id, captured_at in revised.items()
        if captured_at > built[job_of[posting_id]]
    }


def form_question_hits(
    conn: Connection, versions: dict[int, CurrentVersion]
) -> dict[int, str]:
    """`posting_id` -> the quoted form question holding it, for the leads a surface matches.

    PUBLIC because it has two readers, and they must not each have their own: `delivered_unapplied`
    above (the standing queue, the folder tree and the page) and `pipeline.runner._lead_lanes`
    (the pre-tailor split, which decides whether the expensive render is spent at all). Two
    derivations of "is this lead held by its form" would be the second opinion `_review` exists to
    prevent (D-332), and they would disagree the first time the catalog grew.

    The CATALOG is applied here, on every read, over the payload the sweep stored — never stored
    alongside it. So a surface added to `delivery/form_questions.CATALOG` takes effect on the next
    reconcile against every form already fetched, with no board re-asked and no migration.

    A version with no stored row is absent from the result, which is "no questions known". A
    version whose stored form matches nothing is absent too, and folding those two together is
    correct at THIS boundary even though `cached_form_questions` keeps them apart: both mean this
    lead is not held, and the lane must not be able to tell them apart.
    """
    from boardwatch.delivery.form_questions import (  # noqa: PLC0415 - import cycle
        decode_questions,
        match_questions,
    )
    from boardwatch.store.form_question_queries import (  # noqa: PLC0415 - see the module above
        cached_form_questions,
    )

    by_version = {
        version.posting_version_id: posting_id for posting_id, version in versions.items()
    }
    hits: dict[int, str] = {}
    for version_id, stored in cached_form_questions(conn, list(by_version)).items():
        hit = match_questions(decode_questions(stored))
        if hit is not None:
            hits[by_version[version_id]] = hit.question
    return hits


def _job_posting_select() -> Select[Any]:
    """A job's own postings, labelled exactly as `_delivered_select` labels them.

    Only `applied_rows` reads this, and only for a job that reached NO delivery: the application
    still has to name what was applied to, and the facts live on the posting either way. Labelled
    identically — including a `null` `pdf_uri` — so one row constructor serves both shapes and
    `_supersedes` can pick between them by the same rule the queue uses.
    """
    ever_complete = _board_ever_complete()
    return select(
        postings.c.id.label("posting_id"),
        postings.c.job_id,
        postings.c.title,
        postings.c.locations_json,
        postings.c.first_seen_at,
        postings.c.status,
        postings.c.closed_at,
        postings.c.url,
        companies.c.name.label("company"),
        companies.c.watched,
        ever_complete.c.company_id.is_not(None).label("board_ever_complete"),
        # No artifact, so no delivered résumé. `null()` rather than a missing column: the
        # constructor below reads the attribute on both shapes, and an absent one would be an
        # AttributeError at exactly the row this branch exists to serve.
        null().label("pdf_uri"),
    ).join(companies, postings.c.company_id == companies.c.id).outerjoin(
        ever_complete, ever_complete.c.company_id == companies.c.id
    )


def _applied_row(
    row: Row[Any],
    posting: Row[Any] | None,
    *,
    delivered: bool,
    source: str | None,
    can_unmark: bool,
) -> AppliedRow:
    """One application, with the posting that identifies it.

    `posting_id` is exposed ONLY for a delivered posting. It is the id every existing web control
    keys on — `/api/pdf/<id>`, `/api/queue/<id>/unapplied` — and handing out the id of a posting
    the queue never offered would offer a PDF that was never built. The facts around it come from
    whichever posting resolved, because "what did I apply to" has an answer in both cases.
    """
    return AppliedRow(
        application_id=int(row.id),
        job_id=int(row.job_id),
        status=str(row.status),
        created_at=row.created_at,
        submitted_at=row.submitted_at,
        source=source,
        posting_id=int(posting.posting_id) if delivered and posting is not None else None,
        company=None if posting is None else str(posting.company),
        title=None if posting is None else str(posting.title),
        location=None if posting is None else _location(posting.locations_json),
        apply_url=(
            None if posting is None or posting.url is None else str(posting.url)
        ),
        posting_status=(
            None
            if posting is None
            else _status(posting.status, posting.watched, posting.board_ever_complete)
        ),
        closed_at=None if posting is None else posting.closed_at,
        pdf_uri=(
            str(posting.pdf_uri)
            if posting is not None and posting.pdf_uri is not None
            else None
        ),
        can_unmark=can_unmark,
    )


def _deliveries(conn: Connection) -> list[Row[Any]]:
    """Every tailored delivery, ASCENDING by delivery, which is the order `_supersedes` reads.

    Reached by a join out of `artifacts` rather than by binding an id list, exactly as
    `delivered_unapplied` is, so no list is built over the corpus. Executed once and handed to
    both readers below: `applied_rows` needs the same scan keyed two ways — by job, for the
    queue's own choice, and by posting, for the one an application names.
    """
    return list(conn.execute(_delivered_select().order_by(artifacts.c.created_at, artifacts.c.id)))


def _delivered_winners(rows: Sequence[Row[Any]], job_ids: set[int]) -> dict[int, Row[Any]]:
    """The posting the delivery queue offered for each of `job_ids`, by the SAME rule the queue
    uses: `_supersedes` over the delivered artifacts, ascending, so a live posting wins and
    delivery recency only breaks its ties (D-432).
    """
    winners: dict[int, Row[Any]] = {}
    for row in rows:
        if row.job_id is None:
            continue
        job_id = int(row.job_id)
        if job_id not in job_ids:
            continue
        incumbent = winners.get(job_id)
        if incumbent is None or _supersedes(row, incumbent):
            winners[job_id] = row
    return winners


def _delivered_by_posting(rows: Sequence[Row[Any]]) -> dict[int, Row[Any]]:
    """The same deliveries keyed by POSTING, most recent artifact per posting winning.

    `rows` is ascending, so plain assignment keeps the latest delivery for each posting — which is
    the one `queue_detail` resolves for that posting id, so the applied page and the detail pane
    cannot name two different résumés for one requisition.
    """
    return {int(row.posting_id): row for row in rows if row.job_id is not None}


def _applied_versions(conn: Connection) -> dict[int, int]:
    """application_id -> the posting its `posting_version_id` names, for the rows that name one.

    `applications.posting_version_id` records the version the application was MADE against
    (`mark_job_applied`, comment A4), and it is the only column that says WHICH of a job's
    postings the owner actually applied to. An INNER join, so a NULL column and a version row
    that has since gone are both simply absent here rather than a None to test for.

    A join OUTWARD from `applications` — a handful of rows per job the owner acted on — and never
    an `.in_()` over an id list, per this module's rule.
    """
    rows = conn.execute(
        select(applications.c.id, posting_versions.c.posting_id).join(
            posting_versions, applications.c.posting_version_id == posting_versions.c.id
        )
    ).all()
    return {int(row.id): int(row.posting_id) for row in rows}


def _applied_postings(conn: Connection) -> dict[int, Row[Any]]:
    """One posting per job that carries an application, chosen by `_supersedes` as usual.

    Reached by a JOIN OUTWARD from `applications` — one row per job the owner acted on — and
    never by binding a job-id list. This module builds no `.in_()` of its own: the two reads that
    do take an id list hand it to `store/param_chunks.py`, and a list bound here would have none
    of that protection. `tests/unit/test_delivery_queries.py` asserts the absence.

    Computed for EVERY applied job, the delivered ones included, because that is what the join
    shape costs. `applied_rows` prefers the delivered posting wherever there is one, so those rows
    are resolved and never read.

    Ascending by `first_seen_at`, so `_supersedes`' liveness tie falls through to the most
    recently seen posting.
    """
    winners: dict[int, Row[Any]] = {}
    rows = conn.execute(
        _job_posting_select()
        .join(applications, applications.c.job_id == postings.c.job_id)
        .order_by(postings.c.first_seen_at, postings.c.id)
    ).all()
    for row in rows:
        job_id = int(row.job_id)
        incumbent = winners.get(job_id)
        if incumbent is None or _supersedes(row, incumbent):
            winners[job_id] = row
    return winners


def _mark_sources(conn: Connection) -> dict[int, str]:
    """Where each application's CURRENT state came from, out of `application_events.source`.

    `applications` carries no source column; the event log does, and the LAST event for an
    application is the one that put it in the state it is in ("web", "import", "user"). The
    highest `id` wins because `mark_job_applied` appends nothing on a re-POST — the event that set
    the state is still the last one written.

    The whole log, unfiltered and unbound, for the reason `applied_job_ids` gives about
    `applications` itself: it holds a handful of rows per job the owner acted on and cannot
    outgrow the shortlist it is read beside. No `.in_()`, per this module's rule.
    """
    rows = conn.execute(
        select(application_events.c.application_id, application_events.c.source).order_by(
            application_events.c.application_id, application_events.c.id
        )
    ).all()
    return {int(row.application_id): str(row.source) for row in rows}


def applied_rows(conn: Connection) -> list[AppliedRow]:
    """Every application attempt the store holds, newest first, with what it was made against.

    EVERY attempt, at every status — including `withdrawn`. A withdrawal is what the page's own
    unmark writes (`mark_job_unapplied`), so dropping those rows would make the undo look like a
    delete, and `withdrawn` is the documented drain rather than an erasure.

    Ordered by `submitted_at` falling back to `created_at`: the first is WHEN the application was
    made and is what the owner is looking for, and it is NULL for an attempt still at
    `interested`, where when boardwatch learned of it is the only date there is.

    The whole table, unfiltered, for the reason `applied_job_ids` gives: `applications` holds one
    row per job the owner acted on, so it cannot outgrow the shortlist it is read beside.
    """
    rows = conn.execute(
        select(applications).order_by(
            func.coalesce(applications.c.submitted_at, applications.c.created_at).desc(),
            applications.c.id.desc(),
        )
    ).all()
    if not rows:
        return []
    deliveries = _deliveries(conn)
    delivered = _delivered_winners(deliveries, {int(row.job_id) for row in rows})
    by_posting = _delivered_by_posting(deliveries)
    applied_against = _applied_versions(conn)
    fallback = _applied_postings(conn)
    sources = _mark_sources(conn)
    # The attempt `mark_job_unapplied` would reach for each job: `get_applications` orders by
    # `attempt_no` and takes the last, so this is that same row named here rather than re-derived
    # from the delivery order, which is not the same ordering.
    latest_attempt: dict[int, tuple[int, int]] = {}
    for row in rows:
        job_id = int(row.job_id)
        incumbent = latest_attempt.get(job_id)
        if incumbent is None or int(row.attempt_no) > incumbent[0]:
            latest_attempt[job_id] = (int(row.attempt_no), int(row.id))
    built: list[AppliedRow] = []
    for row in rows:
        job_id = int(row.job_id)
        # The posting the application NAMES, where it names one that was delivered for this same
        # job. It beats `_supersedes`' choice because the two answer different questions: the
        # queue's rule prefers a LIVE posting, which is right for finding work and wrong for
        # reporting an application made against a sibling the employer has since taken down. The
        # same-job check is what keeps a regrouped or mis-linked version from pulling in another
        # job's requisition, and the delivered-only check is what keeps `posting_id` an id every
        # existing web control can act on.
        named = by_posting.get(applied_against.get(int(row.id), -1))
        posting = named if named is not None and int(named.job_id) == job_id else None
        if posting is None:
            posting = delivered.get(job_id)
        built.append(
            _applied_row(
                row,
                posting if posting is not None else fallback.get(job_id),
                delivered=posting is not None,
                source=sources.get(int(row.id)),
                can_unmark=(
                    posting is not None
                    and str(row.status) in APPLIED_STATUSES
                    and latest_attempt[job_id][1] == int(row.id)
                ),
            )
        )
    return built


def queue_detail(conn: Connection, posting_id: int) -> QueueDetail | None:
    """One delivered lead in full, or None when `posting_id` has no tailored artifact.

    Deliberately NOT filtered by applied/skipped: the queue page offers an undo on both, so the
    detail of a lead that just left the list still has to be readable.

    `jd_body` comes from `posting_versions.body_text` via `current_posting_versions`, never from
    `postings.body_text`, which `scan/apply.py` rewrites in place — a stored span garbles the
    instant it is sliced from the rewritten string. A live lane-body quarantine suppresses that
    current version's body, and `jd_absent_reason` records why. `requirements` come from
    `load_audit`, which performs that slicing; it is not reimplemented here.
    """
    row = conn.execute(
        _delivered_select()
        .where(postings.c.id == posting_id)
        .order_by(artifacts.c.created_at.desc(), artifacts.c.id.desc())
        .limit(1)
    ).one_or_none()
    if row is None or row.job_id is None:
        return None

    settings = load_settings()
    identity = current_identity(conn, settings)
    profile_hash, rules_hash = identity if identity is not None else (None, None)

    version = current_posting_versions(conn, [posting_id]).get(posting_id)
    # Keep this fact read on the same connection and in this detail read as the version lookup;
    # opening a later connection would let the body and its quarantine status come from different
    # SQLite snapshots.
    quarantined = version is not None and is_quarantined(conn, version.posting_version_id)
    version_ids = [] if version is None else [version.posting_version_id]
    verdicts = current_verdicts(conn, version_ids, profile_hash, rules_hash)
    # T127. The requirement summary from the SAME evaluation as the verdict one line up, exactly as
    # `delivered_unapplied` reads it. Without it the pane fell back to `NO_REQUIREMENT_FLAGS` and
    # served `apply` for a lead the LIST held as `no_requirements_found` -- 12 of 833 standing leads
    # on 2026-09-22, and ~345 before that day's re-judge, since a re-key strands every judge
    # `eligible` that releases the hold.
    flags = current_requirement_flags(conn, version_ids, profile_hash, rules_hash)
    # The FINAL GATE's verdict, through the same read, on the same version, under the same facts,
    # judge and catalog as `delivered_unapplied`'s, so the pane and the list row for one lead
    # cannot report two different gate readings. Without it here the detail served `None` for a
    # lead the list served `uncertain` — the same field, the same lead, two answers. The catalog
    # is loaded once and serves this read and the audit below.
    facts = current_facts(conn)
    catalog = load_rules(settings.config_dir)
    gate = current_gate_verdicts(conn, version_ids, facts, catalog, model=settings.gate.model)
    # The gate's SENIORITY reading, for the same reason its verdict one line up is read here, and
    # missed when that one was added. Two things went wrong without it, and the second is the
    # worse one. `delivery/api.py` keys the above-band badge on `row.judge_seniority_fit == "no"`,
    # so the pane's badge was dead. And `_row_json` feeds the reading into `review_gate.classify`,
    # so a lead the LIST holds as `seniority_judged_above_band` read `review_reason: None` in
    # the PANE -- measured, not inferred. Not two different answers: the pane reported NO HOLD on
    # the surface where the reader decides whether to apply.
    #
    # Gated on the flag HERE and nowhere else on this side, exactly as
    # `delivered_unapplied` gates it: every consumer reads `judge_seniority_fit == "no"` and the
    # inert `"unclear"` default is what keeps them agreeing (D-332). `settings` is already bound
    # above, so this needs no second `load_settings()`.
    seniority = (
        current_gate_seniority(conn, version_ids, facts, model=settings.gate.model)
        if settings.gate.seniority_hold
        else {}
    )
    audit = load_audit(
        conn,
        posting_id,
        catalog,
        profile_hash=profile_hash,
        rules_hash=rules_hash,
    )
    provenance = lead_provenance(conn, [posting_id]).get(posting_id)
    # T91, read HERE for the reason the gate verdict one line up is: `delivered_unapplied` carries
    # it for every list row, and without it the pane served `null` for a lead the list held for
    # `form_question_hard_stop` -- the same field, the same lead, two answers, and the pane is the
    # surface where the reader decides. Same function, so the quote and the hold cannot differ.
    form_questions = form_question_hits(conn, {} if version is None else {posting_id: version})
    # T119, read HERE for the reason every fact above it is, and this file records three separate
    # times what happens when one is missed: the pane published `review_reason: null` for a lead
    # the LIST held, on the surface where the reader decides whether to apply. `row.job_id` is
    # non-`None` by the guard at the top of this function.
    revised = revised_since_build_ids(conn, {posting_id: int(row.job_id)}, now=utcnow())
    return QueueDetail(
        row=_queue_row(
            row,
            verdict=verdicts.get(posting_id),
            now=utcnow(),
            requirement_flags=flags.get(posting_id, NO_REQUIREMENT_FLAGS),
            judge_verdict=gate.get(posting_id),
            judge_seniority_fit=seniority.get(posting_id, "unclear"),
            form_question_hit=form_questions.get(posting_id),
            # T109, read HERE for the reason the gate verdict and the form question above are:
            # `delivered_unapplied` carries it for every list row, and without it the pane
            # reported no hold for a lead the LIST holds as `seniority_above_band` -- the same
            # field, the same lead, two answers, on the surface where the reader decides.
            band=_title_band(conn, settings),
            revised_since_build=posting_id in revised,
        ),
        jd_body=None if version is None or quarantined else version.body_text,
        jd_absent_reason=(
            JD_ABSENT_NO_CURRENT_VERSION
            if version is None
            else JD_ABSENT_QUARANTINED
            if quarantined
            else None
        ),
        requirements=[] if audit is None else list(audit.requirements),
        board_target=(
            None
            if provenance is None
            else f"{provenance.provider}:{provenance.board_slug}"
        ),
    )


__all__ = [
    "REMOTE_POLICY_UNKNOWN",
    "STATUS_CLOSED",
    "STATUS_UNVERIFIABLE",
    "TARGET_TAG",
    "AppliedRow",
    "QueueDetail",
    "QueueRow",
    "RequirementView",
    "applied_rows",
    "closed_job_ids",
    "delivered_unapplied",
    "ineligible_job_ids",
    "lane_decision",
    "queue_detail",
    "standing_lead_job_ids",
    "standing_slate_keys",
]
