"""Pure owner-gate derivation and approval-stamp construction for T11.

This module deliberately contains no terminal or filesystem behavior. The command layer owns the
controlling-TTY confirmation; this pure seam receives the confirmed decisions and produces the
typed stamp that history validation can bind to the candidate.

It also owns the stamp's stored *byte* form, for the same reason it owns the stamp's shape: the
approval that `approve` files under `approvals/sha256-<candidate>.yaml` is the one `promote` reads
back, and two spellings of one document is two chances for an owner's approval to become unreadable
to the command that needs it. Where those bytes go is `paths.approval_path`'s; writing them is the
command layer's.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath

from boardwatch.profile_bundle.canonical import digest_of, normalized, record_digest
from boardwatch.profile_bundle.errors import ProfileBundleError
from boardwatch.profile_bundle.index import BundleIndex, build_index
from boardwatch.profile_bundle.models.documents import BundleDocuments
from boardwatch.profile_bundle.models.history import (
    ApprovalAction,
    ApprovalEntry,
    ApprovalStamp,
)
from boardwatch.profile_bundle.models.policy import SourceSpec
from boardwatch.profile_bundle.yaml_writer import document_bytes


@dataclass(frozen=True)
class ApprovalDecision:
    """One owner-gated transition required by a candidate revision."""

    action: ApprovalAction
    target_record_id: str
    target_content_digest: str
    resulting_state: str


def _record_map(index: BundleIndex) -> dict[str, object]:
    return dict(index.records)


def _changed(candidate: object, parent: object | None) -> bool:
    return parent is None or record_digest(candidate) != record_digest(parent)  # type: ignore[arg-type]


def _joined_source_digest(source: SourceSpec, ledger: object) -> str:
    return digest_of([normalized(source), normalized(ledger)])  # type: ignore[arg-type]


def _source_decisions(candidate: BundleIndex, parent: BundleIndex | None) -> list[ApprovalDecision]:
    decisions: list[ApprovalDecision] = []
    parent_sources = parent.sources.by_id if parent and parent.sources else {}
    parent_ledger = parent.source_ledger.sources if parent and parent.source_ledger else ()
    parent_ledger_by_id = {source.source_id: source for source in parent_ledger}
    ledger_by_id = (
        {source.source_id: source for source in candidate.source_ledger.sources}
        if candidate.source_ledger
        else {}
    )
    if candidate.sources is None:
        return decisions
    for source in candidate.sources.sources:
        ledger = ledger_by_id.get(source.source_id)
        if ledger is None:
            continue
        old_source = parent_sources.get(source.source_id)
        old_ledger = parent_ledger_by_id.get(source.source_id)
        old_digest = (
            _joined_source_digest(old_source, old_ledger)
            if old_source is not None and old_ledger is not None
            else None
        )
        new_digest = _joined_source_digest(source, ledger)
        if old_digest != new_digest:
            decisions.append(
                ApprovalDecision(
                    action=ApprovalAction.APPROVE_SOURCE_SCOPE,
                    target_record_id=source.source_id,
                    target_content_digest=new_digest,
                    resulting_state="approved",
                )
            )
    return decisions


def _exclusion_decisions(
    candidate: BundleIndex, parent: BundleIndex | None
) -> list[ApprovalDecision]:
    parent_by_id = (
        {record.source_record_id: record for record in parent.ledger_records}
        if parent
        else {}
    )
    ledger_by_id = {record.source_record_id: record for record in candidate.ledger_records}
    decisions: list[ApprovalDecision] = []
    for exclusion in candidate.exclusions:
        if exclusion.reason.value != "owner_excluded":
            continue
        ledger = ledger_by_id.get(exclusion.source_record_id)
        old_exclusion = next(
            (
                item
                for item in (parent.exclusions if parent else ())
                if item.source_record_id == exclusion.source_record_id
            ),
            None,
        )
        old_ledger = parent_by_id.get(exclusion.source_record_id)
        old_digest = (
            digest_of([normalized(old_ledger), normalized(old_exclusion)])
            if old_ledger is not None and old_exclusion is not None
            else None
        )
        new_digest = (
            digest_of([normalized(ledger), normalized(exclusion)])
            if ledger is not None
            else digest_of(normalized(exclusion))
        )
        if old_digest != new_digest:
            decisions.append(
                ApprovalDecision(
                    action=ApprovalAction.APPROVE_SOURCE_RECORD_EXCLUSION,
                    target_record_id=exclusion.source_record_id,
                    target_content_digest=new_digest,
                    resulting_state="owner_excluded",
                )
            )
    return decisions


def required_approval_decisions(
    candidate: BundleDocuments, parent: BundleDocuments | None
) -> tuple[ApprovalDecision, ...]:
    """Derive every owner-gated transition from candidate content and its direct parent."""
    current = build_index(candidate)
    previous = build_index(parent) if parent is not None else None
    old = _record_map(previous) if previous else {}
    decisions: list[ApprovalDecision] = []

    for record_id, record in sorted(current.records.items()):
        prior = old.get(record_id)
        if not _changed(record, prior):
            continue
        action: ApprovalAction | None = None
        resulting_state: str | None = None
        if record_id.startswith("fact.") and getattr(
            record, "verification_state", None
        ) == "owner_confirmed":
            action, resulting_state = ApprovalAction.CONFIRM_FACT, "owner_confirmed"
        elif record_id.startswith("contact."):
            action, resulting_state = ApprovalAction.CONFIRM_CONTACT, "owner_confirmed"
        elif record_id.startswith("evidence.") and getattr(
            getattr(record, "sufficiency_review", None), "state", None
        ) == "owner_approved":
            action, resulting_state = ApprovalAction.APPROVE_EVIDENCE_SUFFICIENCY, "owner_approved"
        elif record_id.startswith("claim.") and getattr(record, "status", None) == "approved":
            action, resulting_state = ApprovalAction.APPROVE_CLAIM, "approved"
        elif record_id.startswith("metric.") and (
            prior is None
            or getattr(record, "allowed_surfaces", ()) != getattr(prior, "allowed_surfaces", ())
        ):
            action, resulting_state = ApprovalAction.APPROVE_METRIC_SURFACES, "approved"
        elif record_id.startswith("ruling."):
            action, resulting_state = ApprovalAction.AUTHORIZE_CONFLICT_RULING, "authorized"
        if action is not None and resulting_state is not None:
            decisions.append(
                ApprovalDecision(
                    action=action,
                    target_record_id=record_id,
                    target_content_digest=record_digest(record),
                    resulting_state=resulting_state,
                )
            )

    decisions.extend(_source_decisions(current, previous))
    decisions.extend(_exclusion_decisions(current, previous))
    return tuple(sorted(decisions, key=lambda item: (item.action.value, item.target_record_id)))


def build_approval_stamp(
    *,
    stamp_id: str,
    candidate_digest: str,
    approved_at: datetime,
    decisions: Sequence[ApprovalDecision],
) -> ApprovalStamp:
    """Build a typed stamp from already-confirmed decisions; perform no I/O or TTY checks.

    Each generated `approval_id` carries the stamp's own scope, because §8 makes approval IDs unique
    across the whole bundle and `validate_structural` checks them across every stamp in the ledger —
    not within one. Numbering per action and target alone restarted at `001` in every stamp, so any
    record approved in two revisions produced one ID twice and the second revision could not be
    promoted at all. That is the ordinary case, not an exotic one: re-approving a record the owner
    edited again is what a bundle's history is made of, and §6's evidence-recapture recovery cannot
    complete without it.

    The scope is the stamp ID's own tail, and it must carry no `.` — which is what makes the result
    unique by construction rather than by convention. `ID_TAIL` admits `.` inside a stamp ID's tail
    and inside a record ID alike, so with a dotted scope the three components are joined by a
    character that occurs inside all of them and the boundaries are no longer recoverable: a stamp
    scoped `000001.confirm_fact.fact` approving `claim.w` derives the same ID as one scoped `000001`
    approving `fact.approve_claim.claim.w`, and `ApprovalLedger` accepts both because their stamp
    IDs differ. With a dot-free scope the first segment after `approval.` is the scope, so two
    stamps can only collide by sharing one, which is `ApprovalLedger`'s duplicate rule; and within
    one stamp the scope is constant while the action tokens are a closed catalog with no `.`, so the
    pair cannot be re-bracketed either.
    """
    scope = stamp_id.removeprefix("approval-stamp.")
    if "." in scope:
        raise ProfileBundleError(
            f"approval stamp ID {stamp_id!r} has a dotted tail; that tail is the scope every "
            "approval ID derived here carries, and a dotted one cannot be told apart from the "
            "action and target it is joined to, so two stamps could derive one approval ID"
        )
    counts: Counter[tuple[str, str]] = Counter()
    entries: list[ApprovalEntry] = []
    for decision in decisions:
        key = (decision.action.value, decision.target_record_id)
        counts[key] += 1
        approval_id = (
            f"approval.{scope}.{decision.action.value}.{decision.target_record_id}"
            f".{counts[key]:03d}"
        )
        entries.append(
            ApprovalEntry.model_validate(
                {
                    "approval_id": approval_id,
                    "action": decision.action,
                    "target_record_id": decision.target_record_id,
                    "target_content_digest": decision.target_content_digest,
                    "resulting_state": decision.resulting_state,
                }
            )
        )
    return ApprovalStamp.model_validate(
        {
            "approval_stamp_id": stamp_id,
            "candidate_content_digest": candidate_digest,
            "approved_at": approved_at,
            "approved_via": "controlling_terminal",
            "entries": entries,
        }
    )


def approval_stamp_bytes(stamp: ApprovalStamp, *, logical_path: PurePosixPath) -> bytes:
    """The stored form of one approval stamp: the stamp's own mapping, and nothing wrapping it.

    One stamp rather than a ledger of them, because `paths.approval_path` keys the file by the
    candidate digest and a candidate has exactly one approval. A list at that path could only mean
    two approvals of one thing, and a reader would have to choose between them.

    Emitted through `document_bytes` — the writer whose output this bundle's restricted loader is
    known to read back unchanged — so a stamp cannot be filed in a form `promote` cannot parse.
    """
    return document_bytes(stamp.model_dump(mode="json"), logical_path=logical_path)
