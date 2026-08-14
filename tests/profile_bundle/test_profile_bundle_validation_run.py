"""T13 layered orchestration: `validate_bundle` (design §19, §20, §21).

This is the one entry point every command and test reaches validation through, so three properties
are pinned here rather than in the layers:

- **Every layer runs, in dependency order, and nothing short-circuits.** An operator fixing a
  hand-edited bundle wants the whole list, not the first finding.
- **The blob reader is always supplied.** `validate_digest` returns nothing at all without one, so a
  caller that forgot it would get a silently green digest layer. D-115 says to test a guarantee
  where it lands: it lands here.
- **Completeness is opt-in and dated.** §20 keeps every other layer a pure function of bundle
  content, so the date arrives as an argument and is reported back in machine output.
"""

from __future__ import annotations

import hashlib
import shutil
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

from boardwatch.profile_bundle.errors import IssueCode
from boardwatch.profile_bundle.paths import BLOBS_DIR, revision_root
from boardwatch.profile_bundle.validation import run as run_module
from boardwatch.profile_bundle.validation.run import validate_bundle
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from tests.profile_bundle.conftest import (
    PromotedRevisionTree,
    SyntheticBundle,
    quoted_yaml,
    reseal_without_reapproval,
)

AS_OF = date(2026, 8, 11)


def edit_revision(tree: PromotedRevisionTree, relative: str, mutate: Any) -> None:
    path = tree.revision_dir / relative
    data = load_yaml_bytes(path.read_bytes(), logical_path=PurePosixPath(relative))
    mutate(data)
    path.write_bytes(quoted_yaml(data, logical_path=PurePosixPath(relative)))


def edit_draft(bundle: SyntheticBundle, relative: str, mutate: Any) -> None:
    path = bundle.document(relative)
    data = load_yaml_bytes(path.read_bytes(), logical_path=PurePosixPath(relative))
    mutate(data)
    path.write_bytes(quoted_yaml(data, logical_path=PurePosixPath(relative)))


def revision_outcome(tree: PromotedRevisionTree, **kwargs: Any) -> Any:
    return validate_bundle(
        tree.revision_dir, bundle_root=tree.bundle_root, mode="revision", **kwargs
    )


def draft_outcome(bundle: SyntheticBundle, **kwargs: Any) -> Any:
    return validate_bundle(bundle.draft, bundle_root=bundle.root, mode="draft", **kwargs)


# --------------------------------------------------------------------------------------
# The clean case, and what the report says about it
# --------------------------------------------------------------------------------------


