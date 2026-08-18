"""Stage 1 is JD-blind and total: it either emits a faithful pool or refuses.

The brief's own reference sample supplied seven of these tests near verbatim; three more are added
here because the interface has fields and an obligation (`shell_source` resolution against
`config_dir`) that sample never exercised: `no_match_fallback_ids`, the bundle/projection digest
trio, and a decoy planted at the WRONG resolution target to prove the RIGHT one is actually read.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import yaml

from boardwatch.profile_bundle.models.base import Surface, VerificationState
from boardwatch.profile_bundle.models.policy import SkillCategoryCatalog, SkillCategorySpec
from boardwatch.profile_bundle.models.skills import SkillRecord
from boardwatch.profile_bundle.storage import read_current_once
from boardwatch.projection.declaration import load_declaration, projection_digest
from boardwatch.projection.errors import ProjectionError, ProjectionIssue
from boardwatch.projection.pool import (
    _synthesized_skill_groups,
    project_pool,
    projection_candidate,
)
from boardwatch.projection.stamp import write_stamp
from boardwatch.tailor.model import SkillGroup
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
# Synthesizing `skill_groups` from the bundle when the declaration omits them (D-187): the
# owner's category taxonomy lives in ONE versioned place (`policy/skill-categories.yaml`),
# not restated unversioned in `projection.yaml`.
# --------------------------------------------------------------------------------------


def test_omitting_skill_groups_synthesizes_them_from_the_bundle_catalog(
    projection_env,  # noqa: F811
) -> None:
    """With no `skill_groups` block, the pool derives one group per category that has a
    résumé-surfaced skill — labelled by the category `display_name`, in the catalog's own order.
    The example bundle's `technique` category holds no skill, so it is omitted (no empty section);
    only `programming-language` (Example Language) survives."""
    raw = yaml.safe_load(projection_env.declaration.read_text(encoding="utf-8"))
    assert raw.pop("skill_groups", None) is not None, "fixture stopped declaring skill_groups"
    projection_env.declaration.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    # The digest moved with the edit, so the fixture's stamp no longer applies: re-approve the
    # skill_groups-free declaration against the same promoted bundle.
    digest = projection_digest(load_declaration(projection_env.declaration))
    bundle_digest = read_current_once(projection_env.bundle_root).bundle_digest
    write_stamp(
        projection_env.config_dir,
        digest=digest,
        bundle_digest=bundle_digest,
        approved_at=datetime(2026, 8, 13, 12, tzinfo=UTC),
    )

    pool = project_pool(
        projection_env.bundle_root,
        projection_env.declaration,
        config_dir=projection_env.config_dir,
        as_of=AS_OF,
    )
    assert pool.resume.skill_groups == [
        SkillGroup(label="Programming languages", items=["Example Language"])
    ]


def test_synthesis_follows_catalog_order_filters_non_resume_and_drops_empty_categories() -> None:
    """The ordering and inclusion rules, pinned where the one-skill example bundle cannot reach
    them: groups in catalog order (not alphabetical, not skill order), skills in inventory order,
    only résumé-surfaced skills, and a category with none omitted."""
    categories = SkillCategoryCatalog(
        catalog_version=1,
        career_field="example-field",
        categories=(
            SkillCategorySpec(category_id="tools", display_name="Tools", aliases=()),
            SkillCategorySpec(category_id="languages", display_name="Languages", aliases=()),
            SkillCategorySpec(category_id="empty-cat", display_name="Empty", aliases=()),
        ),
    )

    def skill(sid: str, name: str, cat: str, *surfaces: Surface) -> SkillRecord:
        return SkillRecord(
            skill_id=sid,
            canonical_name=name,
            category=cat,
            supporting_fact_ids=("fact.x.001",),
            verification_state=VerificationState.VERIFIED,
            allowed_surfaces=tuple(surfaces),
        )

    skills = (
        skill("skill.python", "Python", "languages", Surface.RESUME),
        skill("skill.aws", "AWS", "tools", Surface.RESUME),
        skill("skill.swift", "Swift", "languages", Surface.RESUME),
        skill("skill.secret", "Secret", "tools", Surface.PUBLIC),
    )

    groups = _synthesized_skill_groups(skills, categories)

    assert groups == [
        SkillGroup(label="Tools", items=["AWS"]),
        SkillGroup(label="Languages", items=["Python", "Swift"]),
    ]


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


def test_the_pool_carries_the_sort_flag_and_the_project_order(
    projection_env,  # noqa: F811
) -> None:
    """Both Stage-2 inputs the declaration owns, carried like `fill_to_page`. The example does not
    opt into sorting, and its one project makes the order a single-element tuple — the multi-project
    ordering rule is covered by `_order_projects_by_start`'s own test below."""
    pool = project_pool(
        projection_env.bundle_root,
        projection_env.declaration,
        config_dir=projection_env.config_dir,
        as_of=AS_OF,
    )
    assert pool.sort_projects_by_date is False
    assert pool.project_order == ("entry.project.packet-pantry",)


