"""Record-level draft rebase, the deterministic backup drain, and the shared writer lock.

Three claims are worth more than the rest, and each is tested by observing the *filesystem*, never
by reading the outcome the operation reported about itself.

**A conflict is a record, not a file.** The scene below has the draft add a skill to
`skills/inventory.yaml` while the newly promoted revision renames a different skill in the same
file. That must merge. The same scene with both sides renaming the *same* skill must refuse.

**A crash leaves the original or the exact backup, never a mixture.** Failure is injected at each
of the three boundaries the plan names, and every case asserts what is on disk afterwards.

**A persistent lockfile is not a held lock.** A real subprocess takes the lock and is killed with
`SIGKILL`; `career-profile.lock` survives, and the next rebase must succeed anyway. Contention is
proved with a live holder rather than a stubbed one, because the property under test belongs to the
operating system.
"""

from __future__ import annotations

import copy
import errno
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import pytest
from pydantic import BaseModel

from boardwatch.profile_bundle import rebase as rebase_module
from boardwatch.profile_bundle.canonical import candidate_content_digest
from boardwatch.profile_bundle.diff import (
    DocumentMergeConflict,
    diff_records,
    merge_document,
    record_contents,
)
from boardwatch.profile_bundle.drafts import DRAFT_TEMP_PREFIX, checkout_current
from boardwatch.profile_bundle.errors import IssueCode
from boardwatch.profile_bundle.layout import owner_for_path
from boardwatch.profile_bundle.locking import BundleLockHeldError, bundle_lock
from boardwatch.profile_bundle.models.documents import (
    BundleDocuments,
    ProjectFactsDocument,
    SkillInventoryDocument,
)
from boardwatch.profile_bundle.models.history import ApprovalLedger, ConflictRulings
from boardwatch.profile_bundle.models.manifests import DraftManifest, RevisionManifest
from boardwatch.profile_bundle.paths import (
    LOCK_FILE,
    MAX_DRAFT_NAME_LENGTH,
    approval_path,
    blob_path,
    draft_root,
    drafts_dir,
    lock_path,
    rebase_backup_root,
)
from boardwatch.profile_bundle.rebase import rebase_draft
from boardwatch.profile_bundle.schema import DOCUMENT_MODELS
from boardwatch.profile_bundle.validation import load_documents
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from boardwatch.profile_bundle.yaml_writer import DocumentEmitError
from tests.profile_bundle.conftest import (
    PromotedRevisionTree,
    blob_reader,
    materialise,
    promote_example_tree,
    promote_next_revision,
    quoted_yaml,
)

DRAFT_NAME = "work"
SKILLS_PATH = PurePosixPath("skills/inventory.yaml")
ORIGINAL_SKILL = "skill.example-language"
ADDED_SKILL = "skill.example-second"
REVISION_TWO_NAME = "Renamed By Revision Two"
DRAFT_RENAME = "Renamed By The Draft"

#: A live holder for the bundle lock. Written as a subprocess for the same reason the scan-lock
#: test is: the property being tested is the operating system's, and an in-process double would
#: prove only that the double behaves like the double.
HOLDER_SCRIPT = """
import sys, time
from filelock import FileLock
lock = FileLock(sys.argv[1])
lock.acquire()
print("HELD", flush=True)
time.sleep(300)
"""


# --------------------------------------------------------------------------------------
# Scene construction
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Scene:
    """A draft of revision 1 with revision 2 promoted underneath it."""

    bundle_root: Path
    draft: Path
    parent: PromotedRevisionTree
    current: PromotedRevisionTree
    backup: Path


def _edit_document(root: Path, logical: PurePosixPath, mutate: Callable[[Any], None]) -> None:
    path = root / logical
    data = load_yaml_bytes(path.read_bytes(), logical_path=logical)
    mutate(data)
    path.write_bytes(quoted_yaml(data, logical_path=logical))


def _edit_skills(root: Path, mutate: Callable[[Any], None]) -> None:
    _edit_document(root, SKILLS_PATH, mutate)


def _add_second_skill(data: Any) -> None:
    """Clone the example's one skill under a new ID. An addition, not an edit."""
    clone = copy.deepcopy(data["skills"][0])
    clone["skill_id"] = ADDED_SKILL
    clone["canonical_name"] = "Second Example Language"
    clone["aliases"] = ["second-example-lang"]
    data["skills"].append(clone)


def _rename_first_skill(name: str) -> Callable[[Any], None]:
    def mutate(data: Any) -> None:
        data["skills"][0]["canonical_name"] = name

    return mutate


def _scene(tmp_path: Path, *, draft_edit: Callable[[Any], None] | None) -> Scene:
    """Revision 1, a draft checked out of it, an optional draft edit, then revision 2."""
    bundle_root = tmp_path / "career-profile"
    parent = promote_example_tree(bundle_root)
    outcome = checkout_current(bundle_root, name=DRAFT_NAME)
    assert outcome.exit_code == 0, outcome.diagnostics
    draft = draft_root(bundle_root, DRAFT_NAME)
    if draft_edit is not None:
        _edit_skills(draft, draft_edit)
    current = promote_next_revision(parent, mutate=_rename_first_skill(REVISION_TWO_NAME))
    return Scene(
        bundle_root=bundle_root,
        draft=draft,
        parent=parent,
        current=current,
        backup=rebase_backup_root(bundle_root, DRAFT_NAME, parent.bundle_digest),
    )


@pytest.fixture
def scene(tmp_path: Path) -> Scene:
    """The disjoint case: the draft adds a skill, revision 2 renames another one."""
    return _scene(tmp_path, draft_edit=_add_second_skill)


def _snapshot(root: Path) -> dict[str, bytes]:
    """Every file under `root` by relative path, excluding the lockfile.

    `career-profile.lock` is excluded because creating it is not a mutation of the bundle: §6 makes
    its persistence meaningless, and a "nothing was written" assertion that tripped over it would
    be asserting the opposite of the design.
    """
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != LOCK_FILE
    }


def _skills(root: Path) -> SkillInventoryDocument:
    document = load_documents(root, mode="draft").by_path[SKILLS_PATH]
    assert isinstance(document, SkillInventoryDocument)
    return document


def _draft_manifest(root: Path) -> DraftManifest:
    manifest = load_documents(root, mode="draft").manifest
    assert isinstance(manifest, DraftManifest)
    return manifest


def _codes(outcome: Any) -> list[str]:
    return [finding.code for finding in outcome.diagnostics]


@pytest.fixture
def lock_holder(tmp_path: Path) -> Iterator[Callable[[Path], subprocess.Popen[str]]]:
    """Start a subprocess that really holds a bundle lock, and always reap it."""
    started: list[subprocess.Popen[str]] = []

    def start(bundle_root: Path) -> subprocess.Popen[str]:
        process = subprocess.Popen(
            [sys.executable, "-c", HOLDER_SCRIPT, str(lock_path(bundle_root))],
            stdout=subprocess.PIPE,
            text=True,
        )
        started.append(process)
        assert process.stdout is not None
        assert process.stdout.readline().strip() == "HELD"
        return process

    yield start
    for process in started:
        process.kill()
        process.wait()


