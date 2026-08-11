"""Two promoters, one parent, and the readers running alongside them (design §6, §21).

Concurrency here is genuinely concurrent: every writer is a real subprocess, because the properties
under test belong to the operating system. An in-process double would hold no kernel lock and would
prove only that the double behaves like the double.

**Exactly one winner.** Two promotions from one parent cannot both produce revision N. Which one
loses is timing, but *how* it loses is not: either it never got the lock (`bundle_lock_held`, exit
3) or it got the lock after the winner released it and found the parent had moved
(`stale_draft_parent`, exit 1). Both leave the loser's draft exactly as it was, because `rebase-draft`
is the drain and it needs the draft.

**Readers never need the lock.** §6 gives them a four-clause contract instead, and the loop below is
what that contract is for: while a promotion runs, every read resolves either the complete old
revision or the complete new one.
"""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import pytest

from boardwatch.profile_bundle.drafts import checkout_current
from boardwatch.profile_bundle.errors import IssueCode
from boardwatch.profile_bundle.models.history import Actor
from boardwatch.profile_bundle.paths import (
    LOCK_FILE,
    draft_root,
    lock_path,
    revisions_dir,
)
from boardwatch.profile_bundle.promotion import (
    PROMOTION_TEMP_PREFIX,
    PromotionRequest,
    promote,
)
from boardwatch.profile_bundle.storage import read_current_once, selected_documents
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from tests.profile_bundle.conftest import approve_draft, materialise, quoted_yaml

FIRST_DRAFT = "baseline"
SKILLS_PATH = PurePosixPath("skills/inventory.yaml")
PROMOTED_AT = datetime(2026, 8, 11, 9, 0, tzinfo=UTC)

#: One promotion, its outcome printed as a line the parent can parse. Kept deliberately small: the
#: thing being measured is what two of these do to one bundle, not what either does alone.
PROMOTER = """
import sys
from datetime import datetime
from pathlib import Path

from boardwatch.profile_bundle.models.history import Actor
from boardwatch.profile_bundle.promotion import PromotionRequest, promote

outcome = promote(
    Path(sys.argv[1]),
    PromotionRequest(
        draft_name=sys.argv[2],
        summary="Concurrent promotion of " + sys.argv[2],
        actor=Actor.OWNER,
        created_at=datetime.fromisoformat(sys.argv[3]),
    ),
)
print(outcome.exit_code, ",".join(d.code for d in outcome.diagnostics), flush=True)
"""


@dataclass(frozen=True)
class Outcome:
    exit_code: int
    codes: tuple[str, ...]


@dataclass(frozen=True)
class Scene:
    """Revision 1 promoted, and two independently approved drafts of it."""

    bundle_root: Path
    first_digest: str
    drafts: tuple[str, ...]


def _request(name: str) -> PromotionRequest:
    return PromotionRequest(
        draft_name=name,
        summary=f"Concurrent promotion of {name}",
        actor=Actor.OWNER,
        created_at=PROMOTED_AT,
    )


def _rename_skill(draft: Path, name: str) -> None:
    data = load_yaml_bytes((draft / SKILLS_PATH).read_bytes(), logical_path=SKILLS_PATH)
    data["skills"][0]["canonical_name"] = name
    (draft / SKILLS_PATH).write_bytes(quoted_yaml(data, logical_path=SKILLS_PATH))


@pytest.fixture
def scene(tmp_path: Path) -> Scene:
    bundle_root = tmp_path / "career-profile"
    bundle_root.mkdir()
    bundle = materialise(bundle_root, draft_name=FIRST_DRAFT)
    approve_draft(bundle_root, bundle.draft, approved_at=PROMOTED_AT)
    first = promote(bundle_root, _request(FIRST_DRAFT))
    assert first.exit_code == 0, first.diagnostics
    assert first.value is not None

    names = ("alpha", "beta")
    for index, name in enumerate(names):
        assert checkout_current(bundle_root, name=name).exit_code == 0
        draft = draft_root(bundle_root, name)
        _rename_skill(draft, f"Concurrent {name}")
        approve_draft(
            bundle_root,
            draft,
            parent=first.value.root,
            stamp_id=f"approval-stamp.00000{index + 2}",
            approved_at=PROMOTED_AT,
        )
    return Scene(
        bundle_root=bundle_root, first_digest=first.value.bundle_digest, drafts=names
    )


