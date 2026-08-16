"""The promotion slice: imported candidates -> the renderable graph (design §6.8, D-182).

`extract` lands typed candidates; a record reaches `imported` on candidates alone. This module is
the one place those candidates become `FactRecord`s, the entities they attach to, and `SkillRecord`s
whose `skill_id` is a real reference (§6.4). It is deterministic, grounded, and owner-mediated:

- **Grounded.** An entity comes from an entry's metadata candidates; a fact's subject is that
  entity. A skill's binding to an entity is the one grounded signal a résumé carries — a bullet's
  authored `tech_tags` naming a skill item exactly. A skill no bullet tags has no entity to attach
  to and never becomes a `SkillRecord` (`technology.used` is illegal on `person`, so familiarity
  with no entity is unrepresentable as a fact; it stays a candidate).
- **Owner-mediated.** Every fact is born `unresolved` with `evidence_ids=()`. Nothing here
  fabricates an owner attestation or an approval — the architecture exists to prevent exactly that.
  A skill's
  `allowed_surfaces` is therefore `()`: it may render only once the owner confirms its supporting
  facts, which is the step that promotes and renders.

This module is import-wall pure (no `store`, no `tailor`): it takes already-parsed structures and
returns documents to write. The orchestration — reading the draft, re-enumerating the source to
recover `tech_tags`, and writing — is `authoring.promote_candidates`.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import PurePosixPath
from typing import TypeVar

from boardwatch.profile_bundle.models.base import (
    EntityKind,
    Surface,
    UsageContext,
    VerificationBasis,
    VerificationState,
)
from boardwatch.profile_bundle.models.documents import (
    DocumentModel,
    EmploymentFactsDocument,
    ProjectFactsDocument,
    SkillInventoryDocument,
)
from boardwatch.profile_bundle.models.entities import (
    EmploymentEntity,
    EmploymentStatus,
    ProjectEntity,
    ProjectStatus,
)
from boardwatch.profile_bundle.models.facts import (
    DateRangeValue,
    FactRecord,
    FactValue,
    ImportLineage,
    SkillRefValue,
    YearMonthValue,
)
from boardwatch.profile_bundle.models.imports import CandidateRecord
from boardwatch.profile_bundle.models.policy import (
    PredicateCatalog,
    PredicateSpec,
    SkillCategoryCatalog,
)
from boardwatch.profile_bundle.models.skills import SkillRecord

#: First legal member of each list is chosen, so a fact is always born with a legal, deterministic
#: value. `incidental` is last on purpose: a `technology.used` fact must be able to GROUND a skill
#: once the owner confirms it, and grounding refuses `incidental` (`effective.py`). Basis is
#: cosmetic at birth — an `unresolved` fact has no evidence contract (`semantic.py`) — but a legal
#: one keeps
#: the record forward-safe when the owner confirms it.
_USAGE_PREFERENCE: tuple[UsageContext, ...] = (
    UsageContext.PROFESSIONAL,
    UsageContext.ACADEMIC,
    UsageContext.PERSONAL_PROJECT,
    UsageContext.CONTRIBUTION,
    UsageContext.PUBLICATION,
    UsageContext.VOLUNTEER,
    UsageContext.INCIDENTAL,
)
_BASIS_PREFERENCE: tuple[VerificationBasis, ...] = (
    VerificationBasis.OWNER_ATTESTED,
    VerificationBasis.REPOSITORY_VERIFIED,
    VerificationBasis.PRIVATE_DOCUMENT_VERIFIED,
    VerificationBasis.PUBLIC_RECORD_VERIFIED,
    VerificationBasis.MEASURED,
    VerificationBasis.SECONDARY_ONLY,
    VerificationBasis.MULTIPLE_SOURCES,
)
#: Surfaces a promoted fact is allowed on, narrowed to a résumé's reach and always ⊆ legal_surfaces.
_PUBLISHED_SURFACES: frozenset[Surface] = frozenset({Surface.RESUME, Surface.PUBLIC})

_E = TypeVar("_E")

_ENTRY_METADATA = re.compile(r"^entries/(?P<entry>[^/]+)/metadata$")
_ENTRY_BULLET = re.compile(r"^entries/(?P<entry>[^/]+)/bullets/(?P<bullet>[^/]+)$")
_SKILL_ITEM = re.compile(r"^skill-groups/(?P<label>[^/]+)/(?P<index>[^/]+)$")


class PromotionError(ValueError):
    """A candidate set the deterministic promotion contract cannot represent (§6.8)."""


@dataclass(frozen=True)
class PromotionPlan:
    """The documents promotion would write, and the counts the operator reads."""

    documents: dict[PurePosixPath, DocumentModel]
    entity_count: int
    fact_count: int
    skill_count: int
    category_count: int


@dataclass(frozen=True)
class _EntryCandidate:
    """One imported candidate resolved against its record's locator."""

    candidate: CandidateRecord
    locator: str