# --------------------------------------------------------------------------------------
# diff_records
# --------------------------------------------------------------------------------------


def test_a_tree_has_no_diff_against_itself(promoted_tree: PromotedRevisionTree) -> None:
    difference = diff_records(promoted_tree.documents, promoted_tree.documents)
    assert (difference.added, difference.removed, difference.changed) == (
        frozenset(),
        frozenset(),
        frozenset(),
    )
    assert difference.touched == frozenset()


def test_diff_names_the_edited_record_and_the_promotion_records(tmp_path: Path) -> None:
    parent = promote_example_tree(tmp_path / "career-profile")
    child = promote_next_revision(parent, mutate=_rename_first_skill(REVISION_TWO_NAME))

    difference = diff_records(parent.documents, child.documents)

    assert difference.changed == frozenset({ORIGINAL_SKILL})
    assert difference.removed == frozenset()
    assert "change.example.000002" in difference.added
    assert "approval-stamp.000002" in difference.added
    assert ORIGINAL_SKILL in difference.touched


def test_diff_reports_an_addition_and_a_removal_by_id(scene: Scene) -> None:
    before = load_documents(scene.parent.revision_dir, mode="revision")
    after = load_documents(scene.draft, mode="draft")

    assert diff_records(before, after).added == frozenset({ADDED_SKILL})
    assert diff_records(after, before).removed == frozenset({ADDED_SKILL})


def test_reformatting_a_document_is_not_a_record_change(scene: Scene) -> None:
    """Identity is the canonical record digest, so a re-emit must not read as an edit."""
    before = load_documents(scene.draft, mode="draft")
    path = scene.draft / SKILLS_PATH
    data = load_yaml_bytes(path.read_bytes(), logical_path=SKILLS_PATH)
    path.write_bytes(quoted_yaml(data, logical_path=SKILLS_PATH))
    assert path.read_bytes() != b""

    assert diff_records(before, load_documents(scene.draft, mode="draft")).touched == frozenset()


def test_record_contents_keys_every_addressable_record(promoted_tree: PromotedRevisionTree) -> None:
    contents = record_contents(promoted_tree.documents)
    assert ORIGINAL_SKILL in contents
    assert all(digest.startswith("sha256:") for digest in contents.values())


# --------------------------------------------------------------------------------------
# merge_document
# --------------------------------------------------------------------------------------


def _skills_document(*names: tuple[str, str]) -> SkillInventoryDocument:
    base = {
        "skill_id": ORIGINAL_SKILL,
        "canonical_name": "Example Language",
        "aliases": [],
        "category": "programming-language",
        "supporting_fact_ids": ["fact.packet-pantry.language.001"],
        "verification_state": "verified",
        "allowed_surfaces": ["resume"],
    }
    return SkillInventoryDocument.model_validate(
        {
            "skills": [
                {**base, "skill_id": identifier, "canonical_name": canonical}
                for identifier, canonical in names
            ]
        }
    )


def test_merge_keeps_both_sides_when_they_touch_different_records() -> None:
    base = _skills_document((ORIGINAL_SKILL, "Example Language"))
    ours = _skills_document((ORIGINAL_SKILL, "Example Language"), (ADDED_SKILL, "Second"))
    theirs = _skills_document((ORIGINAL_SKILL, REVISION_TWO_NAME))

    merged = merge_document(base, ours, theirs)

    assert isinstance(merged, SkillInventoryDocument)
    assert [skill.skill_id for skill in merged.skills] == [ORIGINAL_SKILL, ADDED_SKILL]
    assert merged.skills[0].canonical_name == REVISION_TWO_NAME


def test_merge_refuses_when_both_sides_changed_one_record() -> None:
    base = _skills_document((ORIGINAL_SKILL, "Example Language"))
    ours = _skills_document((ORIGINAL_SKILL, DRAFT_RENAME))
    theirs = _skills_document((ORIGINAL_SKILL, REVISION_TWO_NAME))

    with pytest.raises(DocumentMergeConflict) as raised:
        merge_document(base, ours, theirs)
    assert raised.value.record_id == ORIGINAL_SKILL


def test_merge_refuses_a_record_removed_by_one_side_and_changed_by_the_other() -> None:
    base = _skills_document((ORIGINAL_SKILL, "Example Language"), (ADDED_SKILL, "Second"))
    ours = _skills_document((ADDED_SKILL, "Second"))
    theirs = _skills_document((ORIGINAL_SKILL, REVISION_TWO_NAME), (ADDED_SKILL, "Second"))

    with pytest.raises(DocumentMergeConflict) as raised:
        merge_document(base, ours, theirs)
    assert raised.value.record_id == ORIGINAL_SKILL


def test_merge_drops_a_record_only_one_side_removed() -> None:
    base = _skills_document((ORIGINAL_SKILL, "Example Language"), (ADDED_SKILL, "Second"))
    ours = _skills_document((ORIGINAL_SKILL, "Example Language"))
    theirs = _skills_document((ORIGINAL_SKILL, "Example Language"), (ADDED_SKILL, "Second"))

    merged = merge_document(base, ours, theirs)

    assert isinstance(merged, SkillInventoryDocument)
    assert [skill.skill_id for skill in merged.skills] == [ORIGINAL_SKILL]


def test_merge_without_a_base_treats_every_record_as_an_addition() -> None:
    ours = _skills_document((ADDED_SKILL, "Second"))
    theirs = _skills_document((ORIGINAL_SKILL, "Example Language"))

    merged = merge_document(None, ours, theirs)

    assert isinstance(merged, SkillInventoryDocument)
    assert [skill.skill_id for skill in merged.skills] == [ORIGINAL_SKILL, ADDED_SKILL]


