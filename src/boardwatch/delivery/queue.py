"""The delivery queue on disk: copies of what a run produced, under their own root (design §4).

**This module never writes into the applications root.** Not a move, not a rename, not a new
file. A read-only sweep of every consumer of the dated output tree (design §4) found that
relocating a lead folder breaks the repository in four independent ways no test would catch
before production: `pipeline/freshness.py:97-110` resolves each tailored artifact's `uri` parent
as the lead folder and treats a mismatch as a run-level fatal, `cli/verify_cmd.py:130,134` stats
those same paths for every funnel it sweeps, `reports/tailor.py:874-880` content-addresses the
projected master so its `uri` pins the first folder that ever produced those bytes, and every
per-run funnel freezes absolute lead paths into an immutable artifact. So the queue is a second
root holding **copies**, and no `artifacts` row ever points into it: lineage lives in
`details.json`, where a folder move cannot invalidate it.

**A queue folder contains exactly four names**, all of them constants in this module: the copied
PDF, one apply-link file, `job_description.txt` and `details.json`. It must NEVER contain
`resume.projected.yaml` or `projection-manifest.json`, which is why the PDF is copied file by
file and `shutil.copytree` is not used anywhere here.
`.agent/2026-08-25-craft-findings/b4_fabrication_audit.py:127-129` identifies a delivered résumé
as any directory holding both of those names, by recursive glob. Copying them in would make the
fabrication gate double-count today, and a later refactor that made the queue the *only* such
directory would leave the gate auditing nothing and reporting clean. It is a correctness
constraint, not tidiness.

Three properties are contractual rather than incidental.

**The database is authoritative in both directions.** `sync_queue` derives the whole queue from
`delivered_unapplied` and makes the filesystem match; `reconcile_queue` drains and un-drains from
`applied_job_ids` and `skipped_job_ids`. Neither ever reads a folder *name* for data — a folder
is identified only by the `posting_id` recorded inside its `details.json` — and neither deletes a
folder it cannot classify.

**Writes are staged then renamed.** Each folder is built under `<root>/.staging-<random>/` on the
same filesystem and `os.replace`d into place, so a crash can leave a stale staging directory
(cleaned by the next sync) but never a half-written folder the review page would list as a lead.

**One failure never costs the rest.** Each lead is attempted independently and a failure is
counted and reported, mirroring the isolation `scan/apply.py` gained after one board's failure
aborted a whole scan (#168).

Idempotence is keyed on `details.json`'s `content_hash`, which covers **every byte the folder
holds**: the canonicalised details, the JD body and the apply-link file are all fed to it, and the
copied PDF enters through `pdf_sha256`. Nothing time-varying is written, so an unchanged lead is
not rewritten merely because a day passed. That is why `posted_days` is absent from
`details.json` even though design §4.2 lists a posted date: the read layer exposes an age relative
to *now*, not `posted_at`, and recording it would either churn every folder daily or record a
number that silently goes stale. The database stays authoritative for it.
"""

from __future__ import annotations

import hashlib
import json
import os
import plistlib
import shutil
import sys
import time
from collections import Counter
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from secrets import token_hex

from filelock import FileLock, Timeout
from sqlalchemy import Connection, select

from boardwatch.core.lock_reclaim import RECLAIM_POLL_SECONDS, RECLAIM_WINDOW_SECONDS
from boardwatch.delivery import DRAIN_DIRS, LeadNames, plan_lead_names
from boardwatch.delivery.review_gate import CLOSED_DIR, REVIEW_DIR, lane
from boardwatch.store.applications import applied_job_ids
from boardwatch.store.delivery_queries import (
    JD_ABSENT_NO_CURRENT_VERSION,
    JD_ABSENT_REASONS,
    QueueRow,
    closed_job_ids,
    delivered_unapplied,
    ineligible_job_ids,
    queue_detail,
    review_job_ids,
)
from boardwatch.store.queries import canonical_job_ids
from boardwatch.store.queue_state import reported_job_ids, skipped_job_ids
from boardwatch.store.run_funnel_queries import TAILORED_KIND
from boardwatch.store.tables import artifacts

#: Where the queue lives unless a caller says otherwise (design §4). A constant rather than a
#: `Settings` field: adding one has four separately gated registration sites, and nothing here
#: needs to be configurable through a file to be overridden — every entry point takes `root`.
DEFAULT_QUEUE_ROOT = Path.home() / "boardwatch-queue"

LOCK_FILE = ".queue.lock"
APPLIED_DIR = "_applied"
SKIPPED_DIR = "_skipped"
REPORTED_DIR = "_reported"
INELIGIBLE_DIR = "_ineligible"
DETAILS_FILE = "details.json"
JD_FILE = "job_description.txt"
WEBLOC_FILE = "apply.webloc"
URL_FILE = "apply.url"
LINK_FILE = "apply-link.txt"
STAGING_PREFIX = ".staging-"

#: Bumped when `details.json`'s shape changes. A reader that finds a schema it does not know is
#: reading a projection, not a source of truth, and the next sync rewrites it.
DETAILS_SCHEMA = 1

#: Bound at import so a test can choose a platform without touching `sys`. The apply-link file's
#: format is a property of the machine the owner clicks on, and it does not change mid-process.
PLATFORM = sys.platform

#: Namespaces `_identity_hash` so a digest from this module can never be confused with one from
#: another, and so the scheme can be revised without silently reusing old names.
IDENTITY_SALT = "boardwatch.delivery.queue.identity.v1"

#: DERIVED from `names.DRAIN_DIRS`, never enumerated again here. `names.py` prices the byte
#: budget against the longest drain, so a drain listed in one place and not the other silently
#: breaks that budget — which is exactly what happened to `_ineligible`. `""` is the queue root
#: itself, which is a location but not a drain.
_LOCATIONS: tuple[str, ...] = ("", *DRAIN_DIRS)
_NO_PDF_ARTIFACT = "no_pdf_artifact"
_PDF_FILE_MISSING = "source_file_missing"
_NO_APPLY_URL = "no_apply_url"


