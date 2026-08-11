"""Predicate contracts, effectiveness, cardinality, exclusivity, and fact-state agreement (§20.4).

The contract sweep is **derived from the shipped catalog, not from a list written here**. It reads
`policy/predicates.yaml` out of the packaged example, synthesises one fact that satisfies every column
of each row, and asserts semantic validation is silent about it — then mutates one dimension at a time
and asserts the matching code fires. A hand-written table of expected cases would sit still while the
catalog changed; this parameterisation cannot, because a new predicate row becomes a new test case and
a changed column changes what the case is built from.

Two boundaries are asserted rather than assumed, because both are places a plausible implementation
would add a check that can never run:

- **An entity's own status is refused at parse time**, by the discriminated union on `entity_type`.
  `ENTITY_STATUS_ILLEGAL` therefore checks the reachable thing: an assertion-tag row naming a status
  no legal subject kind can hold.
- **`technology.used` has no interval to inherit**, and the catalog is what guarantees it.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from boardwatch.profile_bundle.effective import (
    effective_fact_ids,
    eligible_fact_surfaces,
)
from boardwatch.profile_bundle.errors import IssueCode
from boardwatch.profile_bundle.models.base import Surface
from boardwatch.profile_bundle.models.entities import ProjectEntity
from boardwatch.profile_bundle.models.facts import FactValueKind
from boardwatch.profile_bundle.models.policy import (
    OwnerAttestationAuthority,
    PredicateSpec,
)
from boardwatch.profile_bundle.validation import build_context, validate_semantic
from tests.profile_bundle.conftest import SyntheticBundle, materialise
from tests.profile_bundle.test_profile_bundle_structural_validation import edit_document

# --------------------------------------------------------------------------------------
# Reading the shipped catalog
# --------------------------------------------------------------------------------------


def _catalog_context(bundle: SyntheticBundle) -> Any:
    return build_context(bundle.draft, mode="draft", bundle_root=bundle.root)


def semantic_findings(bundle: SyntheticBundle) -> tuple[Any, ...]:
    return validate_semantic(_catalog_context(bundle))


def findings_about(bundle: SyntheticBundle, record_id: str) -> tuple[Any, ...]:
    """Only the findings naming `record_id`.

    The sweep empties every other fact document, which legitimately leaves skills ungrounded and
    claims unsupported. Those findings are about *those* records; filtering by record ID is what keeps
    the sweep's assertions about the fact under test.
    """
    return tuple(f for f in semantic_findings(bundle) if f.record_id == record_id)


def codes(findings: tuple[Any, ...]) -> set[str]:
    return {f.code for f in findings}


#: A value payload per `FactValueKind`, so a fact can be synthesised for any predicate row.
_VALUES: dict[FactValueKind, dict[str, Any]] = {
    FactValueKind.STRING: {"type": "string", "value": "Synthetic value"},
    FactValueKind.INTEGER: {"type": "integer", "value": 4},
    FactValueKind.DECIMAL: {"type": "decimal", "value": "3.5"},
    FactValueKind.BOOLEAN: {"type": "boolean", "value": True},
    FactValueKind.DATE: {"type": "date", "value": "2026-01-15"},
    FactValueKind.YEAR_MONTH: {"type": "year_month", "value": "2026-01"},
    FactValueKind.DATE_RANGE: {
        "type": "date_range",
        "start": "2025-01-01",
        "end": "2026-01-01",
    },
    FactValueKind.URL: {"type": "url", "value": "https://example.com/synthetic"},
    FactValueKind.STRING_LIST: {"type": "string_list", "values": ["EXAMPLE-REGION-A"]},
    FactValueKind.SKILL_REF: {"type": "skill_ref", "skill_id": "skill.example-language"},
}

SYNTHETIC_FACT_ID = "fact.synthetic.contract.001"


def _value_for(spec: PredicateSpec) -> dict[str, Any]:
    kind = spec.legal_value_types[0]
    payload = dict(_VALUES[kind])
    if spec.legal_string_values and kind is FactValueKind.STRING:
        payload["value"] = spec.legal_string_values[0]
    return payload


def _basis_and_state(spec: PredicateSpec) -> tuple[str, str]:
    """A legal basis, and the strongest state that basis may establish for this predicate.

    Owner attestation is the interesting case: `owner_attestation_authority` says what it alone may
    establish, and every shipped row that admits it says `owner_confirmed` rather than `verified`.
    """
    basis = str(spec.legal_verification_bases[0])
    if basis == "owner_attested":
        if spec.owner_attestation_authority is OwnerAttestationAuthority.OWNER_CONFIRMED:
            return basis, "owner_confirmed"
        if spec.owner_attestation_authority is OwnerAttestationAuthority.VERIFIED:
            return basis, "verified"
        pytest.fail(f"{spec.predicate_id} admits owner_attested with no attestation authority")
    return basis, "verified"


def _evidence_by_class(bundle: SyntheticBundle) -> dict[str, str]:
    """evidence class -> one example evidence ID of that class, read from the fixture."""
    ctx = _catalog_context(bundle)
    resolved: dict[str, str] = {}
    for record in ctx.index.evidence:
        resolved.setdefault(str(record.evidence_class), record.evidence_id)
    return resolved


def _entity_of_kind(bundle: SyntheticBundle, kind: str) -> str:
    ctx = _catalog_context(bundle)
    for entity_id, entity in sorted(ctx.index.entities.items()):
        if getattr(entity, "entity_type", None) == kind:
            return entity_id
    pytest.fail(f"the example has no {kind} entity to hang a synthetic fact on")


def _fact_bearing_paths(bundle: SyntheticBundle) -> tuple[str, ...]:
    ctx = _catalog_context(bundle)
    return tuple(
        path.as_posix()
        for path, document in sorted(ctx.documents.by_path.items())
        if hasattr(document, "facts")
    )


def install_single_fact(bundle: SyntheticBundle, fact: dict[str, Any], *, into: str) -> None:
    """Empty every fact document, then put `fact` alone into `into`.

    Emptying the rest is what makes the sweep's cardinality and conflict assertions mean something:
    with the example's own facts still present, a synthesised second `project.summary` would report a
    cardinality violation that belongs to the fixture rather than to the case under test.
    """
    for path in _fact_bearing_paths(bundle):
        edit_document(bundle, path, lambda data: data.__setitem__("facts", []))
    edit_document(bundle, into, lambda data: data.__setitem__("facts", [fact]))


def conforming_fact(bundle: SyntheticBundle, spec: PredicateSpec) -> tuple[dict[str, Any], str]:
    """A fact satisfying every column of `spec`, and the document it belongs in."""
    subject_id = _entity_of_kind(bundle, str(spec.legal_subject_kinds[0]))
    basis, state = _basis_and_state(spec)
    by_class = _evidence_by_class(bundle)
    alternative = min(spec.minimum_evidence, key=lambda item: len(item.classes))
    evidence_ids = []
    for evidence_class in alternative.classes:
        found = by_class.get(str(evidence_class))
        if found is None:
            pytest.fail(f"the example has no {evidence_class} evidence record")
        evidence_ids.append(found)
    fact = {
        "fact_id": SYNTHETIC_FACT_ID,
        "subject_id": subject_id,
        "predicate": spec.predicate_id,
        "value": _value_for(spec),
        "verification_state": state,
        "verification_basis": basis,
        "usage_context": str(spec.legal_usage_contexts[0]),
        "evidence_ids": sorted(evidence_ids),
        "allowed_surfaces": sorted(str(surface) for surface in spec.legal_surfaces),
        "conflict_group_id": None,
        "reviewed_at": "2026-08-10",
        "expires_at": None,
        "supersedes_fact_ids": [],
        "import_lineage": None,
        "notes": None,
    }
    ctx = _catalog_context(bundle)
    owning = ctx.index.path_of(subject_id)
    assert owning is not None
    return fact, owning


def _shipped_predicates(tmp_path_factory: pytest.TempPathFactory) -> tuple[PredicateSpec, ...]:
    root = tmp_path_factory.mktemp("catalog") / "career-profile"
    root.mkdir()
    (root / "drafts").mkdir()
    bundle = materialise(root)
    catalog = _catalog_context(bundle).index.predicates
    assert catalog is not None
    return catalog.predicates


@pytest.fixture(scope="session")
def shipped_predicates(tmp_path_factory: pytest.TempPathFactory) -> tuple[PredicateSpec, ...]:
    return _shipped_predicates(tmp_path_factory)


def _predicate_ids(tmp_path_factory: pytest.TempPathFactory) -> list[str]:
    return [spec.predicate_id for spec in _shipped_predicates(tmp_path_factory)]


def spec_named(specs: tuple[PredicateSpec, ...], predicate_id: str) -> PredicateSpec:
    for spec in specs:
        if spec.predicate_id == predicate_id:
            return spec
    pytest.fail(f"{predicate_id} is not in the shipped catalog")


# --------------------------------------------------------------------------------------
# The clean case, and proof the sweep is exercising something
# --------------------------------------------------------------------------------------


def test_the_comprehensive_example_has_no_semantic_errors(
    synthetic_bundle: SyntheticBundle,
) -> None:
    assert semantic_findings(synthetic_bundle) == ()


def test_the_example_exercises_the_catalogs_this_layer_interprets(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """A clean result against absent catalogs would prove nothing at all."""
    ctx = _catalog_context(synthetic_bundle)
    assert ctx.index.predicates is not None and ctx.index.predicates.predicates
    assert ctx.index.units is not None and ctx.index.units.units
    assert ctx.index.skill_categories is not None
    assert ctx.index.assertion_tags is not None and ctx.index.assertion_tags.assertion_tags
    assert ctx.index.skills and ctx.index.metrics and ctx.index.claims
    assert any(fact.supersedes_fact_ids for fact in ctx.index.facts)
    assert ctx.index.unresolved_conflict_ids, "no unresolved group, so blocking is untested"


def test_every_shipped_predicate_is_exercised_by_at_least_one_example_fact_or_the_sweep(
    synthetic_bundle: SyntheticBundle, shipped_predicates: tuple[PredicateSpec, ...]
) -> None:
    """The sweep below covers every row; this states the count so a shrunken catalog is visible."""
    assert len(shipped_predicates) == 41
    used = {fact.predicate for fact in _catalog_context(synthetic_bundle).index.facts}
    assert used, "the example declares no facts"
    assert used <= {spec.predicate_id for spec in shipped_predicates}


# --------------------------------------------------------------------------------------
# One conforming case per predicate row
# --------------------------------------------------------------------------------------


def test_a_conforming_fact_is_accepted_for_every_shipped_predicate(
    tmp_path: Path,
    shipped_predicates: tuple[PredicateSpec, ...],
) -> None:
    """Every row of the catalog, accepted when every column is satisfied.

    Run as one test over all rows rather than 41 parameterised cases because each case rebuilds a
    bundle on disk; the loop keeps the fixture cost linear and still names the failing predicate.
    """
    for index, spec in enumerate(shipped_predicates):
        root = tmp_path / f"bundle-{index}" / "career-profile"
        root.mkdir(parents=True)
        (root / "drafts").mkdir()
        bundle = materialise(root)
        fact, owning = conforming_fact(bundle, spec)
        install_single_fact(bundle, fact, into=owning)
        found = findings_about(bundle, SYNTHETIC_FACT_ID)
        assert found == (), (
            f"{spec.predicate_id}: a conforming fact was rejected: "
            f"{[(f.code, f.message) for f in found]}"
        )


# --------------------------------------------------------------------------------------
# One rejection per illegal dimension
# --------------------------------------------------------------------------------------


@pytest.fixture
def grounded(synthetic_bundle: SyntheticBundle) -> SyntheticBundle:
    """The example with one conforming `technology.used` fact as the only fact in the tree.

    `technology.used` is the row that exercises the most columns at once: several subject kinds,
    several usage contexts, a skill-reference value, three evidence alternatives, and skill grounding.
    """
    ctx = _catalog_context(synthetic_bundle)
    catalog = ctx.index.predicates
    assert catalog is not None
    spec = spec_named(catalog.predicates, "technology.used")
    fact, owning = conforming_fact(synthetic_bundle, spec)
    install_single_fact(synthetic_bundle, fact, into=owning)
    return synthetic_bundle


def mutate_synthetic(bundle: SyntheticBundle, **changes: Any) -> None:
    path = next(
        p for p in _fact_bearing_paths(bundle) if _has_synthetic(bundle, p)
    )

    def apply(data: Any) -> None:
        data["facts"][0].update(changes)

    edit_document(bundle, path, apply)


def _has_synthetic(bundle: SyntheticBundle, relative: str) -> bool:
    return SYNTHETIC_FACT_ID in bundle.read(relative)


def test_an_unknown_predicate_is_a_hard_failure(grounded: SyntheticBundle) -> None:
    mutate_synthetic(grounded, predicate="technology.invented")
    found = findings_about(grounded, SYNTHETIC_FACT_ID)
    assert IssueCode.UNKNOWN_PREDICATE in codes(found)


def test_a_predicate_refuses_a_subject_kind_its_row_does_not_list(
    grounded: SyntheticBundle,
) -> None:
    """`technology.used` describes education, employment, project, course, publication — not an award."""
    award = _entity_of_kind(grounded, "award")
    mutate_synthetic(grounded, subject_id=award)
    found = findings_about(grounded, SYNTHETIC_FACT_ID)
    assert IssueCode.PREDICATE_SUBJECT_KIND_ILLEGAL in codes(found)


def test_a_predicate_refuses_a_value_type_its_row_does_not_list(
    grounded: SyntheticBundle,
) -> None:
    mutate_synthetic(grounded, value={"type": "integer", "value": 7})
    found = findings_about(grounded, SYNTHETIC_FACT_ID)
    assert IssueCode.PREDICATE_VALUE_TYPE_ILLEGAL in codes(found)


def test_an_enumerated_string_predicate_refuses_a_value_outside_its_enumeration(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """`deployment.environment` is §10.4's one "string enum" cell, and the values are catalog data."""
    ctx = _catalog_context(synthetic_bundle)
    catalog = ctx.index.predicates
    assert catalog is not None
    spec = spec_named(catalog.predicates, "deployment.environment")
    assert spec.legal_string_values, "the enumeration is the point of this case"
    fact, owning = conforming_fact(synthetic_bundle, spec)
    fact["value"] = {"type": "string", "value": "preproduction"}
    install_single_fact(synthetic_bundle, fact, into=owning)
    found = findings_about(synthetic_bundle, SYNTHETIC_FACT_ID)
    assert IssueCode.PREDICATE_VALUE_TYPE_ILLEGAL in codes(found)


