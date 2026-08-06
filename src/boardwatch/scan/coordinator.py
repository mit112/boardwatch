"""Scan coordinator — D16's other half.

Builds each BoardRequest from provider.board_url(slug) + the http_cache row
for that exact URL (D22), dispatches fetches to the worker pool, applies each
returned snapshot serially via apply_board (the single writer), and finalizes
the runs row. insert_run happens at scan start so started_at is queryable
while the scan runs (§0.3).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from filelock import FileLock, Timeout
from sqlalchemy import Engine, func, select

from boardwatch.core.models import BoardRequest, BoardSnapshot
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.providers.base import Provider
from boardwatch.providers.registry import build_providers
from boardwatch.scan.apply import apply_board
from boardwatch.scan.workers import fetch_board_job
from boardwatch.store.db import ensure_schema
from boardwatch.store.queries import (
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
    lock = FileLock(str(settings.data_dir / "scan.lock"))
    try:
        lock.acquire(blocking=False)  # before schema setup, the runs insert, any fetch (D20)
    except Timeout as exc:
        raise ScanLockHeldError(SCAN_LOCK_MESSAGE) from exc
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
        finish_run(engine, active_run_id, errors=[f"scan: aborted: {exc!r}"])
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
                        validators=get_validators(conn, url),
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
            result = apply_board(engine, snapshot, row.id, active_run_id)
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
        postings_seen=summary.postings_seen,
        new_count=summary.new,
        closed_count=summary.closed,
        reopened_count=summary.reopened,
        errors=summary.errors,
        finished=finish,
    )
    return summary
