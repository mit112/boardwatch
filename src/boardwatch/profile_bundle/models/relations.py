"""Cross-entity relationships as explicit records (design §9).

A single-valued fact subject is never overloaded to express a relationship. "This project happened
at that employer" is a `project_at_employment` relation record, not a `project.employer` fact,
because a fact subject is one entity and a relationship is two.

Relations are internal knowledge records and carry **no** `allowed_surfaces` field in this phase.
Omitting the field rather than defaulting it to empty is deliberate: a future projection of a
relation needs its own policy design, and an empty-but-present set is the kind of thing a later
change widens without noticing.
"""

from __future__ import annotations

from boardwatch.profile_bundle.models.base import (
    CatalogTokenId,
    EntityId,
    RelationId,
    StrictModel,
)


class RelationRecord(StrictModel):
    """One typed edge between two entities.

    `relation_type` is a catalog key, not a code enum: §9 puts the relation catalog in
    `policy/relations.yaml` as versioned revision data, and the legal source/target entity kinds
    are declared there. Semantic validation checks this record against that catalog.
    """

    relation_id: RelationId
    relation_type: CatalogTokenId
    source_id: EntityId
    target_id: EntityId
