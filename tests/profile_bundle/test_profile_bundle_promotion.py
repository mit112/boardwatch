"""Normal promotion, the derivation it performs, and the exact-target reuse of §6 step 7.

Three claims carry the rest, and each is checked against the filesystem or against a second
computation, never against what the operation said about itself.

**The digest order is the contract.** The candidate digest must come from the draft as the owner
approved it — before the change record exists — and the bundle digest from the finished tree. The
order is checked here by recomputing both from a different path: the candidate through
`candidate_content_digest` over the pre-promotion draft, and the bundle digest through
`bundle_digest` over the bytes that landed on disk, using the in-memory blob reader rather than the
filesystem one production used. `tests/profile_bundle/conftest.py`'s own promotion helpers then
promote a *further* revision on top of the production one, which only works if production produced a
revision those helpers recognise as a parent.

**An existing digest target is content, not a name.** A torn earlier attempt leaves a complete
directory whose name is its digest; re-running must reuse exactly that directory and refuse anything
that differs, retaining both.

**`CURRENT` has one byte form.** T13's reader accepted `json.dumps(indent=4)` because no writer
existed to say otherwise. It does now, so the loose form is refused here.
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

from boardwatch.profile_bundle import promotion as promotion_module
from boardwatch.profile_bundle.canonical import (
    APPROVAL_LEDGER_PATH,
    CHANGE_LEDGER_PATH,
    bundle_digest,
)
from boardwatch.profile_bundle.drafts import checkout_current
from boardwatch.profile_bundle.errors import IssueCode
from boardwatch.profile_bundle.inspection import inventory
from boardwatch.profile_bundle.models.history import (
    Actor,
    ApprovalLedger,
    ChangeLedger,
    ChangeRecord,
)
from boardwatch.profile_bundle.models.manifests import RevisionManifest
from boardwatch.profile_bundle.paths import (
    LOCK_FILE,
    approval_path,
    complete_marker_path,
    current_path,
    digest_token,
    draft_root,
    lock_path,
    revision_root,
    revisions_dir,
)
from boardwatch.profile_bundle.promotion import (
    PROMOTION_TEMP_PREFIX,
    PromotionRequest,
    TargetConflictReason,
    promote,
)
from boardwatch.profile_bundle.storage import read_current_once, selected_documents
from boardwatch.profile_bundle.validation import load_documents
from boardwatch.profile_bundle.validation.digest import (
    PointerError,
    current_pointer_bytes,
    read_complete,
    read_current,
)
from boardwatch.profile_bundle.validation.run import validate_bundle
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from tests.profile_bundle.conftest import (
    EXAMPLE_PROFILE_ID,
    PromotedRevisionTree,
    approve_draft,
    blob_reader,
    materialise,
    promote_next_revision,
    quoted_yaml,
)

DRAFT_NAME = "baseline"
SECOND_DRAFT = "work"
SKILLS_PATH = PurePosixPath("skills/inventory.yaml")
ORIGINAL_SKILL = "skill.example-language"
PROMOTED_AT = datetime(2026, 8, 11, 9, 0, tzinfo=UTC)

#: A live holder for the bundle lock, in a real subprocess: contention is the operating system's
#: property and an in-process double would only prove the double behaves like the double.
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


def _request(name: str = DRAFT_NAME, **overrides: Any) -> PromotionRequest:
    values: dict[str, Any] = {
        "draft_name": name,
        "summary": "Promote the synthetic baseline",
        "actor": Actor.OWNER,
        "created_at": PROMOTED_AT,
    }
    values.update(overrides)
    return PromotionRequest(**values)


def _approve(
    bundle_root: Path,
    draft: Path,
    *,
    parent: Path | None = None,
    stamp_id: str = "approval-stamp.000001",
) -> str:
    return approve_draft(
        bundle_root, draft, parent=parent, stamp_id=stamp_id, approved_at=PROMOTED_AT
    )


@dataclass(frozen=True)
class Scene:
    """A bundle holding the example as an approved, parentless, promotable draft."""

    bundle_root: Path
    draft: Path
    candidate: str


@pytest.fixture
def scene(tmp_path: Path) -> Scene:
    bundle_root = tmp_path / "career-profile"
    bundle_root.mkdir()
    bundle = materialise(bundle_root, draft_name=DRAFT_NAME)
    return Scene(
        bundle_root=bundle_root,
        draft=bundle.draft,
        candidate=_approve(bundle_root, bundle.draft),
    )


def _promoted(scene: Scene) -> Path:
    """Promote the scene's draft and return the selected revision directory."""
    outcome = promote(scene.bundle_root, _request())
    assert outcome.exit_code == 0, outcome.diagnostics
    assert outcome.value is not None
    return outcome.value.root


def _second_revision(scene: Scene, *, edit: Callable[[Any], None]) -> tuple[Path, Path, str]:
    """Promote revision 1, check out a draft, apply `edit`, approve it, and hand back the pieces."""
    first = _promoted(scene)
    assert checkout_current(scene.bundle_root, name=SECOND_DRAFT).exit_code == 0
    draft = draft_root(scene.bundle_root, SECOND_DRAFT)
    _edit(draft, SKILLS_PATH, edit)
    candidate = _approve(
        scene.bundle_root, draft, parent=first, stamp_id="approval-stamp.000002"
    )
    return first, draft, candidate


def _edit(root: Path, logical: PurePosixPath, mutate: Callable[[Any], None]) -> None:
    path = root / logical
    data = load_yaml_bytes(path.read_bytes(), logical_path=logical)
    mutate(data)
    path.write_bytes(quoted_yaml(data, logical_path=logical))


def _rename_skill(name: str) -> Callable[[Any], None]:
    def mutate(data: Any) -> None:
        data["skills"][0]["canonical_name"] = name

    return mutate


#: Which key each history ledger keeps its entries under, so a test can append to either one.
_LEDGER_FIELD = {CHANGE_LEDGER_PATH: "changes", APPROVAL_LEDGER_PATH: "approvals"}


