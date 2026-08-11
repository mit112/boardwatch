"""T12 candidate identity, idempotent import merging, and import validation (design §18, §20).

Three properties carry the slice:

- **The importer assigns identity.** A proposed candidate ID is accepted from the caller and
  ignored; the stored ID is derived from `source_record_id | predicate | canonicalized value`.
- **Re-extraction of the same material creates nothing.** Different proposed IDs, different order,
  different grouping, and whitespace-equivalent spellings all collapse onto one candidate. A
  paraphrase deliberately does not.
- **The denominator adds up.** Every enumerated record is dispositioned exactly once, and the
  imported/excluded/review totals reconcile with the exclusion ledger.

Expected candidate IDs are recomputed here through a hand-rolled `hashlib`/`json` path rather than
by calling the production helper, so the derivation cannot drift without a failure.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from boardwatch.profile_bundle.approvals import required_approval_decisions
from boardwatch.profile_bundle.enumerators import (
    BoardwatchResumeEnumerator,
    derive_source_record_id,
)
from boardwatch.profile_bundle.errors import IssueCode
from boardwatch.profile_bundle.imports import (
    CandidateImportError,
    ProposedCandidate,
    build_candidate_package,
    build_source_ledger,
    canonicalize_candidate_value,
    derive_candidate_id,
    enumerate_source,
    merge_candidate_package,
)
from boardwatch.profile_bundle.models.facts import FactValue
from boardwatch.profile_bundle.models.history import ApprovalAction
from boardwatch.profile_bundle.models.imports import (
    CandidatePackage,
    CompleteFileScope,
    Disposition,
    ExclusionLedger,
    ExclusionReason,
    ExclusionRecord,
    SelectedSectionsScope,
)
from boardwatch.profile_bundle.models.policy import (
    PredicateCatalog,
    PredicateSpec,
    SourceKind,
    SourceSpec,
)
from boardwatch.profile_bundle.validation import build_context
from boardwatch.profile_bundle.validation.imports import (
    import_totals,
    imports_completeness,
    validate_imports,
)
from tests.profile_bundle.conftest import SyntheticBundle, blob_reader
from tests.profile_bundle.test_profile_bundle_structural_validation import edit_document

SOURCE = "source.synthetic-example"
COMPLETE = CompleteFileScope(kind="complete_file")

MARKDOWN = (
    "# Overview\n"
    "\n"
    "First overview paragraph.\n"
    "\n"
    "- a bullet\n"
    "\n"
    "## Details\n"
    "\n"
    "Detail paragraph.\n"
)


# --------------------------------------------------------------------------------------
# An independent derivation path
# --------------------------------------------------------------------------------------


def independent_digest(value: object) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def expected_candidate_id(record_id: str, predicate: str, value: dict[str, Any]) -> str:
    return "candidate." + independent_digest(["candidate", record_id, predicate, value])


def value_of(payload: dict[str, Any]) -> FactValue:
    return CandidatePackage.model_validate(
        {
            "candidates_version": 1,
            "candidates": [
                {
                    "candidate_id": "candidate." + "a" * 64,
                    "source_record_id": "source-record." + "b" * 64,
                    "predicate": "project.summary",
                    "canonicalized_typed_value": payload,
                    "original_display_value": "x",
                    "occurrences": [
                        {
                            "source_content_digest": "sha256:" + "c" * 64,
                            "record_content_digest": "sha256:" + "d" * 64,
                        }
                    ],
                }
            ],
        }
    ).candidates[0].canonicalized_typed_value


def predicates(bundle: SyntheticBundle) -> PredicateCatalog:
    catalog = build_context(bundle.draft, mode="draft").index.predicates
    assert catalog is not None
    return catalog


# --------------------------------------------------------------------------------------
# Value canonicalization (§18)
# --------------------------------------------------------------------------------------


def spec(bundle: SyntheticBundle, predicate_id: str) -> Any:
    return predicates(bundle).by_id[predicate_id]


def test_unicode_whitespace_is_collapsed_and_ends_are_trimmed(
    synthetic_bundle: SyntheticBundle,
) -> None:
    canonical = canonicalize_candidate_value(
        value_of({"type": "string", "value": "  Built the\t ingestion   path \n"}),
        spec(synthetic_bundle, "project.summary"),
    )
    assert canonical.value == "Built the ingestion path"  # type: ignore[union-attr]


def test_a_string_is_nfc_normalized(synthetic_bundle: SyntheticBundle) -> None:
    contract = spec(synthetic_bundle, "project.summary")
    decomposed = canonicalize_candidate_value(
        value_of({"type": "string", "value": "cafe\u0301 note"}), contract
    )
    composed = canonicalize_candidate_value(
        value_of({"type": "string", "value": "caf\u00e9 note"}), contract
    )
    assert decomposed == composed


def test_case_is_never_folded_because_no_predicate_declares_case_insensitive_identity(
    synthetic_bundle: SyntheticBundle,
) -> None:
    canonical = canonicalize_candidate_value(
        value_of({"type": "string", "value": "Retry-Safe Ingestion"}),
        spec(synthetic_bundle, "project.summary"),
    )
    assert canonical.value == "Retry-Safe Ingestion"  # type: ignore[union-attr]


def test_a_set_like_list_is_sorted_by_canonical_element_identity(
    synthetic_bundle: SyntheticBundle,
) -> None:
    canonical = canonicalize_candidate_value(
        value_of({"type": "string_list", "values": ["  zebra ", "alpha"]}),
        spec(synthetic_bundle, "application.authorized_regions"),
    )
    assert canonical.values == ("alpha", "zebra")  # type: ignore[union-attr]


def test_an_ordered_list_predicate_retains_its_order(synthetic_bundle: SyntheticBundle) -> None:
    """Set-likeness is read from the predicate's exclusivity, not from the value's type.

    The shipped catalog happens to give every string-list predicate `one_effective_set`, so the
    ordered branch is exercised against a spec built by relaxing exactly that one field —
    otherwise the branch would ship with no test at all."""
    set_like = spec(synthetic_bundle, "application.authorized_regions")
    ordered = PredicateSpec.model_validate(
        {**set_like.model_dump(mode="json"), "exclusivity": "none"}
    )
    canonical = canonicalize_candidate_value(
        value_of({"type": "string_list", "values": ["zebra", "alpha"]}), ordered
    )
    assert canonical.values == ("zebra", "alpha")  # type: ignore[union-attr]


def test_a_value_type_the_predicate_does_not_admit_is_refused(
    synthetic_bundle: SyntheticBundle,
) -> None:
    with pytest.raises(CandidateImportError):
        canonicalize_candidate_value(
            value_of({"type": "integer", "value": 3}),
            spec(synthetic_bundle, "project.summary"),
        )


def test_a_string_outside_an_enumerated_predicates_legal_values_is_refused(
    synthetic_bundle: SyntheticBundle,
) -> None:
    with pytest.raises(CandidateImportError):
        canonicalize_candidate_value(
            value_of({"type": "string", "value": "somewhere-else"}),
            spec(synthetic_bundle, "deployment.environment"),
        )


def test_an_enumerated_predicate_accepts_a_catalogued_value(
    synthetic_bundle: SyntheticBundle,
) -> None:
    canonical = canonicalize_candidate_value(
        value_of({"type": "string", "value": " production "}),
        spec(synthetic_bundle, "deployment.environment"),
    )
    assert canonical.value == "production"  # type: ignore[union-attr]


# --------------------------------------------------------------------------------------
# Derived candidate identity (§18)
# --------------------------------------------------------------------------------------

RECORD = "source-record." + "0" * 64


def test_the_candidate_id_is_the_lowercase_sha256_of_the_canonical_json_array() -> None:
    payload = {"type": "string", "value": "Synthetic project summary"}
    assert derive_candidate_id(RECORD, "project.summary", value_of(payload)) == (
        expected_candidate_id(RECORD, "project.summary", payload)
    )


def test_the_candidate_id_changes_with_each_of_its_three_inputs() -> None:
    base = derive_candidate_id(RECORD, "project.summary", value_of({"type": "string", "value": "a"}))
    assert base != derive_candidate_id(
        "source-record." + "1" * 64, "project.summary", value_of({"type": "string", "value": "a"})
    )
    assert base != derive_candidate_id(
        RECORD, "project.contribution", value_of({"type": "string", "value": "a"})
    )
    assert base != derive_candidate_id(
        RECORD, "project.summary", value_of({"type": "string", "value": "b"})
    )


# --------------------------------------------------------------------------------------
# Enumerating a source into an immutable ledger package (§18)
# --------------------------------------------------------------------------------------


def markdown_spec() -> SourceSpec:
    return SourceSpec(
        source_id=SOURCE,
        source_kind=SourceKind.MARKDOWN_DOCUMENT,
        portable_locator="notes/example.md",
    )


def enumerated() -> Any:
    return enumerate_source(markdown_spec(), MARKDOWN.encode("utf-8"), scope=COMPLETE)


def test_enumerate_source_binds_the_adapter_the_closed_table_names() -> None:
    source = enumerated()
    assert source.enumerator_id == "markdown-blocks-v1"
    assert source.enumerator_version == 1
    assert source.source_content_digest == "sha256:" + hashlib.sha256(
        MARKDOWN.encode("utf-8")
    ).hexdigest()


def test_enumerate_source_refuses_a_scope_the_source_kind_does_not_allow() -> None:
    with pytest.raises(CandidateImportError):
        enumerate_source(
            markdown_spec(),
            MARKDOWN.encode("utf-8"),
            scope=SelectedSectionsScope(kind="selected_sections", locators=("Overview",)),
        )


def test_repository_markdown_requires_a_selected_sections_scope() -> None:
    repository = SourceSpec(
        source_id=SOURCE,
        source_kind=SourceKind.REPOSITORY_MARKDOWN,
        portable_locator="project/README.md",
    )
    with pytest.raises(CandidateImportError):
        enumerate_source(repository, MARKDOWN.encode("utf-8"), scope=COMPLETE)


def test_the_ledger_source_row_lists_every_record_in_adapter_order() -> None:
    source = enumerated()
    assert source.ledger_source.source_record_ids == tuple(
        record.source_record_id for record in source.records
    )


def test_the_enumerated_package_is_immutable() -> None:
    source = enumerated()
    with pytest.raises((AttributeError, TypeError)):
        source.records = ()  # type: ignore[misc]


# --------------------------------------------------------------------------------------
# Building a candidate package: the importer assigns identity
# --------------------------------------------------------------------------------------


def proposal(record_id: str, value: str, *, proposed_id: str | None = "candidate.llm-invented") -> (
    ProposedCandidate
):
    return ProposedCandidate(
        source_record_id=record_id,
        predicate="project.summary",
        value=value_of({"type": "string", "value": value}),
        original_display_value=value,
        proposed_candidate_id=proposed_id,
    )


def package_for(
    bundle: SyntheticBundle, proposals: list[ProposedCandidate], source: Any = None
) -> CandidatePackage:
    return build_candidate_package(
        (source or enumerated(),), proposals, predicates=predicates(bundle)
    )


def first_record() -> str:
    return enumerated().records[0].source_record_id


def test_a_proposed_candidate_id_is_accepted_and_ignored(
    synthetic_bundle: SyntheticBundle,
) -> None:
    package = package_for(synthetic_bundle, [proposal(first_record(), "A summary")])
    assert package.candidates[0].candidate_id != "candidate.llm-invented"
    assert package.candidates[0].candidate_id == derive_candidate_id(
        first_record(),
        "project.summary",
        value_of({"type": "string", "value": "A summary"}),
    )


def test_the_original_display_value_is_retained_beside_the_canonical_one(
    synthetic_bundle: SyntheticBundle,
) -> None:
    package = package_for(synthetic_bundle, [proposal(first_record(), "  A   summary  ")])
    candidate = package.candidates[0]
    assert candidate.original_display_value == "  A   summary  "
    assert candidate.canonicalized_typed_value.value == "A summary"  # type: ignore[union-attr]


def test_each_candidate_occurrence_stores_both_source_and_record_digests(
    synthetic_bundle: SyntheticBundle,
) -> None:
    source = enumerated()
    package = package_for(synthetic_bundle, [proposal(first_record(), "A summary")], source)
    occurrence = package.candidates[0].occurrences[0]
    assert occurrence.source_content_digest == source.source_content_digest
    assert occurrence.record_content_digest == source.records[0].record_content_digest


def test_the_same_proposal_twice_yields_one_candidate_with_one_occurrence(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Two extractions of one assertion from one record are the same sighting. Recording the pair
    twice would inflate lineage, and the model refuses it outright."""
    proposals = [proposal(first_record(), "A summary"), proposal(first_record(), " A summary ")]
    package = package_for(synthetic_bundle, proposals)
    assert len(package.candidates) == 1
    assert len(package.candidates[0].occurrences) == 1


