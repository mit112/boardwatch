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
import os
import shutil
from pathlib import Path, PurePosixPath

import pytest

from boardwatch.profile_bundle.authoring import _STATE_AFTER, add_evidence, resolve_conflict
from boardwatch.profile_bundle.errors import (
    COULD_NOT_COMPLETE_CODES,
    IssueCode,
    OperationOutcome,
)
from boardwatch.profile_bundle.index import record_id_of
from boardwatch.profile_bundle.models.base import prefix_of
from boardwatch.profile_bundle.models.documents import (
    FactBearingDocument,
    MetricRecordsDocument,
)
from boardwatch.profile_bundle.models.history import ApprovalAction, RulingDecision
from boardwatch.profile_bundle.paths import blob_path, blobs_dir, draft_root
from boardwatch.profile_bundle.validation import (
    build_context,
    validate_digest,
    validate_referential,
)
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
    """Every file under the bundle, keyed by its **posix** relative path.

    `as_posix()` rather than `str()`: the keys are compared against written-out document paths, and
    `str()` yields `drafts\\baseline\\manifest.yaml` on Windows. Callers that only diff one tree
    against another never noticed; the one that names a path did, on CI.
    """
    return {
        path.relative_to(bundle.root).as_posix(): path.read_bytes()
        for path in sorted(bundle.root.rglob("*"))
        if path.is_file()
    }


# --------------------------------------------------------------------------------------
# add_evidence
# --------------------------------------------------------------------------------------


def test_an_inline_capture_is_appended_and_stores_no_blob(
    synthetic_bundle: SyntheticBundle,
) -> None:
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
        evidence_document=_inline_record(text, evidence_id="evidence.packet-pantry.benchmark.001"),
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


def test_an_absent_bundle_is_named_rather_than_reported_as_an_absent_draft(
    tmp_path: Path,
) -> None:
    """The distinction the test above does not make. These commands answer before they reach any
    function that confines the root, so `draft_not_found` was their answer for a bundle that does
    not exist — and its remedy, "check out a draft", sends the owner to `checkout` for a bundle
    they never created (D-138)."""
    absent = tmp_path / "no-such-bundle"
    text = "Nothing to add this to."

    addition = add_evidence(
        absent,
        draft_name="initial",
        evidence_document=_inline_record(text),
        capture=text.encode("utf-8"),
    )
    ruling = resolve_conflict(absent, draft_name="initial", ruling_document=b"rulings: []\n")

    assert addition.exit_code == 1
    assert _codes(addition) == {"bundle_not_found"}
    assert ruling.exit_code == 1
    assert _codes(ruling) == {"bundle_not_found"}
    assert not absent.exists()


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

    **Both** gates are reported, and the second one is the point: the back-citation this capture
    writes into `fact.example.name.001` (D-143) changes that fact, and a changed fact owes
    `confirm_fact` at promotion. It is not a burden auto-linking invented — the hand edit that used
    to be step two changed the same field of the same fact and owed the same stamp. What changed is
    that the owner is told at the moment they incur it rather than at promotion, which is exactly
    what `_gates` exists for: the command cannot report a gate promotion will not require, or miss
    one it will.
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
    ] == [
        (ApprovalAction.APPROVE_EVIDENCE_SUFFICIENCY, "evidence.example.new.001"),
        (ApprovalAction.CONFIRM_FACT, "fact.example.name.001"),
    ]


# --------------------------------------------------------------------------------------
# add_evidence writes the back-citation (D-143)
# --------------------------------------------------------------------------------------
#
# §12 requires the two link directions to agree exactly. `add_evidence` used to write only the
# evidence side, so a capture supporting a fact left the draft failing `evidence_link_asymmetry`
# until the owner hand-edited the fact. These tests pin the three things a narrower fix would miss:
# all three relationships, both citing kinds, and any of the twelve fact-bearing documents.


