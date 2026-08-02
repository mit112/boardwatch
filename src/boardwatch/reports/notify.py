"""Pure selection of NEW matching postings for `boardwatch notify` (P5).

A "new match" is a posting with a `new` posting_events row past the notify cursor whose
current state passes the profile's hard filters and is not persisted `ineligible`. This
module is pure and side-effect-free: it reads current DB state only — it never runs
preflight, eligibility, or an LLM, so `scan && notify` stays cheap. One connection in,
one value object out, no rendering, no delivery.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Connection, select

from boardwatch.core.clock import utcnow
from boardwatch.core.settings import Settings
from boardwatch.eligibility.preflight import current_identity
from boardwatch.eligibility.read import current_verdicts
from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.rank.heuristic import ProfileView, passes_hard_filters, score_posting
from boardwatch.store.queries import current_posting_versions
from boardwatch.store.tables import companies, extractions, posting_events, postings


@dataclass(frozen=True)
class NotifyItem:
    posting_id: int
    title: str
    company: str
    url: str | None
    score: float
    verdict: str | None


@dataclass(frozen=True)
class NotifyResult:
    items: tuple[NotifyItem, ...]
    since_event_id: int
    max_event_id: int

    @property
    def is_empty(self) -> bool:
        return not self.items


def _new_ids_and_max(conn: Connection, since_event_id: int) -> tuple[set[int], int]:
    rows = conn.execute(
        select(posting_events.c.id, posting_events.c.posting_id)
        .where(posting_events.c.id > since_event_id)
        .where(posting_events.c.kind == "new")
        .order_by(posting_events.c.id)
    ).all()
    # The cursor is the floor: an empty window must not move it backwards.
    max_event_id = since_event_id
    ids: set[int] = set()
    for row in rows:
        max_event_id = max(max_event_id, int(row.id))
        ids.add(int(row.posting_id))
    return ids, max_event_id


def select_new_matches(
    conn: Connection,
    since_event_id: int,
    profile: ProfileView,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> NotifyResult:
    now = now or utcnow()
    new_ids, max_event_id = _new_ids_and_max(conn, since_event_id)
    if not new_ids:
        return NotifyResult(items=(), since_event_id=since_event_id, max_event_id=max_event_id)
    version = load_taxonomy(settings.config_dir).version
    rows = conn.execute(
        select(
            postings.c.id,
            postings.c.title,
            postings.c.url,
            postings.c.posted_at,
            postings.c.locations_json,
            postings.c.remote_policy,
            companies.c.name.label("company_name"),
            extractions.c.json.label("extraction_json"),
        )
        .join(companies, postings.c.company_id == companies.c.id)
        .outerjoin(
            extractions,
            (extractions.c.posting_id == postings.c.id)
            & (extractions.c.content_hash == postings.c.content_hash)
            & (extractions.c.kind == "taxonomy")
            & (extractions.c.engine_version == version),
        )
        .where(postings.c.status == "open")
        .where(postings.c.id.in_(new_ids))
    ).all()
    versions = current_posting_versions(conn, None)
    # Read-only: the live profile's (profile_hash, rules_hash) without running the lane.
    identity = current_identity(conn, settings)
    profile_hash, rules_hash = identity if identity is not None else (None, None)
    verdicts = current_verdicts(
        conn,
        [cv.posting_version_id for cv in versions.values()],
        profile_hash,
        rules_hash,
    )
    items: list[NotifyItem] = []
    for row in rows:
        if not passes_hard_filters(
            row.title, list(row.locations_json or []), row.remote_policy,
            profile, settings.location_filter_mode,
        ):
            continue
        if verdicts.get(int(row.id)) == "ineligible":
            continue
        skills = set((row.extraction_json or {}).get("skills", []))
        score = score_posting(
            profile, skills, row.title, row.posted_at,
            list(row.locations_json or []), row.remote_policy,
            settings.weights, now, settings.recency_half_life_days,
        )
        items.append(NotifyItem(
            posting_id=int(row.id), title=row.title, company=row.company_name,
            url=row.url, score=score.total, verdict=verdicts.get(int(row.id)),
        ))
    items.sort(key=lambda i: i.score, reverse=True)
    return NotifyResult(
        items=tuple(items), since_event_id=since_event_id, max_event_id=max_event_id
    )
