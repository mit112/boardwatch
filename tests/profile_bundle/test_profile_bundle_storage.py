"""One-read selection of the immutable current revision (design §6, §21).

§6's reader contract is four clauses long and every one of them is a way a reader can end up
serving a tree nobody selected: read `CURRENT` exactly once, resolve the digest-named directory,
require `COMPLETE`, verify the manifest's identity. These tests pin each clause separately, because
a reader that satisfied three of them would still hand back a coherent-looking wrong answer.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import FrameType

import pytest

from boardwatch.profile_bundle.errors import IssueCode
from boardwatch.profile_bundle.models.manifests import RevisionManifest
from boardwatch.profile_bundle.paths import (
    CURRENT_FILE,
    DRAFTS_DIR,
    LOCAL_SOURCES_FILE,
    LOCK_FILE,
    ROOT_MEMBERS,
    blobs_dir,
    complete_marker_path,
    current_path,
    digest_token,
    drafts_dir,
    revision_root,
    revisions_dir,
)
from boardwatch.profile_bundle.storage import (
    SelectionError,
    identical_trees,
    read_current_once,
    selected_documents,
    tree_contents,
)
from tests.profile_bundle.conftest import PromotedRevisionTree, example_source_root

OTHER_DIGEST = "sha256:" + "f" * 64


def _write_pointer(bundle_root: Path, payload: object) -> None:
    current_path(bundle_root).write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )


def test_a_promoted_bundle_selects_its_digest_named_directory(
    promoted_tree: PromotedRevisionTree,
) -> None:
    selection = read_current_once(promoted_tree.bundle_root)
    assert selection.root == promoted_tree.revision_dir
    assert selection.bundle_digest == promoted_tree.bundle_digest
    assert selection.revision == promoted_tree.revision
    assert selection.root.name == digest_token(promoted_tree.bundle_digest)


def test_a_bundle_with_no_pointer_reports_no_current_revision(tmp_path: Path) -> None:
    """The state `init` exists to leave behind, so it must be its own typed answer rather than an
    I/O failure an operator has to interpret."""
    root = tmp_path / "career-profile"
    root.mkdir()
    with pytest.raises(SelectionError) as raised:
        read_current_once(root)
    assert raised.value.code is IssueCode.NO_CURRENT_REVISION


def test_a_torn_pointer_is_refused_rather_than_repaired(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """Extra bytes after the object are an interrupted write, not a pointer with a comment."""
    path = current_path(promoted_tree.bundle_root)
    path.write_text(path.read_text(encoding="utf-8") + "{tru", encoding="utf-8")
    with pytest.raises(SelectionError) as raised:
        read_current_once(promoted_tree.bundle_root)
    assert raised.value.code is IssueCode.CURRENT_POINTER_MISMATCH


def test_a_pointer_naming_an_absent_revision_is_refused(
    promoted_tree: PromotedRevisionTree,
) -> None:
    _write_pointer(promoted_tree.bundle_root, {"bundle_digest": OTHER_DIGEST, "revision": 1})
    with pytest.raises(SelectionError) as raised:
        read_current_once(promoted_tree.bundle_root)
    assert raised.value.code is IssueCode.CURRENT_POINTER_MISMATCH


def test_a_selected_directory_without_its_marker_is_refused(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """§6 step 6 writes `COMPLETE` last, so its absence means the tree is a torn promotion."""
    complete_marker_path(promoted_tree.revision_dir).unlink()
    with pytest.raises(SelectionError) as raised:
        read_current_once(promoted_tree.bundle_root)
    assert raised.value.code is IssueCode.COMPLETE_MARKER_MISSING


def test_a_marker_naming_another_digest_is_refused(promoted_tree: PromotedRevisionTree) -> None:
    complete_marker_path(promoted_tree.revision_dir).write_text(
        f"{OTHER_DIGEST}\n", encoding="utf-8"
    )
    with pytest.raises(SelectionError) as raised:
        read_current_once(promoted_tree.bundle_root)
    assert raised.value.code is IssueCode.CURRENT_POINTER_MISMATCH


def test_a_symlinked_pointer_is_refused(promoted_tree: PromotedRevisionTree, tmp_path: Path) -> None:
    """Confinement: a symlinked `CURRENT` selects a revision named by a file outside the root."""
    outside = tmp_path / "elsewhere-CURRENT"
    outside.write_text(current_path(promoted_tree.bundle_root).read_text(encoding="utf-8"))
    current_path(promoted_tree.bundle_root).unlink()
    current_path(promoted_tree.bundle_root).symlink_to(outside)
    with pytest.raises(SelectionError) as raised:
        read_current_once(promoted_tree.bundle_root)
    assert raised.value.code is IssueCode.SYMLINK_REFUSED


def test_a_symlinked_revision_directory_is_refused(
    promoted_tree: PromotedRevisionTree, tmp_path: Path
) -> None:
    """`discover_source_files` refuses symlinks it walks past, but never sees the tree root itself,
    so a symlinked revision directory would import a whole tree from outside the bundle."""
    outside = tmp_path / "elsewhere-revision"
    promoted_tree.revision_dir.rename(outside)
    promoted_tree.revision_dir.symlink_to(outside, target_is_directory=True)
    with pytest.raises(SelectionError) as raised:
        read_current_once(promoted_tree.bundle_root)
    assert raised.value.code is IssueCode.SYMLINK_REFUSED


@pytest.mark.parametrize("member", sorted(ROOT_MEMBERS))
def test_every_declared_root_member_is_refused_as_a_symlink(
    promoted_tree: PromotedRevisionTree, tmp_path: Path, member: str
) -> None:
    """§6: the bundle is self-contained under one root, so no declared member may leave it.

    Parametrised over `ROOT_MEMBERS` itself rather than over the members these commands happen to
    touch today: `approvals/` and `revisions/` hold nothing until promotion writes them, and a
    per-directory guard would leave those two escapes armed for the slice that does.
    """
    inside = promoted_tree.bundle_root / member
    outside = tmp_path / f"outside-{member}"
    if inside.exists():
        inside.rename(outside)
    elif member in {CURRENT_FILE, LOCK_FILE, LOCAL_SOURCES_FILE}:
        outside.write_text("elsewhere\n", encoding="utf-8")
    else:
        outside.mkdir()
    inside.symlink_to(outside, target_is_directory=outside.is_dir())

    with pytest.raises(SelectionError) as raised:
        read_current_once(promoted_tree.bundle_root)
    assert raised.value.code is IssueCode.SYMLINK_REFUSED
    assert member in str(raised.value)


def test_a_member_that_aliases_another_member_inside_the_root_is_refused(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """Confinement is "resolves to its own place", not "resolves somewhere under the root".

    Nothing leaves the root here, so a rule about the boundary alone would admit it — and two names
    for one directory is how `inventory` came to report content as something it is not: with
    `drafts/` resolving to `revisions/`, a digest-named revision directory satisfies the draft-name
    grammar and is listed as a draft of this bundle.
    """
    drafts = drafts_dir(promoted_tree.bundle_root)
    if drafts.exists():
        shutil.rmtree(drafts)
    drafts.symlink_to(revisions_dir(promoted_tree.bundle_root), target_is_directory=True)

    with pytest.raises(SelectionError) as raised:
        read_current_once(promoted_tree.bundle_root)
    assert raised.value.code is IssueCode.SYMLINK_REFUSED
    assert DRAFTS_DIR in str(raised.value)


def test_a_symlink_loop_in_a_declared_member_is_a_typed_refusal(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """A symlink loop is refused on every interpreter this project supports.

    They do different things with it and both are wrong: on CPython 3.11 and 3.12 `Path.resolve()` raises
    `RuntimeError`, which is neither a `ProfileBundleError` nor an `OSError` and so reaches the
    operator as a traceback carrying the absolute bundle path; on 3.13 it returns the loop's own
    path, which satisfies an equality against the derived location and admits the escape entirely.
    Asserted as one outcome rather than parametrised by version, because the refusal is the contract
    and the version is the thing that must not show through it. CI runs 3.11, 3.12 and 3.13.
    """
    drafts = drafts_dir(promoted_tree.bundle_root)
    if drafts.exists():
        shutil.rmtree(drafts)
    os.symlink(DRAFTS_DIR, drafts)

    with pytest.raises(SelectionError) as raised:
        read_current_once(promoted_tree.bundle_root)
    assert raised.value.code is IssueCode.SYMLINK_REFUSED
    assert DRAFTS_DIR in str(raised.value)
    # The `RuntimeError` this replaces carried the absolute bundle path in its message.
    assert str(promoted_tree.bundle_root) not in str(raised.value)


def test_a_blob_store_entry_that_is_not_a_regular_file_is_refused(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """A FIFO resolves to its own place, so an equality against that place admits it — and the
    first command to read the store then blocks in `open()` with no timeout and no diagnostic.

    Named-pipe bytes are also not content anything can address by digest, so this is the same
    sentence as every other confinement refusal rather than a new rule: the store holds the files
    the layout names, and a pipe is not one.
    """
    store = blobs_dir(promoted_tree.bundle_root)
    store.mkdir(parents=True, exist_ok=True)
    os.mkfifo(store / ("sha256-" + "b" * 64))

    with pytest.raises(SelectionError) as raised:
        read_current_once(promoted_tree.bundle_root)
    assert raised.value.code is IssueCode.UNKNOWN_FILE
    assert str(promoted_tree.bundle_root) not in str(raised.value)


def test_the_pointer_is_read_exactly_once(
    promoted_tree: PromotedRevisionTree, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The core of §6's lock-free reader contract.

    A second read is the bug this test exists to catch: a promotion landing between two reads would
    give one operation a revision number from before it and a digest from after it.
    """
    calls = _count_pointer_reads(monkeypatch)
    selection = read_current_once(promoted_tree.bundle_root)
    assert calls == [1]
    assert selection.bundle_digest == promoted_tree.bundle_digest


