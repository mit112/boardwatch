"""§7's lookup rows. Every arm fatal, every arm with its own failing case."""

from __future__ import annotations

import pytest

from boardwatch.projection.contract import check_references
from boardwatch.projection.errors import ProjectionError, ProjectionIssue
from tests.projection.conftest import (  # noqa: F401  (fixture re-export)
    bundle_ctx,
    context_over,
    materialised_bundle,
)


def _declaration(**overrides):  # type: ignore[no-untyped-def]
    """Built in code against real synthetic ids, so a bundle change breaks this loudly."""
    from boardwatch.projection.declaration import (
        EntryDeclaration,
        EntryKind,
        ProjectionDeclaration,
    )

    base = dict(
        projection_version=1,
        shell_source="master_resume.yaml",
        open_range_label="Present",
        entries=(
            EntryDeclaration(
                entity_id="project.packet-pantry",
                kind=EntryKind.PROJECT,
                pinned=True,
                heading="{@display_name}",
                claims=("claim.packet-pantry.backend.001",),
            ),
        ),
    )
    base.update(overrides)
    return ProjectionDeclaration.model_validate(base)


def test_the_real_synthetic_declaration_passes(bundle_ctx) -> None:  # noqa: F811
    """The positive control. Without it every refusal below could be a false positive."""
    check_references(_declaration(), bundle_ctx)


def test_an_unknown_entity_id_is_fatal(bundle_ctx) -> None:  # noqa: F811
    from boardwatch.projection.declaration import EntryDeclaration, EntryKind

    decl = _declaration(
        entries=(
            EntryDeclaration(
                entity_id="project.does-not-exist",
                kind=EntryKind.PROJECT,
                pinned=True,
                heading="x",
                claims=(),
            ),
        )
    )
    with pytest.raises(ProjectionError) as exc:
        check_references(decl, bundle_ctx)
    assert exc.value.violation.issue is ProjectionIssue.UNKNOWN_BUNDLE_ID


def test_an_unknown_claim_id_is_fatal(bundle_ctx) -> None:  # noqa: F811
    """A different lookup over different data than `test_an_unknown_entity_id_is_fatal`: the
    entity resolves, only the claim id does not."""
    from boardwatch.projection.declaration import EntryDeclaration, EntryKind

    decl = _declaration(
        entries=(
            EntryDeclaration(
                entity_id="project.packet-pantry",
                kind=EntryKind.PROJECT,
                pinned=True,
                heading="x",
                claims=("claim.does-not-exist",),
            ),
        )
    )
    with pytest.raises(ProjectionError) as exc:
        check_references(decl, bundle_ctx)
    assert exc.value.violation.issue is ProjectionIssue.UNKNOWN_BUNDLE_ID


#: Appended verbatim to `claims/bullet-candidates.yaml`'s list, in the file's own authoring style.
#: The packaged bundle's one non-conforming claim, `claim.packet-pantry.draft.001`, is
#: simultaneously `status: draft` AND `allowed_surfaces: []`, so a single fixture built from it can
#: never isolate which of the two checks below actually fired. These two are built to violate
#: exactly one condition each.
_CLAIM_DRAFT_BUT_RESUME_SURFACED = """
- claim_id: claim.packet-pantry.isolate-status.001
  subject_id: project.packet-pantry
  claim_type: accomplishment
  text: Drafted a monitoring dashboard for the ingestion path.
  required_fact_ids: []
  required_metric_ids: []
  metric_mentions: []
  status: draft
  allowed_surfaces:
  - resume
  assertion_tags: []
  reviewed_at: '2026-08-10'
"""

_CLAIM_APPROVED_BUT_NOT_RESUME_SURFACED = """
- claim_id: claim.packet-pantry.isolate-surface.001
  subject_id: project.packet-pantry
  claim_type: accomplishment
  text: Documented an internal runbook for the ingestion path.
  required_fact_ids: []
  required_metric_ids: []
  metric_mentions: []
  status: approved
  allowed_surfaces: []
  assertion_tags: []
  reviewed_at: '2026-08-10'
"""


