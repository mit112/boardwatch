"""The seven revision-owned catalogs' row shapes (design §10.4, §11, §12.2, §15).

Two properties matter more than the rest.

**No parser defaults.** §10.4: "Every serialized predicate entry repeats every column across both
tables" and "omitting any field from the actual YAML is invalid". A default would silently supply
the *most permissive* reading of a missing contract column, which is the opposite of fail-closed —
so every `PredicateSpec` field is probed by deletion.

**Design-level closures stay in code.** §20.4 calls the high-risk assertion-tag set "complete", and
§15 rejects `ga_release`/`in_production` by name. Those are not rows a bundle may add or demote,
so the catalog model refuses them rather than trusting the data.
"""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from boardwatch.profile_bundle.models.base import EntityKind
from boardwatch.profile_bundle.models.policy import (
    CLAIM_TYPE_OWNERS,
    HIGH_RISK_ASSERTION_TAGS,
    REJECTED_ASSERTION_TAG_ALIASES,
    AssertionTagCatalog,
    Cardinality,
    ExclusivitySpec,
    ExpiryBehaviour,
    OwnerAttestationAuthority,
    PredicateCatalog,
    PredicateSpec,
    RelationCatalog,
    SecretRule,
    SecretRuleset,
    SecretScanFlag,
    SkillCategoryCatalog,
    SourceCatalog,
    SourceKind,
    SourceSpec,
    SurfacePolicy,
    UnitCatalog,
)

# --------------------------------------------------------------------------------------
# predicates
# --------------------------------------------------------------------------------------

PREDICATE_COLUMNS = (
    "predicate_id",
    "catalog_version",
    "legal_subject_kinds",
    "legal_value_types",
    "legal_string_values",
    "cardinality",
    "exclusivity",
    "minimum_evidence",
    "legal_verification_bases",
    "owner_attestation_authority",
    "legal_surfaces",
    "surface_policy",
    "legal_usage_contexts",
    "expiry",
    "may_ground_skill",
)


def _predicate(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "predicate_id": "technology.used",
        "catalog_version": 1,
        "legal_subject_kinds": ["project", "employment"],
        "legal_value_types": ["skill_ref"],
        "legal_string_values": [],
        "cardinality": "many",
        "exclusivity": "none",
        "minimum_evidence": [
            {"classes": ["repository_artifact"]},
            {"classes": ["private_document"]},
            {"classes": ["owner_attestation"]},
        ],
        "legal_verification_bases": [
            "repository_verified",
            "private_document_verified",
            "owner_attested",
        ],
        "owner_attestation_authority": "owner_confirmed",
        "legal_surfaces": ["resume", "public", "application"],
        "surface_policy": "standard",
        "legal_usage_contexts": ["professional", "personal_project"],
        "expiry": {"behaviour": "never", "review_interval_days": None},
        "may_ground_skill": True,
    }
    payload.update(overrides)
    return payload


def test_predicate_spec_declares_exactly_the_design_columns() -> None:
    assert set(PredicateSpec.model_fields) == set(PREDICATE_COLUMNS)


def test_a_complete_predicate_row_parses() -> None:
    spec = PredicateSpec.model_validate(_predicate())
    assert spec.cardinality is Cardinality.MANY
    assert spec.exclusivity is ExclusivitySpec.NONE
    assert spec.surface_policy is SurfacePolicy.STANDARD
    assert spec.expiry.behaviour is ExpiryBehaviour.NEVER
    assert spec.expiry.review_interval_days is None
    assert spec.may_ground_skill is True


@pytest.mark.parametrize("column", PREDICATE_COLUMNS)
def test_omitting_any_contract_column_is_invalid(column: str) -> None:
    payload = _predicate()
    del payload[column]
    with pytest.raises(ValidationError):
        PredicateSpec.model_validate(payload)


def test_unknown_predicate_column_is_refused() -> None:
    with pytest.raises(ValidationError):
        PredicateSpec.model_validate(_predicate(role_family="backend"))


