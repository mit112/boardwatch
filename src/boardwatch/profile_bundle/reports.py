"""The one validation report, and its two renderings (design §19, §20, §21).

Human text and JSON are both pure functions of a single `ValidationReport`. That is deliberate:
a field only the human rendering shows is a fact no script can act on, and a field only the JSON
carries is one no operator ever reads. Every layer's diagnostics land here and nowhere else.

Three properties this module is responsible for:

- **Deterministic bytes.** Diagnostics are ordered by `Diagnostic.sort_key`, keys are sorted, and
  separators are compact. Two runs that accumulated the same findings in different orders produce
  identical output, so diffing two reports shows what changed rather than how they were traversed.
- **A closed shape.** The JSON object's keys are pinned by test. A diagnostic carries record IDs
  and byte ranges and never captured evidence bytes or contact values (`errors.Diagnostic` says so);
  a closed schema is what stops a future field from quietly carrying one into a report an operator
  pastes into a bug tracker.
- **A stated outcome.** §21 separates "the check completed and found things" from "the check could
  not complete". Both the exit code and the human line say which, because silence and success have
  cost this program real time.

This serializer is **not** `canonical.py`'s. That one computes identity and must never change its
bytes; this one formats a report and may grow a field under `report_schema`.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Final

from boardwatch.profile_bundle.errors import (
    Diagnostic,
    IssueTier,
    JsonValue,
    OperationOutcome,
    outcome_with,
)

#: The report envelope's own version. Independent of the bundle's `schema_version`: a consumer
#: parsing this JSON needs to know when the REPORT shape changed, not when the bundle's did.
REPORT_SCHEMA: Final = 1

_TIERS: Final[tuple[IssueTier, ...]] = ("error", "blocker", "warning", "information")


@dataclass(frozen=True)
class ValidationCounts:
    """Findings per tier. Kept apart because §20.5 reports blockers separately from errors: a
    revision can be perfectly valid and still carry material that is unusable downstream."""

    error: int
    blocker: int
    warning: int
    information: int

    @property
    def total(self) -> int:
        return self.error + self.blocker + self.warning + self.information

    def as_json(self) -> dict[str, int]:
        return {
            "error": self.error,
            "blocker": self.blocker,
            "warning": self.warning,
            "information": self.information,
        }


def count_diagnostics(diagnostics: Iterable[Diagnostic]) -> ValidationCounts:
    tally = dict.fromkeys(_TIERS, 0)
    for finding in diagnostics:
        tally[finding.tier] += 1
    return ValidationCounts(
        error=tally["error"],
        blocker=tally["blocker"],
        warning=tally["warning"],
        information=tally["information"],
    )


@dataclass(frozen=True)
class ValidationReport:
    """Everything one validation run observed.

    Every field is optional-by-type on purpose. A bundle whose manifest will not parse has no
    schema version and no digest, and reporting `0` or `""` for either would be a measurement that
    was never taken (D-012).
    """

    schema_version: int | None
    bundle_digest: str | None
    #: The candidate digest the validated tree RECOMPUTES, never one it merely declares. `None`
    #: means the run made no claim — a missing blob, an unrecoverable candidate view, or a parent
    #: revision that could not be resolved. For a promoted revision `None` is always accompanied by
    #: a `candidate_digest_unverified` information diagnostic carrying the typed reason, so a
    #: consumer reading only `diagnostics` sees the gap too; for a draft with no parent supplied it
    #: is not, because a draft has no approval to have been compared against.
    candidate_digest: str | None
    #: The date the dated completeness checks ran at, and `None` when they did not run at all —
    #: including a completeness run skipped because a structural prerequisite was missing. Reporting
    #: the requested date regardless would make a skipped run read as a clean one.
    as_of: date | None
    diagnostics: tuple[Diagnostic, ...]
    counts: ValidationCounts

    @property
    def ordered(self) -> tuple[Diagnostic, ...]:
        """The one ordering every report uses: tier, code, path, record ID, message."""
        return tuple(sorted(self.diagnostics, key=lambda finding: finding.sort_key()))


def outcome_for_report(report: ValidationReport) -> OperationOutcome[ValidationReport]:
    """The §21 outcome this report implies.

    One definition, used by both the command layer and the renderings, so a script reading
    `exit_code` from the JSON and a shell reading `$?` can never disagree.

    A could-not-complete code outranks an ordinary finding; `errors.outcome_with` owns that
    precedence so the command layer and this report layer cannot disagree about it.
    """
    return outcome_with(report, report.diagnostics)


def _diagnostic_json(finding: Diagnostic) -> dict[str, JsonValue]:
    return {
        "tier": finding.tier,
        "code": finding.code,
        "path": finding.path,
        "record_id": finding.record_id,
        "message": finding.message,
        "details": dict(finding.details),
    }


def report_json(report: ValidationReport) -> str:
    """Deterministic machine output: sorted keys, compact separators, one trailing newline.

    `ensure_ascii=False` because the bundle is Unicode-first and NFC-normalised throughout;
    escaping would make a diagnostic about a non-ASCII record unreadable in the one place an
    operator actually reads it. The bytes stay deterministic either way.
    """
    outcome = outcome_for_report(report)
    payload: dict[str, JsonValue] = {
        "report_schema": REPORT_SCHEMA,
        "schema_version": report.schema_version,
        "bundle_digest": report.bundle_digest,
        "candidate_digest": report.candidate_digest,
        "as_of": report.as_of.isoformat() if report.as_of is not None else None,
        "outcome": outcome.category,
        "exit_code": outcome.exit_code,
        "counts": report.counts.as_json(),
        "diagnostics": [_diagnostic_json(finding) for finding in report.ordered],
    }
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    )


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _location(finding: Diagnostic) -> str:
    where = " ".join(part for part in (finding.path, finding.record_id) if part)
    return f" ({where})" if where else ""


def report_text(report: ValidationReport) -> str:
    """Human output, derived from the same model.

    Plain text rather than Rich markup: the command layer owns presentation, and a report that can
    only be produced through a console is one no test can compare byte for byte.
    """
    outcome = outcome_for_report(report)
    lines = [f"profile-bundle validate: {outcome.category}"]
    if report.as_of is not None:
        lines.append(f"as-of: {report.as_of.isoformat()}")
    lines.append(
        ", ".join(
            (
                _plural(report.counts.error, "error"),
                _plural(report.counts.blocker, "blocker"),
                _plural(report.counts.warning, "warning"),
                f"{report.counts.information} information",
            )
        )
    )
    lines.extend(
        f"{finding.tier}: {finding.code}{_location(finding)}: {finding.message}"
        for finding in report.ordered
    )
    return "\n".join(lines) + "\n"


def empty_report(diagnostics: Iterable[Diagnostic]) -> ValidationReport:
    """A report for a run that never got far enough to identify the bundle.

    Used when parsing fails: there is no schema version and no digest to report, and inventing one
    would be a fact nobody measured.
    """
    found = tuple(diagnostics)
    return ValidationReport(
        schema_version=None,
        bundle_digest=None,
        candidate_digest=None,
        as_of=None,
        diagnostics=found,
        counts=count_diagnostics(found),
    )


__all__ = [
    "REPORT_SCHEMA",
    "ValidationCounts",
    "ValidationReport",
    "count_diagnostics",
    "empty_report",
    "outcome_for_report",
    "report_json",
    "report_text",
]
