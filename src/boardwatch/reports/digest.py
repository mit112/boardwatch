"""Summarize a posting_events window into what the user needs to see (D18).

The window is half-open: (since_event_id, max]. posting_events uses AUTOINCREMENT so ids
are monotonic and never reused, which is why a cursor over ids is safe where a timestamp
cursor is not. Closures are a count rather than a list because a closed posting is not
actionable. This module is pure: one query in, one value object out, no rendering.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Connection, select

from boardwatch.store.tables import companies, posting_events, postings

_LISTED_KINDS = ("new", "reopened", "revised")


@dataclass(frozen=True)
class DigestEntry:
    posting_id: int
    title: str
    company: str
    kind: str


@dataclass(frozen=True)
class DigestSummary:
    new: tuple[DigestEntry, ...]
    reopened: tuple[DigestEntry, ...]
    revised: tuple[DigestEntry, ...]
    closed_count: int
    max_event_id: int
    since_event_id: int

    @property
    def is_empty(self) -> bool:
        return not (self.new or self.reopened or self.revised or self.closed_count)


def summarize_events(conn: Connection, since_event_id: int) -> DigestSummary:
    rows = conn.execute(
        select(
            posting_events.c.id,
            posting_events.c.kind,
            postings.c.id.label("posting_id"),
            postings.c.title,
            companies.c.name.label("company_name"),
        )
        .join(postings, posting_events.c.posting_id == postings.c.id)
        .join(companies, postings.c.company_id == companies.c.id)
        .where(posting_events.c.id > since_event_id)
        .order_by(posting_events.c.id)
    ).all()
    grouped: dict[str, list[DigestEntry]] = {kind: [] for kind in _LISTED_KINDS}
    closed_count = 0
    # The cursor is the floor: an empty window must not move it backwards.
    max_event_id = since_event_id
    for row in rows:
        max_event_id = max(max_event_id, int(row.id))
        if row.kind == "closed":
            closed_count += 1
            continue
        grouped[row.kind].append(
            DigestEntry(
                posting_id=int(row.posting_id), title=row.title,
                company=row.company_name, kind=row.kind,
            )
        )
    return DigestSummary(
        new=tuple(grouped["new"]),
        reopened=tuple(grouped["reopened"]),
        revised=tuple(grouped["revised"]),
        closed_count=closed_count,
        max_event_id=max_event_id,
        since_event_id=since_event_id,
    )