def test_a_promoted_revision_validates_clean_without_completeness(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """§20.5: a bundle can be entirely valid while still being incomplete for downstream use, so a
    run that did not ask for completeness must not exit on the example's open conflict."""
    outcome = revision_outcome(promoted_tree)
    assert (outcome.category, outcome.exit_code) == ("clean", 0)
    assert outcome.diagnostics == ()


def test_a_bundle_whose_blob_store_leaves_the_root_is_refused(
    promoted_tree: PromotedRevisionTree, tmp_path: Path
) -> None:
    """§6's self-containment is what makes the digest layer's answer mean anything.

    The blob bytes are hashed into `evidence_set_digest` and therefore into `bundle_digest`, so a
    `blobs/` pointing outside the root would let content nobody can see from the bundle decide the
    bundle's identity — and `validate` is the command whose job is to say that identity is right.
    `require_confined_root` is the same check `inventory` and the draft commands enter through;
    this test names where it lands for `validate`.
    """
    outside = tmp_path / "outside-blobs"
    store = promoted_tree.bundle_root / BLOBS_DIR
    store.rename(outside)
    store.symlink_to(outside, target_is_directory=True)

    outcome = revision_outcome(promoted_tree)
    assert [d.code for d in outcome.diagnostics] == [str(IssueCode.SYMLINK_REFUSED)]
    assert outcome.exit_code == 1
    assert outcome.value.bundle_digest is None


def content_addressed_file(bundle_root: Path) -> Path:
    """The one file under `bundle_root` whose name is the sha256 of its own bytes.

    Found by hashing, never by joining a path constant, because the two tests below exist to pin a
    fact the confinement check must not be allowed to agree with itself about. The check was written
    over the root's member names, and its test read the same names, so both agreed `blobs/` was the
    store while the bytes that decide `bundle_digest` sat one component deeper in `blobs/sha256/`.
    Content addressing is the outside fact: whatever the layout is called, the file whose *name is
    its digest* is a file whose bytes are hashed into this bundle's identity.
    """
    found = [
        path
        for path in sorted(bundle_root.rglob("*"))
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == path.name
    ]
    assert len(found) == 1, f"expected one content-addressed file, found {found}"
    return found[0]


def test_the_directory_holding_this_bundles_blobs_may_not_leave_the_root(
    promoted_tree: PromotedRevisionTree, tmp_path: Path
) -> None:
    """The store is one component below `blobs/`, and the check guarded only the component above it.

    So symlinking the store itself passed confinement, its bytes were hashed into
    `evidence_set_digest` and therefore into `bundle_digest`, and `validate`, `inventory` and
    `checkout` all reported a clean bundle whose identity was computed from content nobody can see
    from the root. The store is located by content here, so this holds wherever it is spelled.
    """
    store = content_addressed_file(promoted_tree.bundle_root).parent
    outside = tmp_path / "outside-store"
    store.rename(outside)
    store.symlink_to(outside, target_is_directory=True)

    outcome = revision_outcome(promoted_tree)
    assert [d.code for d in outcome.diagnostics] == [str(IssueCode.SYMLINK_REFUSED)]
    assert outcome.exit_code == 1
    assert outcome.value.bundle_digest is None


def test_an_empty_blob_store_pointing_outside_the_root_is_refused_with_nothing_in_it(
    promoted_tree: PromotedRevisionTree, tmp_path: Path
) -> None:
    """The store's own path is confined separately from its entries, and needs its own test.

    An empty store escapes with nothing in it to notice: a check that only resolved the entries it
    found would find none and pass, while every capture written afterwards landed outside the root.
    """
    store = content_addressed_file(promoted_tree.bundle_root).parent
    shutil.rmtree(store)
    outside = tmp_path / "outside-empty-store"
    outside.mkdir()
    store.symlink_to(outside, target_is_directory=True)

    outcome = revision_outcome(promoted_tree)
    assert [d.code for d in outcome.diagnostics] == [str(IssueCode.SYMLINK_REFUSED)]
    assert outcome.exit_code == 1
    assert outcome.value.bundle_digest is None


def test_one_blob_symlinked_out_of_the_root_cannot_decide_the_bundle_digest(
    promoted_tree: PromotedRevisionTree, tmp_path: Path
) -> None:
    """Confinement is per path, not per directory: every directory here stays inside the root.

    A single symlinked file is enough, because its bytes are hashed into `evidence_set_digest` like
    any other blob's. A check that confined the store's own path and stopped there would leave the
    smallest version of the same escape armed.
    """
    blob = content_addressed_file(promoted_tree.bundle_root)
    outside = tmp_path / blob.name
    blob.rename(outside)
    blob.symlink_to(outside)

    outcome = revision_outcome(promoted_tree)
    assert [d.code for d in outcome.diagnostics] == [str(IssueCode.SYMLINK_REFUSED)]
    assert outcome.exit_code == 1
    assert outcome.value.bundle_digest is None


def test_the_report_identifies_the_revision_it_validated(
    promoted_tree: PromotedRevisionTree,
) -> None:
    report = revision_outcome(promoted_tree).value
    assert report.schema_version == 2
    assert report.bundle_digest == promoted_tree.bundle_digest
    assert report.candidate_digest == promoted_tree.candidate_digest
    assert report.as_of is None


def test_a_run_without_completeness_reports_no_as_of(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """Reporting a date the run never used would be a measurement nobody took (D-012): the
    time-dependent checks did not execute, so there is no date to attribute the result to."""
    assert revision_outcome(promoted_tree).value.as_of is None


def test_the_same_bytes_produce_an_identical_report(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """Two runs that accumulated the same findings in different traversal orders must diff as
    nothing. Without this, comparing yesterday's report to today's shows traversal noise.

    Compared as `ordered` rather than as serialized bytes: this layer owns which findings there are
    and what order they come in, and the byte-level guarantee is the command's — pinned by
    `test_profile_bundle_reports.py::test_json_is_byte_identical_across_runs`.
    """
    first = revision_outcome(promoted_tree, completeness=True, as_of=AS_OF).value
    second = revision_outcome(promoted_tree, completeness=True, as_of=AS_OF).value
    assert first.ordered == second.ordered
    assert (first.counts, first.candidate_digest) == (second.counts, second.candidate_digest)


# --------------------------------------------------------------------------------------
# Completeness is opt-in, and needs its date
# --------------------------------------------------------------------------------------


def test_requested_completeness_exits_one_on_the_examples_blockers(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """§20.5 and §21: the revision stays valid, but blockers are findings, so the exit code moves.

    A caller that could not tell "valid and incomplete" from "valid and complete" would have no way
    to gate a downstream step on the bundle being usable.
    """
    outcome = revision_outcome(promoted_tree, completeness=True, as_of=AS_OF)
    assert (outcome.category, outcome.exit_code) == ("findings", 1)
    assert {d.tier for d in outcome.diagnostics} == {"blocker", "information"}


def test_requested_completeness_reports_the_date_it_used(
    promoted_tree: PromotedRevisionTree,
) -> None:
    report = revision_outcome(promoted_tree, completeness=True, as_of=AS_OF).value
    assert report.as_of == AS_OF


def test_completeness_without_a_date_is_refused_rather_than_defaulted(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """The package reads no clock, so there is nothing here to default to.

    Refusing is what keeps `--as-of` the caller's decision; silently substituting a date would make
    the report claim a measurement against a moment the operator never chose.
    """
    with pytest.raises(ValueError, match="as_of"):
        revision_outcome(promoted_tree, completeness=True, as_of=None)


def test_a_date_without_completeness_runs_no_time_dependent_check(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """`as_of` alone does not turn completeness on. Otherwise `--as-of` would silently widen what a
    plain `validate` reports."""
    outcome = revision_outcome(promoted_tree, as_of=AS_OF)
    assert outcome.diagnostics == ()
    assert outcome.value.as_of is None


def test_every_completeness_layer_contributes(promoted_tree: PromotedRevisionTree) -> None:
    """The four completeness producers are separate modules, and wiring one of them up is a line
    that can be forgotten. Each is represented by a code only it emits."""
    outcome = revision_outcome(promoted_tree, completeness=True, as_of=date(2027, 1, 1))
    codes = {d.code for d in outcome.diagnostics}
    assert IssueCode.UNRESOLVED_CONFLICT in codes  # completeness
    assert IssueCode.COMPLETENESS_COUNTS in codes  # completeness counts
    assert IssueCode.EXPIRED_REVIEW in codes  # the dated half of completeness


def test_completeness_is_skipped_when_a_structural_prerequisite_is_absent(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """`policy/predicates.yaml` is what every fact's predicate is checked against. Running
    completeness without it would report a hundred consequences of one missing file.

    The run is not silent about it: the missing file is an error, so the exit code still moves and
    nothing reads as clean.
    """
    (promoted_tree.revision_dir / "policy" / "predicates.yaml").unlink()
    outcome = revision_outcome(promoted_tree, completeness=True, as_of=AS_OF)
    codes = {d.code for d in outcome.diagnostics}
    assert IssueCode.MISSING_REQUIRED_FILE in codes
    assert IssueCode.COMPLETENESS_COUNTS not in codes
    assert outcome.exit_code == 1


def test_a_skipped_completeness_run_reports_no_as_of(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """`as_of` present means the dated checks ran. Nothing else in the report says so.

    A skipped run still carried the requested date and `blocker: 0`, so machine output could not
    tell "completeness ran and found nothing" from "completeness never started" — and the second
    reads as the first, which is the more reassuring of the two.
    """
    (promoted_tree.revision_dir / "policy" / "predicates.yaml").unlink()
    report = revision_outcome(promoted_tree, completeness=True, as_of=AS_OF).value
    assert report.as_of is None


def test_a_deep_history_audit_without_completeness_is_refused(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """`deep_history` only reaches `ancestry_completeness`, which only runs under completeness.

    Accepting it and doing nothing is the worst of the three options: the caller asked for the one
    audit that makes an edited ancestor visible at all and would be told, in a clean report, that
    there was nothing to see. It is a programming error at the call boundary, like `as_of`.
    """
    with pytest.raises(ValueError, match="deep_history"):
        revision_outcome(promoted_tree, deep_history=True)


# --------------------------------------------------------------------------------------
# Every layer runs
# --------------------------------------------------------------------------------------


def test_a_document_edited_after_promotion_reaches_the_digest_layer(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """The behavioural proof that a blob reader was supplied.

    `validate_digest` returns `()` outright when `ctx.blobs is None`, so this finding is impossible
    unless the orchestrator built a reader. Asserting it through the outcome rather than by
    inspecting the call is the point: it counts the deliverable through a different path.
    """

    def retitle(data: Any) -> None:
        data["skills"][0]["canonical_name"] = "Edited After Promotion"

    edit_revision(promoted_tree, "skills/inventory.yaml", retitle)
    codes = {d.code for d in revision_outcome(promoted_tree).diagnostics}
    assert IssueCode.BUNDLE_DIGEST_MISMATCH in codes


def test_validate_bundle_always_supplies_a_blob_reader(
    promoted_tree: PromotedRevisionTree, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same guarantee stated directly, because the behavioural test above would also pass if a
    future refactor computed the digest somewhere else."""
    seen: list[object] = []
    original = run_module.build_context

    def spy(*args: Any, **kwargs: Any) -> Any:
        context = original(*args, **kwargs)
        seen.append(context.blobs)
        return context

    monkeypatch.setattr(run_module, "build_context", spy)
    revision_outcome(promoted_tree)
    assert seen and all(reader is not None for reader in seen)


def test_a_broken_reference_reaches_the_referential_layer(
    synthetic_bundle: SyntheticBundle,
) -> None:
    def break_reference(data: Any) -> None:
        data["skills"][0]["supporting_fact_ids"] = ["fact.does-not-exist"]

    edit_draft(synthetic_bundle, "skills/inventory.yaml", break_reference)
    codes = {d.code for d in draft_outcome(synthetic_bundle).diagnostics}
    assert IssueCode.BROKEN_REFERENCE in codes


def test_an_unknown_predicate_reaches_the_semantic_layer(
    synthetic_bundle: SyntheticBundle,
) -> None:
    def retype(data: Any) -> None:
        data["facts"][0]["predicate"] = "person.invented_predicate"

    edit_draft(synthetic_bundle, "facts/identity.yaml", retype)
    codes = {d.code for d in draft_outcome(synthetic_bundle).diagnostics}
    assert IssueCode.UNKNOWN_PREDICATE in codes


def test_a_missing_blob_reaches_the_evidence_layer(
    synthetic_bundle: SyntheticBundle,
) -> None:
    synthetic_bundle.blob.chmod(0o600)
    synthetic_bundle.blob.unlink()
    codes = {d.code for d in draft_outcome(synthetic_bundle).diagnostics}
    assert IssueCode.MISSING_BLOB in codes


def test_the_layers_accumulate_rather_than_stopping_at_the_first(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Two independent breakages in two layers, reported together. A run that stopped at the first
    would make fixing a hand-edited bundle a sequence of one-finding rounds."""

    def break_reference(data: Any) -> None:
        data["skills"][0]["supporting_fact_ids"] = ["fact.does-not-exist"]

    def retype(data: Any) -> None:
        data["facts"][0]["predicate"] = "person.invented_predicate"

    edit_draft(synthetic_bundle, "skills/inventory.yaml", break_reference)
    edit_draft(synthetic_bundle, "facts/identity.yaml", retype)
    codes = {d.code for d in draft_outcome(synthetic_bundle).diagnostics}
    assert {IssueCode.BROKEN_REFERENCE, IssueCode.UNKNOWN_PREDICATE} <= codes


# --------------------------------------------------------------------------------------
# Drafts
# --------------------------------------------------------------------------------------


def test_a_draft_validates_and_reports_the_candidate_digest_the_owner_must_approve(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§19 step 7: an agent presents "the candidate digest" and stops.

    A draft has no `bundle_digest` — its manifest carries the `""` sentinel — so reporting one would
    be inventing a value. The candidate digest is the thing that actually exists, and it is
    recomputed rather than read, because a draft's manifest carries a sentinel there too.
    """
    from boardwatch.profile_bundle.canonical import candidate_content_digest
    from tests.profile_bundle.conftest import blob_reader, parse_documents

    expected = candidate_content_digest(
        parse_documents(synthetic_bundle.draft), blob_reader(), None
    )
    report = draft_outcome(synthetic_bundle).value
    assert report.bundle_digest is None
    assert report.candidate_digest == expected


def test_a_draft_carrying_a_revision_manifest_is_reported(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """A promoted tree copied into `drafts/` keeps its `state: revision` manifest, and nothing in
    the parse path compares the manifest's state to the mode it was read under."""
    draft = promoted_tree.bundle_root / "drafts" / "copied"
    draft.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(promoted_tree.revision_dir, draft)
    (draft / "COMPLETE").unlink()
    outcome = validate_bundle(draft, bundle_root=promoted_tree.bundle_root, mode="draft")
    assert IssueCode.DRAFT_MANIFEST_INVALID in {d.code for d in outcome.diagnostics}


# --------------------------------------------------------------------------------------
# Runs that could not complete (§21's exit 3)
# --------------------------------------------------------------------------------------


def test_an_unsupported_schema_version_is_reported_under_its_own_code(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """§21: "Bundle schema newer than the validator | Exit 3 with `unsupported_schema_version`".

    `parse_error_diagnostics` had no arm for the typed refusal, so it fell through to
    `internal_error`. The exit code was right by coincidence — both codes are `could_not_complete` —
    which is exactly why no test caught it: an operator reading `internal_error` would file a bug
    instead of upgrading Boardwatch.
    """

    def bump(data: Any) -> None:
        data["schema_version"] = 999

    edit_revision(promoted_tree, "manifest.yaml", bump)
    outcome = revision_outcome(promoted_tree)
    assert (outcome.category, outcome.exit_code) == ("could_not_complete", 3)
    assert [d.code for d in outcome.diagnostics] == [IssueCode.UNSUPPORTED_SCHEMA_VERSION]


def test_a_bundle_that_will_not_parse_reports_every_broken_file_and_identifies_none(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """A parse failure has no schema version and no digest to report, and inventing either would be
    a fact nobody measured."""
    synthetic_bundle.document("skills/inventory.yaml").write_text("skills: [", encoding="utf-8")
    outcome = draft_outcome(synthetic_bundle)
    report = outcome.value
    assert report.schema_version is None
    assert report.bundle_digest is None
    assert report.candidate_digest is None
    assert outcome.exit_code == 1


def test_a_directory_with_no_manifest_is_a_finding_about_that_directory(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """A path that holds no revision reports the missing manifest, not exit 3.

    `discover_source_files` treats an empty or absent directory as a tree with no declared documents
    rather than as an I/O failure, so the manifest's absence surfaces as `missing_required_file`.
    That is the actionable answer for the operator who named the wrong directory; exit 3 is reserved
    for a refusal the validator itself raises, such as an unsupported schema version. Resolving
    `CURRENT` to a revision that is not on disk is a *selection* failure and belongs to T14, which
    owns the pointer and has a `no_current_revision` refusal for it.
    """
    outcome = validate_bundle(
        revision_root(promoted_tree.bundle_root, "sha256:" + "0" * 64),
        bundle_root=promoted_tree.bundle_root,
        mode="revision",
    )
    assert [d.code for d in outcome.diagnostics] == [IssueCode.MISSING_REQUIRED_FILE]
    assert outcome.exit_code == 1


# --------------------------------------------------------------------------------------
# A child revision, validated on its own
# --------------------------------------------------------------------------------------


def test_a_child_revision_validates_clean_without_its_parent(
    chained_tree: PromotedRevisionTree,
) -> None:
    """§20.6: validating an already selected revision does not repeat promotion's parent checks.

    Owner gates are DERIVED by diffing a revision against its parent, so with no parent snapshot the
    derivation treats every record as new and demands the one appended stamp approve the entire
    bundle. Left unguarded that reported ~35 spurious `missing_owner_approval` errors on every
    revision after the first — the same shape as the candidate-digest trap in `validation/digest.py`,
    and the same answer: without the parent, make no claim.
    """
    outcome = revision_outcome(chained_tree)
    assert (outcome.category, outcome.exit_code) == ("clean", 0)


def test_a_child_revisions_owner_gates_are_checked_when_its_parent_is_supplied(
    chained_tree: PromotedRevisionTree,
) -> None:
    """The other half, without which the guard above would just be the check switched off.

    With the parent in hand the derivation is exact, so removing the one approval revision 2 needed
    is caught. Promotion always holds the parent, which is where this check earns its keep.
    """
    from boardwatch.profile_bundle.index import build_index
    from boardwatch.profile_bundle.models.manifests import RevisionManifest
    from boardwatch.profile_bundle.validation import ParentSnapshot, load_documents

    parent_digest = chained_tree.documents.manifest.parent_bundle_digest
    assert parent_digest is not None
    parent_root = revision_root(chained_tree.bundle_root, parent_digest)
    parent_documents = load_documents(parent_root, mode="revision")
    parent_manifest = parent_documents.manifest
    assert isinstance(parent_manifest, RevisionManifest)
    snapshot = ParentSnapshot(
        root=parent_root,
        documents=parent_documents,
        envelope=parent_manifest.envelope,
        index=build_index(parent_documents),
    )

    assert revision_outcome(chained_tree, parent=snapshot).diagnostics == ()

    # A contact whose value moved between the two revisions is an owner-gated transition §13
    # requires a `confirm_contact` sub-approval for, and revision 2's stamp approves only the skill
    # rename it was actually built for.
    def move_contact(data: Any) -> None:
        data["contacts"][0]["value"] = "moved@example.com"

    edit_revision(chained_tree, "facts/identity.yaml", move_contact)
    with_parent = {d.code for d in revision_outcome(chained_tree, parent=snapshot).diagnostics}
    without_parent = {d.code for d in revision_outcome(chained_tree).diagnostics}
    assert IssueCode.MISSING_OWNER_APPROVAL in with_parent
    assert IssueCode.MISSING_OWNER_APPROVAL not in without_parent


# --------------------------------------------------------------------------------------
# Ancestry, wired through
# --------------------------------------------------------------------------------------


def test_a_missing_ancestor_is_a_completeness_blocker_not_an_error(
    chained_tree: PromotedRevisionTree,
) -> None:
    parent_digest = chained_tree.documents.manifest.parent_bundle_digest
    assert parent_digest is not None
    shutil.rmtree(revision_root(chained_tree.bundle_root, parent_digest))

    plain = revision_outcome(chained_tree)
    assert (plain.category, plain.exit_code) == ("clean", 0)

    complete = revision_outcome(chained_tree, completeness=True, as_of=AS_OF)
    assert IssueCode.UNVERIFIABLE_ANCESTOR in {d.code for d in complete.diagnostics}


def test_the_deep_audit_is_opt_in(chained_tree: PromotedRevisionTree) -> None:
    """§20.6: validating an already-selected revision does not deep-parse ancestors. So an edited
    ancestor is invisible by default and visible under `deep_history`, and the difference between
    the two runs is the whole contract."""
    parent_digest = chained_tree.documents.manifest.parent_bundle_digest
    assert parent_digest is not None
    parent_root = revision_root(chained_tree.bundle_root, parent_digest)
    path = parent_root / "skills" / "inventory.yaml"
    data = load_yaml_bytes(path.read_bytes(), logical_path=PurePosixPath("skills/inventory.yaml"))
    data["skills"][0]["canonical_name"] = "Edited Ancestor"
    path.write_bytes(quoted_yaml(data, logical_path=PurePosixPath("skills/inventory.yaml")))

    shallow = revision_outcome(chained_tree, completeness=True, as_of=AS_OF)
    deep = revision_outcome(
        chained_tree, completeness=True, as_of=AS_OF, deep_history=True
    )
    assert IssueCode.UNVERIFIABLE_ANCESTOR not in {d.code for d in shallow.diagnostics}
    assert IssueCode.UNVERIFIABLE_ANCESTOR in {d.code for d in deep.diagnostics}


# --------------------------------------------------------------------------------------
# The installed secret-scan ruleset
# --------------------------------------------------------------------------------------


def test_the_installed_ruleset_version_is_read_at_call_time(
    promoted_tree: PromotedRevisionTree, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A by-name import would snapshot the version set at import time.

    `evidence_completeness` exists so a caller can ask "what would today's catalog say?" about an
    old revision; if this default were bound when the module loaded, adding a ruleset version would
    silently leave every existing process asking the old question.
    """
    from boardwatch.profile_bundle import secret_scan

    monkeypatch.setattr(secret_scan, "CURRENT_RULESET_VERSION", 1)
    assert run_module.installed_secret_ruleset_version() == 1
    monkeypatch.setattr(secret_scan, "CURRENT_RULESET_VERSION", 7)
    assert run_module.installed_secret_ruleset_version() == 7


def test_a_checked_out_draft_makes_no_candidate_claim_without_its_parent(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """A draft created by `checkout` names a parent, and the candidate view folds that parent's
    revision number and digest in. Recomputing without it produces a DIFFERENT digest, not an
    approximate one, and printing it would invite an owner to approve a value nothing will match.
    """

    def adopt_a_parent(data: Any) -> None:
        data["draft_of_revision"] = 1
        data["parent_bundle_digest"] = "sha256:" + "a" * 64

    edit_draft(synthetic_bundle, "manifest.yaml", adopt_a_parent)
    assert draft_outcome(synthetic_bundle).value.candidate_digest is None


def test_a_draft_whose_blob_is_gone_reports_no_candidate_digest(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The digest is over the ACTUAL capture bytes, so without them there is nothing to report.

    `None` rather than a digest computed from what happens to be readable: the missing blob is the
    evidence layer's finding, and a candidate digest that silently skipped a capture is exactly the
    value an owner must never be asked to approve.
    """
    synthetic_bundle.blob.chmod(0o600)
    synthetic_bundle.blob.unlink()
    outcome = draft_outcome(synthetic_bundle)
    assert outcome.value.candidate_digest is None
    assert IssueCode.MISSING_BLOB in {d.code for d in outcome.diagnostics}


# --------------------------------------------------------------------------------------
# What the reported candidate digest means
# --------------------------------------------------------------------------------------


def test_the_reported_candidate_digest_is_the_one_this_tree_recomputes(
    chained_tree: PromotedRevisionTree,
) -> None:
    """Never the manifest's declared value, which is the number under suspicion.

    Reporting `approved_candidate_digest` verbatim made a never-verified declaration
    indistinguishable in JSON from a verified one: a re-sealed revision that no owner ever approved
    printed the forged tree's *claimed* digest under the same key, with the same shape, as a clean
    one. The field is the digest the bytes on disk reduce to, so a consumer diffing it against the
    approval stamp sees the forgery.
    """
    forged = reseal_without_reapproval(
        chained_tree,
        mutate=lambda data: data["skills"][0].update({"canonical_name": "Never Approved"}),
    )
    declared = forged.documents.manifest.approved_candidate_digest
    report = revision_outcome(forged).value
    assert report.candidate_digest is not None
    assert report.candidate_digest != declared
    assert IssueCode.CANDIDATE_DIGEST_MISMATCH in {d.code for d in revision_outcome(forged).diagnostics}


def test_a_revision_whose_parent_is_off_disk_reports_no_candidate_digest(
    chained_tree: PromotedRevisionTree,
) -> None:
    """`None` is "this run made no claim", and it is the only honest answer here.

    The candidate view folds in the parent's revision number and digest, so with the parent gone
    there is nothing to recompute against. Printing the declared value instead would present an
    unverified number exactly as a verified one — which is what §21 keeping a revision valid through
    unavailable history must not be allowed to cost.
    """
    parent_digest = chained_tree.documents.manifest.parent_bundle_digest
    assert parent_digest is not None
    shutil.rmtree(revision_root(chained_tree.bundle_root, parent_digest))
    assert revision_outcome(chained_tree).value.candidate_digest is None


def test_a_revision_whose_parent_is_gone_states_that_it_made_no_claim(
    chained_tree: PromotedRevisionTree,
) -> None:
    """A forgery plus a deleted parent used to report zero diagnostics and exit 0.

    The silence was justified by deferring to `ancestry_completeness`'s `unverifiable_ancestor`
    blocker — which only runs when completeness is requested, so on the DEFAULT path the deferral
    target never ran at all. `candidate_digest: null` was the whole signal, and nothing said why.

    §21 is unchanged deliberately: a missing ancestor stays a completeness blocker and the selected
    revision stays structurally valid, so this is stated at the information tier, which never moves
    an exit code. What it buys is that "unmeasured" stops reading as "verified clean".
    """
    forged = reseal_without_reapproval(
        chained_tree,
        mutate=lambda data: data["skills"][0].update({"canonical_name": "Never Approved"}),
    )
    parent_digest = forged.documents.manifest.parent_bundle_digest
    assert parent_digest is not None
    shutil.rmtree(revision_root(forged.bundle_root, parent_digest))

    outcome = revision_outcome(forged)
    found = [d for d in outcome.diagnostics if d.code == IssueCode.CANDIDATE_DIGEST_UNVERIFIED]
    assert len(found) == 1
    assert (found[0].tier, found[0].details["reason"]) == ("information", "absent")
    assert (outcome.category, outcome.exit_code) == ("clean", 0)
    assert outcome.value.candidate_digest is None


def test_a_revision_that_recomputes_its_candidate_digest_states_nothing(
    chained_tree: PromotedRevisionTree,
) -> None:
    """The negative control for a finding about silence: a claim was made, so nothing is said.

    Without this the new row could be emitted on every revision and still look like it worked.
    """
    outcome = revision_outcome(chained_tree)
    assert IssueCode.CANDIDATE_DIGEST_UNVERIFIED not in {d.code for d in outcome.diagnostics}
    assert outcome.value.candidate_digest == chained_tree.candidate_digest
