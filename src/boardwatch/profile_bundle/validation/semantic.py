"""Semantic validation: the catalogs, interpreted exhaustively (design §20.4).

This layer answers questions the earlier ones cannot. Structural validation knows a document parses;
referential validation knows every ID resolves to the right kind of record. Neither knows whether
`technology.used` is allowed to describe an award, whether two effective job titles are a conflict
nobody declared, or whether the number in a résumé bullet traces to a metric anybody measured.

## It interprets data; it does not know anything about a career

Every rule below reads the active revision's own catalogs — `policy/predicates.yaml`,
`policy/units.yaml`, `policy/skill-categories.yaml`, `policy/assertion-tags.yaml`. There is no
branch on a personal value and no branch on a career field, because the taxonomy is the user's and
the mechanism is ours. A missing catalog produces no findings here at all: `validate_structural`
already reports it as a missing required file, and inventing "no catalog means everything is
allowed" is how a deleted policy file would turn into a clean bill of health.

## Errors and blockers are separate entry points

`validate_semantic` returns the findings that make a revision invalid. `semantic_completeness`
returns the ones that leave it valid while making a named record unusable — §11's `disqualifying`
caveat is the only one this layer owns. The split mirrors `validation/evidence.py`, and it is what
lets the packaged example validate clean while still carrying a deliberately disqualified metric.

## Checks §20.4 names that are NOT here, and where the guarantee actually lands

D-115 established the rule: a check the models already refuse at parse time is deleted rather than
implemented twice, because a check that cannot fire reads as coverage. Two rows of §20.4 are in that
position, and the tests name the real refusal site instead of leaving the row looking uncovered.

- **"Entity statuses come from the correct catalog."** `EntityRecord` is a discriminated union on
  `entity_type`, and each member declares its own status enum, so a project status cannot validate
  against an award. The ID prefix is typed too, so `entity_id: project.x` with `entity_type: award`
  fails `AwardId`'s pattern. Authored YAML cannot reach a wrong-catalog status.
  What *can* go wrong is one step away and is checked here: `policy/assertion-tags.yaml` carries
  `subject_statuses` as bare tokens, so a typo there names a status no entity can ever hold and
  silently disarms a high-risk tag's authorization. `ENTITY_STATUS_ILLEGAL` is that check.
- **Metric "allowed phrasing" presence.** `MetricRecord.allowed_phrasings` has `min_length=1`, so a
  metric with no phrasing does not parse. `METRIC_PHRASING_MISSING` therefore means the reachable
  thing: a claim declares it *renders* a metric, and none of that metric's allowed phrasings appears
  in the claim's text.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from enum import StrEnum
from typing import Final

from boardwatch.profile_bundle.effective import (
    effective_fact_ids,
    eligible_fact_surfaces,
    eligible_metric,
    eligible_metric_surfaces,
    eligible_supporting_facts,
    grounding_facts,
    is_application_only,
)
from boardwatch.profile_bundle.errors import (
    Diagnostic,
    IssueCode,
    JsonValue,
    diagnostic,
    tier_of,
)
from boardwatch.profile_bundle.models.base import (
    EFFECTIVE_STATES,
    Surface,
    VerificationBasis,
    entity_kind_of,
)
from boardwatch.profile_bundle.models.claims import ClaimRecord, ClaimStatus, MetricRendering
from boardwatch.profile_bundle.models.entities import STATUS_CATALOGS
from boardwatch.profile_bundle.models.facts import FactRecord, StringValue
from boardwatch.profile_bundle.models.metrics import MetricRecord
from boardwatch.profile_bundle.models.policy import (
    AssertionAuthorizationBranch,
    AssertionTagSpec,
    Cardinality,
    ExclusivitySpec,
    OwnerAttestationAuthority,
    PredicateSpec,
    SurfacePolicy,
)
from boardwatch.profile_bundle.validation.context import ValidationContext
from boardwatch.profile_bundle.validation.evidence import supporting_evidence


def validate_semantic(ctx: ValidationContext) -> tuple[Diagnostic, ...]:
    """Every semantic finding that makes the revision invalid (§20.4)."""
    return tuple(
        finding
        for check in (
            _predicate_contracts_hold,
            _effective_facts_meet_their_predicate_evidence_contract,
            _cardinality_and_exclusivity_hold_over_effective_facts,
            _competing_single_valued_facts_are_inside_a_conflict_group,
            _fact_states_agree_with_supersession_edges,
            _assertion_tag_statuses_are_holdable,
            _skills_are_categorised_and_grounded,
            _metrics_use_the_revisions_unit_catalog,
            _metric_wordings_carry_their_protected_tokens,
            _application_only_facts_do_not_widen,
            _claims_reference_eligible_records,
            _claim_tags_are_known_and_authorised,
            _claim_text_traces_to_its_metrics,
        )
        for finding in check(ctx)
    )


def semantic_completeness(ctx: ValidationContext) -> tuple[Diagnostic, ...]:
    """Semantic completeness blockers: the revision is valid, a named record is unusable."""
    return tuple(_disqualifying_caveats_block_their_metric(ctx))


# --------------------------------------------------------------------------------------
# Predicate contracts (§10.1, §10.4)
# --------------------------------------------------------------------------------------


def _predicate_contracts_hold(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """Subject kind, value type, usage context, and surfaces against the predicate's row.

    Applied to *every* fact, not only the effective ones. These are shape contracts: a `rejected`
    candidate whose value type its predicate never admitted is malformed data that a later ruling
    could resurrect, and history is only worth keeping if it is well formed.
    """
    catalog = ctx.index.predicates
    if catalog is None:
        return
    by_id = catalog.by_id
    for fact in ctx.index.facts:
        spec = by_id.get(fact.predicate)
        if spec is None:
            yield _fact_finding(
                ctx,
                fact,
                IssueCode.UNKNOWN_PREDICATE,
                f"predicate {fact.predicate!r} is not in the active catalog "
                f"(version {catalog.predicates_version})",
                predicate=fact.predicate,
                catalog_version=catalog.predicates_version,
            )
            continue
        yield from _one_fact_against_its_contract(ctx, fact, spec)


def _one_fact_against_its_contract(
    ctx: ValidationContext, fact: FactRecord, spec: PredicateSpec
) -> Iterator[Diagnostic]:
    try:
        subject_kind = entity_kind_of(fact.subject_id)
    except ValueError:
        subject_kind = None  # a non-entity subject is a referential finding, not a kind one
    if subject_kind is not None and subject_kind not in spec.legal_subject_kinds:
        yield _fact_finding(
            ctx,
            fact,
            IssueCode.PREDICATE_SUBJECT_KIND_ILLEGAL,
            f"{fact.predicate} does not describe a {subject_kind.value} subject",
            predicate=fact.predicate,
            subject_kind=subject_kind.value,
            legal_subject_kinds=sorted(kind.value for kind in spec.legal_subject_kinds),
        )

    if fact.value_kind not in spec.legal_value_types:
        yield _fact_finding(
            ctx,
            fact,
            IssueCode.PREDICATE_VALUE_TYPE_ILLEGAL,
            f"{fact.predicate} does not admit a {fact.value_kind.value} value",
            predicate=fact.predicate,
            value_type=fact.value_kind.value,
            legal_value_types=sorted(kind.value for kind in spec.legal_value_types),
        )
    elif spec.legal_string_values and isinstance(fact.value, StringValue):
        # The one enumerated cell in §10.4: `deployment.environment` is a string ENUM. The values
        # are catalog data, so they are named in `details` rather than compared against a code
        # constant.
        if fact.value.value not in spec.legal_string_values:
            yield _fact_finding(
                ctx,
                fact,
                IssueCode.PREDICATE_VALUE_TYPE_ILLEGAL,
                f"{fact.predicate} enumerates its legal values and this fact is not one of them",
                predicate=fact.predicate,
                legal_string_values=sorted(spec.legal_string_values),
            )

    if fact.usage_context not in spec.legal_usage_contexts:
        yield _fact_finding(
            ctx,
            fact,
            IssueCode.PREDICATE_CONTEXT_ILLEGAL,
            f"{fact.predicate} does not admit usage context {fact.usage_context.value!r}",
            predicate=fact.predicate,
            usage_context=fact.usage_context.value,
            legal_usage_contexts=sorted(item.value for item in spec.legal_usage_contexts),
        )

    beyond = set(fact.allowed_surfaces) - set(spec.legal_surfaces)
    if beyond:
        yield _fact_finding(
            ctx,
            fact,
            IssueCode.PREDICATE_SURFACE_ILLEGAL,
            f"{fact.predicate} does not permit "
            f"{', '.join(sorted(surface.value for surface in beyond))}",
            predicate=fact.predicate,
            declared=sorted(surface.value for surface in beyond),
            legal_surfaces=sorted(surface.value for surface in spec.legal_surfaces),
        )

    if spec.surface_policy is SurfacePolicy.APPLICATION_ONLY:
        # The second latch (§10.4): independent of `legal_surfaces`, so a catalog edit that widened
        # the row by accident still cannot let an application-only predicate reach a résumé.
        leaked = set(fact.allowed_surfaces) - {Surface.APPLICATION}
        if leaked:
            yield _fact_finding(
                ctx,
                fact,
                IssueCode.SURFACE_POLICY_VIOLATED,
                f"{fact.predicate} is application_only but the fact declares "
                f"{', '.join(sorted(surface.value for surface in leaked))}",
                predicate=fact.predicate,
                declared=sorted(surface.value for surface in leaked),
            )


def _effective_facts_meet_their_predicate_evidence_contract(
    ctx: ValidationContext,
) -> Iterator[Diagnostic]:
    """§20.3's "every verified fact meets its predicate's evidence contract", per predicate.

    `validation/evidence.py` checks a basis against the evidence *classes* that can carry it at all
    — a global fact about `secondary_only` and friends. This checks the *predicate's own* columns,
    which are strictly narrower: `project.contribution` accepts only `repository_verified`, so an
    owner-attested contribution is a fact asserting a code review that never happened.

    Scoped to effective facts on purpose. A retained `unresolved` candidate has no established basis
    yet, and forcing a `rejected` record to satisfy the contract it failed would make history
    unstorable.
    """
    catalog = ctx.index.predicates
    if catalog is None:
        return
    by_id = catalog.by_id
    by_evidence_id = {record.evidence_id: record for record in ctx.index.evidence}
    effective = effective_fact_ids(ctx)
    for fact in ctx.index.facts:
        if fact.fact_id not in effective:
            continue
        spec = by_id.get(fact.predicate)
        if spec is None:
            continue  # UNKNOWN_PREDICATE already reported
        if fact.verification_basis not in spec.legal_verification_bases:
            yield _fact_finding(
                ctx,
                fact,
                IssueCode.EVIDENCE_CONTRACT_UNMET,
                f"{fact.predicate} does not accept basis "
                f"{fact.verification_basis.value!r}",
                predicate=fact.predicate,
                basis=fact.verification_basis.value,
                legal_verification_bases=sorted(
                    basis.value for basis in spec.legal_verification_bases
                ),
            )
        # Only the evidence that SUPPORTS this fact counts toward its predicate's contract. A
        # source contradicting or contextualizing a fact is a legitimate §12 citation and must not
        # satisfy `minimum_evidence` — see `supporting_evidence` for what reading the raw list cost.
        cited = frozenset(
            record.evidence_class for record in supporting_evidence(fact, by_evidence_id)
        )
        if not any(
            set(alternative.classes) <= cited for alternative in spec.minimum_evidence
        ):
            yield _fact_finding(
                ctx,
                fact,
                IssueCode.EVIDENCE_CONTRACT_UNMET,
                f"{fact.predicate} requires evidence this fact does not cite",
                predicate=fact.predicate,
                cited_classes=sorted(str(item) for item in cited),
                minimum_evidence=[
                    sorted(str(item) for item in alternative.classes)
                    for alternative in spec.minimum_evidence
                ],
            )
        yield from _owner_attestation_is_permitted(ctx, fact, spec)


def _owner_attestation_is_permitted(
    ctx: ValidationContext, fact: FactRecord, spec: PredicateSpec
) -> Iterator[Diagnostic]:
    """`owner_attestation_authority` is what owner attestation ALONE may establish (§10.2, §10.4).

    Only consulted when the basis actually is `owner_attested`; a fact resting on a repository
    artefact is not using the owner as its authority, whatever its state says. `owner_confirmed` is
    not a weaker synonym for `verified`, so a predicate whose authority is `owner_confirmed` refuses
    an owner-attested `verified` — that is the difference between settling an intended job title and
    proving a measured result.
    """
    if fact.verification_basis is not VerificationBasis.OWNER_ATTESTED:
        return
    authority = spec.owner_attestation_authority
    permitted: frozenset[str] = frozenset()
    if authority is OwnerAttestationAuthority.OWNER_CONFIRMED:
        permitted = frozenset({"owner_confirmed"})
    elif authority is OwnerAttestationAuthority.VERIFIED:
        permitted = frozenset({"owner_confirmed", "verified"})
    if str(fact.verification_state) in permitted:
        return
    yield _fact_finding(
        ctx,
        fact,
        IssueCode.OWNER_ATTESTATION_NOT_PERMITTED,
        f"{fact.predicate} gives owner attestation authority "
        f"{authority.value!r}, which cannot establish {fact.verification_state.value!r}",
        predicate=fact.predicate,
        owner_attestation_authority=authority.value,
        verification_state=fact.verification_state.value,
    )


def _cardinality_and_exclusivity_hold_over_effective_facts(
    ctx: ValidationContext,
) -> Iterator[Diagnostic]:
    """Counted over EFFECTIVE facts only (§10.4), which is what makes correction-by-supersession
    safe.

    The two columns are kept from restating each other. **Cardinality** owns how many effective
    facts a subject may carry. **Exclusivity** owns what cardinality cannot express: the `start <=
    end` ordering that `one_effective_range_ordered` asks for, and the count restriction when a row
    pairs a one-value exclusivity with cardinality `many`. Every shipped row that uses
    `one_effective_value` or `one_effective_set` is also cardinality `one`, so reporting the count
    twice would be two findings for one mistake — but the catalog is revision-owned data, so a
    user's `many` + `one_effective_value` row is authorable and the clause is genuinely reachable.
    """
    catalog = ctx.index.predicates
    if catalog is None:
        return
    by_id = catalog.by_id
    effective = effective_fact_ids(ctx)
    grouped: dict[tuple[str, str], list[FactRecord]] = {}
    for fact in ctx.index.facts:
        if fact.fact_id in effective:
            grouped.setdefault((fact.subject_id, fact.predicate), []).append(fact)

    for (subject_id, predicate), facts in sorted(grouped.items()):
        spec = by_id.get(predicate)
        if spec is None:
            continue
        if spec.cardinality is Cardinality.ONE and len(facts) > 1:
            yield diagnostic(
                IssueCode.PREDICATE_CARDINALITY_EXCEEDED,
                f"{subject_id} carries {len(facts)} effective {predicate} facts; the catalog "
                "allows one",
                path=ctx.index.path_of(facts[0].fact_id),
                record_id=subject_id,
                predicate=predicate,
                effective_fact_ids=sorted(fact.fact_id for fact in facts),
            )
        if (
            spec.cardinality is Cardinality.MANY
            and spec.exclusivity is not ExclusivitySpec.NONE
            and len(facts) > 1
        ):
            yield diagnostic(
                IssueCode.PREDICATE_EXCLUSIVITY_VIOLATED,
                f"{subject_id} carries {len(facts)} effective {predicate} facts; exclusivity "
                f"{spec.exclusivity.value!r} allows one",
                path=ctx.index.path_of(facts[0].fact_id),
                record_id=subject_id,
                predicate=predicate,
                exclusivity=spec.exclusivity.value,
                effective_fact_ids=sorted(fact.fact_id for fact in facts),
            )
        if spec.exclusivity is ExclusivitySpec.ONE_EFFECTIVE_RANGE_ORDERED:
            yield from _ranges_are_ordered(ctx, predicate, facts)


def _ranges_are_ordered(
    ctx: ValidationContext, predicate: str, facts: list[FactRecord]
) -> Iterator[Diagnostic]:
    """The "start <= end" half of §10.4's range cell.

    `DateRangeValue` deliberately does not enforce ordering intrinsically — §10.4 attaches it to two
    specific predicates — so this is where an inverted employment range is caught.
    """
    for fact in facts:
        start = getattr(fact.value, "start", None)
        end = getattr(fact.value, "end", None)
        if start is None or end is None:
            continue  # an open range has no end to compare; a non-range value is a type finding
        if end < start:
            yield _fact_finding(
                ctx,
                fact,
                IssueCode.PREDICATE_EXCLUSIVITY_VIOLATED,
                f"{predicate} requires start <= end, and this range ends before it starts",
                predicate=predicate,
                exclusivity=ExclusivitySpec.ONE_EFFECTIVE_RANGE_ORDERED.value,
            )


def _competing_single_valued_facts_are_inside_a_conflict_group(
    ctx: ValidationContext,
) -> Iterator[Diagnostic]:
    """§13's first detection duty: "different values for the same subject and single-valued
    predicate".

    Read over facts in an *effective state* rather than over effective facts, because a declared
    conflict group is exactly what makes competing candidates non-effective — checking the effective
    set would make the rule vacuous the moment it was obeyed.

    Facts sharing one declared group are not competing; they are a competition the author has
    declared, and the ruling decides it. Facts with the same value are not competing either — that
    is a duplicate, and cardinality reports it.
    """
    catalog = ctx.index.predicates
    if catalog is None:
        return
    by_id = catalog.by_id
    grouped: dict[tuple[str, str], list[FactRecord]] = {}
    for fact in ctx.index.facts:
        if fact.verification_state in EFFECTIVE_STATES:
            grouped.setdefault((fact.subject_id, fact.predicate), []).append(fact)

    for (subject_id, predicate), facts in sorted(grouped.items()):
        spec = by_id.get(predicate)
        if spec is None or spec.cardinality is not Cardinality.ONE or len(facts) < 2:
            continue
        if len({fact.value for fact in facts}) < 2:
            continue
        declared = {fact.conflict_group_id for fact in facts}
        if len(declared) == 1 and None not in declared:
            continue
        yield diagnostic(
            IssueCode.COMPETING_VALUES_OUTSIDE_CONFLICT,
            f"{subject_id} has competing {predicate} values that are not all inside one declared "
            "conflict group",
            path=ctx.index.path_of(facts[0].fact_id),
            record_id=subject_id,
            predicate=predicate,
            competing_fact_ids=sorted(fact.fact_id for fact in facts),
        )


def _fact_states_agree_with_supersession_edges(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """§20.4: "Fact states and supersession edges agree."

    Two directions, both reachable:

    - a fact something supersedes may not still be effective, or the correction and the record it
      corrects would both project;
    - a fact whose state is `superseded` must actually be superseded by something, or the state is
      an assertion about history that history does not contain.

    The acyclicity of the graph is referential validation's; this is about the states on its nodes.
    """
    superseded_by: dict[str, list[str]] = {}
    for fact in ctx.index.facts:
        for target in fact.supersedes_fact_ids:
            superseded_by.setdefault(target, []).append(fact.fact_id)

    for fact in ctx.index.facts:
        supersedes_it = sorted(superseded_by.get(fact.fact_id, ()))
        if supersedes_it and fact.verification_state in EFFECTIVE_STATES:
            yield _fact_finding(
                ctx,
                fact,
                IssueCode.FACT_STATE_INCONSISTENT,
                f"state {fact.verification_state.value!r} is effective, but "
                f"{', '.join(supersedes_it)} supersedes this fact",
                verification_state=fact.verification_state.value,
                superseded_by=supersedes_it,
            )
        if not supersedes_it and fact.verification_state.value == "superseded":
            yield _fact_finding(
                ctx,
                fact,
                IssueCode.FACT_STATE_INCONSISTENT,
                "state is 'superseded' but no fact supersedes it",
                verification_state=fact.verification_state.value,
            )


def _assertion_tag_statuses_are_holdable(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """A `subject_statuses` token must be a status some legal subject kind can actually hold.

    `AssertionAuthorizationBranch.subject_statuses` is a bare `LowerToken`, so `shipped_privately`
    parses cleanly and then matches nothing forever — a high-risk tag silently unauthorizable, which
    is the same defect class as an eligibility rule that can never fire. `person` contributes no
    statuses because §9 declares it no catalog, so a `person`-only tag with any status token is
    reported here too.
    """
    catalog = ctx.index.assertion_tags
    if catalog is None:
        return
    for spec in catalog.assertion_tags:
        holdable = {
            member.value
            for kind in spec.legal_subject_kinds
            for member in _statuses_of(kind.value)
        }
        for branch in spec.authorization_any_of:
            for status in branch.subject_statuses:
                if status in holdable:
                    continue
                yield diagnostic(
                    IssueCode.ENTITY_STATUS_ILLEGAL,
                    f"assertion tag {spec.tag_id!r} authorizes on status {status!r}, which no "
                    f"{', '.join(sorted(kind.value for kind in spec.legal_subject_kinds))} entity "
                    "can hold",
                    path="policy/assertion-tags.yaml",
                    record_id=spec.tag_id,
                    status=status,
                    holdable_statuses=sorted(holdable),
                )


def _statuses_of(kind: str) -> tuple[StrEnum, ...]:
    catalog = STATUS_CATALOGS.get(kind)
    return tuple(catalog) if catalog is not None else ()


# --------------------------------------------------------------------------------------
# Skills (§14, §10.4)
# --------------------------------------------------------------------------------------


def _skills_are_categorised_and_grounded(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """Category closure, grounding, and the per-surface support union (§10.3, §14).

    The surface rule is a **union** and not an intersection, and the asymmetry with claims is the
    design's: each supporting fact independently justifies the skill, so recording one more true
    fact can only ever widen support. A claim is conjunctive — every required record supports the
    complete wording — so its surfaces intersect.
    """
    categories = ctx.index.skill_categories
    for skill in ctx.index.skills:
        if categories is not None and skill.category not in categories.by_id:
            yield diagnostic(
                IssueCode.UNKNOWN_SKILL_CATEGORY,
                f"{skill.skill_id} names category {skill.category!r}, which is not in this "
                f"revision's catalog for career field {categories.career_field!r}",
                path=ctx.index.path_of(skill.skill_id),
                record_id=skill.skill_id,
                category=skill.category,
                career_field=categories.career_field,
            )

        supporting = eligible_supporting_facts(skill, ctx)
        if skill.verification_state in EFFECTIVE_STATES and not grounding_facts(skill, ctx):
            yield diagnostic(
                IssueCode.SKILL_UNSUPPORTED,
                f"{skill.skill_id} is {skill.verification_state.value} but has no effective "
                "supporting fact whose predicate may ground a skill in a non-incidental context",
                path=ctx.index.path_of(skill.skill_id),
                record_id=skill.skill_id,
                verification_state=skill.verification_state.value,
                supporting_fact_ids=sorted(skill.supporting_fact_ids),
            )

        union: set[Surface] = set()
        for fact in supporting:
            union |= eligible_fact_surfaces(fact, ctx)
        unsupported = set(skill.allowed_surfaces) - union
        if unsupported:
            yield diagnostic(
                IssueCode.SKILL_SURFACE_UNSUPPORTED,
                f"{skill.skill_id} declares "
                f"{', '.join(sorted(surface.value for surface in unsupported))} but no eligible "
                "supporting fact allows it",
                path=ctx.index.path_of(skill.skill_id),
                record_id=skill.skill_id,
                unsupported=sorted(surface.value for surface in unsupported),
                supported=sorted(surface.value for surface in union),
            )


def _application_only_facts_do_not_widen(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """§16: an application-only fact may not leak into a résumé or public artefact.

    Not subsumed by the surface rules, and the gap is on the skill side specifically. A claim's
    surfaces intersect its required records, so an application-only fact already sinks a public
    claim. A skill's surfaces are the *union* of its supporting facts, so one public fact alongside
    one application-only fact would let the application-only record ride along inside a public skill
    — the exact widening §10.3 says the graph invariants exist to prevent.
    """
    public_surfaces = {Surface.RESUME, Surface.PUBLIC}
    for skill in ctx.index.skills:
        exposed = sorted(public_surfaces & set(skill.allowed_surfaces))
        if not exposed:
            continue
        for fact_id in skill.supporting_fact_ids:
            fact = ctx.index.fact(fact_id)
            if fact is None or not is_application_only(fact, ctx):
                continue
            yield diagnostic(
                IssueCode.APPLICATION_ONLY_LEAK,
                f"{skill.skill_id} declares "
                f"{', '.join(surface.value for surface in exposed)} while resting on "
                f"application-only fact {fact_id}",
                path=ctx.index.path_of(skill.skill_id),
                record_id=skill.skill_id,
                fact_id=fact_id,
                exposed=[surface.value for surface in exposed],
            )

    for claim in ctx.index.claims:
        exposed = sorted(public_surfaces & set(claim.allowed_surfaces))
        if not exposed:
            continue
        for fact_id in claim.required_fact_ids:
            fact = ctx.index.fact(fact_id)
            if fact is None or not is_application_only(fact, ctx):
                continue
            yield diagnostic(
                IssueCode.APPLICATION_ONLY_LEAK,
                f"{claim.claim_id} declares "
                f"{', '.join(surface.value for surface in exposed)} while requiring "
                f"application-only fact {fact_id}",
                path=ctx.index.path_of(claim.claim_id),
                record_id=claim.claim_id,
                fact_id=fact_id,
                exposed=[surface.value for surface in exposed],
            )


# --------------------------------------------------------------------------------------
# Metrics (§11)
# --------------------------------------------------------------------------------------


def _metrics_use_the_revisions_unit_catalog(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """Exact ID/alias lookup into `policy/units.yaml`, then the kind pairing.

    The catalog defines no conversions and no dimensional inference on purpose, so `120 ms` can
    never be silently compared with `0.12 s`. A unit is either a token this revision declared or it
    is unknown.
    """
    catalog = ctx.index.units
    if catalog is None:
        return
    by_token = catalog.by_token
    for metric in ctx.index.metrics:
        unit = by_token.get(metric.value.unit)
        if unit is None:
            yield _metric_finding(
                ctx,
                metric,
                IssueCode.METRIC_UNIT_UNKNOWN,
                f"unit {metric.value.unit!r} is not a unit ID or alias in this revision's catalog "
                f"(version {catalog.units_version})",
                unit=metric.value.unit,
                units_version=catalog.units_version,
            )
            continue
        if metric.metric_kind not in unit.allowed_metric_kinds:
            yield _metric_finding(
                ctx,
                metric,
                IssueCode.METRIC_UNIT_KIND_MISMATCH,
                f"unit {unit.unit_id!r} does not measure {metric.metric_kind.value}",
                unit=unit.unit_id,
                metric_kind=metric.metric_kind.value,
                allowed_metric_kinds=sorted(
                    kind.value for kind in unit.allowed_metric_kinds
                ),
            )


def _metric_wordings_carry_their_protected_tokens(
    ctx: ValidationContext,
) -> Iterator[Diagnostic]:
    """Every wording the metric authorises must contain every token it protects (§11, §15).

    `protected_tokens` exists so a later projection cannot round `~120 items/s` into "thousands of
    items per second". A declared wording that drops the number is a licence to do exactly that, and
    it would pass every downstream check because the wording is on the allowed list. `display_value`
    is held to the same bar: it is the rendering the bundle offers by default.

    A metric that protects nothing has nothing to preserve, and this reports nothing for it.
    """
    for metric in ctx.index.metrics:
        if not metric.protected_tokens:
            continue
        wordings = [("display_value", metric.display_value)]
        wordings.extend(
            (f"allowed_phrasings[{position}]", phrasing)
            for position, phrasing in enumerate(metric.allowed_phrasings)
        )
        for field, wording in wordings:
            dropped = [token for token in metric.protected_tokens if token not in wording]
            if not dropped:
                continue
            yield _metric_finding(
                ctx,
                metric,
                IssueCode.METRIC_PROTECTED_TOKEN_MISSING,
                f"{field} omits {len(dropped)} protected token(s) this metric declares",
                field=field,
                dropped_token_count=len(dropped),
            )


def _disqualifying_caveats_block_their_metric(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """§11: a `disqualifying` caveat "makes the metric ineligible for projection".

    A blocker rather than an error, and the tier is the design's: the revision is a valid statement
    of what was measured, and the metric is the part that cannot be used. `MetricRecord` has no
    supersession edge, so "until a new metric supersedes it" is satisfied by authoring the
    replacement and retiring this record's state, not by anything this check can see.
    """
    for metric in ctx.index.metrics:
        if not metric.has_disqualifying_caveat:
            continue
        yield diagnostic(
            IssueCode.METRIC_DISQUALIFYING_CAVEAT,
            f"{metric.metric_id} carries a disqualifying caveat and cannot be projected until a "
            "new metric replaces it",
            path=ctx.index.path_of(metric.metric_id),
            record_id=metric.metric_id,
        )


# --------------------------------------------------------------------------------------
# Claims (§15)
# --------------------------------------------------------------------------------------


def _claims_reference_eligible_records(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """An approved claim's support, and the surface intersection (§10.3, §15).

    Scoped to `approved` claims, the same boundary `ClaimRecord` already documents for its empty
    `required_fact_ids`: a `draft` is wording the owner is still assembling support for, and failing
    the revision over an unfinished draft would make the bundle unable to hold work in progress.

    Surfaces intersect because every required record is conjunctive support for the *complete*
    wording. A bullet that needs a public fact and an application-only fact is not two-thirds
    publishable; it is not publishable.
    """
    for claim in ctx.index.claims:
        if claim.status is not ClaimStatus.APPROVED:
            continue
        if not claim.required_fact_ids:
            yield _claim_finding(
                ctx,
                claim,
                IssueCode.CLAIM_WITHOUT_FACTS,
                "an approved claim must reference at least one fact",
            )

        supported: frozenset[Surface] | None = None
        for fact_id in claim.required_fact_ids:
            fact = ctx.index.fact(fact_id)
            if fact is None:
                continue  # referential validation reports the broken reference
            surfaces = eligible_fact_surfaces(fact, ctx)
            if not surfaces and fact.fact_id not in effective_fact_ids(ctx):
                yield _claim_finding(
                    ctx,
                    claim,
                    IssueCode.CLAIM_FACT_INELIGIBLE,
                    f"required fact {fact_id} is not effective "
                    f"({fact.verification_state.value})",
                    required_record_id=fact_id,
                    verification_state=fact.verification_state.value,
                )
            supported = surfaces if supported is None else supported & surfaces

        for metric_id in claim.required_metric_ids:
            metric = ctx.index.metric(metric_id)
            if metric is None:
                continue
            if not eligible_metric(metric, ctx):
                yield _claim_finding(
                    ctx,
                    claim,
                    IssueCode.CLAIM_FACT_INELIGIBLE,
                    f"required metric {metric_id} is not eligible "
                    f"({metric.verification_state.value}"
                    f"{', disqualifying caveat' if metric.has_disqualifying_caveat else ''})",
                    required_record_id=metric_id,
                    verification_state=metric.verification_state.value,
                )
            surfaces = eligible_metric_surfaces(metric, ctx)
            supported = surfaces if supported is None else supported & surfaces

        if supported is None:
            continue  # nothing to intersect; CLAIM_WITHOUT_FACTS already reported
        unsupported = set(claim.allowed_surfaces) - supported
        if unsupported:
            yield _claim_finding(
                ctx,
                claim,
                IssueCode.CLAIM_SURFACE_UNSUPPORTED,
                f"declares {', '.join(sorted(s.value for s in unsupported))} but its required "
                "records do not all allow it",
                unsupported=sorted(surface.value for surface in unsupported),
                supported=sorted(surface.value for surface in supported),
            )


def _claim_tags_are_known_and_authorised(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """Catalog closure and subject kind for every claim; authorization for approved ones.

    The split matches the previous check's. A tag that is not in the catalog, or that cannot
    describe this kind of subject, is wrong in a draft too — those are catalog facts, not support
    facts. Whether the *references* authorize it depends on support the draft may not have gathered
    yet.
    """
    catalog = ctx.index.assertion_tags
    if catalog is None:
        return
    by_id = catalog.by_id
    effective = effective_fact_ids(ctx)
    for claim in ctx.index.claims:
        try:
            subject_kind = entity_kind_of(claim.subject_id)
        except ValueError:
            subject_kind = None
        for tag in claim.assertion_tags:
            spec = by_id.get(tag)
            if spec is None:
                yield _claim_finding(
                    ctx,
                    claim,
                    IssueCode.UNKNOWN_ASSERTION_TAG,
                    f"assertion tag {tag!r} is not in the active catalog "
                    f"(version {catalog.assertion_tags_version})",
                    tag=tag,
                )
                continue
            if subject_kind is not None and subject_kind not in spec.legal_subject_kinds:
                yield _claim_finding(
                    ctx,
                    claim,
                    IssueCode.ASSERTION_TAG_SUBJECT_ILLEGAL,
                    f"assertion tag {tag!r} does not describe a {subject_kind.value} subject",
                    tag=tag,
                    subject_kind=subject_kind.value,
                    legal_subject_kinds=sorted(
                        kind.value for kind in spec.legal_subject_kinds
                    ),
                )
                continue
            if claim.status is not ClaimStatus.APPROVED:
                continue
            if not _any_branch_authorises(ctx, claim, spec, effective):
                yield _claim_finding(
                    ctx,
                    claim,
                    IssueCode.ASSERTION_TAG_UNAUTHORIZED,
                    f"no authorization branch of assertion tag {tag!r} is satisfied by this "
                    "claim's referenced records",
                    tag=tag,
                    high_risk=spec.high_risk,
                )


def _any_branch_authorises(
    ctx: ValidationContext,
    claim: ClaimRecord,
    spec: AssertionTagSpec,
    effective: frozenset[str],
) -> bool:
    """`authorization_any_of` succeeds when at least one COMPLETE branch succeeds (§15)."""
    return any(
        _branch_authorises(ctx, claim, branch, effective)
        for branch in spec.authorization_any_of
    )


def _branch_authorises(
    ctx: ValidationContext,
    claim: ClaimRecord,
    branch: AssertionAuthorizationBranch,
    effective: frozenset[str],
) -> bool:
    """Within one branch every non-empty constraint is ANDed; items inside a list are alternatives.

    An authorizing fact must be effective, must be on the claim's own subject, and must be in the
    claim's `required_fact_ids` — a tag justified by a fact the claim does not carry would survive
    the fact being removed.
    """
    if branch.subject_statuses:
        subject = ctx.index.entities.get(claim.subject_id)
        status = getattr(subject, "status", None)
        if status is None or str(status) not in branch.subject_statuses:
            return False

    if branch.required_fact_predicates:
        matched = False
        for fact_id in claim.required_fact_ids:
            fact = ctx.index.fact(fact_id)
            if fact is None or fact.fact_id not in effective:
                continue
            if fact.subject_id != claim.subject_id:
                continue
            if fact.predicate not in branch.required_fact_predicates:
                continue
            if branch.required_fact_value is not None and fact.value != branch.required_fact_value:
                continue
            matched = True
            break
        if not matched:
            return False

    if branch.require_same_subject_metric:
        matched = False
        for metric_id in claim.required_metric_ids:
            metric = ctx.index.metric(metric_id)
            if metric is None or metric.subject_id != claim.subject_id:
                continue
            if not eligible_metric(metric, ctx):
                continue
            matched = True
            break
        if not matched:
            return False

    return True


#: A figure in claim prose: a digit run with optional grouping, decimal part, and percent sign. Kept
#: deliberately blunt. §15 requires that *every* numeral trace to a referenced metric, so a scanner
#: that tried to tell a "real" measurement from an incidental number would be deciding the very
# thing  the rule exists to stop an author from deciding informally.
_FIGURE_RE: Final = re.compile(r"\d[\d,]*(?:\.\d+)?%?")


def _claim_text_traces_to_its_metrics(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """Figure traceability, rendering declarations, forbidden wording, protected tokens (§15).

    The traceability rule, stated exactly as implemented: a figure in the text traces when some
    referenced metric whose mention is `rendered` has an allowed phrasing that appears verbatim in
    the text *and* contains that figure. Requiring the phrasing itself to appear is what makes the
    check about an authorised rendering rather than about a number happening to match.

    This is strict, and deliberately so. A year, a version number, or a "24/7" in a bullet is an
    untraceable figure, because the bundle cannot tell it apart from a performance number nobody
    measured — and an unbacked number is the failure mode §11 opens by naming.
    """
    for claim in ctx.index.claims:
        yield from _mentions_agree_with_requirements(ctx, claim)
        if claim.status is not ClaimStatus.APPROVED:
            continue
        rendering = claim.mention_by_metric
        referenced = [
            metric
            for metric_id in claim.required_metric_ids
            if (metric := ctx.index.metric(metric_id)) is not None
        ]
        yield from _forbidden_phrasings_are_absent(ctx, claim, referenced)
        yield from _rendered_metrics_appear(ctx, claim, referenced, rendering)
        yield from _figures_trace_to_a_rendering(ctx, claim, referenced, rendering)


def _mentions_agree_with_requirements(
    ctx: ValidationContext, claim: ClaimRecord
) -> Iterator[Diagnostic]:
    """§15: a referenced metric omitted from the text "must be declared `qualitative_only`".

    A metric with no mention at all has declared nothing, which is the omission this reports. The
    mirror case — a mention for a metric the claim does not require — is the same disagreement seen
    from the other side, and sharing the code keeps one condition in one place.
    """
    required = set(claim.required_metric_ids)
    mentioned = set(claim.mention_by_metric)
    for metric_id in sorted(required - mentioned):
        yield _claim_finding(
            ctx,
            claim,
            IssueCode.CLAIM_METRIC_MENTION_MISSING,
            f"required metric {metric_id} has no metric_mentions entry, so its rendering is "
            "undeclared",
            required_record_id=metric_id,
        )
    for metric_id in sorted(mentioned - required):
        yield _claim_finding(
            ctx,
            claim,
            IssueCode.CLAIM_METRIC_MENTION_MISSING,
            f"metric_mentions names {metric_id}, which this claim does not require",
            required_record_id=metric_id,
        )


def _forbidden_phrasings_are_absent(
    ctx: ValidationContext, claim: ClaimRecord, referenced: list[MetricRecord]
) -> Iterator[Diagnostic]:
    for metric in referenced:
        for phrasing in metric.forbidden_phrasings:
            if phrasing not in claim.text:
                continue
            yield _claim_finding(
                ctx,
                claim,
                IssueCode.METRIC_FORBIDDEN_PHRASING,
                f"text contains a phrasing {metric.metric_id} explicitly forbids",
                required_record_id=metric.metric_id,
            )


def _rendered_metrics_appear(
    ctx: ValidationContext,
    claim: ClaimRecord,
    referenced: list[MetricRecord],
    rendering: dict[str, MetricRendering],
) -> Iterator[Diagnostic]:
    """A `rendered` mention must render, in an authorised wording, with its tokens intact."""
    for metric in referenced:
        if rendering.get(metric.metric_id) is not MetricRendering.RENDERED:
            continue
        if not any(phrasing in claim.text for phrasing in metric.allowed_phrasings):
            yield _claim_finding(
                ctx,
                claim,
                IssueCode.METRIC_PHRASING_MISSING,
                f"{metric.metric_id} is declared rendered but none of its allowed phrasings "
                "appears in the text",
                required_record_id=metric.metric_id,
            )
            continue
        dropped = [token for token in metric.protected_tokens if token not in claim.text]
        if dropped:
            yield _claim_finding(
                ctx,
                claim,
                IssueCode.CLAIM_PROTECTED_TOKEN_DROPPED,
                f"text renders {metric.metric_id} but drops {len(dropped)} of its protected "
                "token(s)",
                required_record_id=metric.metric_id,
                dropped_token_count=len(dropped),
            )


def _figures_trace_to_a_rendering(
    ctx: ValidationContext,
    claim: ClaimRecord,
    referenced: list[MetricRecord],
    rendering: dict[str, MetricRendering],
) -> Iterator[Diagnostic]:
    renderings = [
        phrasing
        for metric in referenced
        if rendering.get(metric.metric_id) is MetricRendering.RENDERED
        for phrasing in metric.allowed_phrasings
        if phrasing in claim.text
    ]
    for match in _FIGURE_RE.finditer(claim.text):
        figure = match.group()
        if any(figure in phrasing for phrasing in renderings):
            continue
        yield _claim_finding(
            ctx,
            claim,
            IssueCode.CLAIM_UNTRACEABLE_FIGURE,
            "text carries a figure that no referenced metric's rendered phrasing accounts for",
            offset=match.start(),
        )


# --------------------------------------------------------------------------------------
# Diagnostic helpers
# --------------------------------------------------------------------------------------


def _finding(
    code: IssueCode,
    message: str,
    *,
    path: str | None,
    record_id: str,
    details: Mapping[str, JsonValue],
) -> Diagnostic:
    """One finding, with its tier taken from the code.

    Builds the dataclass instead of calling `errors.diagnostic`, because forwarding a details
    *mapping* through that factory's `**details` would also make its `tier` parameter assignable
    from the mapping — and refusing a caller the ability to quietly downgrade an error is the one
    thing that factory exists to guarantee. `tier_of` is the same source the factory reads.
    """
    return Diagnostic(
        tier=tier_of(code),
        code=str(code),
        path=path,
        record_id=record_id,
        message=message,
        details=dict(details),
    )


def _fact_finding(
    ctx: ValidationContext,
    fact: FactRecord,
    code: IssueCode,
    message: str,
    **details: JsonValue,
) -> Diagnostic:
    return _finding(
        code,
        f"{fact.fact_id}: {message}",
        path=ctx.index.path_of(fact.fact_id),
        record_id=fact.fact_id,
        details=details,
    )


def _metric_finding(
    ctx: ValidationContext,
    metric: MetricRecord,
    code: IssueCode,
    message: str,
    **details: JsonValue,
) -> Diagnostic:
    return _finding(
        code,
        f"{metric.metric_id}: {message}",
        path=ctx.index.path_of(metric.metric_id),
        record_id=metric.metric_id,
        details=details,
    )


def _claim_finding(
    ctx: ValidationContext,
    claim: ClaimRecord,
    code: IssueCode,
    message: str,
    **details: JsonValue,
) -> Diagnostic:
    """Claim findings never quote the claim text — a diagnostic may be pasted into a bug report, and
    the wording is the owner's private draft. An offset locates the problem instead."""
    return _finding(
        code,
        f"{claim.claim_id}: {message}",
        path=ctx.index.path_of(claim.claim_id),
        record_id=claim.claim_id,
        details=details,
    )
