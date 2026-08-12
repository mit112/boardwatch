"""T13 digest validation (design §20.6).

Digest validation is the layer that makes every other layer's guarantee durable: a revision whose
bytes changed after promotion is unusable no matter how cleanly it once validated. Three properties
carry these tests.

- **The positive path must actually run.** Every test here works against a genuinely promoted tree
  built by `promote_example_tree`, whose directory name, `COMPLETE`, manifest and `CURRENT` all
  agree because the fixture reproduced promotion's digest order. A fixture with placeholder digests
  would report a mismatch everywhere and the clean case would never be exercised.
- **Each disagreement is reported under its own code.** The four artifacts that must agree can
  disagree in four different ways, and folding them into one code would leave an operator unable to
  tell "the directory was renamed" from "the manifest was edited".
- **The evidence-set digest needs its own comparison.** `canonical._manifest_with` overwrites the
  declared `evidence_set_digest` with the recomputed one before hashing the manifest leaf, so a
  forged value provably does not move `bundle_digest`. That independence is asserted directly,
  because it is the reason this check cannot be left implicit.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

from boardwatch.profile_bundle.errors import Diagnostic, IssueCode
from boardwatch.profile_bundle.index import build_index
from boardwatch.profile_bundle.models.manifests import RevisionManifest
from boardwatch.profile_bundle.paths import (
    complete_marker_path,
    current_path,
    revision_root,
)
from boardwatch.profile_bundle.validation import (
    ParentSnapshot,
    build_context,
    load_documents,
)
from boardwatch.profile_bundle.validation.digest import (
    CurrentPointer,
    PointerError,
    current_pointer_bytes,
    read_complete,
    read_current,
    validate_digest,
)
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from tests.profile_bundle.conftest import (
    PromotedRevisionTree,
    SyntheticBundle,
    blob_reader,
    quoted_yaml,
    reseal_without_reapproval,
)


def findings(tree: PromotedRevisionTree) -> tuple[Diagnostic, ...]:
    ctx = build_context(
        tree.revision_dir,
        mode="revision",
        blobs=blob_reader(),
        bundle_root=tree.bundle_root,
    )
    return validate_digest(ctx)


def codes(tree: PromotedRevisionTree) -> list[str]:
    return sorted(finding.code for finding in findings(tree))


def edit_revision(tree: PromotedRevisionTree, relative: str, mutate: Any) -> None:
    """Apply `mutate` to one document of the promoted tree, in place.

    Deliberately not `edit_document`: its dumper emits plain scalars, and the promotion documents
    contain `2026-08-10T12:00:00Z`, which the restricted loader then refuses on the way back in. A
    negative test whose setup makes the tree unparseable proves nothing about the layer, so this
    reuses the same quoting writer the fixture used.
    """
    path = tree.revision_dir / relative
    data = load_yaml_bytes(path.read_bytes(), logical_path=PurePosixPath(relative))
    mutate(data)
    path.write_bytes(quoted_yaml(data, logical_path=PurePosixPath(relative)))


# --------------------------------------------------------------------------------------
# The clean case
# --------------------------------------------------------------------------------------


def test_a_genuinely_promoted_revision_reports_nothing(promoted_tree: PromotedRevisionTree) -> None:
    """If this fails, every negative test below is meaningless: they would all be passing on a
    fixture that was already broken rather than on the mutation each one makes."""
    assert findings(promoted_tree) == ()


def test_the_four_artifacts_agree_in_the_fixture(promoted_tree: PromotedRevisionTree) -> None:
    """Stated as a property of the fixture, not of the layer, so a fixture regression is visible as
    a fixture failure instead of as a mysterious validation pass."""
    manifest = promoted_tree.documents.manifest
    assert promoted_tree.revision_dir.name == "sha256-" + promoted_tree.bundle_digest.removeprefix(
        "sha256:"
    )
    assert read_complete(promoted_tree.revision_dir) == promoted_tree.bundle_digest
    assert read_current(promoted_tree.bundle_root) == CurrentPointer(
        bundle_digest=promoted_tree.bundle_digest, revision=promoted_tree.revision
    )
    assert manifest.bundle_digest == promoted_tree.bundle_digest  # type: ignore[union-attr]


# --------------------------------------------------------------------------------------
# The bundle digest
# --------------------------------------------------------------------------------------


def test_a_document_edited_after_promotion_is_a_digest_mismatch(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """§21: "Evidence or revision mutated after promotion | Digest failure; revision unusable"."""

    def retitle(data: Any) -> None:
        data["skills"][0]["canonical_name"] = "Edited After Promotion"

    edit_revision(promoted_tree, "skills/inventory.yaml", retitle)
    assert IssueCode.BUNDLE_DIGEST_MISMATCH in codes(promoted_tree)


def test_reserialising_a_document_without_changing_its_content_is_not_a_mismatch(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """The digest is over logical content, not bytes (§20.6's last clause).

    `edit_document` rewrites the whole file through a different serialiser than the one that
    produced it, so a no-op mutation still changes the bytes on disk. If that moved the digest, the
    bundle could not survive any reformatting — including the one its own writer performs.
    """
    edit_revision(promoted_tree, "skills/inventory.yaml", lambda data: None)
    assert findings(promoted_tree) == ()


# --------------------------------------------------------------------------------------
# The evidence-set digest, which cannot ride on the bundle digest
# --------------------------------------------------------------------------------------


def test_a_forged_evidence_set_digest_is_reported(promoted_tree: PromotedRevisionTree) -> None:
    def forge(data: Any) -> None:
        data["evidence_set_digest"] = "sha256:" + "f" * 64

    edit_revision(promoted_tree, "manifest.yaml", forge)
    assert IssueCode.EVIDENCE_SET_DIGEST_MISMATCH in codes(promoted_tree)


def test_a_forged_evidence_set_digest_does_not_move_the_bundle_digest(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """The independence that makes the check above load-bearing.

    `_manifest_with` overwrites `evidence_set_digest` with the recomputed value before hashing the
    manifest leaf. So the forged value provably cannot be caught by the bundle-digest comparison,
    and without its own check it could never be detected at all.
    """

    def forge(data: Any) -> None:
        data["evidence_set_digest"] = "sha256:" + "f" * 64

    edit_revision(promoted_tree, "manifest.yaml", forge)
    assert IssueCode.BUNDLE_DIGEST_MISMATCH not in codes(promoted_tree)


# --------------------------------------------------------------------------------------
# Directory name, COMPLETE, and CURRENT
# --------------------------------------------------------------------------------------


def test_a_revision_directory_named_for_another_digest_is_reported(
    promoted_tree: PromotedRevisionTree,
) -> None:
    moved = revision_root(promoted_tree.bundle_root, "sha256:" + "b" * 64)
    promoted_tree.revision_dir.rename(moved)
    ctx = build_context(
        moved, mode="revision", blobs=blob_reader(), bundle_root=promoted_tree.bundle_root
    )
    assert IssueCode.MANIFEST_DIRECTORY_MISMATCH in sorted(
        finding.code for finding in validate_digest(ctx)
    )


def test_a_missing_complete_marker_is_reported(promoted_tree: PromotedRevisionTree) -> None:
    complete_marker_path(promoted_tree.revision_dir).unlink()
    assert IssueCode.COMPLETE_MARKER_MISSING in codes(promoted_tree)


@pytest.mark.parametrize(
    "content",
    ["", "\n", "not-a-digest\n", "sha256:" + "a" * 63 + "\n", "sha256:" + "a" * 64],
)
def test_a_complete_marker_that_is_not_the_exact_contract_is_reported(
    promoted_tree: PromotedRevisionTree, content: str
) -> None:
    """`COMPLETE` is exactly `sha256:<64hex>` and one newline.

    The last case has the right digest shape and no trailing newline. It is included deliberately:
    a reader that strips before matching would accept a torn write that stopped mid-flush, and the
    marker exists precisely to distinguish a finished promotion from an interrupted one.
    """
    complete_marker_path(promoted_tree.revision_dir).write_bytes(
        (content).encode("utf-8")
    )
    assert IssueCode.COMPLETE_MARKER_MISSING in codes(promoted_tree)


def test_a_complete_marker_naming_another_digest_is_a_directory_mismatch(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """Present but disagreeing is a different fact from absent, so it gets a different code."""
    complete_marker_path(promoted_tree.revision_dir).write_bytes(
        ("sha256:" + "c" * 64 + "\n").encode("utf-8")
    )
    found = codes(promoted_tree)
    assert IssueCode.MANIFEST_DIRECTORY_MISMATCH in found
    assert IssueCode.COMPLETE_MARKER_MISSING not in found


def _write_pointer(bundle_root: Path, digest: str, revision: int) -> None:
    """Write a pointer through the emitter that owns its byte form.

    Hand-rolled JSON would be refused as non-canonical now that `CURRENT` has a writer, and these
    tests are about which revision the pointer NAMES — a pointer refused for its punctuation would
    let them pass while measuring something else entirely.
    """
    current_path(bundle_root).write_bytes(
        current_pointer_bytes(CurrentPointer(bundle_digest=digest, revision=revision))
    )


def test_a_current_pointer_naming_another_digest_is_reported(
    promoted_tree: PromotedRevisionTree,
) -> None:
    _write_pointer(promoted_tree.bundle_root, "sha256:" + "d" * 64, 1)
    assert IssueCode.CURRENT_POINTER_MISMATCH in codes(promoted_tree)


def test_a_current_pointer_naming_another_revision_number_is_reported(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """The digest agreeing is not enough: `CURRENT.revision` is what `promote` increments, and a
    pointer that names the right tree under the wrong number makes the next revision collide."""
    _write_pointer(promoted_tree.bundle_root, promoted_tree.bundle_digest, 7)
    assert IssueCode.CURRENT_POINTER_MISMATCH in codes(promoted_tree)


def test_a_revision_that_is_not_the_selected_one_is_not_a_pointer_mismatch(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """`CURRENT` names one revision; the others are retained, not wrong.

    §21 forbids deleting unselected digest directories, so validating one of them must not report
    that it is not current — that would make "inspect an older revision" permanently red. The
    pointer here disagrees on BOTH the digest and the number, which is what a later revision being
    selected looks like.
    """
    _write_pointer(promoted_tree.bundle_root, "sha256:" + "9" * 64, 2)
    assert IssueCode.CURRENT_POINTER_MISMATCH not in codes(promoted_tree)


def test_a_tree_with_no_bundle_root_skips_the_pointer_check(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """A bare tree handed in for inspection has no `CURRENT` to disagree with, and inventing a
    finding about a file that is not part of what was handed over would be a measurement nobody
    took."""
    ctx = build_context(promoted_tree.revision_dir, mode="revision", blobs=blob_reader())
    assert validate_digest(ctx) == ()


# --------------------------------------------------------------------------------------
# Manifest state, and the candidate view
# --------------------------------------------------------------------------------------


def test_a_draft_manifest_in_a_revision_tree_is_reported(synthetic_bundle: SyntheticBundle) -> None:
    """`load_documents`'s `mode` governs only whether a `COMPLETE` marker is admissible; it never
    compares `manifest.state` to the mode it was given, so nothing caught this before."""
    ctx = build_context(
        synthetic_bundle.draft,
        mode="revision",
        blobs=blob_reader(),
        bundle_root=synthetic_bundle.root,
    )
    assert IssueCode.DRAFT_MANIFEST_INVALID in sorted(
        finding.code for finding in validate_digest(ctx)
    )


def test_a_revision_manifest_in_a_draft_tree_is_reported(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """The marker is removed first, and that is the whole reachability argument for this direction.

    `discover_source_files` refuses a `COMPLETE` file in a draft tree with a layout error, so the
    only way a revision manifest reaches a draft-mode read is without one — which is exactly what
    copying a promoted tree into `drafts/` produces.
    """
    complete_marker_path(promoted_tree.revision_dir).unlink()
    ctx = build_context(
        promoted_tree.revision_dir,
        mode="draft",
        blobs=blob_reader(),
        bundle_root=promoted_tree.bundle_root,
    )
    assert IssueCode.DRAFT_MANIFEST_INVALID in sorted(
        finding.code for finding in validate_digest(ctx)
    )


def test_a_forged_approved_candidate_digest_is_reported(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """§20.6: the inverse-normalized candidate view must recompute the digest the manifest carries.

    This is what makes the owner's approval bind to content rather than to a name: the stamp
    approved a specific candidate digest, and if the promoted revision does not reduce back to it
    then what was approved is not what was promoted.
    """

    def forge(data: Any) -> None:
        data["approved_candidate_digest"] = "sha256:" + "e" * 64

    edit_revision(promoted_tree, "manifest.yaml", forge)
    assert IssueCode.CANDIDATE_DIGEST_MISMATCH in codes(promoted_tree)


def test_the_recomputed_candidate_digest_is_the_one_the_stamp_approved(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """Checked against the stamp as well as the manifest: editing both together is a forgery the
    manifest-only comparison would accept."""

    def forge(data: Any) -> None:
        data["approvals"][0]["candidate_content_digest"] = "sha256:" + "e" * 64

    edit_revision(promoted_tree, "history/approvals.yaml", forge)
    assert IssueCode.CANDIDATE_DIGEST_MISMATCH in codes(promoted_tree)


def test_a_final_change_naming_another_parent_is_reported(chained_tree: PromotedRevisionTree) -> None:
    """Only the parent digest is checked here. The final entry's revision and `change_id` are
    already `validate_history`'s findings, and reporting them twice under two codes would make an
    operator fix one and assume the other was a second problem.

    This needs revision 2. `ChangeRecord._revision_one_has_no_parent` refuses a revision-1 entry
    that names a parent at all, so at revision 1 the forgery cannot be written and the check cannot
    fire — a fixture that stopped there would have left it shipped and unexercised.
    """

    def forge(data: Any) -> None:
        data["changes"][-1]["parent_bundle_digest"] = "sha256:" + "a" * 64

    edit_revision(chained_tree, "history/changes.yaml", forge)
    assert IssueCode.CHANGE_ENTRY_MISMATCH in codes(chained_tree)


def test_a_second_revision_promoted_onto_the_first_reports_nothing(
    chained_tree: PromotedRevisionTree,
) -> None:
    """The chain's own clean case. Without it, the test above could be passing because revision 2 is
    broken rather than because the forgery was detected."""
    assert findings(chained_tree) == ()


def test_an_unselected_earlier_revision_still_validates(
    chained_tree: PromotedRevisionTree,
) -> None:
    """§21 forbids deleting unselected digest directories, so revision 1 is still on disk after
    revision 2 is selected — and validating it must not report that it is not current."""
    parent_digest = chained_tree.documents.manifest.parent_bundle_digest  # type: ignore[union-attr]
    assert parent_digest is not None
    earlier = revision_root(chained_tree.bundle_root, parent_digest)
    ctx = build_context(
        earlier, mode="revision", blobs=blob_reader(), bundle_root=chained_tree.bundle_root
    )
    assert validate_digest(ctx) == ()


# --------------------------------------------------------------------------------------
# Reading CURRENT and COMPLETE
# --------------------------------------------------------------------------------------


def test_current_is_read_as_the_exact_two_key_object(promoted_tree: PromotedRevisionTree) -> None:
    pointer = read_current(promoted_tree.bundle_root)
    assert (pointer.bundle_digest, pointer.revision) == (
        promoted_tree.bundle_digest,
        promoted_tree.revision,
    )


@pytest.mark.parametrize(
    "content",
    [
        "",
        "{}",
        "not json",
        '{"bundle_digest":"sha256:' + "a" * 64 + '"}',
        '{"revision":1}',
        '{"bundle_digest":"nope","revision":1}',
        '{"bundle_digest":"sha256:' + "a" * 64 + '","revision":0}',
        '{"bundle_digest":"sha256:' + "a" * 64 + '","revision":1,"extra":true}',
    ],
)
def test_a_current_file_outside_its_contract_is_refused(
    promoted_tree: PromotedRevisionTree, content: str
) -> None:
    """`CURRENT` is exactly `{bundle_digest, revision}`.

    The extra-key case matters most: `json.loads` accepting a superset is how a half-written pointer
    from a future format becomes a silently accepted one, and this is the file promotion replaces
    atomically as its commit point.
    """
    current_path(promoted_tree.bundle_root).write_bytes(
        (content).encode("utf-8")
    )
    with pytest.raises(PointerError):
        read_current(promoted_tree.bundle_root)


def test_a_missing_current_file_is_refused(promoted_tree: PromotedRevisionTree) -> None:
    current_path(promoted_tree.bundle_root).unlink()
    with pytest.raises(PointerError):
        read_current(promoted_tree.bundle_root)


def test_an_unreadable_current_pointer_is_reported_not_raised(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """The layer reports; it does not propagate. A validation run that raised on a corrupt pointer
    would lose every other finding it had already accumulated."""
    current_path(promoted_tree.bundle_root).write_bytes(
        b"{}"
    )
    assert IssueCode.CURRENT_POINTER_MISMATCH in codes(promoted_tree)


# --------------------------------------------------------------------------------------
# What the layer deliberately does not do
# --------------------------------------------------------------------------------------


def test_no_digest_is_reported_when_there_is_no_blob_reader(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """Every digest needs the blob bytes, so without a reader there is no measurement to report.

    Returning nothing is right and also dangerous: it makes the whole layer silent for a caller
    that forgot the reader. `test_validate_bundle_always_supplies_a_blob_reader` in the run tests is
    where that guarantee actually lands — per D-115, the check is tested where it can fire.
    """
    ctx = build_context(promoted_tree.revision_dir, mode="revision", bundle_root=promoted_tree.bundle_root)
    assert validate_digest(ctx) == ()


def test_a_missing_blob_is_left_to_the_evidence_layer(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """`validation/evidence.py` already reports a missing blob under its own specific code. Two
    codes for one missing file is noise, and the evidence layer's is the one that names it.

    What this layer does say is that it therefore made no candidate claim — an information row, not
    a second diagnosis of the cause. Without it the digest layer's whole output for a bundle whose
    blobs are gone is indistinguishable from its output for one that verified.
    """
    from boardwatch.profile_bundle.canonical import MappingBlobReader

    ctx = build_context(
        promoted_tree.revision_dir,
        mode="revision",
        blobs=MappingBlobReader({}),
        bundle_root=promoted_tree.bundle_root,
    )
    found = validate_digest(ctx)
    assert [(f.code, f.tier, f.details["reason"]) for f in found] == [
        (IssueCode.CANDIDATE_DIGEST_UNVERIFIED, "information", "not_recomputable")
    ]


def test_a_clean_child_revision_recomputes_its_candidate_digest_from_the_parent_on_disk(
    chained_tree: PromotedRevisionTree,
) -> None:
    """A child revision's candidate view folds in its parent's revision number and digest.

    Recomputing with `parent=None` yields a DIFFERENT digest, not an approximation, so a layer that
    compared it anyway would report every revision after the first as a mismatch. The resolution is
    to read the parent's stable manifest envelope from disk — the exact subset §7 and §20.6 permit
    history traversal to read — rather than to decline the comparison.
    """
    assert IssueCode.CANDIDATE_DIGEST_MISMATCH not in codes(chained_tree)


def test_a_forged_child_revision_is_reported_without_a_parent_snapshot(
    chained_tree: PromotedRevisionTree,
) -> None:
    """§20.6's binding of an approval to content, at the revision where it can actually be evaded.

    The tree is re-sealed around a document the owner never approved: the bundle digest is
    recomputed, the directory renamed, `COMPLETE` and `CURRENT` rewritten. Every other digest check
    therefore agrees with the new bytes, which is why the assertion is on the *whole* code list —
    this comparison is the only thing between the forgery and a clean report, and it must fire on
    the default path, with no caller having supplied a parent snapshot.
    """
    forged = reseal_without_reapproval(
        chained_tree,
        mutate=lambda data: data["skills"][0].update({"canonical_name": "Never Approved"}),
    )
    assert codes(forged) == [IssueCode.CANDIDATE_DIGEST_MISMATCH] * 2
    assert [finding.path for finding in findings(forged)] == [
        "manifest.yaml",
        "history/approvals.yaml",
    ]


def test_a_child_revision_makes_no_claim_when_its_parent_is_not_on_disk(
    chained_tree: PromotedRevisionTree,
) -> None:
    """§21 keeps a selected revision valid when its history is unavailable.

    So an unreadable ancestor withholds the comparison rather than failing it — restoring one old
    directory from backup must not decide whether the bundle is usable. The cause is diagnosed, as
    `unverifiable_ancestor`, by `ancestry_completeness`; reporting it twice here under a digest code
    would send an operator hunting for a second problem.

    But the withholding itself is stated, at the information tier and with the same typed fault, and
    the tree below is why: it is a forgery, and every error-tier check agrees with it. Emitting
    nothing left `candidate_digest: null` as the only trace, on the one path where
    `ancestry_completeness` does not run at all.
    """
    forged = reseal_without_reapproval(
        chained_tree,
        mutate=lambda data: data["skills"][0].update({"canonical_name": "Never Approved"}),
    )
    parent_digest = forged.documents.manifest.parent_bundle_digest  # type: ignore[union-attr]
    assert parent_digest is not None
    shutil.rmtree(revision_root(forged.bundle_root, parent_digest))
    assert codes(forged) == [IssueCode.CANDIDATE_DIGEST_UNVERIFIED]
    assert [(f.tier, f.details["reason"]) for f in findings(forged)] == [("information", "absent")]


def test_a_supplied_parent_snapshot_is_used_instead_of_the_one_on_disk(
    chained_tree: PromotedRevisionTree,
) -> None:
    """Promotion holds the parent it just validated; it must not be made to re-read it.

    Passing the snapshot has to reach the same verdict as resolving the parent from disk, or the
    promotion path and the validation path would disagree about the same tree.
    """
    parent_digest = chained_tree.documents.manifest.parent_bundle_digest  # type: ignore[union-attr]
    assert parent_digest is not None
    earlier = revision_root(chained_tree.bundle_root, parent_digest)
    parent_documents = load_documents(earlier, mode="revision")
    parent_manifest = parent_documents.manifest
    assert isinstance(parent_manifest, RevisionManifest)
    ctx = build_context(
        chained_tree.revision_dir,
        mode="revision",
        blobs=blob_reader(),
        bundle_root=chained_tree.bundle_root,
        parent=ParentSnapshot(
            root=earlier,
            documents=parent_documents,
            envelope=parent_manifest.envelope,
            index=build_index(parent_documents),
        ),
    )
    assert IssueCode.CANDIDATE_DIGEST_MISMATCH not in sorted(
        finding.code for finding in validate_digest(ctx)
    )


@pytest.mark.skipif(
    os.name != "posix" or os.geteuid() == 0,
    reason="root reads a mode-000 file, and Windows has no geteuid and no mode bits that deny "
    "a read, so the guard cannot fire either way",
)
@pytest.mark.parametrize(
    ("filename", "code"),
    [
        ("CURRENT", IssueCode.CURRENT_POINTER_MISMATCH),
        ("COMPLETE", IssueCode.COMPLETE_MARKER_MISSING),
    ],
)
def test_an_unreadable_pointer_names_the_file_and_not_the_filesystem_path(
    promoted_tree: PromotedRevisionTree, filename: str, code: str
) -> None:
    """`reports.py` states a diagnostic never carries a value like an absolute path, and this repo
    runs a generalization checker about home paths in its bytes. `str(OSError)` appends the path it
    failed on, so the reason is taken from the exception and the logical name supplies the rest."""
    path = (
        current_path(promoted_tree.bundle_root)
        if filename == "CURRENT"
        else complete_marker_path(promoted_tree.revision_dir)
    )
    path.chmod(0o000)
    try:
        found = [finding for finding in findings(promoted_tree) if finding.code == code]
        assert len(found) == 1
        assert str(promoted_tree.bundle_root) not in found[0].message
    finally:
        path.chmod(0o644)
