"""The one validation report, and the per-diagnostic renderings both of a command's answers use
(design §19, §20, §21).

Every layer's diagnostics land in a single `ValidationReport`, and `diagnostic_json` and
`diagnostic_line` are the two shapes any one of them is ever shown in. That pairing is deliberate:
a field only the human rendering shows is a fact no script can act on, and a field only the JSON
carries is one no operator ever reads.

Three properties this module is responsible for:

- **Deterministic ordering.** `ValidationReport.ordered` sorts by `Diagnostic.sort_key`, so two
  runs that accumulated the same findings in different orders produce identical output and diffing
  two reports shows what changed rather than how they were traversed.
- **A closed shape.** `diagnostic_json`'s keys are pinned by test. A diagnostic carries record IDs
  and byte ranges and never captured evidence bytes or contact values (`errors.Diagnostic` says so);
  a closed schema is what stops a future field from quietly carrying one into a report an operator
  pastes into a bug tracker.
- **A stated outcome.** §21 separates "the check completed and found things" from "the check could
  not complete", and `outcome_for_report` is the one definition of which.

**The whole-report renderings live in `cli/profile_bundle_cmd.py`, not here.** This module once
carried `report_json` and `report_text` as well, and the command layer rendered the same report a
second time into the envelope every one of the twelve commands emits. Two spellings of one rule is
this project's named recurring defect and these two had already drifted — the human forms disagreed
on pluralisation and the machine forms on whether the counts were nested — while the pair here was
unreachable from any command. D-115: they are deleted, and the properties they held are pinned on
the surface an operator can actually reach.

The `json.dumps` settings that rendering uses are `_emit`'s, not this module's, and are not
`canonical.py`'s either: that one computes identity and must never change its bytes.
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


def diagnostic_json(finding: Diagnostic) -> dict[str, JsonValue]:
    """One diagnostic's machine form.

    Public because the command layer renders diagnostics for eleven commands that have no
    `ValidationReport`, and a second spelling of this mapping would let a field appear under one
    command and not another — which is how `details` (and so `record_ids`) would go missing from
    exactly the refusals that carry it.
    """
    return {
        "tier": finding.tier,
        "code": finding.code,
        "path": finding.path,
        "record_id": finding.record_id,
        "message": finding.message,
        "details": dict(finding.details),
    }


def _location(finding: Diagnostic) -> str:
    where = " ".join(part for part in (finding.path, finding.record_id) if part)
    return f" ({where})" if where else ""


def _detail_value(value: JsonValue) -> str:
    """A string is itself; everything else is its JSON form.

    So an empty list renders `[]` and never a phrase. D-129 turns on `record_ids` being empty
    meaning "the conflicting unit has no addressable records", and any gloss — "none", "no
    records" — reads as reassurance about exactly the case where a whole document is in conflict.
    """
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _details(finding: Diagnostic) -> str:
    """Every `details` entry, one indented line each, ordered by key.

    Rendered rather than dropped because `details` is where the locator lives for the findings that
    have no single record: D-129 fixes `path` plus `details.field` as the whole address of a
    field-level conflict, and `rebase` reports a record overlap by putting every colliding ID in
    `details.record_ids` while the message carries only a count. A human rendering without them
    tells the operator how many records collided and never which — the one fact they have to act
    on — while the machine rendering of the same finding carries them.

    Indented continuation lines rather than a suffix: `record_ids` is unbounded, and the alternative
    is one 3 KB line. `_emit` joins diagnostics with newlines already, so a
    multi-line rendering needs nothing from either.
    """
    return "".join(
        f"\n    {key}: {_detail_value(finding.details[key])}" for key in sorted(finding.details)
    )


def diagnostic_line(finding: Diagnostic) -> str:
    """One diagnostic's human form: tier, code, where, what, and its typed details.

    Public for the same reason `diagnostic_json` is: the command layer prints diagnostics for
    commands that never build a `ValidationReport`, and one operator reading two shapes of the same
    finding would have to learn which command produced which. That is also why `details` is here
    rather than in the command layer — a field that reached one rendering and not the other is a
    fact only half the readers can act on.
    """
    return (
        f"{finding.tier}: {finding.code}{_location(finding)}: {finding.message}"
        f"{_details(finding)}"
    )


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
    "diagnostic_json",
    "diagnostic_line",
    "empty_report",
    "outcome_for_report",
]
