"""`AuditView.presentation`: the derived, presentation-only distinction between an `eligible`
that fired and cleared requirement rows and an `eligible` that fired none at all ("no flags"
!= cleared — CLAUDE.md, P2 item 6). Pure dataclass construction, no DB and no engine call:
these tests must not be able to observe a change to the stored `verdict`, only to the new
`presentation` property derived from it."""

from datetime import datetime

from boardwatch.eligibility.audit import AuditRequirement, AuditView, VerdictPresentation

_NOW = datetime(2026, 1, 1)


def _requirement(disposition: str = "met") -> AuditRequirement:
    return AuditRequirement(
        rule_id="degree:bachelor_required",
        label="a bachelor's degree is required",
        requiredness="required",
        disposition=disposition,
        rationale=None,
        quote="Bachelor's degree is required",
        support=(),
    )


def _view(verdict: str, requirements: tuple[AuditRequirement, ...]) -> AuditView:
    return AuditView(
        verdict=verdict,
        captured_at=_NOW,
        is_historical=False,
        catalog_version_matches=True,
        requirements=requirements,
    )


def test_eligible_with_zero_requirement_rows_is_no_rules_applied() -> None:
    view = _view("eligible", ())
    assert view.presentation is VerdictPresentation.ELIGIBLE_NO_RULES_APPLIED
    assert view.verdict == "eligible"  # the stored verdict itself is untouched


def test_eligible_with_one_or_more_requirement_rows_is_cleared() -> None:
    view = _view("eligible", (_requirement(),))
    assert view.presentation is VerdictPresentation.ELIGIBLE_CLEARED
    assert view.verdict == "eligible"


def test_eligible_with_several_requirement_rows_is_still_cleared() -> None:
    view = _view("eligible", (_requirement(), _requirement(disposition="unknown")))
    assert view.presentation is VerdictPresentation.ELIGIBLE_CLEARED


def test_ineligible_presentation_is_unchanged_regardless_of_requirement_count() -> None:
    assert _view("ineligible", ()).presentation is VerdictPresentation.INELIGIBLE
    assert _view("ineligible", (_requirement("unmet"),)).presentation is (
        VerdictPresentation.INELIGIBLE
    )


def test_uncertain_presentation_is_unchanged_regardless_of_requirement_count() -> None:
    assert _view("uncertain", ()).presentation is VerdictPresentation.UNCERTAIN
    assert _view("uncertain", (_requirement("unknown"),)).presentation is (
        VerdictPresentation.UNCERTAIN
    )
