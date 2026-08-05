"""DB-only aggregate counts for `boardwatch stats`.

Kept separate from queries.py (the P0 catch-all) and funnel_queries.py (the application
display funnel). These are pure counts with no profile/filter dependency; the filtered and
eligibility-partitioned numbers live in reports/stats.py.
"""

from __future__ import annotations

from sqlalchemy import Connection, func, select

from boardwatch.store.tables import applications, postings


def count_open_postings(conn: Connection) -> int:
    """Number of postings with status 'open' — the funnel's `seen` stage."""
    return int(
        conn.execute(
            select(func.count()).select_from(postings).where(postings.c.status == "open")
        ).scalar_one()
    )


def count_tracked_submitted(conn: Connection) -> int:
    """Applications the user actually submitted (submitted_at IS NOT NULL).

    Not a strict subset of postings: applications anchor on `jobs`, allow multiple attempts,
    and survive their posting closing. This is the spec's explicit `tracked` definition.
    """
    return int(
        conn.execute(
            select(func.count())
            .select_from(applications)
            .where(applications.c.submitted_at.is_not(None))
        ).scalar_one()
    )