def _pre_authored_entry(scene: Scene, ledger: PurePosixPath) -> Any:
    """An entry a hand-editor could have put in a first draft's `history/`, valid on its own.

    The approval stamp is the scene's real one, read back from `approvals/` rather than invented, so
    the draft is refused for authoring history and not for authoring something malformed.
    """
    if ledger == APPROVAL_LEDGER_PATH:
        path = approval_path(scene.bundle_root, scene.candidate)
        return load_yaml_bytes(
            path.read_bytes(), logical_path=PurePosixPath(f"approvals/{path.name}")
        )
    return ChangeRecord.model_validate(
        {
            "change_id": "change.000001",
            "revision": 1,
            "parent_bundle_digest": None,
            "actor": Actor.OWNER,
            "authorized_by": Actor.OWNER,
            "summary": "A revision nobody promoted",
            "changed_record_ids": (),
            "created_at": PROMOTED_AT,
        }
    ).model_dump(mode="json")


def _snapshot(root: Path) -> dict[str, bytes]:
    """Every file under `root`, excluding the lockfile, whose persistence §6 makes meaningless."""
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


def _changes(root: Path) -> ChangeLedger:
    document = load_documents(root, mode="revision").by_path[CHANGE_LEDGER_PATH]
    assert isinstance(document, ChangeLedger)
    return document


def _stamps(root: Path) -> ApprovalLedger:
    document = load_documents(root, mode="revision").by_path[
        PurePosixPath("history/approvals.yaml")
    ]
    assert isinstance(document, ApprovalLedger)
    return document


def _temporaries(bundle_root: Path) -> list[str]:
    directory = revisions_dir(bundle_root)
    if not directory.is_dir():
        return []
    return sorted(
        entry.name for entry in directory.iterdir() if entry.name.startswith(PROMOTION_TEMP_PREFIX)
    )


@pytest.fixture
def lock_holder(tmp_path: Path) -> Iterator[Callable[[Path], subprocess.Popen[str]]]:
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
# The revision a promotion produces
# --------------------------------------------------------------------------------------


def test_a_first_promotion_selects_the_revision_it_wrote(scene: Scene) -> None:
    outcome = promote(scene.bundle_root, _request())

    assert outcome.exit_code == 0, outcome.diagnostics
    assert outcome.value is not None
    selection = read_current_once(scene.bundle_root)
    assert selection.revision == 1
    assert selection.bundle_digest == outcome.value.bundle_digest
    assert selection.root.name == digest_token(selection.bundle_digest)
    assert read_complete(selection.root) == selection.bundle_digest
    assert _manifest_of(selection.root).bundle_digest == selection.bundle_digest


def test_the_promoted_revision_validates_from_disk(scene: Scene) -> None:
    """The whole point of writing it: a reader who was handed nothing finds it clean."""
    root = _promoted(scene)

    outcome = validate_bundle(root, bundle_root=scene.bundle_root, mode="revision")

    assert outcome.exit_code == 0, outcome.diagnostics


def test_the_bundle_digest_is_the_one_the_bytes_on_disk_produce(scene: Scene) -> None:
    """Recomputed by a second route: the packaged blob reader, not the filesystem one."""
    root = _promoted(scene)

    recomputed = bundle_digest(load_documents(root, mode="revision"), blob_reader())

    assert recomputed == _manifest_of(root).bundle_digest
    assert root.name == digest_token(recomputed)
    assert read_complete(root) == recomputed
    assert read_current(scene.bundle_root).bundle_digest == recomputed


def test_the_candidate_digest_is_the_one_computed_before_the_change_was_appended(
    scene: Scene,
) -> None:
    """The order §7 forces: the owner approves a tree with no promotion documents in it.

    `scene.candidate` was computed from the draft before `promote` ran, so the promoted revision
    agreeing with it means the change record was appended AFTER the candidate digest was taken. A
    promotion that appended first would produce a different digest and no stamp would be found.
    """
    root = _promoted(scene)
    manifest = _manifest_of(root)

    assert manifest.approved_candidate_digest == scene.candidate
    assert _stamps(root).approvals[-1].candidate_content_digest == scene.candidate
    assert manifest.approval_stamp_id == "approval-stamp.000001"


def test_the_conftest_promotion_helpers_accept_a_production_revision_as_a_parent(
    scene: Scene,
) -> None:
    """The second path: the fixture's own promotion machinery builds revision 2 on production's 1.

    The fixture reproduces the same digest order independently. If production computed its digests
    in another order, or wrote a tree the fixture's parent handling does not recognise, promoting
    onto it would produce a revision that does not validate.
    """
    root = _promoted(scene)
    manifest = _manifest_of(root)
    produced = PromotedRevisionTree(
        bundle_root=scene.bundle_root,
        revision_dir=root,
        bundle_digest=manifest.bundle_digest,
        candidate_digest=manifest.approved_candidate_digest,
        revision=manifest.revision,
        documents=load_documents(root, mode="revision"),
    )

    child = promote_next_revision(produced, mutate=_rename_skill("Fixture Promoted"))

    outcome = validate_bundle(
        child.revision_dir, bundle_root=scene.bundle_root, mode="revision"
    )
    assert outcome.exit_code == 0, outcome.diagnostics
    assert _manifest_of(child.revision_dir).parent_bundle_digest == manifest.bundle_digest


def test_the_promotion_appends_exactly_one_change_and_one_approval(scene: Scene) -> None:
    first, _, _ = _second_revision(scene, edit=_rename_skill("Revision Two"))
    outcome = promote(scene.bundle_root, _request(SECOND_DRAFT))
    assert outcome.exit_code == 0, outcome.diagnostics
    assert outcome.value is not None

    second = outcome.value.root
    assert len(_changes(second).changes) == len(_changes(first).changes) + 1
    assert len(_stamps(second).approvals) == len(_stamps(first).approvals) + 1
    assert _changes(second).changes[: len(_changes(first).changes)] == _changes(first).changes