def _linking_record(
    text: str,
    *,
    supports: list[str] | None = None,
    contradicts: list[str] | None = None,
    contextualizes: list[str] | None = None,
    evidence_id: str = "evidence.example.link.001",
    evidence_class: str = "owner_attestation",
) -> bytes:
    """An inline record whose three link tuples the caller chooses.

    The class matters and is not decoration: each one carries its own model validator about what it
    must link to — an `owner_attestation` must support at least one fact, a `measured_result` at
    least one metric — so a test about *which* links get cited back has to pick a class whose own
    rules its links already satisfy.
    """
    extra: dict[str, object] = {
        "owner_attestation": {"attested_at": "2026-08-11"},
        "measured_result": {},
        "secondary_summary": {
            "source_id": "source.synthetic-notes",
            "locator": {"kind": "section", "value": "Prototype stack"},
            "authoritative": False,
        },
    }[evidence_class]
    return quoted_yaml(
        {
            "evidence_id": evidence_id,
            "title": "Attestation whose links are under test",
            "capture": {"kind": "inline", "text": text, "media_type": "text/plain"},
            "captured_at": "2026-08-11T09:00:00Z",
            "reviewed_at": "2026-08-11",
            "sufficiency_review": {"state": "owner_approved"},
            "redactions": [],
            "supports_record_ids": supports or [],
            "contradicts_record_ids": contradicts or [],
            "contextualizes_record_ids": contextualizes or [],
            "evidence_class": evidence_class,
            **extra,
        },
        logical_path=EVIDENCE_INPUT,
    )


def _asymmetries(bundle: SyntheticBundle) -> list[str]:
    """Every `evidence_link_asymmetry` the real referential check reports over the draft.

    Through `validate_referential` rather than by re-reading the YAML, because the property that
    matters is that the check this closes no longer fires — not that a field the test chose changed.
    """
    ctx = build_context(draft_root(bundle.root, bundle.draft_name), mode="draft")
    return [
        finding.details.get("supported_record_id") or finding.details.get("record_id", "")
        for finding in validate_referential(ctx)
        if finding.code == IssueCode.EVIDENCE_LINK_ASYMMETRY.value
    ]


def _cited_by(bundle: SyntheticBundle, relative: str, record_id: str) -> tuple[str, ...]:
    """One record's `evidence_ids`, read back through the production loader."""
    documents = parse_documents(draft_root(bundle.root, bundle.draft_name))
    document = documents.by_path[PurePosixPath(relative)]
    holder = getattr(document, "facts", None) or getattr(document, "metrics", ())
    (record,) = [item for item in holder if record_id_of(item) == record_id]
    return tuple(record.evidence_ids)


