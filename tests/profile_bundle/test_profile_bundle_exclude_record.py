"""`profile-bundle exclude-record`, and the owner gate an `owner_excluded` exclusion costs (§18).

Three claims, and the file is organised as three sections because they land in three places.

**The write.** `imports/exclusions.yaml` had no authoring command at all, so the only way to
account for a `review_required` record was to hand-edit two documents and hope a third agreed.
Disposition stays derived — the command appends the exclusion and asks `redispositioned_ledger`
what every record now is — and the drain entry that explained the unresolved record retires with
it, because §6.3a forbids a report entry for an excluded record.

**The refusal comes first, because an exclusion cannot be taken back.** Nothing in the package
removes one, and `ExclusionLedger` refuses a second exclusion for the same record, so a wrong
`reason` is permanent in that draft. The pre-write check is therefore the same prospective-tree
DIFF `edit-fact` and `add-fact` use, over the layer set that judges an import ledger rather than a
fact — `imports_completeness` included, since it owns the one reconciliation an exclusion can break
and the closing revalidation of every authoring command skips the completeness tier.

**The gate.** §18 makes `owner_excluded` cost an `approve_source_record_exclusion` sub-approval
bound to `source_exclusion_target_digest`. That binding is enforced by `validate_history` through
`required_approval_decisions`, and the tests for it here go through `promote` — the caller that
actually holds the parent the diff needs — rather than asserting the derivation agrees with itself.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import pytest
from typer.testing import CliRunner

from boardwatch.cli import profile_bundle_cmd
from boardwatch.cli.app import app
from boardwatch.profile_bundle import authoring, promotion
from boardwatch.profile_bundle.approvals import (
    approval_stamp_bytes,
    build_approval_stamp,
    required_approval_decisions,
)
from boardwatch.profile_bundle.canonical import (
    candidate_content_digest,
    source_exclusion_target_digest,
)
from boardwatch.profile_bundle.models.history import ApprovalAction, ApprovalStamp
from boardwatch.profile_bundle.models.imports import (
    Disposition,
    ExclusionLedger,
    ExclusionRecord,
    ExtractionReport,
    SourceLedger,
    SourceLedgerRecord,
)
from boardwatch.profile_bundle.paths import approval_path
from boardwatch.profile_bundle.validation import load_documents, validate_bundle
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from boardwatch.profile_bundle.yaml_writer import document_bytes
from tests.profile_bundle.conftest import SyntheticBundle, stored_blob_reader
from tests.profile_bundle.test_profile_bundle_cli_approval import FakeTerminal

#: The example's one `review_required` record: the pre-heading paragraph its extraction mapping has
#: no locator for. It is the record `docs/profile-bundle-authoring.md` §16 prints as the
#: `import_record_undispositioned` blocker, which is what makes it the right subject here.
UNDISPOSITIONED = "source-record.5e0521371b368f834f16acafdc2d96a63e6ce94c330e8c51bf5eb2d9e09256ce"

#: The example's already-excluded record, and one of its two `imported` ones.
ALREADY_EXCLUDED = "source-record.bcf308bbe38a6812f15001d11e7800cda911cba8a1a47da6fca31a5e60e7a9e5"
IMPORTED = "source-record.944c2949212afd453c6df1f836e3b3f7e8c959c800032f03ac3dfdb18c850725"

RATIONALE = "Pre-heading prose with no professional assertion in it."
AS_OF = "2026-08-15"


def exclude(  # type: ignore[no-untyped-def]
    bundle: SyntheticBundle,
    *,
    record: str = UNDISPOSITIONED,
    reason: str = "owner_excluded",
    rationale: str = RATIONALE,
):
    return authoring.exclude_record(
        bundle.root,
        draft_name=bundle.draft_name,
        source_record_id=record,
        reason=reason,
        rationale=rationale,
    )


def codes(outcome) -> set[str]:  # type: ignore[no-untyped-def]
    return {finding.code for finding in outcome.diagnostics}


def document(bundle: SyntheticBundle, relative: str, kind):  # type: ignore[no-untyped-def]
    """Re-read one written document through the production loader, not through the command."""
    raw = bundle.document(relative).read_bytes()
    return kind.model_validate(
        load_yaml_bytes(raw, logical_path=PurePosixPath(relative))
    )


def ledger_of(bundle: SyntheticBundle) -> SourceLedger:
    return document(bundle, "imports/source-ledger.yaml", SourceLedger)


def exclusions_of(bundle: SyntheticBundle) -> ExclusionLedger:
    return document(bundle, "imports/exclusions.yaml", ExclusionLedger)


def completeness_findings(bundle: SyntheticBundle):  # type: ignore[no-untyped-def]
    outcome = validate_bundle(
        bundle.draft,
        bundle_root=bundle.root,
        mode="draft",
        completeness=True,
        as_of=datetime.fromisoformat(AS_OF).date(),
    )
    report = outcome.value
    assert report is not None
    return report.diagnostics


# --------------------------------------------------------------------------------------
# The write: one exclusion, one re-derived disposition, one retired drain entry
# --------------------------------------------------------------------------------------


def test_excluding_a_review_required_record_moves_it_out_of_the_blocker_bucket(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The claim the command exists for: `import_record_undispositioned` clears for this record.

    Read back off disk through the loader rather than off the command's return value, because a
    command's self-report is not verification of what it wrote.
    """
    before = {
        finding.record_id
        for finding in completeness_findings(synthetic_bundle)
        if finding.code == "import_record_undispositioned"
    }
    assert before == {UNDISPOSITIONED}

    outcome = exclude(synthetic_bundle)
    assert outcome.category == "clean", outcome.diagnostics

    rows = {row.source_record_id: row for row in ledger_of(synthetic_bundle).records}
    assert rows[UNDISPOSITIONED].disposition is Disposition.EXCLUDED
    assert rows[UNDISPOSITIONED].candidate_ids == ()
    # Every other record is untouched: a re-derivation that moved a second row would mean the
    # command decided something the exclusion did not say.
    assert rows[IMPORTED].disposition is Disposition.IMPORTED
    assert rows[ALREADY_EXCLUDED].disposition is Disposition.EXCLUDED

    after = {
        finding.record_id
        for finding in completeness_findings(synthetic_bundle)
        if finding.code == "import_record_undispositioned"
    }
    assert after == set()


