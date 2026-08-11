"""T13 deterministic validation reports (design §19, §20, §21).

The report is the only thing an operator or a script ever sees, so three properties matter more
than its contents:

- **One model, two renderings.** Human text and JSON are both pure functions of the same
  `ValidationReport`. A human-only field would be a fact no script can act on, and a JSON-only
  field would be one no operator ever reads.
- **Deterministic bytes.** Sorted keys, compact separators, one trailing newline. The same report
  must produce the same bytes on every machine, or a diff of two runs is unreadable.
- **Closed shape.** The JSON object's keys are pinned exactly. A diagnostic carries record IDs and
  byte ranges, never captured evidence bytes or contact values, and a closed schema is what stops
  a future field from quietly carrying one into a report an operator pastes into a bug tracker.

These tests build `Diagnostic`s by hand rather than validating a bundle: the rendering contract is
independent of which checks exist, and coupling it to a real tree would make a report-format
failure look like a validation failure.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from boardwatch.profile_bundle.errors import Diagnostic, IssueCode, diagnostic
from boardwatch.profile_bundle.reports import (
    REPORT_SCHEMA,
    ValidationCounts,
    ValidationReport,
    count_diagnostics,
    outcome_for_report,
    report_json,
    report_text,
)

DIGEST = "sha256:" + "a" * 64
CANDIDATE = "sha256:" + "b" * 64


def error(message: str = "an error", **kwargs: object) -> Diagnostic:
    return diagnostic(IssueCode.BROKEN_REFERENCE, message, **kwargs)  # type: ignore[arg-type]


def blocker(message: str = "a blocker") -> Diagnostic:
    return diagnostic(IssueCode.UNRESOLVED_CONFLICT, message, record_id="conflict.example")


def warning(message: str = "a warning") -> Diagnostic:
    return diagnostic(IssueCode.BROKEN_REFERENCE, message, tier="warning")


def information(message: str = "some information") -> Diagnostic:
    return diagnostic(IssueCode.ORPHANED_ARTEFACT, message)


def report(*diagnostics: Diagnostic, as_of: date | None = None) -> ValidationReport:
    return ValidationReport(
        schema_version=1,
        bundle_digest=DIGEST,
        candidate_digest=CANDIDATE,
        as_of=as_of,
        diagnostics=tuple(diagnostics),
        counts=count_diagnostics(diagnostics),
    )


def loaded(text: str) -> dict[str, object]:
    payload = json.loads(text)
    assert isinstance(payload, dict)
    return payload


# --------------------------------------------------------------------------------------
# Counts
# --------------------------------------------------------------------------------------


def test_counts_are_totalled_per_tier() -> None:
    counts = count_diagnostics([error(), error("second"), blocker(), warning(), information()])
    assert counts == ValidationCounts(error=2, blocker=1, warning=1, information=1)


def test_counts_over_no_diagnostics_are_all_zero() -> None:
    assert count_diagnostics([]) == ValidationCounts(0, 0, 0, 0)


def test_total_is_the_sum_of_every_tier() -> None:
    counts = count_diagnostics([error(), blocker(), warning(), information()])
    assert counts.total == 4


# --------------------------------------------------------------------------------------
# Outcome and exit code (§21)
# --------------------------------------------------------------------------------------


def test_a_report_with_no_findings_is_clean_and_exits_zero() -> None:
    outcome = outcome_for_report(report())
    assert (outcome.category, outcome.exit_code) == ("clean", 0)


def test_an_error_is_findings_and_exits_one() -> None:
    outcome = outcome_for_report(report(error()))
    assert (outcome.category, outcome.exit_code) == ("findings", 1)


def test_a_blocker_alone_is_findings_and_exits_one() -> None:
    """§20.5 keeps blockers separate from errors, but both mean the operator has work to do."""
    outcome = outcome_for_report(report(blocker()))
    assert (outcome.category, outcome.exit_code) == ("findings", 1)


@pytest.mark.parametrize("noise", [warning(), information()])
def test_warnings_and_information_never_change_the_exit_code(noise: Diagnostic) -> None:
    outcome = outcome_for_report(report(noise))
    assert (outcome.category, outcome.exit_code) == ("clean", 0)


@pytest.mark.parametrize(
    "code",
    [IssueCode.IO_ERROR, IssueCode.UNSUPPORTED_SCHEMA_VERSION, IssueCode.INTERNAL_ERROR],
)
def test_a_check_that_could_not_complete_exits_three_not_one(code: IssueCode) -> None:
    """A check that did not run is not a check that passed, and it is not a finding either: §21
    gives it its own exit code so a script cannot read "could not read the bundle" as "one error"."""
    outcome = outcome_for_report(report(diagnostic(code, "could not complete")))
    assert (outcome.category, outcome.exit_code) == ("could_not_complete", 3)


def test_could_not_complete_outranks_an_ordinary_error_in_the_same_report() -> None:
    outcome = outcome_for_report(report(error(), diagnostic(IssueCode.IO_ERROR, "unreadable")))
    assert (outcome.category, outcome.exit_code) == ("could_not_complete", 3)


# --------------------------------------------------------------------------------------
# JSON rendering
# --------------------------------------------------------------------------------------


def test_json_carries_exactly_the_declared_top_level_keys() -> None:
    """A closed shape, asserted by equality rather than by containment. A new field cannot appear
    without this failing, which is the point: diagnostics must never grow a payload that carries
    captured evidence or a contact value into a pasted report."""
    assert set(loaded(report_json(report()))) == {
        "as_of",
        "bundle_digest",
        "candidate_digest",
        "counts",
        "diagnostics",
        "exit_code",
        "outcome",
        "report_schema",
        "schema_version",
    }


def test_json_carries_exactly_the_declared_diagnostic_keys() -> None:
    payload = loaded(report_json(report(error(path="a/b.yaml", record_id="fact.x"))))
    entries = payload["diagnostics"]
    assert isinstance(entries, list)
    assert set(entries[0]) == {"code", "details", "message", "path", "record_id", "tier"}


def test_json_uses_sorted_keys_compact_separators_and_one_trailing_newline() -> None:
    text = report_json(report(error()))
    assert text.endswith("}\n")
    assert not text.endswith("}\n\n")
    assert ", " not in text and '": ' not in text, "separators are not compact"
    body = text.rstrip("\n")
    assert body == json.dumps(
        json.loads(body), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def test_json_is_byte_identical_for_the_same_report() -> None:
    assert report_json(report(error(), blocker())) == report_json(report(error(), blocker()))


def test_json_diagnostic_order_does_not_depend_on_the_order_they_were_found() -> None:
    """The report sorts by the one ordering every layer uses, so two runs that accumulate the same
    findings in different orders produce identical bytes."""
    first = report(blocker(), error("aaa"), warning())
    second = report(warning(), error("aaa"), blocker())
    assert report_json(first) == report_json(second)


def test_json_reports_the_outcome_and_exit_code_explicitly() -> None:
    payload = loaded(report_json(report(error())))
    assert payload["outcome"] == "findings"
    assert payload["exit_code"] == 1


def test_json_records_the_as_of_date_it_was_given() -> None:
    payload = loaded(report_json(report(as_of=date(2026, 8, 11))))
    assert payload["as_of"] == "2026-08-11"


def test_json_records_a_null_as_of_when_completeness_was_not_requested() -> None:
    """§20.5 evaluates time-sensitive review only against an explicit date. A missing date must be
    visibly null, not silently today, or a report cannot be reproduced later."""
    assert loaded(report_json(report()))["as_of"] is None


def test_json_carries_the_report_schema_version() -> None:
    assert loaded(report_json(report()))["report_schema"] == REPORT_SCHEMA


def test_json_carries_the_counts_per_tier() -> None:
    payload = loaded(report_json(report(error(), blocker(), warning(), information())))
    assert payload["counts"] == {"blocker": 1, "error": 1, "information": 1, "warning": 1}


def test_json_preserves_non_ascii_rather_than_escaping_it() -> None:
    """The bundle is Unicode-first and NFC-normalised throughout; escaping here would make a
    diagnostic about a non-ASCII record unreadable in the one place an operator reads it."""
    text = report_json(report(error("record café is unresolved")))
    assert "café" in text


def test_json_carries_typed_details_untouched() -> None:
    payload = loaded(report_json(report(error(expected="x", count=3))))
    entries = payload["diagnostics"]
    assert isinstance(entries, list)
    assert entries[0]["details"] == {"count": 3, "expected": "x"}


def test_a_null_digest_is_rendered_as_null() -> None:
    empty = ValidationReport(
        schema_version=None,
        bundle_digest=None,
        candidate_digest=None,
        as_of=None,
        diagnostics=(),
        counts=count_diagnostics([]),
    )
    payload = loaded(report_json(empty))
    assert payload["bundle_digest"] is None
    assert payload["candidate_digest"] is None
    assert payload["schema_version"] is None


# --------------------------------------------------------------------------------------
# Human rendering
# --------------------------------------------------------------------------------------


def test_text_and_json_derive_from_the_same_model() -> None:
    """Every diagnostic in the JSON must be visible to a human too. A finding a script can see and
    an operator cannot is how a real problem gets ignored."""
    built = report(error("first finding"), blocker("second finding"))
    text = report_text(built)
    for finding in built.diagnostics:
        assert finding.message in text
        assert finding.code in text


def test_text_states_the_outcome_and_the_counts() -> None:
    text = report_text(report(error(), blocker(), warning()))
    assert "findings" in text
    assert "1 error" in text
    assert "1 blocker" in text


def test_text_says_a_clean_report_is_clean_rather_than_printing_nothing() -> None:
    """Silence and success look identical, which is exactly the confusion this program keeps
    paying for. A clean run says so."""
    text = report_text(report()).strip()
    assert text
    assert "clean" in text


def test_text_states_the_as_of_date_when_completeness_was_requested() -> None:
    assert "2026-08-11" in report_text(report(blocker(), as_of=date(2026, 8, 11)))


def test_text_is_deterministic() -> None:
    assert report_text(report(blocker(), error())) == report_text(report(error(), blocker()))