def test_the_project_start_key_reads_the_structured_start_not_the_display_string(
    projection_env,  # noqa: F811
    bundle_ctx,  # noqa: F811
) -> None:
    """The sort key is the STRUCTURED `year_month` value, never the rendered display string. The
    example project's effective start is `2025-04` (the owner_confirmed `.002`; `.001` is rejected),
    which the renderer would print as "Apr 2025 – Present" — the key must be the raw `2025-04`."""
    from boardwatch.projection.pool import _project_start_key

    decl = load_declaration(projection_env.declaration)
    project_decl = next(e for e in decl.entries if e.entity_id == "project.packet-pantry")
    key = _project_start_key(project_decl, ctx=bundle_ctx, as_of=AS_OF)
    assert key == "2025-04"


def test_order_projects_by_start_is_newest_first_with_no_start_as_most_recent() -> None:
    """The projects-only ordering rule, in isolation: dated projects descend by `YYYY-MM`, and a
    project with no structured start sorts as most recent, ahead of every dated one."""
    from boardwatch.projection.pool import _order_projects_by_start

    pairs = [
        ("entry.old", "2021-01"),
        ("entry.nostart", None),
        ("entry.present", "2024-03"),
        ("entry.mid", "2022-08"),
    ]
    assert _order_projects_by_start(pairs) == (
        "entry.nostart",  # no structured start ⇒ most recent, at the top
        "entry.present",  # 2024-03
        "entry.mid",  # 2022-08
        "entry.old",  # 2021-01
    )


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


# --------------------------------------------------------------------------------------
# Fact-derived bullets (Path 2, D-188): an entry declaring `bullet_predicates` renders the
# entity's résumé-surfaced facts of those predicates as bullets, so the accomplishment/
# contribution text the bundle already holds reaches the page without a ClaimRecord. Exercised
# through `projection_candidate`, which resolves entries with no approval stamp.
# --------------------------------------------------------------------------------------


def _write_declaration(path: Path, entries: list[dict]) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "projection_version": 1,
                "shell_source": "master_resume.yaml",
                "open_range_label": "Present",
                "entries": entries,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_bullet_predicates_render_entity_facts_in_predicate_then_index_order(
    projection_env,  # noqa: F811
    tmp_path: Path,
) -> None:
    """`employment.example-labs` carries one `employment.responsibility` and one
    `employment.accomplishment` fact, both résumé-surfaced. Declaring both predicates yields two
    bullets in predicate-declaration order, each bullet's id its fact id and its text the fact
    value verbatim — no ClaimRecord involved."""
    decl = tmp_path / "projection.yaml"
    _write_declaration(
        decl,
        [
            {
                "entity_id": "employment.example-labs",
                "kind": "experience",
                "pinned": True,
                "heading": "{@display_name}",
                "bullet_predicates": [
                    "employment.responsibility",
                    "employment.accomplishment",
                ],
            }
        ],
    )
    candidate = projection_candidate(projection_env.bundle_root, decl, as_of=AS_OF)

    (entry,) = candidate.entries
    assert [b.bullet_id for b in entry.bullets] == [
        "fact.example-labs.responsibility.001",
        "fact.example-labs.accomplishment.001",
    ]
    assert [b.text for b in entry.bullets] == [
        "Owned the ingestion service and its on-call rotation",
        "Reduced duplicate ingestion work by adding an idempotency key",
    ]
    assert all(b.tech_tags == [] for b in entry.bullets)


def test_a_bullet_predicate_the_entity_has_no_fact_for_is_refused(
    projection_env,  # noqa: F811
    tmp_path: Path,
) -> None:
    """A declared bullet predicate that resolves to zero résumé-surfaced facts is a typed refusal,
    not a silently bulletless entry — the projected document is Tier A's ground truth, so a
    mistyped predicate must fail loudly rather than drop the owner's accomplishments."""
    decl = tmp_path / "projection.yaml"
    _write_declaration(
        decl,
        [
            {
                "entity_id": "employment.example-labs",
                "kind": "experience",
                "pinned": True,
                "heading": "{@display_name}",
                "bullet_predicates": ["certification.expiry"],
            }
        ],
    )
    with pytest.raises(ProjectionError) as exc:
        projection_candidate(projection_env.bundle_root, decl, as_of=AS_OF)
    assert exc.value.violation.issue is ProjectionIssue.BULLET_PREDICATE_NO_FACTS


def test_a_skill_ref_bullet_predicate_is_refused_as_unrenderable(
    projection_env,  # noqa: F811
    tmp_path: Path,
) -> None:
    """`technology.used` carries a `skill_ref`, not a résumé line. Declaring it as a bullet
    predicate must be refused by the same value-kind gate that guards template rendering — a list
    or reference on a bullet line is authoring, not projection."""
    decl = tmp_path / "projection.yaml"
    _write_declaration(
        decl,
        [
            {
                "entity_id": "project.packet-pantry",
                "kind": "project",
                "pinned": False,
                "heading": "{@display_name}",
                "bullet_predicates": ["technology.used"],
            }
        ],
    )
    with pytest.raises(ProjectionError) as exc:
        projection_candidate(projection_env.bundle_root, decl, as_of=AS_OF)
    assert exc.value.violation.issue is ProjectionIssue.FACT_VALUE_KIND_NOT_ADMITTED


