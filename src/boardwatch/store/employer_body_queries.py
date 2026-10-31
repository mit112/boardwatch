"""D-659: provisional lane-copy recovery candidates, independent of verdicts."""
from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import Connection, func, or_, select

from boardwatch.core.normalize import content_hash, normalize_body
from boardwatch.lanes.dereference import PostingTarget, parse_posting_target
from boardwatch.lanes.quality import is_employer_body, meets_body_floor
from boardwatch.providers.base import supports_employer_body_recovery
from boardwatch.providers.registry import build_providers
from boardwatch.store.param_chunks import id_chunks
from boardwatch.store.tables import (
    companies,
    posting_version_sources,
    posting_versions,
    postings,
    quarantined_bodies,
)

STUB_RECOVERY_CHARS = 1_000
EMPLOYER_BODY_PENDING = "employer_body_pending"


def _aggregator_body_lane(data: dict[str, Any], source_url: str | None) -> str | None:
    """Only local jobright/Indeed text and native Indeed's GraphQL description are suspect."""
    if source_url is None:
        return None
    try:
        source = urlsplit(source_url)
    except ValueError:
        return None
    jobapps = data.get("jobapps")
    if source.scheme == "file" and isinstance(jobapps, dict) and (
        jobapps.get("primary_acquisition") in ("jobright", "indeed")
    ):
        return "jobapps"
    host = source.hostname or ""
    if isinstance(data.get("job"), dict) and (host == "indeed.com" or host.endswith(".indeed.com")):
        return "indeed"
    return None