def test_merge_refuses_a_field_that_holds_no_addressable_records(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """A catalog version has no record identity, so a two-sided bump has to be refused."""
    catalog = promoted_tree.documents.by_path[PurePosixPath("policy/units.yaml")]
    ours = catalog.model_copy(update={"units_version": 2})
    theirs = catalog.model_copy(update={"units_version": 3})

    with pytest.raises(DocumentMergeConflict) as raised:
        merge_document(catalog, ours, theirs)
    assert raised.value.field == "units_version"
    assert raised.value.record_id is None


def test_merge_refuses_a_two_sided_edit_to_catalog_rows(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """Catalog rows are deliberately outside the record space, so they cannot be merged by ID."""
    catalog = promoted_tree.documents.by_path[PurePosixPath("policy/predicates.yaml")]
    assert len(catalog.predicates) > 1
    ours = catalog.model_copy(update={"predicates": ()})
    theirs = catalog.model_copy(update={"predicates": catalog.predicates[:1]})

    with pytest.raises(DocumentMergeConflict) as raised:
        merge_document(catalog, ours, theirs)
    assert raised.value.field == "predicates"
    assert raised.value.record_id is None


def test_merge_takes_their_field_when_only_they_changed_it() -> None:
    base = _skills_document((ORIGINAL_SKILL, "Example Language"))
    theirs = _skills_document((ORIGINAL_SKILL, REVISION_TWO_NAME))

    merged = merge_document(base, base, theirs)

    assert isinstance(merged, SkillInventoryDocument)
    assert merged.skills[0].canonical_name == REVISION_TWO_NAME


def test_merge_keeps_a_record_only_we_removed_while_both_sides_moved() -> None:
    """Our removal survives a field both sides edited; their untouched record is simply gone."""
    base = _skills_document((ORIGINAL_SKILL, "Example Language"), (ADDED_SKILL, "Second"))
    ours = _skills_document((ORIGINAL_SKILL, DRAFT_RENAME))
    theirs = _skills_document(
        (ORIGINAL_SKILL, "Example Language"), (ADDED_SKILL, "Second"), ("skill.theirs", "Theirs")
    )

    merged = merge_document(base, ours, theirs)

    assert isinstance(merged, SkillInventoryDocument)
    assert [skill.skill_id for skill in merged.skills] == [ORIGINAL_SKILL, "skill.theirs"]
    assert merged.skills[0].canonical_name == DRAFT_RENAME


def test_a_logical_path_alone_decides_which_model_parsed_it(scene: Scene) -> None:
    """Where the "both sides are the same kind of document" guarantee lands.

    `merge_document` does not re-check it, so this does: over two independently loaded real trees,
    not over the mapping, so a loader that ever dispatched on content rather than on path would fail
    here rather than inside a merge.
    """
    ours = load_documents(scene.draft, mode="draft")
    theirs = load_documents(scene.current.revision_dir, mode="revision")
    shared = sorted(set(ours.by_path) & set(theirs.by_path), key=str)
    assert len(shared) > 20

    for logical in shared:
        expected = DOCUMENT_MODELS[owner_for_path(logical)]
        assert type(ours.by_path[logical]) is expected
        assert type(theirs.by_path[logical]) is expected


def test_only_nested_fields_hold_tuples_of_scalars(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """Why `merge_values` never has to ask whether a tuple's elements are models.

    Every tuple among a document's or a manifest's *top-level* fields holds records or catalog rows;
    the scalar tuples (`FactRecord.values`, `MetricRecord.allowed_phrasings`, …) live one level down,
    inside records, where the merge never looks. `record_id_of` is the backstop for both cases.
    """
    documents = [promoted_tree.documents.manifest, *promoted_tree.documents.by_path.values()]
    checked = 0
    for document in documents:
        for name in type(document).model_fields:
            value = getattr(document, name)
            if not isinstance(value, tuple) or not value:
                continue
            checked += 1
            assert all(isinstance(item, BaseModel) for item in value), f"{name} holds scalars"
    assert checked > 20


# --------------------------------------------------------------------------------------
# The happy path: disjoint records merge, and the backup holds the original
# --------------------------------------------------------------------------------------


def test_disjoint_edits_to_one_file_merge_onto_the_new_revision(scene: Scene) -> None:
    original = _snapshot(scene.draft)

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 0, outcome.diagnostics
    assert outcome.diagnostics == ()
    assert outcome.value is not None
    assert outcome.value.draft_of_revision == scene.current.revision
    assert outcome.value.parent_bundle_digest == scene.current.bundle_digest

    merged = _skills(scene.draft)
    assert [skill.skill_id for skill in merged.skills] == [ORIGINAL_SKILL, ADDED_SKILL]
    assert merged.skills[0].canonical_name == REVISION_TWO_NAME

    manifest = _draft_manifest(scene.draft)
    assert manifest.draft_of_revision == scene.current.revision
    assert manifest.parent_bundle_digest == scene.current.bundle_digest
    assert manifest.bundle_digest == ""
    assert manifest.approved_candidate_digest == ""
    assert manifest.approval_stamp_id == ""

    # The backup is the pre-rebase draft, byte for byte, under the deterministic name.
    assert scene.backup.name == f"{DRAFT_NAME}.pre-rebase-sha256-" + scene.parent.bundle_digest[7:]
    assert _snapshot(scene.backup) == original


def test_the_rebased_draft_inherits_the_new_revisions_change_ledger(scene: Scene) -> None:
    assert rebase_draft(scene.bundle_root, name=DRAFT_NAME).exit_code == 0

    documents = load_documents(scene.draft, mode="draft")
    ledger = documents.by_path[PurePosixPath("history/changes.yaml")]
    assert [entry.change_id for entry in ledger.changes] == [
        "change.example.000001",
        "change.example.000002",
    ]


def test_a_draft_already_on_the_selected_revision_is_left_alone(tmp_path: Path) -> None:
    bundle_root = tmp_path / "career-profile"
    promote_example_tree(bundle_root)
    assert checkout_current(bundle_root, name=DRAFT_NAME).exit_code == 0
    draft = draft_root(bundle_root, DRAFT_NAME)
    before = _snapshot(bundle_root)

    outcome = rebase_draft(bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 0, outcome.diagnostics
    assert _snapshot(bundle_root) == before
    assert list(drafts_dir(bundle_root).iterdir()) == [draft]


def test_an_absent_draft_is_a_typed_state_refusal(tmp_path: Path) -> None:
    bundle_root = tmp_path / "career-profile"
    promote_example_tree(bundle_root)
    before = _snapshot(bundle_root)

    outcome = rebase_draft(bundle_root, name="missing")

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.DRAFT_NOT_FOUND]
    assert _snapshot(bundle_root) == before


def test_a_revision_tree_parked_under_drafts_is_refused(tmp_path: Path) -> None:
    """Only a draft can be rebased; a revision manifest carries identity a rebase would rewrite."""
    bundle_root = tmp_path / "career-profile"
    promoted = promote_example_tree(bundle_root)
    parked = draft_root(bundle_root, "parked")
    shutil.copytree(promoted.revision_dir, parked)
    (parked / "COMPLETE").unlink()
    before = _snapshot(bundle_root)

    outcome = rebase_draft(bundle_root, name="parked")

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.DRAFT_MANIFEST_INVALID]
    assert _snapshot(bundle_root) == before


def test_an_unreadable_old_parent_refuses_without_writing(scene: Scene) -> None:
    """The base of a three-way merge is not optional; guessing at it would drop somebody's edit."""
    shutil.rmtree(scene.parent.revision_dir)
    before = _snapshot(scene.bundle_root)

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.UNVERIFIABLE_ANCESTOR]
    assert _snapshot(scene.bundle_root) == before
    assert not scene.backup.exists()


# --------------------------------------------------------------------------------------
# Conflicts: never auto-resolved, never written
# --------------------------------------------------------------------------------------


def test_two_edits_to_one_record_refuse_and_write_nothing(tmp_path: Path) -> None:
    conflicting = _scene(tmp_path, draft_edit=_rename_first_skill(DRAFT_RENAME))
    before = _snapshot(conflicting.bundle_root)

    outcome = rebase_draft(conflicting.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.DRAFT_REBASE_CONFLICT]
    finding = outcome.diagnostics[0]
    assert finding.record_id == ORIGINAL_SKILL
    assert finding.details["record_ids"] == [ORIGINAL_SKILL]
    assert _snapshot(conflicting.bundle_root) == before
    assert not conflicting.backup.exists()


def test_a_conflict_keeps_the_drafts_own_value(tmp_path: Path) -> None:
    """Never auto-resolve: the draft still says what the owner said."""
    conflicting = _scene(tmp_path, draft_edit=_rename_first_skill(DRAFT_RENAME))

    rebase_draft(conflicting.bundle_root, name=DRAFT_NAME)

    assert _skills(conflicting.draft).skills[0].canonical_name == DRAFT_RENAME


def _shadow_first_skill(data: Any) -> None:
    """A second record under the ID the first one already claims. The index keeps only one."""
    clone = copy.deepcopy(data["skills"][0])
    clone["canonical_name"] = "Duplicate ID Twin"
    data["skills"].append(clone)


def test_a_duplicate_record_id_in_the_draft_refuses_instead_of_collapsing_it(
    tmp_path: Path,
) -> None:
    """The index drops the shadowed record, so the diff cannot see it and the merge deletes one.

    The revision deliberately touches no record the draft touched, so nothing else in the rebase
    has a reason to refuse: without the collision check this scene is exit 0 with one record gone.
    """
    bundle_root = tmp_path / "career-profile"
    parent = promote_example_tree(bundle_root)
    assert checkout_current(bundle_root, name=DRAFT_NAME).exit_code == 0
    draft = draft_root(bundle_root, DRAFT_NAME)
    _edit_skills(draft, _shadow_first_skill)
    promote_next_revision(parent, mutate=_add_second_skill)
    before = _snapshot(bundle_root)
    assert [skill.canonical_name for skill in _skills(draft).skills] == [
        "Example Language",
        "Duplicate ID Twin",
    ]

    outcome = rebase_draft(bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.DUPLICATE_RECORD_ID]
    finding = outcome.diagnostics[0]
    assert finding.record_id == ORIGINAL_SKILL
    assert finding.path == SKILLS_PATH.as_posix()
    assert f"drafts/{DRAFT_NAME}" in finding.message
    # Both records survive, because nothing was written at all.
    assert len(_skills(draft).skills) == 2
    assert _snapshot(bundle_root) == before


APPROVALS_PATH = PurePosixPath("history/approvals.yaml")
RULINGS_PATH = PurePosixPath("conflicts/rulings.yaml")


def _approval_ids(root: Path, *, mode: str) -> list[str]:
    document = load_documents(root, mode=mode).by_path[APPROVALS_PATH]
    assert isinstance(document, ApprovalLedger)
    return [stamp.approval_stamp_id for stamp in document.approvals]


def _ruling_ids(root: Path, *, mode: str) -> list[str]:
    document = load_documents(root, mode=mode).by_path[RULINGS_PATH]
    assert isinstance(document, ConflictRulings)
    return [ruling.ruling_id for ruling in document.rulings]


def test_a_manifest_field_changed_on_both_sides_refuses(scene: Scene) -> None:
    """The manifest is merged field-wise too, and a catalog version has no record to merge by.

    The end-to-end cover of that refusal: the draft and the newly promoted revision each bump the
    unit catalog version, which is exactly what a real catalog promotion would do.
    """
    manifest_path = PurePosixPath("manifest.yaml")
    def bump(version: int) -> Callable[[Any], None]:
        return lambda data: data.update({"unit_catalog_version": version})

    _edit_document(scene.draft, manifest_path, bump(2))
    _edit_document(scene.current.revision_dir, manifest_path, bump(3))
    before = _snapshot(scene.bundle_root)

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.DRAFT_REBASE_CONFLICT]
    finding = outcome.diagnostics[0]
    assert finding.path == manifest_path.as_posix()
    assert finding.details["field"] == "unit_catalog_version"
    # D-129's empty case, and the negative control for the whole-document one: the conflicting unit
    # is a version field, which has no addressable records, so `field` is the whole locator.
    assert finding.details["record_ids"] == []
    assert _snapshot(scene.bundle_root) == before


