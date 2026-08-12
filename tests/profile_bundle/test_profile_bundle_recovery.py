"""§6's one recovery exception, and everything it deliberately does not cover.

A promoted revision cites a blob. The bytes go missing, or stop hashing to the digest that names
them. §12.1 forbids moving or deleting the file, and §7 forbids editing the revision — so without an
exception the owner owns a bundle that no supported command can repair, and the only way forward
would be to abandon the bundle.

The exception is exactly one sentence wide: a parent whose **source documents still parse** keeps
its quarantine reported, skips only the checks that need the missing bytes, and may be extended by a
replacement revision that recaptures the evidence into a new blob. The recaptured revision is
whole — it validates from disk with nothing skipped — and the hole in history stays visible as an
`unverifiable_ancestor` blocker when completeness asks for it.

Everything else about a broken parent still blocks, and each of those is a test here: documents that
will not parse, a schema this build does not support, a manifest that disagrees with the directory
naming it, and a ledger whose prefix changed.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

from boardwatch.profile_bundle.blobs import BlobQuarantineReason, quarantined_blobs, write_blob
from boardwatch.profile_bundle.canonical import EVIDENCE_PATH, referenced_blob_digests
from boardwatch.profile_bundle.drafts import checkout_current
from boardwatch.profile_bundle.errors import IssueCode
from boardwatch.profile_bundle.models.history import Actor
from boardwatch.profile_bundle.models.manifests import RevisionManifest
from boardwatch.profile_bundle.paths import (
    LOCK_FILE,
    blob_path,
    current_path,
    draft_root,
)
from boardwatch.profile_bundle.promotion import PromotionRequest, promote
from boardwatch.profile_bundle.storage import read_current_once
from boardwatch.profile_bundle.validation import load_documents
from boardwatch.profile_bundle.validation.run import validate_bundle
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from tests.profile_bundle.conftest import (
    BLOB_SHA256,
    approve_draft,
    materialise,
    quoted_yaml,
)

FIRST_DRAFT = "baseline"
REPAIR_DRAFT = "repair"
MANIFEST_PATH = PurePosixPath("manifest.yaml")
PROMOTED_AT = datetime(2026, 8, 11, 9, 0, tzinfo=UTC)
AS_OF = date(2026, 8, 11)

#: The bytes the owner recaptures. A NEW blob under a NEW digest: §12.1 is explicit that the fix for
#: a corrupt capture is to restore the exact digest or to recapture, never to overwrite the file.
RECAPTURED = (
    b"# Packet Pantry baseline A (recaptured)\n\n"
    b"Recaptured after the original blob was lost. Sustained approximately 120 items/s over a\n"
    b"five minute run on a single local node with one producer.\n"
)
RECAPTURED_SHA256 = hashlib.sha256(RECAPTURED).hexdigest()


@dataclass(frozen=True)
class Scene:
    """Revision 1 promoted, and its one blob capture broken in some way."""

    bundle_root: Path
    first: Path
    first_digest: str


def _request(name: str) -> PromotionRequest:
    return PromotionRequest(
        draft_name=name,
        summary="Recapture the lost benchmark evidence",
        actor=Actor.OWNER,
        created_at=PROMOTED_AT,
    )


def _edit(root: Path, logical: PurePosixPath, mutate: Callable[[Any], None]) -> None:
    path = root / logical
    data = load_yaml_bytes(path.read_bytes(), logical_path=logical)
    mutate(data)
    path.write_bytes(quoted_yaml(data, logical_path=logical))


def _promoted_revision_one(tmp_path: Path) -> Scene:
    bundle_root = tmp_path / "career-profile"
    bundle_root.mkdir()
    bundle = materialise(bundle_root, draft_name=FIRST_DRAFT)
    approve_draft(bundle_root, bundle.draft, approved_at=PROMOTED_AT)
    outcome = promote(bundle_root, _request(FIRST_DRAFT))
    assert outcome.exit_code == 0, outcome.diagnostics
    assert outcome.value is not None
    return Scene(
        bundle_root=bundle_root,
        first=outcome.value.root,
        first_digest=outcome.value.bundle_digest,
    )


@pytest.fixture(params=[BlobQuarantineReason.MISSING, BlobQuarantineReason.DIGEST_MISMATCH])
def broken(request: pytest.FixtureRequest, tmp_path: Path) -> Scene:
    """Both halves of §6's exception: the blob is gone, or its bytes no longer hash to its name."""
    scene = _promoted_revision_one(tmp_path)
    path = blob_path(scene.bundle_root, BLOB_SHA256)
    if request.param is BlobQuarantineReason.MISSING:
        path.unlink()
    else:
        path.chmod(0o600)
        path.write_bytes(b"# these are not the bytes this digest names\n")
    return scene