class QueueLockHeldError(RuntimeError):
    """The queue's writer lock is already held.

    Typed at the raise site so `_queue_lock` can be reused by a caller that wants to fail loudly,
    while the two entry points here translate it into `contended=True`. They translate rather than
    propagate because both of their callers need a value: the run hook swallows every exception
    (design §4.3), so an exception would be indistinguishable there from a real write failure, and
    a web request has to answer.

    Not "another process": `_queue_lock` builds a fresh `FileLock` per call, so a second acquire
    inside *this* process is refused identically.
    """


class QueueConflictError(RuntimeError):
    """A folder was going to be written where something already stands that is not it.

    Raised instead of clobbering, in both directions: a lead whose target path is occupied by a
    folder that does not identify it, and a drain move whose destination already exists. Either is
    left exactly as it was and reported.
    """


@dataclass(frozen=True)
class LeadFailure:
    """One lead that could not be written. `posting_id` rather than the folder name, because the
    name is what failed to be produced."""

    posting_id: int
    detail: str


@dataclass(frozen=True)
class FolderFailure:
    """One folder that could not be moved. Named by folder, because reconcile works from disk."""

    folder: str
    detail: str


@dataclass(frozen=True)
class SyncReport:
    """What `sync_queue` did.

    `created`, `updated`, `unchanged` and `failed` partition the leads the database offered —
    every lead lands in exactly one. `moved` is orthogonal and counts relocations, so a lead that
    was renamed and then rewritten increments both `moved` and `updated`.

    `failed` is derived from `failures` rather than counted alongside it, so the two can never
    disagree.

    `retired` is orthogonal too, and counts DUPLICATE folders deleted because identity resolution
    converged two postings onto one canonical job. It is reported rather than silent because it
    is the only destructive thing this function does.
    """

    created: int = 0
    updated: int = 0
    unchanged: int = 0
    moved: int = 0
    retired: int = 0
    failures: tuple[LeadFailure, ...] = ()
    contended: bool = False

    @property
    def failed(self) -> int:
        return len(self.failures)


@dataclass(frozen=True)
class ReconcileReport:
    """What `reconcile_queue` did.

    `unclassified` names every folder left untouched because its `details.json` was absent,
    unreadable, or did not identify a posting — reported, never deleted, and never guessed at from
    the folder name.
    """

    to_applied: int = 0
    to_skipped: int = 0
    to_reported: int = 0
    to_ineligible: int = 0
    to_review: int = 0
    to_closed: int = 0
    to_queue: int = 0
    unclassified: tuple[str, ...] = ()
    failures: tuple[FolderFailure, ...] = ()
    contended: bool = False

    @property
    def moved(self) -> int:
        # EVERY drain, including `_ineligible` and `_review`. Both callers report this and nothing
        # else (`runner.py`'s run line and the server's reconcile endpoint), and `sync_queue`
        # cannot compensate for a reconcile-only move — so omitting a drain here prints "0 moved"
        # while folders move, which is the same unreported-number defect this whole change fixes.
        return (
            self.to_applied
            + self.to_skipped
            + self.to_reported
            + self.to_ineligible
            + self.to_review
            + self.to_closed
            + self.to_queue
        )

    @property
    def failed(self) -> int:
        return len(self.failures)


@dataclass(frozen=True)
class _Entry:
    """One folder already on disk, identified by what its `details.json` says it is."""

    path: Path
    location: str
    posting_id: int
    job_id: int
    content_hash: str | None


@dataclass(frozen=True)
class _Payload:
    """Everything one folder will hold, resolved before anything is written."""

    names: LeadNames
    details: dict[str, object]
    content_hash: str
    pdf_source: Path | None
    link: tuple[str, bytes] | None
    jd: str | None


# ------------------------------------------------------------------------------------ public API


def sync_queue(conn: Connection, *, root: Path, owner_name: str) -> SyncReport:
    """Make the queue under `root` match what the database says is delivered and unapplied.

    Idempotent: a folder whose `details.json` records the same `content_hash` is not rewritten,
    which is what lets this be called at the end of every run, at web-server start-up and after
    every mark-applied without the owner's folders churning under them.

    A lead whose folder currently sits in a drain is pulled back out, because the database has
    just said it is none of applied, skipped or reported, and creating a second folder for it
    would be the one outcome worse than a stale one. `reconcile_queue` applies the same rule from
    the other side; both hold the same lock, so they cannot disagree mid-flight, and neither
    depends on the other having run first.

    `root` is resolved first. `plan_lead_names` prices its byte budget against the path it is
    given, so a relative root would price a shorter destination than the one actually written and
    would be wrong in the unsafe direction.
    """
    resolved = root.resolve()
    try:
        with _queue_lock(resolved):
            return _sync_locked(conn, root=resolved, owner_name=owner_name)
    except QueueLockHeldError:
        return SyncReport(contended=True)


def reconcile_queue(conn: Connection, *, root: Path) -> ReconcileReport:
    """Move every folder to the drain the database says it belongs in, in both directions.

    Applied wins over skipped when a job is both: an application is a statement that the owner
    engaged with the employer, and a skip is a statement that they did not look. The stronger
    claim decides where the folder lives. A REPORTED job ranks below both — those say what the
    owner did with the lead, while a report says the eligibility decision was wrong — and above
    `closed` and the derived verdicts. Full precedence and its reasoning: `_wanted_location`.

    Nothing is deleted, ever — not a folder without a `details.json`, not a folder whose
    destination is already occupied, not a folder for a posting the database has forgotten.
    """
    resolved = root.resolve()
    try:
        with _queue_lock(resolved):
            return _reconcile_locked(conn, root=resolved)
    except QueueLockHeldError:
        return ReconcileReport(contended=True)


# --------------------------------------------------------------------------------------- locking


