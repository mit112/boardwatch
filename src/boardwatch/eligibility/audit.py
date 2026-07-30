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

from sqlalchemy import Connection, Select, select

from boardwatch.eligibility.catalog import RulesCatalog
from boardwatch.eligibility.engine import ENGINE_KIND, engine_version
from boardwatch.store.eligibility import get_requirements, get_support_bulk
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
    conn: Connection,
    posting_id: int,
    catalog: RulesCatalog,
    *,
    profile_hash: str | None = None,
    rules_hash: str | None = None,
) -> AuditView | None:
    """The stored evaluation for `posting_id`, rebuilt for rendering, or None.

    When the caller passes the current profile's (profile_hash, rules_hash), an OPEN posting
    renders the evaluation THAT identity produced for its current version, so `show` agrees
    with `top` after a fact or policy change. Otherwise, and for closed postings, it falls
    back to the newest stored evaluation, flagged historical whenever it is not the current
    profile's current-version, current-engine row. Closed postings are never re-evaluated
    (D-P2-9); this reader is read-only, so that exception is honoured by construction.
    """
    status = conn.execute(
        select(postings.c.status).where(postings.c.id == posting_id)
    ).scalar_one_or_none()
    if status is None:
        return None

    current = current_posting_versions(conn, [posting_id]).get(posting_id)
    identity_given = profile_hash is not None and rules_hash is not None

    def _eval_base() -> Select[Any]:  # a local query builder, not a public interface
        return (
            select(
                eligibility_evaluations.c.id,
                eligibility_evaluations.c.verdict,
                eligibility_evaluations.c.engine_version,
                eligibility_inputs.c.posting_version_id,
                eligibility_inputs.c.rules_snapshot_json,
            )
            .join(
                eligibility_inputs,
                eligibility_evaluations.c.input_id == eligibility_inputs.c.id,
            )
            .join(
                posting_versions,
                eligibility_inputs.c.posting_version_id == posting_versions.c.id,
            )
        )

    newest = None
    is_historical = True
    if identity_given and status == "open" and current is not None:
        newest = conn.execute(
            _eval_base().where(
                posting_versions.c.id == current.posting_version_id,
                eligibility_inputs.c.profile_hash == profile_hash,
                eligibility_inputs.c.rules_hash == rules_hash,
                eligibility_evaluations.c.engine_kind == ENGINE_KIND,
                eligibility_evaluations.c.engine_version == engine_version(),
            )
        ).one_or_none()
        if newest is not None:
            is_historical = False
    if newest is None:
        newest = conn.execute(
            _eval_base()
            .where(posting_versions.c.posting_id == posting_id)
            .order_by(eligibility_evaluations.c.id.desc())
            .limit(1)
        ).one_or_none()
        if newest is None:
            return None
        is_historical = identity_given or not (
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
    req_rows = get_requirements(conn, int(newest.id))
    support_by_req = get_support_bulk(conn, [int(req.id) for req in req_rows])
    for req in req_rows:
        raw_span = (req.jd_locator_json or {}).get("span")
        quote = ""
        # A malformed locator must not crash this read: the eval tables are append-only and
        # trigger-guarded, so a poison row could never be corrected, only superseded.
        if isinstance(raw_span, list) and len(raw_span) == 2:
            try:
                quote = body_text[int(raw_span[0]) : int(raw_span[1])]
            except (TypeError, ValueError):
                quote = ""
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
            for sup in support_by_req.get(int(req.id), ())
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
