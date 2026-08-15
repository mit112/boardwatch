"""`edit-fact` and `add-fact`: the incremental path from a checked-out draft to a new revision.

Before these existed, changing one bullet meant a full rebuild — `init`, `import`, `extract`,
`promote-candidates` — because `promote-candidates` is one-shot and refuses once entities exist. The
capability was always there (`checkout` copies the selected revision into a writable draft); what
was missing was a writer that keeps the three documents an edit touches in agreement.

The three are the point. A fact edit is not one write:

1. the fact-bearing document, which gains the successor and marks the original `superseded`;
2. `evidence/records.yaml`, because §12 requires the two citation directions to agree exactly and
   the successor cites evidence that does not yet name it;
3. `manifest.yaml`, whose `evidence_set_digest` describes the evidence document that just changed.

Omit the second and the draft fails `evidence_link_asymmetry`; omit the third and it fails
`evidence_set_digest_mismatch`. So the test that matters most in this file is not any single
assertion about a field — it is that the draft still validates clean afterwards, which is the only
thing that makes the next `approve` reachable.

Correction is an edge, not a mutation (`models/facts.py`): the successor gets a new `fact_id` and
the original stays immutable, so history is derivable rather than overwritten.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import PurePosixPath

import pytest
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.profile_bundle.authoring import add_fact, edit_fact
from boardwatch.profile_bundle.models.base import EFFECTIVE_STATES, VerificationState
from boardwatch.profile_bundle.models.documents import FactBearingDocument
from boardwatch.profile_bundle.validation import validate_bundle
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from tests.profile_bundle.conftest import (
    PromotedRevisionTree,
    SyntheticBundle,
    parse_documents,
    quoted_yaml,
)

#: An `owner_confirmed`/`owner_attested` string fact citing the owner-attestation record. The shape
#: every résumé bullet has, and so the shape `edit-fact` is for.
TITLE = "fact.example-labs.title.001"

#: `verified`/`private_document_verified`. Editing its wording would inherit a basis the private
#: document no longer supports, which is the one case `edit-fact` refuses.
ORGANIZATION = "fact.example-labs.organization.001"

#: A `date_range` fact — no string can express its value, so `--value` cannot edit it.
DATES = "fact.example-labs.dates.001"

ATTESTATION = "evidence.example.owner-attestation.001"
LABS = "employment.example-labs"
AS_OF = date(2026, 8, 14)


def facts_of(bundle: SyntheticBundle) -> dict[str, object]:
    """Every fact in the draft, by ID, read back through the production loader."""
    documents = parse_documents(bundle.draft)
    found: dict[str, object] = {}
    for document in documents.by_path.values():
        if isinstance(document, FactBearingDocument):
            for fact in document.facts:
                found[fact.fact_id] = fact
    return found


def draft_is_clean(bundle: SyntheticBundle) -> list[str]:
    """The codes the draft reports, so a failure names them instead of just being False."""
    outcome = validate_bundle(bundle.draft, bundle_root=bundle.root, mode="draft")
    return [item.code for item in outcome.diagnostics]


def seed_import_lineage(bundle: SyntheticBundle, fact_id: str) -> None:
    """Give one fact an import lineage, through the loader and writer production uses.

    Written back with `quoted_yaml` rather than a text substitution so the seed is a document the
    restricted loader accepts — a fixture that hand-rolled the quoting would be asserting against
    bytes no production reader would have produced.
    """
    relative = "facts/experience/employment.example-labs.yaml"
    logical = PurePosixPath(relative)
    path = bundle.document(relative)
    data = load_yaml_bytes(path.read_bytes(), logical_path=logical)
    seeded = [row for row in data["facts"] if row["fact_id"] == fact_id]
    assert len(seeded) == 1, f"{fact_id} is not a fact of {relative}"
    seeded[0]["import_lineage"] = {
        "source_id": "source.synthetic-notes",
        "source_locator": "example-labs/title/paragraph-1",
        "source_content_digest": "sha256:" + "0" * 64,
    }
    path.write_bytes(quoted_yaml(data, logical_path=logical))


# --------------------------------------------------------------------------------------
# edit-fact
# --------------------------------------------------------------------------------------


def test_edit_fact_leaves_the_draft_validating_clean(synthetic_bundle: SyntheticBundle) -> None:
    """The whole contract in one assertion: an edit is approvable without a hand repair.

    This is what fails if the evidence back-citation or the manifest digest is skipped — the two
    writes an owner doing this by hand forgets, and the reason the command exists at all.
    """
    outcome = edit_fact(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        fact_id=TITLE,
        value="Senior Software Engineer",
        as_of=AS_OF,
    )

    assert outcome.category == "clean", outcome.diagnostics
    assert draft_is_clean(synthetic_bundle) == []


def test_edit_fact_files_a_successor_carrying_the_new_value(
    synthetic_bundle: SyntheticBundle,
) -> None:
    edit_fact(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        fact_id=TITLE,
        value="Senior Software Engineer",
        as_of=AS_OF,
    )

    successor = facts_of(synthetic_bundle)[f"{TITLE}.r2"]
    assert successor.value.value == "Senior Software Engineer"
    assert successor.supersedes_fact_ids == (TITLE,)
    assert successor.reviewed_at == AS_OF


def test_edit_fact_keeps_the_original_immutable(synthetic_bundle: SyntheticBundle) -> None:
    """Correction is an edge: the original's value is never rewritten in place."""
    before = facts_of(synthetic_bundle)[TITLE].value.value

    edit_fact(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        fact_id=TITLE,
        value="Senior Software Engineer",
        as_of=AS_OF,
    )

    assert facts_of(synthetic_bundle)[TITLE].value.value == before