@contextmanager
def _queue_lock(root: Path) -> Iterator[Path]:
    """Hold the queue's exclusive writer lock, or raise `QueueLockHeldError` at once.

    The repository's third `filelock` lock, taken exactly as the bundle writer lock
    (`profile_bundle/locking.py`) and the scan lock (`scan/coordinator.py`) take theirs: one
    non-blocking acquire per pass, re-asked until `RECLAIM_WINDOW_SECONDS` closes, and the
    operating system left as the only authority. Nothing here reads, ages or unlinks the lockfile,
    so a lockfile left behind by a killed holder means nothing at all.

    `RECLAIM_WINDOW_SECONDS` is bound **by name in this module** because `core/lock_reclaim.py`
    says consumers do, and because patching it there would not reach this binding: a test must
    patch `delivery.queue.RECLAIM_WINDOW_SECONDS` to exercise this loop. The window exists for
    Windows, where `filelock`'s `WindowsFileLock._acquire` swallows the `EACCES` a killed holder's
    asynchronous handle teardown produces and reports `Timeout` for a lock nobody holds; it is
    zero elsewhere, so POSIX asks exactly once.

    `Timeout` derives from `TimeoutError` and therefore from `OSError`, so it is caught first.
    A genuine I/O failure is deliberately *not* caught: it means this is not a usable root, which
    is a different situation from contention and needs a different fix.
    """
    _ensure_root(root)
    path = root / LOCK_FILE
    lock = FileLock(str(path))
    deadline = time.monotonic() + RECLAIM_WINDOW_SECONDS
    while True:
        try:
            lock.acquire(blocking=False)
        except Timeout as exc:
            if time.monotonic() >= deadline:
                raise QueueLockHeldError(
                    f"the delivery queue's {LOCK_FILE} is already held, by another command or by "
                    "this one holding it twice; nothing was changed"
                ) from exc
            time.sleep(RECLAIM_POLL_SECONDS)
            continue
        break
    try:
        yield path
    finally:
        lock.release()


def _ensure_root(root: Path) -> None:
    """Create the root and every drain. Idempotent, and the only writes outside the lock — the
    lockfile has to live somewhere before it can be taken.

    Every drain is created up front rather than lazily by `_relocate`'s `mkdir`. Lazily is not
    merely untidy: a drain that does not exist until the first folder lands in it is invisible to
    every test whose root never produces one, which is precisely what let `_child_dirs` ship
    without knowing about `_ineligible`.
    """
    root.mkdir(parents=True, exist_ok=True)
    for drain in _LOCATIONS:
        if drain:
            (root / drain).mkdir(exist_ok=True)


# ------------------------------------------------------------------------------------------ sync


def _dest(root: Path, lane_dir: str, folder: str) -> Path:
    """Where a lead's folder belongs: the apply queue (`lane_dir == ""`) or a lane subdir."""
    return (root / lane_dir / folder) if lane_dir else root / folder


def _sync_locked(conn: Connection, *, root: Path, owner_name: str) -> SyncReport:
    """Two passes, and the order is load-bearing.

    Every folder that has to move, moves before any folder is created. A lead that is renaming
    itself out of a path a *different* lead now plans to occupy has to vacate first: interleaving
    the two would refuse the second lead a path that was about to be free, and which pass it
    landed in would depend on the query's row order.
    """
    _clear_staging(root)
    # An ineligible lead is not work, so it gets no folder at all. It is EXCLUDED here rather than
    # deleted: `reconcile_queue` has already moved any existing folder into `_ineligible`, and
    # leaving the row out of `rows` is what stops the move-loop below pulling it straight back out.
    # The reverse direction still works — if the verdict later clears, the row reappears here and
    # the folder is drawn back, so the drain self-heals exactly as `_applied` and `_skipped` do.
    #
    # A REVIEW lead, by contrast, IS work to look at, so it STAYS in `rows`: `lane_of` routes it to
    # the `_review` subdir rather than excluding it, and `_index` scans `_review`, so a lead is
    # created wherever it belongs and moves between the apply queue and review as its class changes.
    # A REPORTED lead is excluded on the same footing as a skipped one, and through the same
    # parameter, because `delivered_unapplied` asks its caller for the job-keyed set to withhold
    # rather than deciding what withholding means. `delivery/api.py` already unions the two for
    # the web queue; without the union here `reconcile_queue` would move the folder into
    # `_reported/` and the `sync_queue` that follows it in the SAME call would RELOCATE IT STRAIGHT
    # BACK OUT -- `_index` scans the drains, so the relocation pass finds it and moves it -- and
    # the lead the owner reported would be in the apply queue again every run while the reconcile
    # count read a healthy 1. The tell is `moved`, not `created`: nothing is ever created here, so
    # a test asserting `created == 0` passes against the broken version and pins nothing.
    withheld = set(skipped_job_ids(conn)) | set(reported_job_ids(conn))
    rows = [
        row
        for row in delivered_unapplied(conn, skipped=withheld)
        if row.verdict != "ineligible"
    ]
    lane_of = {
        row.posting_id: lane(
            verdict=row.verdict,
            locations=row.locations,
            title=row.title,
            experience_unconfirmed=row.requirement_flags.experience_unconfirmed,
            eligibility_unconfirmed=row.requirement_flags.eligibility_unconfirmed,
            no_requirement_rows=row.requirement_flags.no_requirement_rows,
            posting_closed=row.closed,
        )
        for row in rows
    }
    artifact_ids = _tailored_artifact_ids(conn)
    entries, by_job, duplicates = _resolve_job_identity(conn, _index(root)[0])
    planned, failures = _plan(rows, root=root, owner_name=owner_name)
    failed = {failure.posting_id for failure in failures}

    # BEFORE the relocation pass, which is what would otherwise refuse the occupied destination.
    retired, retire_failures = _consolidate_duplicates(duplicates, entries, by_job)
    failures.extend(retire_failures)
    failed.update(failure.posting_id for failure in retire_failures)

    moved = 0
    for row in rows:
        names = planned.get(row.posting_id)
        entry = _entry_for(row, entries, by_job)
        if names is None or entry is None:
            continue
        target = _dest(root, lane_of[row.posting_id], names.folder)
        if entry.path == target:
            continue
        try:
            _relocate(entry.path, target)
            moved += 1
        except Exception as exc:  # one lead must never cost the rest
            failures.append(LeadFailure(posting_id=row.posting_id, detail=_detail(exc)))
            failed.add(row.posting_id)

    created = updated = unchanged = 0
    staging = root / f"{STAGING_PREFIX}{token_hex(8)}"
    staging.mkdir()
    try:
        for row in rows:
            names = planned.get(row.posting_id)
            if names is None or row.posting_id in failed:
                continue
            try:
                # `entry.path` is stale after the relocation pass; only its existence and its
                # recorded hash are read here, and neither moved.
                entry = _entry_for(row, entries, by_job)
                target = _dest(root, lane_of[row.posting_id], names.folder)
                if entry is None and target.exists():
                    raise QueueConflictError(
                        f"{names.folder} already exists and does not identify posting "
                        f"{row.posting_id}"
                    )
                payload = _payload(conn, row, names=names, artifact_ids=artifact_ids)
                if entry is not None and entry.content_hash == payload.content_hash:
                    unchanged += 1
                    continue
                _install(staging, target, payload)
                if entry is None:
                    created += 1
                else:
                    updated += 1
            except Exception as exc:  # one lead must never cost the rest
                failures.append(LeadFailure(posting_id=row.posting_id, detail=_detail(exc)))
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    return SyncReport(
        created=created,
        updated=updated,
        unchanged=unchanged,
        moved=moved,
        retired=retired,
        failures=tuple(failures),
    )


