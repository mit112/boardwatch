"""The seeded starter predicate catalog and its §5.2 audit gate (Slice A).

The mechanical invariants catch the defect class the Task-1 audit found in an unaudited catalog: a
dead enum member, an unreachable grounding guard, and an unavailable version silently supplying an
empty vocabulary. Invariant 4 (package-level catalog<->mapping reachability against the builtin
extraction mapping) now ships in `test_extraction_mapping.py`, where the mapping lives — both
directions there. Invariant 3 (§5.1's behavioural grounding assertion) ships at the bottom of this
file, over a `ValidationContext` assembled from typed records: the comprehensive example's
`technology.used` row omits `incidental`, so only a builtin-catalog-backed context can express the
fixture the assertion needs.
"""

from __future__ import annotations

import datetime
import pathlib

import pytest

from boardwatch.profile_bundle import predicate_catalog
from boardwatch.profile_bundle.drafts import init_draft
from boardwatch.profile_bundle.effective import eligible_supporting_facts, grounding_facts
from boardwatch.profile_bundle.errors import UnsupportedPredicateCatalogError
from boardwatch.profile_bundle.extraction import named_predicates
from boardwatch.profile_bundle.extraction_mapping import BUILTIN_EXTRACTION_MAPPINGS
from boardwatch.profile_bundle.models.base import (
    Surface,
    UsageContext,
    VerificationBasis,
    VerificationState,
)
from boardwatch.profile_bundle.models.documents import (
    BundleDocuments,
    ProjectFactsDocument,
    SkillInventoryDocument,
)
from boardwatch.profile_bundle.models.entities import ProjectEntity, ProjectStatus
from boardwatch.profile_bundle.models.facts import FactRecord, SkillRefValue
from boardwatch.profile_bundle.models.manifests import DraftManifest
from boardwatch.profile_bundle.models.skills import SkillRecord
from boardwatch.profile_bundle.schema import CURRENT_SCHEMA_VERSION
from boardwatch.profile_bundle.validation import load_documents
from boardwatch.profile_bundle.validation.context import ValidationContext, context_from_documents

BUILTIN = predicate_catalog.builtin_catalog(predicate_catalog.CURRENT_CATALOG_VERSION)


def _admitted(attr: str) -> set[object]:
    """The union of one set-like field across every builtin predicate."""
    values: set[object] = set()
    for spec in BUILTIN.predicates:
        values.update(getattr(spec, attr))
    return values


# --------------------------------------------------------------------------------------
# The two sanctioned amendments — asserted against outside facts, not the row count
# --------------------------------------------------------------------------------------


def test_the_skill_grounding_predicate_admits_a_familiarity_context() -> None:
    """§5.1: a familiarity-level skill must stay expressible. Without `incidental` on the one
    grounding predicate the owner must overclaim, and `effective.py`'s grounding guard can never
    fire."""
    spec = BUILTIN.by_id["technology.used"]
    assert spec.may_ground_skill
    assert UsageContext.INCIDENTAL in spec.legal_usage_contexts


def test_a_project_name_predicate_exists_mirroring_project_summary() -> None:
    """`render/latex.py` shows `title` is a project's displayed name, so project identity needs its
    own predicate — string, cardinality one, on a `project` subject — mirroring `project.summary`."""
    name = BUILTIN.by_id["project.name"]
    summary = BUILTIN.by_id["project.summary"]
    assert name.legal_subject_kinds == summary.legal_subject_kinds
    assert [t.value for t in name.legal_value_types] == ["string"]
    assert name.cardinality is summary.cardinality


def test_every_predicate_the_builtin_mapping_needs_is_present() -> None:
    """Every predicate the deterministic mapping (§6.2a-proof) resolves to must be in the catalog,
    or `build_candidate_package` raises. `project.name` is the row the audit added.

    `needed` is READ FROM the live mapping through `named_predicates` — the production helper the
    reachability check itself calls, not a second walk of the rule structure. A hand-typed set keeps
    checking the predicates of the day it was typed, so a *twelfth* predicate the mapping started
    naming would never be asked for here and the drift would stay green.

    The two sides are genuinely independent, which is what keeps this from being a tautology:
    `BUILTIN_EXTRACTION_MAPPINGS` is authored in `extraction_mapping.py` as string literals and
    imports nothing from `predicate_catalog`, while `BUILTIN` is parsed from the packaged
    `predicate-catalog-v1.yaml`. Neither artifact is derived from the other.
    """
    needed: set[str] = set().union(
        *(named_predicates(mapping) for mapping in BUILTIN_EXTRACTION_MAPPINGS.values())
    )
    # A mapping that named nothing would make the containment below vacuously true.
    assert needed, "no builtin mapping names any predicate"
    assert needed <= set(BUILTIN.by_id), sorted(needed - set(BUILTIN.by_id))


