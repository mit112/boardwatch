"""`init` and `checkout`: the two ways a writable draft comes into existence (design §6, §19).

The two commands share a shape — produce `drafts/<name>/` or refuse without writing — and differ in
everything else. `init` authors an empty revision-1 draft with no parent at all; `checkout` copies
one immutable revision and records which one it came from. The tests below keep those apart, because
the fields that distinguish them (`draft_of_revision`, `parent_bundle_digest`) are exactly the ones
promotion later re-checks against `CURRENT`.
"""

from __future__ import annotations

import errno
import json
import os
import stat
from pathlib import Path, PurePosixPath
from typing import Any

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
    current_path,
    digest_token,
    draft_root,
    drafts_dir,
    local_sources_path,
    revisions_dir,
)
from boardwatch.profile_bundle.validation import load_documents, validate_bundle
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from tests.profile_bundle.conftest import BLOB_SHA256, PromotedRevisionTree, quoted_yaml

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


def test_a_failed_sidecar_write_leaves_nothing_for_the_retry_to_trip_over(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`init` may leave the skeleton behind, but only whole files.

    A plain write interrupted halfway leaves a truncated `local-sources.yaml`; `inventory` reports an
    unparseable sidecar as an error, and the retry skips an existing one, so the corrupt file would
    outlive every attempt to fix it by re-running the command.
    """
    root = tmp_path / "career-profile"
    real = os.replace

    def failing(src: Any, dst: Any, **kwargs: Any) -> None:
        if Path(dst).name == LOCAL_SOURCES_FILE:
            raise OSError(errno.ENOSPC, "No space left on device")
        real(src, dst, **kwargs)

    monkeypatch.setattr(os, "replace", failing)
    outcome = init_draft(root, name="initial")
    assert outcome.exit_code == 3
    assert [d.code for d in outcome.diagnostics] == [str(IssueCode.IO_ERROR)]
    assert not local_sources_path(root).exists()
    assert [entry.name for entry in root.iterdir() if entry.name.startswith(".tmp-")] == []

    monkeypatch.undo()
    assert init_draft(root, name="initial").category == "clean"
    assert LocalSourcesSidecar.model_validate(
        load_yaml_bytes(
            local_sources_path(root).read_bytes(), logical_path=PurePosixPath(LOCAL_SOURCES_FILE)
        )
    ) == EMPTY_SIDECAR


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


def test_checkout_refuses_a_revision_that_is_not_the_one_selected(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """A draft records its parent digest from the pointer, so a tree whose manifest says something
    else must not become one: promotion would refuse the result with nothing to explain it."""
    other = "sha256:" + "e" * 64
    stolen = revisions_dir(promoted_tree.bundle_root) / digest_token(other)
    promoted_tree.revision_dir.rename(stolen)
    complete_marker_path(stolen).write_text(f"{other}\n", encoding="utf-8")
    current_path(promoted_tree.bundle_root).write_text(
        json.dumps({"bundle_digest": other, "revision": 1}, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    outcome = checkout_current(promoted_tree.bundle_root, name="work")
    assert outcome.exit_code == 1
    assert [d.code for d in outcome.diagnostics] == [str(IssueCode.CURRENT_POINTER_MISMATCH)]
    assert not draft_root(promoted_tree.bundle_root, "work").exists()


def test_checkout_that_cannot_read_a_blob_installs_no_draft(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """§21's exit 3 means the check could not run at all, so it must not also leave a draft behind.

    A blob that is missing or fails its digest is §6's recovery path and still produces a draft; a
    blob whose bytes could not be read at all is not a state anyone can recover from by editing the
    draft, and a caller retrying on exit 3 would otherwise be met with `draft_already_exists`.

    Unreadable by permission rather than by kind: a store entry that is not a regular file is now
    refused by confinement before any command opens it, so a directory here would pin that refusal
    instead of this one.
    """
    stored = blob_path(promoted_tree.bundle_root, BLOB_SHA256)
    before = _tree_snapshot(promoted_tree.bundle_root)
    original_mode = stored.stat().st_mode
    stored.chmod(0o000)
    try:
        outcome = checkout_current(promoted_tree.bundle_root, name="work")
    finally:
        stored.chmod(original_mode)
    assert outcome.exit_code == 3
    assert [d.code for d in outcome.diagnostics] == [str(IssueCode.IO_ERROR)]
    assert outcome.value is None
    assert not draft_root(promoted_tree.bundle_root, "work").exists()
    assert _tree_snapshot(promoted_tree.bundle_root) == before


def test_checkout_reports_a_future_schema_version_the_way_validate_does(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """A bundle this build is too old to read is not a small problem with the draft name.

    `validation.context.parse_error_diagnostics` is already the load-failure to `IssueCode` mapping,
    and it has an arm for exactly this so an operator upgrades Boardwatch instead of filing a bug.
    """
    _edit_revision(promoted_tree, "manifest.yaml", lambda data: data.update({"schema_version": 99}))
    outcome = checkout_current(promoted_tree.bundle_root, name="work")
    control = validate_bundle(
        promoted_tree.revision_dir, bundle_root=promoted_tree.bundle_root, mode="revision"
    )
    assert [d.code for d in outcome.diagnostics] == [d.code for d in control.diagnostics]
    assert [d.code for d in outcome.diagnostics] == [str(IssueCode.UNSUPPORTED_SCHEMA_VERSION)]
    assert outcome.exit_code == control.exit_code == 3


def test_checkout_reports_every_model_error_the_control_reports(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """`BundleParseError` carries one finding per broken field; collapsing them into one code
    throws away the list the operator has to work through."""
    (promoted_tree.revision_dir / "skills" / "inventory.yaml").write_text(
        "'skills':\n- 'nope': 'x'\n", encoding="utf-8"
    )
    outcome = checkout_current(promoted_tree.bundle_root, name="work")
    control = validate_bundle(
        promoted_tree.revision_dir, bundle_root=promoted_tree.bundle_root, mode="revision"
    )
    assert [d.code for d in outcome.diagnostics] == [d.code for d in control.diagnostics]
    assert {d.code for d in outcome.diagnostics} == {str(IssueCode.MODEL_VALIDATION_ERROR)}
    assert outcome.exit_code == control.exit_code == 1
    assert not draft_root(promoted_tree.bundle_root, "work").exists()


def test_checkout_of_a_revision_whose_evidence_document_is_gone_names_the_missing_file(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """`internal_error` is "file a bug"; a declared document that is merely absent is not that.

    Canonicalising the parent's evidence set is not a load, so `parse_error_diagnostics` has no arm
    for its failure: routing it through that mapping reported `internal_error` at exit 3 for a tree
    the control and `inventory` both report as a missing required file at exit 1.
    """
    (promoted_tree.revision_dir / "evidence" / "records.yaml").unlink()
    outcome = checkout_current(promoted_tree.bundle_root, name="work")
    control = validate_bundle(
        promoted_tree.revision_dir, bundle_root=promoted_tree.bundle_root, mode="revision"
    )
    assert str(IssueCode.MISSING_REQUIRED_FILE) in {d.code for d in control.diagnostics}
    assert [d.code for d in outcome.diagnostics] == [str(IssueCode.MISSING_REQUIRED_FILE)]
    assert [d.path for d in outcome.diagnostics] == ["evidence/records.yaml"]
    assert outcome.exit_code == control.exit_code == 1
    assert not draft_root(promoted_tree.bundle_root, "work").exists()


def test_no_draft_command_names_an_absolute_path_in_a_diagnostic(tmp_path: Path) -> None:
    """§19 renders diagnostics as JSON an operator may paste elsewhere, and every pre-T14 diagnostic
    in this package uses logical paths. A stringified `OSError` carries an absolute one."""
    root = tmp_path / "career-profile"
    outcomes = [
        checkout_current(root, name="work"),
        init_draft(root, name="initial"),
        init_draft(root, name="initial"),
        init_draft(root, name="second"),
    ]
    blocked = tmp_path / "blocked-bundle"
    blocked.mkdir()
    drafts_dir(blocked).write_text("not a directory\n", encoding="utf-8")
    outcomes.append(init_draft(blocked, name="initial"))
    assert outcomes[-1].exit_code == 3

    for outcome in outcomes:
        for finding in outcome.diagnostics:
            assert str(tmp_path) not in finding.message, finding


def test_a_symlinked_declared_member_stops_init_from_writing_outside_the_root(
    tmp_path: Path,
) -> None:
    """Confinement is checked over the whole root grammar, so `init` cannot populate a `drafts/`
    that is really somewhere else."""
    root = tmp_path / "career-profile"
    root.mkdir()
    outside = tmp_path / "outside-drafts"
    outside.mkdir()
    drafts_dir(root).symlink_to(outside, target_is_directory=True)

    outcome = init_draft(root, name="initial")
    assert outcome.exit_code == 1
    assert [d.code for d in outcome.diagnostics] == [str(IssueCode.SYMLINK_REFUSED)]
    assert list(outside.iterdir()) == []


def test_a_symlinked_declared_member_is_refused_before_the_draft_name_is_examined(
    promoted_tree: PromotedRevisionTree, tmp_path: Path
) -> None:
    """The reason reported must be the one that matters: a draft name colliding with something
    outside the bundle is not a name collision, it is a bundle that is not self-contained."""
    outside = tmp_path / "outside-drafts"
    drafts_dir(promoted_tree.bundle_root).mkdir(parents=True, exist_ok=True)
    drafts_dir(promoted_tree.bundle_root).rename(outside)
    (outside / "work").mkdir()
    drafts_dir(promoted_tree.bundle_root).symlink_to(outside, target_is_directory=True)

    outcome = checkout_current(promoted_tree.bundle_root, name="work")
    assert [d.code for d in outcome.diagnostics] == [str(IssueCode.SYMLINK_REFUSED)]


def _edit_revision(tree: PromotedRevisionTree, relative: str, mutate: Any) -> None:
    path = tree.revision_dir / relative
    logical = PurePosixPath(relative)
    data = load_yaml_bytes(path.read_bytes(), logical_path=logical)
    mutate(data)
    path.write_bytes(quoted_yaml(data, logical_path=logical))


def test_checkout_reads_the_pointer_exactly_once(
    promoted_tree: PromotedRevisionTree, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.profile_bundle.test_profile_bundle_storage import _count_pointer_reads

    calls = _count_pointer_reads(monkeypatch)
    handle = checkout_current(promoted_tree.bundle_root, name="work").value
    assert calls == [1]
    assert handle is not None
    assert handle.parent_bundle_digest == promoted_tree.bundle_digest
