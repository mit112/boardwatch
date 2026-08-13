"""Stage 1 is JD-blind and total: it either emits a faithful pool or refuses.

The brief's own reference sample supplied seven of these tests near verbatim; three more are added
here because the interface has fields and an obligation (`shell_source` resolution against
`config_dir`) that sample never exercised: `no_match_fallback_ids`, the bundle/projection digest
trio, and a decoy planted at the WRONG resolution target to prove the RIGHT one is actually read.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from boardwatch.projection.declaration import load_declaration, projection_digest
from boardwatch.projection.errors import ProjectionError, ProjectionIssue
from boardwatch.projection.pool import project_pool
from tests.projection.conftest import bundle_ctx  # noqa: F401  (fixture re-export)

AS_OF = date(2026, 8, 13)


def test_the_pool_separates_pinned_from_candidates(projection_env) -> None:  # noqa: F811
    pool = project_pool(
        projection_env.bundle_root,
        projection_env.declaration,
        config_dir=projection_env.config_dir,
        as_of=AS_OF,
    )
    assert pool.pinned_entry_ids == ("entry.employment.example-labs",)
    assert pool.candidate_entry_ids == ("entry.project.packet-pantry",)
    assert set(pool.pinned_entry_ids) & set(pool.candidate_entry_ids) == set()


def test_every_bullet_is_its_claim_text_byte_for_byte(
    projection_env,  # noqa: F811
    bundle_ctx,  # noqa: F811
) -> None:
    """Bullet text is copied, never templated, edited or reflowed. Derived from the bundle at
    run time so a claim edit cannot silently diverge."""
    pool = project_pool(
        projection_env.bundle_root,
        projection_env.declaration,
        config_dir=projection_env.config_dir,
        as_of=AS_OF,
    )
    by_id = {c.claim_id: c.text for c in bundle_ctx.index.claims}
    seen = 0
    for entry in pool.resume.entries:
        for bullet in entry.bullets:
            assert bullet.text == by_id[bullet.bullet_id]
            seen += 1
    assert seen >= 2, "the derivation found nothing; the fixture stopped exercising bullets"


def test_tech_tags_are_emitted_empty(projection_env) -> None:  # noqa: F811
    """A deliberate lineage decision, not a no-op: `reports/tailor.py:433` hashes the model, so
    an empty `tech_tags` changes the master hash."""
    pool = project_pool(
        projection_env.bundle_root,
        projection_env.declaration,
        config_dir=projection_env.config_dir,
        as_of=AS_OF,
    )
    assert all(b.tech_tags == [] for e in pool.resume.entries for b in e.bullets)


def test_the_persona_title_is_left_unset(projection_env) -> None:  # noqa: F811
    """`tailor` owns persona shaping. Stage 1 setting `title` would fight it."""
    pool = project_pool(
        projection_env.bundle_root,
        projection_env.declaration,
        config_dir=projection_env.config_dir,
        as_of=AS_OF,
    )
    assert pool.resume.title is None


def test_the_projected_document_loads_through_the_production_loader(
    projection_env,  # noqa: F811
    tmp_path: Path,
) -> None:
    from boardwatch.projection.serialize import resume_document_bytes
    from boardwatch.tailor.load import load_resume

    pool = project_pool(
        projection_env.bundle_root,
        projection_env.declaration,
        config_dir=projection_env.config_dir,
        as_of=AS_OF,
    )
    path = tmp_path / "projected.yaml"
    path.write_bytes(resume_document_bytes(pool.resume))
    assert load_resume(path) == pool.resume


def test_a_missing_approval_stamp_refuses_to_emit(projection_env_unapproved) -> None:  # noqa: F811
    """The template hole's mechanical gate: no literal reaches a résumé unapproved."""
    with pytest.raises(ProjectionError) as exc:
        project_pool(
            projection_env_unapproved.bundle_root,
            projection_env_unapproved.declaration,
            config_dir=projection_env_unapproved.config_dir,
            as_of=AS_OF,
        )
    assert exc.value.violation.issue is ProjectionIssue.MISSING_PROJECTION_APPROVAL


