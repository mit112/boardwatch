"""The P1a résumé-artifact gate: pure policy + typed failures.

A lead without a compiled, page-compliant PDF is not a lead (PROGRAM.md §3.P1). The runner
reports compile facts (CompileOutcome); this module applies the page-count POLICY and owns the
typed failures the tailoring flow raises. Pure — no subprocess, no DB, no filesystem.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from boardwatch.tailor.model import Resume
from boardwatch.tailor.render.outcome import CompileOutcome, CompileReason


class TypstUnavailableError(RuntimeError):
    """The `typst` binary is not on PATH. An environment fault, never a per-lead failure:
    the pipeline turns it into a run-level fatal and the CLI exits non-zero with install
    guidance."""


class LeadArtifactError(RuntimeError):
    """A lead has no shippable PDF after the untailored-master fallback. Per-lead: the pipeline
    drops the lead (its existing non-fatal accounting), the CLI exits non-zero."""


class ResumeValidationError(RuntimeError):
    """A résumé slot assertion failed (empty header / no entries / an entry with no bullets /
    a blank bullet). Treated like a compile failure: fall back, then drop."""


class GateReason(StrEnum):
    OK = "ok"
    BINARY_MISSING = "binary_missing"
    COMPILE_FAILED = "compile_failed"
    PAGE_LIMIT_EXCEEDED = "page_limit_exceeded"


@dataclass(frozen=True)
class GateResult:
    reason: GateReason
    shippable: bool
    pdf_path: Path | None
    page_count: int | None
    log: str


def evaluate_compile(outcome: CompileOutcome, *, max_pages: int) -> GateResult:
    """Map a compile outcome + the profile's page limit to a shippability verdict."""
    if outcome.reason is CompileReason.BINARY_MISSING:
        return GateResult(GateReason.BINARY_MISSING, False, None, None, outcome.log)
    if outcome.reason is CompileReason.COMPILE_FAILED:
        return GateResult(GateReason.COMPILE_FAILED, False, None, None, outcome.log)
    # OK: the __post_init__ invariant guarantees pdf_path and page_count are set.
    assert outcome.pdf_path is not None and outcome.page_count is not None
    if outcome.page_count > max_pages:
        return GateResult(
            GateReason.PAGE_LIMIT_EXCEEDED, False, outcome.pdf_path, outcome.page_count, outcome.log
        )
    return GateResult(GateReason.OK, True, outcome.pdf_path, outcome.page_count, outcome.log)


def validate_slots(resume: Resume) -> None:
    """Assert the résumé's slots are filled before it is rendered (PROGRAM.md P1 item 4). A
    standalone validator (NOT a pydantic model_validator) so it raises our typed error at the
    render gate and does not reject legitimately-partial intermediate Resume constructions."""
    if not resume.header:
        raise ResumeValidationError("résumé has no header")
    if not resume.entries:
        raise ResumeValidationError("résumé has no entries")
    for entry in resume.entries:
        if not entry.bullets:
            raise ResumeValidationError(f"entry {entry.entry_id!r} has no bullets")
        for bullet in entry.bullets:
            if not bullet.text.strip():
                raise ResumeValidationError(f"bullet {bullet.bullet_id!r} is blank")
