"""§7's fidelity contract. Every row is fatal; nothing degrades.

Refusing costs nothing — the authored `resume.yaml` still works and the daily driver is unaffected
— while emitting a partial document costs everything, because the projected document becomes Tier
A's ground truth. `output_is_entailed` compares the tailored résumé against the master, so a
fabrication introduced by PROJECTION is not caught downstream: it becomes the truth.
"""

from __future__ import annotations

from boardwatch.profile_bundle.models.base import Surface
from boardwatch.profile_bundle.models.claims import ClaimStatus
from boardwatch.profile_bundle.validation.context import ValidationContext
from boardwatch.projection.declaration import ProjectionDeclaration
from boardwatch.projection.errors import ProjectionIssue, raise_violation


def check_references(declaration: ProjectionDeclaration, ctx: ValidationContext) -> None:
    """Every id resolves, every claim is the owner's and this entity's, every skill may surface.

    The fact résumé-surfaced row is deliberately NOT here: `EntryDeclaration` has no fact-id
    field for this module to check against. It is enforced later, in `resume_facts_for` (a later
    task), which reads the bundle's facts directly rather than through this declaration.
    """
    claims = {c.claim_id: c for c in ctx.index.claims}
    skills = {s.skill_id: s for s in ctx.index.skills}

    for group in declaration.skill_groups:
        for skill_id in group.skills:
            skill = skills.get(skill_id)
            if skill is None:
                raise_violation(
                    ProjectionIssue.UNKNOWN_BUNDLE_ID,
                    f"no skill {skill_id!r} in the bundle",
                    where=f"skill_groups: {group.label}",
                )
            if Surface.RESUME not in skill.allowed_surfaces:
                raise_violation(
                    ProjectionIssue.SKILL_NOT_RESUME_SURFACED,
                    f"{skill_id!r} is valid but not résumé-surfaced",
                    where=f"skill_groups: {group.label}",
                )

    for entry in declaration.entries:
        where = f"entries: {entry.entity_id}"
        if entry.entity_id not in ctx.index.entities:
            raise_violation(
                ProjectionIssue.UNKNOWN_BUNDLE_ID,
                f"no entity {entry.entity_id!r} in the bundle",
                where=where,
            )
        for claim_id in entry.claims:
            claim = claims.get(claim_id)
            if claim is None:
                raise_violation(
                    ProjectionIssue.UNKNOWN_BUNDLE_ID,
                    f"no claim {claim_id!r} in the bundle",
                    where=where,
                )
            if claim.status is not ClaimStatus.APPROVED:
                raise_violation(
                    ProjectionIssue.CLAIM_NOT_APPROVED,
                    f"{claim_id!r} is {claim.status.value!r}, not approved",
                    where=where,
                )
            if Surface.RESUME not in claim.allowed_surfaces:
                raise_violation(
                    ProjectionIssue.CLAIM_NOT_RESUME_SURFACED,
                    f"{claim_id!r} is approved but not résumé-surfaced",
                    where=where,
                )
            if claim.subject_id != entry.entity_id:
                raise_violation(
                    ProjectionIssue.CLAIM_SUBJECT_MISMATCH,
                    f"{claim_id!r} is about {claim.subject_id!r}, so printing it here would "
                    f"attribute one entity's accomplishment to {entry.entity_id!r}",
                    where=where,
                )