def test_a_declared_range_with_no_end_renders_the_open_label_end_to_end(
    projection_env,  # noqa: F811
    tmp_path: Path,
) -> None:
    """The capability the template form never had. `'{project.start_date} – {project.end_date}'`
    cannot express an ongoing project at all, because a missing end fact is a fatal unresolved
    placeholder — so before this, an open-ended project could only be rendered by hand-typing the
    word "Present" into the declaration, beside an `open_range_label` that then meant nothing."""
    decl = tmp_path / "projection.yaml"
    _write_declaration(
        decl,
        [
            {
                "entity_id": "project.packet-pantry",
                "kind": "project",
                "pinned": False,
                "heading": "{@display_name}",
                "dates": {"start": "project.start_date"},
                "claims": ["claim.packet-pantry.backend.001"],
            }
        ],
    )
    candidate = projection_candidate(projection_env.bundle_root, decl, as_of=AS_OF)

    (entry,) = candidate.entries
    # `start-date.001` (2025-01) is `rejected`; `.002` (2025-04) is the owner-confirmed one, so
    # this also proves the range reads the effective fact rather than the first one on file.
    assert entry.dates == "Apr 2025 – Present"


def test_a_named_range_end_with_no_fact_is_fatal_not_silently_open(
    projection_env,  # noqa: F811
    tmp_path: Path,
) -> None:
    """**The fabrication guard.** An OMITTED `end` is the owner declaring the range open; a NAMED
    `end` whose fact is missing is a broken declaration. Folding the second into the first would
    print "Present" over work that has finished — claiming ongoing employment on a live job
    application — so the absence of a fact must never be read as a declaration of openness."""
    decl = tmp_path / "projection.yaml"
    _write_declaration(
        decl,
        [
            {
                "entity_id": "project.packet-pantry",
                "kind": "project",
                "pinned": False,
                "heading": "{@display_name}",
                "dates": {"start": "project.start_date", "end": "certification.expiry"},
                "claims": ["claim.packet-pantry.backend.001"],
            }
        ],
    )
    with pytest.raises(ProjectionError) as exc:
        projection_candidate(projection_env.bundle_root, decl, as_of=AS_OF)
    assert exc.value.violation.issue is ProjectionIssue.UNRESOLVED_PLACEHOLDER
    assert "certification.expiry" in exc.value.violation.message


def test_a_bulletless_declaration_yields_an_entry_with_no_bullets(
    projection_env,  # noqa: F811
    tmp_path: Path,
) -> None:
    """D-221's third state, resolved: an entry that declares `bulletless` renders its heading,
    title and dates with an empty bullet list, and carries the declaration forward on the model so
    the render gate can tell this apart from an entry whose bullets failed to resolve. The
    neighbouring `BULLET_PREDICATE_NO_FACTS` test is the other half of the pair — a predicate that
    matches nothing is still fatal, because only a declaration can carry intent."""
    decl = tmp_path / "projection.yaml"
    _write_declaration(
        decl,
        [
            {
                "entity_id": "employment.example-labs",
                "kind": "experience",
                "pinned": True,
                "heading": "{@display_name}",
                "title": "{employment.title}",
                "bulletless": True,
            }
        ],
    )
    candidate = projection_candidate(projection_env.bundle_root, decl, as_of=AS_OF)

    (entry,) = candidate.entries
    assert entry.bullets == []
    assert entry.bulletless is True
    # The rest of the entry still resolves: a bulletless entry is a FULL entry minus its bullets,
    # which is the whole point — the timeline gap it covers is what puts it on the page.
    assert entry.heading == "Example Labs"
    assert entry.title == "Software Engineer"


def test_an_entry_that_declares_no_bullet_source_is_not_marked_bulletless(
    projection_env,  # noqa: F811
    tmp_path: Path,
) -> None:
    """The flag is set by the DECLARATION, never inferred from the resolved bullet list. An entry
    that simply names no `claims` and no `bullet_predicates` resolves to zero bullets today and
    keeps `bulletless` unset — so it is still refused downstream by `validate_slots` rather than
    quietly rendering as the declared third state."""
    decl = tmp_path / "projection.yaml"
    _write_declaration(
        decl,
        [
            {
                "entity_id": "employment.example-labs",
                "kind": "experience",
                "pinned": True,
                "heading": "{@display_name}",
            }
        ],
    )
    candidate = projection_candidate(projection_env.bundle_root, decl, as_of=AS_OF)

    (entry,) = candidate.entries
    assert entry.bullets == []
    assert entry.bulletless is None
