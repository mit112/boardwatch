"""`init` and `checkout`: the two ways a writable draft comes into existence (design §6, §19).

The two commands share a shape — produce `drafts/<name>/` or refuse without writing — and differ in
everything else. `init` authors an empty revision-1 draft with no parent at all; `checkout` copies
one immutable revision and records which one it came from. The tests below keep those apart, because
the fields that distinguish them (`draft_of_revision`, `parent_bundle_digest`) are exactly the ones
promotion later re-checks against `CURRENT`.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path, PurePosixPath

import pytest

from boardwatch.profile_bundle import secret_scan
from boardwatch.profile_bundle.canonical import (
    MappingBlobReader,
    evidence_set_digest,
    referenced_blob_digests,
)
from boardwatch.profile_bundle.drafts import checkout_current, init_draft
from boardwatch.profile_bundle.errors import BundleLayoutError, IssueCode
from boardwatch.profile_bundle.layout import (
    DocumentKind,
    discover_source_files,
    missing_fixed_documents,
    owner_for_path,
)
from boardwatch.profile_bundle.models.manifests import DraftManifest
from boardwatch.profile_bundle.models.policy import SecretRuleset
from boardwatch.profile_bundle.models.sidecars import EMPTY_SIDECAR, LocalSourcesSidecar
from boardwatch.profile_bundle.paths import (
    COMPLETE_FILE,
    LOCAL_SOURCES_FILE,
    approvals_dir,
    blob_path,
    blobs_dir,
    complete_marker_path,
    draft_root,
    drafts_dir,
    local_sources_path,
    revisions_dir,
)
from boardwatch.profile_bundle.validation import load_documents, validate_bundle
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from tests.profile_bundle.conftest import BLOB_SHA256, PromotedRevisionTree

IDENTITY = PurePosixPath("facts/identity.yaml")


def _tree_snapshot(root: Path) -> dict[str, bytes]:
    """Every file under `root`, by relative path. Used to prove a command wrote nothing."""
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


# --------------------------------------------------------------------------------------
# init
# --------------------------------------------------------------------------------------


def test_init_creates_the_root_skeleton_and_one_parentless_draft(tmp_path: Path) -> None:
    root = tmp_path / "career-profile"
    outcome = init_draft(root, name="initial")
    assert outcome.category == "clean", outcome.diagnostics
    handle = outcome.value
    assert handle is not None
    assert handle.root == draft_root(root, "initial")
    assert handle.draft_of_revision is None
    assert handle.parent_bundle_digest is None
    for directory in (approvals_dir(root), revisions_dir(root), drafts_dir(root), blobs_dir(root)):
        assert directory.is_dir(), directory


def test_the_initial_draft_manifest_carries_every_unset_sentinel(tmp_path: Path) -> None:
    """§19: a draft has no promotion-derived fields and declares its "not yet" explicitly."""
    root = tmp_path / "career-profile"
    handle = init_draft(root, name="initial").value
    assert handle is not None
    manifest = load_documents(handle.root, mode="draft").manifest
    assert isinstance(manifest, DraftManifest)
    assert manifest.draft_of_revision is None
    assert manifest.parent_bundle_digest is None
    assert manifest.bundle_digest == ""
    assert manifest.approved_candidate_digest == ""
    assert manifest.approval_stamp_id == ""
    assert manifest.change_id == ""


def test_the_initial_manifest_declares_the_evidence_set_its_own_documents_produce(
    tmp_path: Path,
) -> None:
    """Recomputed rather than compared to a literal: a pinned digest in the test would agree with a
    pinned digest in the writer while both disagreed with `canonical.py`."""
    root = tmp_path / "career-profile"
    handle = init_draft(root, name="initial").value
    assert handle is not None
    documents = load_documents(handle.root, mode="draft")
    assert referenced_blob_digests(documents) == ()
    assert documents.manifest.evidence_set_digest == evidence_set_digest(
        documents, MappingBlobReader({})
    )


def test_identity_is_the_one_declared_document_init_cannot_author(tmp_path: Path) -> None:
    """`IdentityDocument.person` is required, and a person's name and review dates are content only
    the owner has — this package reads no clock and invents no display name. So the empty draft is
    deliberately one file short, and the structural layer names that file as the first task."""
    root = tmp_path / "career-profile"
    handle = init_draft(root, name="initial").value
    assert handle is not None
    found = discover_source_files(handle.root, final_revision=False)
    assert missing_fixed_documents(found) == (IDENTITY,)


def test_the_initial_draft_carries_this_builds_secret_scan_ruleset(tmp_path: Path) -> None:
    """An empty ruleset would let the first revision claim a scan it never ran (§12.2)."""
    root = tmp_path / "career-profile"
    handle = init_draft(root, name="initial").value
    assert handle is not None
    documents = load_documents(handle.root, mode="draft")
    recorded = documents.get("policy/secret-scan.yaml")
    assert isinstance(recorded, SecretRuleset)
    assert secret_scan.ruleset_matches_builtin(recorded)
    assert documents.manifest.secret_scan_ruleset_version == secret_scan.CURRENT_RULESET_VERSION


def test_init_writes_an_empty_private_sidecar_outside_the_draft(tmp_path: Path) -> None:
    root = tmp_path / "career-profile"
    handle = init_draft(root, name="initial").value
    assert handle is not None
    sidecar = local_sources_path(root)
    parsed = LocalSourcesSidecar.model_validate(
        load_yaml_bytes(sidecar.read_bytes(), logical_path=PurePosixPath(LOCAL_SOURCES_FILE))
    )
    assert parsed == EMPTY_SIDECAR
    assert not (handle.root / LOCAL_SOURCES_FILE).exists()
    if os.name == "posix":
        assert stat.S_IMODE(sidecar.stat().st_mode) == 0o600


def test_init_refuses_once_a_revision_has_been_promoted(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """§19 scopes `init` to "no `CURRENT` exists"; after that, `checkout` is the only writable path,
    and a second parentless draft could be promoted as a revision 1 that replaced history."""
    before = _tree_snapshot(promoted_tree.bundle_root)
    outcome = init_draft(promoted_tree.bundle_root, name="second")
    assert outcome.exit_code == 1
    assert [d.code for d in outcome.diagnostics] == [str(IssueCode.CURRENT_ALREADY_EXISTS)]
    assert _tree_snapshot(promoted_tree.bundle_root) == before


def test_init_refuses_a_name_that_is_already_a_draft(tmp_path: Path) -> None:
    root = tmp_path / "career-profile"
    assert init_draft(root, name="initial").category == "clean"
    before = _tree_snapshot(root)
    outcome = init_draft(root, name="initial")
    assert outcome.exit_code == 1
    assert [d.code for d in outcome.diagnostics] == [str(IssueCode.DRAFT_ALREADY_EXISTS)]
    assert _tree_snapshot(root) == before


def test_the_initial_draft_reports_only_the_document_it_could_not_author(tmp_path: Path) -> None:
    """The end-to-end shape of an `init`: everything the owner still owes, and nothing else."""
    root = tmp_path / "career-profile"
    handle = init_draft(root, name="initial").value
    assert handle is not None
    report = validate_bundle(handle.root, bundle_root=root, mode="draft").value
    assert report is not None
    missing = {
        finding.path
        for finding in report.diagnostics
        if finding.code == str(IssueCode.MISSING_REQUIRED_FILE)
    }
    assert missing == {IDENTITY.as_posix()}


# --------------------------------------------------------------------------------------
# checkout
# --------------------------------------------------------------------------------------


def test_checkout_copies_every_source_document_byte_for_byte(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """Only `manifest.yaml` is rewritten; a checkout that re-emitted documents would change bytes
    the owner never edited and make the first diff after a checkout unreadable."""
    outcome = checkout_current(promoted_tree.bundle_root, name="work")
    assert outcome.category == "clean", outcome.diagnostics
    handle = outcome.value
    assert handle is not None
    for entry in discover_source_files(promoted_tree.revision_dir, final_revision=True):
        copied = handle.root / entry.logical_path
        if entry.kind is DocumentKind.MANIFEST:
            assert copied.read_bytes() != entry.abspath.read_bytes()
            continue
        assert copied.read_bytes() == entry.abspath.read_bytes(), entry.logical_path
    assert not (handle.root / COMPLETE_FILE).exists()


def test_a_checked_out_draft_names_the_revision_it_came_from(
    promoted_tree: PromotedRevisionTree,
) -> None:
    handle = checkout_current(promoted_tree.bundle_root, name="work").value
    assert handle is not None
    assert handle.draft_of_revision == promoted_tree.revision
    assert handle.parent_bundle_digest == promoted_tree.bundle_digest
    manifest = load_documents(handle.root, mode="draft").manifest
    assert isinstance(manifest, DraftManifest)
    assert manifest.draft_of_revision == promoted_tree.revision
    assert manifest.parent_bundle_digest == promoted_tree.bundle_digest
    assert manifest.bundle_digest == ""
    assert manifest.approval_stamp_id == ""


def test_a_checked_out_draft_validates_as_a_draft(promoted_tree: PromotedRevisionTree) -> None:
    """The whole point of a checkout: what comes out is editable and already valid."""
    handle = checkout_current(promoted_tree.bundle_root, name="work").value
    assert handle is not None
    outcome = validate_bundle(handle.root, bundle_root=promoted_tree.bundle_root, mode="draft")
    assert outcome.category == "clean", outcome.diagnostics


def test_the_private_sidecar_cannot_reach_a_draft(promoted_tree: PromotedRevisionTree) -> None:
    """§6 says `checkout` never copies `local-sources.yaml`, and it cannot: the file lives at the
    bundle ROOT and the closed logical grammar refuses it inside any tree, so there is no filter to
    write here. This test names where that guarantee actually lands (D-115)."""
    local_sources_path(promoted_tree.bundle_root).write_text("{}\n", encoding="utf-8")
    handle = checkout_current(promoted_tree.bundle_root, name="work").value
    assert handle is not None
    assert not (handle.root / LOCAL_SOURCES_FILE).exists()
    with pytest.raises(BundleLayoutError):
        owner_for_path(PurePosixPath(LOCAL_SOURCES_FILE))


def test_checkout_reports_a_corrupt_blob_and_still_produces_the_draft(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """§6's one recovery exception: the source YAML is parseable, so the owner must be able to check
    it out, recapture the evidence, and promote a replacement."""
    blob_path(promoted_tree.bundle_root, BLOB_SHA256).write_bytes(b"tampered")
    outcome = checkout_current(promoted_tree.bundle_root, name="work")
    assert outcome.exit_code == 1
    assert [d.code for d in outcome.diagnostics] == [str(IssueCode.CORRUPT_BLOB_QUARANTINE)]
    assert outcome.diagnostics[0].details["reason"] == "digest_mismatch"
    handle = outcome.value
    assert handle is not None
    assert (handle.root / "evidence" / "records.yaml").exists()
    assert handle.parent_bundle_digest == promoted_tree.bundle_digest


def test_checkout_reports_a_missing_blob_and_still_produces_the_draft(
    promoted_tree: PromotedRevisionTree,
) -> None:
    blob_path(promoted_tree.bundle_root, BLOB_SHA256).unlink()
    outcome = checkout_current(promoted_tree.bundle_root, name="work")
    assert outcome.exit_code == 1
    assert [d.code for d in outcome.diagnostics] == [str(IssueCode.CORRUPT_BLOB_QUARANTINE)]
    assert outcome.diagnostics[0].details["reason"] == "missing"
    handle = outcome.value
    assert handle is not None
    assert handle.parent_bundle_digest == promoted_tree.bundle_digest


def test_checkout_never_reads_another_draft(promoted_tree: PromotedRevisionTree) -> None:
    """A draft is the one place in the bundle that can hold anything at all, so a command that
    walked `drafts/` would break on somebody else's work in progress."""
    noisy = draft_root(promoted_tree.bundle_root, "someone-elses")
    (noisy / "policy").mkdir(parents=True)
    (noisy / "policy" / "persona.yaml").write_text("not: [a, declared, file\n", encoding="utf-8")
    (noisy / "manifest.yaml").write_text("*** not yaml ***\n", encoding="utf-8")
    outcome = checkout_current(promoted_tree.bundle_root, name="work")
    assert outcome.category == "clean", outcome.diagnostics


