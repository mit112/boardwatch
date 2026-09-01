"""Read-only queries behind lane facet mining (`lanes.facets`). Every function is a select.

The evidence for a mined facet is the user's OWN store and nothing else — which postings this
program built a lead for, and which search page each posting's acquisition was attributed to.
Both already exist: `job_dispositions` has recorded `built` since P6 slice 2, and
`posting_version_sources.source_url` has recorded the exact URL a version was observed at since
P0. Measured on the live store 2026-08-31: 940 `built` dispositions over 957 postings, and 807
posting-version rows carrying a faceted LinkedIn search URL across 21 runs and 14 facets, every
one of which had delivered at least 2 leads. Nothing here needs a new column.

WHY THE PROVENANCE IS MATCHED BY URL PREFIX AND NOT PARSED. The caller passes the URLs its own
request builder produces, so the match is against the exact string that lane would request. A
parser here would be a second, independent statement of another module's URL shape, free to drift
from it silently; a prefix built by the shipping code cannot. `startswith(autoescape=True)` is
not optional — a faceted URL is percent-encoded (`keywords=software%20engineer`), and an
unescaped `%` is a LIKE wildcard that would credit one facet with another's postings.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Select, or_, select
from sqlalchemy.engine import Connection

from boardwatch.lanes.facets import DeliveredPosting, FacetTrial
from boardwatch.store.tables import (
    job_dispositions,
    posting_version_sources,
    posting_versions,
    postings,
)


def _built_job_ids(since: datetime | None = None) -> Select[Any]:
    """The jobs a lead was built for, optionally only those first decided since `since`.

    A scalar subquery rather than a materialised id list: the caller's window can select the
    whole ledger, and an `IN` list of job ids would meet SQLite's 32766 bound-parameter cap as
    the program's delivered history grows (the bound `store.param_chunks` exists for).
    """
    stmt = select(job_dispositions.c.job_id).where(job_dispositions.c.disposition == "built")
    if since is not None:
        stmt = stmt.where(job_dispositions.c.first_decided_at >= since)
    return stmt


def delivered_postings(conn: Connection, *, since: datetime) -> tuple[DeliveredPosting, ...]:
    """Every posting whose job the program built a lead for, first decided on or after `since`.

    The RAW `title`, not `normalized_title` — see `DeliveredPosting` for why that column is the
    wrong space to mine in.

    Driven from `postings` through `ix_postings_job_id` against the subquery, which is what keeps
    this off a full table scan: measured on the live 5.5 GB store, 0.06 s cold and 0.002 s warm
    for 957 rows, against 22.3 s for the same answer written as a join the planner chose to
    drive from `job_dispositions`.
    """
    rows = conn.execute(
        select(postings.c.title, postings.c.id, postings.c.company_id).where(
            postings.c.job_id.in_(_built_job_ids(since))
        )
    ).all()
    return tuple(
        DeliveredPosting(
            title=str(row.title), posting_id=int(row.id), company_id=int(row.company_id)
        )
        for row in rows
    )


def facet_trials(
    conn: Connection, search_urls: Sequence[str], *, since: datetime
) -> dict[str, FacetTrial]:
    """Postings credited to each of `search_urls`, and how many of them were delivered.

    Keyed by the URL the caller passed, so the caller maps back to its own term with the same
    table it built the URLs from. A URL with no rows is ABSENT from the result rather than
    present with zeros: never searched and searched-with-no-result are different facts, and
    `surviving_mined_facets` must not read the first as the second.

    `delivered` counts against the WHOLE ledger, not the window. The window bounds which trials
    still count against a facet; a lead the program built two months ago is still a lead that
    facet produced, and expiring the credit while keeping the trial would manufacture a barren
    record for a facet that was never barren.
    """
    if not search_urls:
        return {}
    delivered_flag = postings.c.job_id.in_(_built_job_ids()).label("delivered")
    rows = conn.execute(
        select(posting_version_sources.c.source_url, delivered_flag)
        .select_from(
            posting_version_sources.join(
                posting_versions,
                posting_versions.c.id == posting_version_sources.c.posting_version_id,
            ).join(postings, postings.c.id == posting_versions.c.posting_id)
        )
        .where(
            posting_version_sources.c.observed_at >= since,
            or_(
                *(
                    posting_version_sources.c.source_url.startswith(url, autoescape=True)
                    for url in search_urls
                )
            ),
        )
    ).all()

    credited = dict.fromkeys(search_urls, 0)
    delivered = dict.fromkeys(search_urls, 0)
    for row in rows:
        url = str(row.source_url)
        for prefix in search_urls:
            if url.startswith(prefix):
                credited[prefix] += 1
                delivered[prefix] += 1 if row.delivered else 0
                break
    return {
        url: FacetTrial(credited=credited[url], delivered=delivered[url])
        for url in search_urls
        if credited[url]
    }
