"""Scan coordinator — D16's other half.

Builds each BoardRequest from provider.board_url(slug) + the http_cache row
for that exact URL (D22), dispatches fetches to the worker pool, applies each
returned snapshot serially via apply_board (the single writer), and finalizes
the runs row. insert_run happens at scan start so started_at is queryable
while the scan runs (§0.3).
"""

from __future__ import annotations

import json
import os
import socket
import time
from collections import defaultdict
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

from filelock import FileLock, Timeout
from sqlalchemy import Engine, func, select

from boardwatch.core.clock import utcnow
from boardwatch.core.lock_reclaim import RECLAIM_POLL_SECONDS, RECLAIM_WINDOW_SECONDS
from boardwatch.core.models import BoardRequest, BoardSnapshot
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.providers.base import Provider
from boardwatch.providers.registry import build_providers
from boardwatch.scan.apply import apply_board
from boardwatch.scan.workers import fetch_board_job
from boardwatch.store.db import ensure_schema
from boardwatch.store.queries import (
    RUN_FAILED,
    RUN_OK,
    finalize_run,
    finish_run,
    get_validators,
    get_watched_companies,
    insert_run,
)
from boardwatch.store.tables import postings

SCAN_LOCK_MESSAGE = "another scan is already running; try again when it finishes."


class ScanLockHeldError(Exception):
    """Raised when another scan process holds the scan lock (D20). Added in Task 9."""


def _lock_meta_path(lock_path: Path) -> Path:
    return lock_path.with_name(lock_path.name + ".meta")


def _write_lock_meta(meta_path: Path) -> None:
    """Best-effort, message-only sidecar (P3 slice 2 item 1). `filelock` is the sole lock
    authority — this file is never read to decide whether to acquire or release; it only lets a
    held lock name the blocking process. Written atomically (temp file + `os.replace`) so a
    reader never observes a partial write. A write failure must not abort the scan over a
    cosmetic feature, so it degrades to no sidecar (contention falls back to the generic
    message) rather than raising.
    """
    payload = {
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "started_at": utcnow().isoformat(),
    }
    tmp_path = meta_path.with_name(meta_path.name + ".tmp")
    try:
        tmp_path.write_text(json.dumps(payload))
        os.replace(tmp_path, meta_path)
    except OSError:
        pass


def _remove_lock_meta(meta_path: Path) -> None:
    """Best-effort removal; must never mask the run's actual outcome."""
    try:
        meta_path.unlink()
    except OSError:
        pass


def _lock_held_message(lock_path: Path, meta_path: Path) -> str:
    """Loud message naming the blocking pid/host/started_at when the sidecar is present and
    valid; the generic `SCAN_LOCK_MESSAGE` otherwise (missing, unreadable, or malformed sidecar —
    a stale/corrupt sidecar is cosmetic here, never a correctness issue, per D-043)."""
    try:
        payload = json.loads(meta_path.read_text())
        pid = payload["pid"]
        hostname = payload["hostname"]
        started_at = payload["started_at"]
    except (OSError, ValueError, KeyError, TypeError):
        return SCAN_LOCK_MESSAGE
    return (
        f"another scan is already running — held by pid {pid} on {hostname} since "
        f"{started_at}. If that process is gone, the lock is stale; remove {lock_path} "
        "to clear it."
    )


def is_systemic_scan_outage(*, attempted: int, complete: int, unchanged: int) -> bool:
    """CLAUDE.md's fail-safe table: "systemic outage => fatal (prevents the silent empty day)".

    Boards were attempted and NOT ONE completed (nor was left unchanged) is a DNS/network
    failure, not a few dead slugs. A few dead boards are NOT this: Workday returns `partial`
    routinely, and only "attempted some, completed/unchanged none" is the outage. This is the
    single predicate both `run_scan` (standalone) and `run_pipeline` classify a run's outcome
    by, so the two callers can never disagree on the same event (D-037).
    """
    return attempted > 0 and complete == 0 and unchanged == 0


@dataclass
class ProviderFetchCost:
    """What one provider's boards cost this run, in FETCH wall clock.

    `untimed` is its own field rather than an absence: a snapshot reaching the coordinator
    with `fetch_seconds is None` did not go through the timing seam (the belt-and-braces
    worker-error fallback builds one directly), and folding those into `seconds` as 0.0 would
    quietly understate the total. A reader can then see that the number is partial.
    """

    boards: int = 0
    seconds: float = 0.0
    untimed: int = 0


