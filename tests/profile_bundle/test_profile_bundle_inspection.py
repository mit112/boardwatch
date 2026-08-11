"""`inventory`, `inspect`, and `conflicts`: the three read-only reports (design §6, §19, §21).

§21 is categorical — "Inventory and inspection perform no writes. No Gate A/B command deletes
revisions, blobs, evidence, conflicts, rulings, drafts, or unselected digest directories" — so every
test here that exercises a command also proves the bundle came out byte-identical. That assertion is
the point of the slice: an inventory that quietly adopted a leftover directory would be reporting a
bundle it had just changed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from boardwatch.profile_bundle.drafts import init_draft
from boardwatch.profile_bundle.errors import IssueCode
from boardwatch.profile_bundle.inspection import conflicts_report, inspect_record, inventory
from boardwatch.profile_bundle.models.history import ConflictRecord
from boardwatch.profile_bundle.paths import (
    approval_path,
    blob_path,
    blobs_dir,
    complete_marker_path,
    current_path,
    digest_token,
    draft_root,
    drafts_dir,
    local_sources_path,
    rebase_backup_root,
    revisions_dir,
)
from tests.profile_bundle.conftest import (
    BLOB_SHA256,
    PromotedRevisionTree,
    promote_next_revision,
)

CANDIDATE_DIGEST = "sha256:" + "3" * 64
FACT_ID = "fact.packet-pantry.end-date.001"
CONFLICT_ID = "conflict.packet-pantry.end-date"


def _snapshot(root: Path) -> dict[str, bytes | None]:
    """Every path under `root`; `None` marks a directory. Proves nothing was added or removed."""
    return {
        str(path.relative_to(root)): path.read_bytes() if path.is_file() else None
        for path in sorted(root.rglob("*"))
    }


# --------------------------------------------------------------------------------------
# inventory
# --------------------------------------------------------------------------------------


def test_inventory_reports_the_selected_revision_and_its_drafts(
    promoted_tree: PromotedRevisionTree,
) -> None:
    draft_root(promoted_tree.bundle_root, "work").mkdir(parents=True)
    draft_root(promoted_tree.bundle_root, "spike").mkdir(parents=True)
    outcome = inventory(promoted_tree.bundle_root)
    assert outcome.category == "clean", outcome.diagnostics
    report = outcome.value
    assert report is not None
    assert report.selected is not None
    assert report.selected.bundle_digest == promoted_tree.bundle_digest
    assert report.drafts == ("spike", "work")
    assert report.complete_revisions == (digest_token(promoted_tree.bundle_digest),)
    assert report.unselected_revisions == ()


def test_inventory_on_a_bundle_that_has_never_promoted_is_clean(tmp_path: Path) -> None:
    """The state `init` leaves behind. An exit code that said "finding" for every fresh bundle
    would teach an operator to ignore this command's exit code, so the absence is a field."""
    root = tmp_path / "career-profile"
    assert init_draft(root, name="initial").category == "clean"
    outcome = inventory(root)
    assert outcome.category == "clean", outcome.diagnostics
    report = outcome.value
    assert report is not None
    assert report.selected is None
    assert report.drafts == ("initial",)