def test_the_change_record_names_the_records_that_changed(scene: Scene) -> None:
    """§17: derived from the validated draft diff, never from an authored list."""
    _second_revision(scene, edit=_rename_skill("Revision Two"))

    outcome = promote(scene.bundle_root, _request(SECOND_DRAFT))

    assert outcome.exit_code == 0, outcome.diagnostics
    assert outcome.value is not None
    assert _changes(outcome.value.root).changes[-1].changed_record_ids == (ORIGINAL_SKILL,)


def test_the_change_record_derives_its_authority_from_the_stamp_not_the_request(
    scene: Scene,
) -> None:
    """An agent may perform a change; only the owner's stamp authorises it (§17)."""
    outcome = promote(scene.bundle_root, _request(actor=Actor.AGENT))

    assert outcome.exit_code == 0, outcome.diagnostics
    assert outcome.value is not None
    change = _changes(outcome.value.root).changes[-1]
    assert change.actor is Actor.AGENT
    assert change.authorized_by is Actor.OWNER
    assert _manifest_of(outcome.value.root).created_by is Actor.AGENT


def test_the_revision_number_is_contiguous_and_the_profile_id_is_stable(scene: Scene) -> None:
    first, _, _ = _second_revision(scene, edit=_rename_skill("Revision Two"))

    outcome = promote(scene.bundle_root, _request(SECOND_DRAFT))

    assert outcome.exit_code == 0, outcome.diagnostics
    assert outcome.value is not None
    assert _manifest_of(first).revision == 1
    assert outcome.value.revision == 2
    assert _manifest_of(outcome.value.root).profile_id == EXAMPLE_PROFILE_ID
    assert _manifest_of(outcome.value.root).parent_bundle_digest == _manifest_of(
        first
    ).bundle_digest
    # The number is never filesystem identity: both directories are named by their digests only.
    assert not any("revision" in entry.name for entry in revisions_dir(scene.bundle_root).iterdir())


def test_the_manifest_states_the_evidence_set_digest_the_owner_approved(scene: Scene) -> None:
    """§7 step 3 makes this the one field that is a claim about the documents beside it.

    The candidate view the owner approves overwrites whatever the draft declared, so promotion
    recomputes it rather than carrying a stale declaration into an immutable revision.
    """
    _edit(
        scene.draft,
        PurePosixPath("manifest.yaml"),
        lambda data: data.update({"evidence_set_digest": "sha256:" + "b" * 64}),
    )
    candidate = _approve(scene.bundle_root, scene.draft)

    outcome = promote(scene.bundle_root, _request())

    assert outcome.exit_code == 0, outcome.diagnostics
    assert outcome.value is not None
    assert _manifest_of(outcome.value.root).evidence_set_digest != "sha256:" + "b" * 64
    assert _manifest_of(outcome.value.root).approved_candidate_digest == candidate


def test_a_successful_promotion_leaves_the_draft_alone(scene: Scene) -> None:
    """§21: no Gate A command deletes a draft, and promotion is not an exception."""
    before = _snapshot(scene.draft)

    assert promote(scene.bundle_root, _request()).exit_code == 0

    assert _snapshot(scene.draft) == before


def test_a_successful_promotion_leaves_no_temporary_behind(scene: Scene) -> None:
    _promoted(scene)

    assert _temporaries(scene.bundle_root) == []
    assert [
        entry.name
        for entry in scene.bundle_root.iterdir()
        if entry.name.startswith(promotion_module.CURRENT_TEMP_PREFIX)
    ] == []


def test_the_promotion_writes_only_the_new_revision_and_the_pointer(scene: Scene) -> None:
    before = _snapshot(scene.bundle_root)

    root = _promoted(scene)

    added = set(_snapshot(scene.bundle_root)) - set(before)
    prefix = f"revisions/{root.name}/"
    assert added - {"CURRENT"} == {name for name in added if name.startswith(prefix)}
    unchanged = {
        name: value
        for name, value in _snapshot(scene.bundle_root).items()
        if name in before
    }
    assert unchanged == before


# --------------------------------------------------------------------------------------
# The pointer's byte contract
# --------------------------------------------------------------------------------------


def test_current_is_written_in_the_canonical_form(scene: Scene) -> None:
    root = _promoted(scene)
    manifest = _manifest_of(root)

    raw = current_path(scene.bundle_root).read_bytes()

    assert raw == current_pointer_bytes(read_current(scene.bundle_root))
    assert raw.endswith(b"\n") and raw.count(b"\n") == 1
    assert json.loads(raw) == {
        "bundle_digest": manifest.bundle_digest,
        "revision": manifest.revision,
    }


def test_a_pointer_that_is_not_in_the_canonical_form_is_refused(scene: Scene) -> None:
    """The T13 reader accepted this; the writer now decides what canonical means."""
    _promoted(scene)
    pointer = read_current(scene.bundle_root)
    current_path(scene.bundle_root).write_text(
        json.dumps(pointer.model_dump(mode="json"), indent=4) + "\n", encoding="utf-8"
    )

    with pytest.raises(PointerError, match="canonical"):
        read_current(scene.bundle_root)

    outcome = inventory(scene.bundle_root)
    assert IssueCode.CURRENT_POINTER_MISMATCH in _codes(outcome)


def test_a_pointer_carrying_an_extra_key_is_refused(scene: Scene) -> None:
    _promoted(scene)
    pointer = read_current(scene.bundle_root)
    payload = {**pointer.model_dump(mode="json"), "note": "hand written"}
    current_path(scene.bundle_root).write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )

    with pytest.raises(PointerError):
        read_current(scene.bundle_root)


# --------------------------------------------------------------------------------------
# Refusals that write nothing
# --------------------------------------------------------------------------------------


def test_a_draft_that_is_not_there_is_a_typed_state_refusal(scene: Scene) -> None:
    before = _snapshot(scene.bundle_root)

    outcome = promote(scene.bundle_root, _request("absent"))

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.DRAFT_NOT_FOUND]
    assert _snapshot(scene.bundle_root) == before