def _plan(
    rows: Sequence[QueueRow], *, root: Path, owner_name: str
) -> tuple[dict[int, LeadNames], list[LeadFailure]]:
    """Plan every lead's names, disambiguating any folder two different postings would share.

    Disambiguation is a second pass over the whole set rather than a check against disk, so the
    name is a function of the database alone and two syncs of the same data agree. Every member of
    a colliding group is disambiguated, not just the newcomer: deciding by arrival order would
    make the name depend on which lead was seen first, and a folder that renames itself when a
    sibling appears is at least reported as `moved`.

    **THE COLLISION KEY IS CASE-FOLDED, because a filesystem's is.** Two leads that plan
    `onX_Full_Stack_Engineer` and `OnX_Full_Stack_Engineer` are two distinct strings and one
    single path on macOS and Windows, so a case-sensitive `Counter` finds no collision, neither
    lead is disambiguated, and the second one to be written finds its target held by a folder
    that does not identify it and fails. That is not hypothetical: it cost run 139 two of the
    three leads it failed to queue (`onX`/`OnX`, `WellSky`/`Wellsky`), and **no test on a
    case-sensitive CI filesystem can reproduce it** — on Linux both folders are created and
    nothing raises. It is the same defect class as `ashby:Lightfield`/`ashby:lightfield`, which
    `store/queries.py:stored_slug` exists to stop: case folded in one layer and not the
    adjacent one.

    `casefold()` rather than `lower()`, and it matters here: `slug()` deliberately keeps
    non-ASCII letters, so a folder name can be French or Japanese, and both APFS and NTFS fold
    case beyond ASCII. `slug()` normalizes to NFC first, so both sides of the comparison are
    already in one normal form and folding is the only difference left to close.

    The disambiguator goes into the *title* handed to `plan_lead_names` rather than being appended
    to the returned folder, so the byte budget stays that function's responsibility. A title long
    enough to be truncated loses the suffix but gains `plan_lead_names`' own, which keys on the
    text as well as the identity and so still separates the two.
    """
    identities = {row.posting_id: _identity_hash(row) for row in rows}
    failures: list[LeadFailure] = []

    def attempt(row: QueueRow, title: str) -> LeadNames | None:
        try:
            return plan_lead_names(
                root=root,
                owner_name=owner_name,
                company=row.company,
                title=title,
                identity_hash=identities[row.posting_id],
            )
        except Exception as exc:
            failures.append(LeadFailure(posting_id=row.posting_id, detail=_detail(exc)))
            return None

    first = {row.posting_id: attempt(row, row.title) for row in rows}
    shared = Counter(names.folder.casefold() for names in first.values() if names is not None)
    planned: dict[int, LeadNames] = {}
    for row in rows:
        names = first[row.posting_id]
        if names is None:
            continue
        if shared[names.folder.casefold()] == 1:
            planned[row.posting_id] = names
            continue
        suffix = identities[row.posting_id][:8]
        retried = attempt(row, f"{row.title} {suffix}")
        if retried is not None:
            planned[row.posting_id] = retried

    # FINAL FOLDED-UNIQUENESS CHECK. The disambiguation above is ONE pass, and a retried name can
    # still collide — with a singleton that was never retried, or with another retried name. The
    # reachable shape is a lead whose ORDINARY title happens to contain another lead's eight-hex
    # suffix, which then plans the identical folder; `_fit`'s truncation does not establish
    # uniqueness either, since it substitutes another eight-hex digest without re-checking.
    # Reproduced: `Acme`/`Engineer` and `acme`/`Engineer` collide by case, both retry, and a third
    # lead titled `Engineer <first lead's suffix>` plans the SAME folder as the first, with
    # `_plan` reporting no failure at all.
    #
    # Left as a REPORTED failure rather than resolved with a longer suffix: extending it is bounded
    # by the byte budget and would re-enter `_fit`, which is the same problem one level down. What
    # this pass buys is that the loss is DETERMINISTIC and NAMED — the lowest `posting_id` keeps
    # the folder and every other member is failed with the reason here, instead of whichever lead
    # happened to be written second failing at write time with a `QueueConflictError` that blames
    # the folder rather than the plan.
    folded = Counter(names.folder.casefold() for names in planned.values())
    for posting_id in sorted(planned):
        names = planned[posting_id]
        if folded[names.folder.casefold()] == 1:
            continue
        key = names.folder.casefold()
        rivals = sorted(
            other for other, item in planned.items() if item.folder.casefold() == key
        )
        if posting_id == rivals[0]:
            continue
        del planned[posting_id]
        failures.append(
            LeadFailure(
                posting_id=posting_id,
                detail=(
                    f"planned folder {names.folder!r} is still taken after disambiguation by "
                    f"posting {rivals[0]}; a title carrying another lead's suffix cannot be "
                    f"separated by one"
                ),
            )
        )
    return planned, failures