def test_inventory_reports_a_corrupt_selection_without_touching_it(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """A torn promotion is different from a bundle that has never promoted, and only one of the two
    is something an operator must act on."""
    complete_marker_path(promoted_tree.revision_dir).unlink()
    before = _snapshot(promoted_tree.bundle_root)
    outcome = inventory(promoted_tree.bundle_root)
    assert outcome.exit_code == 1
    assert str(IssueCode.COMPLETE_MARKER_MISSING) in {d.code for d in outcome.diagnostics}
    report = outcome.value
    assert report is not None
    assert report.selected is None
    assert _snapshot(promoted_tree.bundle_root) == before


def test_inventory_reports_external_approval_stamps(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """§13 keys a stamp by the candidate digest it approved, so the file name IS the report."""
    stamp = approval_path(promoted_tree.bundle_root, CANDIDATE_DIGEST)
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text("approval_stamp_id: 'approval-stamp.000001'\n", encoding="utf-8")
    report = inventory(promoted_tree.bundle_root).value
    assert report is not None
    assert report.approval_stamps == (CANDIDATE_DIGEST,)


def test_inventory_separates_referenced_from_unreferenced_blobs(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """Reported, never collected: §6 forbids automatic blob collection, and an older revision may
    still cite a blob this one dropped."""
    orphan = "b" * 64
    blob_path(promoted_tree.bundle_root, orphan).write_bytes(b"unreferenced")
    before = _snapshot(promoted_tree.bundle_root)
    report = inventory(promoted_tree.bundle_root).value
    assert report is not None
    assert report.referenced_blobs == (BLOB_SHA256,)
    assert report.unreferenced_blobs == (orphan,)
    assert _snapshot(promoted_tree.bundle_root) == before


def test_inventory_reports_torn_and_unselected_revision_directories(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """§6: neither blocks a later promotion, because a digest name reserves no revision number.
    Both are reported and neither is adopted or removed."""
    second = promote_next_revision(
        promoted_tree, mutate=lambda data: data["skills"][0].update({"canonical_name": "Later"})
    )
    torn = revisions_dir(second.bundle_root) / (digest_token("sha256:" + "c" * 64))
    torn.mkdir()
    (torn / "manifest.yaml").write_text("state: 'draft'\n", encoding="utf-8")
    temporary = revisions_dir(second.bundle_root) / ".tmp-promote-1234"
    temporary.mkdir()
    before = _snapshot(second.bundle_root)

    outcome = inventory(second.bundle_root)
    report = outcome.value
    assert report is not None
    assert report.unselected_revisions == (digest_token(promoted_tree.bundle_digest),)
    assert report.incomplete_revisions == (torn.name,)
    assert report.temporary_entries == (temporary.name,)
    assert outcome.exit_code == 0, outcome.diagnostics
    assert _snapshot(second.bundle_root) == before


def test_inventory_reports_undeclared_root_entries_without_failing(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """The root grammar is closed, but an operator's stray note must not break the one command whose
    job is to tell them the note is there."""
    (promoted_tree.bundle_root / "notes.txt").write_text("scratch\n", encoding="utf-8")
    outcome = inventory(promoted_tree.bundle_root)
    report = outcome.value
    assert report is not None
    assert report.undeclared_root_entries == ("notes.txt",)
    assert outcome.exit_code == 0
    assert {d.tier for d in outcome.diagnostics} == {"information"}


def test_inventory_reads_a_rebase_backup_of_a_long_draft_name_as_a_draft(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """A backup name is a draft name plus 83 derived characters, so it outgrows the shorter cap."""
    backup = rebase_backup_root(promoted_tree.bundle_root, "my-work-branch", "sha256:" + "a" * 64)
    backup.mkdir(parents=True)

    outcome = inventory(promoted_tree.bundle_root)

    report = outcome.value
    assert report is not None
    assert backup.name in report.drafts
    assert f"drafts/{backup.name}" not in {finding.path for finding in outcome.diagnostics}


def test_inventory_reports_an_interrupted_draft_installation(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """`init` and `checkout` build a draft beside its destination and rename it in, so a leftover
    staging directory is a real state. It is not a draft, and it is not deleted either."""
    leftover = drafts_dir(promoted_tree.bundle_root) / ".tmp-draft-abc123"
    leftover.mkdir(parents=True)
    before = _snapshot(promoted_tree.bundle_root)
    outcome = inventory(promoted_tree.bundle_root)
    report = outcome.value
    assert report is not None
    assert leftover.name not in report.drafts
    assert "drafts/.tmp-draft-abc123" in {d.path for d in outcome.diagnostics}
    assert outcome.exit_code == 0
    assert _snapshot(promoted_tree.bundle_root) == before


def test_an_in_flight_blob_write_is_not_reported_as_an_artefact(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """The blob store names its own temporaries, and this reader reads that name from the store
    rather than restating it, so a capture being written is not mistaken for a stray file."""
    (blobs_dir(promoted_tree.bundle_root) / ".tmp-halfway.blob").write_bytes(b"partial")
    outcome = inventory(promoted_tree.bundle_root)
    assert outcome.diagnostics == ()


def test_inventory_measures_no_blob_references_when_it_cannot_read_them(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """Empty and unmeasured are different answers.

    Without the distinction a revision whose evidence document had gone missing would report every
    blob in the shared store as unreferenced — a claim nobody computed, about files no command is
    allowed to remove anyway.
    """
    (promoted_tree.revision_dir / "evidence" / "records.yaml").unlink()
    report = inventory(promoted_tree.bundle_root).value
    assert report is not None
    assert report.referenced_blobs == ()
    assert report.unreferenced_blobs == ()


def test_inventory_parses_the_private_sidecar_and_reports_a_dead_mapping(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """A mapping to a source the revision does not declare is dead config: the owner cannot reopen
    the original through it, and nothing else in the bundle will ever mention it."""
    local_sources_path(promoted_tree.bundle_root).write_text(
        "'source.not-in-this-revision': '/tmp/originals'\n", encoding="utf-8"
    )
    outcome = inventory(promoted_tree.bundle_root)
    assert outcome.exit_code == 1
    assert str(IssueCode.BROKEN_REFERENCE) in {d.code for d in outcome.diagnostics}
    report = outcome.value
    assert report is not None
    assert report.local_sources is not None


def test_inventory_reports_an_unparseable_sidecar(promoted_tree: PromotedRevisionTree) -> None:
    local_sources_path(promoted_tree.bundle_root).write_text("[not, a, mapping]\n", encoding="utf-8")
    outcome = inventory(promoted_tree.bundle_root)
    assert outcome.exit_code == 1
    report = outcome.value
    assert report is not None
    assert report.local_sources is None


def test_inventory_reads_the_pointer_exactly_once(
    promoted_tree: PromotedRevisionTree, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.profile_bundle.test_profile_bundle_storage import _count_pointer_reads

    calls = _count_pointer_reads(monkeypatch)
    report = inventory(promoted_tree.bundle_root).value
    assert calls == [1]
    assert report is not None
    assert report.selected is not None
    assert report.selected.bundle_digest == promoted_tree.bundle_digest


# --------------------------------------------------------------------------------------
# inspect
# --------------------------------------------------------------------------------------


def test_inspect_reports_a_record_with_its_owning_file_and_kind(
    promoted_tree: PromotedRevisionTree,
) -> None:
    before = _snapshot(promoted_tree.bundle_root)
    outcome = inspect_record(promoted_tree.bundle_root, FACT_ID)
    assert outcome.category == "clean", outcome.diagnostics
    report = outcome.value
    assert report is not None
    assert report.record_id == FACT_ID
    assert report.kind == "fact"
    assert report.path == "facts/projects/project.packet-pantry.yaml"
    assert report.revision == promoted_tree.revision
    assert report.bundle_digest == promoted_tree.bundle_digest
    assert report.evidence_ids
    assert _snapshot(promoted_tree.bundle_root) == before


def test_inspect_reports_the_conflicts_a_record_is_contested_by(
    promoted_tree: PromotedRevisionTree,
) -> None:
    report = inspect_record(promoted_tree.bundle_root, FACT_ID).value
    assert report is not None
    assert CONFLICT_ID in report.conflict_ids


def test_inspect_refuses_an_unknown_record(promoted_tree: PromotedRevisionTree) -> None:
    outcome = inspect_record(promoted_tree.bundle_root, "fact.nothing.here")
    assert outcome.exit_code == 1
    assert [d.code for d in outcome.diagnostics] == [str(IssueCode.RECORD_NOT_FOUND)]
    assert outcome.value is None


def test_inspect_without_a_promoted_revision_refuses(tmp_path: Path) -> None:
    root = tmp_path / "career-profile"
    assert init_draft(root, name="initial").category == "clean"
    outcome = inspect_record(root, FACT_ID)
    assert outcome.exit_code == 1
    assert [d.code for d in outcome.diagnostics] == [str(IssueCode.NO_CURRENT_REVISION)]


def test_inspect_reads_the_pointer_exactly_once(
    promoted_tree: PromotedRevisionTree, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.profile_bundle.test_profile_bundle_storage import _count_pointer_reads

    calls = _count_pointer_reads(monkeypatch)
    report = inspect_record(promoted_tree.bundle_root, FACT_ID).value
    assert calls == [1]
    assert report is not None
    assert report.bundle_digest == promoted_tree.bundle_digest


# --------------------------------------------------------------------------------------
# conflicts
# --------------------------------------------------------------------------------------


def test_conflicts_lists_every_group_and_names_the_unresolved_ones(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """A bundle may validly preserve uncertainty (§20.5), so an unresolved group is data this
    command reports, never a finding it fails on."""
    before = _snapshot(promoted_tree.bundle_root)
    outcome = conflicts_report(promoted_tree.bundle_root)
    assert outcome.category == "clean", outcome.diagnostics
    report = outcome.value
    assert report is not None
    assert all(isinstance(conflict, ConflictRecord) for conflict in report.conflicts)
    assert CONFLICT_ID in report.unresolved_ids
    assert {conflict.conflict_id for conflict in report.conflicts} > report.unresolved_ids
    assert _snapshot(promoted_tree.bundle_root) == before


def test_conflicts_reports_the_revision_it_read(promoted_tree: PromotedRevisionTree) -> None:
    report = conflicts_report(promoted_tree.bundle_root).value
    assert report is not None
    assert report.revision == promoted_tree.revision
    assert report.bundle_digest == promoted_tree.bundle_digest


def test_conflicts_without_a_promoted_revision_refuses(tmp_path: Path) -> None:
    root = tmp_path / "career-profile"
    assert init_draft(root, name="initial").category == "clean"
    outcome = conflicts_report(root)
    assert outcome.exit_code == 1
    assert [d.code for d in outcome.diagnostics] == [str(IssueCode.NO_CURRENT_REVISION)]


def test_conflicts_reads_the_pointer_exactly_once(
    promoted_tree: PromotedRevisionTree, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.profile_bundle.test_profile_bundle_storage import _count_pointer_reads

    calls = _count_pointer_reads(monkeypatch)
    report = conflicts_report(promoted_tree.bundle_root).value
    assert calls == [1]
    assert report is not None
    assert report.bundle_digest == promoted_tree.bundle_digest


# --------------------------------------------------------------------------------------
# no command adopts anything
# --------------------------------------------------------------------------------------


def test_no_read_command_adopts_a_leftover_directory(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """§6: `inventory` never adopts an unselected or incomplete directory, and §21 forbids deleting
    one. `CURRENT` must therefore be byte-identical after all three commands have run."""
    leftover = revisions_dir(promoted_tree.bundle_root) / digest_token("sha256:" + "d" * 64)
    leftover.mkdir()
    complete_marker_path(leftover).write_text("sha256:" + "d" * 64 + "\n", encoding="utf-8")
    (blobs_dir(promoted_tree.bundle_root) / "not-a-digest").write_bytes(b"x")
    drafts_dir(promoted_tree.bundle_root).mkdir(exist_ok=True)
    pointer = current_path(promoted_tree.bundle_root).read_bytes()
    before = _snapshot(promoted_tree.bundle_root)

    inventory(promoted_tree.bundle_root)
    inspect_record(promoted_tree.bundle_root, FACT_ID)
    conflicts_report(promoted_tree.bundle_root)

    assert current_path(promoted_tree.bundle_root).read_bytes() == pointer
    assert json.loads(pointer)["bundle_digest"] == promoted_tree.bundle_digest
    assert _snapshot(promoted_tree.bundle_root) == before