def test_the_selected_documents_are_the_selected_revisions(
    promoted_tree: PromotedRevisionTree,
) -> None:
    documents = selected_documents(read_current_once(promoted_tree.bundle_root))
    manifest = documents.manifest
    assert isinstance(manifest, RevisionManifest)
    assert manifest.bundle_digest == promoted_tree.bundle_digest


def test_a_manifest_that_disagrees_with_the_pointer_is_refused(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """§6: the reader verifies manifest identity. Both directories are retained on disk, so a
    pointer that selects the wrong one must be refused rather than served."""
    stolen = revisions_dir(promoted_tree.bundle_root) / digest_token(OTHER_DIGEST)
    promoted_tree.revision_dir.rename(stolen)
    complete_marker_path(stolen).write_text(f"{OTHER_DIGEST}\n", encoding="utf-8")
    _write_pointer(promoted_tree.bundle_root, {"bundle_digest": OTHER_DIGEST, "revision": 1})
    with pytest.raises(SelectionError) as raised:
        selected_documents(read_current_once(promoted_tree.bundle_root))
    assert raised.value.code is IssueCode.CURRENT_POINTER_MISMATCH


def test_a_pointer_that_renumbers_the_same_digest_is_refused(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """The digest half and the number half are checked separately because they can disagree.

    `revision` is inside the manifest and therefore inside the bundle digest, so this state is only
    reachable by editing `CURRENT` — which is exactly the hand edit that would otherwise let a
    reader report a revision number no promotion ever produced.
    """
    _write_pointer(
        promoted_tree.bundle_root,
        {"bundle_digest": promoted_tree.bundle_digest, "revision": promoted_tree.revision + 41},
    )
    with pytest.raises(SelectionError) as raised:
        selected_documents(read_current_once(promoted_tree.bundle_root))
    assert raised.value.code is IssueCode.CURRENT_POINTER_MISMATCH


def test_a_draft_manifest_inside_a_revision_directory_is_refused(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """A draft tree moved under `revisions/` carries the `""` sentinels, so nothing it says about
    its own identity is checkable; it must not become a selection."""
    target = revision_root(promoted_tree.bundle_root, promoted_tree.bundle_digest)
    (target / "manifest.yaml").write_bytes(
        (example_source_root() / "manifest.yaml").read_bytes()
    )
    with pytest.raises(SelectionError) as raised:
        selected_documents(read_current_once(promoted_tree.bundle_root))
    assert raised.value.code is IssueCode.DRAFT_MANIFEST_INVALID


def _count_pointer_reads(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Patch the pointer reader so a second call returns a DIFFERENT selection.

    Returned as a one-element list so a caller reads the count after the operation; the point is
    both that the count is 1 and that the divergent second value never reaches the result.
    """
    from boardwatch.profile_bundle import storage
    from boardwatch.profile_bundle.validation.digest import CurrentPointer

    real = storage.read_current
    seen = [0]

    def counting(bundle_root: Path) -> CurrentPointer:
        seen[0] += 1
        if seen[0] == 1:
            return real(bundle_root)
        return CurrentPointer(bundle_digest=OTHER_DIGEST, revision=99)

    monkeypatch.setattr(storage, "read_current", counting)
    return seen


# --------------------------------------------------------------------------------------
# The tree comparison two commands stake a deletion on
# --------------------------------------------------------------------------------------


def _pair(tmp_path: Path) -> tuple[Path, Path]:
    """Two byte-identical trees, each with a document and a nested directory."""
    made: list[Path] = []
    for name in ("left", "right"):
        root = tmp_path / name
        (root / "skills").mkdir(parents=True)
        (root / "skills" / "inventory.yaml").write_bytes(b"skills: []\n")
        made.append(root)
    return made[0], made[1]


def test_two_trees_holding_the_same_bytes_are_identical(tmp_path: Path) -> None:
    """The positive control for everything below: without it, refusing everything would pass."""
    left, right = _pair(tmp_path)

    assert identical_trees(left, right)
    assert tree_contents(left) == {"skills/": b"", "skills/inventory.yaml": b"skills: []\n"}


def test_a_symlinked_entry_is_not_the_bytes_it_points_at(tmp_path: Path) -> None:
    """`promote` and `rebase-draft` both DELETE on this answer, so a link must not compare equal.

    Nothing else would catch it: the two trees hold the same bytes under the same relative paths,
    and the winner of that comparison is the one that is kept. `promote` would exit 0 having
    selected a revision holding a symlinked document, which `load_documents` then refuses to read at
    all, and it would have discarded the real tree it staged.
    """
    left, right = _pair(tmp_path)
    document = right / "skills" / "inventory.yaml"
    elsewhere = tmp_path / "outside.yaml"
    elsewhere.write_bytes(document.read_bytes())
    document.unlink()
    document.symlink_to(elsewhere)
    assert document.read_bytes() == (left / "skills" / "inventory.yaml").read_bytes()

    assert tree_contents(right) is None
    assert not identical_trees(left, right)
    assert not identical_trees(right, left)


def test_a_symlinked_root_is_not_the_tree_it_points_at(tmp_path: Path) -> None:
    """The root is the case an implementation that only checked entries would compare equal to
    itself, and the caller about to delete the loser would delete the only copy."""
    left, right = _pair(tmp_path)
    link = tmp_path / "link"
    link.symlink_to(right, target_is_directory=True)

    assert tree_contents(link) is None
    assert not identical_trees(link, right)
    assert not identical_trees(right, link)


@pytest.mark.skipif(os.name != "posix", reason="mkfifo and SIGALRM are POSIX")
def test_a_named_pipe_is_not_content_and_does_not_block_the_comparison(tmp_path: Path) -> None:
    """A FIFO is neither a symlink nor a directory, so it used to reach `read_bytes()`.

    `open()` on a FIFO with no writer blocks forever, and `promote` reaches this comparison over a
    `revisions/sha256-<digest>/` directory it did not write, while holding the bundle lock — so the
    hang is not one stuck command but every writer refused until an operator notices. The deadline
    below is what makes the old behaviour a failure rather than a suite that never finishes.
    """
    left, right = _pair(tmp_path)
    os.mkfifo(right / "skills" / "blocked.fifo")

    with _deadline(10.0):
        assert tree_contents(right) is None
        assert not identical_trees(left, right)
        assert not identical_trees(right, left)


@contextmanager
def _deadline(seconds: float) -> Iterator[None]:
    """Turn a block into a failure. `open()` on a FIFO is interruptible, and the handler raises, so
    Python does not retry it the way PEP 475 otherwise would."""

    def fire(signum: int, frame: FrameType | None) -> None:
        raise TimeoutError(f"still running after {seconds}s")

    previous = signal.signal(signal.SIGALRM, fire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
