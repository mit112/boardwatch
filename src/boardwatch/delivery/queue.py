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
from dataclasses import dataclass
from pathlib import Path
from secrets import token_hex

from filelock import FileLock, Timeout
from sqlalchemy import Connection, select

from boardwatch.core.lock_reclaim import RECLAIM_POLL_SECONDS, RECLAIM_WINDOW_SECONDS
from boardwatch.delivery import DRAIN_DIRS, LeadNames, plan_lead_names
from boardwatch.delivery.review_gate import REVIEW_DIR, lane
from boardwatch.store.applications import applied_job_ids
from boardwatch.store.delivery_queries import (
    QueueRow,
    delivered_unapplied,
    ineligible_job_ids,
    queue_detail,
    review_job_ids,
)
from boardwatch.store.queue_state import skipped_job_ids
from boardwatch.store.run_funnel_queries import TAILORED_KIND
from boardwatch.store.tables import artifacts

#: Where the queue lives unless a caller says otherwise (design §4). A constant rather than a
#: `Settings` field: adding one has four separately gated registration sites, and nothing here
#: needs to be configurable through a file to be overridden — every entry point takes `root`.
DEFAULT_QUEUE_ROOT = Path.home() / "boardwatch-queue"

LOCK_FILE = ".queue.lock"
APPLIED_DIR = "_applied"
SKIPPED_DIR = "_skipped"
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
_NO_CURRENT_VERSION = "no_current_version"


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
    """

    created: int = 0
    updated: int = 0
    unchanged: int = 0
    moved: int = 0
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
    to_ineligible: int = 0
    to_review: int = 0
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
            + self.to_ineligible
            + self.to_review
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
    just said it is neither applied nor skipped and creating a second folder for it would be the
    one outcome worse than a stale one. `reconcile_queue` applies the same rule from the other
    side; both hold the same lock, so they cannot disagree mid-flight, and neither depends on the
    other having run first.

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
    claim decides where the folder lives.

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
    rows = [
        row
        for row in delivered_unapplied(conn, skipped=set(skipped_job_ids(conn)))
        if row.verdict != "ineligible"
    ]
    lane_of = {
        row.posting_id: lane(
            verdict=row.verdict,
            locations=row.locations,
            title=row.title,
            experience_unconfirmed=row.requirement_flags.experience_unconfirmed,
            eligibility_unconfirmed=row.requirement_flags.eligibility_unconfirmed,
        )
        for row in rows
    }
    artifact_ids = _tailored_artifact_ids(conn)
    entries, _ = _index(root)
    planned, failures = _plan(rows, root=root, owner_name=owner_name)
    failed = {failure.posting_id for failure in failures}

    moved = 0
    for row in rows:
        names = planned.get(row.posting_id)
        entry = entries.get(row.posting_id)
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
                entry = entries.get(row.posting_id)
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
    shared = Counter(names.folder for names in first.values() if names is not None)
    planned: dict[int, LeadNames] = {}
    for row in rows:
        names = first[row.posting_id]
        if names is None:
            continue
        if shared[names.folder] == 1:
            planned[row.posting_id] = names
            continue
        suffix = identities[row.posting_id][:8]
        retried = attempt(row, f"{row.title} {suffix}")
        if retried is not None:
            planned[row.posting_id] = retried
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
        "job_description_absent_reason": None if jd is not None else _NO_CURRENT_VERSION,
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
    ineligible = ineligible_job_ids(conn)
    review = review_job_ids(conn)
    entries, unclassified = _index(root)
    counts = {APPLIED_DIR: 0, SKIPPED_DIR: 0, INELIGIBLE_DIR: 0, REVIEW_DIR: 0, "": 0}
    failures: list[FolderFailure] = []
    for entry in sorted(entries.values(), key=lambda item: item.posting_id):
        wanted = _wanted_location(
            entry, applied=applied, skipped=skipped, ineligible=ineligible, review=review
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
        to_ineligible=counts[INELIGIBLE_DIR],
        to_review=counts[REVIEW_DIR],
        to_queue=counts[""],
        unclassified=unclassified,
        failures=tuple(failures),
    )


def _wanted_location(
    entry: _Entry,
    *,
    applied: dict[int, str],
    skipped: dict[int, str],
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
    """
    if entry.job_id in applied:
        return APPLIED_DIR
    if entry.job_id in skipped:
        return SKIPPED_DIR
    if entry.job_id in ineligible:
        return INELIGIBLE_DIR
    if entry.job_id in review:
        return REVIEW_DIR
    return ""


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
    "DEFAULT_QUEUE_ROOT",
    "DETAILS_FILE",
    "INELIGIBLE_DIR",
    "REVIEW_DIR",
    "DETAILS_SCHEMA",
    "JD_FILE",
    "LINK_FILE",
    "LOCK_FILE",
    "RECLAIM_WINDOW_SECONDS",
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