def _recapture(bundle_root: Path, draft: Path) -> None:
    """What `add-evidence` will do: store new bytes and point the record at their digest."""
    write_blob(
        bundle_root, RECAPTURED, expected_digest=RECAPTURED_SHA256, media_type="text/markdown"
    )
    _edit(
        draft,
        EVIDENCE_PATH,
        lambda data: data["evidence"][0]["capture"].update({"sha256": RECAPTURED_SHA256}),
    )


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != LOCK_FILE
    }


def _codes(outcome: Any) -> list[str]:
    return [finding.code for finding in outcome.diagnostics]


def _manifest_of(root: Path) -> RevisionManifest:
    manifest = load_documents(root, mode="revision").manifest
    assert isinstance(manifest, RevisionManifest)
    return manifest


# --------------------------------------------------------------------------------------
# The recovery path, end to end
# --------------------------------------------------------------------------------------


def test_a_broken_blob_can_be_checked_out_recaptured_approved_and_promoted(
    broken: Scene,
) -> None:
    """The whole exception in one test, because the value of it is that the sequence completes."""
    checkout = checkout_current(broken.bundle_root, name=REPAIR_DRAFT)
    assert IssueCode.CORRUPT_BLOB_QUARANTINE in _codes(checkout)
    draft = draft_root(broken.bundle_root, REPAIR_DRAFT)
    assert draft.is_dir(), "the draft is produced anyway; refusing would strand the owner"

    _recapture(broken.bundle_root, draft)
    approve_draft(
        broken.bundle_root,
        draft,
        parent=broken.first,
        stamp_id="approval-stamp.000002",
        approved_at=PROMOTED_AT,
    )

    outcome = promote(broken.bundle_root, _request(REPAIR_DRAFT))

    assert outcome.exit_code == 0, outcome.diagnostics
    assert outcome.value is not None
    assert outcome.value.revision == 2
    assert read_current_once(broken.bundle_root).bundle_digest == outcome.value.bundle_digest


def test_the_promotion_reports_the_parents_quarantine_without_refusing(broken: Scene) -> None:
    """§6 says promotion *reports* the quarantine. A blocker would refuse the only repair path."""
    assert checkout_current(broken.bundle_root, name=REPAIR_DRAFT).exit_code == 1
    draft = draft_root(broken.bundle_root, REPAIR_DRAFT)
    _recapture(broken.bundle_root, draft)
    approve_draft(
        broken.bundle_root,
        draft,
        parent=broken.first,
        stamp_id="approval-stamp.000002",
        approved_at=PROMOTED_AT,
    )

    outcome = promote(broken.bundle_root, _request(REPAIR_DRAFT))

    assert outcome.exit_code == 0
    quarantine = [
        finding
        for finding in outcome.diagnostics
        if finding.code == IssueCode.CORRUPT_BLOB_QUARANTINE
    ]
    assert len(quarantine) == 1
    assert quarantine[0].tier == "warning", "a blocker here would refuse the only supported repair"
    assert quarantine[0].details["blob"] == BLOB_SHA256
    assert quarantine[0].details["reason"] in {
        BlobQuarantineReason.MISSING.value,
        BlobQuarantineReason.DIGEST_MISMATCH.value,
    }


def test_the_replacement_revision_is_structurally_valid_on_its_own(broken: Scene) -> None:
    """Nothing is skipped for the *new* revision: it cites a blob whose bytes are present."""
    assert checkout_current(broken.bundle_root, name=REPAIR_DRAFT).exit_code == 1
    draft = draft_root(broken.bundle_root, REPAIR_DRAFT)
    _recapture(broken.bundle_root, draft)
    approve_draft(
        broken.bundle_root,
        draft,
        parent=broken.first,
        stamp_id="approval-stamp.000002",
        approved_at=PROMOTED_AT,
    )
    promoted = promote(broken.bundle_root, _request(REPAIR_DRAFT))
    assert promoted.value is not None

    outcome = validate_bundle(
        promoted.value.root, bundle_root=broken.bundle_root, mode="revision"
    )

    assert outcome.exit_code == 0, outcome.diagnostics
    assert quarantined_blobs(
        broken.bundle_root,
        referenced_blob_digests(load_documents(promoted.value.root, mode="revision")),
    ) == ()