def test_edit_fact_takes_the_original_out_of_effect(synthetic_bundle: SyntheticBundle) -> None:
    """`superseded` is in `UNAVAILABLE_STATES`, so the old wording stops reaching any surface.

    Without this the render would show both the old bullet and its replacement, and `validate`
    would report the original as still effective while something supersedes it.
    """
    edit_fact(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        fact_id=TITLE,
        value="Senior Software Engineer",
        as_of=AS_OF,
    )

    original = facts_of(synthetic_bundle)[TITLE]
    assert original.verification_state == VerificationState.SUPERSEDED
    assert original.verification_state not in EFFECTIVE_STATES


def test_edit_fact_drops_the_import_lineage(synthetic_bundle: SyntheticBundle) -> None:
    """An owner's wording is not what the source said, so the successor claims no source.

    Carrying the parent's `source_content_digest` forward would assert a match against bytes that
    no longer contain this text — a provenance claim nothing checks and nothing could repair.

    The lineage is seeded here rather than taken from the example, and that is the whole point of
    the test: every fact the example imports either holds no lineage or is refused for its basis,
    so an assertion against the fixture as shipped passes whether or not the successor drops
    anything. It survived a mutation that deleted the drop until this seeded a parent that
    genuinely had something to lose.
    """
    seed_import_lineage(synthetic_bundle, TITLE)
    assert facts_of(synthetic_bundle)[TITLE].import_lineage is not None, "the seed did not land"

    edit_fact(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        fact_id=TITLE,
        value="Senior Software Engineer",
        as_of=AS_OF,
    )

    assert facts_of(synthetic_bundle)[f"{TITLE}.r2"].import_lineage is None


def test_edit_fact_has_the_evidence_name_the_successor(synthetic_bundle: SyntheticBundle) -> None:
    """§12's two directions, written on both sides by the one command."""
    edit_fact(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        fact_id=TITLE,
        value="Senior Software Engineer",
        as_of=AS_OF,
    )

    documents = parse_documents(synthetic_bundle.draft)
    evidence = next(
        record
        for document in documents.by_path.values()
        for record in getattr(document, "evidence", ())
        if record.evidence_id == ATTESTATION
    )
    assert f"{TITLE}.r2" in evidence.supports_record_ids


