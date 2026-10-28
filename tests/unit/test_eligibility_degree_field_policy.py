"""D-651: `Policy.degree_field_of_study = "ignore"` decides a field-naming degree bar on its LEVEL.

The owner's rule: a master's qualifies for any bachelor's or master's bar, whatever field the
posting names; only a bar above the held level (a doctorate) fails. `compare`, and an unset
policy, keep the catalog's field-of-study comparison for every other tenant.
"""

from pathlib import Path

import pytest

from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.engine import evaluate
from boardwatch.eligibility.facts import Facts, Policy

FAMILIES = {
    "work_auth": "blocker", "experience_years": "blocker",
    "clearance": "blocker", "degree": "blocker",
}
COMPARE = Policy(families=FAMILIES)
IGNORE = Policy(families=FAMILIES, degree_field_of_study="ignore")
MASTER_SE = Facts(highest_degree="master", field_of_study="software_engineering")


@pytest.fixture(scope="module")
def catalog(tmp_path_factory: pytest.TempPathFactory):  # type: ignore[no-untyped-def]
    return load_rules(Path(tmp_path_factory.mktemp("no-override")))


def _rows(result):  # type: ignore[no-untyped-def]
    return sorted([r.rule_id, r.disposition] for r in result.requirements)


@pytest.mark.parametrize(
    "body,rule",
    [
        # An unrelated named field: `unmet` under the comparison (`unknown` for the bare bar).
        ("Bachelor's degree in Mechanical Engineering.", "degree:bachelor_in_field_listed"),
        ("A Bachelor's degree in Mechanical Engineering is required.",
         "degree:bachelor_in_field_required"),
        # A specific field the declared one is only related to: `unknown` under the comparison.
        ("A Bachelor's degree in Computer Science is required.",
         "degree:bachelor_in_field_required"),
        ("A Master's degree in Computer Science is required.",
         "degree:master_in_field_required"),
    ],
)
def test_ignore_meets_a_field_bar_at_or_below_the_held_level(catalog, body, rule) -> None:  # type: ignore[no-untyped-def]
    compared = evaluate(body, MASTER_SE, COMPARE, catalog)
    assert compared.verdict != "eligible"
    ignored = evaluate(body, MASTER_SE, IGNORE, catalog)
    assert ignored.verdict == "eligible"
    assert _rows(ignored) == [[rule, "met"]]


def test_ignore_still_fails_a_doctorate_bar(catalog) -> None:  # type: ignore[no-untyped-def]
    result = evaluate("A PhD in Computer Science is required.", MASTER_SE, IGNORE, catalog)
    assert result.verdict == "ineligible"
    assert _rows(result) == [["degree:doctorate_in_field_required", "unmet"]]


def test_ignore_still_fails_a_candidate_with_no_degree(catalog) -> None:  # type: ignore[no-untyped-def]
    result = evaluate(
        "A Bachelor's degree in Computer Science is required.",
        Facts(highest_degree="none"), IGNORE, catalog,
    )
    assert result.verdict == "ineligible"
    assert _rows(result) == [["degree:bachelor_in_field_required", "unmet"]]


def test_ignore_needs_no_declared_field_of_study(catalog) -> None:  # type: ignore[no-untyped-def]
    """Undeclared, the comparison abstains (`missing_profile_field:field_of_study`); level-only
    has nothing to compare, so the level decides."""
    facts = Facts(highest_degree="bachelor")
    body = "Bachelor's degree in Computer Science."
    assert evaluate(body, facts, COMPARE, catalog).verdict == "uncertain"
    assert evaluate(body, facts, IGNORE, catalog).verdict == "eligible"


def test_compare_is_the_unset_behaviour(catalog) -> None:  # type: ignore[no-untyped-def]
    body = "Bachelor's degree in Mechanical Engineering."
    stated = Policy(families=FAMILIES, degree_field_of_study="compare")
    assert _rows(evaluate(body, MASTER_SE, stated, catalog)) == _rows(
        evaluate(body, MASTER_SE, COMPARE, catalog)
    ) == [["degree:bachelor_in_field_listed", "unknown"]]
