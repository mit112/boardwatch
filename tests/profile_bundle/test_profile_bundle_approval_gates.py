"""T11 owner-gate derivation and pure approval-stamp construction."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from boardwatch.profile_bundle.approvals import (
    ApprovalDecision,
    _joined_source_digest,
    build_approval_stamp,
    required_approval_decisions,
)
from boardwatch.profile_bundle.canonical import source_scope_target_digest
from boardwatch.profile_bundle.errors import ProfileBundleError
from boardwatch.profile_bundle.models.history import ApprovalAction
from boardwatch.profile_bundle.models.imports import SourceLedgerSource
from boardwatch.profile_bundle.models.policy import SourceSpec


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


# --------------------------------------------------------------------------------------
# `approve_source_scope`'s joined target digest (§13) — the twin of the exclusion gate's
# --------------------------------------------------------------------------------------

#: The scope join as `approvals.py` has always spelled it, and therefore as every promoted
#: revision's stamp already binds. Computed from the two records authored below, NOT from the
#: function under test: a value read back off `source_scope_target_digest` would agree with
#: whatever that function currently does, which is the one thing this pins.
PINNED_SCOPE_DIGEST = "sha256:a254525715cf480835e1af23770cf7402952adf1341632c6cf379b6076d055d3"


def _pinned_scope_pair() -> tuple[SourceSpec, SourceLedgerSource]:
    source = SourceSpec.model_validate(
        {
            "source_id": "source.frozen-digest-pin",
            "source_kind": "repository_markdown",
            "portable_locator": "notes/source.md",
        }
    )
    ledger = SourceLedgerSource.model_validate(
        {
            "source_id": "source.frozen-digest-pin",
            "enumerator_id": "markdown-headings",
            "enumerator_version": 1,
            "source_content_digest": "sha256:" + "11" * 32,
            "approved_scope": {"kind": "complete_file"},
            "source_record_ids": [],
        }
    )
    return source, ledger


def test_the_scope_target_digest_keeps_the_spelling_already_on_disk() -> None:
    """The positional-pair spelling `approvals.py` stamped while the helper had no caller.

    A keyed `{"source": ..., "ledger": ...}` mapping is the natural thing to write here and
    produces a different digest — which is exactly what `source_scope_target_digest` returned
    while nothing called it, so no test could see the divergence. Re-spelling the enforced join
    to match the helper would silently invalidate every `approve_source_scope` stamp already on
    disk, so the helper is the side that moves.
    """
    source, ledger = _pinned_scope_pair()

    assert source_scope_target_digest(source, ledger) == PINNED_SCOPE_DIGEST


def test_the_enforced_scope_join_and_the_named_helper_are_one_value() -> None:
    """§13 names `source_scope_target_digest` as this gate's target. Two spellings of one join
    are two chances to disagree, and the disagreement is invisible: the owner stamps whatever
    `approvals.py` computes, while the documented helper is what a reader checks against.
    """
    source, ledger = _pinned_scope_pair()

    assert _joined_source_digest(source, ledger) == source_scope_target_digest(source, ledger)


def test_the_enforced_scope_join_delegates_rather_than_re_spelling(monkeypatch) -> None:
    """Equality alone would still hold if both sides re-derived the same join independently, and
    that is the state this change exists to leave. Patching the name `approvals` resolves proves
    the call actually happens, so a future inline re-spelling fails here rather than drifting.
    """
    sentinel = "sha256:" + "c" * 64
    monkeypatch.setattr(
        "boardwatch.profile_bundle.approvals.source_scope_target_digest",
        lambda source, ledger: sentinel,
    )
    source, ledger = _pinned_scope_pair()

    assert _joined_source_digest(source, ledger) == sentinel
