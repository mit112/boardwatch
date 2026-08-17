"""The two outcome catalogs and the one table that maps every `ProjectionIssue` into exactly one.

Two catalogs, not one, because the units differ: a `ProjectionAvailability` refuses the whole run
before any lead earns a ledger disposition, while a `ProjectionLeadOutcome` skips one lead. Folded
together, "12 leads skipped" and "the run never started" become the same number of nothing.

Every assertion about coverage here is derived from the enum, never from a list spelled in this
file: a hardcoded catalog once passed 98 tests in this repo while covering 5 of 13 classes
(D-142/D-149).
"""

from __future__ import annotations

import subprocess
import sys
import types

import pytest

from boardwatch.extract.taxonomy import TaxonomyError
from boardwatch.profile_bundle.errors import BundleIoError, ProfileBundleError
from boardwatch.projection.errors import (
    ProjectionError,
    ProjectionIssue,
    ProjectionViolation,
)
from boardwatch.projection.run import (
    ISSUE_SCOPE,
    ProjectionAvailability,
    ProjectionLeadOutcome,
    classify_availability,
    classify_lead_outcome,
)
from boardwatch.tailor.equivalences import EquivalenceError
from boardwatch.tailor.persona import PersonaError
from boardwatch.tailor.render.latex import TemplateArtifactError


def _refusal(issue: ProjectionIssue) -> ProjectionError:
    return ProjectionError(ProjectionViolation(issue=issue, message="m", where="w"))


# -- totality -------------------------------------------------------------------------


def test_every_projection_issue_is_mapped() -> None:
    """Derived from the enum, never a hardcoded list: a member added next year must fail here
    rather than land in a default bucket."""
    unmapped = [issue for issue in ProjectionIssue if issue not in ISSUE_SCOPE]
    assert unmapped == []


def test_every_mapped_issue_reaches_its_own_classifier() -> None:
    """Totality of the TABLE is not totality of the FUNCTIONS. Every row is routed through the
    classifier its scope implies, so a row whose value type and whose classifier disagree — the
    one way a total table can still refuse at runtime — fails here rather than at 3am."""
    for issue, scope in ISSUE_SCOPE.items():
        exc = _refusal(issue)
        if isinstance(scope, ProjectionAvailability):
            assert classify_availability(exc) is scope
        else:
            assert classify_lead_outcome(exc) is scope


def test_the_two_catalogs_share_no_member_value() -> None:
    """A shared string would let a summary field carry a value whose scope cannot be recovered."""
    overlap = {member.value for member in ProjectionAvailability} & {
        member.value for member in ProjectionLeadOutcome
    }
    assert overlap == set()


# -- run-invariant causes are run-scoped ------------------------------------------------


def test_run_invariant_causes_are_run_scoped_not_per_lead() -> None:
    """Six causes are identical for every posting in a run: the template, the renderer/toolchain,
    the pinned-set budget, the taxonomy, the equivalence table, and the profile page budget.
    Classifying any of them per-lead would retry a missing renderer once per lead and bill a
    run-wide fault to the owner's content, once per lead."""
    assert isinstance(
        ISSUE_SCOPE[ProjectionIssue.PINNED_SET_EXCEEDS_BUDGET], ProjectionAvailability
    )
    assert isinstance(
        ISSUE_SCOPE[ProjectionIssue.COMPILE_INFRASTRUCTURE_FAILURE], ProjectionAvailability
    )
    # Template failure is NOT a ProjectionIssue — it arrives as TemplateArtifactError from
    # tailor.render.latex, which is why it is classified by exception type, not by issue.
    assert (
        classify_availability(TemplateArtifactError("bad")) is ProjectionAvailability.TEMPLATE_INVALID
    )


def test_the_page_budget_can_never_become_a_per_lead_outcome() -> None:
    """The sixth run-invariant cause has no issue member of its own: `page_budget` is one global
    profile column with a `max(1, …)` floor (`posting.py:93`) and never raises. What must stay true
    is that no per-lead outcome names a budget — the budget is why PINNED_SET_EXCEEDS_BUDGET is
    run-scoped, so a `ProjectionLeadOutcome.*BUDGET*` member would contradict that row."""
    assert [member for member in ProjectionLeadOutcome if "budget" in member.value] == []


