"""Read-only board and provider health for the web Runs page (T305).

Two facts per watched board, from two tables that are written at different moments:

* `companies.last_health` is what the doctor probe last saw (`ok|empty|dead|error|unreachable`,
  NULL for a board never probed). Doctor is its sole writer.
* the board's LATEST `board_scans` row (`scan_kind = 'board'`) is what the last scan did.

**Latest row per company, never the history.** `board_scans` holds ~600k rows and has no index
that leads with `company_id`, so a per-company lookup would be one full scan per board. Instead
one grouped `MAX(id)` pass (a single scan, ~50 ms warm on the live store) names every company's
latest row and a join reads just those ~5k rows. Nothing here walks the table twice for the same
fact, and `scan_kind = 'lane'` rows are excluded: a lane that touches a watched board writes a
second row for it, and that row says nothing about the board's own listing.

**Scan length comes from the latest scan that actually read the board.** A scan the board
answered `304` for (`unchanged`) takes milliseconds, so taking the newest row would make every
slow board look fast. The second grouped pass skips `unchanged`.

**Unwatched boards are out.** Only watched boards are scanned or probed, so an unwatched
`companies` row that still reads `dead` is a stale label, not a board anyone is waiting on.

**What each status asks the owner to do** is decided here, in one table, so the page cannot
disagree with the test that pins it. A status outside the closed catalogs maps to `unknown`
(shown as "unknown status"); it is never dropped.

**`listing_gated` is not a failure.** It counts listings the scan's own `listing_gate` setting
skipped by design (D-663), so it is reported per provider as a count and never raises a board
row: hundreds of healthy Workday boards would drown the boards that need an action.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, func, select

from boardwatch.store.tables import board_scans, companies

# The closed catalogs, as the CheckConstraints on the two tables spell them. A value outside
# either is classified `unknown`, so a future status is shown rather than silently healthy.
KNOWN_HEALTH = frozenset({"ok", "empty", "dead", "error", "unreachable"})
KNOWN_SCAN_STATUS = frozenset({"complete", "partial", "failed", "unchanged"})

# issue -> (label, what to do). Order is severity: the page lists the worst first.
ISSUES: dict[str, tuple[str, str]] = {
    "dead": ("dead", "remove the board or fix its slug"),
    "unreachable": ("unreachable", "the provider did not answer; wait and retry next run"),
    "error": ("failing", "check the board; retry next run"),
    "mismatch": ("count mismatch", "postings may be missing; re-scan"),
    "partial": ("partial scan", "the scan stopped early; retry next run"),
    "empty": ("empty", "the board lists no postings; wait, or remove it if it stays empty"),
    "unknown": ("unknown status", "the status is not recognised; check the board by hand"),
}
ISSUE_ORDER = {issue: rank for rank, issue in enumerate(ISSUES)}

SLOWEST_LIMIT = 10
ERROR_MAX_CHARS = 240


@dataclass(frozen=True)
class _Scan:
    status: str
    dead: bool
    error: str | None
    reported_total: int | None
    enumerated: int | None
    listing_gated: int | None
    started_at: datetime
    finished_at: datetime


def classify_board(
    last_health: str | None, scan: _Scan | None
) -> str | None:
    """The one issue a board needs acted on, or None when it is healthy.

    Precedence is by what the owner would do first: a dead board is removed whatever else is
    true of it; a failing or unreachable one is retried; a count mismatch is a re-scan; a
    partial scan without a mismatch is a retry; an empty board is waited on. The doctor probe
    and the scan can disagree (a board the probe calls dead whose scan completed); the row
    carries both so the owner sees it.
    """
    if last_health is not None and last_health not in KNOWN_HEALTH:
        return "unknown"
    if scan is not None and scan.status not in KNOWN_SCAN_STATUS:
        return "unknown"
    if last_health == "dead" or (scan is not None and scan.dead):
        return "dead"
    if last_health == "unreachable":
        return "unreachable"
    if last_health == "error" or (scan is not None and scan.status == "failed"):
        return "error"
    if scan is not None and _missing(scan) is not None:
        return "mismatch"
    if scan is not None and scan.status == "partial":
        return "partial"
    if last_health == "empty":
        return "empty"
    return None


def _missing(scan: _Scan) -> int | None:
    """`reported - enumerated` when the board stated a total AND the scan counted, and they
    differ; None otherwise. Positive means postings the scan did not reach. NULL on either side
    is "not measured", which is a different claim from agreeing, so it never flags."""
    if scan.reported_total is None or scan.enumerated is None:
        return None
    gap = scan.reported_total - scan.enumerated
    return gap if gap != 0 else None


def _latest(conn: Connection, *, read_only: bool) -> dict[int, _Scan]:
    """The newest board-kind scan row per company. `read_only` skips `unchanged` rows."""
    newest = select(func.max(board_scans.c.id).label("mid")).where(
        board_scans.c.scan_kind == "board"
    )
    if read_only:
        newest = newest.where(board_scans.c.status != "unchanged")
    newest_sq = newest.group_by(board_scans.c.company_id).subquery()
    rows = conn.execute(
        select(
            board_scans.c.company_id,
            board_scans.c.status,
            board_scans.c.dead,
            board_scans.c.error,
            board_scans.c.board_reported_total,
            board_scans.c.board_enumerated,
            board_scans.c.listing_gated,
            board_scans.c.started_at,
            board_scans.c.finished_at,
        ).join_from(board_scans, newest_sq, board_scans.c.id == newest_sq.c.mid)
    ).all()
    return {
        int(r.company_id): _Scan(
            status=str(r.status),
            dead=bool(r.dead),
            error=r.error,
            reported_total=r.board_reported_total,
            enumerated=r.board_enumerated,
            listing_gated=r.listing_gated,
            started_at=r.started_at,
            finished_at=r.finished_at,
        )
        for r in rows
    }


def _iso(dt: datetime) -> str:
    return dt.isoformat() + "+00:00"  # the store's convention is naive UTC


def load_board_health(conn: Connection) -> dict[str, Any]:
    """Per-provider rollup, the boards that need an action, and the slowest boards."""
    watched = conn.execute(
        select(companies.c.id, companies.c.name, companies.c.provider, companies.c.slug,
               companies.c.last_health).where(companies.c.watched.is_(True))
    ).all()
    latest = _latest(conn, read_only=False)
    latest_read = _latest(conn, read_only=True)

    providers: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "boards": 0,
            "healthy": 0,
            **{issue: 0 for issue in ISSUES},
            "gated_boards": 0,
            "gated_postings": 0,
            "scans_timed": 0,
            "seconds_total": 0.0,
            "seconds_max": 0.0,
        }
    )
    problems: list[dict[str, Any]] = []
    timed: list[dict[str, Any]] = []

    for co in watched:
        scan = latest.get(int(co.id))
        row = providers[str(co.provider)]
        row["boards"] += 1
        issue = classify_board(co.last_health, scan)
        if issue is None:
            row["healthy"] += 1
        else:
            row[issue] += 1
            label, action = ISSUES[issue]
            problems.append(
                {
                    "company_id": int(co.id),
                    "name": str(co.name),
                    "provider": str(co.provider),
                    "slug": str(co.slug),
                    "issue": issue,
                    "label": label,
                    "action": action,
                    "last_health": co.last_health,
                    "scan_status": None if scan is None else scan.status,
                    "error": None
                    if scan is None or scan.error is None
                    else scan.error[:ERROR_MAX_CHARS],
                    "reported_total": None if scan is None else scan.reported_total,
                    "enumerated": None if scan is None else scan.enumerated,
                    "missing": None if scan is None else _missing(scan),
                    "scanned_at": None if scan is None else _iso(scan.finished_at),
                }
            )
        if scan is not None and scan.listing_gated:
            row["gated_boards"] += 1
            row["gated_postings"] += scan.listing_gated
        read = latest_read.get(int(co.id))
        if read is not None:
            seconds = max(0.0, (read.finished_at - read.started_at).total_seconds())
            row["scans_timed"] += 1
            row["seconds_total"] += seconds
            row["seconds_max"] = max(row["seconds_max"], seconds)
            timed.append(
                {
                    "company_id": int(co.id),
                    "name": str(co.name),
                    "provider": str(co.provider),
                    "seconds": round(seconds, 3),
                    "scan_status": read.status,
                    "scanned_at": _iso(read.finished_at),
                }
            )

    problems.sort(key=lambda p: (ISSUE_ORDER[p["issue"]], p["provider"], p["name"].lower()))
    timed.sort(key=lambda t: (-t["seconds"], t["provider"], t["name"].lower()))
    out_providers = []
    for name in sorted(providers):
        row = providers[name]
        timed_n = row.pop("scans_timed")
        total = row.pop("seconds_total")
        out_providers.append(
            {
                "provider": name,
                **row,
                "seconds_avg": round(total / timed_n, 3) if timed_n else None,
                "seconds_max": round(row["seconds_max"], 3) if timed_n else None,
            }
        )
    return {
        "providers": out_providers,
        "boards": problems,
        "slowest": timed[:SLOWEST_LIMIT],
        "watched_boards": len(watched),
    }
