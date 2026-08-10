"""Canonical skill records (design §14).

A skill is a reusable capability whose authority is *derived* from entity-bound supporting facts —
it is deliberately not one of the eleven domain entities. Naming a skill in an old résumé, a
generic skills list, a course catalog, or a job description supports nothing.

Role-family tags are deliberately absent. They are selection policy, and selection policy belongs
to the deferred tailoring design; putting a `role_families` field here now would make the later
design a schema migration instead of a new file under `policy/`.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from boardwatch.profile_bundle.models.base import (
    CatalogTokenId,
    FactId,
    NonBlankStr,
    SkillId,
    StrictModel,
    Surface,
    UniqueSorted,
    VerificationState,
)


class SkillRecord(StrictModel):
    """One canonical capability.

    `category` is a key into the revision-owned `policy/skill-categories.yaml` catalog, never a
    code-defined software vocabulary: §10.4 makes categories field-dependent data so the mechanism
    fits a user whose career has nothing to do with software.

    `allowed_surfaces` must be a subset of the union of its eligible supporting facts' surfaces
    (§10.3). That is a graph invariant checked in semantic validation, because it needs the facts.
    """

    skill_id: SkillId
    canonical_name: NonBlankStr
    aliases: Annotated[tuple[NonBlankStr, ...], UniqueSorted] = ()
    category: CatalogTokenId
    supporting_fact_ids: Annotated[tuple[FactId, ...], UniqueSorted] = Field(min_length=1)
    verification_state: VerificationState
    allowed_surfaces: Annotated[tuple[Surface, ...], UniqueSorted]
