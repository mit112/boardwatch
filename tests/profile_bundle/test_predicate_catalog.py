"""The seeded starter predicate catalog and its §5.2 audit gate (Slice A).

The mechanical invariants catch the defect class the Task-1 audit found in an unaudited catalog: a
dead enum member, an unreachable grounding guard, and an unavailable version silently supplying an
empty vocabulary. Invariant 3 (§5.1's behavioural grounding assertion) and invariant 4 (package-level
reachability against the builtin extraction mapping) are owed and tracked in STATE — the first needs a
builtin-catalog-backed grounding context, the second needs the builtin mapping that Slice B seeds.
"""

from __future__ import annotations

import pathlib

import pytest

from boardwatch.profile_bundle import predicate_catalog
from boardwatch.profile_bundle.drafts import init_draft
from boardwatch.profile_bundle.errors import UnsupportedPredicateCatalogError
from boardwatch.profile_bundle.models.base import Surface, UsageContext, VerificationBasis
from boardwatch.profile_bundle.validation import load_documents

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
    """The deterministic mapping (§6.2a-proof) resolves to exactly these; each must be in the
    catalog or `build_candidate_package` raises. `project.name` is the row the audit added."""
    needed = {
        "person.professional_name",
        "technology.used",
        "employment.organization",
        "employment.title",
        "employment.date_range",
        "employment.accomplishment",
        "entity.location",
        "project.name",
        "project.start_date",
        "project.end_date",
        "project.contribution",
    }
    assert needed <= set(BUILTIN.by_id)


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
