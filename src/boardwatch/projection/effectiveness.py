"""Which of an entity's facts a résumé may cite, at an explicit date.

Three gates, deliberately kept apart, because two of them are NOT the same check:

- **effective** — `effective_fact_ids` (verification state, supersession, unresolved conflicts).
- **surfaced** — `resume` in the fact's own declared `allowed_surfaces`, plus `is_application_only`
  (gated by `application/gated-facts.yaml` membership, or a predicate's `application_only` surface
  policy — neither is visible on `allowed_surfaces` alone, so a fact could declare `resume` and
  still be barred). This is deliberately NOT re-intersected with the predicate's own
  `legal_surfaces`, the way `effective.eligible_fact_surfaces` does: `completeness.py`'s
  `_surface_coverage` already establishes that a fact's declared surfaces and its eligible ones
  agree whenever the bundle has passed semantic validation — `PREDICATE_SURFACE_ILLEGAL` and
  `APPLICATION_ONLY_LEAK` are exactly the findings that would make them disagree — and projection
  only ever reads a bundle's CURRENT, promoted revision, which cannot become current without
  passing that gate.
- **unexpired** — `declared_expiry` against an explicit `as_of`, but only for a predicate whose
  `expiry.behaviour` is `block_active_use_after_value_date`. `effective.py` deliberately excludes
  expiry entirely because that package reads no clock, but WHICH predicates the date applies to is
  not this module's to skip: `completeness.py`'s own docstring for the equivalent check names the
  failure of asking `declared_expiry` unconditionally — "a date authored on a fact whose predicate
  expires `never` records when the author expects to revisit it, not a date after which the value
  stops being true — blocking on that alone would retire a live skill because somebody left
  themselves a note."

Keeping effectiveness and surfacing apart matters more than usual here: `eligible_fact_surfaces`
returns an EMPTY surface set for a non-effective fact, so implementing the surface gate through it
would make the effectiveness gate untestable — a bug there would pass without ever being reached.

`effective_fact_ids` is hoisted once. It is O(facts + conflict candidates) per call, so asking it
per fact would make this quadratic for no benefit, since the set cannot change while a context is
alive — the context is frozen.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

from boardwatch.profile_bundle.effective import effective_fact_ids, is_application_only
from boardwatch.profile_bundle.models.base import Surface
from boardwatch.profile_bundle.models.facts import FactRecord
from boardwatch.profile_bundle.models.policy import ExpiryBehaviour
from boardwatch.profile_bundle.validation.completeness import declared_expiry
from boardwatch.profile_bundle.validation.context import ValidationContext


def _resume_facts(entity_id: str, ctx: ValidationContext, *, as_of: date) -> Iterator[FactRecord]:
    """Every fact about `entity_id` a résumé may cite at `as_of`, in index order.

    The four gates — effective, résumé-surfaced, not application-only, unexpired — are the shared
    definition of "citable on a résumé". `resume_facts_for` (one per predicate, for `{predicate}`
    templates) and `resume_bullet_facts_for` (all of one predicate, for fact-derived bullets)
    differ only in how they consume this stream, never in what they admit.
    """
    effective = effective_fact_ids(ctx)
    for fact in ctx.index.facts:
        if fact.subject_id != entity_id:
            continue
        if fact.fact_id not in effective:
            continue
        if Surface.RESUME not in fact.allowed_surfaces:
            continue
        if is_application_only(fact, ctx):
            continue
        if _past_its_value_date(fact, ctx, as_of=as_of):
            continue
        yield fact


def resume_facts_for(
    entity_id: str, ctx: ValidationContext, *, as_of: date
) -> dict[str, FactRecord]:
    """Predicate → fact, for the facts about `entity_id` a résumé may cite at `as_of`.

    Keyed by predicate because that is what the `{predicate}` grammar looks up. A predicate with
    two usable facts keeps the first in index order; a genuine ambiguity there is a bundle
    cardinality problem, which the bundle's own validation owns, not projection's.
    """
    out: dict[str, FactRecord] = {}
    for fact in _resume_facts(entity_id, ctx, as_of=as_of):
        out.setdefault(fact.predicate, fact)
    return out


def resume_bullet_facts_for(
    entity_id: str, predicate: str, ctx: ValidationContext, *, as_of: date
) -> list[FactRecord]:
    """Every résumé-citable fact of `predicate` about `entity_id`, in index order.

    Unlike `resume_facts_for`'s first-wins mapping, this keeps ALL of a multi-valued predicate's
    facts, so `employment.accomplishment` or `project.contribution` renders as several bullets
    (D-188). An empty list is a truthful report of "no such fact", not an error: the pool decides
    whether a declared bullet predicate resolving to nothing is a refusal.
    """
    return [
        fact for fact in _resume_facts(entity_id, ctx, as_of=as_of) if fact.predicate == predicate
    ]


def _past_its_value_date(fact: FactRecord, ctx: ValidationContext, *, as_of: date) -> bool:
    """Whether `fact`'s predicate blocks active use after its value date, and that date has passed.

    Only for `ExpiryBehaviour.BLOCK_ACTIVE_USE_AFTER_VALUE_DATE`: reading `declared_expiry`
    unconditionally would treat every predicate's `expires_at` as a deadline, which is exactly what
    `completeness.py` warns against for a `never`-behaviour predicate. An absent catalog or an
    unknown predicate reads as `False` for the same reason `completeness.py` skips them there: an
    unresolvable predicate is `UNKNOWN_PREDICATE`'s finding to make, not this row's.
    """
    catalog = ctx.index.predicates
    if catalog is None:
        return False
    spec = catalog.by_id.get(fact.predicate)
    blocks_active_use = ExpiryBehaviour.BLOCK_ACTIVE_USE_AFTER_VALUE_DATE
    if spec is None or spec.expiry.behaviour is not blocks_active_use:
        return False
    declared = declared_expiry(fact)
    return declared is not None and declared[0] < as_of
