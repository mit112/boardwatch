"""Scan coordinator — D16's other half.

Builds each BoardRequest from provider.board_url(slug) + the http_cache row
for that exact URL (D22), dispatches fetches to the worker pool, applies each
returned snapshot serially via apply_board (the single writer), and finalizes
the runs row. insert_run happens at scan start so started_at is queryable
while the scan runs (§0.3).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from filelock import FileLock, Timeout
from sqlalchemy import Engine, func, select

from boardwatch.core.models import BoardRequest, BoardSnapshot
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.providers.base import Provider
from boardwatch.providers.greenhouse import GreenhouseProvider
from boardwatch.scan.apply import apply_board
from boardwatch.scan.workers import fetch_board_job
from boardwatch.store.db import ensure_schema
from boardwatch.store.queries import (
    finalize_run,
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


def default_providers() -> dict[str, Provider]:
    from boardwatch.providers.lever import LeverProvider
    return {"greenhouse": GreenhouseProvider(), "lever": LeverProvider()}


def run_scan(
    engine: Engine,
    settings: Settings,
    *,
    fetcher: Fetcher | None = None,
    providers: dict[str, Provider] | None = None,
    company: str | None = None,
    provider: str | None = None,
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
) -> ScanSummary:
    ensure_schema(engine)  # deferred to inside the lock: a REJECTED scan writes nothing
    summary = ScanSummary()

    with engine.connect() as conn:
        company_rows = get_watched_companies(conn, slug=company, provider=provider)
    run_id = insert_run(engine)

    work: list[tuple[Any, Provider, BoardRequest]] = []
    with engine.connect() as conn:
        for row in company_rows:
            prov = providers.get(row.provider)
            if prov is None:
                summary.errors.append(f"{row.slug}: unknown provider {row.provider!r}")
                continue
            url = prov.board_url(row.slug)
            work.append(
                (
                    row,
                    prov,
                    BoardRequest(
                        provider=row.provider, slug=row.slug, url=url,
                        validators=get_validators(conn, url),
                    ),
                )
            )
    summary.companies = len(work)
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
            result = apply_board(engine, snapshot, row.id, run_id)
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
        engine, run_id,
        boards_attempted=summary.companies,
        boards_complete=summary.complete,
        postings_seen=summary.postings_seen,
        new_count=summary.new,
        closed_count=summary.closed,
        reopened_count=summary.reopened,
        errors=summary.errors,
    )
    return summary