def test_completeness_reports_the_broken_parent_as_an_unverifiable_ancestor(
    broken: Scene,
) -> None:
    """The hole in history stays visible, and stays a blocker rather than an error (§21).

    The default run cannot see it: §20.6 forbids deep-parsing ancestors, so it takes the opt-in
    audit to notice that the parent's own bytes no longer produce its digest. That is the honest
    split — the selected revision is fine, and the thing that is not fine is a revision nobody is
    reading.
    """
    assert checkout_current(broken.bundle_root, name=REPAIR_DRAFT).exit_code == 1
    draft = draft_root(broken.bundle_root, REPAIR_DRAFT)
    _recapture(broken.bundle_root, draft)
    approve_draft(
        broken.bundle_root,
        draft,
        parent=broken.first,
        stamp_id="approval-stamp.000002",
        approved_at=PROMOTED_AT,
    )
    promoted = promote(broken.bundle_root, _request(REPAIR_DRAFT))
    assert promoted.value is not None

    outcome = validate_bundle(
        promoted.value.root,
        bundle_root=broken.bundle_root,
        mode="revision",
        completeness=True,
        as_of=AS_OF,
        deep_history=True,
    )

    ancestors = [
        finding
        for finding in outcome.diagnostics
        if finding.code == IssueCode.UNVERIFIABLE_ANCESTOR
    ]
    assert len(ancestors) == 1
    assert ancestors[0].tier == "blocker"
    assert ancestors[0].details["ancestor_bundle_digest"] == broken.first_digest
    assert not [finding for finding in outcome.diagnostics if finding.tier == "error"]


def test_the_broken_blob_is_never_moved_or_deleted(broken: Scene) -> None:
    """§12.1: a quarantine is logical. The recapture adds a blob; it does not replace one."""
    before = sorted(
        entry.name for entry in (broken.bundle_root / "blobs" / "sha256").iterdir()
    )
    assert checkout_current(broken.bundle_root, name=REPAIR_DRAFT).exit_code == 1
    draft = draft_root(broken.bundle_root, REPAIR_DRAFT)
    _recapture(broken.bundle_root, draft)
    approve_draft(
        broken.bundle_root,
        draft,
        parent=broken.first,
        stamp_id="approval-stamp.000002",
        approved_at=PROMOTED_AT,
    )
    assert promote(broken.bundle_root, _request(REPAIR_DRAFT)).exit_code == 0

    after = sorted(entry.name for entry in (broken.bundle_root / "blobs" / "sha256").iterdir())
    assert after == sorted({*before, RECAPTURED_SHA256})
    assert _snapshot(broken.first) == _snapshot(broken.first)


# --------------------------------------------------------------------------------------
# What the exception does NOT cover
# --------------------------------------------------------------------------------------


def _prepared_repair(scene: Scene) -> Path:
    """A checked-out, approved draft of revision 1, ready to promote."""
    assert checkout_current(scene.bundle_root, name=REPAIR_DRAFT).exit_code == 0
    draft = draft_root(scene.bundle_root, REPAIR_DRAFT)
    _edit(
        draft,
        PurePosixPath("skills/inventory.yaml"),
        lambda data: data["skills"][0].update({"canonical_name": "Repaired"}),
    )
    approve_draft(
        scene.bundle_root,
        draft,
        parent=scene.first,
        stamp_id="approval-stamp.000002",
        approved_at=PROMOTED_AT,
    )
    return draft


def test_a_parent_whose_yaml_will_not_parse_still_blocks(tmp_path: Path) -> None:
    scene = _promoted_revision_one(tmp_path)
    _prepared_repair(scene)
    (scene.first / "skills" / "inventory.yaml").write_bytes(b"skills:\n  - [broken\n")
    before = _snapshot(scene.bundle_root)

    outcome = promote(scene.bundle_root, _request(REPAIR_DRAFT))

    assert outcome.exit_code == 1
    assert IssueCode.CORRUPT_BLOB_QUARANTINE not in _codes(outcome)
    assert _snapshot(scene.bundle_root) == before


def test_a_parent_declaring_an_unsupported_schema_still_blocks(tmp_path: Path) -> None:
    scene = _promoted_revision_one(tmp_path)
    _prepared_repair(scene)
    _edit(scene.first, MANIFEST_PATH, lambda data: data.update({"schema_version": 99}))
    before = _snapshot(scene.bundle_root)

    outcome = promote(scene.bundle_root, _request(REPAIR_DRAFT))

    assert outcome.exit_code == 3
    assert _codes(outcome) == [IssueCode.UNSUPPORTED_SCHEMA_VERSION]
    assert _snapshot(scene.bundle_root) == before


def test_a_parent_whose_manifest_disagrees_with_its_directory_still_blocks(
    tmp_path: Path,
) -> None:
    scene = _promoted_revision_one(tmp_path)
    _prepared_repair(scene)
    _edit(
        scene.first,
        MANIFEST_PATH,
        lambda data: data.update({"bundle_digest": "sha256:" + "a" * 64}),
    )
    before = _snapshot(scene.bundle_root)

    outcome = promote(scene.bundle_root, _request(REPAIR_DRAFT))

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.CURRENT_POINTER_MISMATCH]
    assert _snapshot(scene.bundle_root) == before


