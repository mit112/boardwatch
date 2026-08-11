"""T17 §7/§23: `migrate` on a bundle that is already at the schema head.

The claim under test is "writes nothing at all", and the only honest way to assert it is to hash
every byte under the bundle root before and after. Reading the returned outcome would prove that
`migrate_bundle` *says* it did nothing, which is the component's own self-report — the same
argument the design makes for recomputing digests from disk rather than from the objects that were
just written.
"""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath

from boardwatch.profile_bundle import schema
from boardwatch.profile_bundle.errors import IssueCode
from boardwatch.profile_bundle.migrations import migrate_bundle
from boardwatch.profile_bundle.paths import current_path, drafts_dir, lock_path, revisions_dir
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from tests.profile_bundle.conftest import PromotedRevisionTree

DIRECTORY_MARKER = "<dir>"


def tree_state(root: Path) -> dict[str, str]:
    """Every path under `root`, with each file's content digest.

    Directories are included as entries of their own: a draft that was created and then emptied
    would leave every file digest unchanged while still being a write the design forbids.
    """
    state: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            state[f"{relative}/"] = DIRECTORY_MARKER
        else:
            state[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return state


def ledger_length(tree: PromotedRevisionTree, relative: str, key: str) -> int:
    """Count a history ledger's entries by re-reading the file, not by asking the loaded models."""
    path = tree.revision_dir / relative
    data = load_yaml_bytes(path.read_bytes(), logical_path=PurePosixPath(relative))
    assert isinstance(data, dict)
    entries = data[key]
    assert isinstance(entries, list)
    return len(entries)


def test_a_bundle_at_the_head_is_already_current(promoted_tree: PromotedRevisionTree) -> None:
    """§7: "On a v1 bundle, `profile-bundle migrate` returns `already_current`"."""
    outcome = migrate_bundle(promoted_tree.bundle_root)

    assert (outcome.category, outcome.exit_code) == ("clean", 0)
    assert outcome.diagnostics == ()
    assert outcome.value is not None
    assert outcome.value.status == "already_current"
    assert outcome.value.schema_version == schema.CURRENT_SCHEMA_VERSION


def test_migrating_changes_no_byte_under_the_bundle_root(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """"Performs no write" is a claim about the filesystem, so it is measured on the filesystem."""
    before = tree_state(promoted_tree.bundle_root)

    assert migrate_bundle(promoted_tree.bundle_root).exit_code == 0

    assert tree_state(promoted_tree.bundle_root) == before

    # Non-vacuity. A `tree_state` that walked the wrong directory, or one that silently returned
    # nothing, would report "no byte changed" for every implementation this test could be given.
    current_path(promoted_tree.bundle_root).write_bytes(b"tampered\n")
    assert tree_state(promoted_tree.bundle_root) != before


def test_migrating_creates_no_draft_revision_change_or_lock(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """The same claim, counted through the artefacts a real migration would produce.

    A future `1 -> 2` writes a draft, earns an approval stamp, and appends one change record on its
    way to a new revision directory. Every one of those counts must be untouched here, and counting
    them individually is what says *which* of them a regression started producing.
    """
    changes = ledger_length(promoted_tree, "history/changes.yaml", "changes")
    approvals = ledger_length(promoted_tree, "history/approvals.yaml", "approvals")
    revisions = sorted(revisions_dir(promoted_tree.bundle_root).iterdir())

    assert migrate_bundle(promoted_tree.bundle_root).exit_code == 0

    assert list(drafts_dir(promoted_tree.bundle_root).iterdir()) == []
    assert sorted(revisions_dir(promoted_tree.bundle_root).iterdir()) == revisions
    assert ledger_length(promoted_tree, "history/changes.yaml", "changes") == changes
    assert ledger_length(promoted_tree, "history/approvals.yaml", "approvals") == approvals
    assert not lock_path(promoted_tree.bundle_root).exists()


def test_migrating_is_idempotent(promoted_tree: PromotedRevisionTree) -> None:
    """Three runs, because a no-op that only holds on the first call is the interesting bug."""
    before = tree_state(promoted_tree.bundle_root)

    results = [migrate_bundle(promoted_tree.bundle_root) for _ in range(3)]

    assert [(r.category, r.exit_code) for r in results] == [("clean", 0)] * 3
    assert {r.value for r in results} == {results[0].value}
    assert tree_state(promoted_tree.bundle_root) == before


def test_a_bundle_with_no_selected_revision_is_refused_without_writing(tmp_path: Path) -> None:
    """There is nothing to migrate before the first promotion, and inventing a revision to migrate
    would be the one write this command is forbidden to make."""
    root = tmp_path / "career-profile"
    root.mkdir()
    before = tree_state(root)

    outcome = migrate_bundle(root)

    assert (outcome.category, outcome.exit_code) == ("findings", 1)
    assert [d.code for d in outcome.diagnostics] == [IssueCode.NO_CURRENT_REVISION]
    assert tree_state(root) == before


def test_a_previous_schema_fixture_and_a_forward_migration_are_owed_at_v2() -> None:
    """The obligation §7 defers, stated as a tripwire rather than as a comment.

    `migrate_bundle` reports `already_current` for any revision it managed to load, which is sound
    only while the supported set is exactly the head: `load_documents` refuses everything else. The
    moment a second version is supported that reasoning is void, so this assertion fails and the
    change that added v2 must bring with it the exact v1 previous-schema fixture and the
    append-only `1 -> 2` transform the design requires. Reading the constants off the module rather
    than importing them by name keeps the tripwire pointed at the live values.
    """
    assert schema.SUPPORTED_SCHEMA_VERSIONS == frozenset({schema.CURRENT_SCHEMA_VERSION}), (
        "supporting a second schema version obsoletes migrate_bundle's already_current shortcut; "
        "add the previous-version fixture and the forward migration in the same change"
    )
