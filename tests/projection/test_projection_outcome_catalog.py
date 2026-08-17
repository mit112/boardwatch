"""The two outcome catalogs and the one table that maps every `ProjectionIssue` into exactly one.

Two catalogs, not one, because the units differ: a `ProjectionAvailability` refuses the whole run
before any lead earns a ledger disposition, while a `ProjectionLeadOutcome` skips one lead. Folded
together, "12 leads skipped" and "the run never started" become the same number of nothing.

Every assertion about coverage here is derived from the enum, never from a list spelled in this
file: a hardcoded catalog once passed 98 tests in this repo while covering 5 of 13 classes
(D-142/D-149).
"""

from __future__ import annotations

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


def test_the_classifiers_refuse_each_others_scopes() -> None:
    """The one mistake a total table cannot prevent: routing a lead failure to a run gate, or a
    run-wide fault to a lead skip. Dispositions are written per lead before the all-failed check,
    so a run-wide fault classified per-lead would grant `seen` to leads that never ran."""
    with pytest.raises(AssertionError):
        classify_availability(_refusal(ProjectionIssue.NO_JD_EXTRACTION))
    with pytest.raises(AssertionError):
        classify_lead_outcome(_refusal(ProjectionIssue.PINNED_SET_EXCEEDS_BUDGET))
