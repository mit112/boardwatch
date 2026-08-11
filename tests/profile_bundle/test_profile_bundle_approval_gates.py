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
