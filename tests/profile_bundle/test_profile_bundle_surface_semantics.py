"""Surface semantics: the skill union, the claim intersection, and application-only containment.

§10.3 draws an asymmetry that is easy to get backwards, so it gets the most attention here:

- a **skill's** surfaces are bounded by the **union** of its eligible supporting facts', because each
  fact independently justifies the skill — so recording one more true fact can only widen support;
- a **claim's** surfaces are bounded by the **intersection** of every required record's, because each
  required record is conjunctive support for the complete wording.

Getting either backwards produces a validator that passes its own tests: the union rule with an
intersection would reject a legitimately multi-sourced skill, and the intersection rule with a union
would publish a bullet resting on an application-only fact. Both directions are asserted.
"""

from __future__ import annotations

from typing import Any

from boardwatch.profile_bundle.effective import (
    eligible_fact_surfaces,
    eligible_metric_surfaces,
    eligible_supporting_facts,
)
from boardwatch.profile_bundle.errors import IssueCode
from boardwatch.profile_bundle.models.base import Surface
from boardwatch.profile_bundle.validation import build_context, validate_semantic
from tests.profile_bundle.conftest import SyntheticBundle
from tests.profile_bundle.test_profile_bundle_structural_validation import edit_document


def context(bundle: SyntheticBundle) -> Any:
    return build_context(bundle.draft, mode="draft", bundle_root=bundle.root)


def findings(bundle: SyntheticBundle) -> tuple[Any, ...]:
    return validate_semantic(context(bundle))


def codes(found: tuple[Any, ...]) -> set[str]:
    return {f.code for f in found}


PROJECT_FACTS = "facts/projects/project.packet-pantry.yaml"
SKILL = "skill.example-language"


# --------------------------------------------------------------------------------------
# The skill union
# --------------------------------------------------------------------------------------


def test_a_skill_surface_no_eligible_supporting_fact_allows_is_unsupported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    def narrow(data: Any) -> None:
        for fact in data["facts"]:
            if fact["fact_id"] == "fact.packet-pantry.language.001":
                fact["allowed_surfaces"] = ["resume"]

    edit_document(synthetic_bundle, PROJECT_FACTS, narrow)
    found = findings(synthetic_bundle)
    assert IssueCode.SKILL_SURFACE_UNSUPPORTED in codes(found)
    finding = next(f for f in found if f.code == IssueCode.SKILL_SURFACE_UNSUPPORTED)
    assert finding.details["unsupported"] == ["public"]


