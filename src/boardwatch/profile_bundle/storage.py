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
never examines the tree's own root, nor the bundle root's own members, nor the blob store, none of
which are documents. Those are the paths that decide which bytes the walker will be pointed at,
which makes them the confinement boundary rather than an extra check beside one.
`require_confined_root` states that boundary once over every path an identity can be computed from,
rather than once per directory a command happens to touch: `approvals/` and `revisions/` hold
nothing until promotion writes them, and a per-directory guard would leave exactly those two escapes
armed for the slice that does.

The set of those paths is *derived*, never listed again: the root's own entries come from
`ROOT_MEMBERS` and the blob store comes from `paths.blobs_dir`, because the store sits one component
below the member named `blobs` and a check written over the names alone reached `blobs/` while the
bytes that decide `bundle_digest` live in `blobs/sha256/`.

## Why the tree comparison lives here

`identical_trees` answers one question — are these two directories the same bytes under the same
relative paths — and two commands stake a *deletion* on the answer: `rebase-draft` removes the draft
it has proved is retained at the backup path, and `promote` discards its own temporary directory
only when the digest target already holds exactly that tree (§6 step 7). A second implementation is
not a duplication nit; it is a second definition of what "already retained" means, and each of the
two callers deletes something on the strength of it.
"""

from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path

from boardwatch.profile_bundle.errors import IssueCode, ProfileBundleError
from boardwatch.profile_bundle.models.documents import BundleDocuments
from boardwatch.profile_bundle.models.manifests import RevisionManifest
from boardwatch.profile_bundle.paths import (
    COMPLETE_FILE,
    CURRENT_FILE,
    ROOT_MEMBERS,
    blobs_dir,
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
    """Refuse a bundle root that reaches outside itself through any path its identity is read from.

    §6 says the active revision and all required evidence are self-contained under one root, and §7
    depends on it: blob bytes are hashed into `evidence_set_digest` and therefore into
    `bundle_digest`, so a symlinked `blobs/` would let content nobody can see from the root decide
    the bundle's identity.

    Written once over the whole set — the same closed grammar `inventory` reports against, plus the
    blob store `paths` derives below it — so that a member added later, and every writer added
    later, inherits the check instead of restating it.

    Residual risk: this is a path-based check and therefore TOCTOU. A symlink created after it
    returns is not seen, and the operation proceeds against wherever the new link points — for the
    draft commands that is the tree `_install` renames into `drafts/<name>`, and for `validate` it
    is the blob bytes read into `evidence_set_digest`. Closing that window needs `openat`/
    `O_NOFOLLOW` per component, which nothing here attempts; the check narrows the exposure to the
    interval rather than eliminating it.
    """
    resolved_root = bundle_root.resolve()
    for member in sorted(ROOT_MEMBERS):
        _require_derived_location(bundle_root / member, bundle_root, resolved_root)
    # The store is `blobs/<algorithm>/`, one component below the member named `blobs`, and is asked
    # for by the accessor that builds it rather than spelled out again here — a check written over
    # the root's member names alone cannot reach the directory whose bytes decide `bundle_digest`.
    store = blobs_dir(bundle_root)
    _require_derived_location(store, bundle_root, resolved_root)
    if store.is_dir():
        # Each entry on its own: a single blob file is enough to decide `bundle_digest`, and the
        # store's own path being confined says nothing about what its entries point at.
        for entry in sorted(store.iterdir()):
            _require_stored_blob(entry, bundle_root)


def _require_stored_blob(path: Path, bundle_root: Path) -> None:
    """A blob store entry must be a regular file that is not a link.

    One `lstat` rather than `_require_derived_location`'s `resolve()`, and not as an optimisation
    for its own sake: `resolve()` walks every component of an absolute path, so checking the store's
    thousands of entries that way re-walks the same ancestors thousands of times — 8.7 s at 20,000
    blobs, on every command that reads the bundle. The two are equivalent here anyway. The store's
    own path and each of its ancestors have already been checked one loop earlier, so the only way
    an entry can fail the equality is by being a link itself, which is what `S_ISLNK` says.

    The regular-file half is not equivalent and is the reason this is a refusal rather than a
    cheaper spelling of the same one: a FIFO or a socket resolves to exactly its own place, so it
    satisfies the equality — and then the first command to read the store blocks in `open()`
    forever, with no timeout and nothing reported. Neither is content anything can address by
    digest.
    """
    relative = path.relative_to(bundle_root)
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode):
        raise SelectionError(
            IssueCode.SYMLINK_REFUSED,
            f"{relative.as_posix()} does not resolve to its own place in this bundle; a bundle is "
            "self-contained under one root, so every path its identity is computed from must be "
            "the file or directory the layout names and not a link to somewhere else",
        )
    if not stat.S_ISREG(mode):
        raise SelectionError(
            IssueCode.UNKNOWN_FILE,
            f"{relative.as_posix()} is not a regular file; the blob store holds content addressed "
            "by its own digest, and a directory, device or named pipe has no bytes to address",
        )


def _require_derived_location(path: Path, bundle_root: Path, resolved_root: Path) -> None:
    """The one refusal: `path` must resolve to exactly the place the layout derived it from.

    Stated as an equality against that derivation rather than as a rule about symlinks, because the
    fact §6 needs is *where the bytes are*. `resolve()` follows a chain of any length and sees a
    link an ancestor introduced, so every path a later slice derives is covered by one sentence
    without amending it — which is the drift that put the check one component above the blob store.

    The equality refuses both ways out, and it takes both to keep this the only rule here: a member
    that leaves the root entirely lets outside content decide `bundle_digest`, and one that aliases
    another member inside it makes two names for one directory, under which `inventory` reports a
    revision directory as a draft. A dangling link is refused as well, since `resolve()` does not
    require the target to exist and a path resolving to nothing elsewhere is still not this path.

    The reported path is relative to the root, so a diagnostic never carries a machine-specific
    prefix. That is also why `resolve()`'s own failures are translated rather than raised through:
    an ELOOP surfaces as `RuntimeError`, which is neither a `ProfileBundleError` nor an `OSError`
    and so is caught by nothing on the way out of a command — and its message carries the absolute
    path. A path that cannot be resolved is, by the sentence above, not the file the layout names.
    """
    relative = path.relative_to(bundle_root)
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError) as exc:
        raise SelectionError(
            IssueCode.SYMLINK_REFUSED,
            f"{relative.as_posix()} cannot be resolved to a place in this bundle; a bundle is "
            "self-contained under one root, so every path its identity is computed from must be "
            "the file or directory the layout names",
        ) from exc
    if resolved != resolved_root / relative:
        raise SelectionError(
            IssueCode.SYMLINK_REFUSED,
            f"{relative.as_posix()} does not resolve to its own place in this bundle; a bundle is "
            "self-contained under one root, so every path its identity is computed from must be "
            "the file or directory the layout names and not a link to somewhere else",
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


def identical_trees(left: Path, right: Path) -> bool:
    """Whether two real directories hold exactly the same relative paths and bytes.

    A symlink on either side makes the answer `False` rather than "follow it and compare": a
    symlinked directory is not these bytes, it is a pointer at somebody else's. That includes the
    *root* — a path symlinked at its own comparand would otherwise compare equal by construction,
    and a caller about to delete the loser would delete the only copy.
    """
    left_contents = tree_contents(left)
    return left_contents is not None and left_contents == tree_contents(right)


def tree_contents(root: Path) -> dict[str, bytes] | None:
    """Every relative path under `root` and its bytes, or `None` if `root` is not a real directory.

    Directories are entries too, keyed with a trailing `/` and empty bytes, so a tree that differs
    only by an empty declared directory is not reported as identical.

    `rglob` follows a symlinked root silently, so the root is checked before it is walked.
    """
    if root.is_symlink() or not root.is_dir():
        return None
    contents: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            return None
        contents[relative + "/" if path.is_dir() else relative] = (
            b"" if path.is_dir() else path.read_bytes()
        )
    return contents


__all__ = [
    "SelectedRevision",
    "SelectionError",
    "identical_trees",
    "read_current",
    "read_current_once",
    "require_confined_root",
    "selected_documents",
    "tree_contents",
]
