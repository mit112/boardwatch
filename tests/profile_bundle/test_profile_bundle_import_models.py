"""Import ledger, candidate package, and exclusion shapes (design §18).

The Gate B denominator is `len(source-ledger.records)`, and the arithmetic that has to hold is
"imported + excluded + review_required == denominator, with zero missing or duplicate record IDs".
Every rule tested here exists to make that number mean something:

- `record_count` is derived, never authored, so there is no second place for it to disagree;
- an `imported` record must name a candidate, or a record counted as imported contributes nothing;
- `sources[].source_record_ids` must equal its records exactly, in adapter order, so a source cannot
  claim a different denominator from the one the ledger actually holds;
- a content digest is *occurrence lineage*, not identity, so re-enumerating changed bytes at the same
  locator appends a sighting instead of churning the denominator.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from boardwatch.profile_bundle.models.imports import (
    ApprovedScope,
    CandidatePackage,
    CandidateRecord,
    CompleteFileScope,
    Disposition,
    ExclusionLedger,
    ExclusionReason,
    SelectedSectionsScope,
    SourceLedger,
    SourceLedgerRecord,
)

SCOPE_ADAPTER = TypeAdapter(ApprovedScope)
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
RECORD_ONE = "source-record." + "1" * 64
RECORD_TWO = "source-record." + "2" * 64
CANDIDATE_ONE = "candidate." + "3" * 64
CANDIDATE_TWO = "candidate." + "4" * 64


def _ledger_record(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_record_id": RECORD_ONE,
        "source_id": "source.synthetic-notes",
        "normalized_locator": "projects/example/summary/paragraph-1",
        "disposition": "imported",
        "candidate_ids": [CANDIDATE_ONE],
    }
    payload.update(overrides)
    return payload


def _ledger(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "ledger_version": 1,
        "sources": [
            {
                "source_id": "source.synthetic-notes",
                "enumerator_id": "markdown-blocks-v1",
                "enumerator_version": 1,
                "source_content_digest": DIGEST_A,
                "approved_scope": {"kind": "complete_file"},
                "source_record_ids": [RECORD_ONE],
            }
        ],
        "records": [_ledger_record()],
    }
    payload.update(overrides)
    return payload


def _candidate(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "candidate_id": CANDIDATE_ONE,
        "source_record_id": RECORD_ONE,
        "predicate": "project.summary",
        "canonicalized_typed_value": {"type": "string", "value": "Synthetic project summary"},
        "original_display_value": "Synthetic project summary",
        "occurrences": [
            {"source_content_digest": DIGEST_A, "record_content_digest": DIGEST_B}
        ],
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------------------
# approved scope
# --------------------------------------------------------------------------------------


def test_approved_scope_is_a_discriminated_object_never_a_scalar() -> None:
    assert isinstance(SCOPE_ADAPTER.validate_python({"kind": "complete_file"}), CompleteFileScope)
    sections = SCOPE_ADAPTER.validate_python(
        {"kind": "selected_sections", "locators": ["readme/architecture"]}
    )
    assert isinstance(sections, SelectedSectionsScope)
    with pytest.raises(ValidationError):
        SCOPE_ADAPTER.validate_python("complete_file")


def test_complete_file_scope_carries_no_locators() -> None:
    with pytest.raises(ValidationError):
        SCOPE_ADAPTER.validate_python({"kind": "complete_file", "locators": ["a"]})


def test_selected_sections_needs_at_least_one_unique_locator() -> None:
    with pytest.raises(ValidationError):
        SCOPE_ADAPTER.validate_python({"kind": "selected_sections", "locators": []})
    with pytest.raises(ValidationError):
        SCOPE_ADAPTER.validate_python({"kind": "selected_sections", "locators": ["a", "a"]})


def test_selected_section_order_is_preserved_because_it_binds_an_owner_approval() -> None:
    """Reordering the scope changes the `approve_source_scope` target digest, deliberately."""
    scope = SCOPE_ADAPTER.validate_python(
        {"kind": "selected_sections", "locators": ["zeta", "alpha"]}
    )
    assert isinstance(scope, SelectedSectionsScope)
    assert scope.locators == ("zeta", "alpha")


# --------------------------------------------------------------------------------------
# ledger arithmetic
# --------------------------------------------------------------------------------------


def test_dispositions_are_the_closed_three() -> None:
    assert {member.value for member in Disposition} == {
        "imported",
        "excluded",
        "review_required",
    }


def test_record_count_is_derived_and_never_authored() -> None:
    assert "record_count" not in SourceLedger.model_fields
    with pytest.raises(ValidationError):
        SourceLedger.model_validate({**_ledger(), "record_count": 1})
    assert SourceLedger.model_validate(_ledger()).record_count == 1


def test_disposition_counts_sum_to_the_denominator() -> None:
    ledger = SourceLedger.model_validate(
        _ledger(
            sources=[
                {
                    "source_id": "source.synthetic-notes",
                    "enumerator_id": "markdown-blocks-v1",
                    "enumerator_version": 1,
                    "source_content_digest": DIGEST_A,
                    "approved_scope": {"kind": "complete_file"},
                    "source_record_ids": [RECORD_ONE, RECORD_TWO],
                }
            ],
            records=[
                _ledger_record(),
                _ledger_record(
                    source_record_id=RECORD_TWO, disposition="excluded", candidate_ids=[]
                ),
            ],
        )
    )
    counts = ledger.counts_by_disposition()
    assert sum(counts.values()) == ledger.record_count == 2
    assert counts[Disposition.IMPORTED] == 1
    assert counts[Disposition.EXCLUDED] == 1
    assert counts[Disposition.REVIEW_REQUIRED] == 0


def test_an_imported_record_must_name_at_least_one_candidate() -> None:
    with pytest.raises(ValidationError):
        SourceLedgerRecord.model_validate(_ledger_record(candidate_ids=[]))


def test_a_non_imported_record_must_name_no_candidate() -> None:
    """A record excluded but still claiming candidates would be counted out and used in."""
    with pytest.raises(ValidationError):
        SourceLedgerRecord.model_validate(_ledger_record(disposition="excluded"))
    with pytest.raises(ValidationError):
        SourceLedgerRecord.model_validate(_ledger_record(disposition="review_required"))
    assert SourceLedgerRecord.model_validate(
        _ledger_record(disposition="review_required", candidate_ids=[])
    ).disposition is Disposition.REVIEW_REQUIRED


def test_per_source_id_lists_must_match_the_records_exactly_and_in_order() -> None:
    two_records = [
        _ledger_record(),
        _ledger_record(source_record_id=RECORD_TWO, candidate_ids=[CANDIDATE_TWO]),
    ]
    source = {
        "source_id": "source.synthetic-notes",
        "enumerator_id": "markdown-blocks-v1",
        "enumerator_version": 1,
        "source_content_digest": DIGEST_A,
        "approved_scope": {"kind": "complete_file"},
        "source_record_ids": [RECORD_ONE, RECORD_TWO],
    }
    assert SourceLedger.model_validate(
        _ledger(sources=[source], records=two_records)
    ).record_count == 2

    reordered = {**source, "source_record_ids": [RECORD_TWO, RECORD_ONE]}
    with pytest.raises(ValidationError):
        SourceLedger.model_validate(_ledger(sources=[reordered], records=two_records))

    missing = {**source, "source_record_ids": [RECORD_ONE]}
    with pytest.raises(ValidationError):
        SourceLedger.model_validate(_ledger(sources=[missing], records=two_records))

    extra = {**source, "source_record_ids": [RECORD_ONE, RECORD_TWO, "source-record." + "5" * 64]}
    with pytest.raises(ValidationError):
        SourceLedger.model_validate(_ledger(sources=[extra], records=two_records))


def test_a_duplicate_source_record_id_is_refused() -> None:
    with pytest.raises(ValidationError):
        SourceLedger.model_validate(
            _ledger(
                sources=[
                    {
                        "source_id": "source.synthetic-notes",
                        "enumerator_id": "markdown-blocks-v1",
                        "enumerator_version": 1,
                        "source_content_digest": DIGEST_A,
                        "approved_scope": {"kind": "complete_file"},
                        "source_record_ids": [RECORD_ONE, RECORD_ONE],
                    }
                ],
                records=[_ledger_record(), _ledger_record()],
            )
        )


def test_a_record_naming_an_unenumerated_source_is_refused() -> None:
    with pytest.raises(ValidationError):
        SourceLedger.model_validate(
            _ledger(records=[_ledger_record(source_id="source.never-registered")])
        )


def test_the_ledger_does_not_repeat_policy_owned_source_metadata() -> None:
    """§18: the two documents may not repeat the same metadata fields."""
    from boardwatch.profile_bundle.models.imports import SourceLedgerSource

    for policy_owned in ("source_kind", "portable_locator"):
        assert policy_owned not in SourceLedgerSource.model_fields


def test_an_empty_ledger_is_legal() -> None:
    ledger = SourceLedger.model_validate({"ledger_version": 1, "sources": [], "records": []})
    assert ledger.record_count == 0


# --------------------------------------------------------------------------------------
# candidates
# --------------------------------------------------------------------------------------


def test_a_candidate_parses_with_its_typed_value_and_one_occurrence() -> None:
    candidate = CandidateRecord.model_validate(_candidate())
    assert candidate.canonicalized_typed_value.type == "string"
    assert candidate.original_display_value == "Synthetic project summary"


def test_a_candidate_needs_at_least_one_occurrence() -> None:
    with pytest.raises(ValidationError):
        CandidateRecord.model_validate(_candidate(occurrences=[]))


def test_occurrence_pairs_are_unique_within_one_candidate() -> None:
    pair = {"source_content_digest": DIGEST_A, "record_content_digest": DIGEST_B}
    with pytest.raises(ValidationError):
        CandidateRecord.model_validate(_candidate(occurrences=[pair, dict(pair)]))


def test_a_changed_record_digest_is_a_new_occurrence_not_a_new_candidate() -> None:
    """Lineage accumulates; identity does not move, which is what keeps the denominator stable."""
    candidate = CandidateRecord.model_validate(
        _candidate(
            occurrences=[
                {"source_content_digest": DIGEST_A, "record_content_digest": DIGEST_B},
                {"source_content_digest": DIGEST_B, "record_content_digest": DIGEST_A},
            ]
        )
    )
    assert candidate.candidate_id == CANDIDATE_ONE
    assert len(candidate.occurrences) == 2


def test_candidate_ids_are_unique_in_the_package() -> None:
    with pytest.raises(ValidationError):
        CandidatePackage.model_validate(
            {"candidates_version": 1, "candidates": [_candidate(), _candidate()]}
        )


def test_candidate_references_are_typed() -> None:
    with pytest.raises(ValidationError):
        CandidateRecord.model_validate(_candidate(source_record_id="source." + "1" * 64))
    with pytest.raises(ValidationError):
        CandidateRecord.model_validate(_candidate(candidate_id=RECORD_ONE))


def test_candidate_original_display_value_is_retained_separately() -> None:
    """§18 preserves the display value and locator separately from the canonical typed value."""
    candidate = CandidateRecord.model_validate(
        _candidate(
            canonicalized_typed_value={"type": "string", "value": "Synthetic project summary"},
            original_display_value="  Synthetic   project summary  ",
        )
    )
    assert candidate.original_display_value != candidate.canonicalized_typed_value.value


# --------------------------------------------------------------------------------------
# exclusions
# --------------------------------------------------------------------------------------


def test_exclusion_reasons_are_the_closed_seven() -> None:
    assert {member.value for member in ExclusionReason} == {
        "duplicate",
        "administrative_noise",
        "non_professional",
        "prohibited_sensitive",
        "superseded_source",
        "no_candidate_assertion",
        "owner_excluded",
    }


@pytest.mark.parametrize("reason", sorted(member.value for member in ExclusionReason))
def test_every_exclusion_reason_parses_with_a_rationale(reason: str) -> None:
    ledger = ExclusionLedger.model_validate(
        {
            "exclusions_version": 1,
            "exclusions": [
                {
                    "source_record_id": RECORD_ONE,
                    "reason": reason,
                    "rationale": "Synthetic rationale for the excluded record.",
                }
            ],
        }
    )
    assert ledger.counts_by_reason()[ExclusionReason(reason)] == 1


def test_every_exclusion_requires_a_rationale() -> None:
    with pytest.raises(ValidationError):
        ExclusionLedger.model_validate(
            {
                "exclusions_version": 1,
                "exclusions": [
                    {"source_record_id": RECORD_ONE, "reason": "duplicate", "rationale": "  "}
                ],
            }
        )


def test_one_record_cannot_be_excluded_twice() -> None:
    entry = {
        "source_record_id": RECORD_ONE,
        "reason": "duplicate",
        "rationale": "Synthetic rationale.",
    }
    with pytest.raises(ValidationError):
        ExclusionLedger.model_validate(
            {"exclusions_version": 1, "exclusions": [entry, {**entry, "reason": "non_professional"}]}
        )


def test_exclusion_counts_start_at_zero_for_every_reason() -> None:
    """Completeness reports exclusion totals BY REASON, so an absent reason must read as 0."""
    counts = ExclusionLedger.model_validate(
        {"exclusions_version": 1, "exclusions": []}
    ).counts_by_reason()
    assert set(counts) == set(ExclusionReason)
    assert set(counts.values()) == {0}
