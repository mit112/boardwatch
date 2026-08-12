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