def _slug(text: str) -> str:
    """A lowercase `[a-z0-9]`-plus-`-` token that is a legal ID tail and `CatalogTokenId`."""
    lowered = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if not lowered or not lowered[0].isalnum():
        raise PromotionError(f"cannot derive a slug from {text!r}")
    return lowered


def _chosen(preference: Sequence[_E], legal: Sequence[_E], *, what: str, at: str) -> _E:
    legal_set = set(legal)
    for candidate in preference:
        if candidate in legal_set:
            return candidate
    raise PromotionError(f"no legal {what} for {at}: catalog admits {sorted(map(str, legal))}")


def _surfaces(spec: PredicateSpec) -> tuple[Surface, ...]:
    published = tuple(sorted(set(spec.legal_surfaces) & _PUBLISHED_SURFACES, key=lambda s: s.value))
    if published:
        return published
    # An application-only predicate (surface_policy latches to {application}); keep it legal.
    return tuple(sorted(set(spec.legal_surfaces), key=lambda s: s.value))


def build_promotion(
    *,
    candidates: Sequence[CandidateRecord],
    locator_by_record: Mapping[str, str],
    tech_tags_by_bullet_locator: Mapping[str, Sequence[str]],
    catalog: PredicateCatalog,
    existing_categories: SkillCategoryCatalog,
    source_id: str,
    source_content_digest: str,
    as_of: date,
) -> PromotionPlan:
    """Turn one source's imported candidates into entities, facts, and grounded skills (§6.8)."""
    specs = catalog.by_id

    # Partition candidates by the shape of their record's locator.
    by_entry: dict[str, list[_EntryCandidate]] = defaultdict(list)
    skill_display_to_id: dict[str, str] = {}
    skill_id_to_display: dict[str, str] = {}
    skill_id_to_labels: dict[str, set[str]] = defaultdict(set)
    skill_id_to_displays: dict[str, set[str]] = defaultdict(set)
    for candidate in candidates:
        locator = locator_by_record.get(candidate.source_record_id)
        if locator is None:
            continue
        if (match := _ENTRY_METADATA.match(locator)) or (match := _ENTRY_BULLET.match(locator)):
            by_entry[match.group("entry")].append(_EntryCandidate(candidate, locator))
        elif (match := _SKILL_ITEM.match(locator)) and candidate.predicate == "technology.used":
            value = candidate.canonicalized_typed_value
            skill_id = value.skill_id  # type: ignore[union-attr]
            skill_display_to_id[candidate.original_display_value] = skill_id
            skill_id_to_display[skill_id] = candidate.original_display_value
            skill_id_to_labels[skill_id].add(_decode_label(match.group("label")))
            skill_id_to_displays[skill_id].add(candidate.original_display_value)
        # header/* and anything else is not promoted here (person facts need facts/identity.yaml).

    # Build each entry into an entity plus its metadata/bullet facts, and remember its kind so the
    # tech_tags pass can attach technology.used facts to the same entity.
    employment_docs: dict[PurePosixPath, EmploymentFactsDocument] = {}
    project_docs: dict[PurePosixPath, ProjectFactsDocument] = {}
    entity_facts: dict[str, list[FactRecord]] = {}
    entity_id_by_entry: dict[str, str] = {}
    entity_kind_by_entry: dict[str, EntityKind] = {}
    entry_by_entity_id: dict[str, str] = {}
    entity_count = 0

    for entry_id in sorted(by_entry):
        entry_candidates = by_entry[entry_id]
        kind = _entry_subject_kind(entry_candidates, specs, entry_id)
        entity_id = f"{kind.value}.{_slug(entry_id)}"
        # `_slug` is lossy (lowercases, folds punctuation) while entry ids are deduped only
        # case/punctuation-sensitively, so two distinct entries can slug to one entity_id and
        # collapse to a single document path -- silently dropping the first entity and its facts
        # (D-184 class, cf. D-202), while the entity count still reports both. Refuse, don't merge.
        if entity_id in entry_by_entity_id:
            raise PromotionError(
                f"entity id {entity_id!r} is derived from more than one entry "
                f"{sorted((entry_by_entity_id[entity_id], entry_id))!r}: the id slug is lossy, "
                "so these would silently merge into one entity. Rename the entries so their ids "
                "differ after slugging."
            )
        entry_by_entity_id[entity_id] = entry_id
        entity_id_by_entry[entry_id] = entity_id
        entity_kind_by_entry[entry_id] = kind

        facts = _entry_facts(
            entry_candidates,
            entity_id=entity_id,
            specs=specs,
            source_id=source_id,
            source_content_digest=source_content_digest,
            as_of=as_of,
        )
        entity_facts[entry_id] = facts
        entity_count += 1

    # Tech_tags: bind each skill a bullet names exactly to that bullet's entry entity.
    supporting_by_skill: dict[str, list[str]] = defaultdict(list)
    for entry_id in sorted(by_entry):
        entity_id = entity_id_by_entry[entry_id]
        seen: set[str] = set()
        for locator in sorted(tech_tags_by_bullet_locator):
            bullet_match = _ENTRY_BULLET.match(locator)
            if bullet_match is None or bullet_match.group("entry") != entry_id:
                continue
            for tag in tech_tags_by_bullet_locator[locator]:
                skill_id = skill_display_to_id.get(tag)
                if skill_id is None or skill_id in seen:
                    continue
                seen.add(skill_id)
                fact = _tech_fact(
                    entity_id=entity_id,
                    entry_id=entry_id,
                    skill_id=skill_id,
                    spec=specs["technology.used"],
                    locator=locator,
                    source_id=source_id,
                    source_content_digest=source_content_digest,
                    as_of=as_of,
                )
                entity_facts[entry_id].append(fact)
                supporting_by_skill[skill_id].append(fact.fact_id)

    # Both fact-id builders drop the entity KIND -- `_entry_facts` uses
    # `_slug(entity_id.split('.', 1)[1])` and `_tech_fact` uses `_slug(entry_id)` -- so two entries
    # of *different* kinds whose ids slug-collide get distinct `entity_id`s, clear the guard above,
    # and still collide here (`.tech.` is hardcoded, so the tech fact is the reachable arm; metadata
    # and bullet facts carry kind-specific predicate locals). Within one entry, `counters` keyed on
    # the raw predicate local while the id uses `_slug(local)` collides the same way. Neither merges
    # silently at this layer, but both escape UNTYPED: the duplicate reaches `UniqueSorted` on
    # `supporting_fact_ids` as a bare pydantic `ValidationError` that no `PromotionError` handler
    # catches, or surfaces later as `DUPLICATE_RECORD_ID` at `validate`. Refuse where the cause is
    # still nameable (D-205).
    subject_by_fact_id: dict[str, str] = {}
    for entry_id in sorted(by_entry):
        for fact in entity_facts[entry_id]:
            prior_subject = subject_by_fact_id.get(fact.fact_id)
            if prior_subject is not None:
                raise PromotionError(
                    f"fact id {fact.fact_id!r} is derived from more than one candidate (subjects "
                    f"{sorted({prior_subject, fact.subject_id})!r}): the id drops the entity kind "
                    "and slugs the predicate, so these facts would collide in one id namespace. "
                    "Rename the entries or predicates so their ids differ after slugging."
                )
            subject_by_fact_id[fact.fact_id] = fact.subject_id

    # Assemble entity documents now every fact (metadata, bullet, tech) is attached.
    fact_count = 0
    for entry_id in sorted(by_entry):
        entity_id = entity_id_by_entry[entry_id]
        kind = entity_kind_by_entry[entry_id]
        entity_facts_tuple = tuple(entity_facts[entry_id])
        fact_count += len(entity_facts_tuple)
        display_name = _display_name(by_entry[entry_id], kind)
        if kind is EntityKind.EMPLOYMENT:
            employment_entity = EmploymentEntity(
                entity_id=entity_id,
                entity_type="employment",
                display_name=display_name,
                created_at=as_of,
                reviewed_at=as_of,
                status=_employment_status(entity_facts_tuple),
            )
            # model_validate (not the kwarg __init__): the pydantic mypy plugin does not synthesise
            # `entity` for a FactBearingDocument subclass, and validate accepts the built models.
            employment_docs[_entity_path("experience", entity_id)] = (
                EmploymentFactsDocument.model_validate(
                    {"entity": employment_entity, "facts": entity_facts_tuple}
                )
            )
        else:
            project_entity = ProjectEntity(
                entity_id=entity_id,
                entity_type="project",
                display_name=display_name,
                created_at=as_of,
                reviewed_at=as_of,
                status=_project_status(entity_facts_tuple),
            )
            project_docs[_entity_path("projects", entity_id)] = ProjectFactsDocument.model_validate(
                {"entity": project_entity, "facts": entity_facts_tuple}
            )

    # Skills for every skill_id a tech_tag grounded, plus the categories they name.
    skills: list[SkillRecord] = []
    used_categories: dict[str, str] = {}
    for skill_id in sorted(supporting_by_skill):
        # `_derive_skill_id` is lossy on purpose (D-180): distinct items can share one id. A
        # grounded id built from more than one item would collapse to a single `SkillRecord`,
        # silently dropping the rest (D-184). Refuse rather than resolve it by last-write-wins.
        displays = skill_id_to_displays[skill_id]
        if len(displays) > 1:
            raise PromotionError(
                f"skill id {skill_id!r} is grounded by more than one skill item "
                f"{sorted(displays)!r}: the id slug is lossy (D-180), so these would silently "
                "merge into one skill. Rename or merge them in the source before promoting."
            )
        # One item under two groups is not a lossy id (D-202's guard keys on the display value, the
        # same string in both groups, so it cannot see this) and not a category collision (the two
        # labels are distinct). But `SkillRecord.category` is singular, so a bare last-write-wins
        # over an unsorted `candidates` would let arrival order pick the category. The owner picks.
        labels = skill_id_to_labels[skill_id]
        if len(labels) > 1:
            raise PromotionError(
                f"skill item {skill_id_to_display[skill_id]!r} ({skill_id}) is listed under more "
                f"than one skill group {sorted(labels)!r}: a skill has exactly one category, so "
                "one group would silently win by arrival order. List it under a single group."
            )
        (label,) = labels
        category_id = _slug(label)
        # `_slug` is lossy, but skill-group labels are deduped only case/punctuation-sensitively, so
        # two distinct labels can share a category id and silently merge into one category (D-184
        # class, cf. D-202). Refuse rather than let the last label win.
        prior_label = used_categories.get(category_id)
        if prior_label is not None and prior_label != label:
            raise PromotionError(
                f"category id {category_id!r} is derived from more than one skill-group label "
                f"{sorted((prior_label, label))!r}: the id slug is lossy, so these groups would "
                "silently merge into one category. Rename the groups so their ids differ after "
                "slugging."
            )
        used_categories[category_id] = label
        skills.append(
            SkillRecord(
                skill_id=skill_id,
                canonical_name=skill_id_to_display[skill_id],
                category=category_id,
                supporting_fact_ids=tuple(sorted(supporting_by_skill[skill_id])),
                verification_state=VerificationState.UNRESOLVED,
                allowed_surfaces=(),
            )
        )

    categories_doc, added = _merge_categories(existing_categories, used_categories)

    documents: dict[PurePosixPath, DocumentModel] = {}
    documents.update(employment_docs)
    documents.update(project_docs)
    documents[PurePosixPath("skills/inventory.yaml")] = SkillInventoryDocument(skills=tuple(skills))
    if added:
        documents[PurePosixPath("policy/skill-categories.yaml")] = categories_doc

    return PromotionPlan(
        documents=documents,
        entity_count=entity_count,
        fact_count=fact_count,
        skill_count=len(skills),
        category_count=added,
    )


