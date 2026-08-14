"""The extraction report, its uniqueness rule, and the drain it validates (design §6.3a).

`imports/extraction-report.yaml` is the durable carrier that explains every `review_required`
record: exactly one closed reason for each, and none for an `imported` or `excluded` one. It never
asserts disposition — disposition stays derived from candidates and exclusions — so these tests pin
the *reconciliation* between the report and the ledger's dispositions, the mirror of the exclusion
reconciliation in `_dispositions_agree_with_the_exclusion_document`.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from boardwatch.profile_bundle.models.imports import (
    Disposition,
    ExtractionReport,
    ExtractionReportEntry,
    ExtractionReportReason,
    SourceLedger,
)
from boardwatch.profile_bundle.validation.imports import validate_extraction_report

SOURCE_ID = "source.synthetic-notes"
DIGEST_A = "sha256:" + "a" * 64


def _record_id(tag: str) -> str:
    return "source-record." + tag * 64


def _candidate_id(tag: str) -> str:
    return "candidate." + tag * 64


RECORD_IMPORTED = _record_id("1")
RECORD_EXCLUDED = _record_id("2")
RECORD_REVIEW = _record_id("3")
RECORD_REVIEW_TWO = _record_id("4")
UNKNOWN_RECORD = _record_id("9")


def _ledger(records: list[tuple[str, Disposition]]) -> SourceLedger:
    """A single-source ledger over `(record_id, disposition)` pairs.

    An imported record must name a candidate and a non-imported record must name none
    (`_imported_records_name_a_candidate`), so candidates are attached by disposition. The per-source
    ID list must equal the records in order (`_per_source_lists_match_the_records_exactly`).
    """
    ledger_records = []
    for index, (record_id, disposition) in enumerate(records):
        candidate_ids = (
            [_candidate_id(f"{index}" * 63 + "a")]
            if disposition is Disposition.IMPORTED
            else []
        )
        ledger_records.append(
            {
                "source_record_id": record_id,
                "source_id": SOURCE_ID,
                "normalized_locator": f"skills/languages/item-{index}",
                "disposition": disposition.value,
                "candidate_ids": candidate_ids,
            }
        )
    return SourceLedger.model_validate(
        {
            "ledger_version": 1,
            "sources": [
                {
                    "source_id": SOURCE_ID,
                    "enumerator_id": "markdown-blocks-v1",
                    "enumerator_version": 1,
                    "source_content_digest": DIGEST_A,
                    "approved_scope": {"kind": "complete_file"},
                    "source_record_ids": [record_id for record_id, _ in records],
                }
            ],
            "records": ledger_records,
        }
    )


def _report(entries: list[tuple[str, str]]) -> ExtractionReport:
    return ExtractionReport.model_validate(
        {
            "report_version": 1,
            "entries": [
                {"source_record_id": record_id, "reason": reason}
                for record_id, reason in entries
            ],
        }
    )


# --------------------------------------------------------------------------------------
# the document model
# --------------------------------------------------------------------------------------


def test_reasons_are_the_closed_six() -> None:
    assert {member.value for member in ExtractionReportReason} == {
        "no_mapping_for_locator",
        "unsupported_entry_kind",
        "span_not_grounded",
        "value_not_typeable",
        "free_text_deferred",
        "no_predicate_exists",
    }


def test_a_valid_report_parses_and_indexes_by_record() -> None:
    report = _report([(RECORD_REVIEW, "no_predicate_exists")])
    assert isinstance(report.entries[0], ExtractionReportEntry)
    assert report.by_record[RECORD_REVIEW].reason is ExtractionReportReason.NO_PREDICATE_EXISTS
    assert report.counts_by_reason()[ExtractionReportReason.NO_PREDICATE_EXISTS] == 1


def test_an_empty_report_is_legal() -> None:
    """A fresh bundle has no sources, so the seed is empty (§6.3a)."""
    report = ExtractionReport.model_validate({"report_version": 1, "entries": []})
    assert report.entries == ()
    assert set(report.counts_by_reason().values()) == {0}


def test_counts_start_at_zero_for_every_reason() -> None:
    counts = ExtractionReport.model_validate(
        {"report_version": 1, "entries": []}
    ).counts_by_reason()
    assert set(counts) == set(ExtractionReportReason)
    assert set(counts.values()) == {0}


def test_one_record_cannot_carry_two_reasons() -> None:
    """Two reasons for one record would make the reason totals overcount the denominator."""
    with pytest.raises(ValidationError):
        ExtractionReport.model_validate(
            {
                "report_version": 1,
                "entries": [
                    {"source_record_id": RECORD_REVIEW, "reason": "free_text_deferred"},
                    {"source_record_id": RECORD_REVIEW, "reason": "no_predicate_exists"},
                ],
            }
        )


# --------------------------------------------------------------------------------------
# the drain: report reconciles with the ledger's dispositions
# --------------------------------------------------------------------------------------


def test_drain_is_clean_when_every_review_required_has_exactly_one_reason() -> None:
    ledger = _ledger(
        [
            (RECORD_IMPORTED, Disposition.IMPORTED),
            (RECORD_EXCLUDED, Disposition.EXCLUDED),
            (RECORD_REVIEW, Disposition.REVIEW_REQUIRED),
        ]
    )
    report = _report([(RECORD_REVIEW, "free_text_deferred")])
    assert validate_extraction_report(ledger, report) == ()


def test_a_review_required_record_with_no_reason_is_flagged() -> None:
    ledger = _ledger([(RECORD_REVIEW, Disposition.REVIEW_REQUIRED)])
    report = _report([])
    findings = validate_extraction_report(ledger, report)
    assert [f.record_id for f in findings] == [RECORD_REVIEW]


def test_a_review_required_record_with_two_reasons_cannot_reach_the_validator() -> None:
    """The model refuses a duplicate `source_record_id`, so two reasons for one record is a parse
    failure — it can never be a report the validator sees."""
    with pytest.raises(ValidationError):
        _report(
            [
                (RECORD_REVIEW, "free_text_deferred"),
                (RECORD_REVIEW, "no_predicate_exists"),
            ]
        )


def test_an_imported_record_with_a_reason_is_flagged() -> None:
    ledger = _ledger(
        [
            (RECORD_IMPORTED, Disposition.IMPORTED),
            (RECORD_REVIEW, Disposition.REVIEW_REQUIRED),
        ]
    )
    report = _report(
        [
            (RECORD_IMPORTED, "span_not_grounded"),
            (RECORD_REVIEW, "free_text_deferred"),
        ]
    )
    findings = validate_extraction_report(ledger, report)
    assert [f.record_id for f in findings] == [RECORD_IMPORTED]


def test_an_excluded_record_with_a_reason_is_flagged() -> None:
    ledger = _ledger([(RECORD_EXCLUDED, Disposition.EXCLUDED)])
    report = _report([(RECORD_EXCLUDED, "no_mapping_for_locator")])
    findings = validate_extraction_report(ledger, report)
    assert [f.record_id for f in findings] == [RECORD_EXCLUDED]


def test_a_report_entry_for_an_unknown_record_is_flagged() -> None:
    ledger = _ledger([(RECORD_REVIEW, Disposition.REVIEW_REQUIRED)])
    report = _report(
        [
            (RECORD_REVIEW, "free_text_deferred"),
            (UNKNOWN_RECORD, "value_not_typeable"),
        ]
    )
    findings = validate_extraction_report(ledger, report)
    assert [f.record_id for f in findings] == [UNKNOWN_RECORD]