def test_the_manifest_fields_the_rebase_assigns_itself_all_exist() -> None:
    """A typo in that literal would silently three-way-merge a promotion-derived field.

    Pinned against the model rather than against the literal, which is the only way the two can
    disagree.
    """
    assert rebase_module._DERIVED_MANIFEST_FIELDS <= frozenset(DraftManifest.model_fields)
    assert not (rebase_module._INHERITED_MANIFEST_FIELDS & rebase_module._DERIVED_MANIFEST_FIELDS)
    # Every field a draft and a revision share is either inherited by merge or assigned here.
    shared = frozenset(DraftManifest.model_fields) & frozenset(RevisionManifest.model_fields)
    assert shared <= (
        rebase_module._INHERITED_MANIFEST_FIELDS | rebase_module._DERIVED_MANIFEST_FIELDS
    )


def test_a_stamp_the_draft_dropped_from_its_ledger_is_never_merged_away(scene: Scene) -> None:
    """§17: the ledgers are append-only, so a draft-side removal is a conflict, not a deletion."""
    _edit_document(scene.draft, APPROVALS_PATH, lambda data: data["approvals"].clear())
    carried = _approval_ids(scene.current.revision_dir, mode="revision")
    assert len(carried) == 2
    before = _snapshot(scene.bundle_root)

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.DRAFT_REBASE_CONFLICT]
    assert outcome.diagnostics[0].path == APPROVALS_PATH.as_posix()
    assert outcome.diagnostics[0].record_id == carried[0]
    assert _snapshot(scene.bundle_root) == before


def test_a_stamp_the_draft_rewrote_is_a_conflict_rather_than_a_silent_choice(scene: Scene) -> None:
    """Keeping the rewrite breaks the prefix; taking theirs discards an owner edit. Refuse."""

    def forge(data: Any) -> None:
        data["approvals"][0]["candidate_content_digest"] = "sha256:" + "a" * 64

    _edit_document(scene.draft, APPROVALS_PATH, forge)
    before = _snapshot(scene.bundle_root)

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.DRAFT_REBASE_CONFLICT]
    assert outcome.diagnostics[0].path == APPROVALS_PATH.as_posix()
    assert _snapshot(scene.bundle_root) == before


def test_the_rebased_draft_carries_the_selected_revisions_ledgers_as_a_prefix(scene: Scene) -> None:
    """The positive half: an untouched draft ledger inherits every stamp the revision carries."""
    carried = _approval_ids(scene.current.revision_dir, mode="revision")

    assert rebase_draft(scene.bundle_root, name=DRAFT_NAME).exit_code == 0

    installed = _approval_ids(scene.draft, mode="draft")
    assert installed[: len(carried)] == carried


