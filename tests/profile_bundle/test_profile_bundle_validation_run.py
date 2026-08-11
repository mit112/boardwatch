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

import shutil
from datetime import date
from pathlib import PurePosixPath
from typing import Any

import pytest

from boardwatch.profile_bundle.errors import IssueCode
from boardwatch.profile_bundle.paths import revision_root
from boardwatch.profile_bundle.reports import report_json
from boardwatch.profile_bundle.validation import run as run_module
from boardwatch.profile_bundle.validation.run import validate_bundle
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from tests.profile_bundle.conftest import (
    PromotedRevisionTree,
    SyntheticBundle,
    quoted_yaml,
)

AS_OF = date(2026, 8, 11)


def edit_revision(tree: PromotedRevisionTree, relative: str, mutate: Any) -> None:
    path = tree.revision_dir / relative
    data = load_yaml_bytes(path.read_bytes(), logical_path=PurePosixPath(relative))
    mutate(data)
    path.write_bytes(quoted_yaml(data))


def edit_draft(bundle: SyntheticBundle, relative: str, mutate: Any) -> None:
    path = bundle.document(relative)
    data = load_yaml_bytes(path.read_bytes(), logical_path=PurePosixPath(relative))
    mutate(data)
    path.write_bytes(quoted_yaml(data))


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


def test_the_report_identifies_the_revision_it_validated(
    promoted_tree: PromotedRevisionTree,
) -> None:
    report = revision_outcome(promoted_tree).value
    assert report.schema_version == 1
    assert report.bundle_digest == promoted_tree.bundle_digest
    assert report.candidate_digest == promoted_tree.candidate_digest
    assert report.as_of is None


def test_a_run_without_completeness_reports_no_as_of(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """Reporting a date the run never used would be a measurement nobody took (D-012): the
    time-dependent checks did not execute, so there is no date to attribute the result to."""
    assert report_json(revision_outcome(promoted_tree).value).count('"as_of":null') == 1


def test_the_same_bytes_produce_identical_report_bytes(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """Two runs that accumulated the same findings in different traversal orders must diff as
    nothing. Without this, comparing yesterday's report to today's shows traversal noise."""
    first = report_json(revision_outcome(promoted_tree, completeness=True, as_of=AS_OF).value)
    second = report_json(revision_outcome(promoted_tree, completeness=True, as_of=AS_OF).value)
    assert first == second


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
    assert f'"as_of":"{AS_OF.isoformat()}"' in report_json(report)


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
    path.write_bytes(quoted_yaml(data))

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
