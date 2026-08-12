"""T11 owner-gate derivation and pure approval-stamp construction."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from boardwatch.profile_bundle.approvals import (
    ApprovalDecision,
    build_approval_stamp,
    required_approval_decisions,
)
from boardwatch.profile_bundle.errors import ProfileBundleError
from boardwatch.profile_bundle.models.history import ApprovalAction


def test_the_shared_fixture_is_a_promoted_revision_with_one_change_and_stamp(
    promoted_revision_fixture,
) -> None:
    assert promoted_revision_fixture.manifest.revision == 1
    assert promoted_revision_fixture.change.revision == 1
    assert promoted_revision_fixture.approval.approval_stamp_id == "approval-stamp.000001"
    assert promoted_revision_fixture.approval.entries


def test_required_owner_decisions_are_derived_from_a_real_candidate_tree(
    synthetic_bundle,
) -> None:
    decisions = required_approval_decisions(
        __import__("tests.profile_bundle.conftest", fromlist=["parse_documents"]).parse_documents(
            synthetic_bundle.draft
        ),
        None,
    )
    assert decisions
    assert any(decision.action is ApprovalAction.CONFIRM_FACT for decision in decisions)
    assert any(decision.action is ApprovalAction.CONFIRM_CONTACT for decision in decisions)


def test_pure_stamp_constructor_binds_decision_and_performs_no_io() -> None:
    decision = ApprovalDecision(
        action=ApprovalAction.CONFIRM_CONTACT,
        target_record_id="contact.example.email",
        target_content_digest="sha256:" + "a" * 64,
        resulting_state="owner_confirmed",
    )
    stamp = build_approval_stamp(
        stamp_id="approval-stamp.000002",
        candidate_digest="sha256:" + "b" * 64,
        approved_at=datetime(2026, 8, 10, 12, tzinfo=UTC),
        decisions=[decision],
    )
    assert stamp.candidate_content_digest == "sha256:" + "b" * 64
    assert stamp.entries[0].action is ApprovalAction.CONFIRM_CONTACT
    assert stamp.entries[0].target_record_id == "contact.example.email"


def test_an_approval_entry_cannot_cross_target_kind_or_resulting_state() -> None:
    decision = ApprovalDecision(
        action=ApprovalAction.CONFIRM_FACT,
        target_record_id="contact.example.email",
        target_content_digest="sha256:" + "a" * 64,
        resulting_state="owner_confirmed",
    )
    with pytest.raises(ValidationError):
        build_approval_stamp(
            stamp_id="approval-stamp.000002",
            candidate_digest="sha256:" + "b" * 64,
            approved_at=datetime(2026, 8, 10, 12, tzinfo=UTC),
            decisions=[decision],
        )


def test_two_stamps_approving_one_record_do_not_reuse_an_approval_id() -> None:
    """§8 makes approval IDs unique across the bundle, and `validate_structural` checks them there.

    A record the owner edits and re-approves is the ordinary case, so numbering per action and
    target alone — restarting at `001` in every stamp — made the second revision unpromotable:
    `duplicate_approval_id` fired on a ledger both stamps of which were correct. The scope has to
    come from something that differs between stamps, and the stamp's own ID is the only thing that
    does by contract.
    """
    decision = ApprovalDecision(
        action=ApprovalAction.CONFIRM_FACT,
        target_record_id="fact.example.name.001",
        target_content_digest="sha256:" + "a" * 64,
        resulting_state="owner_confirmed",
    )
    first = build_approval_stamp(
        stamp_id="approval-stamp.000001",
        candidate_digest="sha256:" + "b" * 64,
        approved_at=datetime(2026, 8, 10, 12, tzinfo=UTC),
        decisions=[decision],
    )
    second = build_approval_stamp(
        stamp_id="approval-stamp.000002",
        candidate_digest="sha256:" + "c" * 64,
        approved_at=datetime(2026, 8, 11, 12, tzinfo=UTC),
        decisions=[decision],
    )

    assert first.entries[0].approval_id != second.entries[0].approval_id
    assert not {entry.approval_id for entry in first.entries} & {
        entry.approval_id for entry in second.entries
    }


def test_a_dotted_stamp_scope_is_refused_because_it_could_collide() -> None:
    """The reproduction of the collision the derivation now cannot produce.

    `ID_TAIL` admits `.` inside a stamp ID's tail and inside a record ID alike, so joining scope,
    action and target with `.` left the boundaries unrecoverable: these two stamps carry different
    stamp IDs, so `ApprovalLedger` accepts both in one ledger, and yet they derive the same approval
    ID. Refusing a dotted scope is what makes "unique by construction" a property of the code rather
    than a convention about whatever files the stamp.
    """
    colliding = ApprovalDecision(
        action=ApprovalAction.APPROVE_CLAIM,
        target_record_id="claim.w",
        target_content_digest="sha256:" + "a" * 64,
        resulting_state="approved",
    )
    with pytest.raises(ProfileBundleError, match="dotted tail"):
        build_approval_stamp(
            stamp_id="approval-stamp.000001.confirm_fact.fact",
            candidate_digest="sha256:" + "b" * 64,
            approved_at=datetime(2026, 8, 10, 12, tzinfo=UTC),
            decisions=[colliding],
        )


def test_a_dotted_target_alone_still_derives_a_distinct_id_per_stamp() -> None:
    """The negative control: what is refused above is the dotted SCOPE, not a dotted record ID.

    The target here is the other half of the collision — a record ID whose own tail carries the
    action name of the stamp above — and with dot-free scopes the two IDs differ, so the refusal is
    narrow rather than a ban on ordinary record IDs.
    """
    decision = ApprovalDecision(
        action=ApprovalAction.CONFIRM_FACT,
        target_record_id="fact.approve_claim.claim.w",
        target_content_digest="sha256:" + "a" * 64,
        resulting_state="owner_confirmed",
    )
    ids = [
        build_approval_stamp(
            stamp_id=stamp_id,
            candidate_digest="sha256:" + "b" * 64,
            approved_at=datetime(2026, 8, 10, 12, tzinfo=UTC),
            decisions=[decision],
        ).entries[0].approval_id
        for stamp_id in ("approval-stamp.000001", "approval-stamp.000002")
    ]

    assert len(set(ids)) == 2
