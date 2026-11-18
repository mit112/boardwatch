"""Postings whose JD changed after a résumé was built or after an application was sent (T309).

Two lists, kept apart, because they warn about different things: a changed JD after a BUILD means
the tailored résumé may be stale; a changed JD after APPLYING means a requirement may have been
added that the application never answered.

A "change" is a `posting_versions` row with `capture_reason = 'revised'`; the other reasons are the
first capture and backfills, not edits. The version row is read instead of the `revised` event in
`posting_events` because the events table has no `posting_id` index (a lookup by posting scans its
2.1M rows, 6 s) while `ix_posting_versions_posting_captured` serves it, and because the version
id is what a diff needs.

Driven from the small side: the tailored artifacts (a few thousand) and the applications (hundreds),
then the versions of those postings only, in chunked `IN` lists. `posting_versions` rows carry the
whole body text, so only narrow columns are read and the table is never scanned.

Built: per posting, its NEWEST tailored build (the version it was built from, latest by instant).
Stale means a revised version came after that version. A posting rebuilt after its change is not
listed. Applied: per application with a recorded submission date and a posting version, a revised
version captured after `submitted_at`. The "before" version of the diff is the last version live at
`submitted_at`. An import that gave no date carries the import time, not when it was sent, so it is
counted in `excluded_imports` and never compared; an application with no posting version cannot say
which posting it was sent against, so it is counted in `no_posting_version`.

Timestamps in the store mix naive-UTC and offset-carrying text, so every comparison and sort here
normalises in Python (`_naive`); no SQL orders or compares a raw timestamp.

Read-only. Each row carries the board's own posting URL and both version ids; `version_diff` is the
line diff between two of them (T316).
"""

from __future__ import annotations

import difflib
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Connection, exists, select

from boardwatch.store.lead_aging_queries import IMPORT_SOURCE, _naive
from boardwatch.store.param_chunks import id_chunks
from boardwatch.store.run_funnel_queries import TAILORED_KIND
from boardwatch.store.tables import (
    application_events,
    applications,
    artifacts,
    companies,
    posting_versions,
    postings,
)

ROW_LIMIT = 50
_REVISED = "revised"

# (instant, id): the id breaks a tie between two versions captured in the same instant.
_Order = tuple[datetime, int]


def _iso(stamp: datetime) -> str:
    return _naive(stamp).replace(tzinfo=UTC).isoformat()


def _versions(conn: Connection, posting_ids: set[int]) -> dict[int, list[tuple[_Order, int, bool]]]:
    """posting id -> [(order, version id, is_revised)] oldest first, narrow columns only."""
    out: dict[int, list[tuple[_Order, int, bool]]] = {}
    for chunk in id_chunks(sorted(posting_ids)):
        for r in conn.execute(
            select(
                posting_versions.c.id,
                posting_versions.c.posting_id,
                posting_versions.c.captured_at,
                posting_versions.c.capture_reason,
            ).where(posting_versions.c.posting_id.in_(chunk))
        ):
            out.setdefault(int(r.posting_id), []).append(
                ((_naive(r.captured_at), int(r.id)), int(r.id), r.capture_reason == _REVISED)
            )
    for rows in out.values():
        rows.sort()
    return out