@pytest.mark.parametrize("outside", [True, False])
def test_a_symlinked_draft_is_refused_rather_than_promoted(
    scene: Scene, tmp_path: Path, outside: bool
) -> None:
    """A revision's content must come from inside the root, and a draft is where it comes from.

    Both arms are the same rule about the same path: what makes `drafts/<name>` unpromotable is
    that it is a link, not where the link goes. The `outside` arm is the one that matters — the
    promoted revision would be a copy of bytes nobody can see from the bundle root, and it would
    hash and validate perfectly afterwards, so there is no later check that could notice. The inside
    arm shows the refusal does not depend on the target escaping.

    `inventory` already refuses to call either one a draft, which is what makes accepting it here a
    disagreement between two commands rather than a merely permissive rule.
    """
    linked = (tmp_path / "outside-draft") if outside else (scene.draft.parent / "twin")
    shutil.copytree(scene.draft, linked)
    link = scene.draft.parent / "linked"
    link.symlink_to(linked, target_is_directory=True)
    before = _snapshot(scene.bundle_root)

    outcome = promote(scene.bundle_root, _request("linked"))

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.SYMLINK_REFUSED]
    assert not revisions_dir(scene.bundle_root).exists()
    assert _snapshot(scene.bundle_root) == before
    listing = inventory(scene.bundle_root)
    assert listing.value is not None
    assert "linked" not in listing.value.drafts


def test_a_path_that_is_not_a_bundle_is_refused_without_being_created(tmp_path: Path) -> None:
    """`filelock` would create the directory to hold the lockfile; a mistyped path must not."""
    outcome = promote(tmp_path / "not-a-bundle", _request())

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.DRAFT_NOT_FOUND]
    assert not (tmp_path / "not-a-bundle").exists()


def test_a_draft_whose_parent_has_moved_is_refused_with_the_draft_intact(scene: Scene) -> None:
    """§21: exit 1, `stale_draft_parent`, and `rebase-draft` is the drain."""
    _promoted(scene)  # the scene's draft is parentless, and a revision now exists
    before = _snapshot(scene.draft)
    revisions = _snapshot(revisions_dir(scene.bundle_root))
    pointer = current_path(scene.bundle_root).read_bytes()

    outcome = promote(scene.bundle_root, _request())

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.STALE_DRAFT_PARENT]
    assert _snapshot(scene.draft) == before
    assert _snapshot(revisions_dir(scene.bundle_root)) == revisions
    assert current_path(scene.bundle_root).read_bytes() == pointer


def test_a_draft_with_no_approval_stamp_is_refused(tmp_path: Path) -> None:
    bundle_root = tmp_path / "career-profile"
    bundle_root.mkdir()
    materialise(bundle_root, draft_name=DRAFT_NAME)
    before = _snapshot(bundle_root)

    outcome = promote(bundle_root, _request())

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.MISSING_APPROVAL_STAMP]
    assert _snapshot(bundle_root) == before


def test_a_draft_edited_after_approval_no_longer_has_a_stamp(scene: Scene) -> None:
    """The binding is the digest, so an edit invalidates the approval by arithmetic."""
    _edit(scene.draft, SKILLS_PATH, _rename_skill("Edited After Approval"))
    before = _snapshot(scene.bundle_root)

    outcome = promote(scene.bundle_root, _request())

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.MISSING_APPROVAL_STAMP]
    assert approval_path(scene.bundle_root, scene.candidate).exists()
    assert _snapshot(scene.bundle_root) == before


def test_a_stamp_filed_under_a_digest_it_does_not_approve_is_stale(scene: Scene) -> None:
    """A copied or hand-edited stamp: trusting the filename would let one approval cover anything."""
    original = approval_path(scene.bundle_root, scene.candidate)
    data = load_yaml_bytes(original.read_bytes(), logical_path=PurePosixPath("approvals/x.yaml"))
    data["candidate_content_digest"] = "sha256:" + "c" * 64
    original.write_bytes(quoted_yaml(data, logical_path=PurePosixPath("approvals/x.yaml")))
    before = _snapshot(scene.bundle_root)

    outcome = promote(scene.bundle_root, _request())

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.STALE_APPROVAL_STAMP]
    assert _snapshot(scene.bundle_root) == before


def test_a_draft_that_appended_to_the_change_ledger_itself_is_refused(scene: Scene) -> None:
    """§17: the ledgers are append-only and promotion is the only thing that appends to them."""
    _, draft, _ = _second_revision(scene, edit=_rename_skill("Revision Two"))
    forged = load_yaml_bytes(
        (draft / CHANGE_LEDGER_PATH).read_bytes(), logical_path=CHANGE_LEDGER_PATH
    )
    invented = copy.deepcopy(forged["changes"][-1])
    invented.update(
        {
            "change_id": "change.999999",
            "revision": len(forged["changes"]) + 1,
            "parent_bundle_digest": _manifest_of(
                revision_root(
                    scene.bundle_root, read_current(scene.bundle_root).bundle_digest
                )
            ).bundle_digest,
        }
    )
    forged["changes"].append(invented)
    (draft / CHANGE_LEDGER_PATH).write_bytes(
        quoted_yaml(forged, logical_path=CHANGE_LEDGER_PATH)
    )
    before = _snapshot(scene.bundle_root)

    outcome = promote(scene.bundle_root, _request(SECOND_DRAFT))

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.LEDGER_PREFIX_CHANGED]
    assert outcome.diagnostics[0].path == CHANGE_LEDGER_PATH.as_posix()
    assert _snapshot(scene.bundle_root) == before