def test_a_capture_supporting_a_fact_writes_the_back_citation(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The whole point of D-143: a correct operation leaves no standing error behind it."""
    text = "The owner attests to the professional name recorded in this bundle."
    assert _asymmetries(synthetic_bundle) == []

    outcome = add_evidence(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        evidence_document=_linking_record(text, supports=["fact.example.name.001"]),
        capture=text.encode("utf-8"),
    )

    assert outcome.category == "clean", outcome.diagnostics
    assert "evidence.example.link.001" in _cited_by(
        synthetic_bundle, "facts/identity.yaml", "fact.example.name.001"
    )
    assert _asymmetries(synthetic_bundle) == []
    # The rewritten documents are named. The operator asked to add one evidence record; a capture
    # that silently edits records elsewhere is an edit nobody can review, and `owner_gates` does not
    # cover them — a fact that is not `owner_confirmed` is rewritten without incurring a gate.
    assert outcome.value is not None
    assert outcome.value.cited_back == ("facts/identity.yaml",)


def test_a_blob_capture_writes_the_back_citation_too(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The other capture kind, because an unreached arm is not a passed arm.

    `_documents_citing_back` reads only the record's link tuples and never touches `record.capture`,
    so the two kinds should not differ — but the review that checked this change reached every other
    arm with inline captures alone and said so. This runs the one it could not.
    """
    raw = b"# Attested note\n\nStored by digest, and it supports a fact.\n"
    outcome = add_evidence(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        evidence_document=_blob_record(raw),
        capture=raw,
    )

    assert outcome.category == "clean", outcome.diagnostics
    assert outcome.value is not None
    assert outcome.value.blob_outcome == "written"
    assert "evidence.example.blob.001" in _cited_by(
        synthetic_bundle, "facts/identity.yaml", "fact.example.name.001"
    )
    assert outcome.value.cited_back == ("facts/identity.yaml",)
    assert _asymmetries(synthetic_bundle) == []


def test_a_capture_supporting_a_metric_writes_the_back_citation(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Metrics carry `evidence_ids` too, and the guide's example only ever showed a fact."""
    text = "The owner attests to the throughput figure recorded in this bundle."
    outcome = add_evidence(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        evidence_document=_linking_record(
            text,
            supports=["metric.packet-pantry.throughput.001"],
            evidence_class="measured_result",
        ),
        capture=text.encode("utf-8"),
    )

    assert outcome.category == "clean", outcome.diagnostics
    assert "evidence.example.link.001" in _cited_by(
        synthetic_bundle, "metrics/records.yaml", "metric.packet-pantry.throughput.001"
    )
    assert _asymmetries(synthetic_bundle) == []


def test_contradicting_and_contextualizing_records_are_cited_back_too(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """`_evidence_links_are_symmetric` reads the UNION of three relationships, not `supports`.

    A fix that linked only `supports` passes the two tests above and leaves the other two arms
    reporting the very asymmetry it was written to close. One record carries all three, which also
    keeps it a legal `owner_attestation` — that class must support at least one fact.
    """
    text = "The owner attests to a reading that cuts against one fact and colours another."
    outcome = add_evidence(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        evidence_document=_linking_record(
            text,
            supports=["fact.example.name.001"],
            contradicts=["fact.example-prize.name.001"],
            contextualizes=["fact.example-paper.title.001"],
        ),
        capture=text.encode("utf-8"),
    )

    assert outcome.category == "clean", outcome.diagnostics
    assert "evidence.example.link.001" in _cited_by(
        synthetic_bundle, "facts/identity.yaml", "fact.example.name.001"
    )
    assert "evidence.example.link.001" in _cited_by(
        synthetic_bundle, "facts/awards.yaml", "fact.example-prize.name.001"
    )
    assert "evidence.example.link.001" in _cited_by(
        synthetic_bundle, "facts/publications.yaml", "fact.example-paper.title.001"
    )
    assert _asymmetries(synthetic_bundle) == []


def test_a_fact_outside_the_identity_document_is_found(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Twelve document classes bear facts, and one lives in a nested directory.

    The lookup asks `isinstance(document, FactBearingDocument)` rather than naming paths, so this
    guards the failure mode that shipped once already (D-142): a fix that reaches the arms the probe
    happened to touch and claims the whole surface.
    """
    text = "The owner attests to the employer named in this bundle."
    outcome = add_evidence(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        evidence_document=_linking_record(text, supports=["fact.example-labs.organization.001"]),
        capture=text.encode("utf-8"),
    )

    assert outcome.category == "clean", outcome.diagnostics
    assert "evidence.example.link.001" in _cited_by(
        synthetic_bundle,
        "facts/experience/employment.example-labs.yaml",
        "fact.example-labs.organization.001",
    )
    assert _asymmetries(synthetic_bundle) == []


def test_every_record_bearing_document_class_is_reached(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The catalog is derived from the code, not from the documents these tests happen to touch.

    `_documents_citing_back` asks `isinstance(document, FactBearingDocument)` so that the twelve
    fact-bearing classes do not become a list that goes stale. Nothing pinned that: replacing the
    isinstance with a hard-coded tuple of the four classes the other tests exercise passes all 98
    tests that touch `add_evidence` while reaching 5 of 13 documents. That is the shape of D-142 —
    a fix that reaches the arms the probe happened to touch and claims the whole surface — so the
    expected set here is read off `FactBearingDocument.__subclasses__()` at run time.

    The first assertion is the load-bearing one: if the packaged example stopped instantiating one
    of the classes, the loop below would quietly cover fewer arms and still pass.
    """
    draft = draft_root(synthetic_bundle.root, synthetic_bundle.draft_name)
    catalog = {*FactBearingDocument.__subclasses__(), MetricRecordsDocument}

    targets: dict[PurePosixPath, tuple[type[object], str]] = {}
    for path, document in parse_documents(draft).items():
        if isinstance(document, FactBearingDocument):
            holder: tuple[object, ...] = document.facts
        elif isinstance(document, MetricRecordsDocument):
            holder = document.metrics
        else:
            continue
        if holder:
            targets[path] = (type(document), record_id_of(holder[0]))  # type: ignore[arg-type]

    assert {kind for kind, _ in targets.values()} == catalog, (
        "the packaged example no longer instantiates every record-bearing class, so this test "
        "would silently cover fewer arms than the catalog has"
    )

    missed: list[str] = []
    for position, (path, (_, record_id)) in enumerate(sorted(targets.items())):
        evidence_id = f"evidence.example.reach-{position:03d}.001"
        text = f"The owner attests to {record_id}."
        outcome = add_evidence(
            synthetic_bundle.root,
            draft_name=synthetic_bundle.draft_name,
            evidence_document=_linking_record(
                text,
                supports=[record_id],
                evidence_id=evidence_id,
                evidence_class=(
                    "measured_result" if prefix_of(record_id) == "metric" else "owner_attestation"
                ),
            ),
            capture=text.encode("utf-8"),
        )
        if outcome.category != "clean":
            missed.append(f"{path}: {record_id}: refused {_codes(outcome)}")
        elif evidence_id not in _cited_by(synthetic_bundle, path.as_posix(), record_id):
            missed.append(f"{path}: {record_id}: no back-citation written")

    assert missed == [], missed
    assert len(targets) == len(catalog) == 13
    assert _asymmetries(synthetic_bundle) == []


def test_a_capture_naming_only_a_skill_or_a_claim_rewrites_no_record_document(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Skills and claims carry no `evidence_ids`; a one-way link there is legitimate under §12.

    Asserting the tree, not just the exit code: citing back into a record that cannot cite would
    invent an error, and the cheapest way to get that wrong is to link by prefix-blindness.
    """
    text = "The owner attests to the language skill and the summary claim in this bundle."
    before = _tree(synthetic_bundle)

    outcome = add_evidence(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        evidence_document=_linking_record(
            text,
            supports=["skill.example-language"],
            contextualizes=["claim.example.summary.001"],
            evidence_class="secondary_summary",
        ),
        capture=text.encode("utf-8"),
    )

    assert outcome.category == "clean", outcome.diagnostics
    after = _tree(synthetic_bundle)
    changed = {path for path in after if after[path] != before.get(path)}
    assert changed == {
        f"drafts/{synthetic_bundle.draft_name}/evidence/records.yaml",
        f"drafts/{synthetic_bundle.draft_name}/manifest.yaml",
    }
    assert _asymmetries(synthetic_bundle) == []
    assert outcome.value is not None
    assert outcome.value.cited_back == ()


def test_a_record_the_draft_does_not_hold_is_left_to_the_broken_reference_check(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """A dangling target is a broken reference, and inventing a citation would not repair it."""
    text = "The owner attests to something this bundle does not record."
    outcome = add_evidence(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        evidence_document=_linking_record(text, supports=["fact.example.absent.999"]),
        capture=text.encode("utf-8"),
    )

    assert outcome.category == "clean", outcome.diagnostics
    ctx = build_context(
        draft_root(synthetic_bundle.root, synthetic_bundle.draft_name), mode="draft"
    )
    codes = {finding.code for finding in validate_referential(ctx)}
    assert IssueCode.EVIDENCE_LINK_ASYMMETRY.value not in codes
    assert codes, "a dangling target must still be reported by some referential check"


def test_a_record_that_already_cites_the_evidence_is_not_rewritten(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Idempotence, and the reason `evidence_ids` is rebuilt from a set rather than appended to."""
    text = "The owner attests to the professional name recorded in this bundle."
    add_evidence(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        evidence_document=_linking_record(text, supports=["fact.example.name.001"]),
        capture=text.encode("utf-8"),
    )
    cited = _cited_by(synthetic_bundle, "facts/identity.yaml", "fact.example.name.001")

    second = "A second attestation naming the same fact."
    outcome = add_evidence(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        evidence_document=_linking_record(
            second,
            supports=["fact.example.name.001"],
            evidence_id="evidence.example.link.002",
        ),
        capture=second.encode("utf-8"),
    )

    assert outcome.category == "clean", outcome.diagnostics
    after = _cited_by(synthetic_bundle, "facts/identity.yaml", "fact.example.name.001")
    assert set(after) == {*cited, "evidence.example.link.002"}
    assert list(after) == sorted(set(after)), "`evidence_ids` is UniqueSorted"
    assert _asymmetries(synthetic_bundle) == []


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


def test_every_ruling_decision_has_a_resulting_conflict_state() -> None:
    """`_STATE_AFTER` is a total mapping over `RulingDecision`, and nothing else makes it stay one.

    `resolve_conflict` subscripts it directly, so a member added at schema v2 would raise `KeyError`
    — a shape `_guarded` does not catch, §21 has no exit code for, and the operator would meet as a
    traceback. Both sides are read from the modules that own them rather than restated here, so this
    fails the moment either grows without the other.
    """
    assert set(_STATE_AFTER) == set(RulingDecision)


@pytest.mark.skipif(
    os.name != "posix", reason="mode bits do not deny directory writes on Windows"
)
def test_a_manifest_write_that_cannot_start_leaves_the_evidence_document_alone(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """A multi-document edit must not commit half of itself and then report that nothing happened.

    `add_evidence` changes `evidence/records.yaml`, the `evidence_set_digest` in `manifest.yaml`
    that describes it, and — since D-143 — each fact or metric document the capture cites back into.
    Written one at a time, a failure on the last left the earlier ones durable, the
    manifest stale — the exact `evidence_set_digest_mismatch` the second write exists to prevent —
    and the command answered `could_not_complete`, which §21 defines as nothing usable having
    happened. An operator taking that at its word and retrying then landed on `duplicate_record_id`.

    The two writes are not even the same failure domain: `mkstemp` stages beside each destination,
    so the evidence document needs `evidence/` writable and the manifest needs the draft root. This
    makes the draft root unwritable and leaves `evidence/` alone, which is the narrowest way to fail
    the second write and only the second.

    Read-only rather than the more obvious "delete the manifest", because a missing manifest fails
    earlier, at load, and would pass whether or not the writes are staged together.
    """
    draft = draft_root(synthetic_bundle.root, synthetic_bundle.draft_name)
    text = "A note that is entirely unremarkable."
    before = _tree(synthetic_bundle)

    mode = draft.stat().st_mode
    draft.chmod(0o555)
    try:
        outcome = add_evidence(
            synthetic_bundle.root,
            draft_name=synthetic_bundle.draft_name,
            evidence_document=_inline_record(text),
            capture=text.encode("utf-8"),
        )
    finally:
        draft.chmod(mode)

    assert outcome.exit_code == 3
    assert _codes(outcome) == {"io_error"}
    # The blob store is the one documented exception and an inline capture writes no blob, so the
    # whole draft must be byte-identical — not merely "the manifest is consistent with the records".
    assert _tree(synthetic_bundle) == before


def test_a_rename_that_fails_after_the_first_one_names_the_half_applied_state(
    synthetic_bundle: SyntheticBundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second arm of the multi-document write, and the one the first fix moved rather than closed.

    It also pins the write ORDER `add_evidence` states: `applied` below is exactly
    `evidence/records.yaml`, so the evidence record is the first rename — the pointer target before
    the pointer that cites it (D-143).

    Staging both documents before renaming either removes every failure that can be *avoided*, but
    `os.replace` itself can still fail: `mkstemp` needs the directory writable while the rename
    additionally needs the existing target unlinkable, so an immutable target file separates them.
    Left bare, that loop reproduced exactly the fault the staging was added to prevent — first
    document durable, second stale — and reported it as `could_not_complete`, "nothing was written".

    A rename already performed cannot be undone by a process that may not survive to try, so the
    window is *named* rather than closed: `partial_edit_applied`, which is deliberately not a
    could-not-complete code, because exit 3 would invite a retry guaranteed to refuse.

    `os.replace` is monkeypatched rather than made to fail for real: `chflags uchg` is macOS-only and
    `chattr +i` needs root, and the property under test is this function's error handling, not the
    filesystem's.
    """
    real_replace = os.replace
    calls: list[int] = []

    def fail_after_the_first(src, dst, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(1)
        if len(calls) == 1:
            return real_replace(src, dst, **kwargs)
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(os, "replace", fail_after_the_first)
    text = "A note whose second write will not land."
    outcome = add_evidence(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        evidence_document=_inline_record(text),
        capture=text.encode("utf-8"),
    )
    monkeypatch.undo()

    # Not exit 3: something DID happen, and a caller told otherwise retries into a duplicate ID.
    assert outcome.exit_code == 1
    assert _codes(outcome) == {"partial_edit_applied"}
    assert IssueCode.PARTIAL_EDIT_APPLIED not in COULD_NOT_COMPLETE_CODES
    (finding,) = outcome.diagnostics
    assert finding.details["applied"] == ["evidence/records.yaml"]
    # The staged file for the rename that failed must not survive: an undeclared file under the
    # draft makes every later command refuse with `unknown_file` before reading anything, which
    # would hide this very state behind a dotfile no diagnostic names.
    draft = draft_root(synthetic_bundle.root, synthetic_bundle.draft_name)
    assert list(draft.rglob(".tmp-authoring-*")) == []


def test_the_manifest_is_committed_before_the_records_that_cite_the_evidence(
    synthetic_bundle: SyntheticBundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The write order is a claim about which half-applied states are repairable, so it is pinned.

    `evidence_set_digest` describes the evidence document alone, so it goes stale the instant the
    first rename lands. Written LAST it would give every citing document a failure position that
    reports `evidence_set_digest_mismatch` — §21's "evidence mutated after promotion", which no
    command repairs — on top of the citation it did not write. Written second, each remaining
    position carries exactly one error class, and that class is the ordinary
    `evidence_link_asymmetry` an owner can fix with a draft edit.

    Only "evidence is first" was pinned before, so reordering the other two passed the whole suite.
    """
    real_replace = os.replace
    calls: list[int] = []

    def fail_after_the_second(src, dst, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(1)
        if len(calls) <= 2:
            return real_replace(src, dst, **kwargs)
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(os, "replace", fail_after_the_second)
    text = "A note whose citing document will not land."
    outcome = add_evidence(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        evidence_document=_linking_record(text, supports=["fact.example.name.001"]),
        capture=text.encode("utf-8"),
    )
    monkeypatch.undo()

    assert _codes(outcome) == {"partial_edit_applied"}
    (finding,) = outcome.diagnostics
    assert finding.details["applied"] == ["evidence/records.yaml", "manifest.yaml"]

    # The point of the order: the draft owes the citation and nothing about digest integrity.
    ctx = build_context(draft_root(synthetic_bundle.root, synthetic_bundle.draft_name), mode="draft")
    assert IssueCode.EVIDENCE_SET_DIGEST_MISMATCH.value not in {
        finding.code for finding in validate_digest(ctx)
    }
    assert _asymmetries(synthetic_bundle) == ["fact.example.name.001"]


def test_a_first_rename_that_fails_leaves_the_tree_untouched_and_no_residue(
    synthetic_bundle: SyntheticBundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other side of the new boundary: nothing committed, so the old truthful answer stands.

    This is the arm that must NOT report `partial_edit_applied` — no document landed, so
    could-not-complete is correct and the operator may retry. Asserting both arms is the point: a
    fix that reported the half-applied code unconditionally would pass the test above and be wrong
    here.
    """

    def always_fail(src, dst, **kwargs):  # type: ignore[no-untyped-def]
        raise PermissionError(1, "Operation not permitted")

    before = _tree(synthetic_bundle)
    monkeypatch.setattr(os, "replace", always_fail)
    text = "A note whose first write will not land."
    outcome = add_evidence(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        evidence_document=_inline_record(text),
        capture=text.encode("utf-8"),
    )
    monkeypatch.undo()

    assert outcome.exit_code == 3
    assert _codes(outcome) == {"io_error"}
    assert _tree(synthetic_bundle) == before
    draft = draft_root(synthetic_bundle.root, synthetic_bundle.draft_name)
    assert list(draft.rglob(".tmp-authoring-*")) == []


def test_a_ruling_is_committed_before_the_group_that_names_it(
    synthetic_bundle: SyntheticBundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`resolve_conflict` states an order and, until this test, nothing held it.

    The comment at the call site gives the reason: a ledger entry no group names yet is a decision
    waiting to be applied, which the next validation reports plainly, while a group naming a ruling
    the ledger does not hold is a broken reference to a decision nobody can read. Those two crash
    outcomes are not equally bad, so the order is load-bearing — and it is carried by nothing more
    durable than a `Mapping`'s iteration order, which reversing left the entire suite green.

    Pinned at the rename, not at the argument: the order that matters is the order the filesystem
    sees, and staging happens before any of it.
    """
    real_replace = os.replace
    renamed: list[str] = []

    def record(src, dst, **kwargs):  # type: ignore[no-untyped-def]
        renamed.append(os.path.basename(dst))
        return real_replace(src, dst, **kwargs)

    monkeypatch.setattr(os, "replace", record)
    outcome = resolve_conflict(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        ruling_document=_ruling(),
    )
    monkeypatch.undo()

    assert outcome.exit_code == 0, _codes(outcome)
    assert renamed == ["rulings.yaml", "groups.yaml"], renamed


# --------------------------------------------------------------------------------------
# T21 — both writers take the exclusive bundle lock (D-143 recorded the gap)
# --------------------------------------------------------------------------------------


def test_add_evidence_refuses_a_bundle_another_writer_holds(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """T21. `add_evidence` writes FOUR documents in a deliberate order — evidence, then the
    manifest that describes it, then the records that cite it — so a second writer interleaving
    between any two of them leaves exactly the state that ordering was designed to make
    unreachable. It took no lock at all, while `rebase` and `promote` both do.

    Refused, not queued: a second operator is told the bundle is busy rather than waiting behind
    a write they cannot see (§21).
    """
    from boardwatch.profile_bundle.locking import bundle_lock

    before = _tree(synthetic_bundle)
    text = "The owner attests to the professional name recorded in this bundle."
    with bundle_lock(synthetic_bundle.root):
        outcome = add_evidence(
            synthetic_bundle.root,
            draft_name=synthetic_bundle.draft_name,
            evidence_document=_inline_record(text),
            capture=text.encode("utf-8"),
        )

    assert [finding.code for finding in outcome.diagnostics] == [IssueCode.BUNDLE_LOCK_HELD]
    assert outcome.value is None
    assert _tree(synthetic_bundle) == before, "a refused write must not have touched the tree"


def test_resolve_conflict_refuses_a_bundle_another_writer_holds(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The ruling is written before the group it rules on, so a second writer landing between
    the two leaves a group whose recorded ruling and recorded state disagree."""
    from boardwatch.profile_bundle.locking import bundle_lock

    before = _tree(synthetic_bundle)
    with bundle_lock(synthetic_bundle.root):
        outcome = resolve_conflict(
            synthetic_bundle.root,
            draft_name=synthetic_bundle.draft_name,
            ruling_document=_ruling(),
        )

    assert [finding.code for finding in outcome.diagnostics] == [IssueCode.BUNDLE_LOCK_HELD]
    assert outcome.value is None
    assert _tree(synthetic_bundle) == before