def _start(bundle_root: Path, name: str) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "-c", PROMOTER, str(bundle_root), name, PROMOTED_AT.isoformat()],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _finish(process: subprocess.Popen[str]) -> Outcome:
    stdout, stderr = process.communicate(timeout=180)
    assert process.returncode == 0, stderr
    exit_code, _, codes = stdout.strip().partition(" ")
    return Outcome(exit_code=int(exit_code), codes=tuple(c for c in codes.split(",") if c))


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != LOCK_FILE
    }


def _revision_directories(bundle_root: Path) -> list[str]:
    return sorted(
        entry.name
        for entry in revisions_dir(bundle_root).iterdir()
        if not entry.name.startswith(PROMOTION_TEMP_PREFIX)
    )


# --------------------------------------------------------------------------------------
# Two writers
# --------------------------------------------------------------------------------------


def test_two_promotions_from_one_parent_produce_exactly_one_winner(scene: Scene) -> None:
    before = {name: _snapshot(draft_root(scene.bundle_root, name)) for name in scene.drafts}

    processes = [_start(scene.bundle_root, name) for name in scene.drafts]
    outcomes = [_finish(process) for process in processes]

    winners = [outcome for outcome in outcomes if outcome.exit_code == 0]
    losers = [outcome for outcome in outcomes if outcome.exit_code != 0]
    assert len(winners) == 1, outcomes
    assert len(losers) == 1
    loser = losers[0]
    # The two ways to lose, and no third: never got the lock, or got it and found the parent moved.
    if loser.exit_code == 3:
        assert loser.codes == (IssueCode.BUNDLE_LOCK_HELD,)
    else:
        assert loser.exit_code == 1
        assert loser.codes == (IssueCode.STALE_DRAFT_PARENT,)
    # Both drafts survive whatever happened: the loser needs its own for `rebase-draft`, and the
    # winner's is not promotion's to remove.
    assert {name: _snapshot(draft_root(scene.bundle_root, name)) for name in scene.drafts} == before
    # One parent, one child: two revision directories in total, not three.
    assert len(_revision_directories(scene.bundle_root)) == 2
    assert read_current_once(scene.bundle_root).revision == 2


def test_the_loser_of_a_serialised_race_is_refused_for_a_stale_parent(scene: Scene) -> None:
    """The same race, forced to serialise, so the second outcome is deterministic."""
    first = _finish(_start(scene.bundle_root, scene.drafts[0]))
    assert first.exit_code == 0

    second = _finish(_start(scene.bundle_root, scene.drafts[1]))

    assert second.exit_code == 1
    assert second.codes == (IssueCode.STALE_DRAFT_PARENT,)
    assert len(_revision_directories(scene.bundle_root)) == 2


def test_promoting_the_same_draft_twice_is_refused_the_second_time(scene: Scene) -> None:
    """The draft is not consumed, so the refusal has to come from the parent recheck."""
    first = _finish(_start(scene.bundle_root, scene.drafts[0]))
    assert first.exit_code == 0
    before = _snapshot(draft_root(scene.bundle_root, scene.drafts[0]))

    second = _finish(_start(scene.bundle_root, scene.drafts[0]))

    assert second.exit_code == 1
    assert second.codes == (IssueCode.STALE_DRAFT_PARENT,)
    assert _snapshot(draft_root(scene.bundle_root, scene.drafts[0])) == before


def test_a_promotion_in_flight_refuses_a_second_writer_without_waiting(scene: Scene) -> None:
    """Contention is refused, not queued: §6 and §21 both say no wait and no mutation."""
    from boardwatch.profile_bundle.locking import bundle_lock

    with bundle_lock(scene.bundle_root):
        started = time.monotonic()
        outcome = promote(scene.bundle_root, _request(scene.drafts[0]))
        elapsed = time.monotonic() - started

    assert outcome.exit_code == 3
    assert [finding.code for finding in outcome.diagnostics] == [IssueCode.BUNDLE_LOCK_HELD]
    assert elapsed < 2.0
    assert read_current_once(scene.bundle_root).revision == 1


def test_a_lockfile_left_by_a_killed_promoter_is_not_a_held_lock(scene: Scene) -> None:
    """§6: never break a lock on file existence. The kernel released this one; the file remains.

    The child is killed only once its lockfile is on disk. Killing it the instant it starts proved
    nothing — most of a promoter's life is importing, so the process died before `filelock` had
    created anything and the leftover this test is about never existed.
    """
    process = _start(scene.bundle_root, scene.drafts[0])
    deadline = time.monotonic() + 60
    while not lock_path(scene.bundle_root).exists() and time.monotonic() < deadline:
        assert process.poll() is None, "the promoter exited before it took the lock"
    assert lock_path(scene.bundle_root).exists(), "the promoter never created its lockfile"
    process.kill()
    process.wait()
    assert lock_path(scene.bundle_root).exists(), "the killed holder's lockfile is the whole point"

    outcome = promote(scene.bundle_root, _request(scene.drafts[1]))

    assert outcome.exit_code == 0, outcome.diagnostics
    # Deliberately no assertion about the lockfile afterwards: §6 says its presence carries no
    # meaning in either direction, and whether `filelock` unlinks it on release differs between the
    # versions the declared floor admits. A test that pinned it would pin the thing the design says
    # not to depend on.