def _decode_label(encoded: str) -> str:
    """A skill-group label as authored, from its percent-encoded locator segment."""
    from urllib.parse import unquote

    return unquote(encoded)


def _entity_path(directory: str, entity_id: str) -> PurePosixPath:
    return PurePosixPath("facts") / directory / f"{entity_id}.yaml"


def _entry_subject_kind(
    entry_candidates: Sequence[_EntryCandidate],
    specs: Mapping[str, PredicateSpec],
    entry_id: str,
) -> EntityKind:
    """The one entity kind every predicate in the entry admits (§6.2a's `entry_kind_model`).

    Derived from the catalog, not hard-coded: the intersection of the entry's candidates'
    `legal_subject_kinds` pins the entry to `employment` or `project`. This slice builds those two
    kinds; any other resolved kind is refused rather than silently dropped.
    """
    admitted: set[EntityKind] | None = None
    for entry in entry_candidates:
        spec = specs.get(entry.candidate.predicate)
        if spec is None:
            raise PromotionError(f"{entry.candidate.predicate} is not in the predicate catalog")
        kinds = set(spec.legal_subject_kinds)
        admitted = kinds if admitted is None else admitted & kinds
    if not admitted:
        raise PromotionError(f"{entry_id}: its candidates share no legal subject kind")
    buildable = admitted & {EntityKind.EMPLOYMENT, EntityKind.PROJECT}
    if len(buildable) != 1:
        raise PromotionError(
            f"{entry_id}: resolves to subject kinds {sorted(k.value for k in admitted)}, "
            "not exactly one of employment/project"
        )
    return next(iter(buildable))


