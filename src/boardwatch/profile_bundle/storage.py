"""One-read selection of the immutable current revision (design §6).

§6 gives readers a lock-free contract with four clauses, and each one exists because a reader that
skipped it would still return something that looked coherent:

1. **Read `CURRENT` exactly once.** Promotion's commit point is a single `os.replace` of this file.
   A reader that read it twice could take a revision number from before the replacement and a
   digest from after it, and report a revision that was never promoted.
2. **Resolve the digest-named directory.** Revision numbers are never filesystem identity, so two
   torn attempts at the same content cannot reserve two numbered slots.
3. **Require `COMPLETE`.** It is written last, so its absence means the tree is a torn promotion
   whose documents may be half of one revision and half of another.
4. **Verify the manifest's identity.** Unselected digest directories are retained forever by §21, so
   a pointer that names the wrong one is a live possibility rather than a hypothetical.

## Why the pointer read lives behind one function

`read_current` is T13's, defined next to the model it parses, and is deliberately reused rather than
reimplemented — two readers for one 45-byte file are two chances to disagree about what it says.
What this module adds is the *once*: every operation that resolves a selection enters through
`read_current_once`, so "how many times did this command read the pointer?" has one answer that a
test can assert by counting calls. (`validate` is not one of them: it is given a tree and a bundle
root and reads the pointer through `validation.digest.read_current`, once, to find an ancestor.)

**The symbol a test must patch is `storage.read_current`, never `storage.read_current_once`.**
`drafts`, `inspection` and the rebase path all do `from …storage import read_current_once`, which
binds the function object at import; replacing this module's attribute afterwards reaches none of
them, and a counting test written that way would observe zero calls and pass while measuring
nothing. `read_current` is different because it is resolved as a module global *inside*
`read_current_once`, at call time — which is the only reason the existing counting tests work.

## Why a symlink is refused here and not by the layout walker

`discover_source_files` refuses every symlink it walks past, but it starts *inside* the tree and so
never examines the tree's own root, nor the bundle root's own members, none of which are documents.
Those are the paths that decide which bytes the walker will be pointed at, which makes them the
confinement boundary rather than an extra check beside one. `require_confined_root` states that
boundary once over the whole declared grammar, rather than once per directory a command happens to
touch: `approvals/` and `revisions/` hold nothing until promotion writes them, and a per-directory
guard would leave exactly those two escapes armed for the slice that does.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from boardwatch.profile_bundle.errors import IssueCode, ProfileBundleError
from boardwatch.profile_bundle.models.documents import BundleDocuments
from boardwatch.profile_bundle.models.manifests import RevisionManifest
from boardwatch.profile_bundle.paths import (
    COMPLETE_FILE,
    CURRENT_FILE,
    ROOT_MEMBERS,
    current_path,
    revision_root,
)
from boardwatch.profile_bundle.validation.context import load_documents
from boardwatch.profile_bundle.validation.digest import PointerError, read_complete, read_current


class SelectionError(ProfileBundleError):
    """The bundle root has no coherent selected revision.

    Carries the `IssueCode` chosen at the raise site so a caller reports the operator's actual
    situation — "there is no revision yet" and "the pointer names a revision that is not here" are
    different actions — without classifying anything by reading a message.
    """

    def __init__(self, code: IssueCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SelectedRevision:
    """The one immutable revision an operation works against, resolved from a single pointer read.

    Holds `bundle_root` as well as `root` because everything shared across revisions — the blob
    store, the approval stamps, the pointer itself — lives at the root while the documents live in
    the tree, and a caller that had to derive one from the other would be guessing at a layout it
    was already handed.
    """

    bundle_root: Path
    root: Path
    revision: int
    bundle_digest: str


def require_confined_root(bundle_root: Path) -> None:
    """Refuse a bundle root that reaches outside itself through one of its declared members.

    §6 says the active revision and all required evidence are self-contained under one root, and §7
    depends on it: blob bytes are hashed into `evidence_set_digest` and therefore into
    `bundle_digest`, so a symlinked `blobs/` would let content nobody can see from the root decide
    the bundle's identity.

    Written over `ROOT_MEMBERS` — the same closed grammar `inventory` reports against — so that a
    member added later, and every writer added later, inherits the check instead of restating it.
    A dangling symlink is refused too: `is_symlink` does not follow, and a member that resolves to
    nothing today is still a member that is not inside this root.
    """
    for member in sorted(ROOT_MEMBERS):
        if (bundle_root / member).is_symlink():
            raise SelectionError(
                IssueCode.SYMLINK_REFUSED,
                f"{member} is a symlink; a bundle is self-contained under one root, so every "
                "declared member of it must be a real file or directory inside that root",
            )


def read_current_once(bundle_root: Path) -> SelectedRevision:
    """Resolve the selected revision, reading `CURRENT` exactly one time.

    Raises `SelectionError` rather than returning a diagnostic: a caller that cannot resolve a
    selection has no revision to report *about*, and every caller here either refuses outright or
    reports the failure as its own finding (`inventory` does the latter).
    """
    require_confined_root(bundle_root)
    pointer_path = current_path(bundle_root)
    if not pointer_path.exists():
        # Promotion only ever `os.replace`s this path, never unlinks it, so an absent `CURRENT` is
        # a bundle that has never been promoted rather than a race against a promotion in flight.
        raise SelectionError(
            IssueCode.NO_CURRENT_REVISION,
            f"there is no {CURRENT_FILE} in this bundle; no revision has been promoted yet",
        )
    try:
        pointer = read_current(bundle_root)
    except PointerError as exc:
        raise SelectionError(IssueCode.CURRENT_POINTER_MISMATCH, str(exc)) from exc

    root = revision_root(bundle_root, pointer.bundle_digest)
    if root.is_symlink():
        raise SelectionError(
            IssueCode.SYMLINK_REFUSED,
            f"the selected revision directory {root.name} is a symlink; a bundle is self-contained "
            "under one root",
        )
    if not root.is_dir():
        raise SelectionError(
            IssueCode.CURRENT_POINTER_MISMATCH,
            f"{CURRENT_FILE} selects {pointer.bundle_digest}, but {root.name} is not a directory "
            "in this bundle",
        )
    try:
        marker = read_complete(root)
    except PointerError as exc:
        raise SelectionError(IssueCode.COMPLETE_MARKER_MISSING, str(exc)) from exc
    if marker != pointer.bundle_digest:
        raise SelectionError(
            IssueCode.CURRENT_POINTER_MISMATCH,
            f"{CURRENT_FILE} selects {pointer.bundle_digest} but that directory's {COMPLETE_FILE} "
            f"names {marker}",
        )
    return SelectedRevision(
        bundle_root=bundle_root,
        root=root,
        revision=pointer.revision,
        bundle_digest=pointer.bundle_digest,
    )


def selected_documents(selection: SelectedRevision) -> BundleDocuments:
    """Parse the selected revision and verify it is the one the pointer named (§6 clause 4).

    The comparison is against the *pointer*, not against a recomputed digest: recomputing is
    `validate_digest`'s job and needs every blob, while a reader only needs to know it is serving
    the tree that was selected. A mutated document is therefore still served here and reported by
    `validate` — that split is deliberate, because refusing to read a revision would also make it
    impossible to inspect the damage.
    """
    documents = load_documents(selection.root, mode="revision")
    manifest = documents.manifest
    if not isinstance(manifest, RevisionManifest):
        raise SelectionError(
            IssueCode.DRAFT_MANIFEST_INVALID,
            f"{selection.root.name} holds a draft manifest, whose identity fields are the "
            "unset sentinels; it cannot be a selected revision",
        )
    if manifest.bundle_digest != selection.bundle_digest:
        raise SelectionError(
            IssueCode.CURRENT_POINTER_MISMATCH,
            f"{CURRENT_FILE} selects {selection.bundle_digest} but the manifest in "
            f"{selection.root.name} declares {manifest.bundle_digest}",
        )
    if manifest.revision != selection.revision:
        raise SelectionError(
            IssueCode.CURRENT_POINTER_MISMATCH,
            f"{CURRENT_FILE} selects revision {selection.revision} but the manifest declares "
            f"revision {manifest.revision}",
        )
    return documents


__all__ = [
    "SelectedRevision",
    "SelectionError",
    "read_current",
    "read_current_once",
    "require_confined_root",
    "selected_documents",
]
