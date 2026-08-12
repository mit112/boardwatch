"""What a reader sees when a promotion is killed at each of its mutation boundaries (design §6).

The whole crash-consistency claim reduces to one sentence: **before the pointer is replaced a
reader resolves the complete old selection, and after it the complete new one — never a partial
tree.** That is what is asserted here, at every boundary, after a real `SIGKILL`.

## Why a subprocess and a real signal

An exception raised inside the promotion is a *different* failure than a process that stops
existing: the exception unwinds through `finally`, and the `finally` is exactly the code that cleans
up the staging directory. A test that only raised would therefore prove the cleanup works and say
nothing about the case the design is written for. So each boundary is exercised by a child process
that `SIGKILL`s itself, and every assertion afterwards is made by the parent against the filesystem
that child left behind.

The child patches the module's own write primitive, `tempfile.mkdtemp`, `os.rename` and
`os.replace`, which between them are every syscall that changes anything a reader can observe.

## What "readers see a complete tree" is checked with

`read_current_once` plus `selected_documents` — the two functions every command resolves a selection
through — and then a full `validate_bundle` of whatever they returned. Asserting merely that
`CURRENT` still holds the old digest would not catch a torn tree at that digest.
"""

from __future__ import annotations

import signal
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

from boardwatch.profile_bundle.drafts import checkout_current
from boardwatch.profile_bundle.errors import IssueCode
from boardwatch.profile_bundle.inspection import inventory
from boardwatch.profile_bundle.models.history import Actor
from boardwatch.profile_bundle.models.manifests import RevisionManifest
from boardwatch.profile_bundle.paths import (
    LOCK_FILE,
    current_path,
    digest_token,
    draft_root,
    revisions_dir,
)
from boardwatch.profile_bundle.promotion import (
    CURRENT_TEMP_PREFIX,
    PROMOTION_TEMP_PREFIX,
    PromotionRequest,
    promote,
)
from boardwatch.profile_bundle.storage import read_current_once, selected_documents
from boardwatch.profile_bundle.validation import load_documents
from boardwatch.profile_bundle.validation.run import validate_bundle
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from tests.profile_bundle.conftest import approve_draft, materialise, quoted_yaml

FIRST_DRAFT = "baseline"
SECOND_DRAFT = "work"
SKILLS_PATH = PurePosixPath("skills/inventory.yaml")
PROMOTED_AT = datetime(2026, 8, 11, 9, 0, tzinfo=UTC)

#: Every boundary at which the promotion changes something a later reader could observe, in the
#: order they occur. `after_lock` and `after_parent_check` are before any write at all and are here
#: because "no write yet" is itself a claim worth failing.
BEFORE_THE_POINTER = (
    "after_lock",
    "after_parent_check",
    "after_temp_creation",
    "mid_documents",
    "after_reread",
    "before_complete",
    "after_complete",
    "before_rename",
    "after_rename",
    "after_current_write",
    "before_replace",
)

#: The child kills itself at the named point. Boundaries the promotion reaches through its own
#: helpers are hooked on those helpers; the rest are hooked on the syscalls, because a rename and a
#: replace are the only two operations whose completion a reader can detect.
CRASH_WORKER = '''
import os, signal, sys, tempfile
from datetime import datetime
from pathlib import Path

from boardwatch.profile_bundle import promotion
from boardwatch.profile_bundle.models.history import Actor

bundle_root, draft_name, point, created_at = sys.argv[1:5]

real_write = promotion._write_file
real_prepare = promotion._prepare
real_derive = promotion._derive
real_reread = promotion._reread
real_mkdtemp = tempfile.mkdtemp
real_rename = os.rename
real_replace = os.replace
writes = 0


def die(label):
    print("KILLED " + label, flush=True)
    os.kill(os.getpid(), signal.SIGKILL)


def write(path, data):
    global writes
    writes += 1
    name = Path(path).name
    if point == "mid_documents" and writes == 3:
        # A torn document: half the bytes reach the disk and the process stops existing.
        real_write(path, data[: len(data) // 2])
        die(point)
    if point == "before_complete" and name == "COMPLETE":
        die(point)
    real_write(path, data)
    if point == "after_complete" and name == "COMPLETE":
        die(point)
    if point == "after_current_write" and name.startswith(promotion.CURRENT_TEMP_PREFIX):
        die(point)


def mkdtemp(*args, **kwargs):
    made = real_mkdtemp(*args, **kwargs)
    if point == "after_temp_creation":
        die(point)
    return made


def rename(src, dst, **kwargs):
    if point == "before_rename":
        die(point)
    real_rename(src, dst, **kwargs)
    if point == "after_rename":
        die(point)


def replace(src, dst, **kwargs):
    if point == "before_replace":
        die(point)
    real_replace(src, dst, **kwargs)
    if point == "after_replace":
        die(point)


def prepare(*args, **kwargs):
    if point == "after_lock":
        die(point)
    return real_prepare(*args, **kwargs)


def derive(*args, **kwargs):
    if point == "after_parent_check":
        die(point)
    return real_derive(*args, **kwargs)


def reread(*args, **kwargs):
    result = real_reread(*args, **kwargs)
    if point == "after_reread":
        die(point)
    return result


promotion._write_file = write
promotion._prepare = prepare
promotion._derive = derive
promotion._reread = reread
tempfile.mkdtemp = mkdtemp
os.rename = rename
os.replace = replace

outcome = promotion.promote(
    Path(bundle_root),
    promotion.PromotionRequest(
        draft_name=draft_name,
        summary="Crash matrix",
        actor=Actor.OWNER,
        created_at=datetime.fromisoformat(created_at),
    ),
)
print("RETURNED", outcome.exit_code, [d.code for d in outcome.diagnostics], flush=True)
'''


