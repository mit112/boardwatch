"""Authoring one evidence record and one owner ruling into a draft (design §12, §13, §19).

These are the only two Gate A operations that add owner content to a draft, and both are
append-only against documents promotion later checks as prefixes. Three properties are load-bearing
and each has a test that fails without it:

- **A refusal writes nothing.** A secret hit, a duplicate ID, or bytes that do not match the record
  must leave the draft byte-identical, because the operator's next act is to fix the input and
  re-run — and a half-applied first attempt would make the second one refuse for a different reason.
- **The blob store is content-addressed and shared.** Capturing the same bytes twice reuses one
  blob; capturing bytes that do not hash to the record's declared digest is refused before anything
  is stored.
- **Owner gates are derived, not asserted.** What the change made owner-gated comes from
  `required_approval_decisions` against the draft as it was, so the command reports the same
  transitions `validate_history` will later demand a stamp for.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import PurePosixPath

from boardwatch.profile_bundle.authoring import add_evidence, resolve_conflict
from boardwatch.profile_bundle.errors import OperationOutcome
from boardwatch.profile_bundle.models.history import ApprovalAction
from boardwatch.profile_bundle.paths import blob_path, blobs_dir, draft_root
from tests.profile_bundle.conftest import SyntheticBundle, parse_documents, quoted_yaml

EVIDENCE_INPUT = PurePosixPath("evidence-record.yaml")
RULING_INPUT = PurePosixPath("ruling-record.yaml")

#: The unresolved group the packaged example ships, and the one a ruling can settle.
OPEN_CONFLICT = "conflict.packet-pantry.end-date"


def _inline_record(text: str, *, evidence_id: str = "evidence.example.new.001") -> bytes:
    return quoted_yaml(
        {
            "evidence_id": evidence_id,
            "title": "Owner attestation added by the authoring command",
            "capture": {"kind": "inline", "text": text, "media_type": "text/plain"},
            "captured_at": "2026-08-11T09:00:00Z",
            "reviewed_at": "2026-08-11",
            "sufficiency_review": {"state": "owner_approved"},
            "redactions": [],
            "supports_record_ids": ["fact.example.name.001"],
            "contradicts_record_ids": [],
            "contextualizes_record_ids": [],
            "evidence_class": "owner_attestation",
            "attested_at": "2026-08-11",
        },
        logical_path=EVIDENCE_INPUT,
    )


def _blob_record(raw: bytes, *, evidence_id: str = "evidence.example.blob.001") -> bytes:
    return quoted_yaml(
        {
            "evidence_id": evidence_id,
            "title": "Captured note stored as a blob",
            "capture": {
                "kind": "blob",
                "sha256": hashlib.sha256(raw).hexdigest(),
                "media_type": "text/markdown",
            },
            "captured_at": "2026-08-11T09:00:00Z",
            "reviewed_at": "2026-08-11",
            "sufficiency_review": {"state": "owner_approved"},
            "redactions": [],
            "supports_record_ids": ["fact.example.name.001"],
            "contradicts_record_ids": [],
            "contextualizes_record_ids": [],
            "evidence_class": "owner_attestation",
            "attested_at": "2026-08-11",
        },
        logical_path=EVIDENCE_INPUT,
    )


def _ruling(
    *,
    ruling_id: str = "ruling.packet-pantry.end-date.001",
    conflict_id: str = OPEN_CONFLICT,
    decision: str = "select_candidate",
    selected: str | None = "fact.packet-pantry.end-date.002",
) -> bytes:
    return quoted_yaml(
        {
            "ruling_id": ruling_id,
            "conflict_id": conflict_id,
            "decision": decision,
            "selected_fact_id": selected,
            "rejected_fact_ids": (
                ["fact.packet-pantry.end-date.001"] if selected is not None else []
            ),
            "rationale": "The later date is when the work actually stopped.",
            "owner_evidence_id": "evidence.packet-pantry.owner-ruling.001",
            "decided_at": "2026-08-11",
        },
        logical_path=RULING_INPUT,
    )


def _codes(outcome: OperationOutcome[object]) -> set[str]:
    return {finding.code for finding in outcome.diagnostics}


def _tree(bundle: SyntheticBundle) -> dict[str, bytes]:
    return {
        str(path.relative_to(bundle.root)): path.read_bytes()
        for path in sorted(bundle.root.rglob("*"))
        if path.is_file()
    }


# --------------------------------------------------------------------------------------
# add_evidence
# --------------------------------------------------------------------------------------


def test_an_inline_capture_is_appended_and_stores_no_blob(synthetic_bundle: SyntheticBundle) -> None:
    text = "The owner attests to the professional name recorded in this bundle."
    before = sorted(blobs_dir(synthetic_bundle.root).iterdir())
    outcome = add_evidence(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        evidence_document=_inline_record(text),
        capture=text.encode("utf-8"),
    )
    assert outcome.category == "clean", outcome.diagnostics
    assert outcome.value is not None
    assert outcome.value.evidence_id == "evidence.example.new.001"
    assert outcome.value.blob_digest is None
    assert sorted(blobs_dir(synthetic_bundle.root).iterdir()) == before
    assert "evidence.example.new.001" in synthetic_bundle.read("evidence/records.yaml")


def test_an_inline_capture_must_be_the_bytes_the_record_quotes(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Otherwise the record states one excerpt and the scan examined another."""
    before = _tree(synthetic_bundle)
    outcome = add_evidence(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        evidence_document=_inline_record("What the record says."),
        capture=b"What the capture file actually holds.",
    )
    assert outcome.exit_code == 1
    assert _codes(outcome) == {"evidence_contract_unmet"}
    assert _tree(synthetic_bundle) == before