# --------------------------------------------------------------------------------------
# Module contract
# --------------------------------------------------------------------------------------


def test_an_unsupported_catalog_version_is_a_typed_refusal() -> None:
    """§5.2 invariant 5 / §6.7-style version handling: an unavailable recorded version becomes exit
    3, never a silent empty vocabulary."""
    with pytest.raises(UnsupportedPredicateCatalogError) as excinfo:
        predicate_catalog.builtin_catalog(999)
    assert excinfo.value.found == 999
    assert predicate_catalog.CURRENT_CATALOG_VERSION in excinfo.value.supported


def test_catalog_matches_builtin_is_true_for_the_builtin_and_false_for_a_change() -> None:
    assert predicate_catalog.catalog_matches_builtin(BUILTIN)
    mutated = BUILTIN.model_copy(update={"predicates": BUILTIN.predicates[1:]})
    assert not predicate_catalog.catalog_matches_builtin(mutated)


def test_catalog_matches_builtin_is_false_for_a_version_this_build_does_not_retain() -> None:
    other_version = BUILTIN.model_copy(update={"predicates_version": 999})
    assert not predicate_catalog.catalog_matches_builtin(other_version)


# --------------------------------------------------------------------------------------
# init seeds it — mirrors test_the_initial_draft_carries_this_builds_secret_scan_ruleset
# --------------------------------------------------------------------------------------


def test_a_fresh_bundle_is_born_with_this_builds_predicate_catalog(tmp_path: pathlib.Path) -> None:
    """An empty vocabulary would leave every enumerated record `review_required` forever (§5)."""
    handle = init_draft(tmp_path / "career-profile", name="initial").value
    assert handle is not None
    documents = load_documents(handle.root, mode="draft")
    recorded = documents.get("policy/predicates.yaml")
    assert predicate_catalog.catalog_matches_builtin(recorded)
    assert (
        documents.manifest.predicate_catalog_version
        == predicate_catalog.CURRENT_CATALOG_VERSION
    )


# --------------------------------------------------------------------------------------
# §5.2 gate — invariant 1: no dead enum member
# --------------------------------------------------------------------------------------


def test_every_surface_is_admitted_by_some_predicate() -> None:
    assert set(Surface) <= _admitted("legal_surfaces")


def test_every_usage_context_is_admitted_by_some_predicate() -> None:
    assert set(UsageContext) <= _admitted("legal_usage_contexts")


def test_every_verification_basis_is_admitted_or_explicitly_rostered() -> None:
    """A fact-only starter never establishes `measured`/`secondary_only`/`multiple_sources`; they
    are rostered with a reason rather than admitted, so a NEW accidental orphan still fails here."""
    admitted = _admitted("legal_verification_bases")
    rostered = set(predicate_catalog.NOT_ADMITTED_VERIFICATION_BASES)
    assert set(VerificationBasis) == admitted | rostered


def test_the_unadmitted_roster_carries_no_basis_that_is_actually_admitted() -> None:
    """A basis a predicate later admits must leave the roster, or the roster stops being honest."""
    admitted = _admitted("legal_verification_bases")
    assert admitted.isdisjoint(predicate_catalog.NOT_ADMITTED_VERIFICATION_BASES)


# --------------------------------------------------------------------------------------
# §5.2 gate — invariant 2: no unreachable grounding guard
# --------------------------------------------------------------------------------------


def test_every_skill_grounding_predicate_admits_incidental() -> None:
    """`effective.py`'s guard is `may_ground_skill and usage_context != INCIDENTAL`; a grounding
    predicate that never admits `incidental` makes that guard dead."""
    for spec in BUILTIN.predicates:
        if spec.may_ground_skill:
            assert UsageContext.INCIDENTAL in spec.legal_usage_contexts, spec.predicate_id


# --------------------------------------------------------------------------------------
# §5.2 gate — invariant 3: the grounding guard fires, behaviourally
#
# Invariant 2 above is the static half: the catalog PERMITS `incidental` on the one grounding
# predicate. This is the half that says what `effective.py` then does with such a fact — it stays
# supporting and stops grounding — so `grounding_facts`' `usage_context is INCIDENTAL` arm is
# provably reachable rather than dead.
#
# The context is assembled from typed records rather than a bundle on disk, because the packaged
# comprehensive example's catalog omits `incidental` from `technology.used`: an example-backed
# context cannot express this fixture at all. Only the records `effective_fact_ids` and
# `grounding_facts` actually read are present — no evidence, no conflicts — so a failure here can
# only be about the guard.
# --------------------------------------------------------------------------------------

