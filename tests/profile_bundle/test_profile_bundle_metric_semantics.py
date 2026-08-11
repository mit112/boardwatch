"""Metric units, qualifiers, protected tokens, typed caveats, and the assertion-tag catalog (§11, §15).

Two closures get asserted against the *catalog* rather than against a list written here, because both
are things the design declares complete and a drifted catalog would quietly change:

- the initial `metric_kind`, qualifier, and unit rows, and that every metric kind has a unit that
  measures it — a kind with no unit is a kind no metric can ever legally use;
- the twelve assertion tags, their exact high-risk membership, and the two aliases §15 rejects by name.

The unit catalog defines no conversions and no dimensional inference on purpose, so `120 ms` can never
be silently compared with `0.12 s`. A test states that too, because "we just do exact lookup" is the
kind of property that erodes the first time somebody wants a convenience.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from boardwatch.profile_bundle.errors import IssueCode
from boardwatch.profile_bundle.models.metrics import (
    CaveatSeverity,
    MetricKind,
    MetricQualifier,
)
from boardwatch.profile_bundle.models.policy import (
    HIGH_RISK_ASSERTION_TAGS,
    REJECTED_ASSERTION_TAG_ALIASES,
    AssertionTagCatalog,
)
from boardwatch.profile_bundle.validation import (
    build_context,
    semantic_completeness,
    validate_semantic,
)
from tests.profile_bundle.conftest import SyntheticBundle
from tests.profile_bundle.test_profile_bundle_structural_validation import edit_document

METRICS = "metrics/records.yaml"
TAGS = "policy/assertion-tags.yaml"
CLAIMS = "claims/bullet-candidates.yaml"
PROJECT_FACTS = "facts/projects/project.packet-pantry.yaml"
THROUGHPUT = "metric.packet-pantry.throughput.001"


def context(bundle: SyntheticBundle) -> Any:
    return build_context(bundle.draft, mode="draft", bundle_root=bundle.root)


def findings(bundle: SyntheticBundle) -> tuple[Any, ...]:
    return validate_semantic(context(bundle))


def codes(found: tuple[Any, ...]) -> set[str]:
    return {f.code for f in found}


def edit_metric(bundle: SyntheticBundle, metric_id: str, **changes: Any) -> None:
    def apply(data: Any) -> None:
        for metric in data["metrics"]:
            if metric["metric_id"] == metric_id:
                metric.update(changes)

    edit_document(bundle, METRICS, apply)


# --------------------------------------------------------------------------------------
# Units
# --------------------------------------------------------------------------------------


def test_the_fixture_unit_catalog_covers_every_initial_metric_kind(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§11 says the fixture rows "exercise every initial metric kind"; a gap makes a kind unusable."""
    catalog = context(synthetic_bundle).index.units
    assert catalog is not None
    measurable = {
        kind for unit in catalog.units for kind in unit.allowed_metric_kinds
    }
    assert measurable == set(MetricKind)


def test_a_unit_outside_the_revisions_catalog_is_unknown(
    synthetic_bundle: SyntheticBundle,
) -> None:
    edit_metric(
        synthetic_bundle, THROUGHPUT, value={"number": "120", "unit": "furlongs_per_fortnight",
                                             "qualifier": "approximate"}
    )
    found = findings(synthetic_bundle)
    finding = next(f for f in found if f.code == IssueCode.METRIC_UNIT_UNKNOWN)
    assert finding.details["unit"] == "furlongs_per_fortnight"


