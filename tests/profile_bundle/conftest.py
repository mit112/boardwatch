"""The synthetic comprehensive bundle, materialised into a temporary bundle root.

The packaged example is a *logical revision tree*: manifest, facts, claims, policy, imports,
history. Blobs deliberately are not part of it, because design §6 puts `blobs/sha256/` at the bundle
ROOT and shares it across revisions. So the fixture is what turns the example into a usable bundle:
it copies the tree into `drafts/<name>/` (or into a revision directory), writes the blob bytes the
example's one blob capture names, and hands back the paths and digests a test needs.

The blob text lives here rather than in the package because it is *not* part of any revision's
logical content — only its digest is.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

from boardwatch.profile_bundle.approvals import (
    approval_stamp_bytes,
    build_approval_stamp,
    required_approval_decisions,
)
from boardwatch.profile_bundle.canonical import (
    MappingBlobReader,
    bundle_digest,
    candidate_content_digest,
)
from boardwatch.profile_bundle.models.documents import BundleDocuments
from boardwatch.profile_bundle.models.history import ApprovalStamp, ChangeRecord
from boardwatch.profile_bundle.models.manifests import RevisionManifest
from boardwatch.profile_bundle.paths import (
    approval_path,
    blob_path,
    blobs_dir,
    complete_marker_path,
    current_path,
    draft_root,
    drafts_dir,
    revision_root,
)
from boardwatch.profile_bundle.validation import load_documents
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from boardwatch.profile_bundle.yaml_writer import document_bytes

EXAMPLE_PACKAGE = "boardwatch.profile_bundle"
EXAMPLE_RELATIVE = "examples/comprehensive"

#: The bytes behind the example's one blob capture. Its digest is authored into
#: `evidence/records.yaml`, so changing this text without regenerating the example breaks the
#: blob-integrity check — which is the point.
BLOB_TEXT = (
    "# Packet Pantry baseline A\n\n"
    "Synthetic benchmark note. Sustained approximately 120 items/s over a five minute run on a\n"
    "single local node with one producer. Recorded so the linked metric can be reviewed without\n"
    "resolving its origin.\n"
)
BLOB_BYTES = BLOB_TEXT.encode("utf-8")
BLOB_SHA256 = hashlib.sha256(BLOB_BYTES).hexdigest()

#: The example is a parentless revision-1 draft, so its manifest carries this evidence-set digest.
#: Pinned here as well as in the YAML so a test can assert the two agree by a second path.
EXAMPLE_EVIDENCE_SET_DIGEST = (
    "sha256:bb92aef8ff2d82c0178482ab5fa4c24975e6f3ab8251f3e6d939e14d3bcffde0"
)

EXAMPLE_PROFILE_ID = "profile.example-candidate"

WINDOWS_STALE_LOCK_RACE = (
    "Windows is a best-effort platform (D-212) and this is a Windows-only race. `locking.py` rests "
    "on 'the operating system is the only authority', which is a POSIX-shaped premise: the kernel "
    "drops a dead process's flock at once. On Windows, `filelock`'s `WindowsFileLock._acquire` "
    "swallows EACCES from `os.open` without setting the fd, so an acquire that lands inside the "
    "killed holder's handle-teardown window raises `Timeout` and is reported as `bundle_lock_held` "
    "— a lock nobody holds. Measured across three nightly builds it failed 6 of 9 Windows jobs, "
    "landing in whichever of the two suites ran first, so it is a race and not standing breakage. "
    "NOT strict, deliberately: on the other 3 of 9 the test passes, and `strict=True` would turn "
    "that XPASS into a fresh red nightly. The marker is conditional, so on Linux and macOS — where "
    "the guarantee is actually claimed — this stays an ordinary test that must pass."
)

# FOUR tests across three files acquire the lock after killing its holder, and the reason above is
# the same fact about one lock. Kept here so they cannot drift into disagreeing accounts of why they
# are marked. The census is `process.kill()` in a test BODY (fixture teardown does not count) —
# not the word "killed" in a name, which is what left instances 3 and 4 unmarked (D-222, D-223).
# Holder-stays-alive tests are deliberately unmarked: there the race produces a spurious PASS.


def example_source_root() -> Path:
    """The packaged example tree, resolved through `importlib.resources`.

    Resolved as a resource rather than by walking up from `__file__` so the same fixture works
    against an installed wheel, which is where a missing package-data file would actually show up.
    """
    traversable = resources.files(EXAMPLE_PACKAGE).joinpath(EXAMPLE_RELATIVE)
    with resources.as_file(traversable) as path:
        return Path(path)


@dataclass(frozen=True)
class SyntheticBundle:
    """A materialised bundle root holding the comprehensive example as one draft."""

    root: Path
    draft_name: str
    draft: Path
    blob: Path

    @property
    def manifest_path(self) -> Path:
        return self.draft / "manifest.yaml"

    def document(self, relative: str) -> Path:
        return self.draft / relative

    def read(self, relative: str) -> str:
        return self.document(relative).read_text(encoding="utf-8")

    def write(self, relative: str, text: str) -> None:
        """Rewrite one document in place. Used to build the negative cases."""
        self.document(relative).write_text(text, encoding="utf-8")


@dataclass(frozen=True)
class PromotedRevisionFixture:
    """A deliberate promoted-revision seam shared by the later history slices."""

    documents: BundleDocuments
    manifest: RevisionManifest
    change: ChangeRecord
    approval: ApprovalStamp


@pytest.fixture
def promoted_revision_fixture(tmp_path: Path) -> PromotedRevisionFixture:
    """One revision manifest, one change record, and one approval stamp.

    The fixture is intentionally typed rather than assembled from YAML so T13/T16 can reuse the
    same promotion-shaped objects without smuggling an authored revision into the draft example.
    """
    root = tmp_path / "career-profile"
    root.mkdir()
    drafts_dir(root).mkdir()
    bundle = materialise(root)
    documents = parse_documents(bundle.draft)
    draft = documents.manifest
    manifest_values = draft.model_dump(mode="json")
    manifest_values.pop("draft_of_revision", None)
    manifest = RevisionManifest.model_validate(
        {
            **manifest_values,
            "state": "revision",
            "revision": 1,
            "parent_bundle_digest": None,
            "bundle_digest": "sha256:" + "1" * 64,
            "created_at": "2026-08-10T12:00:00Z",
            "created_by": "owner",
            "change_id": "change.example.000001",
            "approved_candidate_digest": "sha256:" + "2" * 64,
            "approval_stamp_id": "approval-stamp.000001",
        }
    )
    change = ChangeRecord.model_validate(
        {
            "change_id": "change.example.000001",
            "revision": 1,
            "parent_bundle_digest": None,
            "actor": "owner",
            "authorized_by": "owner",
            "summary": "Initial promoted synthetic revision",
            "changed_record_ids": [],
            "created_at": "2026-08-10T12:00:00Z",
        }
    )
    approval = build_approval_stamp(
        stamp_id="approval-stamp.000001",
        candidate_digest="sha256:" + "2" * 64,
        approved_at=datetime(2026, 8, 10, 12, tzinfo=UTC),
        decisions=required_approval_decisions(documents, None),
    )
    return PromotedRevisionFixture(
        documents=documents,
        manifest=manifest,
        change=change,
        approval=approval,
    )


def materialise(root: Path, *, draft_name: str = "baseline") -> SyntheticBundle:
    """Copy the packaged example into `root` as a draft, and write its blob bytes."""
    target = draft_root(root, draft_name)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(example_source_root(), target)
    blobs_dir(root).mkdir(parents=True, exist_ok=True)
    blob = blob_path(root, BLOB_SHA256)
    blob.write_bytes(BLOB_BYTES)
    return SyntheticBundle(root=root, draft_name=draft_name, draft=target, blob=blob)


def materialise_revision_tree(destination: Path) -> Path:
    """Copy the example's logical tree to an arbitrary directory, blobs excluded.

    Promotion and digest tests need the tree somewhere that is not `drafts/`, and they own where.
    """
    shutil.copytree(example_source_root(), destination)
    return destination


@pytest.fixture
def synthetic_bundle(tmp_path: Path) -> SyntheticBundle:
    """A fresh bundle root with the comprehensive example checked out as `drafts/baseline/`."""
    root = tmp_path / "career-profile"
    root.mkdir()
    drafts_dir(root).mkdir()
    return materialise(root)


def parse_documents(root: Path, *, final_revision: bool = False) -> BundleDocuments:
    """Parse one logical tree into `BundleDocuments`, through the production loader.

    Delegates rather than re-implementing: a fixture that parsed by its own path would let the
    fixtures agree with each other while disagreeing with what the CLI actually reads.
    """
    return load_documents(root, mode="revision" if final_revision else "draft")


def blob_reader() -> MappingBlobReader:
    """A reader over the one blob the example names, for identity computations in tests."""
    return MappingBlobReader({BLOB_SHA256: BLOB_BYTES})


def stored_blob_reader(bundle_root: Path) -> MappingBlobReader:
    """An in-memory reader over whatever the bundle's store actually holds.

    `blob_reader` knows one blob and is right wherever the example is the whole story. A recapture
    puts a *second* blob in the store under a digest no fixture can predict, so a test that approves
    such a draft needs the store's real contents — and still wants them in memory, so the value it
    computes is not reached through the same `FilesystemBlobReader` the code under test uses.

    Keyed by filename rather than by content on purpose: that is what the store's own reader does,
    so a blob whose bytes no longer hash to its name reaches both readers identically instead of
    disappearing from one of them.
    """
    directory = blobs_dir(bundle_root)
    if not directory.is_dir():
        return MappingBlobReader({})
    return MappingBlobReader(
        {
            entry.name: entry.read_bytes()
            for entry in sorted(directory.iterdir())
            if entry.is_file() and not entry.name.startswith(".tmp-")
        }
    )


# --------------------------------------------------------------------------------------
# A promoted revision that actually exists on disk (T13 §20.6, reused by T14 and T16)
# --------------------------------------------------------------------------------------


def quoted_yaml(payload: object, *, logical_path: PurePosixPath) -> bytes:
    """Serialise `payload` as a document this bundle's loader reads back unchanged.

    T14 shipped that emitter, so this is now `document_bytes` under the name the fixtures already
    used: a fixture that carried its own copy of the quoting policy would be a second statement of
    the authoring contract, and the whole point of `document_bytes` is that it verifies the contract
    by reading the bytes back instead of restating it.

    `logical_path` is passed through rather than defaulted for the emitter's own reason: it is the
    only thing that makes a failure locatable.
    """
    return document_bytes(payload, logical_path=logical_path)


def approve_draft(
    bundle_root: Path,
    draft: Path,
    *,
    parent: Path | None = None,
    stamp_id: str = "approval-stamp.000001",
    approved_at: datetime = datetime(2026, 8, 11, 9, tzinfo=UTC),
) -> str:
    """Do what `profile-bundle approve` will: file a stamp for the draft's candidate digest.

    Shared by every promotion test because the *binding* — which digest a stamp covers, and the
    bytes it is stored as — is a contract, and four copies of it would be four chances for a test to
    approve something `promote` does not look for. The digest is computed through the in-memory blob
    reader, so it reaches the same value by a different route than promotion's filesystem reader.
    """
    documents = load_documents(draft, mode="draft")
    parent_documents = None if parent is None else load_documents(parent, mode="revision")
    envelope = None
    if parent_documents is not None:
        parent_manifest = parent_documents.manifest
        assert isinstance(parent_manifest, RevisionManifest)
        envelope = parent_manifest.envelope
    candidate = candidate_content_digest(documents, stored_blob_reader(bundle_root), envelope)
    stamp = build_approval_stamp(
        stamp_id=stamp_id,
        candidate_digest=candidate,
        approved_at=approved_at,
        decisions=required_approval_decisions(documents, parent_documents),
    )
    path = approval_path(bundle_root, candidate)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        approval_stamp_bytes(stamp, logical_path=PurePosixPath(f"approvals/{path.name}"))
    )
    return candidate


@dataclass(frozen=True)
class PromotedRevisionTree:
    """A revision directory whose name, `COMPLETE`, manifest and `CURRENT` all agree."""

    bundle_root: Path
    revision_dir: Path
    bundle_digest: str
    candidate_digest: str
    revision: int
    documents: BundleDocuments


def promote_example_tree(bundle_root: Path, *, revision: int = 1) -> PromotedRevisionTree:
    """Materialise the packaged example as a genuinely promoted revision.

    Digest validation cannot be tested against a fixture with placeholder digests: every check
    would report a mismatch and the positive path would never run. So this reproduces promotion's
    digest order rather than asserting a number — the candidate digest is computed from the draft,
    the stamp is built over it, the change record is appended, and only then is the bundle digest
    computed from the bytes on disk.

    It writes exactly three documents. The other 24 are copied byte for byte, which keeps the
    fixture from depending on a YAML writer for anything the example already states.
    """
    bundle_root.mkdir(parents=True, exist_ok=True)
    drafts_dir(bundle_root).mkdir(exist_ok=True)
    blobs_dir(bundle_root).mkdir(parents=True, exist_ok=True)
    blob_path(bundle_root, BLOB_SHA256).write_bytes(BLOB_BYTES)

    staging = bundle_root / ".staging-revision"
    materialise_revision_tree(staging)
    draft_documents = load_documents(staging, mode="draft")
    blobs = blob_reader()

    candidate_digest = candidate_content_digest(draft_documents, blobs, None)
    stamp_id = "approval-stamp.000001"
    change_id = "change.example.000001"
    created = "2026-08-10T12:00:00Z"

    stamp = build_approval_stamp(
        stamp_id=stamp_id,
        candidate_digest=candidate_digest,
        approved_at=datetime(2026, 8, 10, 12, tzinfo=UTC),
        decisions=required_approval_decisions(draft_documents, None),
    )
    change = ChangeRecord.model_validate(
        {
            "change_id": change_id,
            "revision": revision,
            "parent_bundle_digest": None,
            "actor": "owner",
            "authorized_by": "owner",
            "summary": "Initial promoted synthetic revision",
            "changed_record_ids": [],
            "created_at": created,
        }
    )

    draft_values = draft_documents.manifest.model_dump(mode="json")
    draft_values.pop("draft_of_revision", None)
    manifest_values = {
        **draft_values,
        "state": "revision",
        "revision": revision,
        "parent_bundle_digest": None,
        # Overwritten below once it can be computed. `_manifest_with` blanks this field before
        # hashing the manifest leaf, so the placeholder cannot influence the digest it becomes.
        "bundle_digest": "sha256:" + "0" * 64,
        "created_at": created,
        "created_by": "owner",
        "change_id": change_id,
        "approved_candidate_digest": candidate_digest,
        "approval_stamp_id": stamp_id,
    }

    def write_promotion_documents(values: dict[str, object]) -> None:
        (staging / "manifest.yaml").write_bytes(
            quoted_yaml(
                RevisionManifest.model_validate(values).model_dump(mode="json"),
                logical_path=PurePosixPath("manifest.yaml"),
            )
        )
        (staging / "history" / "changes.yaml").write_bytes(
            quoted_yaml(
                {"changes": [change.model_dump(mode="json")]},
                logical_path=PurePosixPath("history/changes.yaml"),
            )
        )
        (staging / "history" / "approvals.yaml").write_bytes(
            quoted_yaml(
                {"approvals": [stamp.model_dump(mode="json")]},
                logical_path=PurePosixPath("history/approvals.yaml"),
            )
        )

    return _seal_revision(
        bundle_root,
        staging,
        manifest_values=manifest_values,
        changes=[change],
        stamps=[stamp],
        candidate_digest=candidate_digest,
        revision=revision,
    )


def _seal_revision(
    bundle_root: Path,
    staging: Path,
    *,
    manifest_values: dict[str, object],
    changes: list[ChangeRecord],
    stamps: list[ApprovalStamp],
    candidate_digest: str,
    revision: int,
) -> PromotedRevisionTree:
    """Write the three promotion documents, compute the digest from disk, and name the directory.

    Shared by both promotions so a chain cannot be sealed by different rules than a first revision.
    The digest is deliberately recomputed from what landed on disk rather than from the models above:
    a fixture that digests its own in-memory objects agrees with itself while disagreeing with every
    reader, which is the failure the design calls out for promotion itself.
    """
    blobs = blob_reader()

    def write(values: dict[str, object]) -> None:
        (staging / "manifest.yaml").write_bytes(
            quoted_yaml(
                RevisionManifest.model_validate(values).model_dump(mode="json"),
                logical_path=PurePosixPath("manifest.yaml"),
            )
        )
        (staging / "history" / "changes.yaml").write_bytes(
            quoted_yaml(
                {"changes": [one.model_dump(mode="json") for one in changes]},
                logical_path=PurePosixPath("history/changes.yaml"),
            )
        )
        (staging / "history" / "approvals.yaml").write_bytes(
            quoted_yaml(
                {"approvals": [one.model_dump(mode="json") for one in stamps]},
                logical_path=PurePosixPath("history/approvals.yaml"),
            )
        )

    write(manifest_values)
    digest = bundle_digest(load_documents(staging, mode="revision"), blobs)
    manifest_values["bundle_digest"] = digest
    write(manifest_values)
    final = load_documents(staging, mode="revision")
    assert bundle_digest(final, blobs) == digest, "writing the digest in changed the digest"

    revision_dir = revision_root(bundle_root, digest)
    revision_dir.parent.mkdir(parents=True, exist_ok=True)
    staging.rename(revision_dir)
    # `write_bytes`, never `write_text`: both files are compared byte for byte against what
    # `current_pointer_bytes` and the complete-marker reader emit, and `write_text` translates the
    # trailing "\n" to "\r\n" on Windows. Production writes them through `open("wb")` for the same
    # reason. This fixture used `write_text` and so wrote a pointer no reader would accept, which is
    # why one line here failed ~100 tests on the Windows matrix with `current_pointer_mismatch`.
    complete_marker_path(revision_dir).write_bytes(f"{digest}\n".encode())
    current_path(bundle_root).write_bytes(
        json.dumps(
            {"bundle_digest": digest, "revision": revision}, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        + b"\n"
    )
    return PromotedRevisionTree(
        bundle_root=bundle_root,
        revision_dir=revision_dir,
        bundle_digest=digest,
        candidate_digest=candidate_digest,
        revision=revision,
        documents=final,
    )


def promote_next_revision(
    parent: PromotedRevisionTree, *, mutate: Callable[[Any], None]
) -> PromotedRevisionTree:
    """Promote a child revision of `parent`, changing one document through `mutate`.

    Needed because several §20.6 clauses cannot fire at revision 1 at all: `ChangeRecord` refuses a
    revision-1 entry that names a parent digest, so "the final change names a different parent than
    the manifest" is only reachable once a parent exists. A fixture that stopped at revision 1 would
    leave that check shipped and unexercised.

    The ledgers are appended to, never rewritten, because that prefix property is what
    `validate_history` compares against the parent and what makes local history verifiable.
    """
    revision = parent.revision + 1
    staging = parent.bundle_root / f".staging-revision-{revision}"
    shutil.copytree(parent.revision_dir, staging)
    complete_marker_path(staging).unlink()

    path = staging / "skills" / "inventory.yaml"
    logical = PurePosixPath("skills/inventory.yaml")
    data = load_yaml_bytes(path.read_bytes(), logical_path=logical)
    mutate(data)
    path.write_bytes(quoted_yaml(data, logical_path=logical))

    parent_manifest = parent.documents.manifest
    assert isinstance(parent_manifest, RevisionManifest)
    draft_values = parent_manifest.model_dump(mode="json")
    change_id = f"change.example.{revision:06d}"
    stamp_id = f"approval-stamp.{revision:06d}"
    created = f"2026-08-1{revision}T12:00:00Z"

    # The candidate view of a promotion is the tree with its own change entry removed, so the
    # digest is computed against the parent's ledger length before the new entry is appended.
    staged_documents = load_documents(staging, mode="revision")
    candidate_digest = candidate_content_digest(
        staged_documents, blob_reader(), parent_manifest.envelope
    )
    stamp = build_approval_stamp(
        stamp_id=stamp_id,
        candidate_digest=candidate_digest,
        approved_at=datetime(2026, 8, 10 + revision, 12, tzinfo=UTC),
        # `required_approval_decisions` compares against the parent's DOCUMENTS to see what
        # changed; `candidate_content_digest` takes its manifest ENVELOPE. Two different
        # parent-shaped parameters, and passing one where the other belongs type-checks under
        # neither but fails at runtime deep inside `build_index`.
        decisions=required_approval_decisions(staged_documents, parent.documents),
    )
    change = ChangeRecord.model_validate(
        {
            "change_id": change_id,
            "revision": revision,
            "parent_bundle_digest": parent.bundle_digest,
            "actor": "owner",
            "authorized_by": "owner",
            "summary": f"Synthetic revision {revision}",
            "changed_record_ids": [],
            "created_at": created,
        }
    )
    return _seal_revision(
        parent.bundle_root,
        staging,
        manifest_values={
            **draft_values,
            "state": "revision",
            "revision": revision,
            "parent_bundle_digest": parent.bundle_digest,
            "bundle_digest": "sha256:" + "0" * 64,
            "created_at": created,
            "created_by": "owner",
            "change_id": change_id,
            "approved_candidate_digest": candidate_digest,
            "approval_stamp_id": stamp_id,
        },
        changes=[*parent.documents.by_path[PurePosixPath("history/changes.yaml")].changes, change],
        stamps=[*parent.documents.by_path[PurePosixPath("history/approvals.yaml")].approvals, stamp],
        candidate_digest=candidate_digest,
        revision=revision,
    )


def reseal_without_reapproval(
    tree: PromotedRevisionTree, *, mutate: Callable[[Any], None]
) -> PromotedRevisionTree:
    """Re-seal `tree` around edited content while keeping the owner's original approval.

    This is the forgery §20.6's candidate clause exists to catch, performed exactly as somebody with
    write access to the bundle would: edit a document, recompute the bundle digest, rename the
    directory, rewrite `COMPLETE` and `CURRENT`. Every other digest check then agrees, because every
    other digest is recomputed from the new bytes. Only `approved_candidate_digest` and the approval
    stamp still describe what the owner actually looked at, which is why the candidate comparison is
    the single check standing between this tree and a clean report.
    """
    staging = tree.bundle_root / f".staging-reseal-{tree.revision}"
    shutil.copytree(tree.revision_dir, staging)
    complete_marker_path(staging).unlink()

    logical = PurePosixPath("skills/inventory.yaml")
    path = staging / "skills" / "inventory.yaml"
    data = load_yaml_bytes(path.read_bytes(), logical_path=logical)
    mutate(data)
    path.write_bytes(quoted_yaml(data, logical_path=logical))

    manifest = tree.documents.manifest
    assert isinstance(manifest, RevisionManifest)
    shutil.rmtree(tree.revision_dir)  # the digest-named directory is what gets replaced
    return _seal_revision(
        tree.bundle_root,
        staging,
        manifest_values=manifest.model_dump(mode="json"),
        changes=list(tree.documents.by_path[PurePosixPath("history/changes.yaml")].changes),
        stamps=list(tree.documents.by_path[PurePosixPath("history/approvals.yaml")].approvals),
        candidate_digest=manifest.approved_candidate_digest,
        revision=tree.revision,
    )


@pytest.fixture
def promoted_tree(tmp_path: Path) -> PromotedRevisionTree:
    return promote_example_tree(tmp_path / "career-profile")


@pytest.fixture
def chained_tree(tmp_path: Path) -> PromotedRevisionTree:
    """Revision 2, promoted onto a real revision 1 that is still on disk."""
    first = promote_example_tree(tmp_path / "career-profile")
    return promote_next_revision(
        first,
        mutate=lambda data: data["skills"][0].update({"canonical_name": "Second Revision Language"}),
    )
