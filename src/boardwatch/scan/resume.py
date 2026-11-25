"""Continue an interrupted pipeline scan under its own run id (T353).

Each board's apply commits in one transaction with its `board_scans` row (`scan/apply.py`), so a
scan killed partway leaves every board either fully applied or untouched, and the row is the
marker. A plain retry mints a new run and reads every board again. A board that completed before
the kill then takes a second miss for one absence in one night, and `CLOSE_AFTER_MISSES` is 2.
`run --continue-scan` instead picks up the killed run and fetches only the boards it never
settled. Board level only: there is no cursor inside a board.

The retry must be the SAME scan. At scan start the coordinator writes a manifest of what the
scan was asked to do. The retry computes its own, and any field that differs refuses the resume
by that field's name before anything is written. The operator then runs fresh, as today.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from alembic.migration import MigrationContext
from sqlalchemy import Connection, Engine, exists, func, select

from boardwatch.core.settings import Settings
from boardwatch.eligibility.engine import digest_of_sources
from boardwatch.store.db import schema_revision
from boardwatch.store.tables import board_scans, posting_events, postings, runs, scan_manifests

#: A same-night retry, never the next night's tick (04:00): a run that started longer ago than
#: this is not resumed, whatever else matches.
RESUME_WINDOW = timedelta(hours=12)

#: The event types a scan's `new`, `closed` and `reopened` counts are made of (`scan/apply.py`).
_COUNTED_EVENTS = ("new", "closed", "reopened")


class ScanResumeRefusedError(Exception):
    """`--continue-scan` found no run it may continue. Raised before anything is written.

    `field` names the manifest field that differs, when that is the reason, so the refusal is
    typed at the raise site rather than told apart by its message.
    """

    def __init__(self, reason: str, *, field: str | None = None) -> None:
        super().__init__(f"--continue-scan refused: {reason}. Run without it to scan fresh.")
        self.field = field


@dataclass(frozen=True)
class ScanManifest:
    """What one scan was asked to do. Two scans with equal manifests read the same boards the
    same way, so the second may carry on from the first's committed boards."""

    #: `(id, provider, slug, name)` per board: a slug edited in place keeps its id but reads a
    #: different listing, and the name feeds the posting identities the apply writes.
    boards: tuple[tuple[int, str, str, str], ...]
    company: str | None
    provider: tuple[str, ...] | None
    listing_gate_key: str
    location_filter_mode: str
    detail_fetch_budget: int
    validator_max_age_hours: int
    scan_code: str

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SettledBoard:
    """A board the run already committed. Its effects are applied, so it is never fetched again
    under this run, whatever its status: a `failed` one is carried, and retried the next night."""

    company_id: int
    status: str
    postings_listed: int
    error: str | None
    dead: bool
    empty_guarded: bool


@dataclass(frozen=True)
class ResumePoint:
    run_id: int
    settled: tuple[SettledBoard, ...]


def _scan_sources() -> list[Path]:
    root = Path(__file__).resolve().parent.parent
    files = [path for package in ("scan", "providers", "rank")
             for path in sorted((root / package).glob("*.py"))]
    return [*files, root / "core" / "politeness.py"]


@lru_cache(maxsize=1)
def scan_code_digest() -> str:
    """A digest of the code that fetches and applies a board: the `scan` and `providers` packages,
    `core/politeness.py`, and `rank`, whose vetoes the listing gate runs (the gate key digests
    only the gate's inputs). `engine_version()` digests only the eligibility modules, so it
    cannot see a scan change. Through the same `digest_of_sources`, so a comment or formatting
    edit does not change it and a semantic one does.
    """
    return digest_of_sources([path.read_text(encoding="utf-8") for path in _scan_sources()])


def scan_manifest(
    company_rows: Sequence[Any],
    company: str | None,
    provider: str | Sequence[str] | None,
    listing_gate_key: str,
    settings: Settings,
) -> ScanManifest:
    providers = None
    if provider is not None:
        providers = tuple(sorted([provider] if isinstance(provider, str) else provider))
    return ScanManifest(
        boards=tuple(sorted(
            (int(row.id), str(row.provider), str(row.slug), str(row.name)) for row in company_rows
        )),
        company=company,
        provider=providers,
        listing_gate_key=listing_gate_key,
        location_filter_mode=settings.location_filter_mode,
        detail_fetch_budget=settings.detail_fetch_budget,
        validator_max_age_hours=settings.validator_max_age_hours,
        scan_code=scan_code_digest(),
    )