def test_a_unit_alias_resolves_exactly_and_a_near_miss_does_not(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Aliases are exact tokens, not a fuzzy vocabulary. `item_per_second` resolves; `items/sec` does not."""
    edit_metric(
        synthetic_bundle,
        THROUGHPUT,
        value={"number": "120", "unit": "item_per_second", "qualifier": "approximate"},
    )
    assert IssueCode.METRIC_UNIT_UNKNOWN not in codes(findings(synthetic_bundle))


def test_a_unit_that_does_not_measure_the_metrics_kind_is_a_mismatch(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """`milliseconds` measures duration and latency, never throughput — no dimensional inference."""
    edit_metric(
        synthetic_bundle,
        THROUGHPUT,
        value={"number": "120", "unit": "milliseconds", "qualifier": "approximate"},
    )
    found = findings(synthetic_bundle)
    finding = next(f for f in found if f.code == IssueCode.METRIC_UNIT_KIND_MISMATCH)
    assert finding.details["metric_kind"] == "throughput"
    assert "latency" in finding.details["allowed_metric_kinds"]


def test_the_unit_catalog_declares_no_conversions(synthetic_bundle: SyntheticBundle) -> None:
    """Stated as a shape fact: a `UnitSpec` has no factor, base unit, or dimension field."""
    catalog = context(synthetic_bundle).index.units
    assert catalog is not None
    fields = set(type(catalog.units[0]).model_fields)
    assert fields == {"unit_id", "display_name", "symbol", "aliases", "allowed_metric_kinds"}


# --------------------------------------------------------------------------------------
# Qualifiers and caveats
# --------------------------------------------------------------------------------------


def test_the_qualifier_catalog_is_exactly_the_six_the_design_names() -> None:
    assert {q.value for q in MetricQualifier} == {
        "exact",
        "approximate",
        "at_least",
        "more_than",
        "at_most",
        "range",
    }


def test_an_unknown_qualifier_is_refused_before_this_layer(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """A closed enum, so `roughly` never becomes a model. Asserted where the refusal lands."""
    from boardwatch.profile_bundle.validation import BundleParseError

    edit_metric(
        synthetic_bundle,
        THROUGHPUT,
        value={"number": "120", "unit": "items_per_second", "qualifier": "roughly"},
    )
    with pytest.raises(BundleParseError):
        context(synthetic_bundle)


def test_a_disqualifying_caveat_is_a_completeness_blocker_and_not_an_error(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§11's tiering: the revision stays valid; the metric is the part that cannot be used."""
    ctx = context(synthetic_bundle)
    assert validate_semantic(ctx) == ()
    blockers = semantic_completeness(ctx)
    assert [b.record_id for b in blockers] == ["metric.packet-pantry.legacy-score.001"]
    assert blockers[0].tier == "blocker"
    assert blockers[0].code == IssueCode.METRIC_DISQUALIFYING_CAVEAT


def test_the_three_caveat_severities_are_all_present_in_the_example(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Otherwise the severity rules would be checked against a fixture exercising one of them."""
    ctx = context(synthetic_bundle)
    severities = {
        caveat.severity for metric in ctx.index.metrics for caveat in metric.caveats
    }
    assert severities == set(CaveatSeverity)


def test_a_context_required_caveat_does_not_block_its_metric(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """It must travel with a later projection; it does not make the metric unusable now."""
    ctx = context(synthetic_bundle)
    metric = next(m for m in ctx.index.metrics if m.metric_id == THROUGHPUT)
    assert metric.context_required_caveats
    assert not metric.has_disqualifying_caveat
    assert THROUGHPUT not in {b.record_id for b in semantic_completeness(ctx)}


# --------------------------------------------------------------------------------------
# Protected tokens in the metric's own wordings
# --------------------------------------------------------------------------------------


def test_an_allowed_phrasing_that_drops_a_protected_token_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """A licence to render the metric without its number would pass every downstream check."""
    edit_metric(
        synthetic_bundle,
        THROUGHPUT,
        allowed_phrasings=["sustained high throughput"],
    )
    found = findings(synthetic_bundle)
    finding = next(f for f in found if f.code == IssueCode.METRIC_PROTECTED_TOKEN_MISSING)
    assert finding.details["field"] == "allowed_phrasings[0]"
    assert finding.details["dropped_token_count"] == 2


def test_a_display_value_that_drops_a_protected_token_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    edit_metric(synthetic_bundle, THROUGHPUT, display_value="fast")
    found = findings(synthetic_bundle)
    finding = next(
        f
        for f in found
        if f.code == IssueCode.METRIC_PROTECTED_TOKEN_MISSING
        and f.details["field"] == "display_value"
    )
    assert finding.record_id == THROUGHPUT


def test_a_metric_protecting_nothing_reports_nothing(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """A required-but-empty key means "we decided there are none", not "we forgot"."""
    edit_metric(synthetic_bundle, THROUGHPUT, protected_tokens=[])
    found = [f for f in findings(synthetic_bundle) if f.record_id == THROUGHPUT]
    assert IssueCode.METRIC_PROTECTED_TOKEN_MISSING not in codes(tuple(found))


def test_no_diagnostic_quotes_the_metrics_wording(synthetic_bundle: SyntheticBundle) -> None:
    """A diagnostic may be pasted into a bug report, so it carries a count and a field, not the text."""
    edit_metric(synthetic_bundle, THROUGHPUT, allowed_phrasings=["sustained high throughput"])
    for finding in findings(synthetic_bundle):
        assert "sustained high throughput" not in finding.message
        assert "sustained high throughput" not in str(finding.details)


# --------------------------------------------------------------------------------------
# The assertion-tag catalog
# --------------------------------------------------------------------------------------


def test_the_shipped_catalog_carries_exactly_the_twelve_tags_the_design_lists(
    synthetic_bundle: SyntheticBundle,
) -> None:
    catalog = context(synthetic_bundle).index.assertion_tags
    assert catalog is not None
    assert {spec.tag_id for spec in catalog.assertion_tags} == {
        "shipped",
        "live",
        "production",
        "published",
        "granted",
        "awarded",
        "certified",
        "designed",
        "built",
        "implemented",
        "led",
        "measured",
    }


def test_the_high_risk_set_is_exactly_the_seven_the_design_calls_complete(
    synthetic_bundle: SyntheticBundle,
) -> None:
    catalog = context(synthetic_bundle).index.assertion_tags
    assert catalog is not None
    high_risk = {spec.tag_id for spec in catalog.assertion_tags if spec.high_risk}
    assert high_risk == HIGH_RISK_ASSERTION_TAGS
    assert high_risk == {
        "shipped",
        "live",
        "production",
        "published",
        "granted",
        "awarded",
        "certified",
    }


def test_every_initial_tag_has_exactly_one_authorization_branch(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§15: "Each initial tag has exactly one authorization branch"."""
    catalog = context(synthetic_bundle).index.assertion_tags
    assert catalog is not None
    for spec in catalog.assertion_tags:
        assert len(spec.authorization_any_of) == 1, spec.tag_id


def test_only_production_sets_a_required_fact_value_and_only_measured_requires_a_metric(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§15 names both singletons explicitly, and both are load-bearing."""
    catalog = context(synthetic_bundle).index.assertion_tags
    assert catalog is not None
    with_value = {
        spec.tag_id
        for spec in catalog.assertion_tags
        if spec.authorization_any_of[0].required_fact_value is not None
    }
    needs_metric = {
        spec.tag_id
        for spec in catalog.assertion_tags
        if spec.authorization_any_of[0].require_same_subject_metric
    }
    assert with_value == {"production"}
    assert needs_metric == {"measured"}


@pytest.mark.parametrize("alias", sorted(REJECTED_ASSERTION_TAG_ALIASES))
def test_a_rejected_alias_cannot_enter_the_catalog(alias: str) -> None:
    """§15 rejects `ga_release` and `in_production` by name unless a new version adds them explicitly."""
    with pytest.raises(ValidationError):
        AssertionTagCatalog.model_validate(
            {
                "assertion_tags_version": 1,
                "assertion_tags": [
                    {
                        "tag_id": alias,
                        "high_risk": True,
                        "legal_subject_kinds": ["project"],
                        "authorization_any_of": [
                            {
                                "subject_statuses": ["live_public"],
                                "required_fact_predicates": [],
                                "required_fact_value": None,
                                "require_same_subject_metric": False,
                            }
                        ],
                    }
                ],
            }
        )


@pytest.mark.parametrize("alias", sorted(REJECTED_ASSERTION_TAG_ALIASES))
def test_a_claim_carrying_a_rejected_alias_reports_an_unknown_tag(
    synthetic_bundle: SyntheticBundle, alias: str
) -> None:
    """The other half: the catalog refuses the row, and a claim naming it finds no tag to authorize."""

    def tag_it(data: Any) -> None:
        for claim in data["claims"]:
            if claim["claim_id"] == "claim.packet-pantry.overview.001":
                claim["assertion_tags"] = sorted([*claim["assertion_tags"], alias])

    edit_document(synthetic_bundle, CLAIMS, tag_it)
    found = findings(synthetic_bundle)
    unknown = [f for f in found if f.code == IssueCode.UNKNOWN_ASSERTION_TAG]
    assert unknown and unknown[0].details["tag"] == alias


# --------------------------------------------------------------------------------------
# Assertion-tag authorization, one case per high-risk tag
# --------------------------------------------------------------------------------------


def test_a_tag_on_a_subject_kind_its_row_does_not_list_is_illegal(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """`shipped` describes a project; the employment claim may not carry it."""

    def mistag(data: Any) -> None:
        for claim in data["claims"]:
            if claim["claim_id"] == "claim.example-labs.ownership.001":
                claim["assertion_tags"] = ["shipped"]

    edit_document(synthetic_bundle, CLAIMS, mistag)
    found = findings(synthetic_bundle)
    finding = next(f for f in found if f.code == IssueCode.ASSERTION_TAG_SUBJECT_ILLEGAL)
    assert finding.details["tag"] == "shipped"
    assert finding.details["subject_kind"] == "employment"


def test_shipped_is_unauthorized_when_the_project_status_is_merely_completed(
    synthetic_bundle: SyntheticBundle,
) -> None:
    def demote(data: Any) -> None:
        data["entity"]["status"] = "completed"

    edit_document(synthetic_bundle, PROJECT_FACTS, demote)
    found = findings(synthetic_bundle)
    unauthorized = {
        f.details["tag"] for f in found if f.code == IssueCode.ASSERTION_TAG_UNAUTHORIZED
    }
    assert "shipped" in unauthorized
    assert "live" in unauthorized


def test_production_has_no_implicit_authorization_from_a_completed_project(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§15 says so in as many words, and the branch is the only reason it holds.

    `production` authorizes on a referenced effective `deployment.environment == production` fact and
    on nothing else — not on status. Removing the fact from the claim's references must unauthorize it
    even while the project stays `live_public`.
    """

    def unreference(data: Any) -> None:
        for claim in data["claims"]:
            if claim["claim_id"] == "claim.packet-pantry.overview.001":
                claim["required_fact_ids"] = [
                    fact_id
                    for fact_id in claim["required_fact_ids"]
                    if fact_id != "fact.packet-pantry.deployment.001"
                ]

    edit_document(synthetic_bundle, CLAIMS, unreference)
    found = findings(synthetic_bundle)
    unauthorized = {
        f.details["tag"] for f in found if f.code == IssueCode.ASSERTION_TAG_UNAUTHORIZED
    }
    assert "production" in unauthorized
    assert "shipped" not in unauthorized, "status-based authorization must be unaffected"


def test_production_requires_the_exact_value_and_not_merely_the_predicate(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The one `required_fact_value` in the catalog. A staging deployment is not production."""

    def to_staging(data: Any) -> None:
        for fact in data["facts"]:
            if fact["fact_id"] == "fact.packet-pantry.deployment.001":
                fact["value"] = {"type": "string", "value": "staging"}

    edit_document(synthetic_bundle, PROJECT_FACTS, to_staging)
    found = findings(synthetic_bundle)
    unauthorized = {
        f.details["tag"] for f in found if f.code == IssueCode.ASSERTION_TAG_UNAUTHORIZED
    }
    assert "production" in unauthorized


def test_an_authorizing_fact_must_be_effective_and_not_merely_present(
    synthetic_bundle: SyntheticBundle,
) -> None:
    def reject_it(data: Any) -> None:
        for fact in data["facts"]:
            if fact["fact_id"] == "fact.packet-pantry.deployment.001":
                fact["verification_state"] = "rejected"

    edit_document(synthetic_bundle, PROJECT_FACTS, reject_it)
    found = findings(synthetic_bundle)
    unauthorized = {
        f.details["tag"] for f in found if f.code == IssueCode.ASSERTION_TAG_UNAUTHORIZED
    }
    assert "production" in unauthorized


def test_measured_requires_a_referenced_eligible_metric_on_the_claims_own_subject(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The `require_same_subject_metric` branch, unauthorized by dropping the metric reference."""

    def drop_metric(data: Any) -> None:
        for claim in data["claims"]:
            if claim["claim_id"] == "claim.packet-pantry.backend.001":
                claim["required_metric_ids"] = []
                claim["metric_mentions"] = []

    edit_document(synthetic_bundle, CLAIMS, drop_metric)
    found = findings(synthetic_bundle)
    unauthorized = {
        f.details["tag"] for f in found if f.code == IssueCode.ASSERTION_TAG_UNAUTHORIZED
    }
    assert "measured" in unauthorized


def test_measured_is_unauthorized_by_a_metric_about_a_different_subject(
    synthetic_bundle: SyntheticBundle,
) -> None:
    def repoint(data: Any) -> None:
        for metric in data["metrics"]:
            if metric["metric_id"] == THROUGHPUT:
                metric["subject_id"] = "employment.example-labs"

    edit_document(synthetic_bundle, METRICS, repoint)
    found = findings(synthetic_bundle)
    unauthorized = {
        f.details["tag"] for f in found if f.code == IssueCode.ASSERTION_TAG_UNAUTHORIZED
    }
    assert "measured" in unauthorized


def test_a_high_risk_tag_reports_its_risk_in_the_diagnostic(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """So an operator triaging a report can tell a `production` refusal from a `built` one."""

    def demote(data: Any) -> None:
        data["entity"]["status"] = "prototype"

    edit_document(synthetic_bundle, PROJECT_FACTS, demote)
    found = [f for f in findings(synthetic_bundle) if f.code == IssueCode.ASSERTION_TAG_UNAUTHORIZED]
    by_tag = {f.details["tag"]: f.details["high_risk"] for f in found}
    assert by_tag.get("shipped") is True


def test_the_low_risk_tags_authorize_off_the_example_as_shipped(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """`built`, `led` and `measured` are all exercised by the fixture's approved claims."""
    ctx = context(synthetic_bundle)
    tagged = {tag for claim in ctx.index.claims for tag in claim.assertion_tags}
    assert {"built", "led", "measured", "live", "production", "shipped"} <= tagged
    assert validate_semantic(ctx) == ()
