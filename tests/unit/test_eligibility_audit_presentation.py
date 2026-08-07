"""`AuditView.presentation`: the derived, presentation-only distinction between an `eligible`
that fired and cleared requirement rows, an `eligible` that fired none at all, and an `eligible`
that fired rows NOT all disposed `met` ("no flags" != cleared — CLAUDE.md, P2 item 6; and,
fix round 1, "cleared" must not overclaim a row that isn't). Pure dataclass construction, no DB
and no engine call: these tests must not be able to observe a change to the stored `verdict`,
only to the new `presentation`/`met_count` properties derived from it."""

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


def test_eligible_with_one_met_requirement_row_is_cleared() -> None:
    view = _view("eligible", (_requirement("met"),))
    assert view.presentation is VerdictPresentation.ELIGIBLE_CLEARED
    assert view.met_count == 1
    assert view.verdict == "eligible"


def test_eligible_with_several_all_met_requirement_rows_is_cleared() -> None:
    view = _view("eligible", (_requirement("met"), _requirement("met")))
    assert view.presentation is VerdictPresentation.ELIGIBLE_CLEARED
    assert view.met_count == 2


def test_eligible_with_a_non_met_row_is_mixed_not_cleared() -> None:
    # D-035: five families still ship `preference`, so an `eligible` verdict can carry a
    # non-blocking `unmet`/`unknown` row alongside a cleared `met` row. Counting that row as
    # "cleared" would be the exact overclaim P2 item 6 exists to kill.
    view = _view("eligible", (_requirement("met"), _requirement("unmet")))
    assert view.presentation is VerdictPresentation.ELIGIBLE_MIXED
    assert view.met_count == 1  # only the met row counts, never both


def test_eligible_with_an_unknown_row_is_also_mixed() -> None:
    view = _view("eligible", (_requirement("met"), _requirement("unknown")))
    assert view.presentation is VerdictPresentation.ELIGIBLE_MIXED
    assert view.met_count == 1


def test_eligible_with_zero_met_rows_is_mixed_never_cleared() -> None:
    view = _view("eligible", (_requirement("unmet"), _requirement("unknown")))
    assert view.presentation is VerdictPresentation.ELIGIBLE_MIXED
    assert view.met_count == 0


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