_SUBJECT_ID = "project.example"
_SKILL_ID = "skill.example-language"
_INCIDENTAL_FACT = "fact.example.incidental.001"
_PROFESSIONAL_FACT = "fact.example.professional.001"


def _technology_used(fact_id: str, context: UsageContext) -> FactRecord:
    """One `technology.used` fact naming `_SKILL_ID`. `usage_context` is the ONLY thing that varies
    between the two facts the test compares, so nothing else can explain the difference."""
    return FactRecord(
        fact_id=fact_id,
        subject_id=_SUBJECT_ID,
        predicate="technology.used",
        value=SkillRefValue(type="skill_ref", skill_id=_SKILL_ID),
        # `owner_confirmed` is effective (§10.4), which is the precondition for being supporting at
        # all — a non-effective fact would make the test pass for the wrong reason.
        verification_state=VerificationState.OWNER_CONFIRMED,
        verification_basis=VerificationBasis.OWNER_ATTESTED,
        usage_context=context,
        # Empty rather than a dangling ID: evidence sufficiency is the evidence layer's finding and
        # nothing on this derivation path reads it.
        evidence_ids=(),
        allowed_surfaces=(Surface.RESUME,),
        conflict_group_id=None,
        reviewed_at=datetime.date(2026, 1, 1),
        expires_at=None,
        supersedes_fact_ids=(),
        import_lineage=None,
        notes=None,
    )


def _grounding_context() -> tuple[SkillRecord, ValidationContext]:
    """One skill supported by an incidental and a professional `technology.used` fact, indexed
    against THIS build's builtin catalog through the production indexer."""
    incidental = _technology_used(_INCIDENTAL_FACT, UsageContext.INCIDENTAL)
    professional = _technology_used(_PROFESSIONAL_FACT, UsageContext.PROFESSIONAL)
    skill = SkillRecord(
        skill_id=_SKILL_ID,
        canonical_name="Example Language",
        category="languages",
        supporting_fact_ids=(incidental.fact_id, professional.fact_id),
        verification_state=VerificationState.VERIFIED,
        allowed_surfaces=(Surface.RESUME,),
    )
    documents = BundleDocuments(
        manifest=DraftManifest(
            state="draft",
            schema_version=CURRENT_SCHEMA_VERSION,
            profile_id="profile.example",
            evidence_set_digest="sha256:" + "0" * 64,
            predicate_catalog_version=predicate_catalog.CURRENT_CATALOG_VERSION,
            unit_catalog_version=1,
            relation_catalog_version=1,
            skill_category_catalog_version=1,
            assertion_tag_catalog_version=1,
            secret_scan_ruleset_version=1,
            draft_of_revision=None,
            parent_bundle_digest=None,
            bundle_digest="",
            approved_candidate_digest="",
            approval_stamp_id="",
            change_id="",
        ),
        by_path={
            pathlib.PurePosixPath("policy/predicates.yaml"): BUILTIN,
            pathlib.PurePosixPath("facts/projects/project.example.yaml"): ProjectFactsDocument(
                entity=ProjectEntity(
                    entity_id=_SUBJECT_ID,
                    entity_type="project",
                    display_name="Example Project",
                    status=ProjectStatus.COMPLETED,
                    created_at=datetime.date(2026, 1, 1),
                    reviewed_at=datetime.date(2026, 1, 1),
                ),
                facts=(incidental, professional),
            ),
            pathlib.PurePosixPath("skills/inventory.yaml"): SkillInventoryDocument(
                skills=(skill,)
            ),
        },
    )
    return skill, context_from_documents(documents, root=pathlib.Path("."), mode="draft")


def test_an_incidental_context_fact_supports_but_never_grounds() -> None:
    """§10.1: "`incidental` can never ground a verified skill" — and it must still SUPPORT one.

    The positive control comes first on purpose. Without "the professional fact IS grounding", a
    context that resolved to nothing would leave both sets empty and "the incidental fact is not
    grounding" would pass while proving the opposite of the claim. The membership assertion on
    `eligible_supporting_facts` is the second half of the same guard: it proves the incidental fact
    reached `grounding_facts` and was dropped there, not that it was never eligible to begin with.
    """
    skill, ctx = _grounding_context()
    supporting = {fact.fact_id for fact in eligible_supporting_facts(skill, ctx)}
    grounding = {fact.fact_id for fact in grounding_facts(skill, ctx)}

    assert _PROFESSIONAL_FACT in grounding
    assert supporting == {_INCIDENTAL_FACT, _PROFESSIONAL_FACT}
    assert _INCIDENTAL_FACT not in grounding
    assert grounding == {_PROFESSIONAL_FACT}
