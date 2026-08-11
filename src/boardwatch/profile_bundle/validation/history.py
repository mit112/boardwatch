"""T11 owner-gate and append-only history validation."""

from __future__ import annotations

from collections.abc import Iterable

from boardwatch.profile_bundle.approvals import ApprovalDecision, required_approval_decisions
from boardwatch.profile_bundle.canonical import record_digest
from boardwatch.profile_bundle.errors import Diagnostic, IssueCode, diagnostic
from boardwatch.profile_bundle.models.history import (
    ApprovalEntry,
    ApprovalStamp,
)
from boardwatch.profile_bundle.models.manifests import RevisionManifest
from boardwatch.profile_bundle.validation.context import ValidationContext


def _same_prefix(current: Iterable[object], parent: Iterable[object]) -> bool:
    current_values = tuple(record_digest(item) for item in current)  # type: ignore[arg-type]
    parent_values = tuple(record_digest(item) for item in parent)  # type: ignore[arg-type]
    return (
        len(current_values) >= len(parent_values)
        and current_values[: len(parent_values)] == parent_values
    )


def _entry_for(decision: ApprovalDecision, stamp: ApprovalStamp) -> ApprovalEntry | None:
    for entry in stamp.entries:
        if entry.action is decision.action and entry.target_record_id == decision.target_record_id:
            return entry
    return None


def validate_history(ctx: ValidationContext) -> tuple[Diagnostic, ...]:
    """Validate promotion-shaped ledgers, prefixes, and every derived owner gate."""
    if ctx.mode != "revision" or not isinstance(ctx.manifest, RevisionManifest):
        return ()
    manifest = ctx.manifest
    changes = ctx.index.changes
    stamps = ctx.index.stamps
    rulings = ctx.index.rulings
    findings: list[Diagnostic] = []

    if len(changes) != manifest.revision:
        findings.append(
            diagnostic(
                IssueCode.CHANGE_LEDGER_LENGTH_MISMATCH,
                f"change ledger has {len(changes)} entries for revision {manifest.revision}",
                path="history/changes.yaml",
            )
        )
    if len(stamps) != manifest.revision:
        findings.append(
            diagnostic(
                IssueCode.APPROVAL_STAMP_COUNT_MISMATCH,
                f"approval ledger has {len(stamps)} stamps for revision {manifest.revision}",
                path="history/approvals.yaml",
            )
        )

    if changes:
        latest = changes[-1]
        if latest.revision != manifest.revision or latest.change_id != manifest.change_id:
            findings.append(
                diagnostic(
                    IssueCode.CHANGE_ENTRY_MISMATCH,
                    "latest change does not match the revision manifest",
                    path="history/changes.yaml",
                )
            )
    if stamps:
        latest_stamp = stamps[-1]
        if (
            latest_stamp.approval_stamp_id != manifest.approval_stamp_id
            or latest_stamp.candidate_content_digest != manifest.approved_candidate_digest
        ):
            findings.append(
                diagnostic(
                    IssueCode.APPROVAL_TARGET_DIGEST_MISMATCH,
                    "latest approval stamp does not match the revision manifest",
                    path="history/approvals.yaml",
                )
            )

    if ctx.parent is not None:
        parent = ctx.parent.index
        if (
            not _same_prefix(changes, parent.changes)
            or not _same_prefix(stamps, parent.stamps)
            or not _same_prefix(rulings, parent.rulings)
        ):
            findings.append(
                diagnostic(
                    IssueCode.LEDGER_PREFIX_CHANGED,
                    "revision history changed an existing change, approval, or ruling entry",
                    path="history",
                )
            )
        if len(changes) != len(parent.changes) + 1 or len(stamps) != len(parent.stamps) + 1:
            findings.append(
                diagnostic(
                    IssueCode.CHANGE_LEDGER_LENGTH_MISMATCH,
                    "promotion must append exactly one change and one approval stamp",
                    path="history",
                )
            )

    if not stamps:
        return tuple(findings)
    parent_documents = ctx.parent.documents if ctx.parent is not None else None
    required = required_approval_decisions(ctx.documents, parent_documents)
    latest_stamp = stamps[-1]
    expected_keys = {(item.action, item.target_record_id) for item in required}
    for decision in required:
        entry = _entry_for(decision, latest_stamp)
        if entry is None:
            findings.append(
                diagnostic(
                    IssueCode.MISSING_OWNER_APPROVAL,
                    f"missing {decision.action.value} approval for {decision.target_record_id}",
                    path="history/approvals.yaml",
                    record_id=decision.target_record_id,
                )
            )
            continue
        if entry.target_content_digest != decision.target_content_digest:
            findings.append(
                diagnostic(
                    IssueCode.APPROVAL_TARGET_DIGEST_MISMATCH,
                    f"approval for {decision.target_record_id} binds stale target content",
                    path="history/approvals.yaml",
                    record_id=decision.target_record_id,
                )
            )
    for entry in latest_stamp.entries:
        if (entry.action, entry.target_record_id) not in expected_keys:
            findings.append(
                diagnostic(
                    IssueCode.APPROVAL_ENTRY_UNEXPECTED,
                    f"approval entry {entry.approval_id} has no required owner-gated transition",
                    path="history/approvals.yaml",
                    record_id=entry.target_record_id,
                )
            )
    return tuple(findings)