def test_a_blob_capture_is_written_once_and_then_reused(
    synthetic_bundle: SyntheticBundle,
) -> None:
    raw = b"# Captured note\n\nA second synthetic capture, stored by digest.\n"
    first = add_evidence(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        evidence_document=_blob_record(raw),
        capture=raw,
    )
    assert first.category == "clean", first.diagnostics
    assert first.value is not None
    assert first.value.blob_outcome == "written"
    assert blob_path(synthetic_bundle.root, hashlib.sha256(raw).hexdigest()).read_bytes() == raw

    second = add_evidence(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        evidence_document=_blob_record(raw, evidence_id="evidence.example.blob.002"),
        capture=raw,
    )
    assert second.category == "clean", second.diagnostics
    assert second.value is not None
    assert second.value.blob_outcome == "reused"


def test_a_blob_capture_whose_bytes_do_not_match_the_declared_digest_is_refused(
    synthetic_bundle: SyntheticBundle,
) -> None:
    before = _tree(synthetic_bundle)
    outcome = add_evidence(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        evidence_document=_blob_record(b"the bytes the record describes"),
        capture=b"different bytes entirely",
    )
    assert outcome.exit_code == 1
    assert _codes(outcome) == {"blob_digest_mismatch"}
    assert _tree(synthetic_bundle) == before