def _entry_facts(
    entry_candidates: Sequence[_EntryCandidate],
    *,
    entity_id: str,
    specs: Mapping[str, PredicateSpec],
    source_id: str,
    source_content_digest: str,
    as_of: date,
) -> list[FactRecord]:
    facts: list[FactRecord] = []
    counters: dict[str, int] = defaultdict(int)
    ordered = sorted(entry_candidates, key=lambda entry: (entry.candidate.predicate, entry.locator))
    for entry in ordered:
        candidate = entry.candidate
        spec = specs[candidate.predicate]
        local = candidate.predicate.split(".")[-1]
        counters[local] += 1
        fact_id = f"fact.{_slug(entity_id.split('.', 1)[1])}.{_slug(local)}.{counters[local]:03d}"
        facts.append(
            _fact(
                fact_id=fact_id,
                subject_id=entity_id,
                predicate=candidate.predicate,
                value=candidate.canonicalized_typed_value,
                spec=spec,
                locator=entry.locator,
                source_id=source_id,
                source_content_digest=source_content_digest,
                as_of=as_of,
            )
        )
    return facts


def _tech_fact(
    *,
    entity_id: str,
    entry_id: str,
    skill_id: str,
    spec: PredicateSpec,
    locator: str,
    source_id: str,
    source_content_digest: str,
    as_of: date,
) -> FactRecord:
    skill_tail = skill_id.split(".", 1)[1]
    return _fact(
        fact_id=f"fact.{_slug(entry_id)}.tech.{_slug(skill_tail)}",
        subject_id=entity_id,
        predicate="technology.used",
        value=SkillRefValue(type="skill_ref", skill_id=skill_id),
        spec=spec,
        locator=locator,
        source_id=source_id,
        source_content_digest=source_content_digest,
        as_of=as_of,
    )