def test_a_skill_surface_is_supported_by_the_union_and_not_by_every_fact_separately(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The union half, stated so an intersection implementation cannot pass.

    Two supporting facts, one allowing `resume` only and one allowing `public` only. Neither allows
    both, so an intersection rule would report the skill's `[resume, public]` as unsupported. The
    design says a skill's surfaces are a subset of the union, and this is why.
    """

    def split(data: Any) -> None:
        for fact in data["facts"]:
            if fact["fact_id"] == "fact.packet-pantry.language.001":
                fact["allowed_surfaces"] = ["resume"]
            if fact["fact_id"] == "fact.packet-pantry.legacy-language.001":
                # promote the stale record so it is eligible, and give it the other surface
                fact["verification_state"] = "verified"
                fact["expires_at"] = None
                fact["allowed_surfaces"] = ["public"]
                fact["evidence_ids"] = ["evidence.packet-pantry.manifest.001"]

    edit_document(synthetic_bundle, PROJECT_FACTS, split)
    ctx = context(synthetic_bundle)
    skill = next(s for s in ctx.index.skills if s.skill_id == SKILL)
    supporting = eligible_supporting_facts(skill, ctx)
    assert len(supporting) == 2
    per_fact = [eligible_fact_surfaces(fact, ctx) for fact in supporting]
    assert not set.intersection(*(set(item) for item in per_fact))
    assert IssueCode.SKILL_SURFACE_UNSUPPORTED not in codes(findings(synthetic_bundle))


def test_recording_one_more_true_fact_never_narrows_an_already_grounded_skill(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Monotonicity (§10.3): "Recording an additional true fact cannot narrow an already grounded skill."

    Measured rather than argued: the supported set before and after adding a narrower supporting fact.
    """
    before = _supported_surfaces(synthetic_bundle)

    def add_narrow_support(data: Any) -> None:
        original = next(
            f for f in data["facts"] if f["fact_id"] == "fact.packet-pantry.language.001"
        )
        clone = dict(original)
        clone["fact_id"] = "fact.packet-pantry.language.002"
        clone["allowed_surfaces"] = ["resume"]
        clone["usage_context"] = "contribution"
        data["facts"].append(clone)

    edit_document(synthetic_bundle, PROJECT_FACTS, add_narrow_support)

    def widen_support(data: Any) -> None:
        for skill in data["skills"]:
            if skill["skill_id"] == SKILL:
                skill["supporting_fact_ids"] = sorted(
                    [*skill["supporting_fact_ids"], "fact.packet-pantry.language.002"]
                )

    edit_document(synthetic_bundle, "skills/inventory.yaml", widen_support)
    after = _supported_surfaces(synthetic_bundle)
    assert before <= after


def _supported_surfaces(bundle: SyntheticBundle) -> set[Surface]:
    ctx = context(bundle)
    skill = next(s for s in ctx.index.skills if s.skill_id == SKILL)
    union: set[Surface] = set()
    for fact in eligible_supporting_facts(skill, ctx):
        union |= eligible_fact_surfaces(fact, ctx)
    return union


def test_a_skill_whose_only_grounding_fact_is_incidental_is_unsupported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """"`incidental` can never ground a verified skill" (§10.1), and the catalog must allow it first.

    `technology.used` does not list `incidental` among its legal contexts, so the context has to be
    added to the catalog row for the grounding rule to be the thing under test rather than the context
    rule. That is itself the design's belt and braces: two independent latches on the same door.
    """

    def admit_incidental(data: Any) -> None:
        for spec in data["predicates"]:
            if spec["predicate_id"] == "technology.used":
                spec["legal_usage_contexts"] = sorted(
                    [*spec["legal_usage_contexts"], "incidental"]
                )

    def make_incidental(data: Any) -> None:
        for fact in data["facts"]:
            if fact["fact_id"] == "fact.packet-pantry.language.001":
                fact["usage_context"] = "incidental"

    edit_document(synthetic_bundle, "policy/predicates.yaml", admit_incidental)
    edit_document(synthetic_bundle, PROJECT_FACTS, make_incidental)
    found = findings(synthetic_bundle)
    assert IssueCode.SKILL_UNSUPPORTED in codes(found)


def test_a_skill_grounded_only_by_a_predicate_that_may_not_ground_is_unsupported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    def forbid_grounding(data: Any) -> None:
        for spec in data["predicates"]:
            if spec["predicate_id"] == "technology.used":
                spec["may_ground_skill"] = False

    edit_document(synthetic_bundle, "policy/predicates.yaml", forbid_grounding)
    found = findings(synthetic_bundle)
    assert IssueCode.SKILL_UNSUPPORTED in codes(found)


def test_a_grounding_fact_naming_a_different_skill_does_not_ground_this_one(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The reading §14 implies but does not spell out: a `skill_ref` must name the skill it grounds.

    Without it, a fact recording that one technology was used would ground a record for a different
    one — which is the substance of §14's "referencing a skill only in an old résumé … is
    insufficient". Recorded as an interpretation in `effective.grounding_facts`.
    """

    def add_other_skill(data: Any) -> None:
        original = dict(data["skills"][0])
        original["skill_id"] = "skill.example-other"
        original["canonical_name"] = "Example Other"
        original["aliases"] = []
        data["skills"].append(original)

    edit_document(synthetic_bundle, "skills/inventory.yaml", add_other_skill)
    found = findings(synthetic_bundle)
    unsupported = [
        f
        for f in found
        if f.code == IssueCode.SKILL_UNSUPPORTED and f.record_id == "skill.example-other"
    ]
    assert unsupported, [(f.code, f.record_id) for f in found]


def test_an_unknown_skill_category_is_reported_against_the_revisions_own_catalog(
    synthetic_bundle: SyntheticBundle,
) -> None:
    def retype(data: Any) -> None:
        data["skills"][0]["category"] = "not-in-this-catalog"

    edit_document(synthetic_bundle, "skills/inventory.yaml", retype)
    found = findings(synthetic_bundle)
    finding = next(f for f in found if f.code == IssueCode.UNKNOWN_SKILL_CATEGORY)
    assert finding.details["career_field"] == "example-field"


# --------------------------------------------------------------------------------------
# The claim intersection
# --------------------------------------------------------------------------------------


def test_a_claim_surface_missing_from_one_required_record_is_unsupported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The intersection half. One required fact dropping `public` sinks the claim's `public`."""

    def narrow(data: Any) -> None:
        for fact in data["facts"]:
            if fact["fact_id"] == "fact.packet-pantry.url.001":
                fact["allowed_surfaces"] = ["resume"]

    edit_document(synthetic_bundle, PROJECT_FACTS, narrow)
    found = findings(synthetic_bundle)
    surface_findings = [
        f
        for f in found
        if f.code == IssueCode.CLAIM_SURFACE_UNSUPPORTED
        and f.record_id == "claim.packet-pantry.overview.001"
    ]
    assert surface_findings
    assert surface_findings[0].details["unsupported"] == ["public"]


def test_a_claim_surface_absent_from_a_required_metric_is_unsupported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    def narrow(data: Any) -> None:
        for metric in data["metrics"]:
            if metric["metric_id"] == "metric.packet-pantry.throughput.001":
                metric["allowed_surfaces"] = ["public"]

    edit_document(synthetic_bundle, "metrics/records.yaml", narrow)
    found = findings(synthetic_bundle)
    surface_findings = [
        f
        for f in found
        if f.code == IssueCode.CLAIM_SURFACE_UNSUPPORTED
        and f.record_id == "claim.packet-pantry.backend.001"
    ]
    assert surface_findings
    assert surface_findings[0].details["unsupported"] == ["resume"]


def test_a_claim_intersects_across_every_required_fact_and_metric(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The example's approved claims are the positive case, and the sets are checked by a second path."""
    ctx = context(synthetic_bundle)
    claim = next(c for c in ctx.index.claims if c.claim_id == "claim.packet-pantry.overview.001")
    assert len(claim.required_fact_ids) == 3
    supported: set[Surface] | None = None
    for fact_id in claim.required_fact_ids:
        fact = ctx.index.fact(fact_id)
        assert fact is not None
        surfaces = eligible_fact_surfaces(fact, ctx)
        supported = set(surfaces) if supported is None else supported & set(surfaces)
    assert supported is not None
    assert set(claim.allowed_surfaces) <= supported


# --------------------------------------------------------------------------------------
# Application-only containment
# --------------------------------------------------------------------------------------


def test_an_application_only_fact_cannot_widen_into_a_public_skill(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The gap the union rule leaves, and the reason `APPLICATION_ONLY_LEAK` is not redundant.

    The skill keeps a genuinely public supporting fact, so the union still permits `public` and
    `SKILL_SURFACE_UNSUPPORTED` stays silent. Only the application-only rule notices that a gated fact
    is now inside a public skill's support.
    """

    def support_with_gated(data: Any) -> None:
        for skill in data["skills"]:
            if skill["skill_id"] == SKILL:
                skill["supporting_fact_ids"] = sorted(
                    [*skill["supporting_fact_ids"], "fact.example.sponsorship.001"]
                )

    edit_document(synthetic_bundle, "skills/inventory.yaml", support_with_gated)
    found = findings(synthetic_bundle)
    assert IssueCode.APPLICATION_ONLY_LEAK in codes(found)
    assert IssueCode.SKILL_SURFACE_UNSUPPORTED not in codes(found)
    leak = next(f for f in found if f.code == IssueCode.APPLICATION_ONLY_LEAK)
    assert leak.details["fact_id"] == "fact.example.sponsorship.001"


def test_an_application_only_fact_cannot_widen_into_a_public_claim(
    synthetic_bundle: SyntheticBundle,
) -> None:
    def require_gated(data: Any) -> None:
        for claim in data["claims"]:
            if claim["claim_id"] == "claim.packet-pantry.overview.001":
                claim["required_fact_ids"] = sorted(
                    [*claim["required_fact_ids"], "fact.example.sponsorship.001"]
                )

    edit_document(synthetic_bundle, "claims/bullet-candidates.yaml", require_gated)
    found = findings(synthetic_bundle)
    assert IssueCode.APPLICATION_ONLY_LEAK in codes(found)


def test_an_application_surface_claim_resting_on_a_gated_fact_is_legitimate(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The containment rule must not forbid the case §16 exists to support.

    A gated fact belongs in an application answer. The example's summary claim already declares
    `application`, so pointing it at the sponsorship fact keeps every surface inside `application`
    plus surfaces the other required record allows.
    """

    def application_only_claim(data: Any) -> None:
        for claim in data["claims"]:
            if claim["claim_id"] == "claim.example.summary.001":
                claim["required_fact_ids"] = ["fact.example.sponsorship.001"]
                claim["allowed_surfaces"] = ["application"]

    edit_document(synthetic_bundle, "claims/summary-candidates.yaml", application_only_claim)
    found = findings(synthetic_bundle)
    about_claim = [f for f in found if f.record_id == "claim.example.summary.001"]
    assert about_claim == [], [(f.code, f.message) for f in about_claim]


def test_the_gated_document_refuses_a_resume_surface_before_this_layer_runs(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§16's file-level latch, asserted where it lands rather than re-implemented here.

    `GatedFactsDocument` rejects the record at parse time, so the tree does not become models at all —
    which is why the semantic layer's application-only check is about the *graph* instead.
    """
    from boardwatch.profile_bundle.validation import BundleParseError

    def leak(data: Any) -> None:
        data["facts"][0]["allowed_surfaces"] = ["application", "resume"]

    edit_document(synthetic_bundle, "application/gated-facts.yaml", leak)
    try:
        context(synthetic_bundle)
    except BundleParseError as exc:
        assert any(d.code == IssueCode.MODEL_VALIDATION_ERROR for d in exc.diagnostics)
    else:  # pragma: no cover - the latch is the point of the test
        raise AssertionError("the gated document accepted a resume surface")


# --------------------------------------------------------------------------------------
# Metrics and relations
# --------------------------------------------------------------------------------------


def test_metric_surfaces_are_owner_declared_and_not_intersected_with_evidence_visibility(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§10.3: "private supporting evidence may legitimately verify a public metric".

    The example's throughput metric is `[resume, public]` and rests on a `measured_result` capture; a
    validator that intersected evidence-record visibility into a metric's surfaces would narrow it.
    """
    ctx = context(synthetic_bundle)
    metric = next(m for m in ctx.index.metrics if m.metric_id == "metric.packet-pantry.throughput.001")
    assert eligible_metric_surfaces(metric, ctx) == frozenset(
        {Surface.RESUME, Surface.PUBLIC}
    )


def test_a_metric_with_a_disqualifying_caveat_exposes_no_surfaces(
    synthetic_bundle: SyntheticBundle,
) -> None:
    ctx = context(synthetic_bundle)
    metric = next(
        m for m in ctx.index.metrics if m.metric_id == "metric.packet-pantry.legacy-score.001"
    )
    assert metric.has_disqualifying_caveat
    assert eligible_metric_surfaces(metric, ctx) == frozenset()


def test_relations_expose_no_surfaces_at_all(synthetic_bundle: SyntheticBundle) -> None:
    """§10.3: relations are internal knowledge records with no `allowed_surfaces` field in this phase.

    Asserted against the model so a future field addition fails here rather than silently projecting a
    relation, which §10.3 says requires its own policy design.
    """
    ctx = context(synthetic_bundle)
    assert ctx.index.relations, "the example declares no relation to check"
    for relation in ctx.index.relations:
        assert not hasattr(relation, "allowed_surfaces")
    assert "allowed_surfaces" not in type(ctx.index.relations[0]).model_fields