def test_a_draft_but_resume_surfaced_claim_is_fatal(materialised_bundle) -> None:  # noqa: F811
    """Isolates `CLAIM_NOT_APPROVED`: this claim would pass the résumé-surfaced check and the
    subject-match check, so only the status check can be what raises."""
    from boardwatch.projection.declaration import EntryDeclaration, EntryKind

    materialised_bundle.write(
        "claims/bullet-candidates.yaml",
        materialised_bundle.read("claims/bullet-candidates.yaml") + _CLAIM_DRAFT_BUT_RESUME_SURFACED,
    )
    ctx = context_over(materialised_bundle)
    decl = _declaration(
        entries=(
            EntryDeclaration(
                entity_id="project.packet-pantry",
                kind=EntryKind.PROJECT,
                pinned=True,
                heading="x",
                claims=("claim.packet-pantry.isolate-status.001",),
            ),
        )
    )
    with pytest.raises(ProjectionError) as exc:
        check_references(decl, ctx)
    assert exc.value.violation.issue is ProjectionIssue.CLAIM_NOT_APPROVED


def test_an_approved_but_not_resume_surfaced_claim_is_fatal(materialised_bundle) -> None:  # noqa: F811
    """Isolates `CLAIM_NOT_RESUME_SURFACED`: this claim would pass the status check and the
    subject-match check, so only the surface check can be what raises."""
    from boardwatch.projection.declaration import EntryDeclaration, EntryKind

    materialised_bundle.write(
        "claims/bullet-candidates.yaml",
        materialised_bundle.read("claims/bullet-candidates.yaml")
        + _CLAIM_APPROVED_BUT_NOT_RESUME_SURFACED,
    )
    ctx = context_over(materialised_bundle)
    decl = _declaration(
        entries=(
            EntryDeclaration(
                entity_id="project.packet-pantry",
                kind=EntryKind.PROJECT,
                pinned=True,
                heading="x",
                claims=("claim.packet-pantry.isolate-surface.001",),
            ),
        )
    )
    with pytest.raises(ProjectionError) as exc:
        check_references(decl, ctx)
    assert exc.value.violation.issue is ProjectionIssue.CLAIM_NOT_RESUME_SURFACED


def test_a_claim_belonging_to_another_entity_is_fatal(bundle_ctx) -> None:  # noqa: F811
    """The row that closes revision 1's worst hole: an approved, résumé-surfaced claim about a
    DIFFERENT entity passed every other rule and would have printed one project's
    accomplishment under another employer."""
    from boardwatch.projection.declaration import EntryDeclaration, EntryKind

    decl = _declaration(
        entries=(
            EntryDeclaration(
                entity_id="employment.example-labs",
                kind=EntryKind.EXPERIENCE,
                pinned=True,
                heading="x",
                claims=("claim.packet-pantry.backend.001",),  # subject is the PROJECT
            ),
        )
    )
    with pytest.raises(ProjectionError) as exc:
        check_references(decl, bundle_ctx)
    assert exc.value.violation.issue is ProjectionIssue.CLAIM_SUBJECT_MISMATCH


def test_an_unknown_skill_id_is_fatal(bundle_ctx) -> None:  # noqa: F811
    from boardwatch.projection.declaration import SkillGroupDeclaration

    decl = _declaration(
        skill_groups=(SkillGroupDeclaration(label="Languages", skills=("skill.nope",)),)
    )
    with pytest.raises(ProjectionError) as exc:
        check_references(decl, bundle_ctx)
    assert exc.value.violation.issue is ProjectionIssue.UNKNOWN_BUNDLE_ID


#: Appended verbatim to `skills/inventory.yaml`'s list. The packaged bundle's one skill IS
#: résumé-surfaced, so there is no negative case to point at without injecting one.
_SKILL_VALID_BUT_NOT_RESUME_SURFACED = """
- skill_id: skill.internal-only-tool
  canonical_name: Internal Only Tool
  aliases: []
  category: technique
  supporting_fact_ids:
  - fact.packet-pantry.language.001
  verification_state: verified
  allowed_surfaces:
  - public
"""


def test_a_skill_that_is_valid_but_not_resume_surfaced_is_fatal(materialised_bundle) -> None:  # noqa: F811
    from boardwatch.projection.declaration import SkillGroupDeclaration

    materialised_bundle.write(
        "skills/inventory.yaml",
        materialised_bundle.read("skills/inventory.yaml") + _SKILL_VALID_BUT_NOT_RESUME_SURFACED,
    )
    ctx = context_over(materialised_bundle)
    decl = _declaration(
        skill_groups=(
            SkillGroupDeclaration(label="Tools", skills=("skill.internal-only-tool",)),
        )
    )
    with pytest.raises(ProjectionError) as exc:
        check_references(decl, ctx)
    assert exc.value.violation.issue is ProjectionIssue.SKILL_NOT_RESUME_SURFACED
