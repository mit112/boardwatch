"""`inventory`, `inspect`, and `conflicts`: the three read-only reports (design §6, §19, §21).

§21 is categorical — "Inventory and inspection perform no writes. No Gate A/B command deletes
revisions, blobs, evidence, conflicts, rulings, drafts, or unselected digest directories" — so every
test here that exercises a command also proves the bundle came out byte-identical. That assertion is
the point of the slice: an inventory that quietly adopted a leftover directory would be reporting a
bundle it had just changed.
"""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

import pytest

from boardwatch.profile_bundle.drafts import DRAFT_TEMP_PREFIX, init_draft
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
    revisions_dir,
)
from boardwatch.profile_bundle.validation import validate_bundle
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from tests.profile_bundle.conftest import (
    BLOB_SHA256,
    PromotedRevisionTree,
    promote_next_revision,
    quoted_yaml,
)

CANDIDATE_DIGEST = "sha256:" + "3" * 64
OTHER_DIGEST = "sha256:" + "f" * 64
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


def test_an_in_flight_blob_write_is_not_reported_as_an_artefact(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """The blob store names its own temporaries, and this reader reads that name from the store
    rather than restating it, so a capture being written is not mistaken for a stray file."""
    (blobs_dir(promoted_tree.bundle_root) / ".tmp-halfway.blob").write_bytes(b"partial")
    outcome = inventory(promoted_tree.bundle_root)
    assert outcome.diagnostics == ()


def test_inventory_reports_an_unmeasured_blob_reference_set_as_unmeasured(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """Empty and unmeasured are different answers, and the report has to be able to say which.

    Collapsed into `()`, a revision whose evidence document had gone missing reports a fully
    populated, clean-looking inventory in which the one genuinely unaccounted-for blob has
    disappeared — a claim nobody computed, about files no command is allowed to remove anyway.
    """
    orphan = "b" * 64
    blob_path(promoted_tree.bundle_root, orphan).write_bytes(b"unreferenced")
    measured = inventory(promoted_tree.bundle_root).value
    assert measured is not None
    assert measured.referenced_blobs == (BLOB_SHA256,)
    assert measured.unreferenced_blobs == (orphan,)

    (promoted_tree.revision_dir / "evidence" / "records.yaml").unlink()
    outcome = inventory(promoted_tree.bundle_root)
    report = outcome.value
    assert report is not None
    assert report.referenced_blobs is None
    assert report.unreferenced_blobs is None
    assert (str(IssueCode.MISSING_REQUIRED_FILE), "evidence/records.yaml") in {
        (d.code, d.path) for d in outcome.diagnostics
    }
    assert outcome.exit_code == 1


def test_inventory_does_not_measure_blob_references_without_a_readable_selection(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """Unmeasured is unmeasured on the route that produces it most, not only on the rarest one.

    A selection that cannot be resolved or read at all leaves no documents to take a reference set
    from, and that is the state a torn promotion, an unparseable revision and a fresh bundle are all
    in. Reporting `()` there calls every blob in the shared store unreferenced — the same
    measurement-nobody-took this field exists to avoid, on the common path instead of the rare one.
    """
    orphan = "b" * 64
    blob_path(promoted_tree.bundle_root, orphan).write_bytes(b"unreferenced")
    measured = inventory(promoted_tree.bundle_root).value
    assert measured is not None
    assert (measured.referenced_blobs, measured.unreferenced_blobs) == ((BLOB_SHA256,), (orphan,))

    complete_marker_path(promoted_tree.revision_dir).unlink()
    outcome = inventory(promoted_tree.bundle_root)
    report = outcome.value
    assert report is not None
    assert report.selected is None
    assert report.referenced_blobs is None
    assert report.unreferenced_blobs is None


def test_inventory_reports_a_dead_local_source_mapping_without_changing_its_exit_code(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """A mapping to a source the revision does not declare is dead config: the owner cannot reopen
    the original through it, and nothing else in the bundle will ever mention it.

    It is not an error, because the sidecar is machine-local, excluded from every digest and never
    exported — so an error tier would make one bundle exit 1 on this machine and 0 on the next. The
    finding names the revision it was measured against, because a mapping live for revision 1 and
    dropped by revision 2 is dead only against the selection.
    """
    local_sources_path(promoted_tree.bundle_root).write_text(
        "'source.not-in-this-revision': '/tmp/originals'\n", encoding="utf-8"
    )
    outcome = inventory(promoted_tree.bundle_root)
    assert outcome.exit_code == 0, outcome.diagnostics
    dead = [d for d in outcome.diagnostics if d.record_id == "source.not-in-this-revision"]
    assert [d.tier for d in dead] == ["information"]
    assert str(promoted_tree.revision) in dead[0].message
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


def test_inventory_refuses_a_bundle_root_that_reaches_outside_itself(
    promoted_tree: PromotedRevisionTree, tmp_path: Path
) -> None:
    """Every enumeration `inventory` performs would otherwise report content from outside the root
    as this bundle's own — and it did: 44 files under a symlinked `drafts/` were listed as drafts of
    this bundle, at information tier, exit 0."""
    outside = tmp_path / "outside-drafts"
    drafts_dir(promoted_tree.bundle_root).mkdir(parents=True, exist_ok=True)
    drafts_dir(promoted_tree.bundle_root).rename(outside)
    (outside / "not-this-bundles-draft").mkdir()
    drafts_dir(promoted_tree.bundle_root).symlink_to(outside, target_is_directory=True)

    outcome = inventory(promoted_tree.bundle_root)
    assert [d.code for d in outcome.diagnostics] == [str(IssueCode.SYMLINK_REFUSED)]
    assert outcome.value is None
    assert "member list is closed" not in outcome.diagnostics[0].message


def test_inventory_tells_an_interrupted_install_apart_from_a_file_that_does_not_belong(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """`DRAFT_TEMP_PREFIX` says `inventory` recognises an interrupted install; the prefix is read
    from the writer that produces it, exactly as the blob store's is."""
    leftover = drafts_dir(promoted_tree.bundle_root) / f"{DRAFT_TEMP_PREFIX}abc123"
    leftover.mkdir(parents=True)
    (drafts_dir(promoted_tree.bundle_root) / "NOTES.txt").write_text("mine\n", encoding="utf-8")
    before = _snapshot(promoted_tree.bundle_root)
    outcome = inventory(promoted_tree.bundle_root)
    said = {d.path: d.message for d in outcome.diagnostics}
    assert "interrupted draft installation" in said[f"drafts/{leftover.name}"]
    assert "interrupted draft installation" not in said["drafts/NOTES.txt"]
    report = outcome.value
    assert report is not None
    assert leftover.name not in report.drafts
    assert outcome.exit_code == 0
    assert _snapshot(promoted_tree.bundle_root) == before


def test_inventory_selects_nothing_when_the_manifest_identity_check_fails(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """The same corruption class as a missing `COMPLETE`, which is already pinned to
    `selected is None`: a revision whose manifest names another digest is not the selected one."""
    stolen = revisions_dir(promoted_tree.bundle_root) / digest_token(OTHER_DIGEST)
    promoted_tree.revision_dir.rename(stolen)
    complete_marker_path(stolen).write_text(f"{OTHER_DIGEST}\n", encoding="utf-8")
    current_path(promoted_tree.bundle_root).write_text(
        json.dumps({"bundle_digest": OTHER_DIGEST, "revision": promoted_tree.revision},
                   sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    outcome = inventory(promoted_tree.bundle_root)
    assert str(IssueCode.CURRENT_POINTER_MISMATCH) in {d.code for d in outcome.diagnostics}
    report = outcome.value
    assert report is not None
    assert report.selected is None


def test_inventory_selects_nothing_when_the_selected_revision_does_not_parse(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """The second shape of the same corruption class as a manifest that names another digest.

    `selected` is the field T18 renders, so naming a revision this command could not read is a claim
    it did not verify — and it takes the directory out of `unselected_revisions` at the same time,
    hiding the one directory the diagnostics are about.
    """
    (promoted_tree.revision_dir / "manifest.yaml").write_text("'state': 'revision'\n",
                                                              encoding="utf-8")
    outcome = inventory(promoted_tree.bundle_root)
    report = outcome.value
    assert report is not None
    assert report.selected is None
    assert report.complete_revisions == (digest_token(promoted_tree.bundle_digest),)
    assert report.unselected_revisions == (digest_token(promoted_tree.bundle_digest),)
    assert outcome.exit_code == 1


@pytest.mark.parametrize(
    ("relative", "content", "expected"),
    [
        ("skills/inventory.yaml", "'skills':\n- 'nope': 'x'\n", IssueCode.MODEL_VALIDATION_ERROR),
        ("facts/notes.txt", "stray\n", IssueCode.UNKNOWN_FILE),
    ],
)
def test_inventory_codes_a_load_failure_the_way_the_control_does(
    promoted_tree: PromotedRevisionTree, relative: str, content: str, expected: IssueCode
) -> None:
    """`validate_bundle` is the control: `parse_error_diagnostics` is already the one mapping from a
    typed load failure to an `IssueCode`, and a second copy here reported a grammar violation as
    "could not run at all" and seven field errors as one wrong finding."""
    (promoted_tree.revision_dir / relative).write_text(content, encoding="utf-8")
    outcome = inventory(promoted_tree.bundle_root)
    control = validate_bundle(
        promoted_tree.revision_dir, bundle_root=promoted_tree.bundle_root, mode="revision"
    )
    assert [d.code for d in outcome.diagnostics] == [d.code for d in control.diagnostics]
    assert {d.code for d in outcome.diagnostics} == {str(expected)}
    assert outcome.exit_code == control.exit_code == 1


def test_inventory_codes_a_future_schema_version_as_unsupported(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """The arm `parse_error_diagnostics` documents: without it an operator files a bug instead of
    upgrading Boardwatch."""
    manifest = promoted_tree.revision_dir / "manifest.yaml"
    logical = PurePosixPath("manifest.yaml")
    data = load_yaml_bytes(manifest.read_bytes(), logical_path=logical)
    assert isinstance(data, dict)
    data["schema_version"] = 99
    manifest.write_bytes(quoted_yaml(data, logical_path=logical))

    outcome = inventory(promoted_tree.bundle_root)
    assert [d.code for d in outcome.diagnostics] == [str(IssueCode.UNSUPPORTED_SCHEMA_VERSION)]
    assert outcome.exit_code == 3


def test_no_read_command_names_an_absolute_path_in_a_diagnostic(tmp_path: Path) -> None:
    """Every pre-T14 diagnostic in this package uses logical paths; `no_current_revision` fires on
    the most common state of all, and a machine-specific path is not deterministic JSON."""
    root = tmp_path / "career-profile"
    root.mkdir()
    local_sources_path(root).mkdir()
    unreadable = tmp_path / "unreadable-pointer"
    unreadable.mkdir()
    current_path(unreadable).mkdir()
    outcomes = [
        inventory(root),
        inspect_record(root, FACT_ID),
        conflicts_report(root),
        inventory(unreadable),
        inspect_record(unreadable, FACT_ID),
    ]
    for outcome in outcomes:
        assert outcome.diagnostics
        for finding in outcome.diagnostics:
            assert str(tmp_path) not in finding.message, finding


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
