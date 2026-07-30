"""Read the persisted, evidence-linked audit for one posting, for the `show` render.

This never evaluates. It reads the newest stored evaluation for the posting and rebuilds a
render-ready view from it. Two rules make the view honest rather than merely present:

- The JD quote is sliced from the evaluated version's `posting_versions.body_text`, which is
  immutable, never from `postings.body_text`, which a scan rewrites in place. A stored span
  garbles the instant it is sliced from the wrong string.
- Labels are version-gated (D-P2-21). When the frozen rules snapshot's catalog version still
  matches the live catalog, the stored requirement text IS a current label; when it does not,
  the current vocabulary can no longer be trusted to name the old rule, so the raw composite
  rule_id is shown with an explicit note instead.

A closed posting is the one deliberate exception: it renders its newest historical evaluation
and is never freshly evaluated (D-P2-9), so this reader falls back to the newest stored row
rather than expecting a current-version, current-engine one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, select

from boardwatch.eligibility.catalog import RulesCatalog
from boardwatch.eligibility.engine import engine_version
from boardwatch.store.eligibility import get_requirements, get_support
from boardwatch.store.queries import current_posting_versions
from boardwatch.store.tables import (
    eligibility_evaluations,
    eligibility_inputs,
    posting_versions,
    postings,
)


@dataclass(frozen=True)
class AuditSupport:
    profile_locator: dict[str, Any]
    evidence_quote: str
    support_kind: str


@dataclass(frozen=True)
class AuditRequirement:
    rule_id: str | None
    label: str
    requiredness: str
    disposition: str
    rationale: str | None
    quote: str
    support: tuple[AuditSupport, ...]


@dataclass(frozen=True)
class AuditView:
    verdict: str
    captured_at: datetime
    is_historical: bool
    catalog_version_matches: bool
    requirements: tuple[AuditRequirement, ...]


def load_audit(
    conn: Connection, posting_id: int, catalog: RulesCatalog
) -> AuditView | None:
    """The newest stored evaluation for `posting_id`, rebuilt for rendering, or None.

    Closed postings render their newest historical evaluation and are never re-evaluated
    (D-P2-9); this reader is read-only, so that exception is honoured by construction.
    """
    status = conn.execute(
        select(postings.c.status).where(postings.c.id == posting_id)
    ).scalar_one_or_none()
    if status is None:
        return None

    newest = conn.execute(
        select(
            eligibility_evaluations.c.id,
            eligibility_evaluations.c.verdict,
            eligibility_evaluations.c.engine_version,
            eligibility_inputs.c.posting_version_id,
            eligibility_inputs.c.rules_snapshot_json,
        )
        .join(eligibility_inputs, eligibility_evaluations.c.input_id == eligibility_inputs.c.id)
        .join(posting_versions, eligibility_inputs.c.posting_version_id == posting_versions.c.id)
        .where(posting_versions.c.posting_id == posting_id)
        .order_by(eligibility_evaluations.c.id.desc())
        .limit(1)
    ).one_or_none()
    if newest is None:
        return None

    current = current_posting_versions(conn, [posting_id]).get(posting_id)
    is_historical = not (
        status == "open"
        and current is not None
        and newest.posting_version_id == current.posting_version_id
        and newest.engine_version == engine_version()
    )

    version = conn.execute(
        select(posting_versions.c.body_text, posting_versions.c.captured_at).where(
            posting_versions.c.id == newest.posting_version_id
        )
    ).one()
    body_text = str(version.body_text)
    rules_snapshot = newest.rules_snapshot_json or {}
    catalog_version_matches = rules_snapshot.get("catalog_version") == catalog.version

    requirements: list[AuditRequirement] = []
    for req in get_requirements(conn, int(newest.id)):
        span = (req.jd_locator_json or {}).get("span") or [0, 0]
        quote = body_text[int(span[0]) : int(span[1])]
        if catalog_version_matches:
            label = req.requirement_text
        else:
            label = f"{req.rule_id} (catalog version no longer present)"
        support = tuple(
            AuditSupport(
                profile_locator=sup.profile_locator_json or {},
                evidence_quote=str(sup.evidence_quote),
                support_kind=str(sup.support_kind),
            )
            for sup in get_support(conn, int(req.id))
        )
        requirements.append(
            AuditRequirement(
                rule_id=req.rule_id,
                label=label,
                requiredness=req.requiredness,
                disposition=req.disposition,
                rationale=req.rationale,
                quote=quote,
                support=support,
            )
        )

    return AuditView(
        verdict=str(newest.verdict),
        captured_at=version.captured_at,
        is_historical=is_historical,
        catalog_version_matches=catalog_version_matches,
        requirements=tuple(requirements),
    )
