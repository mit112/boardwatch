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
    assert len(report.rules) == 45


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
    assert len(report.never_fired) == 45


def test_a_structurally_undecidable_rule_is_reported_apart_from_the_fixable_ones() -> None:
    """D-253: `scoped_years_minimum` abstains unconditionally (the schema stores no per-skill
    durations), so its 100% abstain is a schema gap, not a fixable blind spot. It must stay
    visible but must NOT inflate the actionable 'fire but never decide' count and mask the
    rules a profile fact or a code line would fix."""
    from boardwatch.reports.abstain import STRUCTURALLY_UNDECIDABLE

    cat = catalog()
    structural = "experience_years:scoped_years_minimum"
    assert structural in STRUCTURALLY_UNDECIDABLE  # the constant names a real catalog rule
    fixable = next(r for r in rule_ids(cat) if r not in STRUCTURALLY_UNDECIDABLE)
    report = build_abstain_report(
        cat, {(structural, "unknown"): 16007, (fixable, "unknown"): 5}
    )

    by_id = {rule.rule_id: rule for rule in report.rules}
    assert by_id[structural].structurally_undecidable is True
    assert by_id[fixable].structurally_undecidable is False
    # both fire and only ever abstain, so both are fully_abstaining (unchanged semantics)...
    assert {structural, fixable} <= {rule.rule_id for rule in report.fully_abstaining}
    # ...but the structural one is bucketed apart and dropped from the actionable count. The
    # structurally-undecidable set is intrinsic (flagged from the constant), so it lists every
    # such catalog rule regardless of rows — both scoped_years_minimum and clearable_required.
    # A LITERAL, not `set(STRUCTURALLY_UNDECIDABLE)`: comparing the report against the same
    # constant the production code reads is vacuous, because a mutant that drops a member from
    # `STRUCTURALLY_UNDECIDABLE` moves BOTH sides and the equality still holds. Pinned to the two
    # ids `abstain.py` declares so dropping either one fails here (D-253).
    structural_ids = {rule.rule_id for rule in report.structurally_undecidable}
    assert structural_ids == {
        "experience_years:scoped_years_minimum",
        "clearance:clearable_required",
    }
    fixable_ids = {rule.rule_id for rule in report.fully_abstaining_fixable}
    assert structural not in fixable_ids
    assert fixable in fixable_ids


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

    assert report.total_rows == sum(counts.values()) == 18
    assert report.observed_rows == 7
    assert report.out_of_catalog_rows == 5
    assert report.unattributed == 6


def test_an_unrecognised_disposition_still_counts_toward_observed() -> None:
    """Impossible while the DB CHECK holds. Guarded so that widening it cannot silently shrink
    every denominator in the report — a lost row would inflate abstain rates, not just vanish."""
    cat = catalog()
    rid = rule_ids(cat)[0]
    report = build_abstain_report(cat, {(rid, "unknown"): 1, (rid, "not_a_disposition"): 3})

    rule = report.rules[0]
    assert (rule.other, rule.observed) == (3, 4)
    assert rule.abstain_rate == 0.25
    assert report.total_rows == 4


def test_a_family_outside_the_catalog_is_surfaced_as_a_failure() -> None:
    """Closed catalog at the FAMILY level: a disposition observed under a family the catalog
    does not declare is a failure, never a silent new bucket. Distinct from the rule_id
    surfacing, so a report reader learns which VOCABULARY drifted, not only which id."""
    cat = catalog()
    report = build_abstain_report(cat, {("ghost:retired_rule", "met"): 7})

    assert report.out_of_catalog_families == ("ghost",)
    # A catalog family never appears here, and the failure is not folded into any real rule.
    assert all(f not in {f.id for f in cat.families} for f in report.out_of_catalog_families)
    assert all(rule.family != "ghost" for rule in report.rules)


def test_a_bogus_disposition_token_is_surfaced_as_a_failure() -> None:
    """Closed token set: a disposition outside {met, unmet, unknown} — including a stray
    verdict literal like 'eligible' leaking into the disposition column — is surfaced as a
    FAILURE rather than only counted. It still reconciles into `observed`/`total_rows` (the
    denominator invariant one level up), but it is never invisible: the anomaly gets its own
    failure line instead of being quietly absorbed."""
    cat = catalog()
    rid = rule_ids(cat)[0]
    report = build_abstain_report(
        cat, {(rid, "met"): 1, (rid, "eligible"): 2, (rid, "not_a_disposition"): 3}
    )

    assert report.bad_dispositions == ("eligible", "not_a_disposition")
    # Surfaced AND still reconciled — not dropped, not hidden.
    assert report.total_rows == 6
    assert report.rules[0].observed == 6


def test_valid_dispositions_produce_no_bogus_token_failure() -> None:
    """The closed-token guard must not fire on the legitimate vocabulary."""
    cat = catalog()
    rid = rule_ids(cat)[0]
    report = build_abstain_report(
        cat, {(rid, "met"): 1, (rid, "unmet"): 1, (rid, "unknown"): 1}
    )

    assert report.bad_dispositions == ()
    assert report.out_of_catalog_families == ()


def test_skip_family_reports_not_applicable_not_never_fired() -> None:
    import pathlib
    import tempfile

    import yaml

    from boardwatch.eligibility.catalog import bundled_rules_text, load_rules

    doc = yaml.safe_load(bundled_rules_text())
    doc["career_fields"] = ["software", "data"]
    for fam in doc["families"]:
        if fam["id"] == "internship":
            fam["tier"] = "field"
            fam["applies_to"] = ["software"]
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "rules.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    catalog = load_rules(d)
    # internship is skipped for a "data" profile → zero rows → must be not_applicable, not never_fired
    na = frozenset({"internship"})
    report = build_abstain_report(catalog, {}, not_applicable_families=na)
    internship_rules = [r for r in report.rules if r.family == "internship"]
    assert internship_rules and all(r.not_applicable for r in internship_rules)
    assert all(not r.never_fired for r in internship_rules)
    assert all(r.rule_id in {x.rule_id for x in report.not_applicable} for r in internship_rules)
    # a genuinely never-fired family is still never_fired
    assert any(r.never_fired for r in report.rules if r.family != "internship")