def test_a_proposal_naming_a_record_outside_the_ledger_package_is_refused(
    synthetic_bundle: SyntheticBundle,
) -> None:
    with pytest.raises(CandidateImportError):
        package_for(synthetic_bundle, [proposal("source-record." + "9" * 64, "A summary")])


def test_an_unknown_predicate_is_refused(synthetic_bundle: SyntheticBundle) -> None:
    unknown = ProposedCandidate(
        source_record_id=first_record(),
        predicate="invented.predicate",
        value=value_of({"type": "string", "value": "A summary"}),
        original_display_value="A summary",
    )
    with pytest.raises(CandidateImportError):
        package_for(synthetic_bundle, [unknown])


def test_the_llm_cannot_enumerate_records_only_annotate_them(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Every candidate must attach to a record the adapter produced; the proposal carries no
    locator, so there is no route by which extraction can invent a denominator unit."""
    assert not hasattr(proposal(first_record(), "A summary"), "normalized_locator")


# --------------------------------------------------------------------------------------
# Idempotence (§18, §21)
# --------------------------------------------------------------------------------------


def test_re_extracting_identical_input_creates_zero_new_candidates(
    synthetic_bundle: SyntheticBundle,
) -> None:
    package = package_for(synthetic_bundle, [proposal(first_record(), "A summary")])
    merged = merge_candidate_package(package, package)
    assert merged.added == ()
    assert merged.appended_occurrences == ()
    assert merged.unchanged == (package.candidates[0].candidate_id,)
    assert merged.package == package


def test_merging_is_idempotent_under_repetition(synthetic_bundle: SyntheticBundle) -> None:
    package = package_for(synthetic_bundle, [proposal(first_record(), "A summary")])
    once = merge_candidate_package(package, package).package
    twice = merge_candidate_package(once, package).package
    assert once == twice


def test_a_different_proposed_id_still_collapses_onto_one_candidate(
    synthetic_bundle: SyntheticBundle,
) -> None:
    first = package_for(
        synthetic_bundle, [proposal(first_record(), "A summary", proposed_id="candidate.one")]
    )
    second = package_for(
        synthetic_bundle, [proposal(first_record(), "A summary", proposed_id="candidate.two")]
    )
    merged = merge_candidate_package(first, second)
    assert len(merged.package.candidates) == 1
    assert merged.added == ()


def test_whitespace_equivalent_values_collapse_onto_one_candidate(
    synthetic_bundle: SyntheticBundle,
) -> None:
    first = package_for(synthetic_bundle, [proposal(first_record(), "A summary")])
    second = package_for(synthetic_bundle, [proposal(first_record(), " A   summary ")])
    merged = merge_candidate_package(first, second)
    assert len(merged.package.candidates) == 1
    assert merged.added == ()


def test_a_paraphrase_is_deliberately_outside_the_equivalence_class(
    synthetic_bundle: SyntheticBundle,
) -> None:
    first = package_for(synthetic_bundle, [proposal(first_record(), "A summary")])
    second = package_for(synthetic_bundle, [proposal(first_record(), "A short summary")])
    merged = merge_candidate_package(first, second)
    assert len(merged.package.candidates) == 2
    assert len(merged.added) == 1


def test_extraction_order_and_grouping_do_not_change_the_result(
    synthetic_bundle: SyntheticBundle,
) -> None:
    source = enumerated()
    one = proposal(source.records[0].source_record_id, "First")
    two = proposal(source.records[1].source_record_id, "Second")
    together = package_for(synthetic_bundle, [one, two], source)
    reversed_order = package_for(synthetic_bundle, [two, one], source)
    grouped = merge_candidate_package(
        package_for(synthetic_bundle, [one], source),
        package_for(synthetic_bundle, [two], source),
    ).package
    assert together == reversed_order == grouped


def test_a_changed_source_digest_with_the_same_value_appends_one_occurrence(
    synthetic_bundle: SyntheticBundle,
) -> None:
    package = package_for(synthetic_bundle, [proposal(first_record(), "A summary")])
    edited = enumerate_source(
        markdown_spec(),
        MARKDOWN.replace("First overview paragraph.", "First overview paragraph, revised.").encode(
            "utf-8"
        ),
        scope=COMPLETE,
    )
    later = package_for(synthetic_bundle, [proposal(first_record(), "A summary")], edited)
    merged = merge_candidate_package(package, later)

    assert merged.added == ()
    assert merged.appended_occurrences == (package.candidates[0].candidate_id,)
    assert len(merged.package.candidates) == 1
    assert len(merged.package.candidates[0].occurrences) == 2


def test_an_occurrence_pair_is_unique_within_one_candidate(
    synthetic_bundle: SyntheticBundle,
) -> None:
    package = package_for(synthetic_bundle, [proposal(first_record(), "A summary")])
    merged = merge_candidate_package(package, package).package
    pairs = [
        (occurrence.source_content_digest, occurrence.record_content_digest)
        for occurrence in merged.candidates[0].occurrences
    ]
    assert len(pairs) == len(set(pairs)) == 1


def test_merging_never_overwrites_a_retained_display_value(
    synthetic_bundle: SyntheticBundle,
) -> None:
    first = package_for(synthetic_bundle, [proposal(first_record(), "A summary")])
    second = package_for(synthetic_bundle, [proposal(first_record(), " A summary ")])
    merged = merge_candidate_package(first, second).package
    assert merged.candidates[0].original_display_value == "A summary"


def test_a_forged_candidate_id_is_refused_rather_than_merged(
    synthetic_bundle: SyntheticBundle,
) -> None:
    package = package_for(synthetic_bundle, [proposal(first_record(), "A summary")])
    forged = CandidatePackage.model_validate(
        {
            "candidates_version": 1,
            "candidates": [
                {
                    **package.candidates[0].model_dump(mode="json"),
                    "predicate": "project.contribution",
                }
            ],
        }
    )
    with pytest.raises(CandidateImportError):
        merge_candidate_package(package, forged)


def test_merging_packages_of_different_versions_is_refused(
    synthetic_bundle: SyntheticBundle,
) -> None:
    package = package_for(synthetic_bundle, [proposal(first_record(), "A summary")])
    other = CandidatePackage.model_validate(
        {**package.model_dump(mode="json"), "candidates_version": 2}
    )
    with pytest.raises(CandidateImportError):
        merge_candidate_package(package, other)


# --------------------------------------------------------------------------------------
# The ledger: dispositions and arithmetic (§18)
# --------------------------------------------------------------------------------------


def built_ledger(
    bundle: SyntheticBundle, *, exclusions: dict[str, ExclusionRecord] | None = None
) -> Any:
    source = enumerated()
    package = package_for(bundle, [proposal(source.records[0].source_record_id, "A summary")], source)
    return source, package, build_source_ledger((source,), package, exclusions=exclusions or {})


def test_a_record_with_candidates_is_imported_and_names_them(
    synthetic_bundle: SyntheticBundle,
) -> None:
    source, package, ledger = built_ledger(synthetic_bundle)
    record = ledger.records[0]
    assert record.disposition is Disposition.IMPORTED
    assert record.candidate_ids == (package.candidates[0].candidate_id,)


def test_a_record_with_an_exclusion_is_excluded(synthetic_bundle: SyntheticBundle) -> None:
    source = enumerated()
    target = source.records[1].source_record_id
    _, _, ledger = built_ledger(
        synthetic_bundle,
        exclusions={
            target: ExclusionRecord(
                source_record_id=target,
                reason=ExclusionReason.ADMINISTRATIVE_NOISE,
                rationale="Navigation text with no professional assertion.",
            )
        },
    )
    excluded = [r for r in ledger.records if r.source_record_id == target]
    assert excluded[0].disposition is Disposition.EXCLUDED


def test_an_undispositioned_record_becomes_review_required(
    synthetic_bundle: SyntheticBundle,
) -> None:
    _, _, ledger = built_ledger(synthetic_bundle)
    assert any(r.disposition is Disposition.REVIEW_REQUIRED for r in ledger.records)


def test_every_enumerated_record_appears_exactly_once(
    synthetic_bundle: SyntheticBundle,
) -> None:
    source, _, ledger = built_ledger(synthetic_bundle)
    ids = [record.source_record_id for record in ledger.records]
    assert ids == list(source.ledger_source.source_record_ids)
    assert len(ids) == len(set(ids))


def test_the_disposition_counts_sum_to_the_denominator(
    synthetic_bundle: SyntheticBundle,
) -> None:
    _, _, ledger = built_ledger(synthetic_bundle)
    counts = ledger.counts_by_disposition()
    assert sum(counts.values()) == ledger.record_count == len(ledger.records)


@pytest.mark.parametrize("reason", list(ExclusionReason))
def test_every_closed_exclusion_reason_works(
    synthetic_bundle: SyntheticBundle, reason: ExclusionReason
) -> None:
    source = enumerated()
    target = source.records[1].source_record_id
    _, _, ledger = built_ledger(
        synthetic_bundle,
        exclusions={
            target: ExclusionRecord(
                source_record_id=target, reason=reason, rationale="A synthetic rationale."
            )
        },
    )
    assert ledger.counts_by_disposition()[Disposition.EXCLUDED] == 1


def test_import_totals_reconcile_the_ledger_with_the_exclusion_document(
    synthetic_bundle: SyntheticBundle,
) -> None:
    source = enumerated()
    target = source.records[1].source_record_id
    exclusion = ExclusionRecord(
        source_record_id=target,
        reason=ExclusionReason.NON_PROFESSIONAL,
        rationale="A synthetic rationale.",
    )
    _, _, ledger = built_ledger(synthetic_bundle, exclusions={target: exclusion})
    totals = import_totals(
        ledger, ExclusionLedger(exclusions_version=1, exclusions=(exclusion,))
    )
    assert totals.denominator == len(ledger.records)
    assert totals.dispositioned == totals.denominator
    assert totals.exclusions_by_reason[ExclusionReason.NON_PROFESSIONAL] == 1


# --------------------------------------------------------------------------------------
# Approved scope discriminants (§18)
# --------------------------------------------------------------------------------------


def test_the_first_three_source_kinds_take_a_complete_file_scope() -> None:
    resume = BoardwatchResumeEnumerator(source_id=SOURCE)
    assert resume.id == "boardwatch-resume-v1"
    for kind in (
        SourceKind.BOARDWATCH_RESUME,
        SourceKind.MARKDOWN_DOCUMENT,
        SourceKind.STRUCTURED_OBJECTS,
    ):
        spec_for_kind = SourceSpec(
            source_id=SOURCE, source_kind=kind, portable_locator="a/b"
        )
        with pytest.raises(CandidateImportError):
            enumerate_source(
                spec_for_kind,
                b"alpha: first\n",
                scope=SelectedSectionsScope(kind="selected_sections", locators=("x",)),
            )


def test_widening_a_selected_scope_changes_the_owner_approval_target(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§18 binds `approve_source_scope` to the ledger's exact scope object, so adding a locator
    must produce a different required approval digest — otherwise scope grows for free."""
    from tests.profile_bundle.conftest import parse_documents

    before = required_approval_decisions(parse_documents(synthetic_bundle.draft), None)

    def widen(data: Any) -> None:
        for entry in data["sources"]:
            scope = entry["approved_scope"]
            if scope["kind"] == "selected_sections":
                scope["locators"] = [*scope["locators"], "readme/deployment"]

    edit_document(synthetic_bundle, "imports/source-ledger.yaml", widen)
    after = required_approval_decisions(parse_documents(synthetic_bundle.draft), None)

    scoped_before = {
        d.target_record_id: d.target_content_digest
        for d in before
        if d.action is ApprovalAction.APPROVE_SOURCE_SCOPE
    }
    scoped_after = {
        d.target_record_id: d.target_content_digest
        for d in after
        if d.action is ApprovalAction.APPROVE_SOURCE_SCOPE
    }
    assert scoped_before["source.synthetic-repository"] != scoped_after["source.synthetic-repository"]


def test_owner_excluded_is_approval_gated_where_the_gate_actually_lands(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The gate lives in T11's derivation, not in a second copy here: an `owner_excluded`
    exclusion produces a required `approve_source_record_exclusion` decision, and a closed-reason
    exclusion does not."""
    from tests.profile_bundle.conftest import parse_documents

    def owner_excluded(data: Any) -> None:
        data["exclusions"][0]["reason"] = "owner_excluded"

    assert not [
        d
        for d in required_approval_decisions(parse_documents(synthetic_bundle.draft), None)
        if d.action is ApprovalAction.APPROVE_SOURCE_RECORD_EXCLUSION
    ]
    edit_document(synthetic_bundle, "imports/exclusions.yaml", owner_excluded)
    gated = [
        d
        for d in required_approval_decisions(parse_documents(synthetic_bundle.draft), None)
        if d.action is ApprovalAction.APPROVE_SOURCE_RECORD_EXCLUSION
    ]
    assert len(gated) == 1
    assert gated[0].resulting_state == "owner_excluded"


# --------------------------------------------------------------------------------------
# validate_imports over a real tree (§20)
# --------------------------------------------------------------------------------------


def findings(bundle: SyntheticBundle) -> tuple[Any, ...]:
    ctx = build_context(bundle.draft, mode="draft", blobs=blob_reader(), bundle_root=bundle.root)
    return validate_imports(ctx)


def codes(found: tuple[Any, ...]) -> list[str]:
    return sorted(finding.code for finding in found)


def test_the_comprehensive_example_has_no_import_errors(
    synthetic_bundle: SyntheticBundle,
) -> None:
    assert findings(synthetic_bundle) == ()


def test_the_example_actually_exercises_the_layer_it_is_checking(
    synthetic_bundle: SyntheticBundle,
) -> None:
    ctx = build_context(synthetic_bundle.draft, mode="draft")
    ledger = ctx.index.source_ledger
    assert ledger is not None
    counts = ledger.counts_by_disposition()
    assert counts[Disposition.IMPORTED] and counts[Disposition.EXCLUDED]
    assert any(
        source.approved_scope.kind == "selected_sections" for source in ledger.sources
    )


def test_an_enumerator_that_does_not_pair_with_the_source_kind_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    def swap(data: Any) -> None:
        data["sources"][0]["enumerator_id"] = "structured-objects-v1"

    edit_document(synthetic_bundle, "imports/source-ledger.yaml", swap)
    assert IssueCode.IMPORT_ENUMERATOR_MISMATCH in codes(findings(synthetic_bundle))


def test_a_wrong_enumerator_version_is_reported(synthetic_bundle: SyntheticBundle) -> None:
    def swap(data: Any) -> None:
        data["sources"][0]["enumerator_version"] = 2

    edit_document(synthetic_bundle, "imports/source-ledger.yaml", swap)
    assert IssueCode.IMPORT_ENUMERATOR_MISMATCH in codes(findings(synthetic_bundle))


def test_a_ledger_source_absent_from_the_source_catalog_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    def drop(data: Any) -> None:
        data["sources"] = [s for s in data["sources"] if s["source_id"] != "source.synthetic-notes"]

    edit_document(synthetic_bundle, "policy/sources.yaml", drop)
    assert IssueCode.IMPORT_ENUMERATOR_MISMATCH in codes(findings(synthetic_bundle))


def test_a_complete_file_scope_on_a_repository_source_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    def narrow(data: Any) -> None:
        for entry in data["sources"]:
            if entry["source_id"] == "source.synthetic-repository":
                entry["approved_scope"] = {"kind": "complete_file"}

    edit_document(synthetic_bundle, "imports/source-ledger.yaml", narrow)
    assert IssueCode.IMPORT_SCOPE_INVALID in codes(findings(synthetic_bundle))


def test_a_selected_sections_scope_on_a_complete_file_source_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    def widen(data: Any) -> None:
        for entry in data["sources"]:
            if entry["source_id"] == "source.synthetic-notes":
                entry["approved_scope"] = {
                    "kind": "selected_sections",
                    "locators": ["packet-pantry"],
                }

    edit_document(synthetic_bundle, "imports/source-ledger.yaml", widen)
    assert IssueCode.IMPORT_SCOPE_INVALID in codes(findings(synthetic_bundle))


def test_a_scope_locator_that_is_not_normalized_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    def denormalize(data: Any) -> None:
        for entry in data["sources"]:
            scope = entry["approved_scope"]
            if scope["kind"] == "selected_sections":
                scope["locators"] = ["readme/../architecture"]

    edit_document(synthetic_bundle, "imports/source-ledger.yaml", denormalize)
    assert IssueCode.IMPORT_SCOPE_INVALID in codes(findings(synthetic_bundle))


def test_a_record_id_that_is_not_the_derived_one_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The importer, not an LLM, assigns identity. A ledger whose IDs are not the derived ones
    has had its denominator renumbered by whatever wrote it."""
    forged = "source-record." + "f" * 64

    def renumber(data: Any) -> None:
        original = data["records"][0]["source_record_id"]
        data["records"][0]["source_record_id"] = forged
        data["records"][0]["candidate_ids"] = []
        data["records"][0]["disposition"] = "review_required"
        for entry in data["sources"]:
            entry["source_record_ids"] = [
                forged if item == original else item for item in entry["source_record_ids"]
            ]

    edit_document(synthetic_bundle, "imports/source-ledger.yaml", renumber)
    edit_document(
        synthetic_bundle,
        "imports/candidates.yaml",
        lambda data: data.__setitem__("candidates", data["candidates"][1:]),
    )
    assert IssueCode.IMPORT_ENUMERATOR_MISMATCH in codes(findings(synthetic_bundle))


def test_a_record_locator_that_is_not_normalized_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    def denormalize(data: Any) -> None:
        record = data["records"][2]
        locator = "packet pantry/stack/paragraph-9"
        record["normalized_locator"] = locator
        new_id = derive_source_record_id(record["source_id"], locator)
        original = record["source_record_id"]
        record["source_record_id"] = new_id
        for entry in data["sources"]:
            entry["source_record_ids"] = [
                new_id if item == original else item for item in entry["source_record_ids"]
            ]

    edit_document(synthetic_bundle, "imports/source-ledger.yaml", denormalize)
    assert IssueCode.IMPORT_ENUMERATOR_MISMATCH in codes(findings(synthetic_bundle))


def test_two_records_for_one_logical_unit_are_reported_as_a_duplicate(
    synthetic_bundle: SyntheticBundle,
) -> None:
    def duplicate(data: Any) -> None:
        clone = dict(data["records"][2])
        clone["source_record_id"] = "source-record." + "e" * 64
        data["records"].append(clone)
        for entry in data["sources"]:
            if entry["source_id"] == clone["source_id"]:
                entry["source_record_ids"] = [*entry["source_record_ids"], clone["source_record_id"]]

    edit_document(synthetic_bundle, "imports/source-ledger.yaml", duplicate)
    assert IssueCode.IMPORT_DUPLICATE_RECORD in codes(findings(synthetic_bundle))


def test_an_excluded_record_without_an_exclusion_entry_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    edit_document(
        synthetic_bundle,
        "imports/exclusions.yaml",
        lambda data: data.__setitem__("exclusions", []),
    )
    found = codes(findings(synthetic_bundle))
    assert IssueCode.IMPORT_MISSING_EXCLUSION in found
    assert IssueCode.IMPORT_DENOMINATOR_MISMATCH in found


def test_an_exclusion_for_a_record_that_is_not_excluded_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Moving the exclusion onto the review-required record breaks both directions at once, so the
    assertion names the record and the document rather than only the code."""
    review_required = (
        "source-record.5e0521371b368f834f16acafdc2d96a63e6ce94c330e8c51bf5eb2d9e09256ce"
    )

    def move(data: Any) -> None:
        data["exclusions"][0]["source_record_id"] = review_required

    edit_document(synthetic_bundle, "imports/exclusions.yaml", move)
    reported = [
        finding
        for finding in findings(synthetic_bundle)
        if finding.code == IssueCode.IMPORT_MISSING_EXCLUSION
        and finding.record_id == review_required
    ]
    assert len(reported) == 1
    assert reported[0].path == "imports/exclusions.yaml"


def test_an_imported_record_naming_another_records_candidate_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    def crosswire(data: Any) -> None:
        data["records"][0]["candidate_ids"] = [
            "candidate.ff1a028b491c3395ad8789bc76620a33c31676a10519819f409b4a711045c7ed"
        ]

    edit_document(synthetic_bundle, "imports/source-ledger.yaml", crosswire)
    assert IssueCode.IMPORT_MISSING_CANDIDATE in codes(findings(synthetic_bundle))


# --------------------------------------------------------------------------------------
# Import completeness blockers (§20.5)
# --------------------------------------------------------------------------------------


def blockers(bundle: SyntheticBundle) -> tuple[Any, ...]:
    ctx = build_context(bundle.draft, mode="draft", blobs=blob_reader(), bundle_root=bundle.root)
    return imports_completeness(ctx)


def test_a_review_required_record_is_a_blocker_not_an_error(
    synthetic_bundle: SyntheticBundle,
) -> None:
    found = blockers(synthetic_bundle)
    undispositioned = [
        f for f in found if f.code == IssueCode.IMPORT_RECORD_UNDISPOSITIONED
    ]
    assert len(undispositioned) == 1
    assert undispositioned[0].tier == "blocker"
    assert IssueCode.IMPORT_RECORD_UNDISPOSITIONED not in codes(findings(synthetic_bundle))


def test_a_catalogued_source_that_is_never_enumerated_is_an_unexplained_blocker(
    synthetic_bundle: SyntheticBundle,
) -> None:
    unexplained = [f for f in blockers(synthetic_bundle) if f.code == IssueCode.IMPORT_UNEXPLAINED_RECORD]
    assert [f.record_id for f in unexplained] == ["source.synthetic-private-record"]
    assert unexplained[0].tier == "blocker"


def test_enumerating_the_missing_source_clears_the_unexplained_blocker(
    synthetic_bundle: SyntheticBundle,
) -> None:
    def drop(data: Any) -> None:
        data["sources"] = [
            s for s in data["sources"] if s["source_id"] != "source.synthetic-private-record"
        ]

    edit_document(synthetic_bundle, "policy/sources.yaml", drop)
    assert not [
        f for f in blockers(synthetic_bundle) if f.code == IssueCode.IMPORT_UNEXPLAINED_RECORD
    ]