# -- specific rows ---------------------------------------------------------------------


def test_the_stamp_arms_use_their_real_issue_members() -> None:
    """Verified member names, not guessed ones."""
    assert (
        ISSUE_SCOPE[ProjectionIssue.MISSING_PROJECTION_APPROVAL]
        is ProjectionAvailability.MISSING_APPROVAL
    )
    assert (
        ISSUE_SCOPE[ProjectionIssue.STALE_PROJECTION_APPROVAL]
        is ProjectionAvailability.STALE_APPROVAL
    )
    assert ISSUE_SCOPE[ProjectionIssue.BUNDLE_UNREADABLE] is ProjectionAvailability.BUNDLE_UNREADABLE


def test_an_absent_declaration_is_not_a_corrupt_one() -> None:
    """`errors.py` keeps DECLARATION_MISSING distinct from DECLARATION_UNREADABLE because "you
    have not opted into projection" and "your declaration is corrupt" are different operator
    problems. Folding them in the availability catalog would undo that at the only place an
    unattended run reports it."""
    assert (
        ISSUE_SCOPE[ProjectionIssue.DECLARATION_MISSING]
        is ProjectionAvailability.DECLARATION_MISSING
    )
    assert (
        ISSUE_SCOPE[ProjectionIssue.DECLARATION_UNREADABLE]
        is ProjectionAvailability.DECLARATION_UNREADABLE
    )


def test_a_broken_shell_source_is_not_a_broken_declaration() -> None:
    """`SHELL_SOURCE_UNREADABLE` describes the file `declaration.shell_source` points at; the
    DECLARATION_* members describe `projection.yaml`. Two files, two remedies — folding them would
    make an availability member send the operator to edit the wrong file, which is the one thing
    this catalog exists to prevent.

    Pinned as a NON-IDENTITY as well as an identity: asserting only the positive row would still
    pass if a later edit added a second issue mapping to DECLARATION_UNREADABLE, but re-pointing
    this row back at DECLARATION_UNREADABLE has to fail here.
    """
    assert (
        ISSUE_SCOPE[ProjectionIssue.SHELL_SOURCE_UNREADABLE]
        is ProjectionAvailability.SHELL_SOURCE_INVALID
    )
    assert (
        ISSUE_SCOPE[ProjectionIssue.SHELL_SOURCE_UNREADABLE]
        is not ProjectionAvailability.DECLARATION_UNREADABLE
    )
    # No `.value !=` assertion here on purpose (task 5b): two equal values inside ONE StrEnum alias
    # to a single member, so the `is not` above already fails first and a `.value !=` line could
    # never fail independently. `test_the_two_catalogs_share_no_member_value` covers the ACROSS-
    # catalog case, which is the one where a shared value is actually representable.


def test_a_missing_extraction_and_an_empty_skill_set_are_different() -> None:
    """`jd_skills_for` returns None for missing extraction and a valid empty set separately, and
    `select` routes an empty set to the curated no-match fallback. Collapsing them would turn a
    working fallback into a dropped lead.

    NO_JD_EXTRACTION is per-lead deliberately: `run_preflight` still loads its own taxonomy on
    every `posting_context` call, so a mid-run `taxonomy.yaml` edit is one way to reach it. That is
    acceptable only because the lead is skipped and counted rather than rendered under mixed rules.
    """
    assert ISSUE_SCOPE[ProjectionIssue.NO_JD_EXTRACTION] is ProjectionLeadOutcome.EXTRACTION_UNAVAILABLE
    assert not hasattr(ProjectionLeadOutcome, "NO_JD_SKILLS")


def test_a_posting_refusal_skips_one_lead() -> None:
    assert ISSUE_SCOPE[ProjectionIssue.POSTING_NOT_OPEN] is ProjectionLeadOutcome.POSTING_UNAVAILABLE
    assert (
        ISSUE_SCOPE[ProjectionIssue.POSTING_NO_CURRENT_VERSION]
        is ProjectionLeadOutcome.POSTING_UNAVAILABLE
    )