def _normalized(manifest: dict[str, Any]) -> dict[str, Any]:
    """The stored JSON reads tuples back as lists; compare in one shape."""
    normalized: dict[str, Any] = json.loads(json.dumps(manifest))
    return normalized


def require_current_schema(engine: Engine) -> None:
    """Refuse a resume against a store the bundled migrations have not reached, before
    `ensure_schema` would migrate it: a refused resume writes nothing, a migration included. Such
    a store has no manifest from this code anyway, so nothing on it could be continued.
    """
    database = engine.url.database
    if not database or not Path(database).exists():
        raise ScanResumeRefusedError("there is no store to continue a scan in")
    with engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
    if current != schema_revision():
        raise ScanResumeRefusedError(
            f"the store is at schema {current or 'none'}, not {schema_revision()}"
        )


def resolve_resume(conn: Connection, manifest: ScanManifest, now: datetime) -> ResumePoint:
    """The run `--continue-scan` continues, or a refusal saying why. Reads only.

    The NEWEST scan's manifest, never an older unfinished one: a fresh scan that ran after the
    kill has already read every board, so continuing the killed run behind it would charge its
    boards a second miss, the double count this exists to remove.
    """
    newest = conn.execute(
        select(
            scan_manifests.c.run_id,
            scan_manifests.c.manifest_json,
            scan_manifests.c.scan_finalized_at,
            runs.c.started_at,
        )
        .join(runs, runs.c.id == scan_manifests.c.run_id)
        .order_by(scan_manifests.c.run_id.desc())
        .limit(1)
    ).first()
    if newest is None:
        raise ScanResumeRefusedError("no scan has a manifest to continue")
    run_id = int(newest.run_id)
    if newest.scan_finalized_at is not None:
        raise ScanResumeRefusedError(f"run {run_id}'s scan finished; there is nothing to continue")
    if newest.started_at < now - RESUME_WINDOW:
        raise ScanResumeRefusedError(
            f"run {run_id} started at {newest.started_at:%Y-%m-%d %H:%M} UTC, more than "
            f"{RESUME_WINDOW.total_seconds() / 3600:g} h ago"
        )
    pipeline_boards = exists().where(
        board_scans.c.run_id == run_id,
        board_scans.c.scan_kind == "board",
        board_scans.c.pipeline_scan.is_(True),
    )
    if not conn.execute(select(pipeline_boards)).scalar():
        raise ScanResumeRefusedError(f"run {run_id} committed no pipeline board scan")
    stored = _normalized(dict(newest.manifest_json))
    current = _normalized(manifest.as_json())
    for name in current:
        if stored.get(name) != current[name]:
            raise ScanResumeRefusedError(
                f"{name} differs from run {run_id}'s manifest", field=name
            )
    rows = conn.execute(
        select(
            board_scans.c.company_id,
            board_scans.c.status,
            board_scans.c.postings_listed,
            board_scans.c.error,
            board_scans.c.dead,
            board_scans.c.empty_guarded,
        ).where(board_scans.c.run_id == run_id, board_scans.c.scan_kind == "board")
    ).all()
    return ResumePoint(
        run_id=run_id,
        settled=tuple(
            SettledBoard(
                company_id=int(r.company_id),
                status=str(r.status),
                postings_listed=int(r.postings_listed or 0),
                error=r.error,
                dead=bool(r.dead),
                empty_guarded=bool(r.empty_guarded),
            )
            for r in rows
        ),
    )


def settled_event_counts(
    conn: Connection, run_id: int, company_ids: Sequence[int]
) -> Counter[str]:
    """The `new`, `closed` and `reopened` events the settled boards wrote under this run."""
    if not company_ids:
        return Counter()
    rows = conn.execute(
        select(posting_events.c.kind, func.count())
        .join(postings, postings.c.id == posting_events.c.posting_id)
        .where(
            posting_events.c.run_id == run_id,
            posting_events.c.kind.in_(_COUNTED_EVENTS),
            postings.c.company_id.in_(list(company_ids)),
        )
        .group_by(posting_events.c.kind)
    ).all()
    return Counter({str(event): int(count) for event, count in rows})