def test_a_parent_whose_ledger_was_rewritten_still_blocks(tmp_path: Path) -> None:
    """A rewritten parent ledger is caught by the parent's own digest, before any prefix comparison.

    Both checks would refuse it, and which one speaks first is not arbitrary: recomputing the
    parent's digest is what says "this revision is not the one that was promoted", and that is the
    more accurate sentence for an edit made inside an immutable revision. The prefix comparison is
    what remains when the digest cannot be recomputed at all, which is the test below this one.
    """
    scene = _promoted_revision_one(tmp_path)
    _prepared_repair(scene)
    _edit(
        scene.first,
        PurePosixPath("history/changes.yaml"),
        lambda data: data["changes"][0].update({"summary": "A history nobody promoted"}),
    )
    before = _snapshot(scene.bundle_root)

    outcome = promote(scene.bundle_root, _request(REPAIR_DRAFT))

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.BUNDLE_DIGEST_MISMATCH]
    assert _snapshot(scene.bundle_root) == before


def test_a_broken_blob_does_not_excuse_an_edited_parent_document(tmp_path: Path) -> None:
    """The exception skips the parent's blob integrity, not its documents.

    Worth its own test because the two used to be checked by the same computation: skipping the
    digest recomputation for a quarantined parent is exactly what let an edited document through.
    The recomputation now runs with the quarantined blob's declared digest standing in for its leaf,
    so it speaks here for the same reason it speaks with the blob intact — an edit inside an
    immutable revision means this is not the revision that was promoted. The prefix comparison the
    draft's own ledgers are held to is a separate rule about a separate tree, and is pinned in
    `test_profile_bundle_promotion.py`.
    """
    scene = _promoted_revision_one(tmp_path)
    _prepared_repair(scene)
    blob_path(scene.bundle_root, BLOB_SHA256).unlink()
    _edit(
        scene.first,
        PurePosixPath("history/changes.yaml"),
        lambda data: data["changes"][0].update({"summary": "Rewritten under cover of a lost blob"}),
    )
    before = _snapshot(scene.bundle_root)

    outcome = promote(scene.bundle_root, _request(REPAIR_DRAFT))

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.BUNDLE_DIGEST_MISMATCH]
    assert _snapshot(scene.bundle_root) == before


def test_a_broken_blob_does_not_excuse_an_edited_parent_policy_document(broken: Scene) -> None:
    """The same claim for a document no ledger prefix and no approval decision looks at.

    The test above cannot say whether the parent's digest was recomputed: `history/changes.yaml` is
    one of the three ledgers the prefix comparison covers, and that comparison needs no blob bytes,
    so it refuses either way. `policy/units.yaml` carries no record ID, sits in no ledger and is in
    no approval decision, which leaves the parent's own bundle digest as the only thing that can
    speak about it — and the parent's digest is what the quarantine used to switch off entirely.

    The draft here is the *recaptured* one, so the promotion is otherwise ready to succeed: without
    the recomputation this scene installs revision 2 with exit 0, declaring a `parent_bundle_digest`
    the parent's bytes no longer produce. Its negative control is
    `test_a_broken_blob_can_be_checked_out_recaptured_approved_and_promoted`, which is this scene
    without the tamper and does promote.
    """
    assert checkout_current(broken.bundle_root, name=REPAIR_DRAFT).exit_code == 1
    draft = draft_root(broken.bundle_root, REPAIR_DRAFT)
    _recapture(broken.bundle_root, draft)
    approve_draft(
        broken.bundle_root,
        draft,
        parent=broken.first,
        stamp_id="approval-stamp.000002",
        approved_at=PROMOTED_AT,
    )
    # After the approval, so the owner approved the content they actually saw.
    _edit(
        broken.first,
        PurePosixPath("policy/units.yaml"),
        lambda data: data["units"][0].update({"display_name": "forged under a lost blob"}),
    )
    before = _snapshot(broken.bundle_root)

    outcome = promote(broken.bundle_root, _request(REPAIR_DRAFT))

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.BUNDLE_DIGEST_MISMATCH]
    assert _snapshot(broken.bundle_root) == before
    assert _manifest_of(broken.first).revision == 1


def test_a_draft_that_still_cites_the_broken_blob_cannot_be_promoted(broken: Scene) -> None:
    """Recapturing is the repair. Promoting the same broken citation forward is not."""
    assert checkout_current(broken.bundle_root, name=REPAIR_DRAFT).exit_code == 1
    draft = draft_root(broken.bundle_root, REPAIR_DRAFT)
    _edit(
        draft,
        PurePosixPath("skills/inventory.yaml"),
        lambda data: data["skills"][0].update({"canonical_name": "Repaired"}),
    )
    before = _snapshot(broken.bundle_root)

    outcome = promote(broken.bundle_root, _request(REPAIR_DRAFT))

    assert outcome.exit_code == 1
    assert _snapshot(broken.bundle_root) == before
    assert current_path(broken.bundle_root).exists()
    assert _manifest_of(broken.first).revision == 1
