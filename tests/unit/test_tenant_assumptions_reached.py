"""T185 review: the tenant-assumption tally counts a review gate only for a lead the classifier
actually put to it. `classify` returns at the first hold, so a lead the form question stopped
never reached the location, role or judge gates — counting it there would report an abstain for
a gate that never ran."""

from __future__ import annotations

import inspect
import re

import pytest

from boardwatch.delivery import review_gate
from boardwatch.rank.tenant_assumptions import _REVIEW_REASONS_BEFORE, review_gate_reached


@pytest.mark.parametrize(
    ("reason", "reached"),
    [
        (None, {"location", "role", "judge_seniority"}),
        ("form_question_hard_stop", set()),
        ("ineligible_verdict", set()),
        ("non_us_location", {"location"}),
        ("role_vetoed", {"location", "role"}),
        ("role_unconfirmed", {"location", "role"}),
        ("seniority_above_band", {"location", "role"}),
        ("judged_ineligible_verdict", {"location", "role"}),
        ("seniority_judged_above_band", {"location", "role", "judge_seniority"}),
        ("no_requirements_found", {"location", "role", "judge_seniority"}),
    ],
)
def test_a_hold_above_a_gate_means_the_gate_was_never_reached(
    reason: str | None, reached: set[str]
) -> None:
    gates = ("location", "role", "judge_seniority")
    assert {g for g in gates if review_gate_reached(g, reason)} == reached  # type: ignore[arg-type]


def test_the_reached_table_matches_the_classifiers_own_order() -> None:
    """The table is a copy of `classify`'s clause order. Pinned against the classifier's SOURCE
    so a clause moved or added above a gate fails here rather than silently mis-attributing."""
    source = inspect.getsource(review_gate.classify)
    order = re.findall(r'return LaneDecision\(REVIEW_DIR, "([a-z_]+)"\)', source)
    assert order, "guard: the classifier's holds were not found"
    first_of = {gate: order.index(marker) for gate, marker in (
        ("location", "non_us_location"),
        ("role", "role_vetoed"),
        ("judge_seniority", "seniority_judged_above_band"),
    )}
    for gate, index in first_of.items():
        assert _REVIEW_REASONS_BEFORE[gate] == frozenset(order[:index]), gate  # type: ignore[index]
