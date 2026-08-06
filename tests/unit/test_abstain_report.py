"""Per-rule abstain rate — the metric that makes a rule which CANNOT fire visible.

The whole point of these tests is the LEFT JOIN. A `GROUP BY rule_id` over
eligibility_requirements emits no group for a rule that has never been detected, so the
rules most worth knowing about are exactly the ones such a query cannot show. Every test
here that asserts on a never-fired rule is guarding that.
"""

from __future__ import annotations

from pathlib import Path

from boardwatch.eligibility.catalog import RulesCatalog, load_rules
from boardwatch.reports.abstain import build_abstain_report

# No override dir exists here, so load_rules falls back to the bundled catalog.
BUNDLED = Path("does-not-exist")


def catalog() -> RulesCatalog:
    return load_rules(BUNDLED)


def rule_ids(cat: RulesCatalog) -> list[str]:
    return [pattern.rule_id for family in cat.families for pattern in family.patterns]


def test_every_catalog_rule_appears_even_with_no_rows() -> None:
    """The keystone requirement: enumeration comes from the catalog, not from the data."""
    cat = catalog()
    report = build_abstain_report(cat, {})

    assert [rule.rule_id for rule in report.rules] == rule_ids(cat)
    assert len(report.rules) == 44


def test_a_rule_that_never_fired_has_no_rate_rather_than_zero() -> None:
    """`None` and `0.0` mean opposite things: 'cannot be measured' vs 'never abstains'.

    Folding never-fired into 0% would report a rule that has never once fired as the
    healthiest rule in the catalog.
    """
    cat = catalog()
    fired, never = rule_ids(cat)[0], rule_ids(cat)[1]
    report = build_abstain_report(cat, {(fired, "met"): 3})

    by_id = {rule.rule_id: rule for rule in report.rules}
    assert by_id[never].observed == 0
    assert by_id[never].abstain_rate is None
    assert by_id[fired].abstain_rate == 0.0

    assert [rule.rule_id for rule in report.never_fired] == [
        rid for rid in rule_ids(cat) if rid != fired
    ]


def test_abstain_rate_is_unknown_over_observed() -> None:
    cat = catalog()
    rid = rule_ids(cat)[0]
    report = build_abstain_report(
        cat, {(rid, "met"): 1, (rid, "unmet"): 1, (rid, "unknown"): 2}
    )

    rule = report.rules[0]
    assert (rule.met, rule.unmet, rule.unknown, rule.observed) == (1, 1, 2, 4)
    assert rule.abstain_rate == 0.5


def test_a_rule_that_only_ever_abstains_is_reported_as_fully_abstaining() -> None:
    """The live pathology this metric exists to surface (17 rules, as of 2026-08-06)."""
    cat = catalog()
    always, sometimes = rule_ids(cat)[0], rule_ids(cat)[1]
    report = build_abstain_report(
        cat,
        {(always, "unknown"): 11670, (sometimes, "unknown"): 1, (sometimes, "met"): 1},
    )

    assert [rule.rule_id for rule in report.fully_abstaining] == [always]
    assert report.rules[0].abstain_rate == 1.0


def test_never_fired_is_not_counted_as_fully_abstaining() -> None:
    """Both are broken, but differently: one cannot fire, the other fires and never decides.

    Merging them would hide the never-fired rules inside a number that looks measured.
    """
    cat = catalog()
    report = build_abstain_report(cat, {})

    assert report.fully_abstaining == ()
    assert len(report.never_fired) == 44


def test_a_rule_id_outside_the_catalog_is_surfaced_not_bucketed() -> None:
    """Closed catalog: an unknown rule_id is a failure, never a new row in the table."""
    cat = catalog()
    report = build_abstain_report(cat, {("ghost:retired_rule", "met"): 7})

    assert report.out_of_catalog == ("ghost:retired_rule",)
    assert all(rule.rule_id != "ghost:retired_rule" for rule in report.rules)


def test_rows_with_no_rule_id_are_their_own_bucket() -> None:
    """NULL rule_id is allowed by the schema; it must not be folded into any real rule."""
    cat = catalog()
    report = build_abstain_report(cat, {(None, "unknown"): 5, (None, "met"): 2})

    assert report.unattributed == 7
    assert report.out_of_catalog == ()
    assert all(rule.observed == 0 for rule in report.rules)


def test_family_is_carried_so_the_report_can_group_without_reparsing() -> None:
    cat = catalog()
    report = build_abstain_report(cat, {})

    for rule in report.rules:
        assert rule.rule_id.startswith(f"{rule.family}:")
    assert {rule.family for rule in report.rules} == {f.id for f in cat.families}


def test_totals_reconcile_to_every_row_handed_in() -> None:
    """B6's reconciliation invariant in miniature: no row may vanish between input and report."""
    cat = catalog()
    known = rule_ids(cat)[0]
    counts = {
        (known, "met"): 3,
        (known, "unknown"): 4,
        ("ghost:retired_rule", "unmet"): 5,
        (None, "unknown"): 6,
    }
    report = build_abstain_report(cat, counts)

    accounted = (
        sum(rule.observed for rule in report.rules)
        + report.out_of_catalog_rows
        + report.unattributed
    )
    assert accounted == sum(counts.values()) == 18