def test_a_ruling_the_draft_dropped_is_refused_though_the_revision_left_it_untouched(
    scene: Scene,
) -> None:
    """The append-only rule must not depend on the revision having touched the same ledger.

    A promotion appends a change record and an approval stamp; it almost never appends a *ruling*.
    So `conflicts/rulings.yaml` is byte-identical in the parent and the selected revision on the
    ordinary path, and a plan that takes the draft's copy wholesale in that case would drop an
    owner's ruling with exit 0 and nothing said. Asserted against the revision's own bytes rather
    than against the merge, so the test states the scene it needs instead of assuming it.
    """
    inherited = _ruling_ids(scene.current.revision_dir, mode="revision")
    assert inherited, "the example bundle must carry a ruling for this scene to exist"
    assert (scene.current.revision_dir / RULINGS_PATH).read_bytes() == (
        scene.parent.revision_dir / RULINGS_PATH
    ).read_bytes()
    _edit_document(scene.draft, RULINGS_PATH, lambda data: data["rulings"].clear())
    before = _snapshot(scene.bundle_root)

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.DRAFT_REBASE_CONFLICT]
    assert outcome.diagnostics[0].path == RULINGS_PATH.as_posix()
    assert outcome.diagnostics[0].record_id == inherited[0]
    assert _snapshot(scene.bundle_root) == before


def test_a_merged_document_that_fails_its_own_validator_is_a_typed_refusal(scene: Scene) -> None:
    """Two individually valid sides, one invalid merge. Never an exception out of `rebase_draft`."""
    changes = PurePosixPath("history/changes.yaml")

    def append_own_entry(data: Any) -> None:
        entry = copy.deepcopy(data["changes"][0])
        entry["change_id"] = "change.mine.000002"
        entry["revision"] = 2
        entry["parent_bundle_digest"] = scene.parent.bundle_digest
        entry["summary"] = "the owner's own note in the draft ledger"
        data["changes"].append(entry)

    _edit_document(scene.draft, changes, append_own_entry)
    # Each side still loads on its own; only the merge of the two is invalid.
    assert changes in load_documents(scene.draft, mode="draft").by_path
    assert changes in load_documents(scene.current.revision_dir, mode="revision").by_path
    before = _snapshot(scene.bundle_root)

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.DRAFT_REBASE_CONFLICT]
    assert outcome.diagnostics[0].path == changes.as_posix()
    # The validator's own sentence reaches the operator rather than a traceback.
    assert "contiguous" in outcome.diagnostics[0].message
    # D-129: an empty `record_ids` means the conflicting unit holds no addressable records. This
    # unit is the whole document, and this document holds records on both sides.
    reported = outcome.diagnostics[0].details["record_ids"]
    assert set(reported) == {
        "change.example.000001",
        "change.example.000002",
        "change.mine.000002",
    }
    assert _snapshot(scene.bundle_root) == before


# --------------------------------------------------------------------------------------
# One side deleted a document the other side changed
# --------------------------------------------------------------------------------------

UNITS_PATH = PurePosixPath("policy/units.yaml")
PROJECT_PATH = PurePosixPath("facts/projects/project.packet-pantry.yaml")
PROMOTED_FACT = "fact.packet-pantry.summary.003"


def _bump_units(data: Any) -> None:
    data["units_version"] = data["units_version"] + 1


def _add_fact(fact_id: str) -> Callable[[Any], None]:
    def mutate(data: Any) -> None:
        clone = copy.deepcopy(data["facts"][0])
        clone["fact_id"] = fact_id
        clone["supersedes_fact_ids"] = []
        data["facts"].append(clone)

    return mutate


def test_a_recordless_document_the_draft_deleted_and_the_revision_changed_refuses(
    scene: Scene,
) -> None:
    """`policy/*.yaml` holds no addressable records, so the overlap gate cannot see this at all."""
    (scene.draft / UNITS_PATH).unlink()
    _edit_document(scene.current.revision_dir, UNITS_PATH, _bump_units)
    before = _snapshot(scene.bundle_root)

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.DRAFT_REBASE_CONFLICT]
    assert outcome.diagnostics[0].path == UNITS_PATH.as_posix()
    # No addressable records exist in this document, so `path` is the whole locator.
    assert outcome.diagnostics[0].details["record_ids"] == []
    assert _snapshot(scene.bundle_root) == before


def test_a_recordless_document_the_revision_deleted_and_the_draft_changed_refuses(
    scene: Scene,
) -> None:
    """The mirror. Dropping the document here would discard the owner's own edit."""
    _edit_document(scene.draft, UNITS_PATH, _bump_units)
    (scene.current.revision_dir / UNITS_PATH).unlink()
    before = _snapshot(scene.bundle_root)

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.DRAFT_REBASE_CONFLICT]
    assert outcome.diagnostics[0].path == UNITS_PATH.as_posix()
    assert _snapshot(scene.bundle_root) == before


def test_a_record_the_revision_promoted_is_never_reverted_by_a_draft_side_deletion(
    scene: Scene,
) -> None:
    """The worst half: promoting the rebased draft would remove a record `CURRENT` holds."""
    (scene.draft / PROJECT_PATH).unlink()
    _edit_document(scene.current.revision_dir, PROJECT_PATH, _add_fact(PROMOTED_FACT))
    before = _snapshot(scene.bundle_root)

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.DRAFT_REBASE_CONFLICT]
    finding = outcome.diagnostics[0]
    assert finding.path == PROJECT_PATH.as_posix()
    # §19: the conflict carries the exact record IDs — here, the work the deletion would discard.
    assert PROMOTED_FACT in finding.details["record_ids"]
    assert finding.record_id == sorted(finding.details["record_ids"])[0]
    assert _snapshot(scene.bundle_root) == before


def test_a_record_the_draft_added_is_never_discarded_by_a_revision_side_deletion(
    scene: Scene,
) -> None:
    """And its mirror: the owner's own new fact in a file the revision dropped."""
    added = "fact.packet-pantry.summary.004"
    _edit_document(scene.draft, PROJECT_PATH, _add_fact(added))
    (scene.current.revision_dir / PROJECT_PATH).unlink()
    before = _snapshot(scene.bundle_root)

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.DRAFT_REBASE_CONFLICT]
    assert added in outcome.diagnostics[0].details["record_ids"]
    assert _snapshot(scene.bundle_root) == before


def test_a_document_the_owner_dropped_and_nobody_else_touched_stays_dropped(scene: Scene) -> None:
    """The legitimate case the refusal must not swallow: dropping a project is an owner edit."""
    (scene.draft / PROJECT_PATH).unlink()

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 0, outcome.diagnostics
    assert not (scene.draft / PROJECT_PATH).exists()
    assert PROJECT_PATH not in load_documents(scene.draft, mode="draft").by_path


# --------------------------------------------------------------------------------------
# The deterministic backup drain
# --------------------------------------------------------------------------------------


def test_an_exact_existing_backup_is_reused(scene: Scene) -> None:
    shutil.copytree(scene.draft, scene.backup)
    backup_before = _snapshot(scene.backup)

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 0, outcome.diagnostics
    assert _snapshot(scene.backup) == backup_before
    assert _skills(scene.draft).skills[0].canonical_name == REVISION_TWO_NAME
    # The vacated copy is not left behind beside the draft it came from.
    assert sorted(entry.name for entry in drafts_dir(scene.bundle_root).iterdir()) == [
        DRAFT_NAME,
        scene.backup.name,
    ]