# --------------------------------------------------------------------------------------
# Scene
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Scene:
    """Revision 1 promoted, and an approved draft of it waiting to become revision 2."""

    bundle_root: Path
    first: Path
    first_digest: str
    draft: Path


def _request(name: str) -> PromotionRequest:
    return PromotionRequest(
        draft_name=name,
        summary="Crash matrix",
        actor=Actor.OWNER,
        created_at=PROMOTED_AT,
    )


def _edit(root: Path, logical: PurePosixPath, mutate: Callable[[Any], None]) -> None:
    path = root / logical
    data = load_yaml_bytes(path.read_bytes(), logical_path=logical)
    mutate(data)
    path.write_bytes(quoted_yaml(data, logical_path=logical))


@pytest.fixture
def scene(tmp_path: Path) -> Scene:
    bundle_root = tmp_path / "career-profile"
    bundle_root.mkdir()
    bundle = materialise(bundle_root, draft_name=FIRST_DRAFT)
    approve_draft(bundle_root, bundle.draft, approved_at=PROMOTED_AT)
    first = promote(bundle_root, _request(FIRST_DRAFT))
    assert first.exit_code == 0, first.diagnostics
    assert first.value is not None

    assert checkout_current(bundle_root, name=SECOND_DRAFT).exit_code == 0
    draft = draft_root(bundle_root, SECOND_DRAFT)
    _edit(
        draft,
        SKILLS_PATH,
        lambda data: data["skills"][0].update({"canonical_name": "Crash Matrix Revision"}),
    )
    approve_draft(
        bundle_root,
        draft,
        parent=first.value.root,
        stamp_id="approval-stamp.000002",
        approved_at=PROMOTED_AT,
    )
    return Scene(
        bundle_root=bundle_root,
        first=first.value.root,
        first_digest=first.value.bundle_digest,
        draft=draft,
    )


