"""The lane-body quarantine and its drain (D-406).

A body that is an aggregator's rendered PAGE rather than the employer's own text must never
become an eligibility input: `work_auth` is a blocker family and `INELIGIBLE` must carry a
quoted span from the frozen JD, so an `ineligible(work_auth)` quoting jobright's own
`H1B Sponsor Likely` label would present a third party's guess as the employer's stated
requirement. The precondition itself lives in `lanes.quality`; this module is where a body that
fails it is held, and — in the same change, as the standing rule requires — where it gets out.

**Fail-safe direction, chosen for THIS gate and deliberately not the one its neighbours chose.**
Two different things can fail here and they need opposite defaults:

* *Judging a body we cannot attribute to the employer* fails SAFE — closed. The body is withheld
  from the rules, so no verdict is ever produced from it. A missing verdict is visible (the
  posting carries none); a verdict quoting the wrong author's text is not, which is exactly why
  the keystone invariant cannot detect this failure after the fact.
* *The posting itself* fails OPEN. Nothing is deleted, nothing is closed, no disposition is
  written: the posting stays in the corpus, stays `open`, and stays listable. A false positive
  therefore costs a withheld verdict, never a lost job — and it is released automatically by the
  drain below the moment the catalog that misjudged it is corrected.

Deliberately NOT `job_dispositions`, and the reasons are specific rather than stylistic. That
table is keyed on `job_id`, a dedup GROUP, so quarantining there would also suppress a sibling
posting whose body is the employer's own text. `record_disposition` is rank-monotonic, so
`skipped` cannot be written over a job already `built` — the quarantine would silently no-op on
precisely the rows that were already harmed. And its drain releases on `policy_version` drift
reviewed by a human `ledger reopen --stale`; the re-entry condition here is a different event on
a different cadence, and encoding a body hash into `policy_version` would make every quarantined
row permanently "stale", so the next unrelated `ledger reopen --stale` would drain this whole
bucket unreviewed and break that drain too.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Connection, select, tuple_, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from boardwatch.lanes.quality import FOREIGN_BODY_CATALOG_VERSION, is_employer_body
from boardwatch.store.param_chunks import id_chunks
from boardwatch.store.tables import posting_versions, quarantined_bodies


def record_quarantine(
    conn: Connection,
    *,
    posting_version_id: int,
    posting_id: int,
    markers: Sequence[str],
    now: datetime,
    run_id: int | None = None,
) -> None:
    """Hold one posting version out of the rules, recording WHICH markers fired.

    Upserted rather than inserted, and the conflict branch clears `reopened_at`: a version the
    drain released under an older catalog, which the current catalog refuses again, is back in
    the bucket. The row's history survives either way — nothing here deletes.
    """
    stmt = sqlite_insert(quarantined_bodies).values(
        posting_version_id=posting_version_id,
        posting_id=posting_id,
        markers_json=list(markers),
        catalog_version=FOREIGN_BODY_CATALOG_VERSION,
        quarantined_at=now,
        run_id=run_id,
        reopened_at=None,
    )
    conn.execute(
        stmt.on_conflict_do_update(
            index_elements=[quarantined_bodies.c.posting_version_id],
            set_={
                "markers_json": stmt.excluded.markers_json,
                "catalog_version": stmt.excluded.catalog_version,
                "quarantined_at": stmt.excluded.quarantined_at,
                "run_id": stmt.excluded.run_id,
                "reopened_at": None,
            },
        )
    )


def live_quarantine(conn: Connection) -> dict[int, tuple[str, ...]]:
    """Every version currently withheld, and the markers that withheld it.

    The bucket read directly, so a suppression can be listed rather than inferred from what the
    rules happened not to judge. A suppression that cannot be listed is a leak, not a filter.
    """
    rows = conn.execute(
        select(quarantined_bodies.c.posting_version_id, quarantined_bodies.c.markers_json).where(
            quarantined_bodies.c.reopened_at.is_(None)
        )
    ).all()
    return {int(row.posting_version_id): tuple(row.markers_json or ()) for row in rows}


def drain_quarantine(conn: Connection, *, now: datetime) -> int:
    """Release every held body that may re-enter. Returns the number released.

    **WHAT re-opens a quarantined row — two conditions, either one suffices.**

    1. *The body was re-fetched from the employer's own board.* `scan/apply.py` appends a NEW
       immutable `posting_versions` row whenever a posting's content hash moves, so a lane
       re-ingesting a clean body, a board scan revising it, or the death probe's refetch all
       show up here as "a newer version exists for this posting". The newer version was never
       quarantined, so releasing the old one is what stops the bucket holding rows that are no
       longer withholding anything.
    2. *The catalog that refused it no longer does.* The current marker catalog is re-run
       against the stored body — O(rows held), not O(corpus) — so withdrawing a marker after a
       false positive releases every row it was the reason for, with no operator action.

    **WHO runs it, and on what CADENCE.** `eligibility.preflight.run_eligibility`, immediately
    BEFORE it selects pending work: every pipeline run, plus every `top`, `export`, `stats` and
    `eligibility run` invocation that triggers the preflight as a side effect. A row released
    here is selected as pending by the SAME call and judged in the same pass, which is what
    makes this a drain that runs on both sides of the gate rather than a door nobody opens.

    Sets `reopened_at` rather than deleting, exactly as `ledger_queries.reopen_jobs` does: the
    record that this body was ever held is the audit trail, and a DELETE would erase the only
    evidence that the precondition ever fired.
    """
    # The SAME `newer` shape `eligibility.preflight._pending` uses to find each posting's
    # current version, aliased for the same reason: without the alias both sides of the
    # comparison bind to one table and the EXISTS is true for every row.
    newest = posting_versions.alias("pv_newer")
    newer = (
        select(newest.c.id)
        .where(
            newest.c.posting_id == posting_versions.c.posting_id,
            tuple_(newest.c.captured_at, newest.c.id)
            > tuple_(posting_versions.c.captured_at, posting_versions.c.id),
        )
        .exists()
    )
    held = conn.execute(
        select(
            quarantined_bodies.c.posting_version_id,
            posting_versions.c.body_text,
            newer.label("superseded"),
        )
        .join(
            posting_versions,
            posting_versions.c.id == quarantined_bodies.c.posting_version_id,
        )
        .where(quarantined_bodies.c.reopened_at.is_(None))
    ).all()
    releasable = [
        int(row.posting_version_id)
        for row in held
        if bool(row.superseded) or is_employer_body(str(row.body_text))
    ]
    if not releasable:
        return 0
    # CHUNKED (D-288), and — like `ledger_queries.reopen_jobs`, the other site of this shape —
    # the pieces are ADDED, because this returns a scalar `rowcount` rather than a mapping.
    # Keeping the last chunk's result would report a smaller drain than it performed while
    # raising nothing. The bucket is nine rows today; it is the CORPUS that decides how large it
    # can get, and an unchunked `IN` past SQLite's 32,766 bound parameters is a scheduled
    # failure in the one path that lets held bodies out.
    released = 0
    for chunk in id_chunks(releasable):
        result = conn.execute(
            update(quarantined_bodies)
            .where(
                quarantined_bodies.c.posting_version_id.in_(chunk),
                quarantined_bodies.c.reopened_at.is_(None),
            )
            .values(reopened_at=now)
        )
        released += int(result.rowcount)
    return released