def test_a_backup_differing_by_one_byte_refuses_with_no_writes(scene: Scene) -> None:
    shutil.copytree(scene.draft, scene.backup)
    (scene.backup / SKILLS_PATH).write_bytes(
        (scene.backup / SKILLS_PATH).read_bytes() + b"# drift\n"
    )
    before = _snapshot(scene.bundle_root)

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.DRAFT_BACKUP_CONFLICT]
    assert outcome.diagnostics[0].path == f"drafts/{scene.backup.name}"
    assert _snapshot(scene.bundle_root) == before


def test_a_backup_with_an_extra_file_refuses(scene: Scene) -> None:
    shutil.copytree(scene.draft, scene.backup)
    (scene.backup / "facts" / "projects" / "project.extra.yaml").write_bytes(b"facts: []\n")
    before = _snapshot(scene.bundle_root)

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.DRAFT_BACKUP_CONFLICT]
    assert _snapshot(scene.bundle_root) == before


@pytest.mark.parametrize("name", ["my-work-branch", "a" * MAX_DRAFT_NAME_LENGTH])
def test_a_long_but_legal_draft_name_is_rebasable(tmp_path: Path, name: str) -> None:
    """`checkout` accepts these, so the rebase must too — and the filesystem must take the backup.

    14 characters is the first length whose derived backup name outgrows the operator-facing cap.
    """
    bundle_root = tmp_path / "career-profile"
    parent = promote_example_tree(bundle_root)
    assert checkout_current(bundle_root, name=name).exit_code == 0
    promote_next_revision(parent, mutate=_rename_first_skill(REVISION_TWO_NAME))

    outcome = rebase_draft(bundle_root, name=name)

    assert outcome.exit_code == 0, outcome.diagnostics
    backup = rebase_backup_root(bundle_root, name, parent.bundle_digest)
    assert backup.is_dir()
    assert _skills(draft_root(bundle_root, name)).skills[0].canonical_name == REVISION_TWO_NAME


def test_a_parentless_draft_uses_the_root_backup_token(tmp_path: Path) -> None:
    """`.pre-rebase-root`, because a revision-1 draft has no parent digest to name."""
    bundle_root = tmp_path / "career-profile"
    promote_example_tree(bundle_root)
    materialise(bundle_root, draft_name="fresh")
    backup = rebase_backup_root(bundle_root, "fresh", None)
    assert backup.name == "fresh.pre-rebase-root"
    backup.mkdir()
    (backup / "manifest.yaml").write_bytes(b"state: 'draft'\n")
    before = _snapshot(bundle_root)

    outcome = rebase_draft(bundle_root, name="fresh")

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.DRAFT_BACKUP_CONFLICT]
    assert outcome.diagnostics[0].path == "drafts/fresh.pre-rebase-root"
    assert _snapshot(bundle_root) == before


# --------------------------------------------------------------------------------------
# Approval stamps: retained, and the candidate digest they bind is invalidated
# --------------------------------------------------------------------------------------


def test_a_stale_approval_stamp_is_retained_and_its_digest_invalidated(scene: Scene) -> None:
    parent_manifest = scene.parent.documents.manifest
    assert isinstance(parent_manifest, RevisionManifest)
    before_documents = load_documents(scene.draft, mode="draft")
    before_digest = candidate_content_digest(
        before_documents, blob_reader(), parent_manifest.envelope
    )
    stamp = approval_path(scene.bundle_root, before_digest)
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_bytes(b"approvals: []\n")
    stamp_bytes = stamp.read_bytes()

    assert rebase_draft(scene.bundle_root, name=DRAFT_NAME).exit_code == 0

    current_manifest = scene.current.documents.manifest
    assert isinstance(current_manifest, RevisionManifest)
    after_digest = candidate_content_digest(
        load_documents(scene.draft, mode="draft"), blob_reader(), current_manifest.envelope
    )
    assert after_digest != before_digest
    assert stamp.exists()
    assert stamp.read_bytes() == stamp_bytes


# --------------------------------------------------------------------------------------
# The crash matrix
# --------------------------------------------------------------------------------------


def _inject_rename_failure(
    monkeypatch: pytest.MonkeyPatch,
    *,
    before: Path | None = None,
    after: Path | None = None,
) -> None:
    """Fail an `os.rename` whose destination is `before`, or fail immediately once `after` lands."""
    real = os.rename

    def fake(src: Any, dst: Any, **kwargs: Any) -> None:
        if before is not None and Path(dst) == before:
            raise OSError(errno.EIO, "injected failure")
        real(src, dst, **kwargs)
        if after is not None and Path(dst) == after:
            raise OSError(errno.EIO, "injected failure")

    monkeypatch.setattr(os, "rename", fake)


