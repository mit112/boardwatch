"""Manifests, conflicts, rulings, approval stamps, and the append-only ledgers (§7, §13, §17).

The draft/revision split is the property under test. Promotion derives `revision`, `created_at`, and
`created_by`; if a draft could carry them, an agent could author `revision: 7` and promotion would
have to remember to discard it. Here the draft model has no such fields, so the refusal is a parse
error rather than a policy somebody has to enforce.

The second property is that owner authority never comes from a string. `ApprovalEntry` refuses a
target of the wrong record kind and a `resulting_state` its action does not establish, so a stamp
cannot be repurposed after the fact.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from boardwatch.profile_bundle.models.history import (
    APPROVAL_RESULTING_STATE,
    APPROVAL_TARGET_PREFIX,
    Actor,
    ApprovalAction,
    ApprovalEntry,
    ApprovalLedger,
    ApprovalStamp,
    ApprovedVia,
    ChangeLedger,
    ChangeRecord,
    ConflictGroups,
    ConflictRecord,
    ConflictRulings,
    ConflictState,
    RulingDecision,
    RulingRecord,
)
from boardwatch.profile_bundle.models.manifests import (
    BundleManifest,
    DraftManifest,
    RevisionManifest,
    StableManifestEnvelope,
)

MANIFEST_ADAPTER = TypeAdapter(BundleManifest)
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64

CATALOG_VERSIONS = {
    "predicate_catalog_version": 1,
    "unit_catalog_version": 1,
    "relation_catalog_version": 1,
    "skill_category_catalog_version": 1,
    "assertion_tag_catalog_version": 1,
    "secret_scan_ruleset_version": 1,
}


def _draft(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "state": "draft",
        "profile_id": "profile.example-candidate",
        "draft_of_revision": 1,
        "parent_bundle_digest": DIGEST_A,
        "bundle_digest": "",
        "evidence_set_digest": DIGEST_B,
        "approved_candidate_digest": "",
        "approval_stamp_id": "",
        "change_id": "",
        **CATALOG_VERSIONS,
    }
    payload.update(overrides)
    return payload


def _revision(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "state": "revision",
        "profile_id": "profile.example-candidate",
        "revision": 2,
        "parent_bundle_digest": DIGEST_A,
        "bundle_digest": DIGEST_C,
        "evidence_set_digest": DIGEST_B,
        "created_at": "2026-08-10T12:00:00Z",
        "created_by": "owner",
        "change_id": "change.000002",
        "approved_candidate_digest": DIGEST_B,
        "approval_stamp_id": "approval-stamp.000002",
        **CATALOG_VERSIONS,
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------------------
# manifests
# --------------------------------------------------------------------------------------


def test_draft_and_revision_manifests_parse_through_the_state_discriminant() -> None:
    assert isinstance(MANIFEST_ADAPTER.validate_python(_draft()), DraftManifest)
    assert isinstance(MANIFEST_ADAPTER.validate_python(_revision()), RevisionManifest)


@pytest.mark.parametrize("forbidden", ["revision", "created_at", "created_by"])
def test_a_draft_cannot_carry_a_promotion_derived_field(forbidden: str) -> None:
    values = {"revision": 7, "created_at": "2026-08-10T12:00:00Z", "created_by": "agent"}
    with pytest.raises(ValidationError):
        MANIFEST_ADAPTER.validate_python(_draft(**{forbidden: values[forbidden]}))
    assert forbidden not in DraftManifest.model_fields


@pytest.mark.parametrize(
    "sentinel", ["bundle_digest", "approved_candidate_digest", "approval_stamp_id", "change_id"]
)
def test_draft_sentinels_must_be_the_empty_string(sentinel: str) -> None:
    with pytest.raises(ValidationError):
        MANIFEST_ADAPTER.validate_python(_draft(**{sentinel: DIGEST_C}))
    with pytest.raises(ValidationError):
        MANIFEST_ADAPTER.validate_python(_draft(**{sentinel: None}))


def test_a_parentless_revision_one_draft_is_legal() -> None:
    draft = MANIFEST_ADAPTER.validate_python(
        _draft(draft_of_revision=None, parent_bundle_digest=None)
    )
    assert isinstance(draft, DraftManifest)
    assert draft.draft_of_revision is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"draft_of_revision": None},
        {"parent_bundle_digest": None},
        {"draft_of_revision": 0},
    ],
)
def test_draft_parentage_is_all_or_nothing(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        MANIFEST_ADAPTER.validate_python(_draft(**overrides))


def test_only_revision_one_may_be_parentless() -> None:
    assert MANIFEST_ADAPTER.validate_python(
        _revision(revision=1, parent_bundle_digest=None)
    ).parent_bundle_digest is None
    with pytest.raises(ValidationError):
        MANIFEST_ADAPTER.validate_python(_revision(revision=1))
    with pytest.raises(ValidationError):
        MANIFEST_ADAPTER.validate_python(_revision(revision=3, parent_bundle_digest=None))


def test_revision_requires_every_promotion_field() -> None:
    for field in ("revision", "created_at", "created_by", "change_id",
                  "approved_candidate_digest", "approval_stamp_id", "bundle_digest"):
        payload = _revision()
        del payload[field]
        with pytest.raises(ValidationError):
            MANIFEST_ADAPTER.validate_python(payload)


def test_every_catalog_carries_its_own_version() -> None:
    """Catalogs move independently: adding a skill category must not imply a predicate change."""
    for field in CATALOG_VERSIONS:
        payload = _revision()
        del payload[field]
        with pytest.raises(ValidationError):
            MANIFEST_ADAPTER.validate_python(payload)
        with pytest.raises(ValidationError):
            MANIFEST_ADAPTER.validate_python(_revision(**{field: 0}))


def test_created_by_is_a_closed_actor_catalog() -> None:
    assert {member.value for member in Actor} == {"owner", "agent", "importer"}
    with pytest.raises(ValidationError):
        MANIFEST_ADAPTER.validate_python(_revision(created_by="ci"))


def test_manifest_state_must_be_one_of_the_two_declared_states() -> None:
    with pytest.raises(ValidationError):
        MANIFEST_ADAPTER.validate_python(_draft(state="candidate"))


def test_stable_envelope_is_the_only_ancestor_surface() -> None:
    """§7 traverses ancestors through a stable envelope without reparsing their domain models."""
    envelope = MANIFEST_ADAPTER.validate_python(_revision()).envelope  # type: ignore[union-attr]
    assert isinstance(envelope, StableManifestEnvelope)
    assert envelope.bundle_digest == DIGEST_C
    assert envelope.parent_bundle_digest == DIGEST_A
    assert not hasattr(envelope, "created_at")


def test_unknown_manifest_field_is_refused() -> None:
    with pytest.raises(ValidationError):
        MANIFEST_ADAPTER.validate_python(_revision(persona_version=1))


# --------------------------------------------------------------------------------------
# conflicts and rulings
# --------------------------------------------------------------------------------------


def _conflict(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "conflict_id": "conflict.packet-pantry.launch-date",
        "subject_id": "project.packet-pantry",
        "predicate": "project.start_date",
        "state": "unresolved",
        "candidate_fact_ids": [
            "fact.packet-pantry.start-date.001",
            "fact.packet-pantry.start-date.002",
        ],
        "active_ruling_id": None,
        "opened_at": "2026-08-10",
    }
    payload.update(overrides)
    return payload


def _ruling(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "ruling_id": "ruling.packet-pantry.launch-date.001",
        "conflict_id": "conflict.packet-pantry.launch-date",
        "decision": "select_candidate",
        "selected_fact_id": "fact.packet-pantry.start-date.002",
        "rejected_fact_ids": ["fact.packet-pantry.start-date.001"],
        "rationale": "The later date is the start of implementation.",
        "owner_evidence_id": "evidence.packet-pantry.owner-ruling.001",
        "decided_at": "2026-08-10",
    }
    payload.update(overrides)
    return payload


def test_conflict_states_are_the_closed_three_including_reopened() -> None:
    assert {member.value for member in ConflictState} == {"unresolved", "resolved", "reopened"}


def test_a_conflict_needs_at_least_two_candidates() -> None:
    with pytest.raises(ValidationError):
        ConflictRecord.model_validate(
            _conflict(candidate_fact_ids=["fact.packet-pantry.start-date.001"])
        )


def test_a_resolved_conflict_must_name_its_active_ruling() -> None:
    with pytest.raises(ValidationError):
        ConflictRecord.model_validate(_conflict(state="resolved"))
    resolved = ConflictRecord.model_validate(
        _conflict(state="resolved", active_ruling_id="ruling.packet-pantry.launch-date.001")
    )
    assert resolved.active_ruling_id == "ruling.packet-pantry.launch-date.001"


def test_a_reopened_conflict_may_still_name_its_previous_ruling() -> None:
    reopened = ConflictRecord.model_validate(
        _conflict(state="reopened", active_ruling_id="ruling.packet-pantry.launch-date.001")
    )
    assert reopened.state is ConflictState.REOPENED


def test_ruling_decisions_are_the_closed_four() -> None:
    assert {member.value for member in RulingDecision} == {
        "select_candidate",
        "replace_all",
        "keep_unresolved",
        "not_applicable",
    }


def test_select_candidate_must_name_a_fact_and_others_must_not() -> None:
    with pytest.raises(ValidationError):
        RulingRecord.model_validate(_ruling(selected_fact_id=None))
    with pytest.raises(ValidationError):
        RulingRecord.model_validate(_ruling(decision="keep_unresolved"))
    kept = RulingRecord.model_validate(
        _ruling(decision="keep_unresolved", selected_fact_id=None, rejected_fact_ids=[])
    )
    assert kept.decision is RulingDecision.KEEP_UNRESOLVED


def test_a_fact_cannot_be_both_selected_and_rejected() -> None:
    with pytest.raises(ValidationError):
        RulingRecord.model_validate(
            _ruling(rejected_fact_ids=["fact.packet-pantry.start-date.002"])
        )


def test_a_ruling_requires_a_rationale_and_owner_evidence() -> None:
    with pytest.raises(ValidationError):
        RulingRecord.model_validate(_ruling(rationale="  "))
    with pytest.raises(ValidationError):
        RulingRecord.model_validate(_ruling(owner_evidence_id="fact.a.001"))


def test_conflict_documents_hold_their_records() -> None:
    groups = ConflictGroups.model_validate({"conflicts": [_conflict()]})
    rulings = ConflictRulings.model_validate({"rulings": [_ruling()]})
    assert len(groups.conflicts) == 1
    assert len(rulings.rulings) == 1


def test_a_repeated_ruling_entry_is_refused() -> None:
    """The ledger is append-only; the same ruling twice would break the parent-prefix comparison."""
    with pytest.raises(ValidationError):
        ConflictRulings.model_validate({"rulings": [_ruling(), _ruling()]})


# --------------------------------------------------------------------------------------
# approvals
# --------------------------------------------------------------------------------------


def test_the_sub_approval_action_catalog_is_the_closed_eight() -> None:
    assert {member.value for member in ApprovalAction} == {
        "confirm_fact",
        "confirm_contact",
        "approve_evidence_sufficiency",
        "approve_claim",
        "approve_metric_surfaces",
        "approve_source_scope",
        "approve_source_record_exclusion",
        "authorize_conflict_ruling",
    }


def test_every_action_declares_a_target_kind_and_a_resulting_state() -> None:
    assert set(APPROVAL_TARGET_PREFIX) == set(ApprovalAction)
    assert set(APPROVAL_RESULTING_STATE) == set(ApprovalAction)


@pytest.mark.parametrize("action", sorted(ApprovalAction, key=str))
def test_each_action_accepts_only_its_own_target_kind(action: ApprovalAction) -> None:
    prefix = APPROVAL_TARGET_PREFIX[action]
    good = ApprovalEntry.model_validate(
        {
            "approval_id": "approval.example.001",
            "action": action.value,
            "target_record_id": f"{prefix}.example",
            "target_content_digest": DIGEST_A,
            "resulting_state": APPROVAL_RESULTING_STATE[action],
        }
    )
    assert good.action is action
    wrong_prefix = "skill" if prefix != "skill" else "fact"
    with pytest.raises(ValidationError):
        ApprovalEntry.model_validate(
            {
                "approval_id": "approval.example.001",
                "action": action.value,
                "target_record_id": f"{wrong_prefix}.example",
                "target_content_digest": DIGEST_A,
                "resulting_state": APPROVAL_RESULTING_STATE[action],
            }
        )


@pytest.mark.parametrize("action", sorted(ApprovalAction, key=str))
def test_each_action_establishes_only_its_own_resulting_state(action: ApprovalAction) -> None:
    with pytest.raises(ValidationError):
        ApprovalEntry.model_validate(
            {
                "approval_id": "approval.example.001",
                "action": action.value,
                "target_record_id": f"{APPROVAL_TARGET_PREFIX[action]}.example",
                "target_content_digest": DIGEST_A,
                "resulting_state": "rejected",
            }
        )


def _stamp(entries: list[dict[str, object]]) -> dict[str, object]:
    return {
        "approval_stamp_id": "approval-stamp.000002",
        "candidate_content_digest": DIGEST_B,
        "approved_at": "2026-08-10T12:00:00Z",
        "approved_via": "controlling_terminal",
        "entries": entries,
    }


def _entry(action: ApprovalAction, target: str, approval_id: str) -> dict[str, object]:
    return {
        "approval_id": approval_id,
        "action": action.value,
        "target_record_id": target,
        "target_content_digest": DIGEST_A,
        "resulting_state": APPROVAL_RESULTING_STATE[action],
    }


def test_a_stamp_may_carry_zero_one_or_many_entries() -> None:
    assert ApprovalStamp.model_validate(_stamp([])).entries == ()
    one = ApprovalStamp.model_validate(
        _stamp([_entry(ApprovalAction.APPROVE_CLAIM, "claim.a.001", "approval.claim.a.001")])
    )
    assert len(one.entries) == 1
    many = ApprovalStamp.model_validate(
        _stamp(
            [
                _entry(ApprovalAction.APPROVE_CLAIM, "claim.a.001", "approval.claim.a.001"),
                _entry(ApprovalAction.CONFIRM_FACT, "fact.a.001", "approval.fact.a.001"),
                _entry(
                    ApprovalAction.APPROVE_EVIDENCE_SUFFICIENCY,
                    "evidence.a.001",
                    "approval.evidence.a.001",
                ),
            ]
        )
    )
    assert len(many.entries) == 3


def test_duplicate_approval_ids_in_one_stamp_are_refused() -> None:
    duplicate = _entry(ApprovalAction.APPROVE_CLAIM, "claim.a.001", "approval.same")
    with pytest.raises(ValidationError):
        ApprovalStamp.model_validate(_stamp([duplicate, dict(duplicate)]))


def test_approved_via_is_a_closed_catalog_not_free_text() -> None:
    assert {member.value for member in ApprovedVia} == {"controlling_terminal"}
    with pytest.raises(ValidationError):
        ApprovalStamp.model_validate({**_stamp([]), "approved_via": "environment_variable"})


def test_entries_for_finds_a_specific_owner_decision() -> None:
    stamp = ApprovalStamp.model_validate(
        _stamp([_entry(ApprovalAction.CONFIRM_CONTACT, "contact.a.email", "approval.contact.a")])
    )
    assert stamp.entries_for(ApprovalAction.CONFIRM_CONTACT, "contact.a.email")
    assert not stamp.entries_for(ApprovalAction.CONFIRM_FACT, "contact.a.email")


def test_approval_ledger_refuses_a_duplicate_stamp_id() -> None:
    stamp = _stamp([])
    with pytest.raises(ValidationError):
        ApprovalLedger.model_validate({"approvals": [stamp, {**stamp}]})


# --------------------------------------------------------------------------------------
# change ledger
# --------------------------------------------------------------------------------------


def _change(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "change_id": "change.000001",
        "revision": 1,
        "parent_bundle_digest": None,
        "actor": "owner",
        "authorized_by": "owner",
        "summary": "Freeze the synthetic baseline",
        "changed_record_ids": ["fact.packet-pantry.language.001"],
        "created_at": "2026-08-10T12:00:00Z",
    }
    payload.update(overrides)
    return payload


def test_a_change_record_parses_and_omits_the_resulting_bundle_digest() -> None:
    """The digest lives only in the manifest; here it would hash a document containing itself."""
    record = ChangeRecord.model_validate(_change())
    assert record.actor is Actor.OWNER
    assert "bundle_digest" not in ChangeRecord.model_fields


def test_change_revision_one_is_parentless_and_later_revisions_are_not() -> None:
    with pytest.raises(ValidationError):
        ChangeRecord.model_validate(_change(parent_bundle_digest=DIGEST_A))
    with pytest.raises(ValidationError):
        ChangeRecord.model_validate(_change(revision=2, parent_bundle_digest=None))
    assert ChangeRecord.model_validate(
        _change(change_id="change.000002", revision=2, parent_bundle_digest=DIGEST_A)
    ).revision == 2


def test_change_ledger_revisions_must_be_contiguous_from_one() -> None:
    first = _change()
    third = _change(change_id="change.000003", revision=3, parent_bundle_digest=DIGEST_A)
    with pytest.raises(ValidationError):
        ChangeLedger.model_validate({"changes": [first, third]})
    second = _change(change_id="change.000002", revision=2, parent_bundle_digest=DIGEST_A)
    ledger = ChangeLedger.model_validate({"changes": [first, second]})
    assert len(ledger.changes) == 2


def test_change_ledger_refuses_a_duplicate_change_id() -> None:
    with pytest.raises(ValidationError):
        ChangeLedger.model_validate({"changes": [_change(), _change()]})


def test_an_empty_change_ledger_is_legal_for_a_revision_one_draft() -> None:
    assert ChangeLedger.model_validate({"changes": []}).changes == ()


def test_a_change_requires_a_summary() -> None:
    with pytest.raises(ValidationError):
        ChangeRecord.model_validate(_change(summary=""))