def test_none_is_an_explicit_exclusivity_rule_and_the_catalog_is_closed() -> None:
    assert {member.value for member in ExclusivitySpec} == {
        "none",
        "one_effective_value",
        "one_effective_set",
        "one_effective_range_ordered",
    }


def test_owner_attestation_authority_catalog_is_the_declared_three() -> None:
    assert {member.value for member in OwnerAttestationAuthority} == {
        "none",
        "verified",
        "owner_confirmed",
    }


def test_minimum_evidence_alternatives_may_carry_a_combination() -> None:
    spec = PredicateSpec.model_validate(
        _predicate(
            minimum_evidence=[{"classes": ["public_record", "private_document"]}],
            legal_verification_bases=[
                "public_record_verified",
                "private_document_verified",
            ],
        )
    )
    assert spec.minimum_evidence[0].classes == ("private_document", "public_record")


def test_every_legal_verification_basis_has_a_satisfiable_evidence_route() -> None:
    with pytest.raises(ValidationError):
        PredicateSpec.model_validate(
            _predicate(
                minimum_evidence=[{"classes": ["private_document"]}],
                legal_verification_bases=["public_record_verified"],
            )
        )


@pytest.mark.parametrize(
    "bad",
    [
        {"minimum_evidence": []},
        {"minimum_evidence": [{"classes": []}]},
        {"minimum_evidence": [{"classes": ["not_a_class"]}]},
        {"legal_subject_kinds": []},
        {"legal_value_types": []},
        {"legal_surfaces": []},
        {"legal_usage_contexts": []},
        {"legal_verification_bases": []},
        {"legal_subject_kinds": ["skill"]},
        {"legal_value_types": ["float"]},
        {"cardinality": "two"},
        {"exclusivity": "one effective value"},
        {"expiry": {"behaviour": "sometimes", "review_interval_days": None}},
        {"expiry": {"behaviour": "never"}},
        {"expiry": {"behaviour": "never", "review_interval_days": 0}},
        {"catalog_version": 0},
    ],
)
def test_out_of_catalog_or_empty_contract_values_are_refused(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PredicateSpec.model_validate(_predicate(**bad))


def test_legal_string_values_carry_the_designs_one_enumerated_value_cell() -> None:
    """`deployment.environment` is "string enum: development, staging, production" in §10.4."""
    spec = PredicateSpec.model_validate(
        _predicate(
            predicate_id="deployment.environment",
            legal_value_types=["string"],
            legal_string_values=["development", "staging", "production"],
            may_ground_skill=False,
        )
    )
    assert spec.legal_string_values == ("development", "staging", "production")


def test_string_enumeration_without_a_string_value_type_is_refused() -> None:
    with pytest.raises(ValidationError):
        PredicateSpec.model_validate(
            _predicate(legal_value_types=["integer"], legal_string_values=["production"])
        )


def test_application_only_policy_cannot_admit_resume_or_public() -> None:
    """§10.4 makes `application_only` a second latch, so a widened maximum must still fail."""
    with pytest.raises(ValidationError):
        PredicateSpec.model_validate(
            _predicate(surface_policy="application_only", legal_surfaces=["resume", "application"])
        )
    spec = PredicateSpec.model_validate(
        _predicate(surface_policy="application_only", legal_surfaces=["application"])
    )
    assert spec.legal_surfaces == ("application",)


def test_predicate_catalog_requires_entry_versions_to_match_the_document() -> None:
    with pytest.raises(ValidationError):
        PredicateCatalog.model_validate(
            {"predicates_version": 2, "predicates": [_predicate()]}
        )
    catalog = PredicateCatalog.model_validate(
        {"predicates_version": 1, "predicates": [_predicate()]}
    )
    assert catalog.by_id["technology.used"].may_ground_skill is True


def test_predicate_catalog_refuses_a_duplicate_predicate_id() -> None:
    with pytest.raises(ValidationError):
        PredicateCatalog.model_validate(
            {"predicates_version": 1, "predicates": [_predicate(), _predicate()]}
        )


# --------------------------------------------------------------------------------------
# units
# --------------------------------------------------------------------------------------

FIXTURE_UNITS = {
    "items": ("count",),
    "milliseconds": ("duration", "latency"),
    "items_per_second": ("rate", "throughput"),
    "percent": ("percentage",),
    "usd": ("currency",),
    "bytes": ("size",),
    "ordinal": ("rank",),
    "points": ("score",),
}


def _unit(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "unit_id": "items",
        "display_name": "items",
        "symbol": "items",
        "aliases": ["item"],
        "allowed_metric_kinds": ["count"],
    }
    payload.update(overrides)
    return payload


def test_unit_rows_have_exactly_the_five_declared_columns() -> None:
    from boardwatch.profile_bundle.models.policy import UnitSpec

    assert set(UnitSpec.model_fields) == {
        "unit_id",
        "display_name",
        "symbol",
        "aliases",
        "allowed_metric_kinds",
    }


def test_unit_catalog_parses_and_resolves_aliases() -> None:
    catalog = UnitCatalog.model_validate({"units_version": 1, "units": [_unit()]})
    assert catalog.by_token["item"].unit_id == "items"
    assert catalog.by_token["items"].unit_id == "items"


def test_unit_tokens_are_globally_unique_across_ids_and_aliases() -> None:
    with pytest.raises(ValidationError):
        UnitCatalog.model_validate(
            {
                "units_version": 1,
                "units": [_unit(), _unit(unit_id="pieces", aliases=["items"])],
            }
        )


@pytest.mark.parametrize(
    "bad",
    [
        {"allowed_metric_kinds": []},
        {"allowed_metric_kinds": ["velocity"]},
        {"unit_id": "Items"},
        {"unit_id": "items-per-second"},
        {"display_name": ""},
        {"symbol": "  "},
        {"aliases": ["item", "item"]},
    ],
)
def test_malformed_unit_rows_are_refused(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        UnitCatalog.model_validate({"units_version": 1, "units": [_unit(**bad)]})


def test_no_universal_unit_vocabulary_is_built_into_code() -> None:
    """§11: "Gate A ships no universal built-in unit vocabulary." An empty catalog must parse."""
    assert UnitCatalog.model_validate({"units_version": 1, "units": []}).units == ()


def test_the_declared_fixture_units_cover_every_metric_kind() -> None:
    from boardwatch.profile_bundle.models.metrics import MetricKind

    covered = {kind for kinds in FIXTURE_UNITS.values() for kind in kinds}
    assert covered == {member.value for member in MetricKind}


# --------------------------------------------------------------------------------------
# relations
# --------------------------------------------------------------------------------------


def test_relation_catalog_declares_typed_endpoints() -> None:
    catalog = RelationCatalog.model_validate(
        {
            "relations_version": 1,
            "relations": [
                {
                    "relation_type": "project_at_employment",
                    "legal_source_kinds": ["project"],
                    "legal_target_kinds": ["employment"],
                }
            ],
        }
    )
    spec = catalog.by_type["project_at_employment"]
    assert spec.legal_source_kinds == (EntityKind.PROJECT,)
    assert spec.legal_target_kinds == (EntityKind.EMPLOYMENT,)


def test_relation_catalog_refuses_empty_endpoint_sets_and_duplicates() -> None:
    row = {
        "relation_type": "project_at_employment",
        "legal_source_kinds": ["project"],
        "legal_target_kinds": ["employment"],
    }
    with pytest.raises(ValidationError):
        RelationCatalog.model_validate({"relations_version": 1, "relations": [row, row]})
    with pytest.raises(ValidationError):
        RelationCatalog.model_validate(
            {"relations_version": 1, "relations": [{**row, "legal_source_kinds": []}]}
        )


# --------------------------------------------------------------------------------------
# sources
# --------------------------------------------------------------------------------------


def test_source_kinds_are_the_closed_four() -> None:
    assert {member.value for member in SourceKind} == {
        "boardwatch_resume",
        "markdown_document",
        "structured_objects",
        "repository_markdown",
    }


def test_source_catalog_holds_only_portable_metadata() -> None:
    from boardwatch.profile_bundle.models.policy import SourceSpec

    assert set(SourceSpec.model_fields) == {"source_id", "source_kind", "portable_locator"}
    catalog = SourceCatalog.model_validate(
        {
            "sources_version": 1,
            "sources": [
                {
                    "source_id": "source.synthetic-notes",
                    "source_kind": "markdown_document",
                    "portable_locator": "notes/synthetic.md",
                }
            ],
        }
    )
    assert catalog.by_id["source.synthetic-notes"].source_kind is SourceKind.MARKDOWN_DOCUMENT


@pytest.mark.parametrize(
    "locator",
    [
        "/absolute/source.md",
        "../escape/source.md",
        "notes/../../escape.md",
        "./notes/source.md",
        "C:/machine/source.md",
        "C:\\machine\\source.md",
        "\\\\host\\share\\source.md",
        "notes\\source.md",
    ],
)
def test_a_portable_locator_that_is_not_a_relative_posix_path_is_refused(locator: str) -> None:
    """§6/§18: `portable_locator` is portable *because* it is relative.

    The absolute machine-local root lives only in the non-revisioned `local-sources.yaml`, and the
    portable locator is resolved beneath it. An absolute or traversing locator escapes that root
    entirely, so it is not a portability defect but a read outside the approved tree — and it
    survived structural, referential, semantic, and import validation because the field was only
    `NonBlankStr`. The refusal belongs at parse time, where every reader of the document gets it.
    """
    with pytest.raises(ValidationError):
        SourceSpec.model_validate(
            {
                "source_id": "source.synthetic-notes",
                "source_kind": "markdown_document",
                "portable_locator": locator,
            }
        )


def test_a_relative_posix_portable_locator_is_accepted() -> None:
    spec = SourceSpec.model_validate(
        {
            "source_id": "source.synthetic-notes",
            "source_kind": "markdown_document",
            "portable_locator": "notes/synthetic.md",
        }
    )
    assert spec.portable_locator == "notes/synthetic.md"


def test_source_catalog_does_not_repeat_ledger_owned_fields() -> None:
    """§18: the two documents may not repeat the same metadata fields."""
    from boardwatch.profile_bundle.models.policy import SourceSpec

    for ledger_owned in ("enumerator_id", "enumerator_version", "approved_scope",
                         "source_content_digest", "source_record_ids"):
        assert ledger_owned not in SourceSpec.model_fields


# --------------------------------------------------------------------------------------
# skill categories
# --------------------------------------------------------------------------------------


def _skill_categories(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "catalog_version": 1,
        "career_field": "example-field",
        "categories": [
            {
                "category_id": "language",
                "display_name": "Languages",
                "parent_category_id": None,
                "aliases": ["programming-language"],
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_skill_category_catalog_is_field_scoped_data() -> None:
    catalog = SkillCategoryCatalog.model_validate(_skill_categories())
    assert catalog.career_field == "example-field"
    assert catalog.by_id["language"].display_name == "Languages"


def test_parent_category_id_is_optional_per_the_design() -> None:
    catalog = SkillCategoryCatalog.model_validate(
        _skill_categories(
            categories=[{"category_id": "language", "display_name": "L", "aliases": []}]
        )
    )
    assert catalog.by_id["language"].parent_category_id is None


def test_parent_must_resolve_inside_the_catalog_and_cannot_cycle() -> None:
    with pytest.raises(ValidationError):
        SkillCategoryCatalog.model_validate(
            _skill_categories(
                categories=[
                    {
                        "category_id": "language",
                        "display_name": "L",
                        "parent_category_id": "absent",
                        "aliases": [],
                    }
                ]
            )
        )
    with pytest.raises(ValidationError):
        SkillCategoryCatalog.model_validate(
            _skill_categories(
                categories=[
                    {
                        "category_id": "a",
                        "display_name": "A",
                        "parent_category_id": "b",
                        "aliases": [],
                    },
                    {
                        "category_id": "b",
                        "display_name": "B",
                        "parent_category_id": "a",
                        "aliases": [],
                    },
                ]
            )
        )


def test_no_software_only_default_catalog_is_shipped_as_product_truth() -> None:
    """§10.4: the repository must not ship a software-only default catalog as universal truth."""
    assert SkillCategoryCatalog.model_validate(
        _skill_categories(career_field="clinical-nursing", categories=[])
    ).categories == ()


# --------------------------------------------------------------------------------------
# assertion tags
# --------------------------------------------------------------------------------------


def _tag(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "tag_id": "shipped",
        "high_risk": True,
        "legal_subject_kinds": ["project"],
        "authorization_any_of": [
            {
                "subject_statuses": [
                    "shipped_private",
                    "shipped_open_source",
                    "live_public",
                    "sunset",
                ],
                "required_fact_predicates": [],
                "required_fact_value": None,
                "require_same_subject_metric": False,
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_assertion_tag_rows_have_exactly_the_four_declared_columns() -> None:
    from boardwatch.profile_bundle.models.policy import AssertionTagSpec

    assert set(AssertionTagSpec.model_fields) == {
        "tag_id",
        "high_risk",
        "legal_subject_kinds",
        "authorization_any_of",
    }


def test_authorization_branch_has_exactly_the_four_declared_fields() -> None:
    from boardwatch.profile_bundle.models.policy import AssertionAuthorizationBranch

    assert set(AssertionAuthorizationBranch.model_fields) == {
        "subject_statuses",
        "required_fact_predicates",
        "required_fact_value",
        "require_same_subject_metric",
    }


def test_the_high_risk_set_is_exactly_the_designs_complete_set() -> None:
    assert HIGH_RISK_ASSERTION_TAGS == frozenset(
        {"shipped", "live", "production", "published", "granted", "awarded", "certified"}
    )


def test_a_high_risk_tag_cannot_be_demoted_by_catalog_data() -> None:
    with pytest.raises(ValidationError):
        AssertionTagCatalog.model_validate(
            {"assertion_tags_version": 1, "assertion_tags": [_tag(high_risk=False)]}
        )


def test_a_new_tag_cannot_promote_itself_to_high_risk() -> None:
    with pytest.raises(ValidationError):
        AssertionTagCatalog.model_validate(
            {
                "assertion_tags_version": 1,
                "assertion_tags": [_tag(tag_id="deployed", high_risk=True)],
            }
        )


@pytest.mark.parametrize("alias", sorted(REJECTED_ASSERTION_TAG_ALIASES))
def test_the_rejected_aliases_are_refused_by_name(alias: str) -> None:
    with pytest.raises(ValidationError):
        AssertionTagCatalog.model_validate(
            {"assertion_tags_version": 1, "assertion_tags": [_tag(tag_id=alias, high_risk=False)]}
        )


def test_an_unconstrained_authorization_branch_is_refused() -> None:
    """A branch with no constraint authorizes its tag about anything, `production` included."""
    with pytest.raises(ValidationError):
        AssertionTagCatalog.model_validate(
            {
                "assertion_tags_version": 1,
                "assertion_tags": [
                    _tag(
                        authorization_any_of=[
                            {
                                "subject_statuses": [],
                                "required_fact_predicates": [],
                                "required_fact_value": None,
                                "require_same_subject_metric": False,
                            }
                        ]
                    )
                ],
            }
        )


def test_a_tag_needs_at_least_one_branch() -> None:
    with pytest.raises(ValidationError):
        AssertionTagCatalog.model_validate(
            {"assertion_tags_version": 1, "assertion_tags": [_tag(authorization_any_of=[])]}
        )


def test_production_branch_encodes_its_required_value_structurally() -> None:
    catalog = AssertionTagCatalog.model_validate(
        {
            "assertion_tags_version": 1,
            "assertion_tags": [
                _tag(
                    tag_id="production",
                    high_risk=True,
                    authorization_any_of=[
                        {
                            "subject_statuses": [],
                            "required_fact_predicates": ["deployment.environment"],
                            "required_fact_value": {"type": "string", "value": "production"},
                            "require_same_subject_metric": False,
                        }
                    ],
                )
            ],
        }
    )
    branch = catalog.by_id["production"].authorization_any_of[0]
    assert branch.required_fact_value is not None
    assert branch.required_fact_value.value == "production"


def test_a_required_value_with_several_predicates_is_refused() -> None:
    with pytest.raises(ValidationError):
        AssertionTagCatalog.model_validate(
            {
                "assertion_tags_version": 1,
                "assertion_tags": [
                    _tag(
                        tag_id="production",
                        authorization_any_of=[
                            {
                                "subject_statuses": [],
                                "required_fact_predicates": [
                                    "deployment.environment",
                                    "project.contribution",
                                ],
                                "required_fact_value": {"type": "string", "value": "production"},
                                "require_same_subject_metric": False,
                            }
                        ],
                    )
                ],
            }
        )


def test_prose_authorization_strings_are_forbidden_by_shape() -> None:
    """§15: "The YAML rows encode those branches structurally; prose authorization strings are
    forbidden." A string where a branch object belongs must fail."""
    with pytest.raises(ValidationError):
        AssertionTagCatalog.model_validate(
            {
                "assertion_tags_version": 1,
                "assertion_tags": [
                    _tag(authorization_any_of=["subject status is shipped_open_source"])
                ],
            }
        )


# --------------------------------------------------------------------------------------
# secret scan document
# --------------------------------------------------------------------------------------


def test_the_secret_scan_document_is_the_ruleset_itself() -> None:
    from boardwatch.profile_bundle.models.policy import SecretScanDocument

    assert SecretScanDocument is SecretRuleset
    assert set(SecretRuleset.model_fields) == {"ruleset_version", "rules"}


def test_secret_rule_rows_have_exactly_the_three_declared_columns() -> None:
    assert set(SecretRule.model_fields) == {"rule_id", "pattern", "flags"}
    assert {member.value for member in SecretScanFlag} == {"ignore_case", "multiline"}


def test_an_uncompilable_pattern_is_refused_where_it_is_authored() -> None:
    with pytest.raises(ValidationError):
        SecretRule.model_validate({"rule_id": "broken", "pattern": "([unclosed", "flags": []})


def test_secret_rule_flags_are_closed_and_deduplicated_by_refusal() -> None:
    with pytest.raises(ValidationError):
        SecretRule.model_validate({"rule_id": "r", "pattern": "x", "flags": ["dotall"]})
    with pytest.raises(ValidationError):
        SecretRule.model_validate(
            {"rule_id": "r", "pattern": "x", "flags": ["ignore_case", "ignore_case"]}
        )


def test_secret_ruleset_refuses_a_duplicate_rule_id() -> None:
    row = {"rule_id": "r", "pattern": "x", "flags": []}
    with pytest.raises(ValidationError):
        SecretRuleset.model_validate({"ruleset_version": 1, "rules": [row, row]})


# --------------------------------------------------------------------------------------
# claim-type ownership
# --------------------------------------------------------------------------------------


def test_claim_type_owners_split_bullets_from_summaries() -> None:
    assert {tag.value for tag in CLAIM_TYPE_OWNERS["claims/bullet-candidates.yaml"]} == {
        "responsibility",
        "accomplishment",
        "project_summary",
    }
    assert {tag.value for tag in CLAIM_TYPE_OWNERS["claims/summary-candidates.yaml"]} == {
        "professional_summary"
    }


@pytest.mark.parametrize(
    "locator",
    [
        "notes/\x00escape.md",
        "notes/line\nbreak.md",
        "notes/tab\there.md",
        "notes/bell\x07.md",
        "notes/delete\x7f.md",
    ],
)
def test_a_portable_locator_carrying_a_control_character_is_refused(locator: str) -> None:
    """A NUL produces a structurally valid bundle whose source path cannot be opened at all.

    The earlier validator enumerated the spellings a reviewer had shown — absolute, traversing,
    drive-qualified, backslashed — rather than the character classes that break a path. `open()`
    raises `ValueError: embedded null byte` before any filesystem call, so the bundle validates
    clean through all four layers and fails at the one place with no diagnostic to give.
    """
    with pytest.raises(ValidationError):
        SourceSpec.model_validate(
            {
                "source_id": "source.synthetic-notes",
                "source_kind": "markdown_document",
                "portable_locator": locator,
            }
        )


PORTABLE_LOCATOR_CORPUS = [
    "notes/synthetic.md",
    "a.md",
    "deep/nested/path/source.md",
    "notes/caf\u00e9.md",
    "notes/Ship it \N{ROCKET}.md",
    "notes/100% done.md",
    "notes/dot.in.name.md",
    "notes/..hidden.md",
    "~/notes/source.md",
    "~mit/notes/source.md",
    "notes/~backup.md",
    "a//b",
    "notes/",
    "ab:c",
    "/absolute/source.md",
    "../escape/source.md",
    "notes/../escape.md",
    "./notes/source.md",
    "C:/machine/source.md",
    "c:source.md",
    "notes\\source.md",
    "\\\\host\\share\\source.md",
    "notes/\x00escape.md",
    "notes/line\nbreak.md",
    "notes/trailing.md\n",
    "   ",
    "",
    ".",
    "..",
]


def _model_accepts(locator: str) -> bool:
    try:
        SourceSpec.model_validate(
            {
                "source_id": "source.synthetic-notes",
                "source_kind": "markdown_document",
                "portable_locator": locator,
            }
        )
    except ValidationError:
        return False
    return True


@pytest.mark.parametrize("locator", PORTABLE_LOCATOR_CORPUS)
def test_the_exported_schemas_locator_pattern_agrees_with_the_model(locator: str) -> None:
    """A `field_validator` contributes nothing to the exported JSON Schema, so an authoring tool
    reading `career-profile.schema.json` accepted `../escape/source.md` while the model refused it.

    D-122 accepted that gap on the grounds that a single regex collapses four distinct refusals
    into one message. The third review overrode it: the schema is what every external authoring
    tool reads. Both now exist — the branches keep their diagnostics, the pattern lands in the
    schema — and this test is what stops the two from drifting apart.
    """
    from boardwatch.profile_bundle.models.policy import PORTABLE_LOCATOR_PATTERN

    constraint = re.compile(PORTABLE_LOCATOR_PATTERN)
    assert bool(constraint.search(locator)) is _model_accepts(locator), locator


@pytest.mark.parametrize("locator", ["~/notes/source.md", "~mit/notes/source.md", "~"])
def test_a_home_relative_portable_locator_is_refused(locator: str) -> None:
    """`SourceSpec`'s docstring has claimed since T12 that "validation rejects a home path inside
    it". D-122 recorded that both halves of that sentence were false and fixed only the first: the
    absolute-path branch does not see `~/notes/x.md`, which is relative. A documented guarantee
    that lands nowhere is the defect class this slice has now been reviewed for four times, so the
    sentence is made true rather than deleted — a leading `~` segment is the home path it names.
    """
    with pytest.raises(ValidationError):
        SourceSpec.model_validate(
            {
                "source_id": "source.synthetic-notes",
                "source_kind": "markdown_document",
                "portable_locator": locator,
            }
        )


def test_a_tilde_that_is_not_the_home_prefix_is_still_a_usable_filename() -> None:
    """The refusal is positional. `~` only means `$HOME` at the start of a path."""
    spec = SourceSpec.model_validate(
        {
            "source_id": "source.synthetic-notes",
            "source_kind": "markdown_document",
            "portable_locator": "notes/~backup.md",
        }
    )
    assert spec.portable_locator == "notes/~backup.md"
