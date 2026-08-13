"""§7's lookup rows. Every arm fatal, every arm with its own failing case."""

from __future__ import annotations

import pytest

from boardwatch.projection.contract import check_references
from boardwatch.projection.errors import ProjectionError, ProjectionIssue
from tests.projection.conftest import bundle_ctx  # noqa: F401  (fixture re-export)


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


def test_a_draft_claim_is_fatal(bundle_ctx) -> None:  # noqa: F811
    """`claim.packet-pantry.draft.001` really is `status: draft` with `allowed_surfaces: []`."""
    from boardwatch.projection.declaration import EntryDeclaration, EntryKind

    decl = _declaration(
        entries=(
            EntryDeclaration(
                entity_id="project.packet-pantry",
                kind=EntryKind.PROJECT,
                pinned=True,
                heading="x",
                claims=("claim.packet-pantry.draft.001",),
            ),
        )
    )
    with pytest.raises(ProjectionError) as exc:
        check_references(decl, bundle_ctx)
    assert exc.value.violation.issue in {
        ProjectionIssue.CLAIM_NOT_APPROVED,
        ProjectionIssue.CLAIM_NOT_RESUME_SURFACED,
    }


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