@pytest.mark.parametrize("ledger", [CHANGE_LEDGER_PATH, APPROVAL_LEDGER_PATH])
def test_a_first_promotion_whose_draft_pre_authored_history_is_refused(
    scene: Scene, ledger: PurePosixPath
) -> None:
    """The same rule for revision 1, where there is no parent to compare against.

    Revision 1 inherits nothing, so "the parent's entries unchanged" means "empty" — and promotion
    appends the first change record and the first stamp itself. Running the comparison only for a
    parented draft left the ledger models as the first thing to see a pre-authored entry, and they
    raise, which leaves `promote` as a `ValidationError` rather than one of §21's exit codes.

    The negative control is every other test in this file: the same scene without the pre-authored
    entry promotes.
    """
    document = load_yaml_bytes((scene.draft / ledger).read_bytes(), logical_path=ledger)
    document[_LEDGER_FIELD[ledger]].append(_pre_authored_entry(scene, ledger))
    (scene.draft / ledger).write_bytes(quoted_yaml(document, logical_path=ledger))
    # Re-approved because `history/changes.yaml` is inside the candidate view: without this the
    # draft would simply have no stamp, and the refusal would be about the approval instead.
    _approve(scene.bundle_root, scene.draft)
    before = _snapshot(scene.bundle_root)

    outcome = promote(scene.bundle_root, _request())

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.LEDGER_PREFIX_CHANGED]
    assert outcome.diagnostics[0].path == ledger.as_posix()
    assert _snapshot(scene.bundle_root) == before


def test_a_stamp_id_the_parent_ledger_already_holds_is_a_typed_refusal(scene: Scene) -> None:
    """Nothing in `src/` generates a stamp ID, so a repeat is the filing tool's to make.

    `ApprovalLedger` refuses a duplicate `approval_stamp_id`, and promotion is what hands it the
    stamp, so the refusal is promotion's to report rather than to raise through.
    """
    first = _promoted(scene)
    assert checkout_current(scene.bundle_root, name=SECOND_DRAFT).exit_code == 0
    draft = draft_root(scene.bundle_root, SECOND_DRAFT)
    _edit(draft, SKILLS_PATH, _rename_skill("Revision Two"))
    _approve(scene.bundle_root, draft, parent=first, stamp_id="approval-stamp.000001")
    before = _snapshot(scene.bundle_root)

    outcome = promote(scene.bundle_root, _request(SECOND_DRAFT))

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.MODEL_VALIDATION_ERROR]
    assert outcome.diagnostics[0].path == "history"
    assert _snapshot(scene.bundle_root) == before


@pytest.mark.parametrize(
    "overrides",
    [
        {"summary": ""},
        {"summary": "   "},
        {"created_at": PROMOTED_AT.replace(tzinfo=None)},
    ],
    ids=["blank-summary", "whitespace-summary", "naive-timestamp"],
)
def test_a_request_the_change_record_refuses_is_a_typed_refusal(
    scene: Scene, overrides: dict[str, Any]
) -> None:
    """`PromotionRequest` is a plain dataclass, so `ChangeRecord` is the first thing to see these.

    Its field types are the rules and they are not restated here — what is asserted is that the
    refusal reaches the operator as an outcome. The negative control is the test below, whose
    request differs only in carrying an offset `ChangeRecord` accepts.
    """
    before = _snapshot(scene.bundle_root)

    outcome = promote(scene.bundle_root, _request(**overrides))

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.MODEL_VALIDATION_ERROR]
    assert outcome.diagnostics[0].path == CHANGE_LEDGER_PATH.as_posix()
    assert _snapshot(scene.bundle_root) == before


def test_a_created_at_in_another_offset_is_normalised_and_promoted(scene: Scene) -> None:
    """The negative control for the refusals above: an aware timestamp is accepted, not refused."""
    elsewhere = PROMOTED_AT.astimezone(timezone(timedelta(hours=5, minutes=30)))
    assert elsewhere.utcoffset() != timedelta(0)

    outcome = promote(scene.bundle_root, _request(created_at=elsewhere))

    assert outcome.exit_code == 0, outcome.diagnostics
    assert outcome.value is not None
    assert _changes(outcome.value.root).changes[0].created_at == PROMOTED_AT


def test_a_draft_that_rewrote_a_promoted_change_is_refused(scene: Scene) -> None:
    _, draft, _ = _second_revision(scene, edit=_rename_skill("Revision Two"))
    rewritten = load_yaml_bytes(
        (draft / CHANGE_LEDGER_PATH).read_bytes(), logical_path=CHANGE_LEDGER_PATH
    )
    rewritten["changes"][0]["summary"] = "A history nobody promoted"
    (draft / CHANGE_LEDGER_PATH).write_bytes(
        quoted_yaml(rewritten, logical_path=CHANGE_LEDGER_PATH)
    )
    before = _snapshot(scene.bundle_root)

    outcome = promote(scene.bundle_root, _request(SECOND_DRAFT))

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.LEDGER_PREFIX_CHANGED]
    assert _snapshot(scene.bundle_root) == before


def test_a_parent_whose_documents_were_edited_after_promotion_cannot_be_extended(
    scene: Scene,
) -> None:
    """§21: a revision mutated after promotion is a digest failure, and so is building on it."""
    first, _, _ = _second_revision(scene, edit=_rename_skill("Revision Two"))
    _edit(first, SKILLS_PATH, _rename_skill("Edited In Place"))
    before = _snapshot(scene.bundle_root)

    outcome = promote(scene.bundle_root, _request(SECOND_DRAFT))

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.BUNDLE_DIGEST_MISMATCH]
    assert _snapshot(scene.bundle_root) == before


def test_a_revision_manifest_parked_under_drafts_is_refused(scene: Scene) -> None:
    root = _promoted(scene)
    shutil.copytree(root, draft_root(scene.bundle_root, SECOND_DRAFT))
    complete_marker_path(draft_root(scene.bundle_root, SECOND_DRAFT)).unlink()

    outcome = promote(scene.bundle_root, _request(SECOND_DRAFT))

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.DRAFT_MANIFEST_INVALID]


# --------------------------------------------------------------------------------------
# The lock
# --------------------------------------------------------------------------------------


def test_contention_refuses_immediately_without_waiting_or_writing(
    scene: Scene, lock_holder: Callable[[Path], subprocess.Popen[str]]
) -> None:
    lock_holder(scene.bundle_root)
    before = _snapshot(scene.bundle_root)

    started = time.monotonic()
    outcome = promote(scene.bundle_root, _request())
    elapsed = time.monotonic() - started

    assert outcome.exit_code == 3
    assert _codes(outcome) == [IssueCode.BUNDLE_LOCK_HELD]
    assert elapsed < 2.0
    assert _snapshot(scene.bundle_root) == before