def test_editing_twice_files_a_third_revision(synthetic_bundle: SyntheticBundle) -> None:
    """The successor of a successor, so refining one bullet repeatedly does not collide."""
    for target, wording in (
        (TITLE, "Senior Software Engineer"),
        (f"{TITLE}.r2", "Staff Software Engineer"),
    ):
        outcome = edit_fact(
            synthetic_bundle.root,
            draft_name=synthetic_bundle.draft_name,
            fact_id=target,
            value=wording,
            as_of=AS_OF,
        )
        assert outcome.category == "clean", outcome.diagnostics

    found = facts_of(synthetic_bundle)
    assert found[f"{TITLE}.r3"].value.value == "Staff Software Engineer"
    assert found[f"{TITLE}.r3"].supersedes_fact_ids == (f"{TITLE}.r2",)
    assert found[f"{TITLE}.r2"].verification_state == VerificationState.SUPERSEDED
    assert draft_is_clean(synthetic_bundle) == []


def test_edit_fact_refuses_a_fact_already_superseded(synthetic_bundle: SyntheticBundle) -> None:
    """Editing a corrected record would branch the chain, leaving two live successors.

    The operator names the record they can see; once it has been corrected, the one that still
    reaches a surface is its successor, so that is the one an edit has to name.
    """
    edit_fact(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        fact_id=TITLE,
        value="Senior Software Engineer",
        as_of=AS_OF,
    )

    outcome = edit_fact(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        fact_id=TITLE,
        value="Staff Software Engineer",
        as_of=AS_OF,
    )

    assert outcome.category == "findings"
    assert [item.code for item in outcome.diagnostics] == ["fact_state_inconsistent"]