def test_failure_before_the_backup_rename_leaves_the_original_draft(
    scene: Scene, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _snapshot(scene.bundle_root)
    _inject_rename_failure(monkeypatch, before=scene.backup)

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 3
    assert _codes(outcome) == [IssueCode.IO_ERROR]
    assert _snapshot(scene.bundle_root) == before
    assert not scene.backup.exists()
    assert sorted(entry.name for entry in drafts_dir(scene.bundle_root).iterdir()) == [DRAFT_NAME]


def test_failure_after_the_backup_rename_leaves_the_exact_backup(
    scene: Scene, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = _snapshot(scene.draft)
    _inject_rename_failure(monkeypatch, after=scene.backup)

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 3
    assert _snapshot(scene.backup) == original
    # No mixed draft: the name is either absent or the original, never half of each.
    assert not scene.draft.exists()
    assert sorted(entry.name for entry in drafts_dir(scene.bundle_root).iterdir()) == [
        scene.backup.name
    ]


def test_failure_before_the_rebased_install_leaves_the_exact_backup(
    scene: Scene, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = _snapshot(scene.draft)
    _inject_rename_failure(monkeypatch, before=scene.draft)

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 3
    assert _snapshot(scene.backup) == original
    assert not scene.draft.exists()
    assert sorted(entry.name for entry in drafts_dir(scene.bundle_root).iterdir()) == [
        scene.backup.name
    ]


def test_failure_while_vacating_a_reused_backup_leaves_the_retained_backup(
    scene: Scene, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reuse path vacates the draft to a temporary name, so its window is a different one.

    §21 still has to hold across it: the original is recoverable from the backup that was proved
    byte-identical, and the draft name holds either the original or nothing.
    """
    shutil.copytree(scene.draft, scene.backup)
    original = _snapshot(scene.draft)
    real = os.rename

    def fake(src: Any, dst: Any, **kwargs: Any) -> None:
        real(src, dst, **kwargs)
        if Path(dst).name.startswith(DRAFT_TEMP_PREFIX):
            raise OSError(errno.EIO, "injected failure")

    monkeypatch.setattr(os, "rename", fake)

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 3
    assert _codes(outcome) == [IssueCode.IO_ERROR]
    assert _snapshot(scene.backup) == original
    assert not scene.draft.exists()
    vacated = [
        entry
        for entry in drafts_dir(scene.bundle_root).iterdir()
        if entry.name.startswith(DRAFT_TEMP_PREFIX)
    ]
    assert [_snapshot(entry) for entry in vacated] == [original]


def test_a_staged_tree_that_does_not_read_back_is_never_installed(
    scene: Scene, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rebased draft is verified by rereading it, not by trusting the writer."""
    before = _snapshot(scene.bundle_root)
    real = rebase_module.document_bytes

    def tampered(payload: Any, *, logical_path: PurePosixPath) -> bytes:
        if logical_path == PurePosixPath("manifest.yaml"):
            payload = {**payload, "profile_id": "profile.tampered"}
        return real(payload, logical_path=logical_path)

    monkeypatch.setattr(rebase_module, "document_bytes", tampered)

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 3
    assert _codes(outcome) == [IssueCode.INTERNAL_ERROR]
    assert _snapshot(scene.bundle_root) == before
    assert sorted(entry.name for entry in drafts_dir(scene.bundle_root).iterdir()) == [DRAFT_NAME]


def test_a_missing_blob_refuses_before_anything_is_written(scene: Scene) -> None:
    """The rebased manifest states an evidence-set digest; without the bytes it cannot."""
    from tests.profile_bundle.conftest import BLOB_SHA256

    blob_path(scene.bundle_root, BLOB_SHA256).unlink()
    before = _snapshot(scene.bundle_root)

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.MISSING_BLOB]
    assert _snapshot(scene.bundle_root) == before


def test_a_bundle_root_that_does_not_exist_is_refused_without_being_created(
    tmp_path: Path,
) -> None:
    """`filelock` would create the directory to hold the lockfile; a mistyped path must not."""
    outcome = rebase_draft(tmp_path / "not-a-bundle", name=DRAFT_NAME)

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.BUNDLE_NOT_FOUND]
    assert not (tmp_path / "not-a-bundle").exists()


@pytest.mark.skipif(os.name != "posix", reason="mode bits do not deny directory writes on Windows")
def test_a_bundle_root_that_cannot_be_locked_reports_io_without_leaking_a_path(
    scene: Scene,
) -> None:
    if os.geteuid() == 0:  # pragma: no cover - root ignores the mode bits entirely
        pytest.skip("running as root, so a read-only directory is still writable")
    scene.bundle_root.chmod(0o500)
    try:
        outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)
    finally:
        scene.bundle_root.chmod(0o700)

    assert outcome.exit_code == 3
    assert _codes(outcome) == [IssueCode.IO_ERROR]
    assert str(scene.bundle_root) not in outcome.diagnostics[0].message


def test_a_selected_revision_that_will_not_parse_refuses_without_writing(scene: Scene) -> None:
    (scene.current.revision_dir / SKILLS_PATH).write_bytes(b"skills:\n  - [broken\n")
    before = _snapshot(scene.bundle_root)

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 1
    assert all(finding.path == SKILLS_PATH.as_posix() for finding in outcome.diagnostics)
    assert _snapshot(scene.bundle_root) == before


def test_a_file_only_the_draft_has_survives_the_rebase(scene: Scene) -> None:
    """An entity-owned file the owner added exists in neither the base nor the new revision."""
    added = PurePosixPath("facts/projects/project.new-thing.yaml")
    (scene.draft / added).write_bytes(
        quoted_yaml(
            {
                "entity": {
                    "entity_id": "project.new-thing",
                    "entity_type": "project",
                    "display_name": "New Thing",
                    "aliases": [],
                    "created_at": "2026-08-10",
                    "reviewed_at": "2026-08-10",
                    "status": "prototype",
                },
                "facts": [],
            },
            logical_path=added,
        )
    )

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 0, outcome.diagnostics
    assert (scene.draft / added).exists()
    document = load_documents(scene.draft, mode="draft").by_path[added]
    assert isinstance(document, ProjectFactsDocument)
    assert document.entity.entity_id == "project.new-thing"


def test_a_bundle_with_no_selected_revision_has_nothing_to_rebase_onto(tmp_path: Path) -> None:
    bundle_root = tmp_path / "career-profile"
    drafts_dir(bundle_root).mkdir(parents=True)

    outcome = rebase_draft(bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.NO_CURRENT_REVISION]


def test_a_draft_that_will_not_parse_is_reported_per_document(scene: Scene) -> None:
    (scene.draft / SKILLS_PATH).write_bytes(b"skills:\n  - [broken\n")
    before = _snapshot(scene.bundle_root)

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 1
    assert outcome.diagnostics
    assert all(finding.path == SKILLS_PATH.as_posix() for finding in outcome.diagnostics)
    assert _snapshot(scene.bundle_root) == before


def test_a_selected_revision_whose_manifest_disagrees_with_the_pointer_refuses(
    scene: Scene,
) -> None:
    manifest_path = scene.current.revision_dir / "manifest.yaml"
    data = load_yaml_bytes(manifest_path.read_bytes(), logical_path=PurePosixPath("manifest.yaml"))
    data["bundle_digest"] = "sha256:" + "e" * 64
    manifest_path.write_bytes(quoted_yaml(data, logical_path=PurePosixPath("manifest.yaml")))

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.CURRENT_POINTER_MISMATCH]
    assert not scene.backup.exists()


def test_a_parent_revision_that_will_not_parse_is_an_unverifiable_ancestor(scene: Scene) -> None:
    (scene.parent.revision_dir / SKILLS_PATH).write_bytes(b"skills:\n  - [broken\n")
    before = _snapshot(scene.bundle_root)

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.UNVERIFIABLE_ANCESTOR]
    assert _snapshot(scene.bundle_root) == before


def test_a_parentless_draft_collides_with_everything_the_revision_already_states(
    tmp_path: Path,
) -> None:
    """`init`'s empty draft against a populated revision: no base, so nothing can be attributed."""
    bundle_root = tmp_path / "career-profile"
    from boardwatch.profile_bundle.drafts import init_draft

    assert init_draft(bundle_root, name="fresh").exit_code == 0
    promote_example_tree(bundle_root)
    before = _snapshot(bundle_root)

    outcome = rebase_draft(bundle_root, name="fresh")

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.DRAFT_REBASE_CONFLICT]
    finding = outcome.diagnostics[0]
    assert finding.details["record_ids"] == []
    assert finding.record_id is None
    assert finding.path is not None
    assert _snapshot(bundle_root) == before


def test_a_draft_missing_its_evidence_document_cannot_state_a_digest(scene: Scene) -> None:
    (scene.draft / "evidence" / "records.yaml").unlink()
    before = _snapshot(scene.bundle_root)

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.MISSING_REQUIRED_FILE]
    assert outcome.diagnostics[0].path == "evidence/records.yaml"
    assert _snapshot(scene.bundle_root) == before