def test_the_lock_is_taken_before_the_pointer_is_read(
    scene: Scene,
    lock_holder: Callable[[Path], subprocess.Popen[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ordering proved by making the pointer read fatal: a contended run must never reach it."""
    lock_holder(scene.bundle_root)

    def forbidden(bundle_root: Path) -> None:
        raise AssertionError("CURRENT was read before the lock was held")

    monkeypatch.setattr(promotion_module, "read_current_once", forbidden)

    outcome = promote(scene.bundle_root, _request())

    assert _codes(outcome) == [IssueCode.BUNDLE_LOCK_HELD]


def test_a_persistent_lockfile_left_by_a_killed_process_is_not_a_held_lock(
    scene: Scene, lock_holder: Callable[[Path], subprocess.Popen[str]]
) -> None:
    process = lock_holder(scene.bundle_root)
    process.kill()
    process.wait()
    assert lock_path(scene.bundle_root).exists(), "the lockfile is expected to survive a SIGKILL"

    outcome = promote(scene.bundle_root, _request())

    assert outcome.exit_code == 0, outcome.diagnostics


# --------------------------------------------------------------------------------------
# §6 step 7: an existing digest target
# --------------------------------------------------------------------------------------


def _torn_before_the_pointer(scene: Scene) -> Path:
    """Promote, then remove `CURRENT`: the state a crash between steps 7 and 8 leaves behind."""
    root = _promoted(scene)
    current_path(scene.bundle_root).unlink()
    return root


def test_an_exact_existing_target_is_reused_rather_than_rewritten(scene: Scene) -> None:
    root = _torn_before_the_pointer(scene)
    before = _snapshot(root)
    inode = root.stat().st_ino

    outcome = promote(scene.bundle_root, _request())

    assert outcome.exit_code == 0, outcome.diagnostics
    assert outcome.value is not None
    assert outcome.value.root == root
    assert _snapshot(root) == before
    assert root.stat().st_ino == inode, "the retained directory was replaced rather than reused"
    assert [entry.name for entry in revisions_dir(scene.bundle_root).iterdir()] == [root.name]
    assert _temporaries(scene.bundle_root) == []
    assert read_current(scene.bundle_root).bundle_digest == _manifest_of(root).bundle_digest


def test_a_target_without_its_marker_is_a_conflict_that_retains_both(scene: Scene) -> None:
    root = _torn_before_the_pointer(scene)
    complete_marker_path(root).unlink()
    before = _snapshot(root)

    outcome = promote(scene.bundle_root, _request())

    assert outcome.exit_code == 3
    assert _codes(outcome) == [IssueCode.PROMOTION_TARGET_CONFLICT]
    assert outcome.diagnostics[0].details["reason"] == TargetConflictReason.MARKER_MISSING.value
    assert _snapshot(root) == before
    assert len(_temporaries(scene.bundle_root)) == 1
    assert not current_path(scene.bundle_root).exists()


def test_a_target_whose_content_differs_is_a_conflict_that_retains_both(scene: Scene) -> None:
    root = _torn_before_the_pointer(scene)
    _edit(root, SKILLS_PATH, _rename_skill("Not What This Digest Names"))
    before = _snapshot(root)

    outcome = promote(scene.bundle_root, _request())

    assert outcome.exit_code == 3
    assert _codes(outcome) == [IssueCode.PROMOTION_TARGET_CONFLICT]
    assert outcome.diagnostics[0].details["reason"] == TargetConflictReason.CONTENT_DIFFERS.value
    assert _snapshot(root) == before
    retained = _temporaries(scene.bundle_root)
    assert len(retained) == 1
    assert not current_path(scene.bundle_root).exists()


def test_a_target_with_an_extra_file_is_a_conflict(scene: Scene) -> None:
    root = _torn_before_the_pointer(scene)
    (root / "facts" / "projects" / "project.extra.yaml").write_bytes(b"facts: []\n")

    outcome = promote(scene.bundle_root, _request())

    assert outcome.exit_code == 3
    assert _codes(outcome) == [IssueCode.PROMOTION_TARGET_CONFLICT]
    assert (root / "facts" / "projects" / "project.extra.yaml").exists()


def test_a_target_whose_marker_names_another_revision_is_a_conflict(scene: Scene) -> None:
    root = _torn_before_the_pointer(scene)
    complete_marker_path(root).write_text("sha256:" + "d" * 64 + "\n", encoding="utf-8")

    outcome = promote(scene.bundle_root, _request())

    assert outcome.exit_code == 3
    assert _codes(outcome) == [IssueCode.PROMOTION_TARGET_CONFLICT]
    assert outcome.diagnostics[0].details["reason"] == TargetConflictReason.CONTENT_DIFFERS.value


def test_inventory_reports_the_temporary_a_conflict_retained(scene: Scene) -> None:
    """§6: `inventory` reports incomplete temporaries, and neither blocks a later promotion."""
    root = _torn_before_the_pointer(scene)
    complete_marker_path(root).unlink()
    assert promote(scene.bundle_root, _request()).exit_code == 3

    outcome = inventory(scene.bundle_root)

    assert outcome.value is not None
    assert outcome.value.temporary_entries == tuple(_temporaries(scene.bundle_root))
    assert any(
        finding.path is not None and PROMOTION_TEMP_PREFIX in finding.path
        for finding in outcome.diagnostics
    )


def test_a_retained_temporary_does_not_block_a_later_promotion(scene: Scene) -> None:
    """Digest names do not reserve a revision-number slot, so leftovers block nothing."""
    root = _torn_before_the_pointer(scene)
    complete_marker_path(root).unlink()
    assert promote(scene.bundle_root, _request()).exit_code == 3
    complete_marker_path(root).write_text(
        f"{_manifest_of(root).bundle_digest}\n", encoding="utf-8"
    )

    outcome = promote(scene.bundle_root, _request())

    assert outcome.exit_code == 0, outcome.diagnostics
    assert outcome.value is not None
    assert outcome.value.root == root
    assert len(_temporaries(scene.bundle_root)) == 1  # the earlier conflict's, still retained


# --------------------------------------------------------------------------------------
# What the staged tree must survive before it is installed
# --------------------------------------------------------------------------------------


def test_a_staged_tree_that_does_not_read_back_is_never_installed(
    scene: Scene, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The writer's own claim to have written the right bytes is not evidence.

    The guarantee lands on the digest recomputed from the bytes on disk: the digest is computed
    from the models, so a document that reads back as anything else produces a different one. A
    separate model-by-model comparison was removed because it could never be the check that
    refused — mutating it away left this test green, which is what showed it was covering nothing.
    """
    before = _snapshot(scene.bundle_root)
    real = promotion_module.document_bytes

    def tampered(payload: Any, *, logical_path: PurePosixPath) -> bytes:
        if logical_path == PurePosixPath("manifest.yaml"):
            payload = {**payload, "profile_id": "profile.tampered"}
        return real(payload, logical_path=logical_path)

    monkeypatch.setattr(promotion_module, "document_bytes", tampered)

    outcome = promote(scene.bundle_root, _request())

    assert outcome.exit_code == 3
    assert _codes(outcome) == [IssueCode.INTERNAL_ERROR]
    assert _snapshot(scene.bundle_root) == before
    assert _temporaries(scene.bundle_root) == []


def test_a_staged_tree_that_fails_validation_is_never_installed(
    scene: Scene, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A structural fault in the draft reaches disk only inside the temporary directory."""
    (scene.draft / "facts" / "identity.yaml").unlink()
    _approve(scene.bundle_root, scene.draft)
    before = _snapshot(scene.bundle_root)

    outcome = promote(scene.bundle_root, _request())

    assert outcome.exit_code == 1
    assert IssueCode.MISSING_REQUIRED_FILE in _codes(outcome)
    assert _snapshot(scene.bundle_root) == before
    assert _temporaries(scene.bundle_root) == []


def test_a_marker_written_for_another_digest_stops_the_promotion(
    scene: Scene, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The deferred `COMPLETE` clause, asserted where the marker now exists.

    The step-6 validation tolerates `complete_marker_missing` because the marker is written after
    it. This is what makes that tolerance safe: the marker is read back through the same strict
    reader every later command uses.
    """
    real = promotion_module._write_file

    def wrong_marker(path: Path, data: bytes) -> None:
        if path.name == "COMPLETE":
            data = ("sha256:" + "e" * 64 + "\n").encode()
        real(path, data)

    monkeypatch.setattr(promotion_module, "_write_file", wrong_marker)
    before = _snapshot(scene.bundle_root)

    outcome = promote(scene.bundle_root, _request())

    assert outcome.exit_code == 3
    assert _codes(outcome) == [IssueCode.INTERNAL_ERROR]
    assert _snapshot(scene.bundle_root) == before
    assert not current_path(scene.bundle_root).exists()


def test_a_draft_with_two_records_claiming_one_id_is_refused(scene: Scene) -> None:
    """`diff_records` raises rather than reports, so the derivation cannot reach the staged tree."""
    duplicate = scene.draft / "facts" / "projects"
    existing = sorted(duplicate.glob("*.yaml"))
    assert existing, "the example is expected to own at least one project file"
    shutil.copyfile(existing[0], duplicate / "project.duplicate.yaml")
    _approve(scene.bundle_root, scene.draft)
    before = _snapshot(scene.bundle_root)

    outcome = promote(scene.bundle_root, _request())

    assert outcome.exit_code == 1
    assert IssueCode.DUPLICATE_RECORD_ID in _codes(outcome)
    assert _snapshot(scene.bundle_root) == before


def test_a_missing_blob_refuses_before_anything_is_written(scene: Scene) -> None:
    """Identity cannot be computed without the bytes, and promotion never guesses at one."""
    from boardwatch.profile_bundle.paths import blob_path
    from tests.profile_bundle.conftest import BLOB_SHA256

    blob_path(scene.bundle_root, BLOB_SHA256).unlink()
    before = _snapshot(scene.bundle_root)

    outcome = promote(scene.bundle_root, _request())

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.MISSING_BLOB]
    assert _snapshot(scene.bundle_root) == before


def test_every_module_in_the_package_imports_on_its_own(tmp_path: Path) -> None:
    """Each module, imported FIRST in a fresh interpreter, in a subprocess per module.

    The property this pins is an outside fact rather than anything the package says about itself:
    `python -c "import boardwatch.profile_bundle.<module>"` either works or does not. It did not,
    for `storage` and every module reading it, because `validation/__init__` imported `run` which
    imported `storage` which read `validation.context`. A test session never saw it — pytest imports
    `validation` long before anything else — and the crash matrix, which starts a bare interpreter
    and imports `promotion` first, is what walked into it.

    Subprocesses rather than `importlib.reload`, because "first" is the whole condition and this
    process has already imported all of them.
    """
    package = Path(promotion_module.__file__).parent
    modules = sorted(
        path.stem
        for path in package.glob("*.py")
        if path.stem != "__init__"
    )
    assert {"promotion", "storage", "rebase", "drafts"} <= set(modules)

    failures = {
        name: subprocess.run(
            [sys.executable, "-c", f"import boardwatch.profile_bundle.{name}"],
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        for name in modules
    }
    assert {
        name: result.stderr.strip().splitlines()[-1]
        for name, result in failures.items()
        if result.returncode != 0
    } == {}


def test_the_selected_revision_reads_back_through_the_ordinary_reader(scene: Scene) -> None:
    """Counted through a different path than the one that produced it."""
    outcome = promote(scene.bundle_root, _request())
    assert outcome.value is not None

    selection = read_current_once(scene.bundle_root)
    documents = selected_documents(selection)

    assert documents.manifest == _manifest_of(outcome.value.root)
    assert selection == outcome.value


# --------------------------------------------------------------------------------------
# The store is shared and takes no lock, so it can move under a promotion
# --------------------------------------------------------------------------------------


def test_a_blob_that_disappears_mid_promotion_refuses_instead_of_raising(
    scene: Scene, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`blobs/` is shared across revisions and no writer of it takes the bundle lock.

    So the bytes behind a digest can leave between the derivation and the from-disk re-read. §21 has
    no exit code for an exception escaping a command, and this is the backstop that keeps it a
    typed refusal.
    """
    from boardwatch.profile_bundle.paths import blob_path
    from tests.profile_bundle.conftest import BLOB_SHA256

    real = promotion_module._write_revision

    def vanish(staged: Path, prepared: Any) -> None:
        real(staged, prepared)
        blob_path(scene.bundle_root, BLOB_SHA256).unlink()

    monkeypatch.setattr(promotion_module, "_write_revision", vanish)

    outcome = promote(scene.bundle_root, _request())

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.MISSING_BLOB]
    assert not current_path(scene.bundle_root).exists()
    assert _temporaries(scene.bundle_root) == []


def test_a_blob_rewritten_mid_promotion_stops_the_promotion(
    scene: Scene, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The re-read recomputes the digest from disk, and a blob leaf is part of that digest.

    Comparing the documents alone would not catch this: the models are unchanged and only the bytes
    the manifest hashes have moved, which is exactly the mutation §21 calls a digest failure.
    """
    from boardwatch.profile_bundle.paths import blob_path
    from tests.profile_bundle.conftest import BLOB_SHA256

    real = promotion_module._write_revision

    def rewrite(staged: Path, prepared: Any) -> None:
        real(staged, prepared)
        path = blob_path(scene.bundle_root, BLOB_SHA256)
        path.chmod(0o600)
        path.write_bytes(b"# different bytes under the same digest\n")

    monkeypatch.setattr(promotion_module, "_write_revision", rewrite)

    outcome = promote(scene.bundle_root, _request())

    assert outcome.exit_code == 3
    assert _codes(outcome) == [IssueCode.INTERNAL_ERROR]
    assert not current_path(scene.bundle_root).exists()
    assert _temporaries(scene.bundle_root) == []


def test_a_pointer_written_for_another_revision_is_caught_after_the_replace(
    scene: Scene, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The deferred pointer clause, asserted where the pointer now exists.

    Step 6 tolerates `current_pointer_mismatch` because for a first promotion there is no `CURRENT`
    at all. What makes that safe is this: after the replace, the selection is resolved through the
    ordinary reader and compared with what the promotion wrote.
    """
    first, _, _ = _second_revision(scene, edit=_rename_skill("Revision Two"))
    stale = current_path(scene.bundle_root).read_bytes()
    real = promotion_module._write_file

    def wrong_pointer(path: Path, data: bytes) -> None:
        if path.name.startswith(promotion_module.CURRENT_TEMP_PREFIX):
            data = stale
        real(path, data)

    monkeypatch.setattr(promotion_module, "_write_file", wrong_pointer)

    outcome = promote(scene.bundle_root, _request(SECOND_DRAFT))

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.CURRENT_POINTER_MISMATCH]
    assert read_current_once(scene.bundle_root).root == first


def test_a_current_file_that_cannot_be_resolved_refuses_before_any_write(scene: Scene) -> None:
    """Only "there is no pointer yet" means revision 1; every other failure is a refusal."""
    _promoted(scene)
    current_path(scene.bundle_root).write_bytes(b"not a pointer\n")
    before = _snapshot(scene.bundle_root)

    outcome = promote(scene.bundle_root, _request(SECOND_DRAFT))

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.CURRENT_POINTER_MISMATCH]
    assert _snapshot(scene.bundle_root) == before


def test_a_stamp_file_that_is_not_a_stamp_is_reported_as_such(scene: Scene) -> None:
    """It exists, so it is not missing; it does not parse, so it is not stale either."""
    approval_path(scene.bundle_root, scene.candidate).write_bytes(b"approvals: []\n")
    before = _snapshot(scene.bundle_root)

    outcome = promote(scene.bundle_root, _request())

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.MODEL_VALIDATION_ERROR]
    assert outcome.diagnostics[0].path is not None
    assert outcome.diagnostics[0].path.startswith("approvals/")
    assert _snapshot(scene.bundle_root) == before


def test_a_draft_missing_its_history_documents_cannot_be_promoted(scene: Scene) -> None:
    """Promotion appends to those two ledgers; there is nothing to append to."""
    (scene.draft / "history" / "changes.yaml").unlink()
    _approve(scene.bundle_root, scene.draft)
    before = _snapshot(scene.bundle_root)

    outcome = promote(scene.bundle_root, _request())

    assert outcome.exit_code == 1
    assert _codes(outcome) == [IssueCode.MISSING_REQUIRED_FILE]
    assert outcome.diagnostics[0].path == "history"
    assert _snapshot(scene.bundle_root) == before


def test_a_manifest_field_the_digest_cannot_police_is_still_refused(
    scene: Scene, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half of the from-disk check, and the reason there is no model comparison.

    `canonical._manifest_with` blanks `bundle_digest` and overwrites `evidence_set_digest` before
    hashing the manifest leaf, so forging either of them moves no digest at all. That is precisely
    what `validate_digest`'s own two comparisons exist for, and running the real `validate_bundle`
    over the staged tree is what brings them to bear here — so nothing installs a revision whose
    manifest claims an identity its content does not have.
    """
    real = promotion_module.document_bytes

    def forge(payload: Any, *, logical_path: PurePosixPath) -> bytes:
        if logical_path == PurePosixPath("manifest.yaml"):
            payload = {**payload, "evidence_set_digest": "sha256:" + "f" * 64}
        return real(payload, logical_path=logical_path)

    monkeypatch.setattr(promotion_module, "document_bytes", forge)
    before = _snapshot(scene.bundle_root)

    outcome = promote(scene.bundle_root, _request())

    assert outcome.exit_code == 1
    assert IssueCode.EVIDENCE_SET_DIGEST_MISMATCH in _codes(outcome)
    assert _snapshot(scene.bundle_root) == before
    assert _temporaries(scene.bundle_root) == []