# --------------------------------------------------------------------------------------
# Readers, which take no lock at all
# --------------------------------------------------------------------------------------


def test_a_lock_free_reader_only_ever_sees_a_complete_tree(scene: Scene) -> None:
    """Repeatedly resolve a selection while a promotion runs, and prove every answer is whole.

    Each observation goes through the reader's own path — one pointer read, resolve the digest-named
    directory, require `COMPLETE`, verify the manifest's identity — and then parses the tree. A torn
    tree, a directory without its marker, or a pointer naming something half-written would raise.
    """
    process = _start(scene.bundle_root, scene.drafts[0])
    seen: set[tuple[int, str]] = set()
    try:
        while process.poll() is None:
            selection = read_current_once(scene.bundle_root)
            documents = selected_documents(selection)
            assert documents.by_path, "the selected tree parsed as empty"
            seen.add((selection.revision, selection.bundle_digest))
    finally:
        outcome = _finish(process)

    assert outcome.exit_code == 0, outcome.codes
    final = read_current_once(scene.bundle_root)
    seen.add((final.revision, final.bundle_digest))
    # Only two selections are admissible at any point: the old one and the new one.
    assert seen <= {(1, scene.first_digest), (2, final.bundle_digest)}
    assert (2, final.bundle_digest) in seen


def test_a_reader_is_never_handed_a_revision_the_pointer_does_not_name(scene: Scene) -> None:
    """The identity clause: what a reader parses must be the tree `CURRENT` selected."""
    process = _start(scene.bundle_root, scene.drafts[0])
    try:
        while process.poll() is None:
            selection = read_current_once(scene.bundle_root)
            manifest = selected_documents(selection).manifest
            assert getattr(manifest, "bundle_digest", None) == selection.bundle_digest
    finally:
        assert _finish(process).exit_code == 0


def test_the_loser_can_still_rebase_and_promote_afterwards(scene: Scene) -> None:
    """The refusal has to leave a recoverable situation, or `stale_draft_parent` is a dead end."""
    from boardwatch.profile_bundle.rebase import rebase_draft

    assert _finish(_start(scene.bundle_root, scene.drafts[0])).exit_code == 0
    assert _finish(_start(scene.bundle_root, scene.drafts[1])).exit_code == 1

    rebased = rebase_draft(scene.bundle_root, name=scene.drafts[1])
    assert rebased.exit_code == 1, "both drafts renamed one skill, so the rebase must conflict"
    assert [finding.code for finding in rebased.diagnostics] == [IssueCode.DRAFT_REBASE_CONFLICT]

    # Resolving it the way the owner would: take the selected revision's value and re-approve.
    draft = draft_root(scene.bundle_root, scene.drafts[1])
    selection = read_current_once(scene.bundle_root)
    _rename_skill(draft, "Resolved By The Owner")
    manifest_path = draft / "manifest.yaml"
    manifest = load_yaml_bytes(manifest_path.read_bytes(), logical_path=PurePosixPath("manifest.yaml"))
    manifest["draft_of_revision"] = selection.revision
    manifest["parent_bundle_digest"] = selection.bundle_digest
    manifest_path.write_bytes(
        quoted_yaml(manifest, logical_path=PurePosixPath("manifest.yaml"))
    )
    _carry_ledgers(draft, selection.root)
    approve_draft(
        scene.bundle_root,
        draft,
        parent=selection.root,
        stamp_id="approval-stamp.000004",
        approved_at=PROMOTED_AT,
    )

    outcome = promote(scene.bundle_root, _request(scene.drafts[1]))

    assert outcome.exit_code == 0, outcome.diagnostics
    assert outcome.value is not None
    assert outcome.value.revision == 3


def _carry_ledgers(draft: Path, revision_root: Path) -> None:
    """Copy the selected revision's history into the draft, as `rebase-draft` would have."""
    for logical in ("history/changes.yaml", "history/approvals.yaml"):
        (draft / logical).write_bytes((revision_root / logical).read_bytes())
