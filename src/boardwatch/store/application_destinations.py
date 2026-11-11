"""Verified application links, independent of provider-owned discovery URLs.

Only an explicit verification writer changes these rows. Scans continue refreshing
`postings.url` for provenance, fetching and identity without undoing link checks.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import Connection, delete, func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.sql.elements import ColumnElement

from boardwatch.store.param_chunks import id_chunks
from boardwatch.store.tables import application_destinations, postings


class InvalidApplicationDestinationError(ValueError):
    """The supplied destination is not a usable HTTP(S) application URL."""


@dataclass(frozen=True)
class ApplicationDestination:
    url: str
    source_url: str
    evidence_ref: str
    verified_at: datetime


def record_application_destination(
    conn: Connection,
    *,
    posting_id: int,
    url: str,
    source_url: str,
    evidence_ref: str,
    verified_at: datetime,
    only_if_absent: bool = False,
) -> bool:
    """Record or explicitly replace a verified link; identical evidence is a no-op.

    The caller verifies the job match and retains its evidence. This layer validates
    transport safety, not whether a site's application form is currently live.

    `only_if_absent=True` refuses to replace an existing row at all, for a writer that read the
    table earlier and did network work before this call: a browser-verified destination can be
    written by another session in that window, and it must win. Returns False when a row already
    existed, so the caller can report the write as not landed.
    """
    try:
        parts = urlsplit(url)
        valid = (
            parts.scheme in {"http", "https"}
            and bool(parts.hostname)
            and not parts.username
            and not parts.password
        )
        _ = parts.port
    except ValueError:
        valid = False
    if not valid or url != url.strip() or any(c.isspace() for c in url):
        raise InvalidApplicationDestinationError(
            "expected an HTTP(S) URL without credentials or whitespace"
        )
    if not source_url.strip() or not evidence_ref.strip():
        raise InvalidApplicationDestinationError("source URL and evidence reference are required")
    if verified_at.tzinfo is not None:
        verified_at = verified_at.astimezone(UTC).replace(tzinfo=None)
    values = dict(
        url=url, source_url=source_url, evidence_ref=evidence_ref, verified_at=verified_at
    )
    statement = insert(application_destinations).values(posting_id=posting_id, **values)
    if only_if_absent:
        # No-clobber: the row this call was told about may not be the only writer's. A deferred
        # re-read inside the transaction would be too late on SQLite, so the conflict clause
        # itself decides.
        result = conn.execute(
            statement.on_conflict_do_nothing(index_elements=[application_destinations.c.posting_id])
        )
    else:
        result = conn.execute(
            statement.on_conflict_do_update(
                index_elements=[application_destinations.c.posting_id],
                set_=values,
                where=(application_destinations.c.url != url)
                | (application_destinations.c.source_url != source_url)
                | (application_destinations.c.evidence_ref != evidence_ref)
                | (application_destinations.c.verified_at != verified_at),
            )
        )
    return bool(result.rowcount)


def clear_application_destination(conn: Connection, *, posting_id: int) -> None:
    """Explicitly return a posting to its provider's application-link behavior."""
    conn.execute(
        delete(application_destinations).where(application_destinations.c.posting_id == posting_id)
    )


def read_application_destinations(
    conn: Connection,
    posting_ids: Sequence[int],
) -> dict[int, ApplicationDestination]:
    result = {}
    for chunk in id_chunks(posting_ids):
        for row in conn.execute(
            select(application_destinations).where(application_destinations.c.posting_id.in_(chunk))
        ):
            result[int(row.posting_id)] = ApplicationDestination(
                url=row.url,
                source_url=row.source_url,
                evidence_ref=row.evidence_ref,
                verified_at=row.verified_at,
            )
    return result


def verified_application_url() -> ColumnElement[Any]:
    """The explicit destination, or NULL; keep absence distinct from the source fallback."""
    return (
        select(application_destinations.c.url)
        .where(
            application_destinations.c.posting_id == postings.c.id,
        )
        .correlate(postings)
        .scalar_subquery()
    )


def effective_apply_url() -> ColumnElement[Any]:
    """An indexed lookup correlated to the current posting; never read mutable raw_json."""
    return func.coalesce(verified_application_url(), postings.c.url)