def _labels(conn: Connection, posting_ids: set[int]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for chunk in id_chunks(sorted(posting_ids)):
        for p in conn.execute(
            select(
                postings.c.id,
                postings.c.job_id,
                postings.c.title,
                postings.c.url,
                companies.c.name,
            )
            .join(companies, companies.c.id == postings.c.company_id)
            .where(postings.c.id.in_(chunk))
        ):
            out[int(p.id)] = {
                "posting_id": int(p.id),
                "job_id": None if p.job_id is None else int(p.job_id),
                "title": str(p.title),
                "company": str(p.name),
                "url": p.url,
            }
    return out


def _revisions_after(
    versions: list[tuple[_Order, int, bool]], after: _Order
) -> list[tuple[_Order, int, bool]]:
    return [v for v in versions if v[2] and v[0] > after]


def _built(conn: Connection) -> tuple[int, list[dict[str, Any]]]:
    """(postings with a tailored résumé, stale ones as unsorted row dicts with an order key)."""
    # posting id -> (order of the version it was built from, that version id, build time). The
    # newest BUILD is the one that finished last (`artifacts.created_at`, then id), not the one
    # from the newest JD capture: overlapping builds can finish out of order (T320).
    newest: dict[int, tuple[_Order, int, datetime]] = {}
    built_order: dict[int, tuple[datetime, int]] = {}
    for r in conn.execute(
        select(
            artifacts.c.id,
            artifacts.c.posting_version_id,
            artifacts.c.created_at,
            artifacts.c.meta_json,
            posting_versions.c.posting_id,
            posting_versions.c.captured_at,
        )
        .join(posting_versions, artifacts.c.posting_version_id == posting_versions.c.id)
        .where(artifacts.c.kind == TAILORED_KIND)
    ):
        meta = r.meta_json
        if isinstance(meta, dict) and meta.get("pending_tailor"):
            continue  # a review-lane stub renders no résumé, so it is not a build (T310)
        pid = int(r.posting_id)
        order = (_naive(r.captured_at), int(r.posting_version_id))
        built_at = _naive(r.created_at)
        key = (built_at, int(r.id))
        if pid not in built_order or key > built_order[pid]:
            built_order[pid] = key
            newest[pid] = (order, int(r.posting_version_id), built_at)

    versions = _versions(conn, set(newest))
    stale: list[tuple[int, list[tuple[_Order, int, bool]], tuple[_Order, int, datetime]]] = []
    for pid, build in newest.items():
        later = _revisions_after(versions.get(pid, []), build[0])
        if later:
            stale.append((pid, later, build))
    labels = _labels(conn, {pid for pid, _, _ in stale})
    rows = []
    for pid, later, build in stale:
        label = labels.get(pid)
        if label is None:
            continue
        rows.append(
            {
                **label,
                "built_at": _iso(build[2]),
                "built_version_id": build[1],
                "revisions": len(later),
                "latest_version_id": later[-1][1],
                "latest_revised_at": _iso(later[-1][0][0]),
                "_order": later[-1][0],
            }
        )
    return len(newest), rows


def _applied(conn: Connection) -> tuple[int, int, int, list[dict[str, Any]]]:
    """(checked, excluded imports, no posting version, changed rows with an order key)."""
    imported = exists().where(
        application_events.c.application_id == applications.c.id,
        application_events.c.event_type == "created",
        application_events.c.source == IMPORT_SOURCE,
    )
    excluded = no_version = 0
    # application id -> (row, submitted instant)
    sent: dict[int, tuple[Any, datetime]] = {}
    for a in conn.execute(
        select(
            applications.c.id,
            applications.c.status,
            applications.c.created_at,
            applications.c.submitted_at,
            posting_versions.c.posting_id,
            imported.label("imported"),
        )
        .outerjoin(posting_versions, applications.c.posting_version_id == posting_versions.c.id)
        .where(applications.c.submitted_at.is_not(None))
    ):
        submitted = _naive(a.submitted_at)
        if a.imported and submitted == _naive(a.created_at):
            excluded += 1
        elif a.posting_id is None:
            no_version += 1
        else:
            sent[int(a.id)] = (a, submitted)

    versions = _versions(conn, {int(a.posting_id) for a, _ in sent.values()})
    changed = []
    for app_id, (a, submitted) in sent.items():
        vs = versions.get(int(a.posting_id), [])
        later = [v for v in vs if v[2] and v[0][0] > submitted]
        if not later:
            continue
        # The version live when the application was sent: the last one captured at or before it.
        live = [v for v in vs if v[0][0] <= submitted]
        changed.append((app_id, a, submitted, later, live[-1][1] if live else None))
    labels = _labels(conn, {int(a.posting_id) for _, a, _, _, _ in changed})
    rows = []
    for app_id, a, submitted, later, live_id in changed:
        label = labels.get(int(a.posting_id))
        if label is None:
            continue
        rows.append(
            {
                **label,
                "application_id": app_id,
                "status": str(a.status),
                "submitted_at": _iso(submitted),
                "sent_version_id": live_id,
                "revisions": len(later),
                "latest_version_id": later[-1][1],
                "latest_revised_at": _iso(later[-1][0][0]),
                "_order": later[-1][0],
            }
        )
    return len(sent), excluded, no_version, rows


def _top(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    """Newest change first, ties by id, capped; the order key is dropped from the output."""
    ordered = sorted(rows, key=lambda r: (r["_order"], r[key]), reverse=True)
    return [{k: v for k, v in r.items() if k != "_order"} for r in ordered[:ROW_LIMIT]]


def jd_changes(conn: Connection) -> dict[str, Any]:
    checked_built, built = _built(conn)
    checked_applied, excluded, no_version, applied = _applied(conn)
    return {
        "limit": ROW_LIMIT,
        "built": {"checked": checked_built, "stale": len(built), "rows": _top(built, "posting_id")},
        "applied": {
            "checked": checked_applied,
            "changed": len(applied),
            "excluded_imports": excluded,
            "no_posting_version": no_version,
            "rows": _top(applied, "application_id"),
        },
    }


DIFF_CONTEXT = 2


def version_diff(
    conn: Connection, posting_id: int, from_id: int, to_id: int
) -> dict[str, Any] | None:
    """A line diff of two versions' body text, or None unless BOTH belong to `posting_id`.

    Only the two named rows are read (by primary key), so the heavy table is never scanned. Each
    line is `{"kind": "add" | "del" | "same" | "hunk", "text": ...}`: `hunk` is the `@@` marker that
    opens a run of changes with up to `DIFF_CONTEXT` unchanged lines around it.
    """
    bodies = {
        int(r.id): str(r.body_text)
        for r in conn.execute(
            select(posting_versions.c.id, posting_versions.c.body_text).where(
                posting_versions.c.id.in_({from_id, to_id}),
                posting_versions.c.posting_id == posting_id,
            )
        )
    }
    if from_id not in bodies or to_id not in bodies:
        return None
    kinds = {"+": "add", "-": "del", " ": "same", "@": "hunk"}
    # The first two rows are the `---`/`+++` file headers (absent when nothing differs); dropped by
    # position, since a removed line whose text starts with `-- ` reads exactly like a header.
    rows = list(
        difflib.unified_diff(
            bodies[from_id].splitlines(), bodies[to_id].splitlines(), n=DIFF_CONTEXT, lineterm=""
        )
    )[2:]
    lines = [{"kind": kinds[r[0]], "text": r if r[0] == "@" else r[1:]} for r in rows]
    return {"posting_id": posting_id, "from": from_id, "to": to_id, "lines": lines}