def test_an_unpromoted_bundle_is_wrapped_as_a_typed_refusal(
    projection_env_unpromoted_bundle,  # noqa: F811
) -> None:
    """`bundle_root` here was never promoted (no `CURRENT` pointer at all), so
    `read_current_once` raises `profile_bundle.storage.SelectionError` for real. `project_pool`
    must not let that different exception hierarchy escape uniform `ProjectionError` handling."""
    with pytest.raises(ProjectionError) as exc:
        project_pool(
            projection_env_unpromoted_bundle.bundle_root,
            projection_env_unpromoted_bundle.declaration,
            config_dir=projection_env_unpromoted_bundle.config_dir,
            as_of=AS_OF,
        )
    assert exc.value.violation.issue is ProjectionIssue.BUNDLE_UNREADABLE


def test_editing_a_template_literal_reopens_the_gate(projection_env) -> None:  # noqa: F811
    """Approved, then edited: the digest moves and the old stamp no longer matches."""
    text = projection_env.declaration.read_text(encoding="utf-8")
    projection_env.declaration.write_text(
        text.replace("{@display_name}", "Senior {@display_name}"), encoding="utf-8"
    )
    with pytest.raises(ProjectionError) as exc:
        project_pool(
            projection_env.bundle_root,
            projection_env.declaration,
            config_dir=projection_env.config_dir,
            as_of=AS_OF,
        )
    assert exc.value.violation.issue is ProjectionIssue.MISSING_PROJECTION_APPROVAL


# --------------------------------------------------------------------------------------
# Not in the brief's reference sample: interface surface and the obligation it never exercised.
# --------------------------------------------------------------------------------------


def test_the_no_match_fallback_ids_are_derived_and_prefixed(projection_env) -> None:  # noqa: F811
    """`no_match_fallback_ids` is untouched by every test above. Derived at run time from the
    same declaration the pinned/candidate split reads, so a fixture edit cannot silently
    diverge from what the assertion expects."""
    declaration = load_declaration(projection_env.declaration)
    expected = tuple("entry." + entity_id for entity_id in declaration.no_match_fallback)
    assert expected, "the derivation found nothing; the fixture stopped declaring a fallback"

    pool = project_pool(
        projection_env.bundle_root,
        projection_env.declaration,
        config_dir=projection_env.config_dir,
        as_of=AS_OF,
    )
    assert pool.no_match_fallback_ids == expected
    assert set(pool.no_match_fallback_ids) <= set(pool.candidate_entry_ids)


def test_the_pool_carries_the_bundles_revision_digest_and_projection_digest(
    projection_env,  # noqa: F811
) -> None:
    """The three identity fields `ProjectionPool` adds beyond a bare `Resume`. None of the
    sample tests above touch them, so an empty or wrong value here would read as a pass
    everywhere else."""
    expected_digest = projection_digest(load_declaration(projection_env.declaration))

    pool = project_pool(
        projection_env.bundle_root,
        projection_env.declaration,
        config_dir=projection_env.config_dir,
        as_of=AS_OF,
    )
    assert pool.bundle_revision == "1"
    assert pool.bundle_digest.startswith("sha256:")
    assert pool.projection_digest == expected_digest


def test_the_shell_source_resolves_against_config_dir_not_the_bundle_root(
    projection_env,  # noqa: F811
) -> None:
    """`shell_source` (`master_resume.yaml`) is declared RELATIVE. A decoy, invalid shell at the
    same relative name under `bundle_root` proves resolution targets `config_dir` specifically:
    if `project_pool` ever joined against the wrong base, it would read the decoy instead and
    either raise `SHELL_SOURCE_UNREADABLE` (this decoy has no email) or silently swap the shell,
    not merely fail on a missing file."""
    decoy = projection_env.bundle_root / "master_resume.yaml"
    decoy.write_text("header:\n  - No Email Here\neducation:\n  - Nowhere\n", encoding="utf-8")

    pool = project_pool(
        projection_env.bundle_root,
        projection_env.declaration,
        config_dir=projection_env.config_dir,
        as_of=AS_OF,
    )
    assert pool.resume.header == ["Example Candidate", "candidate@example.com"]
    assert pool.resume.education == ["Example University"]
