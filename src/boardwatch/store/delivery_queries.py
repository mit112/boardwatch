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
- **`jd_body` is `None`, never `""`, when the posting has no current version.** An empty body and
  an absent body are different claims. The two existing callers disagree — `eligibility/audit.py`
  tolerates the case, `projection/posting.py` raises — and this module tolerates it, because a
  detail request that raises would take a whole page down over one missing row.
- **`verdict` is `None` when nothing was evaluated.** It comes from
  `eligibility/read.current_verdicts`, the existing identity-scoped read, so a corrected fact or
  policy is reflected the moment its re-evaluation lands. No default is invented for the
  unevaluated case.
- **`status` is `unverifiable`, not `open`, when nothing enumerates the company's board.**
  `postings.status` is a two-valued column and stays one; the third state is derived HERE, at the
  read boundary, and no consumer of the column sees it (D-324).

**Deduplication is by canonical job, not by posting** (design §6.1). Measured on the live store: 227
postings fall into 100 multi-posting job groups, and `applications` keys on `job_id`, so a posting
whose sibling was applied to must not reappear. One entry per job, showing the most recently
delivered posting.

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

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, Row, Select, func, select

from boardwatch.core.clock import utcnow
from boardwatch.core.settings import load_settings
from boardwatch.eligibility.audit import AuditRequirement, load_audit
from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.preflight import current_identity
from boardwatch.eligibility.read import current_verdicts
from boardwatch.store.applications import applied_job_ids
from boardwatch.store.queries import current_posting_versions
from boardwatch.store.run_funnel_queries import TAILORED_KIND, lead_provenance
from boardwatch.store.tables import artifacts, companies, posting_versions, postings

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

#: The one `companies.tags_json` entry this module reads. Nothing in `src/` writes that column
#: today, so `target_flag` is `None` for every company on the live store; it is tri-state so that
#: "this company carries no tags at all" can never render as "this company is not a target".
TARGET_TAG = "target"


@dataclass(frozen=True)
class QueueRow:
    posting_id: int
    job_id: int
    title: str
    company: str
    location: str | None
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


@dataclass(frozen=True)
class QueueDetail:
    row: QueueRow
    jd_body: str | None
    requirements: list[RequirementView]
    board_target: str | None


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
            postings.c.url,
            companies.c.name.label("company"),
            companies.c.tags_json,
            companies.c.watched,
        )
        .join(posting_versions, artifacts.c.posting_version_id == posting_versions.c.id)
        .join(postings, posting_versions.c.posting_id == postings.c.id)
        .join(companies, postings.c.company_id == companies.c.id)
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


def _status(status: object, watched: object) -> str:
    """`open` only where a board is actually enumerated; otherwise `unverifiable` (D-314).

    `_process_missing` is the sole writer of `closed` and it runs on `complete` snapshots only,
    so `closed` is always a real measurement and passes through untouched — including on a
    company that has since been unwatched. `open`, by contrast, is only ever the ABSENCE of a
    close, and for a company nobody enumerates no scan can ever produce one: the posting was
    never measured as still listed, merely never contradicted. Probing 45 such rows found 40
    alive and 0 dead, so this is not "probably gone" either — it is not known.

    Keyed on `companies.watched`, which is the literal question ("does anything enumerate this
    board?"), and NOT on `source='lane'`. Measured on the live store 2026-08-27: 274 of the 722
    affected rows are on `source='user'` companies, and 23 lane-acquired postings sit on watched
    companies where `open` IS a measurement. The source predicate is wrong in both directions.
    """
    return STATUS_UNVERIFIABLE if str(status) == "open" and not watched else str(status)


def _queue_row(row: Row[Any], *, verdict: str | None, now: datetime) -> QueueRow:
    return QueueRow(
        posting_id=int(row.posting_id),
        job_id=int(row.job_id),
        title=str(row.title),
        company=str(row.company),
        location=_location(row.locations_json),
        remote_policy=(
            None if row.remote_policy == REMOTE_POLICY_UNKNOWN else str(row.remote_policy)
        ),
        posted_days=_posted_days(row.posted_at, now),
        first_seen=row.first_seen_at,
        status=_status(row.status, row.watched),
        verdict=verdict,
        apply_url=str(row.url) if row.url is not None else None,
        delivered_run_id=(
            int(row.delivered_run_id) if row.delivered_run_id is not None else None
        ),
        tex_uri=str(row.tex_uri),
        pdf_uri=str(row.pdf_uri) if row.pdf_uri is not None else None,
        target_flag=_target_flag(row.tags_json),
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

    Ordered most recently delivered first. Callers that want it ranked re-rank it; the store does
    not recompute a score (design §6.2 — score and coverage are recomputed live, never persisted).
    """
    applied = applied_job_ids(conn)
    # Ascending, so the LAST row written into `winners` for a job is its most recent delivery.
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
        winners[job_id] = row

    ordered = sorted(
        winners.values(), key=lambda row: (row.delivered_at, int(row.artifact_id)), reverse=True
    )
    # Both reads chunk internally past the bound-parameter cap, and the list handed to them is
    # bounded by the artifact count rather than by the open corpus.
    versions = current_posting_versions(conn, [int(row.posting_id) for row in ordered])
    profile_hash, rules_hash = _identity(conn)
    verdicts = current_verdicts(
        conn,
        [version.posting_version_id for version in versions.values()],
        profile_hash,
        rules_hash,
    )
    now = utcnow()
    return [
        _queue_row(row, verdict=verdicts.get(int(row.posting_id)), now=now) for row in ordered
    ]


def queue_detail(conn: Connection, posting_id: int) -> QueueDetail | None:
    """One delivered lead in full, or None when `posting_id` has no tailored artifact.

    Deliberately NOT filtered by applied/skipped: the queue page offers an undo on both, so the
    detail of a lead that just left the list still has to be readable.

    `jd_body` comes from `posting_versions.body_text` via `current_posting_versions`, never from
    `postings.body_text`, which `scan/apply.py` rewrites in place — a stored span garbles the
    instant it is sliced from the rewritten string. `requirements` come from `load_audit`, which
    performs that slicing; it is not reimplemented here.
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
    verdicts = current_verdicts(
        conn,
        [] if version is None else [version.posting_version_id],
        profile_hash,
        rules_hash,
    )
    audit = load_audit(
        conn,
        posting_id,
        load_rules(settings.config_dir),
        profile_hash=profile_hash,
        rules_hash=rules_hash,
    )
    provenance = lead_provenance(conn, [posting_id]).get(posting_id)
    return QueueDetail(
        row=_queue_row(row, verdict=verdicts.get(posting_id), now=utcnow()),
        jd_body=None if version is None else version.body_text,
        requirements=[] if audit is None else list(audit.requirements),
        board_target=(
            None
            if provenance is None
            else f"{provenance.provider}:{provenance.board_slug}"
        ),
    )


__all__ = [
    "REMOTE_POLICY_UNKNOWN",
    "STATUS_UNVERIFIABLE",
    "TARGET_TAG",
    "QueueDetail",
    "QueueRow",
    "RequirementView",
    "delivered_unapplied",
    "ineligible_job_ids",
    "queue_detail",
]