def test_an_attributable_compile_failure_skips_one_lead_not_the_run() -> None:
    """A `COMPILE_FAILED` raised inside `select`'s JD-dependent candidate loop is attributable to the
    entry that was just added — the same document without it compiled. Run-scoped, it would abort the
    whole projected run as "toolchain unavailable" and send the operator to reinstall a working
    tectonic. A missing binary is the arm that really is the machine's."""
    assert (
        ISSUE_SCOPE[ProjectionIssue.CANDIDATE_COMPILE_FAILED]
        is ProjectionLeadOutcome.CANDIDATE_UNRENDERABLE
    )
    assert isinstance(
        ISSUE_SCOPE[ProjectionIssue.COMPILE_INFRASTRUCTURE_FAILURE], ProjectionAvailability
    )
    assert classify_lead_outcome(_refusal(ProjectionIssue.CANDIDATE_COMPILE_FAILED)) is (
        ProjectionLeadOutcome.CANDIDATE_UNRENDERABLE
    )
    with pytest.raises(AssertionError):
        classify_availability(_refusal(ProjectionIssue.CANDIDATE_COMPILE_FAILED))


def test_an_unattributable_compile_failure_refuses_the_whole_run() -> None:
    """The mirror row, and the one the reviewer found missing: `COMPILE_FAILED` on the PINNED-ONLY
    prefix is not attributable to any candidate, and the pinned set is fixed by the frozen
    declaration, so it is run-invariant — `ProjectionLeadOutcome`'s own rule forbids naming it there.

    It must NOT resolve to `TOOLCHAIN_UNAVAILABLE` either: a compile that ran and failed is no
    evidence the toolchain is absent, and that member's remedy is "install something", which is the
    misdiagnosis this whole split exists to remove."""
    assert (
        ISSUE_SCOPE[ProjectionIssue.PINNED_SET_COMPILE_FAILED]
        is ProjectionAvailability.PINNED_SET_UNRENDERABLE
    )
    assert (
        ISSUE_SCOPE[ProjectionIssue.PINNED_SET_COMPILE_FAILED]
        is not ProjectionAvailability.TOOLCHAIN_UNAVAILABLE
    )
    assert classify_availability(_refusal(ProjectionIssue.PINNED_SET_COMPILE_FAILED)) is (
        ProjectionAvailability.PINNED_SET_UNRENDERABLE
    )
    with pytest.raises(AssertionError):
        classify_lead_outcome(_refusal(ProjectionIssue.PINNED_SET_COMPILE_FAILED))


def test_no_lead_outcome_claims_a_cause_compile_failed_cannot_establish() -> None:
    """`CompileReason.COMPILE_FAILED` folds a non-zero exit, a missing PDF and an unreadable page
    count into one value, and `reports/resume_gate.py:87-90` reasons that a non-zero exit is
    typically ENVIRONMENTAL. So no member on either side of this split may be named for "content":
    a disk-full run would then bill every lead to the owner's text. The members name the observation
    — what was added, or that nothing was — and the two catalogs stay consistent with resume_gate's."""
    named_for_content = [
        member
        for member in (*ProjectionLeadOutcome, *ProjectionAvailability)
        if "content" in member.value
    ]
    assert named_for_content == []


def test_an_unknown_scorer_is_a_run_configuration_fault() -> None:
    """Not a declaration or bundle fault: nothing about the owner's data is wrong."""
    assert ISSUE_SCOPE[ProjectionIssue.UNKNOWN_SCORER] is ProjectionAvailability.SCORER_INVALID


# -- foreign exception families ---------------------------------------------------------


def test_foreign_exception_families_classify() -> None:
    assert classify_availability(TaxonomyError("bad")) is ProjectionAvailability.TAXONOMY_INVALID
    assert (
        classify_availability(EquivalenceError("bad")) is ProjectionAvailability.EQUIVALENCES_INVALID
    )
    assert classify_availability(PersonaError("bad")) is ProjectionAvailability.PERSONA_INVALID


def test_the_bundle_family_classifies_through_its_subclasses() -> None:
    """`project_pool` calls `read_stamp`, which raises `ProfileBundleError` — not
    `ProjectionError` — for a stamp this build cannot parse, so the family really escapes
    `resolve_projection_run`. Matching must be by `isinstance`, not by exact type: every arm the
    bundle raises is a subclass."""
    assert (
        classify_availability(ProfileBundleError("bad")) is ProjectionAvailability.BUNDLE_UNREADABLE
    )
    assert classify_availability(BundleIoError("bad")) is ProjectionAvailability.BUNDLE_UNREADABLE