def _identity_hash(row: QueueRow) -> str:
    """A stable, opaque identity for one posting: the same lead hashes the same on every run.

    Built from the lead's own facts plus the canonical `job_id`, which is boardwatch's own
    posting-identity anchor — `applications` keys on it (`tables.py:354`), the skip state keys on
    it, and `delivered_unapplied` deduplicates on it, so exactly one queue row exists per job and
    the digest is therefore unique within a sync. Nothing here reads a run id or a clock: those
    change on every run, and a name derived from one would move a folder out from under the owner
    nightly.

    The natural facts are included rather than hashing the id alone so this is a real content
    identity, and the digest is what reaches a name, so no id is ever visible in a folder. A
    posting regrouped onto another job does get a new identity; that surfaces as a `moved` folder,
    not as an orphan, which is the reason `sync_queue` relocates rather than recreates.
    """
    parts = (
        IDENTITY_SALT,
        row.company,
        row.title,
        row.apply_url or "",
        str(row.job_id),
    )
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()


def _payload(
    conn: Connection, row: QueueRow, *, names: LeadNames, artifact_ids: dict[str, int]
) -> _Payload:
    """Resolve one lead's whole folder — every byte of it — before anything is written."""
    detail = queue_detail(conn, row.posting_id)
    jd = None if detail is None else detail.jd_body
    # Out-of-catalog is a failure, never a new bucket: a reason this module does not know is a
    # reason `details.json` would publish unexplained.
    jd_absent_reason = (
        JD_ABSENT_NO_CURRENT_VERSION if detail is None else detail.jd_absent_reason
    )
    if jd is None and jd_absent_reason not in JD_ABSENT_REASONS:
        raise ValueError(f"unknown job-description absence reason: {jd_absent_reason!r}")
    if jd is not None and jd_absent_reason is not None:
        raise ValueError(f"job-description body has an absence reason: {jd_absent_reason!r}")
    board_target = None if detail is None else detail.board_target
    link = None if row.apply_url is None else _apply_link(row.apply_url, PLATFORM)
    pdf_source, pdf_sha256, pdf_absent = _pdf_source(row.pdf_uri)

    details: dict[str, object] = {
        "schema": DETAILS_SCHEMA,
        "posting_id": row.posting_id,
        "job_id": row.job_id,
        "delivered_run_id": row.delivered_run_id,
        "identity_hash": _identity_hash(row),
        # Unslugged, because slugging is lossy and this is where the originals live (design §4.1).
        "company": row.company,
        "title": row.title,
        "location": row.location,
        "remote_policy": row.remote_policy,
        "status": row.status,
        "verdict": row.verdict,
        "first_seen": row.first_seen.isoformat(),
        "apply_url": row.apply_url,
        "board_target": board_target,
        "target_flag": row.target_flag,
        "folder": names.folder,
        # Lineage (design §4.2). `source_uri` is the PDF that was copied; `source_tex_uri` is the
        # artifact row's own `uri`, which is the `.typ`/`.tex`.
        "source_artifact_id": artifact_ids.get(row.tex_uri),
        "source_uri": row.pdf_uri,
        "source_tex_uri": row.tex_uri,
        "pdf_filename": None if pdf_source is None else names.pdf,
        "pdf_missing": pdf_source is None,
        "pdf_absent_reason": pdf_absent,
        "pdf_sha256": pdf_sha256,
        # An absent file and an empty file are different claims, so each absence is named.
        "apply_link_file": None if link is None else link[0],
        "apply_link_absent_reason": None if link is not None else _NO_APPLY_URL,
        "job_description_file": None if jd is None else JD_FILE,
        "job_description_absent_reason": None if jd is not None else jd_absent_reason,
    }
    return _Payload(
        names=names,
        details=details,
        content_hash=_content_hash(details, jd=jd, link=link),
        pdf_source=pdf_source,
        link=link,
        jd=jd,
    )


def _pdf_source(pdf_uri: str | None) -> tuple[Path | None, str | None, str | None]:
    """`(path to copy, its sha256, why there is nothing to copy)`.

    A missing PDF must not cost the owner the apply link and the JD, so it is a recorded fact
    about one file rather than a failure for the lead. The two ways it can be absent are kept
    apart: the tailor never built one, or the row names one that is no longer on disk. They lead
    to different investigations.
    """
    if pdf_uri is None:
        return None, None, _NO_PDF_ARTIFACT
    source = Path(pdf_uri)
    if not source.is_file():
        return None, None, _PDF_FILE_MISSING
    return source, _file_sha256(source), None


def _apply_link(url: str, platform: str) -> tuple[str, bytes]:
    """`(filename, bytes)` for the one-click apply link, in the host's own shortcut format.

    A `.webloc` is a plist, so `plistlib` writes it — hand-rolling the XML would be one escaping
    bug away from a broken link for any URL containing an ampersand. Anything that is neither
    macOS nor Windows gets the bare URL in a text file, which every desktop can at least open.
    """
    if platform == "darwin":
        return WEBLOC_FILE, plistlib.dumps({"URL": url})
    if platform == "win32":
        return URL_FILE, f"[InternetShortcut]\r\nURL={url}\r\n".encode()
    return LINK_FILE, f"{url}\n".encode()