def test_a_writer_that_raises_installs_nothing(
    scene: Scene, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _snapshot(scene.bundle_root)

    def refuse(payload: Any, *, logical_path: PurePosixPath) -> bytes:
        raise DocumentEmitError(f"{logical_path}: injected")

    monkeypatch.setattr(rebase_module, "document_bytes", refuse)

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 3
    assert _codes(outcome) == [IssueCode.INTERNAL_ERROR]
    assert _snapshot(scene.bundle_root) == before


def test_a_staged_tree_that_will_not_parse_installs_nothing(
    scene: Scene, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = rebase_module.document_bytes

    def truncate(payload: Any, *, logical_path: PurePosixPath) -> bytes:
        if logical_path == PurePosixPath("manifest.yaml"):
            return b"state: 'draft'\n"
        return real(payload, logical_path=logical_path)

    monkeypatch.setattr(rebase_module, "document_bytes", truncate)
    before = _snapshot(scene.bundle_root)

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 1
    assert IssueCode.MODEL_VALIDATION_ERROR in _codes(outcome)
    assert _snapshot(scene.bundle_root) == before


def test_a_backup_path_symlinked_at_the_draft_is_not_this_draft_byte_for_byte(
    scene: Scene,
) -> None:
    """The trivially-equal case: comparing a draft with itself must not authorise deleting it."""
    scene.backup.symlink_to(scene.draft)
    original = _snapshot(scene.draft)

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.DRAFT_BACKUP_CONFLICT]
    # §21: the original or the exact backup survives. Here that has to be the original.
    assert _snapshot(scene.draft) == original
    assert scene.backup.is_symlink()


def test_a_backup_path_symlinked_outside_the_bundle_is_refused(
    scene: Scene, tmp_path: Path
) -> None:
    """A byte-identical copy somewhere else is still not a backup inside this bundle."""
    outside = tmp_path / "elsewhere"
    shutil.copytree(scene.draft, outside)
    scene.backup.symlink_to(outside)
    original = _snapshot(scene.draft)

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.DRAFT_BACKUP_CONFLICT]
    assert _snapshot(scene.draft) == original
    assert _snapshot(outside) == original


def test_a_symlinked_backup_is_never_read_as_this_draft(scene: Scene) -> None:
    shutil.copytree(scene.draft, scene.backup)
    target = scene.backup / SKILLS_PATH
    target.unlink()
    target.symlink_to(scene.draft / SKILLS_PATH)
    before = _snapshot(scene.bundle_root)

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.DRAFT_BACKUP_CONFLICT]
    assert _snapshot(scene.bundle_root) == before


# --------------------------------------------------------------------------------------
# The shared writer lock
# --------------------------------------------------------------------------------------


def test_contention_refuses_immediately_without_waiting_or_writing(
    scene: Scene, lock_holder: Callable[[Path], subprocess.Popen[str]]
) -> None:
    lock_holder(scene.bundle_root)
    before = _snapshot(scene.bundle_root)

    started = time.monotonic()
    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)
    elapsed = time.monotonic() - started

    assert outcome.exit_code == 3
    assert _codes(outcome) == [IssueCode.BUNDLE_LOCK_HELD]
    assert elapsed < 2.0
    assert _snapshot(scene.bundle_root) == before


def test_the_lock_is_taken_before_current_is_reread(
    scene: Scene,
    lock_holder: Callable[[Path], subprocess.Popen[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ordering proved by making the pointer read fatal: a contended run must never reach it."""
    lock_holder(scene.bundle_root)

    def forbidden(bundle_root: Path) -> None:
        raise AssertionError("CURRENT was read before the lock was held")

    monkeypatch.setattr(rebase_module, "read_current_once", forbidden)

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert _codes(outcome) == [IssueCode.BUNDLE_LOCK_HELD]


def test_a_persistent_lockfile_left_by_a_killed_process_is_not_a_held_lock(
    scene: Scene, lock_holder: Callable[[Path], subprocess.Popen[str]]
) -> None:
    process = lock_holder(scene.bundle_root)
    process.kill()
    process.wait()
    # The killed holder never ran its own release, so the file it created is still there. §6 makes
    # that meaningless, and this is the state the next command has to survive.
    assert lock_path(scene.bundle_root).exists(), "the lockfile is expected to survive a SIGKILL"

    outcome = rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert outcome.exit_code == 0, outcome.diagnostics
    assert _skills(scene.draft).skills[0].canonical_name == REVISION_TWO_NAME


def test_the_lock_helper_refuses_a_second_holder_and_releases_on_exit(
    scene: Scene, lock_holder: Callable[[Path], subprocess.Popen[str]]
) -> None:
    process = lock_holder(scene.bundle_root)
    with pytest.raises(BundleLockHeldError):
        with bundle_lock(scene.bundle_root):
            pass

    process.kill()
    process.wait()
    with bundle_lock(scene.bundle_root) as held:
        assert held == lock_path(scene.bundle_root)
    # Released, so the same process can take it again.
    with bundle_lock(scene.bundle_root):
        pass


def test_a_second_acquire_in_one_process_does_not_blame_another_process(scene: Scene) -> None:
    """A fresh `FileLock` per call means one process can contend with itself, and T16 will.

    The refusal is correct; the sentence has to be too, or the operator goes looking for a process
    that is not there.
    """
    with bundle_lock(scene.bundle_root):
        with pytest.raises(BundleLockHeldError) as raised:
            with bundle_lock(scene.bundle_root):
                pass

    assert "another process" not in str(raised.value)
    assert LOCK_FILE in str(raised.value)


def test_the_lock_is_never_broken_or_removed(
    scene: Scene, lock_holder: Callable[[Path], subprocess.Popen[str]]
) -> None:
    lock_holder(scene.bundle_root)
    stat_before = lock_path(scene.bundle_root).stat()

    rebase_draft(scene.bundle_root, name=DRAFT_NAME)

    assert lock_path(scene.bundle_root).exists()
    assert lock_path(scene.bundle_root).stat().st_ino == stat_before.st_ino


# --------------------------------------------------------------------------------------
# Documents the merge must not have disturbed
# --------------------------------------------------------------------------------------


def test_the_rebase_writes_nothing_outside_the_draft_and_its_backup(scene: Scene) -> None:
    outside_before = {
        name: value
        for name, value in _snapshot(scene.bundle_root).items()
        if not name.startswith("drafts/")
    }

    assert rebase_draft(scene.bundle_root, name=DRAFT_NAME).exit_code == 0

    outside_after = {
        name: value
        for name, value in _snapshot(scene.bundle_root).items()
        if not name.startswith("drafts/")
    }
    assert outside_after == outside_before


def test_untouched_documents_keep_the_selected_revisions_bytes(scene: Scene) -> None:
    """A document neither side edited is copied, not re-emitted; the first diff stays readable."""
    assert rebase_draft(scene.bundle_root, name=DRAFT_NAME).exit_code == 0

    relative = PurePosixPath("policy/predicates.yaml")
    assert (scene.draft / relative).read_bytes() == (
        scene.current.revision_dir / relative
    ).read_bytes()


def test_the_merged_tree_parses_as_a_draft_of_the_new_parent(scene: Scene) -> None:
    assert rebase_draft(scene.bundle_root, name=DRAFT_NAME).exit_code == 0

    documents: BundleDocuments = load_documents(scene.draft, mode="draft")
    assert documents.is_draft
    difference = diff_records(scene.current.documents, documents)
    assert difference.added == frozenset({ADDED_SKILL})
    assert difference.changed == frozenset()
    assert difference.removed == frozenset()