@dataclass
class ScanSummary:
    companies: int = 0
    providers: int = 0
    complete: int = 0
    partial: int = 0
    failed: int = 0
    unchanged: int = 0
    new: int = 0
    closed: int = 0
    reopened: int = 0
    postings_seen: int = 0
    open_postings: int = 0
    # FETCH wall clock per provider (D-330). Keyed by `BoardRequest.provider`, so a provider
    # that contributed no work is absent rather than present at zero.
    fetch_cost: dict[str, ProviderFetchCost] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    # Set once the runs row exists. The pipeline reads it rather than minting its own, so the
    # INSERT stays inside the scan lock (see pipeline/runner.py).
    run_id: int = 0


def default_providers() -> dict[str, Provider]:
    return build_providers()


def run_scan(
    engine: Engine,
    settings: Settings,
    *,
    fetcher: Fetcher | None = None,
    providers: dict[str, Provider] | None = None,
    company: str | None = None,
    provider: str | None = None,
    finish: bool = True,
) -> ScanSummary:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    lock_path = settings.data_dir / "scan.lock"
    meta_path = _lock_meta_path(lock_path)
    lock = FileLock(str(lock_path))
    # Before schema setup, the runs insert, any fetch (D20) — and re-asked until a deadline rather
    # than believed on the first refusal (D-227). A scan killed mid-run leaves Windows tearing its
    # handles down asynchronously, and during that window `filelock` reports `Timeout` for a lock
    # nobody holds; believing it would refuse the next scheduled scan and write nothing, which on
    # the unattended path is a silent empty day rather than a visible failure. The window is zero
    # off Windows, so POSIX asks exactly once and this stays the fail-fast path state test j
    # measures.
    deadline = time.monotonic() + RECLAIM_WINDOW_SECONDS
    while True:
        try:
            lock.acquire(blocking=False)
        except Timeout as exc:
            if time.monotonic() >= deadline:
                raise ScanLockHeldError(_lock_held_message(lock_path, meta_path)) from exc
            time.sleep(RECLAIM_POLL_SECONDS)
            continue
        break
    _write_lock_meta(meta_path)  # message-only; never governs the lock itself
    try:
        return _run_scan_locked(
            engine,
            settings,
            fetcher or Fetcher(settings),
            providers or default_providers(),
            company,
            provider,
            finish,
        )
    finally:
        _remove_lock_meta(meta_path)
        lock.release()


def _run_scan_locked(
    engine: Engine,
    settings: Settings,
    fetcher: Fetcher,
    providers: dict[str, Provider],
    company: str | None,
    provider: str | None,
    finish: bool = True,
) -> ScanSummary:
    ensure_schema(engine)  # deferred to inside the lock: a REJECTED scan writes nothing
    summary = ScanSummary()

    with engine.connect() as conn:
        company_rows = get_watched_companies(conn, slug=company, provider=provider)
    # The insert stays INSIDE the lock, so a scan rejected for contention writes nothing at
    # all. `finish=False` means this scan is stage one of a pipeline: it records its counts
    # but the pipeline stamps finished_at, so a run is not "finished" the moment scan returns.
    active_run_id = insert_run(engine)
    summary.run_id = active_run_id
    try:
        return _scan_body(
            engine, settings, fetcher, providers, company, provider,
            summary, company_rows, active_run_id, finish,
        )
    except BaseException as exc:
        # The row exists from here on, and on an exception the caller never learns its id —
        # `run_scan` returns nothing to read `ScanSummary.run_id` from. So the scan closes it
        # itself, unconditionally, even when `finish=False`. Without this, Ctrl-C during the
        # multi-board fetch loop leaves a row that `doctor` reports as in progress forever,
        # one more per retry. This is the scan-side half of the same guard the pipeline holds.
        # `failed`, not the default `ok`: this row is closed with a finished_at, so nothing
        # downstream can tell it apart from a clean run by timestamps alone — `doctor` looks
        # only for a NULL finished_at. Under `boardwatch run` the scan is called outside the
        # pipeline's own try, so this handler is the ONLY place a scan abort is ever recorded.
        finish_run(
            engine, active_run_id, errors=[f"scan: aborted: {exc!r}"], status=RUN_FAILED
        )
        raise