def _content_hash(
    details: dict[str, object], *, jd: str | None, link: tuple[str, bytes] | None
) -> str:
    """A digest over every byte the folder will hold, and nothing else.

    `details` is fed in canonicalised, the JD body and the link file are fed in whole, and the
    copied PDF enters through `details["pdf_sha256"]`. So "the recorded hash matches" really does
    mean "the folder is already exactly this", which is what makes skipping the rewrite safe
    rather than merely fast. `details` must not yet carry `content_hash`; it is added on write.
    """
    digest = hashlib.sha256()
    digest.update(
        json.dumps(details, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    )
    digest.update(b"\x00")
    digest.update(b"" if jd is None else jd.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(b"" if link is None else link[1])
    return digest.hexdigest()


def _file_sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _tailored_artifact_ids(conn: Connection) -> dict[str, int]:
    """`artifacts.uri` -> the id of the tailored row that wrote it.

    `QueueRow` carries the uri but not the id, and design §4.2 requires the id in `details.json`,
    so it is looked up here. The whole tailored set in one statement, ordered ascending so the
    highest id wins a duplicated uri: two rows can share a uri when a lead is re-tailored on the
    same day, and the latest row is the one whose bytes are on disk. No `IN (...)` list is built,
    so nothing here can meet SQLite's 32,766 bound-parameter cap (D-287).
    """
    rows = conn.execute(
        select(artifacts.c.id, artifacts.c.uri)
        .where(artifacts.c.kind == TAILORED_KIND)
        .order_by(artifacts.c.id)
    ).all()
    return {str(row.uri): int(row.id) for row in rows}


# ------------------------------------------------------------------------------- staged installs


def _install(staging: Path, target: Path, payload: _Payload) -> None:
    """Build the folder under `staging` and `os.replace` it onto `target`.

    An existing `target` is moved aside into `staging` first rather than removed, for two reasons:
    `os.replace` will not rename onto a non-empty directory on POSIX and refuses one at all on
    Windows, and it keeps the window in which the owner could see nothing at all down to a single
    rename. Worst case a crash leaves the superseded copy under `.staging-…`, which the next sync
    clears — the target itself is only ever the whole old folder or the whole new one.
    """
    built = staging / f"build-{token_hex(8)}"
    _write_lead(built, payload)
    if target.exists():
        os.replace(target, staging / f"old-{token_hex(8)}")
    os.replace(built, target)


def _write_lead(built: Path, payload: _Payload) -> None:
    """Write the folder's contents, file by file — never `copytree`.

    Copying the source directory wholesale would drag `resume.projected.yaml` and
    `projection-manifest.json` into the queue and break the fabrication audit (module docstring).
    Naming every file explicitly is what makes that impossible rather than merely unintended.
    """
    built.mkdir(parents=True)
    if payload.pdf_source is not None:
        shutil.copyfile(payload.pdf_source, built / payload.names.pdf)
    if payload.link is not None:
        (built / payload.link[0]).write_bytes(payload.link[1])
    if payload.jd is not None:
        (built / JD_FILE).write_text(payload.jd, encoding="utf-8")
    _write_details(built, payload)


def _write_details(built: Path, payload: _Payload) -> None:
    """`details.json`, written last: it is the marker that says the folder is complete, and the
    hash it records is only true once every other file is there."""
    body = dict(payload.details)
    body["content_hash"] = payload.content_hash
    (built / DETAILS_FILE).write_text(
        json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _clear_staging(root: Path) -> None:
    """Remove staging directories a crashed sync left behind. Safe because the lock serialises
    syncs, so no live sync's staging can be visible here."""
    for path in root.glob(f"{STAGING_PREFIX}*"):
        shutil.rmtree(path, ignore_errors=True)


# ------------------------------------------------------------------------------------- reconcile


def _reconcile_locked(conn: Connection, *, root: Path) -> ReconcileReport:
    applied = applied_job_ids(conn)
    skipped = skipped_job_ids(conn)
    reported = reported_job_ids(conn)
    closed = closed_job_ids(conn)
    ineligible = ineligible_job_ids(conn)
    review = review_job_ids(conn)
    entries, unclassified = _index(root)
    # Refreshed before `_wanted_location` reads `entry.job_id`: a folder whose canonical job moved
    # would otherwise be filed against the identity it was written under rather than the one it
    # has now.
    # Duplicates are read but NOT consolidated here: deleting a folder happens in exactly one
    # place, `sync_queue`, which is the pass that has the plan and the offered rows to decide a
    # keeper with. Reconcile moves by `entry.job_id` and never renames, so it cannot hit the
    # occupied-destination conflict that consolidation exists to end.
    entries, _, _ = _resolve_job_identity(conn, entries)
    counts = {
        APPLIED_DIR: 0,
        SKIPPED_DIR: 0,
        REPORTED_DIR: 0,
        INELIGIBLE_DIR: 0,
        REVIEW_DIR: 0,
        CLOSED_DIR: 0,
        "": 0,
    }
    failures: list[FolderFailure] = []
    for entry in sorted(entries.values(), key=lambda item: item.posting_id):
        wanted = _wanted_location(
            entry,
            applied=applied,
            skipped=skipped,
            reported=reported,
            closed=closed,
            ineligible=ineligible,
            review=review,
        )
        if wanted == entry.location:
            continue
        # `entry.path.name`, not a freshly planned name: reconcile moves a folder, it never
        # renames one. One consequence is worth knowing rather than rediscovering. `_sync_locked`
        # plans names over non-ineligible rows only, so a lead parked in `_ineligible` no longer
        # forces a same-company-same-title sibling to disambiguate. If its verdict later clears,
        # this move can find the plain name taken and raise, and the run line reports `1 failed`.
        # It is SPURIOUS and self-heals in the same run: the `sync_queue` that follows plans both
        # leads, disambiguates them, and relocates from `_ineligible` (which `_index` scans). Not
        # fixed by widening `_plan`'s input, because that would report naming failures for leads
        # this function deliberately never creates.
        target = (root / wanted / entry.path.name) if wanted else root / entry.path.name
        try:
            _relocate(entry.path, target)
        except Exception as exc:
            failures.append(FolderFailure(folder=entry.path.name, detail=_detail(exc)))
            continue
        counts[wanted] += 1
    return ReconcileReport(
        to_applied=counts[APPLIED_DIR],
        to_skipped=counts[SKIPPED_DIR],
        to_reported=counts[REPORTED_DIR],
        to_ineligible=counts[INELIGIBLE_DIR],
        to_review=counts[REVIEW_DIR],
        to_closed=counts[CLOSED_DIR],
        to_queue=counts[""],
        unclassified=unclassified,
        failures=tuple(failures),
    )


def _wanted_location(
    entry: _Entry,
    *,
    applied: dict[int, str],
    skipped: dict[int, str],
    reported: dict[int, str],
    closed: set[int],
    ineligible: dict[int, str],
    review: set[int],
) -> str:
    """Precedence, and it is not arbitrary.

    Applied and skipped are both statements the OWNER made about what they did; `ineligible` is
    a verdict the gate derived and can revise on the next run. So an owner statement wins: a
    lead they already applied to must not be swept into an eligibility drain months later
    because a rule tightened, and a lead they chose to skip keeps that record. `review` ranks
    below `ineligible` — a lead that is both is ineligible, not merely unverified — and above the
    apply queue, so an unverified `uncertain` lead is held for a look rather than blind-applied.

    `reported` is an owner statement too, so it outranks the derived verdicts for the same reason
    — but it ranks BELOW `applied` and `skipped`, and that is not arbitrary. Those two say what the
    owner DID with the lead; a report says the eligibility DECISION was wrong. A lead they actually
    applied to, or deliberately skipped, is filed under the action they took. **Nothing is lost by
    ranking it last of the three**: the `queue.reported.<job_id>` marker is the record a later
    investigation reads, and it survives whichever folder holds the copy (D-427). It must NOT reuse
    `_ineligible` — reconcile pulls those back out the moment the verdict clears, and a reported
    lead's verdict is still `eligible`, so it would return to the queue on the very next run.

    `closed` sits between the owner statements and the derived verdicts, and both boundaries are
    deliberate. It ranks BELOW them because an application the owner already sent is a fact about
    what they did and does not stop being true when the requisition comes down. It ranks ABOVE
    them because a closed posting cannot be applied to whatever the gate decided: filing it under
    `_ineligible` would claim a verdict the gate never reached, and filing it under `_review`
    would ask the owner to read a job that no longer exists.
    """
    if entry.job_id in applied:
        return APPLIED_DIR
    if entry.job_id in skipped:
        return SKIPPED_DIR
    if entry.job_id in reported:
        return REPORTED_DIR
    if entry.job_id in closed:
        return CLOSED_DIR
    if entry.job_id in ineligible:
        return INELIGIBLE_DIR
    if entry.job_id in review:
        return REVIEW_DIR
    return ""


def _consolidate_duplicates(
    duplicates: dict[int, tuple[_Entry, ...]],
    entries: dict[int, _Entry],
    by_job: dict[int, _Entry],
) -> tuple[int, list[LeadFailure]]:
    """Collapse folders that identity resolution converged onto ONE canonical job.

    **This is the only place this module deletes a lead folder, and the deletion is safe for a
    reason that does not generalise.** The queue holds COPIES — no `artifacts` row points into
    it, and `reconcile_queue`/`sync_queue` rebuild any folder from the store — and every folder
    reaching here is fully classified, so the "never delete what you cannot classify" rule is not
    engaged. What is removed is a SECOND copy of one job; the job keeps a folder.

    **The keeper is simply the first path, and which one survives is genuinely arbitrary.** Both
    folders are copies of one job; the relocation pass then moves the survivor to the planned
    name — free, because the duplicate that occupied it is gone — and the create/update pass
    re-stamps its `details.json` for the offered posting. Preferring the offered posting's folder
    was tried and no test could tell the two apart, which is the definition of a branch that is
    not earning its place. Sorting by path is what makes the choice deterministic across runs.
    There is no oscillation risk to guard against here: after this pass the job has ONE folder,
    so a second run finds no duplicate at all.

    Deleting is per-folder isolated: one unremovable directory must not cost the other leads, so
    it becomes a `LeadFailure` like any other and the survivor is still indexed.
    """
    retired = 0
    failures: list[LeadFailure] = []
    for job_id, group in sorted(duplicates.items()):
        keeper = group[0]
        by_job[job_id] = keeper
        for entry in group:
            if entry.path == keeper.path:
                continue
            try:
                shutil.rmtree(entry.path)
            except Exception as exc:  # one undeletable folder must never cost the rest
                failures.append(LeadFailure(posting_id=entry.posting_id, detail=_detail(exc)))
                continue
            # Drop the removed folder from the posting index too, or `_entry_for` hands the
            # create/update pass a path that no longer exists.
            if entries.get(entry.posting_id) is entry:
                del entries[entry.posting_id]
            retired += 1
    return retired, failures


def _relocate(src: Path, dst: Path) -> None:
    """Move a whole folder, refusing an occupied destination rather than merging into it."""
    if dst.exists():
        raise QueueConflictError(f"{dst.name} already exists at its destination")
    dst.parent.mkdir(parents=True, exist_ok=True)
    os.replace(src, dst)


# ----------------------------------------------------------------------------------- disk survey


def _index(root: Path) -> tuple[dict[int, _Entry], tuple[str, ...]]:
    """Every queue folder, keyed by the posting its own `details.json` claims.

    Never by folder name: design §4.1 is explicit that nothing derives data from a queue folder's
    name, because the name is lossy and the owner may well have renamed one. A folder that cannot
    identify itself is returned as unclassified and touched by nothing.

    Two folders claiming one posting is the one case where a claim is *withdrawn*: both are
    reported unclassified and neither is used, because picking one would silently orphan the
    other's contents and the owner is the only one who can say which is real.
    """
    entries: dict[int, _Entry] = {}
    unclassified: list[str] = []
    duplicated: set[int] = set()
    for location in _LOCATIONS:
        base = root / location if location else root
        for path in _child_dirs(base):
            label = f"{location}/{path.name}" if location else path.name
            details = _read_details(path)
            posting_id = None if details is None else _as_int(details.get("posting_id"))
            job_id = None if details is None else _as_int(details.get("job_id"))
            if posting_id is None or job_id is None:
                unclassified.append(label)
                continue
            if posting_id in duplicated:
                unclassified.append(label)
                continue
            claimed = entries.pop(posting_id, None)
            if claimed is not None:
                duplicated.add(posting_id)
                unclassified.append(_label(claimed, root))
                unclassified.append(label)
                continue
            entries[posting_id] = _Entry(
                path=path,
                location=location,
                posting_id=posting_id,
                job_id=job_id,
                content_hash=_as_str(details.get("content_hash")) if details else None,
            )
    return entries, tuple(unclassified)


def _resolve_job_identity(
    conn: Connection, entries: dict[int, _Entry]
) -> tuple[dict[int, _Entry], dict[int, _Entry], dict[int, tuple[_Entry, ...]]]:
    """Refresh each folder's job identity from the store, and index the folders by it as well.

    A folder records the `job_id` it was written under, and that answer GOES STALE. Identity
    resolution can converge a lane copy onto a native find, and then the posting's canonical job
    moves while `details.json` still names the old one. Run 139's measured case: posting 131367
    (a lane copy) now carries `job_id = 69007`, the native Workday find, and its folder still
    recorded 131367 — so the folder identified neither the posting `delivered_unapplied` offered
    (69007, because it deduplicates on `job_id`) nor the job it actually belongs to. The lead was
    reported as a failure and never got a folder.

    **`job_id` is already the identity everywhere else here**, which is why this reconciles TO it:
    `_wanted_location` tests `entry.job_id` against all five of its sets, `applications` keys on
    it, the skip state keys on it, and `delivered_unapplied` deduplicates on it. `_index` keying
    its dict on `posting_id` was the odd one out.

    Returns the entries with a refreshed `job_id`, a second index keyed by that job, and the
    groups where more than one folder resolved to one job.

    **The duplicates are RETURNED rather than dropped, and that is a correction.** Dropping them
    was believed to cost "nothing beyond leaving today's exact-posting behaviour in place", which
    is true when only ONE of the two postings has a folder. When BOTH do — the disambiguation
    pair, which is exactly what a shared company+title produces — the dropped job left
    `_entry_for` returning the OLD folder while the planned name pointed at the folder the other
    posting already occupied, and `_relocate` then refused an occupied destination on every run
    forever, because nothing here removed a folder and the losing posting was no longer offered.
    Measured: posting 131368, in every run from 140 to 144.
    """
    current = canonical_job_ids(conn, sorted({entry.posting_id for entry in entries.values()}))
    refreshed: dict[int, _Entry] = {}
    grouped: dict[int, list[_Entry]] = {}
    for posting_id, entry in entries.items():
        entry = replace(entry, job_id=current.get(posting_id, entry.job_id))
        refreshed[posting_id] = entry
        grouped.setdefault(entry.job_id, []).append(entry)
    by_job = {job_id: group[0] for job_id, group in grouped.items() if len(group) == 1}
    duplicates = {
        job_id: tuple(sorted(group, key=lambda e: e.path))
        for job_id, group in grouped.items()
        if len(group) > 1
    }
    return refreshed, by_job, duplicates


def _entry_for(
    row: QueueRow, entries: dict[int, _Entry], by_job: dict[int, _Entry]
) -> _Entry | None:
    """The folder that already holds this lead, by posting first and canonical job second.

    Exact posting first so a lead whose identity never moved keeps the folder it has and nothing
    renames itself; the job fallback only ever rescues a lead that would otherwise be reported as
    a failure and left with no folder at all.
    """
    return entries.get(row.posting_id) or by_job.get(row.job_id)


def _child_dirs(base: Path) -> list[Path]:
    """The lead folders directly under `base`, sorted for a deterministic report.

    Dot-prefixed names are skipped, which is what keeps a live `.staging-…` build out of the
    queue's own view of itself, and every drain is skipped so they are surveyed as locations
    rather than as leads. Miss one and `_index` reports the drain directory itself as
    `unclassified` — a field that means "a folder the owner must go and look at" — forever.
    """
    if not base.is_dir():
        return []
    return sorted(
        path
        for path in base.iterdir()
        if path.is_dir()
        and not path.name.startswith(".")
        and path.name not in DRAIN_DIRS
    )


def _label(entry: _Entry, root: Path) -> str:
    return str(entry.path.relative_to(root))


def _read_details(path: Path) -> dict[str, object] | None:
    """`details.json` as a mapping, or None for absent, unreadable or non-object content.

    Every failure mode collapses to None on purpose: the answer to all of them is the same, which
    is to leave the folder alone and report it.
    """
    try:
        parsed = json.loads((path / DETAILS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _as_int(value: object) -> int | None:
    """`value` if it is a real integer. `bool` is excluded: it is an `int` subclass, and `True`
    reading as posting 1 would attach a folder to whichever posting happens to be first."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _detail(exc: BaseException) -> str:
    """One line naming what went wrong, without pasting an absolute path into a report.

    `strerror` rather than `str(exc)` for an `OSError`, following `profile_bundle/locking.py`: the
    stringified form embeds the offending path, and a report the owner copies out of a terminal
    would carry their home directory with it. The lead is already identified by its posting id.
    """
    if isinstance(exc, OSError) and exc.strerror:
        return f"{type(exc).__name__}: {exc.strerror}"
    return f"{type(exc).__name__}: {exc}"


__all__ = [
    "APPLIED_DIR",
    "CLOSED_DIR",
    "DEFAULT_QUEUE_ROOT",
    "DETAILS_FILE",
    "INELIGIBLE_DIR",
    "REVIEW_DIR",
    "DETAILS_SCHEMA",
    "JD_FILE",
    "LINK_FILE",
    "LOCK_FILE",
    "RECLAIM_WINDOW_SECONDS",
    "REPORTED_DIR",
    "SKIPPED_DIR",
    "URL_FILE",
    "WEBLOC_FILE",
    "FolderFailure",
    "LeadFailure",
    "QueueConflictError",
    "QueueLockHeldError",
    "ReconcileReport",
    "SyncReport",
    "reconcile_queue",
    "sync_queue",
]