# -- closure --------------------------------------------------------------------------


def test_an_unmapped_exception_is_fatal_not_a_bucket() -> None:
    with pytest.raises(AssertionError):
        classify_availability(RuntimeError("something nobody mapped"))


def test_a_foreign_exception_is_never_a_lead_outcome() -> None:
    """`classify_lead_outcome` takes only this package's typed refusals. A foreign exception in the
    per-lead loop is a run-scoped or unclassified fault, never a lead skip."""
    with pytest.raises(AssertionError):
        classify_lead_outcome(TaxonomyError("bad"))


#: Run in a child interpreter under `-O`, which strips `assert`. Every case must refuse, and refuse
#: with the same `AssertionError` the un-optimised interpreter raises: a classifier whose only guard
#: is an `assert` returns the OTHER catalog's member, typed as its own, under optimisation — exactly
#: the silent wrong bucket two catalogs exist to prevent.
#:
#: The unclassified-INPUT cases (`RuntimeError`, and a foreign exception at the lead gate) are
#: included but are not what makes this test able to fail: `classify_availability` already ended in
#: a real `raise`. The scope-CROSSING cases are the ones that returned `NO_REFUSAL` before the fix.
_OPTIMIZE_PROBE = """
from boardwatch.extract.taxonomy import TaxonomyError
from boardwatch.projection.errors import ProjectionError, ProjectionIssue, ProjectionViolation
from boardwatch.projection.run import classify_availability, classify_lead_outcome


def refusal(issue):
    return ProjectionError(ProjectionViolation(issue=issue, message="m", where="w"))


CASES = (
    ("availability/unclassified", classify_availability, RuntimeError("unmapped")),
    (
        "availability/per-lead-scope",
        classify_availability,
        refusal(ProjectionIssue.NO_JD_EXTRACTION),
    ),
    ("lead/foreign", classify_lead_outcome, TaxonomyError("bad")),
    (
        "lead/run-scoped-scope",
        classify_lead_outcome,
        refusal(ProjectionIssue.PINNED_SET_EXCEEDS_BUDGET),
    ),
)

for name, classify, exc in CASES:
    try:
        got = classify(exc)
    except AssertionError:
        print(name + ": REFUSED")
    except Exception as other:
        print(name + ": WRONG_ERROR " + type(other).__name__)
    else:
        print(name + ": NO_REFUSAL " + repr(got))
"""


def test_the_classifiers_still_refuse_out_of_scope_input_under_optimize() -> None:
    """`-O` strips asserts. A classifier whose only guard is `assert` returns the wrong enum type
    silently under optimisation, which is the one outcome the closed catalog exists to prevent."""
    out = subprocess.run(
        [sys.executable, "-O", "-c", _OPTIMIZE_PROBE], capture_output=True, text=True, check=True
    )
    assert "NO_REFUSAL" not in out.stdout, out.stdout
    assert "WRONG_ERROR" not in out.stdout, out.stdout
    assert out.stdout.count("REFUSED") == 4, out.stdout


def test_the_catalog_cannot_be_mutated_at_runtime() -> None:
    """A closed catalog annotated `Mapping` but built as a plain `dict` is only CONVENTIONALLY
    closed — the annotation binds mypy, not a caller holding the object. A read-only proxy is what
    makes "a cause this does not name is a defect here, never a new bucket" true at runtime."""
    assert isinstance(ISSUE_SCOPE, types.MappingProxyType)
    with pytest.raises(TypeError):
        ISSUE_SCOPE[ProjectionIssue.NO_JD_EXTRACTION] = (  # type: ignore[index]
            ProjectionAvailability.TOOLCHAIN_UNAVAILABLE
        )


def test_the_classifiers_refuse_each_others_scopes() -> None:
    """The one mistake a total table cannot prevent: routing a lead failure to a run gate, or a
    run-wide fault to a lead skip. Dispositions are written per lead before the all-failed check,
    so a run-wide fault classified per-lead would grant `seen` to leads that never ran."""
    with pytest.raises(AssertionError):
        classify_availability(_refusal(ProjectionIssue.NO_JD_EXTRACTION))
    with pytest.raises(AssertionError):
        classify_lead_outcome(_refusal(ProjectionIssue.PINNED_SET_EXCEEDS_BUDGET))
