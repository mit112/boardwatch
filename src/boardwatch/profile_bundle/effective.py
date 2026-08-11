"""Derived effectiveness and surface eligibility (design §10.3, §10.4).

Nothing in the bundle stores "is this fact usable". §10.3 says plainly that "downstream eligibility
is derived", and this module is that derivation — one place, so the cardinality check, the skill
surface union, the claim surface intersection, and §15's assertion-tag authorizations all agree
about what "effective" means instead of each re-deriving it slightly differently.

## The two words, kept apart

**Effective** is §10.4's exact definition, and it is what cardinality, exclusivity and tag
authorization count: state `verified` or `owner_confirmed`, not superseded by an active edge, not
blocked by an unresolved conflict. Retained `unresolved`, `stale`, `rejected` and `superseded`
records are therefore invisible to those rules — which is the whole reason a correction by
supersession cannot push a predicate over its cardinality.

**Eligible for a surface** adds the surface question on top: the fact must declare the surface, the
predicate's catalog row must permit it, and an `application_only` predicate collapses the set to
`application` however wide the row got.

## What this module deliberately does NOT fold in

§10.3 also lists evidence problems and subject-status incompatibility as reasons a fact is
unavailable. Those stay out, because they belong to layers that already report them: the evidence
layer owns missing blobs, unmet evidence contracts and unreviewed sufficiency, and §20 runs the
layers in dependency order rather than having each one restate the previous one's findings. Folding
them in would turn one unreviewed evidence record into a cascade of surface errors on every fact,
skill and claim downstream of it, and the operator would have to work backwards to the single cause.

Expiry is out for a different reason: §20 requires validation to be a pure function of bundle
content, so `certification.expiry`'s "block active use after value date" is evaluated by
completeness against an explicit `--as-of` date, never here.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from boardwatch.profile_bundle.models.base import (
    EFFECTIVE_STATES,
    Surface,
    UsageContext,
)
from boardwatch.profile_bundle.models.facts import FactRecord, SkillRefValue
from boardwatch.profile_bundle.models.metrics import MetricRecord
from boardwatch.profile_bundle.models.policy import SurfacePolicy
from boardwatch.profile_bundle.models.skills import SkillRecord

if TYPE_CHECKING:  # pragma: no cover - import-cycle avoidance, see below
    from boardwatch.profile_bundle.validation.context import ValidationContext

# `validation/__init__.py` imports `semantic`, which imports this module, so importing anything from
# the `validation` package at module scope here would make
# `import boardwatch.profile_bundle.effective` re-enter a half-initialised module. The context type
# is only ever an annotation, and the one runtime helper is imported inside the function that uses
# it — the same deferred-import shape `validation/evidence.py` already uses for
# `BASIS_EVIDENCE_CLASSES`.


def superseded_fact_ids(ctx: ValidationContext) -> frozenset[str]:
    """Facts an active supersession edge points at.

    "Active" means the *superseding* fact is itself in an effective state. A correction the owner
    has not accepted yet — a proposed replacement sitting at `unresolved` — must not retire the
    record it proposes to replace, or a draft edit would silently remove a verified fact from every
    downstream projection while looking like an addition.
    """
    return frozenset(
        target
        for fact in ctx.index.facts
        if fact.verification_state in EFFECTIVE_STATES
        for target in fact.supersedes_fact_ids
    )


def effective_fact_ids(ctx: ValidationContext) -> frozenset[str]:
    """The effective set, computed once. §10.4's three conditions and nothing else.

    The layer calls this once and asks the set; `effective_fact` is the per-record convenience form.
    Computing it per fact would make every check that consults it quadratic in the fact count for no
    benefit, since the set cannot change while a context is alive — the context is frozen.
    """
    from boardwatch.profile_bundle.validation.referential import (
        records_blocked_by_unresolved_conflicts,
    )

    retired = superseded_fact_ids(ctx)
    blocked = records_blocked_by_unresolved_conflicts(ctx.index)
    return frozenset(
        fact.fact_id
        for fact in ctx.index.facts
        if fact.verification_state in EFFECTIVE_STATES
        and fact.fact_id not in retired
        and fact.fact_id not in blocked
    )


def effective_fact(fact: FactRecord, ctx: ValidationContext) -> bool:
    """Whether `fact` is effective in `ctx`. The per-record form of `effective_fact_ids`."""
    return fact.fact_id in effective_fact_ids(ctx)


def is_application_only(fact: FactRecord, ctx: ValidationContext) -> bool:
    """Whether `fact` may never reach a résumé or a public artefact (§16).

    Two independent declarations mean the same thing, and either is enough: the predicate's
    `surface_policy`, and membership of `application/gated-facts.yaml`. Reading only the predicate
    would miss a `standard` predicate deliberately filed in the gated document; reading only the
    file would miss an `application.*` fact authored into `facts/identity.yaml`, which is exactly
    where a leak would be least visible.
    """
    if fact.fact_id in ctx.index.gated_fact_ids:
        return True
    catalog = ctx.index.predicates
    if catalog is None:
        return False
    spec = catalog.by_id.get(fact.predicate)
    return spec is not None and spec.surface_policy is SurfacePolicy.APPLICATION_ONLY


def eligible_fact_surfaces(fact: FactRecord, ctx: ValidationContext) -> frozenset[Surface]:
    """The surfaces `fact` may currently be projected to.

    Empty for a fact that is not effective, and empty when the predicate is unknown — an unknown
    predicate has no contract to read surfaces from, and reporting it as permitting everything would
    let a typo'd predicate name widen a fact. `UNKNOWN_PREDICATE` is reported separately, so the
    operator sees the cause rather than only the consequence.
    """
    return _surfaces_of(fact, ctx, effective_fact_ids(ctx))


def _surfaces_of(
    fact: FactRecord, ctx: ValidationContext, effective: frozenset[str]
) -> frozenset[Surface]:
    """`eligible_fact_surfaces` against an already-computed effective set."""
    if fact.fact_id not in effective:
        return frozenset()
    catalog = ctx.index.predicates
    if catalog is None:
        return frozenset()
    spec = catalog.by_id.get(fact.predicate)
    if spec is None:
        return frozenset()
    allowed = set(fact.allowed_surfaces) & set(spec.legal_surfaces)
    if spec.surface_policy is SurfacePolicy.APPLICATION_ONLY:
        allowed &= {Surface.APPLICATION}
    return frozenset(allowed)


def eligible_metric(metric: MetricRecord, ctx: ValidationContext) -> bool:
    """Whether `metric` may be referenced downstream.

    A `disqualifying` caveat is what §11 says it is — "makes the metric ineligible for projection
    until a new metric supersedes it" — so it is read here rather than only reported. `ctx` is
    accepted for symmetry with the fact predicates and because a later revision-owned metric policy
    would be read from it.
    """
    del ctx  # metric eligibility is intrinsic; the parameter keeps the call sites uniform
    return metric.verification_state in EFFECTIVE_STATES and not metric.has_disqualifying_caveat


def eligible_metric_surfaces(metric: MetricRecord, ctx: ValidationContext) -> frozenset[Surface]:
    """A metric's surfaces are owner-declared (§10.3), so no evidence visibility is intersected in.

    "Private supporting evidence may legitimately verify a public metric" — a benchmark captured
    from a private repository is still a public number once the owner approves the surface. The
    `approve_metric_surfaces` binding that authorises the declaration is an owner gate, not this
    module's business.
    """
    return frozenset(metric.allowed_surfaces) if eligible_metric(metric, ctx) else frozenset()


def eligible_supporting_facts(
    skill: SkillRecord, ctx: ValidationContext
) -> tuple[FactRecord, ...]:
    """The skill's supporting facts that are effective, in authored order.

    §14 is explicit that support is not limited to `technology.used`: a supporting fact "may
    describe implementation, professional use, substantial coursework, publication work, or another
    explicit context". So this is the set whose surface union §10.3 bounds the skill by, and it is
    deliberately wider than `grounding_facts`.
    """
    effective = effective_fact_ids(ctx)
    return tuple(_supporting(skill, ctx, effective))


def _supporting(
    skill: SkillRecord, ctx: ValidationContext, effective: frozenset[str]
) -> Iterator[FactRecord]:
    for fact_id in skill.supporting_fact_ids:
        fact = ctx.index.fact(fact_id)
        if fact is None:
            continue  # a broken supporting reference is referential validation's finding
        if fact.fact_id in effective:
            yield fact


def grounding_facts(skill: SkillRecord, ctx: ValidationContext) -> tuple[FactRecord, ...]:
    """The supporting facts that can make the skill *verified* (§10.4, §14).

    Narrower than `eligible_supporting_facts` by three conditions the design states: the predicate's
    row must set `may_ground_skill`, the usage context must not be `incidental`, and — the reading
    this implementation takes — a `skill_ref` value must name the skill it is grounding.

    That last condition is an interpretation rather than a quotation. §14 says a verified skill
    needs "a supporting `technology.used` fact whose predicate contract allows skill grounding"
    without saying the fact's own `skill_id` must match. Without it, a fact recording that one
    language was used would ground a record for a different language, which is the substance of the
    rule §14 exists to state ("referencing a skill only in an old résumé … is insufficient"). A fact
    whose value is not a skill reference at all is not filtered on this condition, because it names
    no skill to disagree with.
    """
    effective = effective_fact_ids(ctx)
    catalog = ctx.index.predicates
    if catalog is None:
        return ()
    grounded: list[FactRecord] = []
    for fact in _supporting(skill, ctx, effective):
        spec = catalog.by_id.get(fact.predicate)
        if spec is None or not spec.may_ground_skill:
            continue
        if fact.usage_context is UsageContext.INCIDENTAL:
            continue
        if isinstance(fact.value, SkillRefValue) and fact.value.skill_id != skill.skill_id:
            continue
        grounded.append(fact)
    return tuple(grounded)