def _fact(
    *,
    fact_id: str,
    subject_id: str,
    predicate: str,
    value: FactValue,
    spec: PredicateSpec,
    locator: str,
    source_id: str,
    source_content_digest: str,
    as_of: date,
) -> FactRecord:
    """One fact born `unresolved` with no fabricated evidence (§6.8/D-182)."""
    return FactRecord(
        fact_id=fact_id,
        subject_id=subject_id,
        predicate=predicate,
        value=value,
        verification_state=VerificationState.UNRESOLVED,
        verification_basis=_chosen(
            _BASIS_PREFERENCE, spec.legal_verification_bases, what="basis", at=predicate
        ),
        usage_context=_chosen(
            _USAGE_PREFERENCE, spec.legal_usage_contexts, what="usage context", at=predicate
        ),
        evidence_ids=(),
        allowed_surfaces=_surfaces(spec),
        conflict_group_id=None,
        reviewed_at=as_of,
        expires_at=None,
        supersedes_fact_ids=(),
        import_lineage=ImportLineage(
            source_id=source_id,
            source_locator=locator,
            source_content_digest=source_content_digest,
        ),
        notes=None,
    )


def _display_name(entry_candidates: Sequence[_EntryCandidate], kind: EntityKind) -> str:
    naming = "project.name" if kind is EntityKind.PROJECT else "employment.organization"
    for entry in entry_candidates:
        if entry.candidate.predicate == naming:
            return entry.candidate.original_display_value
    # No naming candidate: fall back to any string display so the entity is still nameable.
    return entry_candidates[0].candidate.original_display_value