def test_edit_fact_refuses_a_basis_the_owner_cannot_attest(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Rewriting a `private_document_verified` fact would inherit a basis nothing supports.

    The document verified the old wording. Inheriting its basis would let an owner's retype acquire
    the authority of a record that was never re-read, so this refuses rather than silently
    downgrading the basis to `owner_attested` on the owner's behalf.
    """
    outcome = edit_fact(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        fact_id=ORGANIZATION,
        value="Example Laboratories",
        as_of=AS_OF,
    )

    assert outcome.category == "findings"
    assert [item.code for item in outcome.diagnostics] == ["verification_basis_unsupported"]


def test_edit_fact_refuses_a_value_a_string_cannot_express(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """`--value` is text, and a `date_range` is not. Refuse rather than coerce."""
    outcome = edit_fact(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        fact_id=DATES,
        value="2024-01 to 2025-06",
        as_of=AS_OF,
    )

    assert outcome.category == "findings"
    assert [item.code for item in outcome.diagnostics] == ["model_validation_error"]


def test_edit_fact_refuses_a_fact_the_draft_does_not_hold(
    synthetic_bundle: SyntheticBundle,
) -> None:
    outcome = edit_fact(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        fact_id="fact.example-labs.nonexistent.001",
        value="anything",
        as_of=AS_OF,
    )

    assert outcome.category == "findings"
    assert [item.code for item in outcome.diagnostics] == ["broken_reference"]


@pytest.mark.parametrize(
    ("fact_id", "value"),
    [
        (ORGANIZATION, "Example Laboratories"),
        (DATES, "2024-01 to 2025-06"),
        ("fact.example-labs.nonexistent.001", "anything"),
    ],
)
def test_a_refused_edit_writes_nothing(
    synthetic_bundle: SyntheticBundle, fact_id: str, value: str
) -> None:
    """A refusal leaves the draft byte-identical, so the operator's second attempt starts clean."""
    before = {
        path: path.read_bytes()
        for path in sorted(synthetic_bundle.draft.rglob("*"))
        if path.is_file()
    }

    edit_fact(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        fact_id=fact_id,
        value=value,
        as_of=AS_OF,
    )

    after = {
        path: path.read_bytes()
        for path in sorted(synthetic_bundle.draft.rglob("*"))
        if path.is_file()
    }
    assert after == before


def test_edit_fact_refuses_a_draft_that_does_not_exist(synthetic_bundle: SyntheticBundle) -> None:
    outcome = edit_fact(
        synthetic_bundle.root,
        draft_name="no-such-draft",
        fact_id=TITLE,
        value="anything",
        as_of=AS_OF,
    )

    assert outcome.category == "findings"
    assert [item.code for item in outcome.diagnostics] == ["draft_not_found"]


def test_edit_fact_reports_the_owner_gate_the_successor_owes(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """An `owner_confirmed` successor is a confirmation the promotion will require."""
    outcome = edit_fact(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        fact_id=TITLE,
        value="Senior Software Engineer",
        as_of=AS_OF,
    )

    assert outcome.value is not None
    assert outcome.value.successor_fact_id == f"{TITLE}.r2"
    assert outcome.value.owner_gates != ()


# --------------------------------------------------------------------------------------
# add-fact
# --------------------------------------------------------------------------------------


def test_add_fact_leaves_the_draft_validating_clean(synthetic_bundle: SyntheticBundle) -> None:
    """A brand-new bullet, evidence linked both ways and the digest restated."""
    outcome = add_fact(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        fact_id="fact.example-labs.accomplishment.002",
        subject_id=LABS,
        predicate="employment.accomplishment",
        value="Cut nightly batch runtime from six hours to forty minutes.",
        evidence_id=ATTESTATION,
        verification_state="owner_confirmed",
        verification_basis="owner_attested",
        usage_context="professional",
        surfaces=("resume", "public"),
        as_of=AS_OF,
    )

    assert outcome.category == "clean", outcome.diagnostics
    assert draft_is_clean(synthetic_bundle) == []


def test_add_fact_supersedes_nothing(synthetic_bundle: SyntheticBundle) -> None:
    """An addition is not a correction: nothing already in the draft changes state."""
    add_fact(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        fact_id="fact.example-labs.accomplishment.002",
        subject_id=LABS,
        predicate="employment.accomplishment",
        value="Cut nightly batch runtime from six hours to forty minutes.",
        evidence_id=ATTESTATION,
        verification_state="owner_confirmed",
        verification_basis="owner_attested",
        usage_context="professional",
        surfaces=("resume", "public"),
        as_of=AS_OF,
    )

    found = facts_of(synthetic_bundle)
    assert found["fact.example-labs.accomplishment.002"].supersedes_fact_ids == ()
    assert found["fact.example-labs.accomplishment.001"].verification_state in EFFECTIVE_STATES


def test_add_fact_refuses_an_identifier_already_in_use(
    synthetic_bundle: SyntheticBundle,
) -> None:
    outcome = add_fact(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        fact_id=TITLE,
        subject_id=LABS,
        predicate="employment.title",
        value="Senior Software Engineer",
        evidence_id=ATTESTATION,
        verification_state="owner_confirmed",
        verification_basis="owner_attested",
        usage_context="professional",
        surfaces=("resume",),
        as_of=AS_OF,
    )

    assert outcome.category == "findings"
    assert [item.code for item in outcome.diagnostics] == ["duplicate_record_id"]


def test_add_fact_refuses_a_subject_the_draft_does_not_hold(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """No document owns the fact, so there is nowhere to write it."""
    outcome = add_fact(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        fact_id="fact.absent-corp.title.001",
        subject_id="employment.absent-corp",
        predicate="employment.title",
        value="Software Engineer",
        evidence_id=ATTESTATION,
        verification_state="owner_confirmed",
        verification_basis="owner_attested",
        usage_context="professional",
        surfaces=("resume",),
        as_of=AS_OF,
    )

    assert outcome.category == "findings"
    assert [item.code for item in outcome.diagnostics] == ["broken_reference"]


def test_add_fact_refuses_evidence_the_draft_does_not_hold(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Citing an absent record would leave the asymmetry this command exists to prevent."""
    outcome = add_fact(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        fact_id="fact.example-labs.accomplishment.002",
        subject_id=LABS,
        predicate="employment.accomplishment",
        value="Cut nightly batch runtime from six hours to forty minutes.",
        evidence_id="evidence.example.absent.001",
        verification_state="owner_confirmed",
        verification_basis="owner_attested",
        usage_context="professional",
        surfaces=("resume",),
        as_of=AS_OF,
    )

    assert outcome.category == "findings"
    assert [item.code for item in outcome.diagnostics] == ["broken_reference"]


def test_a_refused_addition_writes_nothing(synthetic_bundle: SyntheticBundle) -> None:
    before = {
        path: path.read_bytes()
        for path in sorted(synthetic_bundle.draft.rglob("*"))
        if path.is_file()
    }

    add_fact(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        fact_id="fact.absent-corp.title.001",
        subject_id="employment.absent-corp",
        predicate="employment.title",
        value="Software Engineer",
        evidence_id=ATTESTATION,
        verification_state="owner_confirmed",
        verification_basis="owner_attested",
        usage_context="professional",
        surfaces=("resume",),
        as_of=AS_OF,
    )

    after = {
        path: path.read_bytes()
        for path in sorted(synthetic_bundle.draft.rglob("*"))
        if path.is_file()
    }
    assert after == before


def test_add_fact_writes_the_value_the_caller_gave(synthetic_bundle: SyntheticBundle) -> None:
    wording = "Cut nightly batch runtime from six hours to forty minutes."

    add_fact(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        fact_id="fact.example-labs.accomplishment.002",
        subject_id=LABS,
        predicate="employment.accomplishment",
        value=wording,
        evidence_id=ATTESTATION,
        verification_state="owner_confirmed",
        verification_basis="owner_attested",
        usage_context="professional",
        surfaces=("resume", "public"),
        as_of=AS_OF,
    )

    added = facts_of(synthetic_bundle)["fact.example-labs.accomplishment.002"]
    assert added.value.value == wording
    assert added.evidence_ids == (ATTESTATION,)
    assert set(added.allowed_surfaces) == {"resume", "public"}


def test_add_fact_names_the_document_it_wrote(synthetic_bundle: SyntheticBundle) -> None:
    """The report says where the fact landed, so the operator can read it back."""
    outcome = add_fact(
        synthetic_bundle.root,
        draft_name=synthetic_bundle.draft_name,
        fact_id="fact.example-labs.accomplishment.002",
        subject_id=LABS,
        predicate="employment.accomplishment",
        value="Cut nightly batch runtime from six hours to forty minutes.",
        evidence_id=ATTESTATION,
        verification_state="owner_confirmed",
        verification_basis="owner_attested",
        usage_context="professional",
        surfaces=("resume",),
        as_of=AS_OF,
    )

    assert outcome.value is not None
    assert outcome.value.document == "facts/experience/employment.example-labs.yaml"


def test_the_incremental_loop_runs_without_re_importing_the_source(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """`checkout` then `edit-fact`, against a genuinely promoted revision.

    The workflow claim, at the command layer: correcting one bullet in a bundle that has already
    been promoted needs neither `import`, `extract`, nor `promote-candidates` — the last of which
    is one-shot and refuses outright once entities exist, which is what used to force a full
    rebuild for every wording change. What the loop leaves behind is a draft that validates clean,
    which is the state `approve` requires.
    """
    root = promoted_tree.bundle_root
    runner = CliRunner()

    checkout = runner.invoke(
        app, ["profile-bundle", "checkout", "--bundle", str(root), "--draft", "wording", "--json"]
    )
    assert checkout.exit_code == 0, checkout.output

    edit = runner.invoke(
        app,
        [
            "profile-bundle",
            "edit-fact",
            "--bundle",
            str(root),
            "--draft",
            "wording",
            "--fact-id",
            TITLE,
            "--value",
            "Senior Software Engineer",
            "--json",
        ],
    )
    assert edit.exit_code == 0, edit.output
    report = json.loads(edit.output)
    assert report["result"]["successor_fact_id"] == f"{TITLE}.r2"
    assert report["outcome"] == "clean"


def test_a_path_that_would_orphan_the_fact_is_refused_before_any_write(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """A draft-name that escapes `drafts/` is a path refusal, not a fact refusal."""
    outcome = add_fact(
        synthetic_bundle.root,
        draft_name="../escape",
        fact_id="fact.example-labs.accomplishment.002",
        subject_id=LABS,
        predicate="employment.accomplishment",
        value="Cut nightly batch runtime from six hours to forty minutes.",
        evidence_id=ATTESTATION,
        verification_state="owner_confirmed",
        verification_basis="owner_attested",
        usage_context="professional",
        surfaces=("resume",),
        as_of=AS_OF,
    )

    assert outcome.category == "findings"
    assert [item.code for item in outcome.diagnostics] == ["draft_not_found"]
