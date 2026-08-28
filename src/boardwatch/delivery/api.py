"""JSON payloads for the local review app (design §7.1). No HTTP, no sockets, no logging.

`server.py` owns the socket, the token and the headers; this module owns the answers. The split
is what makes the payload rules testable without a listener, and it is also what keeps both halves
honest about their own responsibilities: nothing here writes a status code, and nothing in
`server.py` decides what a field means.

**Nothing here calls `rank_open_postings`.** That function is a writer three times over — it runs
the extraction preflight, inserts eligibility evaluations, and mints a `runs` row through
`ensure_run` — so a page load reaching it would create a phantom run every time the browser
refreshed (design §6.3), the automated form of the empty run already sitting in the live store.
The pieces of it this module needs are the *pure* ones, called directly: `score_posting`,
`why_summary`, `role_verdict` and `coverage_report`. Everything else here is a select.

Four fields are computed live rather than read, and each is labelled "as of now" in the UI because
that is what it is (design §6.2):

* `score` and `why` — `rank/heuristic.score_posting` over the profile and the posting's stored
  taxonomy extraction. Never persisted, so for a lead delivered three days ago this is the current
  answer and not the run's. **No extraction is created here.** `show` calls `run_preflight` before
  scoring; that writes, so this reads whatever extraction the last run left and scores without one
  when there is none, which the ranker already has a defined answer for (a neutral coverage prior).
* `coverage` — `tailor/coverage.coverage_report` over the frozen JD body and the MASTER résumé.
  Its `fraction` is `None` over an empty denominator, which is exactly the thin-JD case, so
  `thin_jd` is derived from it rather than from a second opinion about what a thin JD is. The JD
  half of it is memoized per `posting_version_id` (`_TermCache`); it is the one expensive thing
  on the render path and, the version table being append-only, the one thing that cannot change.
* `off_target` / `off_target_reason` — `rank/role_gate.role_verdict`, which returns the text it
  matched. That string is the whole point: a veto that cannot be traced to the words that caused
  it is not auditable, and re-deriving "off target" from a title pattern written here would be a
  second, wrong opinion about a shipped gate.

`off_target` is `not_swe` only, never `uncertain`. About a third of the delivered set classifies
`uncertain` (design §6.4: 69 of 220) and `uncertain` is not a veto — badging it "off target"
would assert a decision the gate declined to make, which is the same error as folding an abstain
into a neighbour.

`review_reason` is therefore a SEPARATE field and `off_target` must never be stretched to stand in
for it. It names which of `review_gate.ReviewReason`'s four members held the lead, and it comes
from `review_gate.classify` — the same call `lane` projects, so the reason on a row and the lane
the row arrived in are one decision and cannot disagree (D-332). It is `None` for every apply-lane
row, which makes `review_reason is not None` and "this row came in `review`" the same statement.
The two fields answer different questions: `off_target` is `not_swe` alone, while the lane also
holds a confirmed non-US location and a title the role gate merely could not call software, so
most review leads carry a reason and no badge.

`rank` is deliberately not a field. The rows arrive ordered, so rank is the array position; a
field for it could disagree with the order it describes.

**Two names are imported private from `delivery/queue.py`** — `_index` and `_identity_hash`. Both
are the queue's own answer to a question this module has to ask (which folder is this lead's, and
what is this lead's stable identity), and re-deriving either here would put a second opinion
against the module that writes the folders. `_index` in particular identifies a folder by the
`posting_id` inside its `details.json` and never by its name, which is design §4.1's rule; a
reimplementation that globbed for a planned name would break the moment the owner renamed a
folder, and would break silently.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import threading
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, Row, and_, func, select

from boardwatch.core.clock import utcnow
from boardwatch.core.settings import Settings
from boardwatch.delivery.answers import (
    IDENTITY_FIELDS,
    RESUME_FILENAME,
    WORK_AUTH_FIELDS,
    AnswersPanel,
    load_answers,
)
from boardwatch.delivery.names import NameBudgetError, plan_lead_names
from boardwatch.delivery.queue import _identity_hash, _index
from boardwatch.delivery.review_gate import classify, lane
from boardwatch.extract.taxonomy import Taxonomy, TaxonomyError, load_taxonomy
from boardwatch.projection.errors import ProjectionError
from boardwatch.projection.shell import load_shell
from boardwatch.rank.explain import why_summary
from boardwatch.rank.heuristic import profile_view_from_row, score_posting
from boardwatch.rank.role_gate import role_verdict
from boardwatch.store.applications import applied_job_ids
from boardwatch.store.delivery_queries import (
    QueueDetail,
    QueueRow,
    delivered_unapplied,
    queue_detail,
)
from boardwatch.store.param_chunks import id_chunks
from boardwatch.store.queries import CurrentVersion, current_posting_versions, get_profile
from boardwatch.store.queue_state import skipped_job_ids
from boardwatch.store.run_funnel_queries import TAILORED_KIND
from boardwatch.store.tables import artifacts, extractions, postings, runs
from boardwatch.tailor.coverage import (
    CoverageReport,
    coverage_report,
    coverage_to_dict,
    requirement_terms,
    resume_fact_skills,
)
from boardwatch.tailor.load import ResumeLoadError, load_resume

#: `extractions.kind` for the taxonomy pass, as every other reader spells it
#: (`cli/show_cmd.py`, `cli/top_cmd.py`, `reports/notify.py`).
TAXONOMY_KIND = "taxonomy"

#: How many runs the runs page offers. The picker is for "which recent run", not an archive.
RUNS_LIMIT = 20

#: Hard cap on the `requirement_terms` memo below. The queue renders a few hundred rows and grows
#: by tens a day, so this is ample — and it is a CAP rather than an absence of one because an
#: unbounded dict over a corpus that grows every day is a leak on a slow fuse, not a cache.
TERM_CACHE_MAX = 5_000

#: Last resort for the owner's name, used only in the PDF's download filename. Never a person's
#: name: a hardcoded one would be wrong for every user but one (CLAUDE.md, multi-tenancy).
FALLBACK_OWNER_NAME = "owner"

#: One `subprocess.run` argv per platform, or nothing. Shape taken from `notify/desktop.py`,
#: including the injectable runner, so no test spawns a real file manager.
Runner = Callable[[list[str]], int]

#: One memo generation's identity: the store whose `posting_version_id`s the entries are keyed on,
#: the taxonomy version that parsed the bodies, and the master résumé's fingerprint. NOT part of
#: any entry's key — see `_TermCache`. The store is in here because a version id is only unique
#: WITHIN a store: one process serves one data dir, but the test suite builds a fresh store per
#: test in a single process, and there id 1 means a different body every time.
CacheIdentity = tuple[str, str, str]


@dataclass(frozen=True)
class ApiContext:
    """Everything the payload functions need that is not the connection.

    `out_root` and `queue_root` are separate and both resolved: the applications root holds the
    canonical PDFs and the per-run funnels, the queue root holds the copies. A path is checked for
    containment under whichever of the two it is supposed to be inside, never under "a root".
    """

    settings: Settings
    out_root: Path
    queue_root: Path
    owner_name: str
    platform: str


@dataclass(frozen=True)
class LiveFacts:
    """What was recomputed for one lead at request time. Every field is "as of now"."""

    score: float | None
    why: str | None
    coverage: CoverageReport | None
    role: str
    role_reason: str


class PdfIssue(StrEnum):
    """Why a PDF cannot be served. Typed at the return site so `server.py` maps an issue to a
    status code instead of matching prose, and so `OUTSIDE_ROOT` can never be reported as an
    ordinary absence — a path escaping the output root is a refusal, not a missing file."""

    NO_LEAD = "no_lead"
    NO_PDF = "no_pdf"
    OUTSIDE_ROOT = "outside_root"
    MISSING_FILE = "missing_file"


@dataclass(frozen=True)
class PdfFile:
    """A PDF that resolved, exists, and is contained under the applications root."""

    path: Path
    filename: str


# ------------------------------------------------------------------------------------- the queue


def queue_payload(conn: Connection, ctx: ApiContext) -> dict[str, Any]:
    """`GET /api/queue`: every delivered, unapplied, unskipped, non-ineligible lead, ranked now,
    split into the APPLY lane (`rows`) and the REVIEW lane (`review`).

    The split is `delivery.review_gate.lane`, the same single definition the folder tree uses
    (D-332), so `rows` holds exactly what `~/boardwatch-queue`'s top level holds and `review`
    holds exactly what `_review` holds. `rows` is therefore a blind-apply list and says so.

    Ineligible leads are excluded from BOTH and reported in `counts.ineligible` instead. Their
    folders drain to `_ineligible`, so listing them here would make the page and the folder tree
    disagree about the same lead. A review lead is the opposite case and is NOT excluded: it is
    work to look at, so it is listed under its own key rather than hidden.

    Ranked here rather than in the store because the score is not persisted (design §6.2). The
    sort is stable, so leads that score equally — and every lead when there is no profile to score
    against — keep `delivered_unapplied`'s most-recent-delivery-first order rather than an
    arbitrary one.
    """
    every = delivered_unapplied(conn, skipped=set(skipped_job_ids(conn)))
    # An ineligible lead is not work: it is drained to `_ineligible` on disk, so the page must
    # not list it either, or the folder tree and the page disagree about the same lead. It is
    # COUNTED though — see `_counts`. Silently dropping rows from a report is the failure this
    # repository treats an unreported abstain as.
    kept = [row for row in every if row.verdict != "ineligible"]
    drained = len(every) - len(kept)
    facts = _live_facts(conn, ctx, kept)

    def rank_key(row: QueueRow) -> tuple[bool, float]:
        return (facts[row.posting_id].score is None, -(facts[row.posting_id].score or 0.0))

    # The SAME split the folder tree uses, from the SAME function (D-332). Calling
    # `review_gate.lane` rather than re-deriving "is this appliable" here is the whole point: a
    # second opinion in this module is how the page and the drain start disagreeing about one
    # lead, which is the defect `_ineligible` and `_review` both exist to prevent.
    apply_rows = sorted(
        (r for r in kept if lane(verdict=r.verdict, locations=r.locations, title=r.title) == ""),
        key=rank_key,
    )
    review_rows = sorted(
        (r for r in kept if lane(verdict=r.verdict, locations=r.locations, title=r.title) != ""),
        key=rank_key,
    )
    return {
        "rows": [_row_json(row, facts[row.posting_id], ctx) for row in apply_rows],
        # Its own list, NOT an exclusion. These leads are real work — they are held for a look
        # rather than blind-applied — so dropping them from the payload would hide ~30% of the
        # delivered set behind a folder the page never mentions. `off_target` cannot stand in for
        # this: it is `not_swe` ONLY, never `uncertain` (see this module's docstring), so most
        # review leads carry no flag at all and were previously indistinguishable on the page.
        "review": [_row_json(row, facts[row.posting_id], ctx) for row in review_rows],
        "counts": _counts(conn, apply_rows, ineligible=drained, review=len(review_rows)),
        # A capability flag, not a preference: the button is hidden where the platform has no
        # file-manager handler, because a control that can only fail is worse than no control.
        "meta": {"reveal_supported": reveal_supported(ctx.platform)},
    }


def detail_payload(conn: Connection, ctx: ApiContext, posting_id: int) -> dict[str, Any] | None:
    """`GET /api/queue/<id>`: one lead in full, or None when nothing was ever delivered for it.

    A posting with **no current version** returns the detail with `jd_body: null` rather than
    raising. The two existing callers disagree here (`eligibility/audit.py` tolerates,
    `projection/posting.py` raises) and the API picks tolerate and says so, because a detail
    request that raised would take a whole page down over one missing row.
    """
    detail = queue_detail(conn, posting_id)
    if detail is None:
        return None
    facts = _live_facts(conn, ctx, [detail.row])[detail.row.posting_id]
    return {
        "row": _row_json(detail.row, facts, ctx),
        "jd_body": detail.jd_body,
        "requirements": _requirements_json(detail, facts),
        "board_target": detail.board_target,
    }


def _row_json(row: QueueRow, facts: LiveFacts, ctx: ApiContext) -> dict[str, Any]:
    """One `QueueRow` as the frontend's `QueueRow` interface.

    `coverage` is the fraction, matching the client that is already written against it, and the
    covered/missing lists travel beside it as `coverage_detail` through `coverage_to_dict` — the
    serializer the funnel artifact already uses, so the two surfaces cannot drift apart.

    `thin_jd` is `fraction is None`, which is true both for a JD carrying no recognised
    requirement at all and for a store with no master résumé to measure against. Both are
    literally "no coverage fraction could be computed", which is what the badge says.

    `review_reason` is on EVERY row rather than only on the review list, because `detail_payload`
    serializes one row with no list around it — a field that existed only inside `review` would be
    absent exactly where the pane has to explain why the lead is held.
    """
    fraction = None if facts.coverage is None else facts.coverage.fraction
    off_target = facts.role == "not_swe"
    # From `classify`, which `lane` is a projection of, so this row's reason and the list it was
    # sorted into are the SAME decision rather than two that agree today. `None` on an apply-lane
    # row by construction: `classify` returns a reason only where it returns `REVIEW_DIR`.
    held = classify(verdict=row.verdict, locations=row.locations, title=row.title).reason
    pdf = _pdf_path(row.pdf_uri, ctx.out_root)
    return {
        "posting_id": row.posting_id,
        "job_id": row.job_id,
        "title": row.title,
        "company": row.company,
        "location": row.location,
        "remote_policy": row.remote_policy,
        "posted_days": row.posted_days,
        "first_seen": row.first_seen.isoformat(),
        "status": row.status,
        "verdict": row.verdict,
        "apply_url": row.apply_url,
        "delivered_run_id": row.delivered_run_id,
        "tex_uri": row.tex_uri,
        "pdf_uri": row.pdf_uri,
        "target_flag": row.target_flag,
        "thin_jd": fraction is None,
        "off_target": off_target,
        "off_target_reason": facts.role_reason if off_target else None,
        "review_reason": held,
        "pdf_available": pdf is not None,
        "score": facts.score,
        "why": facts.why,
        "coverage": fraction,
        "coverage_detail": coverage_to_dict(facts.coverage),
    }


def _requirements_json(detail: QueueDetail, facts: LiveFacts) -> list[dict[str, Any]]:
    """The audit's requirement rows, plus the coverage terms, as one list.

    Two different questions share one shape here on purpose, and the `rule` field is what tells
    them apart: a row carrying a `rule` is eligibility evidence (which rule disposed of which
    requirement, against which profile field, quoting which span of the FROZEN version), and a row
    without one is a résumé-coverage term. `covered` therefore means "met" for the first kind and
    "present in the master résumé" for the second.

    `profile_field` is the locator the resolver recorded (`{"field": "facts.<name>"}`), taken from
    the first support row. A requirement with no support has no field to name and gets `None`
    rather than a guess.
    """
    entries: list[dict[str, Any]] = []
    for req in detail.requirements:
        entries.append(
            {
                "requirement": req.label,
                "covered": req.disposition == "met",
                "rule": req.rule_id,
                "disposition": req.disposition,
                "profile_field": next(
                    (
                        str(sup.profile_locator["field"])
                        for sup in req.support
                        if "field" in sup.profile_locator
                    ),
                    None,
                ),
                # Sliced from the immutable `posting_versions.body_text` by `load_audit`, so it
                # is rendered as text by the client and never as markup.
                "quote": req.quote or None,
                "rationale": req.rationale,
            }
        )
    if facts.coverage is not None:
        for term in facts.coverage.covered:
            entries.append(_coverage_entry(term, covered=True))
        for term in facts.coverage.missing:
            entries.append(_coverage_entry(term, covered=False))
    return entries


def _coverage_entry(term: str, *, covered: bool) -> dict[str, Any]:
    return {
        "requirement": term,
        "covered": covered,
        "rule": None,
        "disposition": None,
        "profile_field": None,
        "quote": None,
        "rationale": None,
    }


def _counts(
    conn: Connection, rows: Sequence[QueueRow], *, ineligible: int = 0, review: int = 0
) -> dict[str, Any]:
    """The status band. `uncertain` is its own bucket and is NEVER summed into `eligible`.

    `rows` here is the APPLY lane, so `in_queue` counts what is blindly appliable; `review` and
    `ineligible` are passed in because neither is in `rows` and both would otherwise be an
    unexplained remainder between `in_queue` and the delivered set.

    That is the same rule the repository applies to every other report: an abstain is never folded
    into either neighbour, and a page is a report. `eligible` is the affirmatively-eligible count
    and is the headline yield; a row whose verdict is `None` (nothing evaluated) is in neither.

    `applied_ever`, not applied-today. With zero applications ever recorded the two are
    indistinguishable, and only the second says whether the tool works.
    """
    last = _last_finished_run(conn)
    return {
        "in_queue": len(rows),
        "eligible": sum(1 for row in rows if row.verdict == "eligible"),
        "uncertain": sum(1 for row in rows if row.verdict == "uncertain"),
        # Its OWN cell, never folded into either neighbour and never left as an unexplained
        # remainder. `in_queue` counts the work list, which excludes these, so the band now
        # reconciles: in_queue == eligible + uncertain + (rows with no verdict yet).
        "ineligible": ineligible,
        # Held for a look, not rejected and not blind-appliable. Its own cell for the same reason
        # `ineligible` has one: `in_queue` counts the apply lane, so without this the difference
        # between the apply lane and the delivered set is an unexplained remainder.
        "review": review,
        "applied_ever": len(applied_job_ids(conn)),
        "skipped": len(skipped_job_ids(conn)),
        "delivered_last_run": (
            0
            if last is None
            else sum(1 for row in rows if row.delivered_run_id == int(last.id))
        ),
        "last_run_finished": (
            None if last is None or last.finished_at is None else last.finished_at.isoformat()
        ),
    }


def _last_finished_run(conn: Connection) -> Row[Any] | None:
    return conn.execute(
        select(runs)
        .where(runs.c.finished_at.is_not(None))
        .order_by(runs.c.id.desc())
        .limit(1)
    ).one_or_none()


# ------------------------------------------------------------------------ live score and coverage


def _live_facts(
    conn: Connection, ctx: ApiContext, rows: Sequence[QueueRow]
) -> dict[int, LiveFacts]:
    """Recompute score, why, coverage and the role verdict for every row, once per request.

    The taxonomy, the master résumé and the profile are each loaded ONE time for the whole set.
    The queue holds hundreds of leads and this runs on every render, so a per-row load would be
    hundreds of file reads and hundreds of `IN`-list statements.

    The per-body parse behind `coverage` is memoized in `_TERM_CACHE` across requests, which is
    where the render's cost actually was. The memo's identity is built once here for the same
    reason everything else on this path is loaded once: it is a per-request constant.
    """
    if not rows:
        return {}
    settings = ctx.settings
    now = utcnow()
    taxonomy = _taxonomy(settings.config_dir)
    resume_skills = _resume_skills(settings.config_dir, taxonomy)
    taxonomy_version = "" if taxonomy is None else taxonomy.version
    identity: CacheIdentity = (
        str(settings.data_dir),
        taxonomy_version,
        _resume_digest(resume_skills),
    )
    profile_row = get_profile(conn)
    profile = None if profile_row is None else profile_view_from_row(profile_row)
    posting_ids = [row.posting_id for row in rows]
    inputs = _posting_inputs(conn, posting_ids, taxonomy_version)
    versions = current_posting_versions(conn, posting_ids)

    facts: dict[int, LiveFacts] = {}
    for row in rows:
        role, role_reason = role_verdict(row.title)
        score: float | None = None
        why: str | None = None
        source = inputs.get(row.posting_id)
        if profile is not None and source is not None:
            scored = score_posting(
                profile,
                set((source.extraction or {}).get("skills", [])),
                str(source.title),
                source.posted_at,
                list(source.locations_json or []),
                str(source.remote_policy),
                settings.weights,
                now,
                settings.recency_half_life_days,
                settings.zero_skill_coverage_prior,
            )
            score = scored.total
            why = why_summary(scored, source.posted_at, now)
        version = versions.get(row.posting_id)
        facts[row.posting_id] = LiveFacts(
            score=score,
            why=why,
            coverage=(
                None
                if taxonomy is None or resume_skills is None or version is None
                else _coverage(version, taxonomy, resume_skills, identity)
            ),
            role=role,
            role_reason=role_reason,
        )
    return facts


def _posting_inputs(
    conn: Connection, posting_ids: Sequence[int], taxonomy_version: str
) -> dict[int, Row[Any]]:
    """The ranker's inputs for each posting, with its taxonomy extraction where one exists.

    Not reconstructed from `QueueRow`: that carries `posted_days` and a joined location string,
    both of which are presentation, and scoring off them would price recency to whole days and
    location fit against a re-split string. The columns the ranker actually reads are read.

    The extraction join is OUTER and is gated on the posting's CURRENT `content_hash`, exactly as
    every other reader gates it, so a stale extraction from a superseded body is not used. A
    posting with no usable extraction scores through the ranker's own zero-skill prior.

    Chunked by `id_chunks`, and `dict.update` is the correct merge because the chunked column is
    the key of the result — no aggregate crosses a chunk boundary.
    """
    resolved: dict[int, Row[Any]] = {}
    for chunk in id_chunks(list(posting_ids)):
        stmt = (
            select(
                postings.c.id,
                postings.c.title,
                postings.c.posted_at,
                postings.c.locations_json,
                postings.c.remote_policy,
                extractions.c.json.label("extraction"),
            )
            .outerjoin(
                extractions,
                and_(
                    extractions.c.posting_id == postings.c.id,
                    extractions.c.content_hash == postings.c.content_hash,
                    extractions.c.kind == TAXONOMY_KIND,
                    extractions.c.engine_version == taxonomy_version,
                ),
            )
            .where(postings.c.id.in_(chunk))
        )
        resolved.update({int(row.id): row for row in conn.execute(stmt).all()})
    return resolved


def _taxonomy(config_dir: Path) -> Taxonomy | None:
    """The taxonomy, or None when it cannot be loaded. A broken override costs the score and
    coverage columns, not the page."""
    try:
        return load_taxonomy(config_dir)
    except (TaxonomyError, OSError):
        return None


def _resume_skills(config_dir: Path, taxonomy: Taxonomy | None) -> frozenset[str] | None:
    """The MASTER résumé's canonical skills — the anti-echo denominator, never the tailored
    output — or None when there is no readable master résumé.

    None rather than an empty set: an empty set would compute a real-looking 0.00 coverage for
    every lead, and "your résumé covers none of this" is a very different claim from "there is no
    résumé here to measure".
    """
    if taxonomy is None:
        return None
    try:
        return resume_fact_skills(load_resume(config_dir / RESUME_FILENAME), taxonomy)
    except (ResumeLoadError, OSError):
        return None


def _resume_digest(resume_skills: frozenset[str] | None) -> str:
    """A stable fingerprint of the master résumé, as the coverage path actually consumes it.

    Over the canonical skill SET rather than the file's bytes, for two reasons. It is already
    loaded once per request, so no second read of `resume.yaml` is needed; and it is the exact
    résumé-side input to `coverage_report`, so two files that differ only in wording the taxonomy
    does not recognise cannot produce a different fingerprint — a reformatted résumé does not throw
    away a cache whose contents provably cannot change because of it.
    """
    return hashlib.sha256("\n".join(sorted(resume_skills or ())).encode("utf-8")).hexdigest()


class _TermCache:
    """In-process LRU memo of `requirement_terms`, keyed on `posting_version_id`.

    `GET /api/queue` re-parses every delivered JD body on every render. Measured against the live
    corpus that is ~3.6 ms per body over a queue of several hundred, so about two seconds of a page
    the owner opens daily, rising with the corpus. It is also *the same answer every time*:
    `posting_versions` is append-only, enforced by the `posting_versions_no_update` /
    `posting_versions_no_delete` triggers, so a given `posting_version_id` can never change its
    `body_text` and the parse of that body into canonical terms is a pure function of the id.

    The two inputs that CAN move — the taxonomy and the master résumé — are the cache's *identity*
    and not part of any entry's key. When either changes the whole memo is dropped, so a render can
    never mix terms parsed under two taxonomies. Keying each entry on all three instead would leave
    the superseded generation resident until eviction pushed it out, which is the same leak in
    slower motion.

    Only the PARSE is memoized, never the `CoverageReport`: the résumé side is a cheap set
    intersection, and caching the finished report would tie a lead's numbers to the résumé that
    happened to be on disk when its body was first seen.

    Locked because `ReviewServer` is a `ThreadingHTTPServer` and this is shared mutable state — two
    tabs, or one page's queue and detail requests, land here concurrently. `requirement_terms` runs
    OUTSIDE the lock so a slow parse never serializes the other threads; the cost is that two
    threads racing on one id may both parse it, which is a duplicate computation and not a wrong
    answer. The store re-checks the identity because the generation may have rolled while the parse
    was running, and a value parsed under the old taxonomy must not land in the new generation.
    """

    def __init__(self, max_entries: int = TERM_CACHE_MAX) -> None:
        self._max = max_entries
        self._lock = threading.Lock()
        self._identity: CacheIdentity | None = None
        self._entries: OrderedDict[int, tuple[frozenset[str], str]] = OrderedDict()

    def clear(self) -> None:
        """Drop every entry and the identity they were parsed under."""
        with self._lock:
            self._identity = None
            self._entries.clear()

    def terms(
        self, identity: CacheIdentity, taxonomy: Taxonomy, version: CurrentVersion
    ) -> tuple[frozenset[str], str]:
        with self._lock:
            if identity != self._identity:
                self._identity = identity
                self._entries.clear()
            hit = self._entries.get(version.posting_version_id)
            if hit is not None:
                self._entries.move_to_end(version.posting_version_id)
                return hit
        computed = requirement_terms(version.body_text, taxonomy)
        with self._lock:
            if identity == self._identity:
                self._entries[version.posting_version_id] = computed
                while len(self._entries) > self._max:
                    self._entries.popitem(last=False)
        return computed


#: One memo per process, shared by every request. Lives at module scope rather than on
#: `ApiContext` because that is rebuilt per launch and frozen, and a cache hanging off a
#: per-request value would never hit.
_TERM_CACHE = _TermCache()


def _coverage(
    version: CurrentVersion,
    taxonomy: Taxonomy,
    resume_skills: frozenset[str],
    identity: CacheIdentity,
) -> CoverageReport | None:
    """Keyword coverage for one JD, wrapped fail-safe exactly as `reports/tailor.py` wraps it: a
    measurement bug records `None` and never takes down the lead it was measuring."""
    try:
        jd_skills, denominator_source = _TERM_CACHE.terms(identity, taxonomy, version)
        return coverage_report(jd_skills, resume_skills, denominator_source)
    except Exception:  # noqa: BLE001 - a coverage-measurement bug must not drop a whole page
        return None


# ------------------------------------------------------------------------------ the answers panel


def answers_payload(conn: Connection, ctx: ApiContext) -> dict[str, Any]:
    """`GET /api/answers`. Never logged, anywhere, by anything on this path.

    Every catalog field is present, holding `null` where nothing resolved. `AnswersPanel.missing`
    names those fields and is carried through too, but a field silently absent from the mapping
    would render as a row the panel simply does not have — and a missing row is invisible, while
    an empty one is visibly empty. `missing` stays beside them so a reader has the list as well.
    """
    panel = load_answers(config_dir=ctx.settings.config_dir, conn=conn)
    return {
        "identity": {name: panel.identity.get(name) for name in IDENTITY_FIELDS},
        "work_auth": {name: panel.work_auth.get(name) for name in WORK_AUTH_FIELDS},
        # `AnswersPanel.education` is one rendered line per entry, read from the authored résumé
        # and never retyped. The client renders each entry as labelled key/value rows, so each
        # line travels as a single named field rather than being split into guessed parts.
        "education": [{"education": line} for line in panel.education],
        "questions": [
            {"q": question.q, "a": question.a, "note": question.note}
            for question in panel.questions
        ],
        "missing": list(panel.missing),
    }


def resolve_owner_name(conn: Connection | None, config_dir: Path) -> str:
    """The owner's name for the résumé filename, from their own data and never hardcoded.

    `answers.yaml`'s `identity.full_name` first, because it is the one place a name is a named
    field; then the authored résumé's header line, which `validate_master` already guarantees is
    non-blank when it loads at all. `FALLBACK_OWNER_NAME` is last so a first-run user with neither
    file still gets a working page with a generic filename.
    """
    try:
        panel: AnswersPanel = load_answers(config_dir=config_dir, conn=conn)
    except Exception:  # noqa: BLE001 - a malformed answers file must not block the whole app
        panel = AnswersPanel()
    named = panel.identity.get("full_name")
    if named:
        return named
    try:
        header, _education = load_shell(config_dir / RESUME_FILENAME)
    except ProjectionError:
        return FALLBACK_OWNER_NAME
    return header[0].strip() if header and header[0].strip() else FALLBACK_OWNER_NAME


# ---------------------------------------------------------------------------------------- the PDF


def resolve_pdf(conn: Connection, ctx: ApiContext, posting_id: int) -> PdfFile | PdfIssue:
    """The canonical PDF for one lead, or a typed refusal.

    **Containment is asserted, not assumed.** `artifacts.meta_json.pdf_uri` is a path this process
    wrote, but it is still a path out of the database being handed to `open()` on behalf of an
    HTTP request, so it is resolved and then required to sit under the applications root. Nothing
    outside that root is opened, whatever the row says — and `resolve()` is what makes the check
    hold, because a `..` segment survives a prefix comparison unless the path is normalised first.

    The download filename is the human-readable queue name, planned from the same pure function
    the queue folders are planned from, so what the browser saves matches what is on disk.
    """
    detail = queue_detail(conn, posting_id)
    if detail is None:
        return PdfIssue.NO_LEAD
    if detail.row.pdf_uri is None:
        return PdfIssue.NO_PDF
    candidate = Path(detail.row.pdf_uri).resolve()
    if not _contained(candidate, ctx.out_root):
        return PdfIssue.OUTSIDE_ROOT
    if not candidate.is_file():
        return PdfIssue.MISSING_FILE
    return PdfFile(path=candidate, filename=_pdf_filename(detail.row, ctx))


def _pdf_filename(row: QueueRow, ctx: ApiContext) -> str:
    try:
        return plan_lead_names(
            root=ctx.queue_root,
            owner_name=ctx.owner_name,
            company=row.company,
            title=row.title,
            identity_hash=_identity_hash(row),
        ).pdf
    except NameBudgetError:
        # The budget is a filesystem limit on a path being WRITTEN; nothing is being written
        # here, so an unplannable name costs the pretty filename and not the download.
        return Path(str(row.pdf_uri)).name


def _pdf_path(pdf_uri: str | None, out_root: Path) -> Path | None:
    """The PDF's path when it exists inside the applications root, else None.

    This is what `pdf_available` reports, and it is deliberately the same three checks
    `resolve_pdf` makes: a row that advertises a PDF the endpoint would refuse is a button that
    only fails.
    """
    if pdf_uri is None:
        return None
    candidate = Path(pdf_uri).resolve()
    if not _contained(candidate, out_root) or not candidate.is_file():
        return None
    return candidate


def _contained(candidate: Path, root: Path) -> bool:
    """`candidate` is `root` itself or sits under it. Both sides resolved before comparing.

    `is_relative_to` on resolved paths, not a string prefix: `/out-evil` starts with `/out` as a
    string and is not inside it.
    """
    try:
        return candidate.resolve().is_relative_to(root.resolve())
    except OSError:
        return False


# ---------------------------------------------------------------------------------- reveal folder


def reveal_argv(platform: str, folder: Path) -> list[str] | None:
    """The platform's "show this folder" argv, or None where there is no handler.

    Shape and injection point taken from `notify/desktop.py`: a closed set of platforms, None for
    everything else, and the answer to "is this supported" derived from this one function so the
    capability flag and the behaviour cannot disagree.
    """
    if platform == "darwin":
        return ["open", str(folder)]
    if platform.startswith("linux"):
        return ["xdg-open", str(folder)]
    if platform == "win32":
        return ["explorer", str(folder)]
    return None


def reveal_supported(platform: str) -> bool:
    return reveal_argv(platform, Path(".")) is not None


def lead_folder(ctx: ApiContext, posting_id: int) -> Path | None:
    """This lead's queue folder, identified by the `posting_id` inside its `details.json`.

    Never by folder name (design §4.1). The owner may have renamed one, and slugging is lossy in
    the first place, so a name-derived lookup would be wrong in a way nothing would report.
    """
    entries, _unclassified = _index(ctx.queue_root.resolve())
    entry = entries.get(posting_id)
    return None if entry is None else entry.path


def reveal(ctx: ApiContext, posting_id: int, runner: Runner | None = None) -> dict[str, Any]:
    """Open the platform's file manager on one lead's queue folder.

    Refused rather than attempted when the resolved folder is not contained under the queue root.
    `_index` only ever yields children of that root, so this cannot currently fail — which is
    exactly why it is asserted: the check has to be here for the day the survey changes, not
    added afterwards.
    """
    if not reveal_supported(ctx.platform):
        return {"ok": False, "reason": f"no file-manager handler on {ctx.platform}"}
    folder = lead_folder(ctx, posting_id)
    if folder is None:
        return {"ok": False, "reason": "this lead has no folder in the queue yet"}
    if not _contained(folder, ctx.queue_root):
        return {"ok": False, "reason": "the folder resolved outside the queue root"}
    argv = reveal_argv(ctx.platform, folder)
    if argv is None:  # pragma: no cover - reveal_supported already answered this
        return {"ok": False, "reason": f"no file-manager handler on {ctx.platform}"}
    try:
        code = (runner or _default_runner)(argv)
    except OSError as exc:
        return {"ok": False, "reason": f"{argv[0]} could not be run: {exc.strerror}"}
    if ctx.platform == "win32":
        # `explorer.exe` exits 1 even when it opened the window. Checking its code would report
        # a failure toast on every successful reveal on Windows, which is worse than reporting
        # nothing: the owner would learn to ignore the toast.
        return {"ok": True}
    return {"ok": True} if code == 0 else {"ok": False, "reason": f"{argv[0]} exit {code}"}


def _default_runner(argv: list[str]) -> int:
    return subprocess.run(argv, check=False, capture_output=True).returncode


# --------------------------------------------------------------------------------------- the runs


def runs_payload(conn: Connection) -> dict[str, Any]:
    """`GET /api/runs`: the recent runs, with how many leads each delivered.

    `leads` is counted from `artifacts`, which is where a delivery is recorded — `runs` carries no
    such column, and a run that delivered nothing is a real 0 rather than an unknown.
    """
    delivered: dict[int, int] = {
        int(row[0]): int(row[1])
        for row in conn.execute(
            select(artifacts.c.run_id, func.count())
            .where(artifacts.c.kind == TAILORED_KIND, artifacts.c.run_id.is_not(None))
            .group_by(artifacts.c.run_id)
        ).all()
    }
    rows = conn.execute(select(runs).order_by(runs.c.id.desc()).limit(RUNS_LIMIT)).all()
    return {
        "runs": [
            {
                "id": int(row.id),
                "started": None if row.started_at is None else row.started_at.isoformat(),
                "finished": None if row.finished_at is None else row.finished_at.isoformat(),
                "status": row.status,
                "boards_attempted": row.boards_attempted,
                "boards_complete": row.boards_complete,
                "boards_partial": row.boards_partial,
                "boards_unchanged": row.boards_unchanged,
                "boards_failed": row.boards_failed,
                "postings_seen": row.postings_seen,
                "new_count": row.new_count,
                "leads": delivered.get(int(row.id), 0),
            }
            for row in rows
        ]
    }


def funnel_payload(ctx: ApiContext, run_id: int) -> dict[str, Any] | None:
    """`GET /api/runs/<id>`: that run's own funnel artifact, passed through unchanged.

    `funnel-<id>.json` is the artifact designed for exactly this question and is already what
    `verify` reads, so nothing new is written and the page cannot disagree with the reconciliation.
    Located by glob rather than by reconstructing the day folder from the run's start date, the way
    `cli/verify_cmd.py` locates it: the run row may be gone while the artifact is not.
    """
    path = next(
        iter(
            sorted(ctx.out_root.glob(f"funnel-{run_id}.json"))
            or sorted(ctx.out_root.glob(f"*/funnel-{run_id}.json"))
        ),
        None,
    )
    if path is None or not _contained(path, ctx.out_root):
        return None
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


__all__ = [
    "FALLBACK_OWNER_NAME",
    "RUNS_LIMIT",
    "TAXONOMY_KIND",
    "TERM_CACHE_MAX",
    "ApiContext",
    "CacheIdentity",
    "LiveFacts",
    "PdfFile",
    "PdfIssue",
    "Runner",
    "answers_payload",
    "detail_payload",
    "funnel_payload",
    "lead_folder",
    "queue_payload",
    "resolve_owner_name",
    "resolve_pdf",
    "reveal",
    "reveal_argv",
    "reveal_supported",
    "runs_payload",
]