def _crash(scene: Scene, point: str) -> subprocess.CompletedProcess[str]:
    """Run a promotion in a child process that kills itself at `point`."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            CRASH_WORKER,
            str(scene.bundle_root),
            SECOND_DRAFT,
            point,
            PROMOTED_AT.isoformat(),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert f"KILLED {point}" in result.stdout, result.stdout + result.stderr
    assert result.returncode == -signal.SIGKILL, (
        f"the child returned {result.returncode} rather than dying: {result.stdout}{result.stderr}"
    )
    return result


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != LOCK_FILE
    }


def _resolved_and_complete(bundle_root: Path) -> tuple[int, str]:
    """Resolve the selection the way every command does, and prove the tree is whole.

    Returns the revision and digest so a caller can say which selection it found; raising here would
    be the finding, because a torn tree makes one of these three steps fail.
    """
    selection = read_current_once(bundle_root)
    documents = selected_documents(selection)
    manifest = documents.manifest
    assert isinstance(manifest, RevisionManifest)
    outcome = validate_bundle(selection.root, bundle_root=bundle_root, mode="revision")
    assert outcome.exit_code == 0, outcome.diagnostics
    return selection.revision, selection.bundle_digest


def _temporaries(bundle_root: Path) -> list[str]:
    return sorted(
        entry.name
        for entry in revisions_dir(bundle_root).iterdir()
        if entry.name.startswith(PROMOTION_TEMP_PREFIX)
    )


# --------------------------------------------------------------------------------------
# The matrix
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("point", BEFORE_THE_POINTER)
def test_a_kill_before_the_pointer_leaves_the_complete_old_selection(
    scene: Scene, point: str
) -> None:
    """Every boundary up to and including the last write before `os.replace`."""
    draft_before = _snapshot(scene.draft)
    first_before = _snapshot(scene.first)

    _crash(scene, point)

    assert _resolved_and_complete(scene.bundle_root) == (1, scene.first_digest)
    assert _snapshot(scene.first) == first_before
    # §21: a refusal, an interruption, and a success all leave the draft alone.
    assert _snapshot(scene.draft) == draft_before


def test_a_kill_immediately_after_the_pointer_replace_selects_the_new_revision(
    scene: Scene,
) -> None:
    """The commit point is one `os.replace`, so the instant after it the new revision is live."""
    _crash(scene, "after_replace")

    revision, digest = _resolved_and_complete(scene.bundle_root)
    assert revision == 2
    assert digest != scene.first_digest
    # The old revision is retained, not replaced: §21 keeps every promoted revision.
    assert scene.first.is_dir()


@pytest.mark.parametrize("point", ["mid_documents", "after_reread", "before_complete"])
def test_a_partial_tree_is_never_reachable_from_the_pointer(scene: Scene, point: str) -> None:
    """The torn trees, named explicitly: none of them has a `COMPLETE`, so none is selectable.

    `after_rename` is deliberately not in this list — that tree is complete by then, and being
    complete-but-unselected is a state §6 expects and `inventory` reports.
    """
    _crash(scene, point)

    for staged in _temporaries(scene.bundle_root):
        for candidate in sorted((revisions_dir(scene.bundle_root) / staged).iterdir()):
            assert not (candidate / "COMPLETE").exists()
    assert read_current_once(scene.bundle_root).revision == 1


@pytest.mark.parametrize("point", ["after_temp_creation", "mid_documents", "after_complete"])
def test_inventory_reports_what_a_killed_promotion_left(scene: Scene, point: str) -> None:
    """§6: `inventory` reports incomplete temporary directories, and adopts none of them."""
    _crash(scene, point)

    outcome = inventory(scene.bundle_root)

    assert outcome.value is not None
    assert outcome.value.temporary_entries == tuple(_temporaries(scene.bundle_root))
    assert outcome.value.temporary_entries != ()
    assert outcome.value.selected is not None
    assert outcome.value.selected.revision == 1
    assert any(
        finding.code == IssueCode.ORPHANED_ARTEFACT for finding in outcome.diagnostics
    )


def test_a_kill_after_the_rename_leaves_a_complete_but_unselected_revision(
    scene: Scene,
) -> None:
    """Step 7 done, step 8 not: the directory is whole and nothing points at it yet."""
    _crash(scene, "after_rename")

    assert read_current_once(scene.bundle_root).revision == 1
    outcome = inventory(scene.bundle_root)
    assert outcome.value is not None
    assert len(outcome.value.unselected_revisions) == 1
    assert outcome.value.incomplete_revisions == ()


# --------------------------------------------------------------------------------------
# Retrying after the crash
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("point", BEFORE_THE_POINTER)
def test_the_same_promotion_succeeds_after_any_crash_before_the_pointer(
    scene: Scene, point: str
) -> None:
    """The recovery the whole protocol exists for, including through the exact-target reuse path.

    A crash at `after_rename` leaves the digest target already in place, so the retry takes §6 step
    7's reuse branch; every other boundary leaves it absent and the retry renames its own tree in.
    Both must end with the same selected revision, because the digest is content and the content did
    not change.
    """
    _crash(scene, point)

    outcome = promote(scene.bundle_root, _request(SECOND_DRAFT))

    assert outcome.exit_code == 0, outcome.diagnostics
    assert outcome.value is not None
    assert _resolved_and_complete(scene.bundle_root) == (2, outcome.value.bundle_digest)


def test_a_crashed_promotion_does_not_leave_the_lock_held(scene: Scene) -> None:
    """The kernel drops a dead process's lock; §6 forbids ever breaking one on file existence."""
    _crash(scene, "after_complete")

    assert (scene.bundle_root / LOCK_FILE).exists(), "the lockfile is expected to survive"
    assert promote(scene.bundle_root, _request(SECOND_DRAFT)).exit_code == 0


def test_a_retry_after_a_torn_document_write_does_not_reuse_the_torn_bytes(
    scene: Scene,
) -> None:
    """The torn tree is retained and ignored; the retry builds its own from the draft."""
    _crash(scene, "mid_documents")
    torn = _temporaries(scene.bundle_root)
    assert len(torn) == 1

    outcome = promote(scene.bundle_root, _request(SECOND_DRAFT))

    assert outcome.exit_code == 0, outcome.diagnostics
    assert outcome.value is not None
    torn_tree = (
        revisions_dir(scene.bundle_root) / torn[0] / digest_token(outcome.value.bundle_digest)
    )
    assert torn_tree.is_dir(), "the killed attempt staged the same digest name"
    assert _snapshot(outcome.value.root) != _snapshot(torn_tree), (
        "the installed revision must be the retry's own bytes, not the half-written ones"
    )
    assert load_documents(outcome.value.root, mode="revision").by_path[SKILLS_PATH] == (
        load_documents(scene.draft, mode="draft").by_path[SKILLS_PATH]
    )
    assert torn[0] in _temporaries(scene.bundle_root), "the torn tree must be retained, not deleted"


def test_the_pointer_is_never_absent_between_the_two_selections(scene: Scene) -> None:
    """`os.replace` rather than unlink-then-write: a bundle never briefly selects nothing."""
    _crash(scene, "after_current_write")

    assert current_path(scene.bundle_root).exists()
    assert _resolved_and_complete(scene.bundle_root) == (1, scene.first_digest)
    staged = [
        entry.name
        for entry in scene.bundle_root.iterdir()
        if entry.name.startswith(CURRENT_TEMP_PREFIX)
    ]
    assert len(staged) == 1, "the staged pointer is expected to survive the kill"