def test_a_predicate_refuses_a_usage_context_its_row_does_not_list(
    grounded: SyntheticBundle,
) -> None:
    mutate_synthetic(grounded, usage_context="incidental")
    found = findings_about(grounded, SYNTHETIC_FACT_ID)
    assert IssueCode.PREDICATE_CONTEXT_ILLEGAL in codes(found)


def test_a_predicate_refuses_a_surface_its_row_does_not_list(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """`education.result` permits resume and application, never public."""
    ctx = _catalog_context(synthetic_bundle)
    catalog = ctx.index.predicates
    assert catalog is not None
    spec = spec_named(catalog.predicates, "education.result")
    assert Surface.PUBLIC not in spec.legal_surfaces
    fact, owning = conforming_fact(synthetic_bundle, spec)
    fact["allowed_surfaces"] = ["public", "resume"]
    install_single_fact(synthetic_bundle, fact, into=owning)
    found = findings_about(synthetic_bundle, SYNTHETIC_FACT_ID)
    assert IssueCode.PREDICATE_SURFACE_ILLEGAL in codes(found)


def test_an_application_only_predicate_refuses_a_resume_surface_outside_the_gated_file(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The second latch (§10.4), and it must work where the document validator does not reach.

    `GatedFactsDocument` refuses a résumé surface inside `application/gated-facts.yaml`. An
    `application.*` fact authored into `facts/identity.yaml` bypasses that document entirely, which is
    exactly where a leak would be least visible — so `surface_policy` has to catch it independently.
    """
    ctx = _catalog_context(synthetic_bundle)
    catalog = ctx.index.predicates
    assert catalog is not None
    spec = spec_named(catalog.predicates, "application.requires_sponsorship")
    fact, _ = conforming_fact(synthetic_bundle, spec)
    fact["allowed_surfaces"] = ["application", "resume"]
    install_single_fact(synthetic_bundle, fact, into="facts/identity.yaml")
    found = findings_about(synthetic_bundle, SYNTHETIC_FACT_ID)
    assert IssueCode.SURFACE_POLICY_VIOLATED in codes(found)
    assert IssueCode.PREDICATE_SURFACE_ILLEGAL in codes(found)


def test_a_basis_outside_the_predicates_own_list_is_an_evidence_contract_failure(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Narrower than the global basis/class rule the evidence layer applies.

    `project.contribution` accepts `repository_verified` and nothing else, so an owner-attested
    contribution asserts a code review that never happened even though `owner_attested` is a perfectly
    real basis elsewhere.
    """
    ctx = _catalog_context(synthetic_bundle)
    catalog = ctx.index.predicates
    assert catalog is not None
    spec = spec_named(catalog.predicates, "project.contribution")
    fact, owning = conforming_fact(synthetic_bundle, spec)
    fact["verification_basis"] = "owner_attested"
    install_single_fact(synthetic_bundle, fact, into=owning)
    found = findings_about(synthetic_bundle, SYNTHETIC_FACT_ID)
    assert IssueCode.EVIDENCE_CONTRACT_UNMET in codes(found)


def test_evidence_below_the_predicates_minimum_class_is_an_evidence_contract_failure(
    synthetic_bundle: SyntheticBundle,
) -> None:
    ctx = _catalog_context(synthetic_bundle)
    catalog = ctx.index.predicates
    assert catalog is not None
    spec = spec_named(catalog.predicates, "project.contribution")
    fact, owning = conforming_fact(synthetic_bundle, spec)
    fact["evidence_ids"] = ["evidence.example.legacy-summary.001"]
    install_single_fact(synthetic_bundle, fact, into=owning)
    found = findings_about(synthetic_bundle, SYNTHETIC_FACT_ID)
    assert IssueCode.EVIDENCE_CONTRACT_UNMET in codes(found)


def test_owner_attestation_cannot_establish_verified_when_the_row_says_owner_confirmed(
    grounded: SyntheticBundle,
) -> None:
    """`owner_confirmed` is not a weaker synonym for `verified` (§10.2)."""
    mutate_synthetic(grounded, verification_state="verified", verification_basis="owner_attested")
    found = findings_about(grounded, SYNTHETIC_FACT_ID)
    assert IssueCode.OWNER_ATTESTATION_NOT_PERMITTED in codes(found)


def test_owner_attestation_is_not_consulted_for_a_fact_resting_on_a_repository_artefact(
    grounded: SyntheticBundle,
) -> None:
    """The authority column is about attestation, not about every fact on an attesting predicate."""
    mutate_synthetic(
        grounded,
        verification_state="verified",
        verification_basis="repository_verified",
        evidence_ids=["evidence.packet-pantry.manifest.001"],
    )
    found = findings_about(grounded, SYNTHETIC_FACT_ID)
    assert IssueCode.OWNER_ATTESTATION_NOT_PERMITTED not in codes(found)


# --------------------------------------------------------------------------------------
# Cardinality, exclusivity, and effective-only counting
# --------------------------------------------------------------------------------------


def test_two_effective_facts_on_a_single_valued_predicate_exceed_its_cardinality(
    synthetic_bundle: SyntheticBundle,
) -> None:
    def duplicate(data: Any) -> None:
        facts = data["facts"]
        original = next(f for f in facts if f["fact_id"] == "fact.packet-pantry.summary.002")
        clone = dict(original)
        clone["fact_id"] = "fact.packet-pantry.summary.003"
        clone["supersedes_fact_ids"] = []
        facts.append(clone)

    edit_document(synthetic_bundle, "facts/projects/project.packet-pantry.yaml", duplicate)
    found = semantic_findings(synthetic_bundle)
    assert IssueCode.PREDICATE_CARDINALITY_EXCEEDED in codes(found)


def test_a_correction_by_supersession_does_not_exceed_cardinality(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The example already ships the correction: two `project.summary` facts, one superseded.

    This is the property §10.4 exists to protect — "retained records therefore do not make a
    correction exceed cardinality" — so it is asserted against the fixture rather than a construction.
    """
    ctx = _catalog_context(synthetic_bundle)
    summaries = [
        fact
        for fact in ctx.index.facts
        if fact.predicate == "project.summary" and fact.subject_id == "project.packet-pantry"
    ]
    assert len(summaries) == 2, "the fixture no longer ships a superseded correction"
    effective = effective_fact_ids(ctx)
    assert len([f for f in summaries if f.fact_id in effective]) == 1
    assert IssueCode.PREDICATE_CARDINALITY_EXCEEDED not in codes(semantic_findings(synthetic_bundle))


def test_facts_blocked_by_an_unresolved_conflict_are_not_effective(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Two competing `project.end_date` candidates, both `unresolved`, inside one declared group."""
    ctx = _catalog_context(synthetic_bundle)
    effective = effective_fact_ids(ctx)
    end_dates = [
        fact.fact_id
        for fact in ctx.index.facts
        if fact.predicate == "project.end_date" and fact.subject_id == "project.packet-pantry"
    ]
    assert len(end_dates) == 2
    assert not [fact_id for fact_id in end_dates if fact_id in effective]


def test_a_superseding_fact_that_is_not_itself_effective_does_not_retire_its_target(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """A proposed correction the owner has not accepted must not silently remove what it replaces."""

    def unaccept(data: Any) -> None:
        for fact in data["facts"]:
            if fact["fact_id"] == "fact.packet-pantry.summary.002":
                fact["verification_state"] = "unresolved"
            if fact["fact_id"] == "fact.packet-pantry.summary.001":
                fact["verification_state"] = "verified"
                fact["verification_basis"] = "owner_attested"

    edit_document(synthetic_bundle, "facts/projects/project.packet-pantry.yaml", unaccept)
    ctx = _catalog_context(synthetic_bundle)
    effective = effective_fact_ids(ctx)
    assert "fact.packet-pantry.summary.001" in effective


def test_an_inverted_date_range_violates_its_exclusivity_rule(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """`start <= end` is `employment.date_range`'s exclusivity cell, not the value type's business."""

    def invert(data: Any) -> None:
        for fact in data["facts"]:
            if fact["value"].get("type") == "date_range":
                fact["value"]["start"] = "2030-01-01"
                fact["value"]["end"] = "2020-01-01"

    edit_document(
        synthetic_bundle, "facts/experience/employment.example-labs.yaml", invert
    )
    found = semantic_findings(synthetic_bundle)
    assert IssueCode.PREDICATE_EXCLUSIVITY_VIOLATED in codes(found)


def test_an_exclusive_predicate_with_many_cardinality_still_admits_only_one_effective_fact(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The exclusivity count clause, reached the only way it can be: through catalog data.

    Every shipped row pairing `one_effective_value` with cardinality `one` makes the count clause
    redundant, so it is scoped to cardinality `many` to avoid two findings for one mistake. The
    catalog is revision-owned data, so a `many` + `one_effective_value` row is authorable — this edits
    one and shows the clause fires.
    """

    def widen(data: Any) -> None:
        for spec in data["predicates"]:
            if spec["predicate_id"] == "project.contribution":
                spec["exclusivity"] = "one_effective_value"

    def duplicate(data: Any) -> None:
        original = next(
            f for f in data["facts"] if f["fact_id"] == "fact.packet-pantry.contribution.001"
        )
        clone = dict(original)
        clone["fact_id"] = "fact.packet-pantry.contribution.002"
        clone["value"] = {"type": "string", "value": "A second distinct contribution"}
        data["facts"].append(clone)

    edit_document(synthetic_bundle, "policy/predicates.yaml", widen)
    edit_document(synthetic_bundle, "facts/projects/project.packet-pantry.yaml", duplicate)
    found = semantic_findings(synthetic_bundle)
    assert IssueCode.PREDICATE_EXCLUSIVITY_VIOLATED in codes(found)
    assert IssueCode.PREDICATE_CARDINALITY_EXCEEDED not in codes(found)


# --------------------------------------------------------------------------------------
# Conflicts and fact states
# --------------------------------------------------------------------------------------


def test_competing_single_valued_values_outside_a_conflict_group_are_a_hard_failure(
    synthetic_bundle: SyntheticBundle,
) -> None:
    def compete(data: Any) -> None:
        original = next(
            f for f in data["facts"] if f["fact_id"] == "fact.packet-pantry.summary.002"
        )
        clone = dict(original)
        clone["fact_id"] = "fact.packet-pantry.summary.rival"
        clone["value"] = {"type": "string", "value": "A completely different summary"}
        clone["supersedes_fact_ids"] = []
        data["facts"].append(clone)

    edit_document(synthetic_bundle, "facts/projects/project.packet-pantry.yaml", compete)
    found = semantic_findings(synthetic_bundle)
    assert IssueCode.COMPETING_VALUES_OUTSIDE_CONFLICT in codes(found)


def test_competing_values_inside_one_declared_group_are_not_a_competition_finding(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The example's two `project.end_date` candidates are the case: declared, and therefore fine."""
    assert IssueCode.COMPETING_VALUES_OUTSIDE_CONFLICT not in codes(
        semantic_findings(synthetic_bundle)
    )


def test_a_duplicate_value_is_a_cardinality_finding_and_not_a_competition_finding(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Two effective facts asserting the SAME value are a duplicate, not a conflict to rule on."""

    def duplicate(data: Any) -> None:
        original = next(
            f for f in data["facts"] if f["fact_id"] == "fact.packet-pantry.summary.002"
        )
        clone = dict(original)
        clone["fact_id"] = "fact.packet-pantry.summary.twin"
        clone["supersedes_fact_ids"] = []
        data["facts"].append(clone)

    edit_document(synthetic_bundle, "facts/projects/project.packet-pantry.yaml", duplicate)
    found = codes(semantic_findings(synthetic_bundle))
    assert IssueCode.PREDICATE_CARDINALITY_EXCEEDED in found
    assert IssueCode.COMPETING_VALUES_OUTSIDE_CONFLICT not in found


def test_a_superseded_fact_left_effective_is_a_state_inconsistency(
    synthetic_bundle: SyntheticBundle,
) -> None:
    def resurrect(data: Any) -> None:
        for fact in data["facts"]:
            if fact["fact_id"] == "fact.packet-pantry.summary.001":
                fact["verification_state"] = "owner_confirmed"

    edit_document(synthetic_bundle, "facts/projects/project.packet-pantry.yaml", resurrect)
    found = semantic_findings(synthetic_bundle)
    assert IssueCode.FACT_STATE_INCONSISTENT in codes(found)


def test_a_superseded_state_with_no_incoming_edge_is_a_state_inconsistency(
    synthetic_bundle: SyntheticBundle,
) -> None:
    def orphan(data: Any) -> None:
        for fact in data["facts"]:
            if fact["fact_id"] == "fact.packet-pantry.summary.002":
                fact["supersedes_fact_ids"] = []

    edit_document(synthetic_bundle, "facts/projects/project.packet-pantry.yaml", orphan)
    found = semantic_findings(synthetic_bundle)
    assert IssueCode.FACT_STATE_INCONSISTENT in codes(found)


# --------------------------------------------------------------------------------------
# Where §20.4's entity-status row actually lands
# --------------------------------------------------------------------------------------


def test_an_entity_status_from_the_wrong_catalog_is_refused_before_this_layer() -> None:
    """§20.4 says entity statuses come from the correct catalog; the union enforces it at parse time.

    Asserted here, rather than implemented a second time in `semantic.py`, so the row does not look
    uncovered while the guarantee is in fact stronger than a validation pass would make it — a wrong
    status never becomes a model at all. See D-115.
    """
    with pytest.raises(ValidationError):
        ProjectEntity.model_validate(
            {
                "entity_id": "project.synthetic",
                "entity_type": "project",
                "display_name": "Synthetic",
                "created_at": "2026-01-01",
                "reviewed_at": "2026-01-01",
                "status": "awarded",  # an AwardStatus, not a ProjectStatus
            }
        )


def test_an_assertion_tag_naming_an_unholdable_status_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The reachable half: `subject_statuses` is a bare token, so a typo disarms the tag silently."""

    def typo(data: Any) -> None:
        for spec in data["assertion_tags"]:
            if spec["tag_id"] == "shipped":
                spec["authorization_any_of"][0]["subject_statuses"] = ["shipped_privately"]

    edit_document(synthetic_bundle, "policy/assertion-tags.yaml", typo)
    found = semantic_findings(synthetic_bundle)
    assert IssueCode.ENTITY_STATUS_ILLEGAL in codes(found)


# --------------------------------------------------------------------------------------
# `technology.used` inherits no interval
# --------------------------------------------------------------------------------------


def test_technology_used_has_no_interval_to_inherit(
    shipped_predicates: tuple[PredicateSpec, ...],
) -> None:
    """A usage fact carries no dates, so it cannot silently borrow its employer's date range.

    Stated against the catalog because the catalog is the mechanism: the row admits only a skill
    reference, and its expiry cell is `never; null`. Nothing downstream can then read a start or end
    off a `technology.used` fact.
    """
    spec = spec_named(shipped_predicates, "technology.used")
    assert spec.legal_value_types == (FactValueKind.SKILL_REF,)
    assert FactValueKind.DATE_RANGE not in spec.legal_value_types
    assert str(spec.expiry.behaviour) == "never"
    assert spec.expiry.review_interval_days is None
    assert spec.may_ground_skill is True


def test_expiry_is_not_evaluated_by_this_layer(synthetic_bundle: SyntheticBundle) -> None:
    """§20 requires validation to be a pure function of content, so a past expiry is not an error.

    The example ships a fact whose `expires_at` is already in the past. It stays semantically valid;
    completeness against an explicit `--as-of` date is what reports it.
    """
    ctx = _catalog_context(synthetic_bundle)
    expired = [
        fact
        for fact in ctx.index.facts
        if fact.expires_at is not None and fact.expires_at < date(2026, 8, 10)
    ]
    assert expired, "the fixture no longer carries a past expiry"
    assert validate_semantic(ctx) == ()


def test_eligible_surfaces_are_empty_for_a_fact_that_is_not_effective(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """A retained record still declares surfaces; eligibility is derived, and derives to nothing."""
    ctx = _catalog_context(synthetic_bundle)
    stale = ctx.index.fact("fact.packet-pantry.legacy-language.001")
    assert stale is not None
    assert stale.allowed_surfaces == (Surface.RESUME,)
    assert eligible_fact_surfaces(stale, ctx) == frozenset()