def evidenced_url(raw_json: Any, stored_url: str | None) -> str | None:
    """Explicit resolver/recruit evidence may name an unsupported host; never infer one."""
    data = raw_json if isinstance(raw_json, dict) else {}
    jobapps = data.get("jobapps")
    job = data.get("job")
    recruit = job.get("recruit") if isinstance(job, dict) else None
    candidates = [
        jobapps.get("employer_url") if isinstance(jobapps, dict) else None,
        recruit.get("viewJobUrl") if isinstance(recruit, dict) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    if stored_url:
        try:
            parse_posting_target(stored_url)
        except ValueError:
            pass
        else:
            return stored_url
    return None


def verified_source(
    body: str, url: str | None, record_id: str | None, payload_hash: str | None,
    employer_url: str | None,
) -> bool:
    """Employer posting or native board source, matching the evidence, id and frozen bytes."""
    if url is None or employer_url is None:
        return False
    try:
        target = parse_posting_target(employer_url)
    except ValueError:
        return False
    if record_id != target.posting_ref or payload_hash != content_hash(body):
        return False
    if not body.strip() or not is_employer_body(body):
        return False
    try:
        source_target = parse_posting_target(url)
    except ValueError:
        provider = build_providers().get(target.provider)
        return provider is not None and url == provider.board_url(target.slug)
    return source_target == target


@dataclass(frozen=True)
class EmployerBodyPending:
    posting_id: int
    posting_version_id: int
    employer_url: str
    captured_at: datetime
    lane: str

    def target(self) -> PostingTarget:
        return parse_posting_target(self.employer_url)


def pending_employer_bodies(
    conn: Connection, version_ids: Sequence[int] | None = None, *,
    posting_id: int | None = None, open_only: bool = True,
    unrecoverable: Counter[str] | None = None,
    held_only: bool = False,
) -> dict[int, EmployerBodyPending]:
    """Version -> hold; read dynamically so an old ELIGIBLE or absent sweep cannot bypass it.

    Without ids, select current open copies for the scheduled drain. Explicit ids are chunked
    for read boundaries and may include closed/historical versions, like current_verdicts.
    Optionally count unsupported stubs by provider for the run diagnostics, without holding them.
    The drain uses held_only to visit just postings with an active employer-body hold.
    """
    pv = posting_versions
    source = posting_version_sources
    held_scope = (
        quarantined_bodies.c.posting_id == postings.c.id,
        quarantined_bodies.c.reopened_at.is_(None),
        func.json_extract(quarantined_bodies.c.markers_json, "$[0]") == EMPLOYER_BODY_PENDING,
    )
    held = select(quarantined_bodies.c.posting_version_id).where(
        *held_scope
    ).correlate(postings).exists()
    held_url = select(func.json_extract(quarantined_bodies.c.markers_json, "$[1]")).where(
        *held_scope
    ).order_by(quarantined_bodies.c.quarantined_at.desc()).limit(1).correlate(postings).scalar_subquery()
    held_lane = select(func.json_extract(quarantined_bodies.c.markers_json, "$[2]")).where(
        *held_scope
    ).order_by(quarantined_bodies.c.quarantined_at.desc()).limit(1).correlate(postings).scalar_subquery()
    candidate = or_(companies.c.provider.in_(("jobapps", "indeed")), held, *(
        func.json_type(postings.c.raw_json, f"$.{key}") == "object"
        for key in ("jobapps", "job")
    ))
    stmt = (
        select(pv.c.id, pv.c.posting_id, pv.c.body_text, pv.c.captured_at,
               postings.c.raw_json, postings.c.url, companies.c.source, companies.c.provider,
               source.c.source_url, source.c.source_record_id, source.c.payload_hash,
               held.label("held"), held_url.label("held_url"), held_lane.label("held_lane"))
        .join(postings, postings.c.id == pv.c.posting_id)
        .join(companies, companies.c.id == postings.c.company_id)
        .outerjoin(source, source.c.posting_version_id == pv.c.id)
    )
    if held_only:
        held_postings = select(quarantined_bodies.c.posting_id).where(
            quarantined_bodies.c.reopened_at.is_(None),
            func.json_extract(quarantined_bodies.c.markers_json, "$[0]") == EMPLOYER_BODY_PENDING,
        ).distinct().subquery()
        stmt = stmt.join(held_postings, held_postings.c.posting_id == postings.c.id)
    elif version_ids is None and posting_id is None:
        # DISTINCT prevents SQLite from flattening this scope and seeking a version for
        # every posting before testing its acquisition evidence. Native-provider companies
        # can also carry jobapps/Indeed copies, so provider alone is not a sufficient bound.
        candidates = select(postings.c.id).join(
            companies, companies.c.id == postings.c.company_id,
        ).where(candidate)
        if open_only:
            candidates = candidates.where(postings.c.status == "open")
        scoped = candidates.distinct().subquery()
        stmt = stmt.join(scoped, scoped.c.id == postings.c.id)
    else:
        stmt = stmt.where(candidate)
    if posting_id is not None:
        stmt = stmt.where(postings.c.id == posting_id)
    if version_ids is None:
        newer = pv.alias("employer_body_newer")
        if open_only:
            stmt = stmt.where(postings.c.status == "open")
        # Seek one current version through ix_posting_versions_posting_captured;
        # do not scan the immutable version history to discard every superseded body.
        latest = select(newer.c.id).where(
            newer.c.posting_id == postings.c.id,
        ).order_by(newer.c.captured_at.desc(), newer.c.id.desc()).limit(1).correlate(postings)
        stmt = stmt.where(pv.c.id == latest.scalar_subquery())
        batches = [stmt]
    else:
        batches = [stmt.where(pv.c.id.in_(chunk)) for chunk in id_chunks(list(version_ids))]
    out: dict[int, EmployerBodyPending] = {}
    providers = build_providers()
    for batch in batches:
        for row in conn.execute(batch):
            data = row.raw_json if isinstance(row.raw_json, dict) else {}
            body = str(row.body_text)
            lane = _aggregator_body_lane(data, row.source_url)
            if lane is None and row.held and row.held_lane in {"jobapps", "indeed"}:
                jobapps = data.get("jobapps")
                if isinstance(jobapps, dict) and "primary_acquisition" in jobapps and (
                    jobapps["primary_acquisition"] not in ("jobright", "indeed")
                ):
                    continue
                # A hold survives missing metadata or a revision with unverified source lineage.
                lane = str(row.held_lane)
            if lane is None:
                continue
            if (
                not row.held and meets_body_floor(body)
                and len(normalize_body(body)) >= STUB_RECOVERY_CHARS
            ):
                continue
            url = evidenced_url(data, row.url)
            if url is None and isinstance(row.held_url, str):
                url = row.held_url
            if verified_source(body, row.source_url, row.source_record_id, row.payload_hash, url):
                continue
            if url is not None:
                try:
                    target = parse_posting_target(url)
                except ValueError:
                    target = None
                if target is None or not supports_employer_body_recovery(
                    providers.get(target.provider)
                ):
                    if unrecoverable is not None:
                        name = target.provider if target is not None else "unparseable_url"
                        unrecoverable[name] += 1
                    continue
                out[int(row.id)] = EmployerBodyPending(
                    int(row.posting_id), int(row.id), url, row.captured_at, lane,
                )
    return out