def _scan_body(
    engine: Engine,
    settings: Settings,
    fetcher: Fetcher,
    providers: dict[str, Provider],
    company: str | None,
    provider: str | None,
    summary: ScanSummary,
    company_rows: Sequence[Any],
    active_run_id: int,
    finish: bool,
) -> ScanSummary:

    work: list[tuple[Any, Provider, BoardRequest]] = []
    with engine.connect() as conn:
        company_ids = [row.id for row in company_rows]
        grouped: dict[int, set[str]] = defaultdict(set)
        if company_ids:
            for r in conn.execute(
                select(postings.c.company_id, postings.c.provider_posting_id).where(
                    postings.c.company_id.in_(company_ids),
                    postings.c.status == "open",
                )
            ).all():
                grouped[r.company_id].add(str(r.provider_posting_id))
        for row in company_rows:
            prov = providers.get(row.provider)
            if prov is None:
                summary.errors.append(f"{row.slug}: unknown provider {row.provider!r}")
                continue
            try:
                url = prov.board_url(row.slug)
            except Exception as exc:  # a malformed stored slug is one board, not the run
                summary.errors.append(f"{row.slug}: invalid board target: {exc}")
                summary.failed += 1
                # ATTEMPTED, because it produced a `failed` outcome: leaving it out of
                # `companies` made the report self-contradictory (outcomes > scanned) and
                # under-counted runs.boards_attempted. The unknown-provider branch above
                # deliberately records neither — a config error was never attempted.
                summary.companies += 1
                continue
            work.append(
                (
                    row,
                    prov,
                    BoardRequest(
                        provider=row.provider, slug=row.slug, url=url,
                        validators=get_validators(
                            conn, url, max_age=timedelta(hours=settings.validator_max_age_hours)
                        ),
                        known_posting_ids=frozenset(grouped.get(row.id, ())),
                        detail_budget=settings.detail_fetch_budget,
                    ),
                )
            )
    summary.companies += len(work)
    summary.providers = len({row.provider for row, _, _ in work})

    with ThreadPoolExecutor(max_workers=settings.scan_workers) as pool:
        future_map = {
            pool.submit(fetch_board_job, prov, fetcher, request): (row, request)
            for row, prov, request in work
        }
        for future in as_completed(future_map):
            row, request = future_map[future]
            try:
                snapshot = future.result()
            except Exception as exc:  # providers map failures themselves; belt-and-braces
                snapshot = BoardSnapshot(
                    status="failed", postings=[], url=request.url,
                    observed_validators=None, error=f"unexpected worker error: {exc}",
                )
            # Accounted BEFORE the apply, and outside its try: the fetch already cost the run
            # its seconds whether or not the apply then succeeds, and attributing cost only to
            # boards that applied cleanly would hide the expensive failures.
            cost = summary.fetch_cost.setdefault(request.provider, ProviderFetchCost())
            cost.boards += 1
            if snapshot.fetch_seconds is None:
                cost.untimed += 1
            else:
                cost.seconds += snapshot.fetch_seconds
            try:
                result = apply_board(engine, snapshot, row.id, active_run_id)
            except Exception as exc:  # noqa: BLE001 - one board's apply must not abort the scan
                # A single board's apply failing — a data quirk tripping a DB constraint, as a
                # duplicate Workable shortcode did — must cost that board its reach and nothing
                # else, the same isolation the fetch path above already gives and the "additive
                # breadth never fails the run" rule the lanes follow. apply_board's transaction has
                # rolled back, so no partial rows survive; the next board opens a fresh one.
                summary.failed += 1
                summary.errors.append(f"{row.slug}: apply failed: {exc!r}")
                continue
            summary.postings_seen += result.listed
            summary.new += result.new
            summary.closed += result.closed
            summary.reopened += result.reopened
            if result.status == "complete":
                summary.complete += 1
            elif result.status == "partial":
                summary.partial += 1
            elif result.status == "unchanged":
                summary.unchanged += 1
            else:
                summary.failed += 1
                summary.errors.append(f"{row.slug}: {snapshot.error}")

    with engine.connect() as conn:
        summary.open_postings = int(
            conn.execute(
                select(func.count()).select_from(postings).where(postings.c.status == "open")
            ).scalar_one()
        )
    finalize_run(
        engine, active_run_id,
        boards_attempted=summary.companies,
        boards_complete=summary.complete,
        boards_partial=summary.partial,
        boards_unchanged=summary.unchanged,
        boards_failed=summary.failed,
        postings_seen=summary.postings_seen,
        new_count=summary.new,
        closed_count=summary.closed,
        reopened_count=summary.reopened,
        errors=summary.errors,
        finished=finish,
        # CLAUDE.md's fail-safe table: "systemic outage => fatal". `run_pipeline` already
        # classifies this exact state as fatal via the same `is_systemic_scan_outage`
        # predicate (D-037), so the SAME event can never record `ok` under `boardwatch scan`
        # and `failed` under `boardwatch run`.
        status=(
            RUN_FAILED
            if is_systemic_scan_outage(
                attempted=summary.companies,
                complete=summary.complete,
                unchanged=summary.unchanged,
            )
            else RUN_OK
        ),
    )
    return summary