def test_checkout_writes_nothing_into_revisions(promoted_tree: PromotedRevisionTree) -> None:
    before = _tree_snapshot(revisions_dir(promoted_tree.bundle_root))
    assert checkout_current(promoted_tree.bundle_root, name="work").category == "clean"
    assert _tree_snapshot(revisions_dir(promoted_tree.bundle_root)) == before


def test_checkout_refuses_a_name_that_is_already_a_draft(
    promoted_tree: PromotedRevisionTree,
) -> None:
    assert checkout_current(promoted_tree.bundle_root, name="work").category == "clean"
    before = _tree_snapshot(promoted_tree.bundle_root)
    outcome = checkout_current(promoted_tree.bundle_root, name="work")
    assert outcome.exit_code == 1
    assert [d.code for d in outcome.diagnostics] == [str(IssueCode.DRAFT_ALREADY_EXISTS)]
    assert _tree_snapshot(promoted_tree.bundle_root) == before


def test_checkout_without_a_promoted_revision_refuses(tmp_path: Path) -> None:
    root = tmp_path / "career-profile"
    assert init_draft(root, name="initial").category == "clean"
    outcome = checkout_current(root, name="work")
    assert outcome.exit_code == 1
    assert [d.code for d in outcome.diagnostics] == [str(IssueCode.NO_CURRENT_REVISION)]


def test_checkout_from_a_torn_revision_refuses(promoted_tree: PromotedRevisionTree) -> None:
    complete_marker_path(promoted_tree.revision_dir).unlink()
    outcome = checkout_current(promoted_tree.bundle_root, name="work")
    assert outcome.exit_code == 1
    assert [d.code for d in outcome.diagnostics] == [str(IssueCode.COMPLETE_MARKER_MISSING)]
    assert not draft_root(promoted_tree.bundle_root, "work").exists()


def test_checkout_reads_the_pointer_exactly_once(
    promoted_tree: PromotedRevisionTree, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.profile_bundle.test_profile_bundle_storage import _count_pointer_reads

    calls = _count_pointer_reads(monkeypatch)
    handle = checkout_current(promoted_tree.bundle_root, name="work").value
    assert calls == [1]
    assert handle is not None
    assert handle.parent_bundle_digest == promoted_tree.bundle_digest
