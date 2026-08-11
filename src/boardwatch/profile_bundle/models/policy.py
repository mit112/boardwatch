"""The seven revision-owned versioned catalogs under `policy/` (design §10.4, §11, §12.2, §15).

Everything here is *data in the revision*, not code. That is the multi-tenancy requirement made
structural: skill categories are field-dependent, units are field-dependent, and a repository that
shipped a software-only vocabulary as universal product truth would only fit one kind of user.

Code owns three things about these catalogs and nothing else:

1. the **row shape** — so an entry cannot omit a contract column and inherit a parser default;
2. the closed **code-defined enums** a row draws on (metric kinds, entity kinds, surfaces …), which
   is why changing one of them bumps `schema_version` while adding a catalog ROW does not;
3. two **closure facts the design states as complete**: the high-risk assertion-tag set (§20.4
   calls it "the complete high-risk set") and the built-in v1 secret-scan rules (§12.2 says the
   implementation ships that exact catalog).

Design §10.4 is emphatic that "every serialized predicate entry repeats every column" and
"omitting any field from the actual YAML is invalid", so no field in `PredicateSpec` has a default.
`none` is an explicit exclusivity rule and `never; null` is an explicit expiry, not an absence.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from enum import StrEnum
from typing import Annotated, Final

from pydantic import Field, PositiveInt, field_validator, model_validator

from boardwatch.profile_bundle.models.base import (
    CatalogTokenId,
    EntityKind,
    LowerSlug,
    LowerToken,
    NonBlankStr,
    PredicateId,
    SourceId,
    StrictModel,
    Surface,
    UniqueOrdered,
    UniqueSorted,
    UsageContext,
    VerificationBasis,
)
from boardwatch.profile_bundle.models.claims import ClaimType
from boardwatch.profile_bundle.models.evidence import BASIS_EVIDENCE_CLASSES, EvidenceClass
from boardwatch.profile_bundle.models.facts import FactValue, FactValueKind
from boardwatch.profile_bundle.models.metrics import MetricKind

# ======================================================================================
# policy/predicates.yaml
# ======================================================================================


class Cardinality(StrEnum):
    """How many EFFECTIVE facts a subject may carry for this predicate (§10.4)."""

    ONE = "one"
    MANY = "many"


class ExclusivitySpec(StrEnum):
    """The closed exclusivity rules the design's catalog actually uses (§10.4).

    `NONE` is an explicit rule rather than an omission. `ONE_EFFECTIVE_RANGE_ORDERED` carries both
    halves of the design's "one effective range; start <= end" cell, because splitting them would
    let a row ask for the ordering without the uniqueness or the reverse.
    """

    NONE = "none"
    ONE_EFFECTIVE_VALUE = "one_effective_value"
    ONE_EFFECTIVE_SET = "one_effective_set"
    ONE_EFFECTIVE_RANGE_ORDERED = "one_effective_range_ordered"


class OwnerAttestationAuthority(StrEnum):
    """What state, if any, owner attestation alone may establish (§10.4).

    Every initial predicate that admits owner attestation uses `owner_confirmed`, never `verified`.
    `VERIFIED` exists because the design declares the catalog as
    `none | verified | owner_confirmed`; a test asserts no shipped row uses it.
    """

    NONE = "none"
    VERIFIED = "verified"
    OWNER_CONFIRMED = "owner_confirmed"


class SurfacePolicy(StrEnum):
    """`application_only` forbids `resume` and `public` even if a future catalog edit accidentally
    widens `legal_surfaces` (§10.4). It is a second, independent latch on the same door."""

    STANDARD = "standard"
    APPLICATION_ONLY = "application_only"


class ExpiryBehaviour(StrEnum):
    NEVER = "never"
    BLOCK_ACTIVE_USE_AFTER_VALUE_DATE = "block_active_use_after_value_date"


class ExpirySpec(StrictModel):
    """The design's "Expiry; review" cell, both halves explicit.

    `review_interval_days: null` is the design's `null` review column — no fixed interval — and is
    a required key so "we decided there is no interval" appears in the diff.
    """

    behaviour: ExpiryBehaviour
    review_interval_days: PositiveInt | None


class EvidenceAlternative(StrictModel):
    """One independently sufficient way to meet a predicate's minimum evidence standard.

    §10.4: "Each listed minimum evidence class is independently sufficient unless the entry lists a
    combination." An alternative is therefore a set of classes that must ALL be present, and a
    predicate lists one alternative per acceptable route.
    """

    classes: Annotated[tuple[EvidenceClass, ...], UniqueSorted] = Field(min_length=1)


class PredicateSpec(StrictModel):
    """One predicate contract (§10.1, §10.4). No field has a parser default.

    `legal_string_values` carries the design's one enumerated value cell:
    `deployment.environment`'s value type is "string enum: development, staging, production".
    Representing it as data is what makes that enum enforceable instead of decorative — §21 lists
    an unknown enum as a hard failure, and §15's `production` tag authorization requires the value
    to be exactly `production`. An empty tuple means "unconstrained beyond the value type", and
    every row must state it explicitly.
    """

    predicate_id: PredicateId
    catalog_version: PositiveInt
    legal_subject_kinds: Annotated[tuple[EntityKind, ...], UniqueSorted] = Field(min_length=1)
    legal_value_types: Annotated[tuple[FactValueKind, ...], UniqueSorted] = Field(min_length=1)
    legal_string_values: Annotated[tuple[NonBlankStr, ...], UniqueOrdered]
    cardinality: Cardinality
    exclusivity: ExclusivitySpec
    minimum_evidence: tuple[EvidenceAlternative, ...] = Field(min_length=1)
    legal_verification_bases: Annotated[tuple[VerificationBasis, ...], UniqueSorted] = Field(
        min_length=1
    )
    owner_attestation_authority: OwnerAttestationAuthority
    legal_surfaces: Annotated[tuple[Surface, ...], UniqueSorted] = Field(min_length=1)
    surface_policy: SurfacePolicy
    legal_usage_contexts: Annotated[tuple[UsageContext, ...], UniqueSorted] = Field(min_length=1)
    expiry: ExpirySpec
    may_ground_skill: bool

    @model_validator(mode="after")
    def _string_values_need_a_string_type(self) -> PredicateSpec:
        if self.legal_string_values and FactValueKind.STRING not in self.legal_value_types:
            raise ValueError(
                f"{self.predicate_id}: legal_string_values is set but `string` is not a legal "
                "value type, so the enumeration could never apply"
            )
        return self

    @model_validator(mode="after")
    def _verification_bases_need_evidence_routes(self) -> PredicateSpec:
        for basis in self.legal_verification_bases:
            corresponding = BASIS_EVIDENCE_CLASSES[basis.value]
            if any(
                not corresponding.isdisjoint(alternative.classes)
                for alternative in self.minimum_evidence
            ):
                continue
            raise ValueError(
                f"{self.predicate_id}: legal verification basis {basis.value!r} has no "
                "minimum_evidence alternative containing a corresponding evidence class"
            )
        return self

    @model_validator(mode="after")
    def _application_only_forbids_public_surfaces(self) -> PredicateSpec:
        if self.surface_policy is SurfacePolicy.APPLICATION_ONLY:
            leaked = set(self.legal_surfaces) - {Surface.APPLICATION}
            if leaked:
                raise ValueError(
                    f"{self.predicate_id}: surface_policy is application_only but legal_surfaces "
                    f"admits {sorted(surface.value for surface in leaked)}"
                )
        return self


class PredicateCatalog(StrictModel):
    """`policy/predicates.yaml`.

    The document version and every entry's `catalog_version` must agree: §10.1 puts the version on
    the entry, and the manifest carries `predicate_catalog_version`. Three copies of one number is
    only safe if disagreement is an error, so it is.
    """

    predicates_version: PositiveInt
    predicates: tuple[PredicateSpec, ...]

    @model_validator(mode="after")
    def _entry_versions_match_the_document(self) -> PredicateCatalog:
        for spec in self.predicates:
            if spec.catalog_version != self.predicates_version:
                raise ValueError(
                    f"{spec.predicate_id}: catalog_version {spec.catalog_version} disagrees with "
                    f"predicates_version {self.predicates_version}"
                )
        _refuse_duplicate_keys(
            (spec.predicate_id for spec in self.predicates), "predicate_id", "policy/predicates"
        )
        return self

    @property
    def by_id(self) -> dict[str, PredicateSpec]:
        return {spec.predicate_id: spec for spec in self.predicates}


# ======================================================================================
# policy/units.yaml
# ======================================================================================


class UnitSpec(StrictModel):
    """Exactly the five columns §11 declares. Nothing else is a unit's business.

    The catalog defines no conversions, implicit aliases, or dimensional inference: validation does
    exact ID/alias lookup only, so `120 ms` can never be silently compared with `0.12 s`.
    """

    unit_id: LowerToken
    display_name: NonBlankStr
    symbol: NonBlankStr
    aliases: Annotated[tuple[LowerToken, ...], UniqueSorted]
    allowed_metric_kinds: Annotated[tuple[MetricKind, ...], UniqueSorted] = Field(min_length=1)


class UnitCatalog(StrictModel):
    """`policy/units.yaml`. Gate A ships no universal built-in unit vocabulary (§11)."""

    units_version: PositiveInt
    units: tuple[UnitSpec, ...]

    @model_validator(mode="after")
    def _ids_and_aliases_are_globally_unique(self) -> UnitCatalog:
        """One token, one unit. An alias colliding with another unit's ID would make lookup
        depend on iteration order, and the two units need not share a metric kind."""
        tokens: list[str] = []
        for unit in self.units:
            tokens.append(unit.unit_id)
            tokens.extend(unit.aliases)
        _refuse_duplicate_keys(tokens, "unit token", "policy/units")
        return self

    @property
    def by_token(self) -> dict[str, UnitSpec]:
        resolved: dict[str, UnitSpec] = {}
        for unit in self.units:
            resolved[unit.unit_id] = unit
            for alias in unit.aliases:
                resolved[alias] = unit
        return resolved


# ======================================================================================
# policy/relations.yaml
# ======================================================================================


class RelationSpec(StrictModel):
    """One relation type and the entity kinds its endpoints may name (§9)."""

    relation_type: CatalogTokenId
    legal_source_kinds: Annotated[tuple[EntityKind, ...], UniqueSorted] = Field(min_length=1)
    legal_target_kinds: Annotated[tuple[EntityKind, ...], UniqueSorted] = Field(min_length=1)


class RelationCatalog(StrictModel):
    relations_version: PositiveInt
    relations: tuple[RelationSpec, ...]

    @model_validator(mode="after")
    def _types_are_unique(self) -> RelationCatalog:
        _refuse_duplicate_keys(
            (spec.relation_type for spec in self.relations), "relation_type", "policy/relations"
        )
        return self

    @property
    def by_type(self) -> dict[str, RelationSpec]:
        return {spec.relation_type: spec for spec in self.relations}


# ======================================================================================
# policy/sources.yaml
# ======================================================================================


class SourceKind(StrEnum):
    """The closed source-kind catalog (§18). Each pairs with exactly one approved enumerator."""

    BOARDWATCH_RESUME = "boardwatch_resume"
    MARKDOWN_DOCUMENT = "markdown_document"
    STRUCTURED_OBJECTS = "structured_objects"
    REPOSITORY_MARKDOWN = "repository_markdown"


class SourceSpec(StrictModel):
    """Portable source metadata only (§6, §18).

    `policy/sources.yaml` is authoritative for `source_kind` and `portable_locator`;
    `imports/source-ledger.yaml` owns enumeration, scope, digests, and dispositions. The two
    documents may not repeat the same metadata fields, so there is no `enumerator_id` here.

    Absolute machine-local roots live only in the non-revisioned root `local-sources.yaml`, which
    is why `portable_locator` is relative and validation rejects a home path inside it.
    """

    source_id: SourceId
    source_kind: SourceKind
    portable_locator: NonBlankStr


class SourceCatalog(StrictModel):
    sources_version: PositiveInt
    sources: tuple[SourceSpec, ...]

    @model_validator(mode="after")
    def _source_ids_are_unique(self) -> SourceCatalog:
        _refuse_duplicate_keys(
            (spec.source_id for spec in self.sources), "source_id", "policy/sources"
        )
        return self

    @property
    def by_id(self) -> dict[str, SourceSpec]:
        return {spec.source_id: spec for spec in self.sources}


# ======================================================================================
# policy/skill-categories.yaml
# ======================================================================================


class SkillCategorySpec(StrictModel):
    """One skill category. `parent_category_id` is optional per §10.4 and defaults to `null`."""

    category_id: CatalogTokenId
    display_name: NonBlankStr
    parent_category_id: CatalogTokenId | None = None
    aliases: Annotated[tuple[NonBlankStr, ...], UniqueSorted]


class SkillCategoryCatalog(StrictModel):
    """`policy/skill-categories.yaml`: field-dependent taxonomy, never a code vocabulary (§10.4).

    `career_field` is part of the catalog so a bundle states which field its categories belong to.
    Gate A uses a synthetic catalog; Gate B gathers the private one for the user's declared field.
    """

    catalog_version: PositiveInt
    career_field: CatalogTokenId
    categories: tuple[SkillCategorySpec, ...]

    @model_validator(mode="after")
    def _ids_unique_and_parents_resolve(self) -> SkillCategoryCatalog:
        ids = [spec.category_id for spec in self.categories]
        _refuse_duplicate_keys(ids, "category_id", "policy/skill-categories")
        known = set(ids)
        for spec in self.categories:
            if spec.parent_category_id is None:
                continue
            if spec.parent_category_id not in known:
                raise ValueError(
                    f"{spec.category_id}: parent_category_id {spec.parent_category_id!r} is not in "
                    "this catalog"
                )
            if spec.parent_category_id == spec.category_id:
                raise ValueError(f"{spec.category_id}: cannot be its own parent")
        _refuse_parent_cycles(self.categories)
        return self

    @property
    def by_id(self) -> dict[str, SkillCategorySpec]:
        return {spec.category_id: spec for spec in self.categories}


def _refuse_parent_cycles(categories: tuple[SkillCategorySpec, ...]) -> None:
    """A cycle would make any later "walk to the root" traversal non-terminating."""
    parents = {spec.category_id: spec.parent_category_id for spec in categories}
    for start in parents:
        seen = {start}
        current = parents[start]
        while current is not None:
            if current in seen:
                raise ValueError(f"skill-category parent cycle through {current!r}")
            seen.add(current)
            current = parents.get(current)


# ======================================================================================
# policy/assertion-tags.yaml
# ======================================================================================


class AssertionAuthorizationBranch(StrictModel):
    """One complete authorization route for a tag (§15).

    Exactly the four fields the design declares, all required. Within one branch every non-empty
    constraint is ANDed; items inside either list are alternatives. At least one constraint must be
    set, or the branch would authorize the tag unconditionally — which is how `production` would
    become claimable about a merely `completed` project.
    """

    subject_statuses: Annotated[tuple[LowerToken, ...], UniqueSorted]
    required_fact_predicates: Annotated[tuple[PredicateId, ...], UniqueSorted]
    required_fact_value: FactValue | None
    require_same_subject_metric: bool

    @model_validator(mode="after")
    def _branch_constrains_something(self) -> AssertionAuthorizationBranch:
        if not (
            self.subject_statuses
            or self.required_fact_predicates
            or self.required_fact_value is not None
            or self.require_same_subject_metric
        ):
            raise ValueError("an authorization branch must set at least one constraint")
        return self

    @model_validator(mode="after")
    def _a_required_value_names_exactly_one_predicate(self) -> AssertionAuthorizationBranch:
        if self.required_fact_value is not None and len(self.required_fact_predicates) != 1:
            raise ValueError(
                "required_fact_value requires exactly one required_fact_predicates item; with "
                "several, the value would have no unambiguous predicate to be compared against"
            )
        return self


class AssertionTagSpec(StrictModel):
    """Exactly the four columns §15 declares."""

    tag_id: LowerToken
    high_risk: bool
    legal_subject_kinds: Annotated[tuple[EntityKind, ...], UniqueSorted] = Field(min_length=1)
    authorization_any_of: tuple[AssertionAuthorizationBranch, ...] = Field(min_length=1)


#: §20.4 calls this "the complete high-risk set", so it is closed in code: a catalog that demoted
#: `production` to low risk, or promoted `designed`, would be changing a design-level closure rather
#: than adding data.
HIGH_RISK_ASSERTION_TAGS: Final[frozenset[str]] = frozenset(
    {"shipped", "live", "production", "published", "granted", "awarded", "certified"}
)

#: Aliases §15 rejects explicitly. They are the two spellings a well-meaning author reaches for, and
#: admitting either would let a project claim production status with no deployment evidence.
REJECTED_ASSERTION_TAG_ALIASES: Final[frozenset[str]] = frozenset({"ga_release", "in_production"})


class AssertionTagCatalog(StrictModel):
    assertion_tags_version: PositiveInt
    assertion_tags: tuple[AssertionTagSpec, ...]

    @model_validator(mode="after")
    def _closure_and_high_risk_agree_with_the_design(self) -> AssertionTagCatalog:
        ids = [spec.tag_id for spec in self.assertion_tags]
        _refuse_duplicate_keys(ids, "tag_id", "policy/assertion-tags")
        for spec in self.assertion_tags:
            if spec.tag_id in REJECTED_ASSERTION_TAG_ALIASES:
                raise ValueError(
                    f"{spec.tag_id!r} is a rejected alias; add the tag it aliases explicitly in a "
                    "new catalog version instead"
                )
            expected = spec.tag_id in HIGH_RISK_ASSERTION_TAGS
            if spec.tag_id in HIGH_RISK_ASSERTION_TAGS and not spec.high_risk:
                raise ValueError(f"{spec.tag_id!r} is in the complete high-risk set but declares "
                                 "high_risk: false")
            if spec.high_risk and not expected:
                raise ValueError(
                    f"{spec.tag_id!r} declares high_risk: true but is not in the design's complete "
                    "high-risk set; a new high-risk tag is a schema-level decision"
                )
        return self

    @property
    def by_id(self) -> dict[str, AssertionTagSpec]:
        return {spec.tag_id: spec for spec in self.assertion_tags}


# ======================================================================================
# policy/secret-scan.yaml
# ======================================================================================

class SecretScanFlag(StrEnum):
    """The closed set of `re` behaviours a rule may opt into (§12.2). Nothing else parses."""

    IGNORE_CASE = "ignore_case"
    MULTILINE = "multiline"


class SecretRule(StrictModel):
    """One named detection rule: exactly `rule_id`, `pattern`, and `flags` (§12.2).

    `pattern` is compiled at construction time so an unparseable regex is rejected where it is
    authored, rather than surfacing later as an opaque `re.error` from inside a scan — which would
    make a capture unscannable while looking like a clean one.
    """

    rule_id: LowerSlug
    pattern: NonBlankStr
    flags: Annotated[tuple[SecretScanFlag, ...], UniqueOrdered]

    @field_validator("pattern")
    @classmethod
    def _pattern_compiles(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"pattern is not a valid regular expression: {exc}") from exc
        return value


class SecretRuleset(StrictModel):
    """`policy/secret-scan.yaml`: `ruleset_version` plus `rules`, and nothing else (§12.2).

    The row shape lives here with the other catalogs; the built-in v1 registry and the scanning
    itself live in `secret_scan`, which is where the rules are applied.
    """

    ruleset_version: PositiveInt
    rules: tuple[SecretRule, ...]

    @model_validator(mode="after")
    def _rule_ids_are_unique(self) -> SecretRuleset:
        _refuse_duplicate_keys(
            (rule.rule_id for rule in self.rules), "rule_id", "policy/secret-scan"
        )
        return self


#: The secret-scan document is the ruleset itself.
SecretScanDocument = SecretRuleset


# ======================================================================================
# shared helper
# ======================================================================================


def _refuse_duplicate_keys(keys: Iterable[str], label: str, document: str) -> None:
    """A duplicate key makes `by_id` lookup depend on iteration order, silently picking a winner."""
    seen: set[str] = set()
    for key in keys:
        if key in seen:
            raise ValueError(f"{document}: duplicate {label} {key!r}")
        seen.add(key)


#: The claim types each owning file admits, exposed here so the document layer and the tests read
#: the same source rather than two copies of §15's sentence.
CLAIM_TYPE_OWNERS: Final[dict[str, frozenset[ClaimType]]] = {
    "claims/bullet-candidates.yaml": frozenset(
        {ClaimType.RESPONSIBILITY, ClaimType.ACCOMPLISHMENT, ClaimType.PROJECT_SUMMARY}
    ),
    "claims/summary-candidates.yaml": frozenset({ClaimType.PROFESSIONAL_SUMMARY}),
}