def _employment_status(facts: Sequence[FactRecord]) -> EmploymentStatus:
    for fact in facts:
        if fact.predicate == "employment.date_range" and isinstance(fact.value, DateRangeValue):
            return EmploymentStatus.ACTIVE if fact.value.end is None else EmploymentStatus.COMPLETED
    return EmploymentStatus.COMPLETED


def _project_status(facts: Sequence[FactRecord]) -> ProjectStatus:
    has_start = any(fact.predicate == "project.start_date" for fact in facts)
    has_end = any(
        fact.predicate == "project.end_date" and isinstance(fact.value, YearMonthValue)
        for fact in facts
    )
    if has_start and not has_end:
        return ProjectStatus.ACTIVE_DEVELOPMENT
    return ProjectStatus.COMPLETED


def _merge_categories(
    existing: SkillCategoryCatalog, used: Mapping[str, str]
) -> tuple[SkillCategoryCatalog, int]:
    """Add any category a promoted skill names that the catalog does not already define."""
    known = {spec.category_id for spec in existing.categories}
    new: list[dict[str, object]] = [
        {
            "category_id": category_id,
            "display_name": display_name,
            "parent_category_id": None,
            "aliases": [],
        }
        for category_id, display_name in sorted(used.items())
        if category_id not in known
    ]
    if not new:
        return existing, 0
    merged = SkillCategoryCatalog.model_validate(
        {
            "catalog_version": existing.catalog_version,
            "career_field": existing.career_field,
            "categories": [
                *(spec.model_dump(mode="json") for spec in existing.categories),
                *new,
            ],
        }
    )
    return merged, len(new)
