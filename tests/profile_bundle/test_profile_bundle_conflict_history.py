"""T11 append-only history validation."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path, PurePosixPath

from boardwatch.profile_bundle.errors import IssueCode
from boardwatch.profile_bundle.index import build_index
from boardwatch.profile_bundle.models.documents import BundleDocuments
from boardwatch.profile_bundle.models.history import ApprovalLedger, ChangeLedger
from boardwatch.profile_bundle.validation import ParentSnapshot, context_from_documents
from boardwatch.profile_bundle.validation.history import validate_history


def _with_history(fixture) -> BundleDocuments:
    by_path = dict(fixture.documents.by_path)
    by_path[PurePosixPath("history/changes.yaml")] = ChangeLedger(changes=(fixture.change,))
    by_path[PurePosixPath("history/approvals.yaml")] = ApprovalLedger(
        approvals=(fixture.approval,)
    )
    return BundleDocuments(manifest=fixture.manifest, by_path=by_path)


def test_a_promoted_revision_with_one_change_and_one_stamp_is_clean(
    promoted_revision_fixture,
) -> None:
    documents = _with_history(promoted_revision_fixture)
    ctx = context_from_documents(documents, root=PurePosixPath("."), mode="revision")
    assert validate_history(ctx) == ()


def test_revision_one_requires_exactly_one_change_and_approval_stamp(
    promoted_revision_fixture,
) -> None:
    documents = promoted_revision_fixture.documents
    ctx = context_from_documents(
        BundleDocuments(manifest=promoted_revision_fixture.manifest, by_path=documents.by_path),
        root=PurePosixPath("."),
        mode="revision",
    )
    codes = {finding.code for finding in validate_history(ctx)}
    assert IssueCode.CHANGE_LEDGER_LENGTH_MISMATCH in codes
    assert IssueCode.APPROVAL_STAMP_COUNT_MISMATCH in codes


def test_a_missing_required_owner_entry_is_reported(promoted_revision_fixture) -> None:
    documents = _with_history(promoted_revision_fixture)
    approval_path = PurePosixPath("history/approvals.yaml")
    by_path = dict(documents.by_path)
    by_path[approval_path] = ApprovalLedger(approvals=(promoted_revision_fixture.approval.model_copy(update={"entries": ()}),))
    ctx = context_from_documents(
        BundleDocuments(manifest=documents.manifest, by_path=by_path),
        root=Path("."),
        mode="revision",
    )
    codes = {finding.code for finding in validate_history(ctx)}
    assert IssueCode.MISSING_OWNER_APPROVAL in codes


def test_a_stale_target_digest_is_reported(promoted_revision_fixture) -> None:
    documents = _with_history(promoted_revision_fixture)
    first = promoted_revision_fixture.approval.entries[0]
    stale = first.model_copy(update={"target_content_digest": "sha256:" + "f" * 64})
    approval = promoted_revision_fixture.approval.model_copy(update={"entries": (stale, *promoted_revision_fixture.approval.entries[1:])})
    by_path = dict(documents.by_path)
    by_path[PurePosixPath("history/approvals.yaml")] = ApprovalLedger(approvals=(approval,))
    ctx = context_from_documents(
        BundleDocuments(manifest=documents.manifest, by_path=by_path),
        root=Path("."),
        mode="revision",
    )
    codes = {finding.code for finding in validate_history(ctx)}
    assert IssueCode.APPROVAL_TARGET_DIGEST_MISMATCH in codes


def test_a_forged_authorized_by_value_is_reported(promoted_revision_fixture) -> None:
    documents = _with_history(promoted_revision_fixture)
    forged = promoted_revision_fixture.change.model_copy(update={"authorized_by": "agent"})
    by_path = dict(documents.by_path)
    by_path[PurePosixPath("history/changes.yaml")] = ChangeLedger(changes=(forged,))
    ctx = context_from_documents(
        BundleDocuments(manifest=documents.manifest, by_path=by_path),
        root=Path("."),
        mode="revision",
    )
    assert IssueCode.CHANGE_ENTRY_MISMATCH in {
        finding.code for finding in validate_history(ctx)
    }


def test_parent_ledgers_are_prefixes_and_promotion_appends_one_change_and_stamp(
    promoted_revision_fixture,
) -> None:
    parent = _with_history(promoted_revision_fixture)
    parent_index = build_index(parent)
    parent_manifest = promoted_revision_fixture.manifest
    current_manifest = parent_manifest.model_copy(
        update={
            "revision": 2,
            "parent_bundle_digest": parent_manifest.bundle_digest,
            "bundle_digest": "sha256:" + "3" * 64,
            "approved_candidate_digest": "sha256:" + "4" * 64,
            "approval_stamp_id": "approval-stamp.000002",
            "change_id": "change.example.000002",
        }
    )
    change = promoted_revision_fixture.change.model_copy(
        update={
            "change_id": "change.example.000002",
            "revision": 2,
            "parent_bundle_digest": parent_manifest.bundle_digest,
        }
    )
    stamp = promoted_revision_fixture.approval.model_copy(
        update={
            "approval_stamp_id": "approval-stamp.000002",
            "candidate_content_digest": "sha256:" + "4" * 64,
            "entries": (),
        }
    )
    by_path = dict(parent.by_path)
    by_path[PurePosixPath("history/changes.yaml")] = ChangeLedger(
        changes=(promoted_revision_fixture.change, change)
    )
    by_path[PurePosixPath("history/approvals.yaml")] = ApprovalLedger(
        approvals=(promoted_revision_fixture.approval, stamp)
    )
    current = BundleDocuments(manifest=current_manifest, by_path=by_path)
    ctx = context_from_documents(current, root=Path("."), mode="revision")
    ctx = replace(
        ctx,
        parent=ParentSnapshot(
            root=Path("."),
            documents=parent,
            envelope=parent_manifest.envelope,
            index=parent_index,
        ),
    )
    assert validate_history(ctx) == ()

    mutated_change = promoted_revision_fixture.change.model_copy(update={"summary": "edited old history"})
    by_path[PurePosixPath("history/changes.yaml")] = ChangeLedger(
        changes=(mutated_change, change)
    )
    mutated = context_from_documents(
        BundleDocuments(manifest=current_manifest, by_path=by_path),
        root=Path("."),
        mode="revision",
    )
    mutated = replace(
        mutated,
        parent=ParentSnapshot(
            root=Path("."), documents=parent, envelope=parent_manifest.envelope, index=parent_index
        ),
    )
    assert IssueCode.LEDGER_PREFIX_CHANGED in {finding.code for finding in validate_history(mutated)}