def test_the_exclusion_records_the_reason_and_the_rationale_the_owner_gave(
    synthetic_bundle: SyntheticBundle,
) -> None:
    assert exclude(synthetic_bundle, reason="non_professional").category == "clean"

    written = exclusions_of(synthetic_bundle).by_record[UNDISPOSITIONED]
    assert written.reason.value == "non_professional"
    assert written.rationale == RATIONALE
    # Appended, not re-sorted: the existing row keeps its position so a one-record change produces
    # a one-record diff.
    assert exclusions_of(synthetic_bundle).exclusions[0].source_record_id == ALREADY_EXCLUDED


def test_the_drain_entry_for_the_now_excluded_record_retires_with_it(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§6.3a forbids an extraction-report entry for an `imported` or `excluded` record.

    Left behind, it reconciles to `import_denominator_mismatch` — in the COMPLETENESS tier, which
    no authoring command's closing revalidation runs, so the mistake would first appear at
    `promote`, against a draft holding an exclusion no command can remove.
    """
    report_path = synthetic_bundle.document("imports/extraction-report.yaml")
    assert UNDISPOSITIONED in report_path.read_text(encoding="utf-8")

    outcome = exclude(synthetic_bundle)
    assert outcome.category == "clean", outcome.diagnostics
    assert UNDISPOSITIONED not in report_path.read_text(encoding="utf-8")

    assert outcome.value is not None
    # Ledger, drain, exclusion — the order the renames land in, and the reason the half-applied
    # state below is repairable. See the retry test.
    assert outcome.value.documents == (
        "imports/source-ledger.yaml",
        "imports/extraction-report.yaml",
        "imports/exclusions.yaml",
    )
    assert outcome.value.previous_disposition == "review_required"
    # What the command REPORTS against what the ledger on disk says, read back through the loader.
    # `RecordExclusion.disposition` is taken off the re-derived row for this reason: stated as the
    # constant `excluded` it would report the expected answer whatever the derivation produced.
    row = next(
        item for item in ledger_of(synthetic_bundle).records
        if item.source_record_id == UNDISPOSITIONED
    )
    assert outcome.value.disposition == row.disposition.value == "excluded"
    assert "import_denominator_mismatch" not in {
        finding.code for finding in completeness_findings(synthetic_bundle)
    }


def test_a_half_applied_write_is_completed_by_running_the_same_command_again(
    synthetic_bundle: SyntheticBundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The write ORDER is a claim about which half-applied state a retry can repair, so it is pinned.

    Three renames, and D-137 says they cannot be made atomic. Exclusion-first leaves the reason
    durable against a ledger that never moved — and that is the one state nothing repairs:
    `_excludable_record` refuses `duplicate_record_id` on the retry, no command removes an
    exclusion, so the operator's only remaining move is to discard the draft. Ledger and drain
    first leaves a row dispositioned `excluded` with no exclusion beside it, which the same command
    run again completes, because that row is still one it admits.

    `os.replace` is monkeypatched rather than made to fail for real, for
    `test_profile_bundle_authoring`'s reason: the property under test is this command's ordering,
    not the filesystem's.
    """
    real_replace = os.replace
    calls: list[int] = []

    def fail_after_the_second(src, dst, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(1)
        if len(calls) <= 2:
            return real_replace(src, dst, **kwargs)
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(os, "replace", fail_after_the_second)
    first = exclude(synthetic_bundle)
    monkeypatch.undo()

    assert codes(first) == {"partial_edit_applied"}
    (finding,) = first.diagnostics
    assert finding.details["applied"] == [
        "imports/source-ledger.yaml",
        "imports/extraction-report.yaml",
    ]
    rows = {row.source_record_id: row for row in ledger_of(synthetic_bundle).records}
    assert rows[UNDISPOSITIONED].disposition is Disposition.EXCLUDED
    assert UNDISPOSITIONED not in exclusions_of(synthetic_bundle).by_record

    second = exclude(synthetic_bundle)

    assert second.category == "clean", second.diagnostics
    assert second.value is not None
    # `excluded -> excluded`: the row had already moved, which is why `previous_disposition` cannot
    # be the constant `review_required` the docstring used to claim.
    assert second.value.previous_disposition == "excluded"
    assert second.value.disposition == "excluded"
    assert second.value.documents == ("imports/source-ledger.yaml", "imports/exclusions.yaml")
    assert exclusions_of(synthetic_bundle).by_record[UNDISPOSITIONED].rationale == RATIONALE
    assert "import_denominator_mismatch" not in {
        finding.code for finding in completeness_findings(synthetic_bundle)
    }


def drift_a_second_record(bundle: SyntheticBundle) -> None:
    """Hand-edit the ledger so a row the command will NOT be asked about disagrees with derivation.

    Not an invented state: `docs/profile-bundle-authoring.md` §"Editing" makes direct editing of a
    draft's YAML "supported and expected", so a draft whose ledger disagrees with the documents its
    dispositions derive from is one an operator can arrive with — this command exists precisely
    because doing it by hand is easy to get wrong. `IMPORTED` is recorded here as
    `review_required` while `imports/candidates.yaml`
    still holds its candidate, so re-deriving the whole ledger moves it straight back to `imported`
    — and §6.3a's drain entry, added here because a `review_required` record owes one, retires with
    it. Both writes go through the models and the bundle writer, so the fixture cannot encode a
    document the loader would not accept.
    """
    ledger = ledger_of(bundle).model_dump(mode="json")
    for row in ledger["records"]:
        if row["source_record_id"] == IMPORTED:
            row["disposition"] = "review_required"
            row["candidate_ids"] = []
    bundle.write(
        "imports/source-ledger.yaml",
        document_bytes(
            SourceLedger.model_validate(ledger).model_dump(mode="json"),
            logical_path=PurePosixPath("imports/source-ledger.yaml"),
        ).decode("utf-8"),
    )

    report = document(bundle, "imports/extraction-report.yaml", ExtractionReport).model_dump(
        mode="json"
    )
    report["entries"].append({"source_record_id": IMPORTED, "reason": "free_text_deferred"})
    bundle.write(
        "imports/extraction-report.yaml",
        document_bytes(
            ExtractionReport.model_validate(report).model_dump(mode="json"),
            logical_path=PurePosixPath("imports/extraction-report.yaml"),
        ).decode("utf-8"),
    )


def test_a_row_the_operator_did_not_name_is_refused_rather_than_silently_re_derived(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """`redispositioned_ledger` re-derives EVERY row, and repairing one is a silent Gate B move.

    `_catalog_admits` cannot object: it is a DIFF keyed on `(code, record_id, message)`, and
    repairing a pre-existing inconsistency only ever REMOVES findings, so there is nothing for it
    to call introduced. Without the refusal this returns `clean`, reports one record, and moves a
    second one — `imported` 1 -> 2, `review_required` 2 -> 0 — with the drain entry that explained
    it gone too.
    """
    drift_a_second_record(synthetic_bundle)
    before = {
        name: synthetic_bundle.read(f"imports/{name}.yaml")
        for name in ("source-ledger", "exclusions", "extraction-report")
    }

    outcome = exclude(synthetic_bundle)

    assert codes(outcome) == {"import_ledger_derivation_drift"}
    assert [finding.record_id for finding in outcome.diagnostics] == [IMPORTED]
    assert outcome.diagnostics[0].details["recorded"] == "review_required"
    assert outcome.diagnostics[0].details["derived"] == "imported"
    # Nothing written, which is what makes this a refusal rather than a partial repair: the drifted
    # row is still drifted and the record the operator DID name is still unaccounted for.
    for name, original in before.items():
        assert synthetic_bundle.read(f"imports/{name}.yaml") == original


def stale_drain_entry_only(bundle: SyntheticBundle) -> None:
    """Give an already-`imported` record a drain entry, and leave the ledger completely alone.

    The distinction from `drift_a_second_record` is the whole point: there the second row's
    disposition moves, so the ledger check sees it. Here NO row moves — the entry is simply one
    §6.3a forbids, on a record that is `imported` before and after — so the ledger diff is empty
    and only the drain diff can catch it.
    """
    report = document(bundle, "imports/extraction-report.yaml", ExtractionReport).model_dump(
        mode="json"
    )
    report["entries"].append({"source_record_id": IMPORTED, "reason": "free_text_deferred"})
    bundle.write(
        "imports/extraction-report.yaml",
        document_bytes(
            ExtractionReport.model_validate(report).model_dump(mode="json"),
            logical_path=PurePosixPath("imports/extraction-report.yaml"),
        ).decode("utf-8"),
    )


def test_a_drain_entry_the_operator_did_not_name_is_refused_rather_than_silently_retired(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Guarding the ledger alone closes the reproduction, not the defect.

    `_report_without_dispositioned` retires by a record's CURRENT disposition in the rebuilt
    ledger, not by whether this write moved it. So a stale entry on a record already `imported`
    is dropped with **zero ledger drift** — `_only_the_named_record_moves` compares rows and finds
    none moved, and `_catalog_admits` is a DIFF that refuses only what a write introduces, while
    this write REMOVES `import_denominator_mismatch`. Without the drain check the command returns
    `clean`, names one record, and silently clears a Gate B blocker on another.
    """
    stale_drain_entry_only(synthetic_bundle)
    before = {
        name: synthetic_bundle.read(f"imports/{name}.yaml")
        for name in ("source-ledger", "exclusions", "extraction-report")
    }

    outcome = exclude(synthetic_bundle)

    assert codes(outcome) == {"import_ledger_derivation_drift"}
    assert [finding.record_id for finding in outcome.diagnostics] == [IMPORTED]
    assert outcome.diagnostics[0].path == "imports/extraction-report.yaml"
    assert outcome.diagnostics[0].details["drain_reason"] == "free_text_deferred"
    for name, original in before.items():
        assert synthetic_bundle.read(f"imports/{name}.yaml") == original


# --------------------------------------------------------------------------------------
# Refusals, all of which write nothing
# --------------------------------------------------------------------------------------


def test_a_record_the_ledger_does_not_enumerate_is_refused(
    synthetic_bundle: SyntheticBundle,
) -> None:
    original = synthetic_bundle.read("imports/exclusions.yaml")
    outcome = exclude(synthetic_bundle, record="source-record." + "a" * 64)
    assert codes(outcome) == {"broken_reference"}
    assert synthetic_bundle.read("imports/exclusions.yaml") == original


def test_a_record_already_excluded_is_refused_rather_than_re_decided(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The reason a wrong `reason` is permanent, said as a refusal instead of as a surprise."""
    original = synthetic_bundle.read("imports/exclusions.yaml")
    outcome = exclude(synthetic_bundle, record=ALREADY_EXCLUDED)
    assert codes(outcome) == {"duplicate_record_id"}
    assert synthetic_bundle.read("imports/exclusions.yaml") == original


def test_an_imported_record_is_refused_because_its_candidates_would_be_orphaned(
    synthetic_bundle: SyntheticBundle,
) -> None:
    outcome = exclude(synthetic_bundle, record=IMPORTED)
    assert codes(outcome) == {"import_missing_exclusion"}
    assert ledger_of(synthetic_bundle).records[0].disposition is Disposition.IMPORTED


@pytest.mark.parametrize("rationale", ["", "   "])
def test_a_blank_rationale_is_refused(
    synthetic_bundle: SyntheticBundle, rationale: str
) -> None:
    """§18: every exclusion requires a rationale. `NonBlankStr` is the rule; this is not a second
    copy of it, which is why the code is the model's rather than a bespoke one."""
    original = synthetic_bundle.read("imports/exclusions.yaml")
    outcome = exclude(synthetic_bundle, rationale=rationale)
    assert codes(outcome) == {"model_validation_error"}
    assert synthetic_bundle.read("imports/exclusions.yaml") == original


def test_a_reason_outside_the_closed_catalog_is_refused(
    synthetic_bundle: SyntheticBundle,
) -> None:
    outcome = exclude(synthetic_bundle, reason="the_owner_did_not_like_it")
    assert codes(outcome) == {"model_validation_error"}


# --------------------------------------------------------------------------------------
# The pre-write check, which is the reason the refusals above write nothing
# --------------------------------------------------------------------------------------


def test_the_pre_write_check_refuses_a_write_the_completeness_layer_would_reject(
    synthetic_bundle: SyntheticBundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Break the drain retirement and the command must refuse BEFORE the first byte.

    This is the defect the check exists for, reproduced: the exclusion and the ledger would be
    written, the closing revalidation would report nothing (it does not run the completeness tier),
    and the draft would hold an exclusion no command removes plus a report entry §6.3a forbids.
    """
    monkeypatch.setattr(authoring, "_report_without_dispositioned", lambda report, ledger: None)
    original = synthetic_bundle.read("imports/exclusions.yaml")

    outcome = exclude(synthetic_bundle)

    assert codes(outcome) == {"import_denominator_mismatch"}
    assert synthetic_bundle.read("imports/exclusions.yaml") == original
    assert ledger_of(synthetic_bundle).records[2].disposition is Disposition.REVIEW_REQUIRED


def test_the_ledger_pre_write_layers_are_read_off_validate_bundles_own_lists() -> None:
    """Derived from `run.py`'s source, never restated — the emitter owns both lists.

    `_LEDGER_LAYERS` is a SUBSET of what `promote` runs, and a subset is only safe while it is
    derived from the whole. Two things it must keep true: an eighth validity layer cannot appear in
    `validate_bundle` and be silently absent here, and `imports_completeness` cannot be dropped from
    the completeness lane while this set still claims to consult it.
    """
    source = (Path(authoring.__file__).parent / "validation" / "run.py").read_text(encoding="utf-8")
    block = source.split("findings: list[Diagnostic] = [", 1)[1].split("]", 1)[0]
    # Any starred call over `ctx`, not `validate_*` specifically: matching the naming convention
    # would make a validity layer that does not follow it invisible here, and "invisible" is the
    # exact failure this test exists to prevent. The completeness pattern below is already
    # name-agnostic for the same reason.
    validity = set(re.findall(r"\*(\w+)\(ctx\)", block))
    completeness = set(re.findall(r"findings\.extend\(\s*(\w+)\(\s*ctx", source))
    assert validity, "could not read validate_bundle's validity layer list"
    assert "imports_completeness" in completeness, "run.py no longer runs imports_completeness"

    consulted = {layer.__name__ for layer in authoring._LEDGER_LAYERS}
    # `history` needs a stamp a draft does not have; `digest` compares the manifest against bytes a
    # pre-write check has deliberately not written.
    excluded = {"validate_history", "validate_digest"}
    assert consulted == (validity - excluded) | {"imports_completeness"}, (
        f"validate_bundle runs {sorted(validity)} for validity; the ledger pre-write check "
        f"consults {sorted(consulted)}"
    )


# --------------------------------------------------------------------------------------
# The owner gate `owner_excluded` costs (§18), where it is enforced
# --------------------------------------------------------------------------------------

#: A ledger record and its exclusion, authored here and never derived from a bundle, and the digest
#: their join produces. Frozen because `source_exclusion_target_digest` is DURABLE: every promoted
#: revision carrying an `owner_excluded` exclusion has this value stamped into its approval, and no
#: command re-approves one — so a respelling of the join silently invalidates approvals already on
#: disk. Every other assertion about that digest in this file compares it against the function under
#: test and therefore agrees with itself; this literal is the one statement made from outside it.
#: Regenerating it to make a failing test pass is the mistake it exists to catch.
PINNED_RECORD_ID = "source-record." + "0f" * 32
PINNED_EXCLUSION_DIGEST = "sha256:9216ee93ddfdc042ce94ce5ca65cf03b646eec1c9c4f5b2c6d02c227e17ba0d8"


def test_the_exclusion_target_digest_keeps_the_spelling_already_on_disk() -> None:
    """The positional-pair spelling `approvals.py` stamped before the helper had any caller.

    A keyed `{"record": ..., "exclusion": ...}` mapping is the natural thing to write here and
    produces a different digest, which is exactly the change no test could see.
    """
    record = SourceLedgerRecord.model_validate(
        {
            "source_record_id": PINNED_RECORD_ID,
            "source_id": "source.frozen-digest-pin",
            "normalized_locator": "notes/heading-1",
            "disposition": "excluded",
            "candidate_ids": [],
        }
    )
    exclusion = ExclusionRecord.model_validate(
        {
            "source_record_id": PINNED_RECORD_ID,
            "reason": "owner_excluded",
            "rationale": "Not something the owner wants represented.",
        }
    )

    assert source_exclusion_target_digest(record, exclusion) == PINNED_EXCLUSION_DIGEST


def test_owner_excluded_reports_a_gate_bound_to_the_named_target_digest(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The digest is recomputed from the written documents by the function §18 names.

    `source_exclusion_target_digest` shipped with zero callers while `approvals.py` spelled the
    same join inline, so the documented binding and the enforced one were free to drift with no
    test able to notice. This asserts they are one value.
    """
    outcome = exclude(synthetic_bundle)
    assert outcome.value is not None
    gates = [
        gate
        for gate in outcome.value.owner_gates
        if gate.action is ApprovalAction.APPROVE_SOURCE_RECORD_EXCLUSION
    ]
    assert len(gates) == 1
    assert gates[0].target_record_id == UNDISPOSITIONED
    assert gates[0].resulting_state == "owner_excluded"

    row = next(
        item for item in ledger_of(synthetic_bundle).records
        if item.source_record_id == UNDISPOSITIONED
    )
    written = exclusions_of(synthetic_bundle).by_record[UNDISPOSITIONED]
    assert gates[0].target_content_digest == source_exclusion_target_digest(row, written)


@pytest.mark.parametrize(
    "reason",
    [
        "duplicate",
        "administrative_noise",
        "non_professional",
        "prohibited_sensitive",
        "superseded_source",
        "no_candidate_assertion",
    ],
)
def test_a_closed_reason_exclusion_owes_no_sub_approval(
    synthetic_bundle: SyntheticBundle, reason: str
) -> None:
    """Six of the seven reasons are the owner accounting for material, not asserting a preference.

    Every one of them, not a representative: §18 singles out exactly one reason, and a test that
    checked one alternative would pass just as well if the gate had been attached to five.
    """
    outcome = exclude(synthetic_bundle, reason=reason)
    assert outcome.category == "clean", outcome.diagnostics
    assert outcome.value is not None
    assert not [
        gate
        for gate in outcome.value.owner_gates
        if gate.action is ApprovalAction.APPROVE_SOURCE_RECORD_EXCLUSION
    ]


def stamp_for(
    bundle: SyntheticBundle, *, drop_exclusion_entries: bool = False
) -> str:
    """File the stamp `promote` will look for, optionally missing the exclusion sub-approval."""
    documents = load_documents(bundle.draft, mode="draft")
    digest = candidate_content_digest(documents, stored_blob_reader(bundle.root), None)
    decisions = required_approval_decisions(documents, None)
    if drop_exclusion_entries:
        decisions = tuple(
            decision
            for decision in decisions
            if decision.action is not ApprovalAction.APPROVE_SOURCE_RECORD_EXCLUSION
        )
    stamp = build_approval_stamp(
        stamp_id="approval-stamp.000001",
        candidate_digest=digest,
        approved_at=datetime(2026, 8, 15, 9, tzinfo=UTC),
        decisions=decisions,
    )
    path = approval_path(bundle.root, digest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        approval_stamp_bytes(stamp, logical_path=PurePosixPath(f"approvals/{path.name}"))
    )
    return digest


def promote_draft(bundle: SyntheticBundle):  # type: ignore[no-untyped-def]
    return promotion.promote(
        bundle.root,
        promotion.PromotionRequest(
            draft_name=bundle.draft_name,
            summary="account for the undispositioned record",
            actor="owner",
            created_at=datetime(2026, 8, 15, 10, tzinfo=UTC),
        ),
    )


def test_an_owner_excluded_exclusion_without_its_stamp_entry_is_refused_at_promotion(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The graph check §18 promises, asked of the caller that actually holds the parent diff.

    Nothing else in the tree changes between this test and the one below it — same draft, same
    write, same promotion — so the only thing the refusal can be about is the missing entry.
    """
    assert exclude(synthetic_bundle).category == "clean"
    stamp_for(synthetic_bundle, drop_exclusion_entries=True)

    outcome = promote_draft(synthetic_bundle)

    assert outcome.category == "findings"
    assert codes(outcome) == {"missing_owner_approval"}
    assert UNDISPOSITIONED in outcome.diagnostics[0].message


def test_the_same_exclusion_promotes_cleanly_once_the_stamp_carries_the_entry(
    synthetic_bundle: SyntheticBundle,
) -> None:
    assert exclude(synthetic_bundle).category == "clean"
    stamp_for(synthetic_bundle)

    outcome = promote_draft(synthetic_bundle)

    assert outcome.category == "clean", outcome.diagnostics


def test_a_closed_reason_exclusion_promotes_with_no_sub_approval_in_the_stamp(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The other direction of the same gate: `APPROVAL_ENTRY_UNEXPECTED` would fire if the stamp
    carried an entry, and `MISSING_OWNER_APPROVAL` if one were required. Neither does."""
    assert exclude(synthetic_bundle, reason="no_candidate_assertion").category == "clean"
    digest = stamp_for(synthetic_bundle)

    outcome = promote_draft(synthetic_bundle)
    assert outcome.category == "clean", outcome.diagnostics

    filed = ApprovalStamp.model_validate(
        load_yaml_bytes(
            approval_path(synthetic_bundle.root, digest).read_bytes(),
            logical_path=PurePosixPath("approvals/stamp.yaml"),
        )
    )
    assert not [
        entry
        for entry in filed.entries
        if entry.action is ApprovalAction.APPROVE_SOURCE_RECORD_EXCLUSION
    ]


# --------------------------------------------------------------------------------------
# How the owner produces that stamp: the existing `approve`, on a controlling terminal
# --------------------------------------------------------------------------------------


def test_approve_shows_the_exclusion_gate_and_files_it_in_the_one_stamp(
    tmp_path: Path,
    synthetic_bundle: SyntheticBundle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§13 puts ONE stamp on a candidate, so this gate has nowhere else to be filed.

    The test replaces only the terminal, so the digest, the decisions, the stamp and its bytes are
    all production code — and the entry's `target_content_digest` is checked against
    `source_exclusion_target_digest` recomputed from the tree, which is a different route to the
    value than the one that produced it.
    """
    assert exclude(synthetic_bundle).category == "clean"
    terminal = FakeTerminal()
    monkeypatch.setattr(profile_bundle_cmd, "approval_terminal", lambda: terminal)

    result = CliRunner().invoke(
        app,
        [
            "--data-dir",
            str(tmp_path / "data"),
            "profile-bundle",
            "approve",
            "--draft",
            synthetic_bundle.draft_name,
            "--bundle",
            str(synthetic_bundle.root),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output

    shown = "\n".join(terminal.shown)
    assert f"approve_source_record_exclusion {UNDISPOSITIONED} -> owner_excluded" in shown

    digest = json.loads(result.output)["result"]["candidate_digest"]
    filed = ApprovalStamp.model_validate(
        load_yaml_bytes(
            approval_path(synthetic_bundle.root, digest).read_bytes(),
            logical_path=PurePosixPath("approvals/stamp.yaml"),
        )
    )
    entries = [
        entry
        for entry in filed.entries
        if entry.action is ApprovalAction.APPROVE_SOURCE_RECORD_EXCLUSION
    ]
    assert len(entries) == 1
    row = next(
        item for item in ledger_of(synthetic_bundle).records
        if item.source_record_id == UNDISPOSITIONED
    )
    written = exclusions_of(synthetic_bundle).by_record[UNDISPOSITIONED]
    assert entries[0].target_content_digest == source_exclusion_target_digest(row, written)
    assert entries[0].resulting_state == "owner_excluded"


# --------------------------------------------------------------------------------------
# The command layer
# --------------------------------------------------------------------------------------


def test_the_cli_reports_the_disposition_move_and_the_gate(
    tmp_path: Path, synthetic_bundle: SyntheticBundle
) -> None:
    result = CliRunner().invoke(
        app,
        [
            "--data-dir",
            str(tmp_path / "data"),
            "profile-bundle",
            "exclude-record",
            "--draft",
            synthetic_bundle.draft_name,
            "--bundle",
            str(synthetic_bundle.root),
            "--source-record-id",
            UNDISPOSITIONED,
            "--reason",
            "owner_excluded",
            "--rationale",
            RATIONALE,
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["outcome"] == "clean"
    assert payload["result"]["previous_disposition"] == "review_required"
    assert payload["result"]["disposition"] == "excluded"
    row = next(
        item for item in ledger_of(synthetic_bundle).records
        if item.source_record_id == UNDISPOSITIONED
    )
    written = exclusions_of(synthetic_bundle).by_record[UNDISPOSITIONED]
    assert payload["result"]["owner_gates"] == [
        {
            "action": "approve_source_record_exclusion",
            "target_record_id": UNDISPOSITIONED,
            "target_content_digest": source_exclusion_target_digest(row, written),
            "resulting_state": "owner_excluded",
        }
    ]


def test_the_cli_refuses_a_reason_outside_the_closed_catalog_before_reading_the_bundle(
    tmp_path: Path, synthetic_bundle: SyntheticBundle
) -> None:
    """Typer's own enum handling, which is why the exit code is 2 rather than 1."""
    result = CliRunner().invoke(
        app,
        [
            "--data-dir",
            str(tmp_path / "data"),
            "profile-bundle",
            "exclude-record",
            "--draft",
            synthetic_bundle.draft_name,
            "--bundle",
            str(synthetic_bundle.root),
            "--source-record-id",
            UNDISPOSITIONED,
            "--reason",
            "the_owner_did_not_like_it",
            "--rationale",
            RATIONALE,
        ],
    )
    assert result.exit_code == 2
    assert synthetic_bundle.read("imports/exclusions.yaml").count("source_record_id") == 1
