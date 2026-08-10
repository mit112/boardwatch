"""The typed outcome contract: design §21's 0/1/2/3 exit categories.

Exit codes are the CLI's whole promise to an automated caller, so they are pinned per code
rather than derived at the call site. A state refusal the operator can act on (a moved parent)
is a *finding*; a check that could not run at all (lock contention, unsupported schema) is
`could_not_complete`. Collapsing those two is how a skipped check gets read as a clean one.
"""

from __future__ import annotations

import pytest

from boardwatch.profile_bundle.errors import (
    COULD_NOT_COMPLETE_CODES,
    STATE_REFUSAL_CODES,
    Diagnostic,
    IssueCode,
    OperationOutcome,
    exit_code_for_category,
    outcome_for,
    tier_of,
)


def test_state_refusal_and_finding_exit_one_but_io_exit_three() -> None:
    assert outcome_for(IssueCode.STALE_DRAFT_PARENT).exit_code == 1
    assert outcome_for(IssueCode.BUNDLE_LOCK_HELD).exit_code == 3


def test_every_category_maps_to_its_design_exit_code() -> None:
    assert exit_code_for_category("clean") == 0
    assert exit_code_for_category("findings") == 1
    assert exit_code_for_category("usage_error") == 2
    assert exit_code_for_category("could_not_complete") == 3


@pytest.mark.parametrize(
    "code",
    [
        IssueCode.STALE_DRAFT_PARENT,
        IssueCode.DRAFT_REBASE_CONFLICT,
        IssueCode.DRAFT_BACKUP_CONFLICT,
    ],
)
def test_design_state_refusals_are_findings(code: IssueCode) -> None:
    outcome = outcome_for(code)
    assert outcome.category == "findings"
    assert outcome.exit_code == 1
    assert code in STATE_REFUSAL_CODES


@pytest.mark.parametrize(
    "code",
    [
        IssueCode.BUNDLE_LOCK_HELD,
        IssueCode.PROMOTION_TARGET_CONFLICT,
        IssueCode.UNSUPPORTED_SCHEMA_VERSION,
        IssueCode.UNSUPPORTED_SECRET_SCAN_RULESET_VERSION,
        IssueCode.IO_ERROR,
        IssueCode.INTERNAL_ERROR,
    ],
)
def test_design_could_not_complete_codes_exit_three(code: IssueCode) -> None:
    outcome = outcome_for(code)
    assert outcome.category == "could_not_complete"
    assert outcome.exit_code == 3
    assert code in COULD_NOT_COMPLETE_CODES


def test_state_refusal_and_could_not_complete_sets_are_disjoint() -> None:
    """One code, one category. An overlap would make `outcome_for` order-dependent."""
    assert not (STATE_REFUSAL_CODES & COULD_NOT_COMPLETE_CODES)


def test_outcome_carries_one_diagnostic_naming_its_code() -> None:
    outcome = outcome_for(IssueCode.STALE_DRAFT_PARENT)
    assert outcome.value is None
    assert len(outcome.diagnostics) == 1
    assert outcome.diagnostics[0].code == "stale_draft_parent"
    assert outcome.diagnostics[0].tier == "error"


def test_every_issue_code_has_a_declared_tier() -> None:
    """A code with no tier would silently become a warning in the report layer."""
    for code in IssueCode:
        assert tier_of(code) in {"error", "blocker", "warning", "information"}


def test_unverifiable_ancestor_is_a_completeness_blocker_not_an_error() -> None:
    """Design §7: a missing ancestor never makes the SELECTED revision invalid."""
    assert tier_of(IssueCode.UNVERIFIABLE_ANCESTOR) == "blocker"


def test_clean_outcome_has_exit_zero_and_no_diagnostics() -> None:
    outcome: OperationOutcome[int] = OperationOutcome.clean(7)
    assert outcome.category == "clean"
    assert outcome.exit_code == 0
    assert outcome.value == 7
    assert outcome.diagnostics == ()


def test_findings_outcome_reports_the_worst_tier_present() -> None:
    warning = Diagnostic(
        tier="warning", code="x", path=None, record_id=None, message="m", details={}
    )
    blocker = Diagnostic(
        tier="blocker", code="y", path=None, record_id=None, message="m", details={}
    )
    assert OperationOutcome.from_diagnostics(None, (warning,)).category == "clean"
    assert OperationOutcome.from_diagnostics(None, (warning, blocker)).category == "findings"


def test_diagnostic_sort_key_is_total_and_deterministic() -> None:
    """Report order must not depend on discovery order."""
    first = Diagnostic(
        tier="blocker", code="b", path="p", record_id=None, message="m", details={}
    )
    second = Diagnostic(
        tier="error", code="a", path="p", record_id=None, message="m", details={}
    )
    assert sorted((first, second), key=lambda d: d.sort_key())[0] is second