def test_a_secret_in_the_capture_refuses_and_writes_nothing(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§21: a secret hit is a hard failure, and the draft must not be half-updated.

    The capture carries a synthetic AWS-shaped key. The diagnostic names the rule and the byte
    range and never the matched text (`Diagnostic` forbids it).
    """
    secret = "AKIA" + "A" * 16
    text = f"Deployment note that accidentally includes {secret} in the log line."
    before = _tree(synthetic_bundle)
    outcome = add_evidence(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        evidence_document=_inline_record(text),
        capture=text.encode("utf-8"),
    )
    assert outcome.exit_code == 1
    assert _codes(outcome) == {"secret_detected"}
    assert _tree(synthetic_bundle) == before
    assert all(secret not in finding.message for finding in outcome.diagnostics)
    assert all(secret not in str(finding.details) for finding in outcome.diagnostics)


def test_a_capture_over_the_per_capture_limit_is_refused(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """One byte over 1 MiB — the §12.2 cap, written here rather than read from the module."""
    raw = b"a" * (1024 * 1024 + 1)
    before = _tree(synthetic_bundle)
    outcome = add_evidence(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        evidence_document=_blob_record(raw),
        capture=raw,
    )
    assert outcome.exit_code == 1
    assert _codes(outcome) == {"capture_too_large"}
    assert _tree(synthetic_bundle) == before


def test_an_evidence_id_the_draft_already_holds_is_refused(
    synthetic_bundle: SyntheticBundle,
) -> None:
    text = "A second record claiming an identifier the draft already uses."
    before = _tree(synthetic_bundle)
    outcome = add_evidence(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        evidence_document=_inline_record(
            text, evidence_id="evidence.packet-pantry.benchmark.001"
        ),
        capture=text.encode("utf-8"),
    )
    assert outcome.exit_code == 1
    assert _codes(outcome) == {"duplicate_record_id"}
    assert _tree(synthetic_bundle) == before


def test_an_absent_draft_is_a_state_refusal(synthetic_bundle: SyntheticBundle) -> None:
    text = "Nothing to add this to."
    outcome = add_evidence(
        synthetic_bundle.root,
        draft_name="no-such-draft",
        evidence_document=_inline_record(text),
        capture=text.encode("utf-8"),
    )
    assert outcome.exit_code == 1
    assert _codes(outcome) == {"draft_not_found"}


def test_an_unparseable_evidence_document_is_refused(
    synthetic_bundle: SyntheticBundle,
) -> None:
    before = _tree(synthetic_bundle)
    outcome = add_evidence(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        evidence_document=b"evidence_id: 'evidence.x.001'\ntitle: 'missing everything else'\n",
        capture=b"anything",
    )
    assert outcome.exit_code == 1
    assert _codes(outcome) == {"model_validation_error"}
    assert _tree(synthetic_bundle) == before


def test_adding_owner_approved_evidence_reports_the_gate_it_creates(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The new record's `owner_approved` sufficiency is an owner-gated transition (§13).

    Derived by diffing the draft against itself-before, so it is the same derivation
    `validate_history` uses rather than a second statement of which transitions are gated.
    """
    text = "An attested note whose sufficiency the owner has approved."
    outcome = add_evidence(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        evidence_document=_inline_record(text),
        capture=text.encode("utf-8"),
    )
    assert outcome.value is not None
    assert [
        (decision.action, decision.target_record_id) for decision in outcome.value.owner_gates
    ] == [(ApprovalAction.APPROVE_EVIDENCE_SUFFICIENCY, "evidence.example.new.001")]


# --------------------------------------------------------------------------------------
# resolve_conflict
# --------------------------------------------------------------------------------------


def test_a_ruling_is_appended_and_settles_only_its_own_group(
    synthetic_bundle: SyntheticBundle,
) -> None:
    before_rulings = synthetic_bundle.read("conflicts/rulings.yaml")
    outcome = resolve_conflict(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        ruling_document=_ruling(),
    )
    assert outcome.category == "clean", outcome.diagnostics
    assert outcome.value is not None
    assert outcome.value.conflict_state == "resolved"

    rulings = synthetic_bundle.read("conflicts/rulings.yaml")
    assert "ruling.packet-pantry.end-date.001" in rulings
    assert "ruling.packet-pantry.start-date.001" in before_rulings
    assert "ruling.packet-pantry.start-date.001" in rulings

    # Re-read through the loader rather than by string, because the rewritten document is emitted
    # in `document_bytes`' quoting style and a substring assertion would be about the writer.
    reread = parse_documents(synthetic_bundle.draft)
    settled = {
        group.conflict_id: (group.state, group.active_ruling_id)
        for group in reread.by_path[PurePosixPath("conflicts/groups.yaml")].conflicts  # type: ignore[union-attr]
    }
    assert settled[OPEN_CONFLICT] == ("resolved", "ruling.packet-pantry.end-date.001")
    # The other group is untouched.
    assert settled["conflict.packet-pantry.start-date"] == (
        "resolved",
        "ruling.packet-pantry.start-date.001",
    )


def test_a_ruling_reports_the_authorization_it_requires(
    synthetic_bundle: SyntheticBundle,
) -> None:
    outcome = resolve_conflict(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        ruling_document=_ruling(),
    )
    assert outcome.value is not None
    actions = {decision.action for decision in outcome.value.owner_gates}
    assert ApprovalAction.AUTHORIZE_CONFLICT_RULING in actions
    assert "ruling.packet-pantry.end-date.001" in {
        decision.target_record_id for decision in outcome.value.owner_gates
    }


def test_keep_unresolved_leaves_the_group_unresolved(
    synthetic_bundle: SyntheticBundle,
) -> None:
    outcome = resolve_conflict(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        ruling_document=_ruling(decision="keep_unresolved", selected=None),
    )
    assert outcome.category == "clean", outcome.diagnostics
    assert outcome.value is not None
    assert outcome.value.conflict_state == "unresolved"


def test_a_ruling_on_an_unknown_conflict_is_refused(
    synthetic_bundle: SyntheticBundle,
) -> None:
    before = _tree(synthetic_bundle)
    outcome = resolve_conflict(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        ruling_document=_ruling(conflict_id="conflict.nothing.here"),
    )
    assert outcome.exit_code == 1
    assert _codes(outcome) == {"broken_reference"}
    assert _tree(synthetic_bundle) == before


def test_a_ruling_id_the_draft_already_holds_is_refused(
    synthetic_bundle: SyntheticBundle,
) -> None:
    before = _tree(synthetic_bundle)
    outcome = resolve_conflict(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        ruling_document=_ruling(ruling_id="ruling.packet-pantry.start-date.001"),
    )
    assert outcome.exit_code == 1
    assert _codes(outcome) == {"duplicate_record_id"}
    assert _tree(synthetic_bundle) == before


def test_neither_command_touches_a_draft_it_was_not_named(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """`--draft` names the one tree that may change; a second draft must come out byte-identical."""
    other = draft_root(synthetic_bundle.root, "second")
    other.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(synthetic_bundle.draft, other)
    snapshot = {
        str(path.relative_to(other)): path.read_bytes()
        for path in sorted(other.rglob("*"))
        if path.is_file()
    }
    text = "A note added to exactly one draft."
    assert (
        add_evidence(
            synthetic_bundle.root,
            draft_name=synthetic_bundle.draft_name,
            evidence_document=_inline_record(text),
            capture=text.encode("utf-8"),
        ).category
        == "clean"
    )
    assert (
        resolve_conflict(
            synthetic_bundle.root,
            draft_name=synthetic_bundle.draft_name,
            ruling_document=_ruling(),
        ).category
        == "clean"
    )
    assert {
        str(path.relative_to(other)): path.read_bytes()
        for path in sorted(other.rglob("*"))
        if path.is_file()
    } == snapshot
