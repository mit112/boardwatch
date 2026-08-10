"""Conflicts, owner rulings, approval stamps, and the append-only ledgers (design §13, §17).

Three properties are load-bearing here and each one is a refusal rather than a convention.

**Owner authority is never inferred from a YAML string.** An agent may propose `owner_confirmed`,
`approved`, or `authorized_by: owner` in a draft; none of them establish anything. Authority comes
from an approval stamp bound to the draft's exact candidate-content digest, which is why
`ApprovalEntry` carries `target_content_digest` and why target records never point back at their
approvals — that direction would make the digest computation cyclic.

**Ledgers are append-only.** Promotion requires the parent's canonical change, approval, and ruling
sequences as identical prefixes, plus exactly one new change and one new stamp. Removing,
reordering, or editing a prior entry is a hard failure, so history cannot be rewritten to make a
present state look justified.

**Resolving a conflict never deletes a candidate.** A ruling selects; the losing facts stay, and a
later ruling can reopen the group. That is the difference between a decision log and an edit.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated, Final

from pydantic import Field, PositiveInt, model_validator

from boardwatch.profile_bundle.models.base import (
    ApprovalId,
    ApprovalStampId,
    ChangeId,
    ConflictId,
    EntityId,
    EvidenceId,
    FactId,
    NonBlankStr,
    PredicateId,
    RecordId,
    RulingId,
    Sha256Digest,
    StrictModel,
    UniqueOrdered,
    UniqueSorted,
    UtcTimestamp,
    prefix_of,
)


class Actor(StrEnum):
    """Who performed a change (§17). `authorized_by` is DERIVED from the matching approval stamp,
    never trusted from the YAML, so an `importer` actor cannot authorise its own promotion."""

    OWNER = "owner"
    AGENT = "agent"
    IMPORTER = "importer"


# --------------------------------------------------------------------------------------
# Conflicts and rulings
# --------------------------------------------------------------------------------------


class ConflictState(StrEnum):
    """`reopened` exists because new evidence must be able to reopen a settled group without
    deleting the ruling that settled it (§13)."""

    UNRESOLVED = "unresolved"
    RESOLVED = "resolved"
    REOPENED = "reopened"


class RulingDecision(StrEnum):
    SELECT_CANDIDATE = "select_candidate"
    REPLACE_ALL = "replace_all"
    KEEP_UNRESOLVED = "keep_unresolved"
    NOT_APPLICABLE = "not_applicable"


class ConflictRecord(StrictModel):
    """One group of competing otherwise-effective values for one subject and predicate (§13).

    At least two candidates: a "conflict" with one candidate has nothing to choose between, and
    admitting it would let a fact be parked in a permanently unresolved group to dodge cardinality.
    """

    conflict_id: ConflictId
    subject_id: EntityId
    predicate: PredicateId
    state: ConflictState
    candidate_fact_ids: Annotated[tuple[FactId, ...], UniqueSorted] = Field(min_length=2)
    active_ruling_id: RulingId | None
    opened_at: date

    @model_validator(mode="after")
    def _resolved_groups_name_their_ruling(self) -> ConflictRecord:
        if self.state is ConflictState.RESOLVED and self.active_ruling_id is None:
            raise ValueError(f"{self.conflict_id}: state is resolved but no active ruling is named")
        return self


class RulingRecord(StrictModel):
    """One append-only owner decision about a conflict (§13).

    `select_candidate` names the winner; every other decision must not, because a `keep_unresolved`
    or `not_applicable` ruling that also selected a fact would make the group both undecided and
    decided.
    """

    ruling_id: RulingId
    conflict_id: ConflictId
    decision: RulingDecision
    selected_fact_id: FactId | None
    rejected_fact_ids: Annotated[tuple[FactId, ...], UniqueSorted]
    rationale: NonBlankStr
    owner_evidence_id: EvidenceId
    decided_at: date

    @model_validator(mode="after")
    def _selection_matches_the_decision(self) -> RulingRecord:
        if self.decision is RulingDecision.SELECT_CANDIDATE:
            if self.selected_fact_id is None:
                raise ValueError(f"{self.ruling_id}: select_candidate names no selected fact")
        elif self.selected_fact_id is not None:
            raise ValueError(
                f"{self.ruling_id}: decision {self.decision.value} must not select a fact"
            )
        if self.selected_fact_id is not None and self.selected_fact_id in self.rejected_fact_ids:
            raise ValueError(
                f"{self.ruling_id}: {self.selected_fact_id} is both selected and rejected"
            )
        return self


# --------------------------------------------------------------------------------------
# Approvals
# --------------------------------------------------------------------------------------


class ApprovalAction(StrEnum):
    """The closed sub-approval catalog (§13). Each action has one legal target record kind."""

    CONFIRM_FACT = "confirm_fact"
    CONFIRM_CONTACT = "confirm_contact"
    APPROVE_EVIDENCE_SUFFICIENCY = "approve_evidence_sufficiency"
    APPROVE_CLAIM = "approve_claim"
    APPROVE_METRIC_SURFACES = "approve_metric_surfaces"
    APPROVE_SOURCE_SCOPE = "approve_source_scope"
    APPROVE_SOURCE_RECORD_EXCLUSION = "approve_source_record_exclusion"
    AUTHORIZE_CONFLICT_RULING = "authorize_conflict_ruling"


#: action -> the record-kind prefix its target must have. Checked at parse time so a
#: `confirm_contact` cannot be pointed at a fact and quietly widen that fact's surfaces.
APPROVAL_TARGET_PREFIX: Final[dict[ApprovalAction, str]] = {
    ApprovalAction.CONFIRM_FACT: "fact",
    ApprovalAction.CONFIRM_CONTACT: "contact",
    ApprovalAction.APPROVE_EVIDENCE_SUFFICIENCY: "evidence",
    ApprovalAction.APPROVE_CLAIM: "claim",
    ApprovalAction.APPROVE_METRIC_SURFACES: "metric",
    ApprovalAction.APPROVE_SOURCE_SCOPE: "source",
    ApprovalAction.APPROVE_SOURCE_RECORD_EXCLUSION: "source-record",
    ApprovalAction.AUTHORIZE_CONFLICT_RULING: "ruling",
}

#: action -> the state it establishes. A stamp claiming a different resulting state is refused, so
#: an `approve_claim` cannot be repurposed to mark a claim `rejected`.
APPROVAL_RESULTING_STATE: Final[dict[ApprovalAction, str]] = {
    ApprovalAction.CONFIRM_FACT: "owner_confirmed",
    ApprovalAction.CONFIRM_CONTACT: "owner_confirmed",
    ApprovalAction.APPROVE_EVIDENCE_SUFFICIENCY: "owner_approved",
    ApprovalAction.APPROVE_CLAIM: "approved",
    ApprovalAction.APPROVE_METRIC_SURFACES: "approved",
    ApprovalAction.APPROVE_SOURCE_SCOPE: "approved",
    ApprovalAction.APPROVE_SOURCE_RECORD_EXCLUSION: "owner_excluded",
    ApprovalAction.AUTHORIZE_CONFLICT_RULING: "authorized",
}


class ApprovedVia(StrEnum):
    """How the owner confirmed. One member today, and it is the seam: adding a second is a visible
    schema decision rather than a free-text string a caller can invent."""

    CONTROLLING_TERMINAL = "controlling_terminal"


class ApprovalEntry(StrictModel):
    """One owner decision inside the revision's single stamp (§13).

    `target_content_digest` is the canonical digest of the target record BEFORE any approval
    metadata is attached, which is what makes the binding acyclic and what makes a post-approval
    edit detectable.
    """

    approval_id: ApprovalId
    action: ApprovalAction
    target_record_id: RecordId
    target_content_digest: Sha256Digest
    resulting_state: NonBlankStr

    @model_validator(mode="after")
    def _target_kind_and_state_match_the_action(self) -> ApprovalEntry:
        expected_prefix = APPROVAL_TARGET_PREFIX[self.action]
        actual_prefix = prefix_of(self.target_record_id)
        if actual_prefix != expected_prefix:
            raise ValueError(
                f"{self.approval_id}: action {self.action.value} targets a "
                f"{expected_prefix!r} record, got {actual_prefix or 'unknown'!r}"
            )
        expected_state = APPROVAL_RESULTING_STATE[self.action]
        if self.resulting_state != expected_state:
            raise ValueError(
                f"{self.approval_id}: action {self.action.value} establishes "
                f"{expected_state!r}, not {self.resulting_state!r}"
            )
        return self


class ApprovalStamp(StrictModel):
    """One promoted revision appends exactly one stamp, which may carry any number of entries (§13).

    `entries` may be empty: the stamp itself authorizes the candidate revision, so a revision whose
    diff triggers no sub-approval needs none. An empty list is therefore a legitimate state, not a
    missing approval.
    """

    approval_stamp_id: ApprovalStampId
    candidate_content_digest: Sha256Digest
    approved_at: UtcTimestamp
    approved_via: ApprovedVia
    entries: tuple[ApprovalEntry, ...]

    @model_validator(mode="after")
    def _approval_ids_are_unique(self) -> ApprovalStamp:
        seen: set[str] = set()
        for entry in self.entries:
            if entry.approval_id in seen:
                raise ValueError(f"duplicate approval_id {entry.approval_id!r} in one stamp")
            seen.add(entry.approval_id)
        return self

    def entries_for(self, action: ApprovalAction, target: str) -> tuple[ApprovalEntry, ...]:
        return tuple(
            entry
            for entry in self.entries
            if entry.action is action and entry.target_record_id == target
        )


# --------------------------------------------------------------------------------------
# Change ledger
# --------------------------------------------------------------------------------------


class ChangeRecord(StrictModel):
    """One promoted revision's change record (§17).

    The resulting bundle digest deliberately lives only in the manifest: putting it here would make
    the change record contain a hash of a document containing the change record.

    `changed_record_ids` is derived by the authoring CLI from the validated draft diff rather than
    trusted from a manually authored list, which is why nothing downstream treats it as authority
    for what actually changed — the record digests do.
    """

    change_id: ChangeId
    revision: PositiveInt
    parent_bundle_digest: Sha256Digest | None
    actor: Actor
    authorized_by: Actor
    summary: NonBlankStr
    changed_record_ids: Annotated[tuple[RecordId, ...], UniqueSorted]
    created_at: UtcTimestamp

    @model_validator(mode="after")
    def _revision_one_has_no_parent(self) -> ChangeRecord:
        if self.revision == 1 and self.parent_bundle_digest is not None:
            raise ValueError("revision 1 cannot name a parent bundle digest")
        if self.revision > 1 and self.parent_bundle_digest is None:
            raise ValueError(f"revision {self.revision} must name its parent bundle digest")
        return self


class ChangeLedger(StrictModel):
    """`history/changes.yaml`. Append-only, and contiguous from revision 1.

    A gap would make "change-ledger length equals the revision number" unenforceable, which is the
    cheap check that catches a rewritten history without recomputing every ancestor.
    """

    changes: Annotated[tuple[ChangeRecord, ...], UniqueOrdered]

    @model_validator(mode="after")
    def _revisions_are_contiguous_from_one(self) -> ChangeLedger:
        for index, record in enumerate(self.changes, start=1):
            if record.revision != index:
                raise ValueError(
                    f"change ledger entry {index} declares revision {record.revision}; the "
                    "sequence must be contiguous from 1"
                )
        seen: set[str] = set()
        for record in self.changes:
            if record.change_id in seen:
                raise ValueError(f"duplicate change_id {record.change_id!r}")
            seen.add(record.change_id)
        return self


class ApprovalLedger(StrictModel):
    """`history/approvals.yaml`. One stamp per promoted revision, in promotion order."""

    approvals: Annotated[tuple[ApprovalStamp, ...], UniqueOrdered]

    @model_validator(mode="after")
    def _stamp_ids_are_unique(self) -> ApprovalLedger:
        seen: set[str] = set()
        for stamp in self.approvals:
            if stamp.approval_stamp_id in seen:
                raise ValueError(f"duplicate approval_stamp_id {stamp.approval_stamp_id!r}")
            seen.add(stamp.approval_stamp_id)
        return self


class ConflictGroups(StrictModel):
    """`conflicts/groups.yaml`."""

    conflicts: tuple[ConflictRecord, ...]


class ConflictRulings(StrictModel):
    """`conflicts/rulings.yaml`. Append-only: promotion requires the parent sequence as a prefix."""

    rulings: Annotated[tuple[RulingRecord, ...], UniqueOrdered]
