"""The P1a résumé-artifact gate: pure policy + typed failures.

A lead without a compiled, page-compliant PDF is not a lead (PROGRAM.md §3.P1). The runner
reports compile facts (CompileOutcome); this module applies the page-count POLICY and owns the
typed failures the tailoring flow raises. Pure — no subprocess, no DB, no filesystem.

Also houses the P4 item 5a per-lead structural layout gate (`validate_layout`): deterministic
assertions — a bullet length ceiling, bullet-count ceiling, an escaping round-trip, and
leftover template artifacts — that P1a's slot check does not cover.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from boardwatch.tailor.model import Resume
from boardwatch.tailor.plan import MAX_BULLETS_PER_ENTRY
from boardwatch.tailor.render.outcome import CompileOutcome, CompileReason
from boardwatch.tailor.render.typst import escape


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
    BULLET_TOO_LONG = "bullet_too_long"
    TOO_MANY_BULLETS = "too_many_bullets"
    ESCAPING_MISMATCH = "escaping_mismatch"
    TEMPLATE_ARTIFACT = "template_artifact"
    # P4 item 5b: run-once, fatal checks on the authored MASTER at load time (see
    # `tailor.load.validate_master`). TEMPLATE_ARTIFACT above is reused for the
    # master-authoring instance of that check rather than duplicated.
    CONTACT_BLOCK_MISSING_NAME = "contact_block_missing_name"
    CONTACT_BLOCK_INVALID_EMAIL = "contact_block_invalid_email"


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


# --- P4 item 5a: per-lead structural layout gate ----------------------------------------

BULLET_MAX_LENGTH = 220

# Closed catalog of leftover template/placeholder tells, shared by the per-lead layout gate
# (5a) and the master-authoring check (5b, not built yet). Split by how a token can safely
# be matched:
#   - symbols can never legitimately appear in résumé prose, so a plain case-insensitive
#     substring match is correct and cheap.
#   - word-like tokens (TODO, lorem, ...) are real English/Latin words that also occur inside
#     legitimate product/framework names ("Todo-list app", "TodoMVC-based tool"), so they are
#     matched as a standalone token only — see `_word_token_pattern` below.
TEMPLATE_ARTIFACT_SYMBOLS: tuple[str, ...] = ("{{", "}}", "<placeholder>")
TEMPLATE_ARTIFACT_WORDS: tuple[str, ...] = ("TODO", "FIXME", "lorem", "ipsum", "XXX")
TEMPLATE_ARTIFACT_TOKENS: tuple[str, ...] = TEMPLATE_ARTIFACT_SYMBOLS + TEMPLATE_ARTIFACT_WORDS


def _word_token_pattern(token: str) -> re.Pattern[str]:
    # A stricter boundary than \w alone: a hyphen does not count as a separator either, so
    # a word-like token glued into a hyphenated compound name ("Todo-list", "TodoMVC-based")
    # is not flagged as a standalone occurrence — only genuine standalone usage is.
    return re.compile(rf"(?<![\w-]){re.escape(token)}(?![\w-])", re.IGNORECASE)


def contains_template_artifact(text: str) -> str | None:
    """Return the offending token if `text` contains a leftover template/placeholder tell
    from the closed catalog above, else None. Symbols match as a substring; word-like
    tokens match only as a standalone token (see `_word_token_pattern`)."""
    lowered = text.lower()
    for token in TEMPLATE_ARTIFACT_SYMBOLS:
        if token.lower() in lowered:
            return token
    for token in TEMPLATE_ARTIFACT_WORDS:
        if _word_token_pattern(token).search(text):
            return token
    return None


class LayoutViolation(ResumeValidationError):
    """A structural layout invariant failed (PROGRAM.md P4 item 5a). Carries the specific
    `GateReason` so the degrade path can report exactly which check failed, rather than
    classifying behaviour by string-matching the message."""

    def __init__(self, reason: GateReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason


def layout_scan_fields(resume: Resume) -> list[tuple[str, str]]:
    """(text, description) pairs for the template-artifact scan: header, education, every
    skill group's label and items, and every entry's heading and bullets. Not underscore-
    prefixed: reused by `tailor.load.validate_master` (P4 item 5b) for the master-authoring
    instance of the same scan, so the field list is defined once for both populations."""
    fields: list[tuple[str, str]] = [(h, "header") for h in resume.header]
    fields += [(ed, "education") for ed in resume.education]
    for g in resume.skill_groups:
        fields.append((g.label, f"skill group {g.label!r} label"))
        fields.extend((item, f"skill group {g.label!r} item {item!r}") for item in g.items)
    for e in resume.entries:
        fields.append((e.heading, f"entry {e.entry_id!r} heading"))
        if e.title is not None:
            fields.append((e.title, f"entry {e.entry_id!r} title"))
        if e.dates is not None:
            fields.append((e.dates, f"entry {e.entry_id!r} dates"))
        if e.subtitle is not None:
            fields.append((e.subtitle, f"entry {e.entry_id!r} subtitle"))
        if e.location is not None:
            fields.append((e.location, f"entry {e.entry_id!r} location"))
        fields.extend((b.text, f"bullet {b.bullet_id!r}") for b in e.bullets)
    fields.extend((line, "extracurricular") for line in resume.extracurricular)
    return fields


def _assert_escaped_round_trip(source: str, expected_line: str, where: str) -> None:
    """`escape()` re-derived from the model field must appear verbatim in the already-
    emitted `.typ` source — belt-and-suspenders against a future emit path that forgets to
    escape (typst.py's `escape()` itself is not new logic; this only asserts it held)."""
    if expected_line not in source:
        raise LayoutViolation(
            GateReason.ESCAPING_MISMATCH,
            f"{where}: emitted source does not match escape() round-trip",
        )


def validate_layout(resume: Resume, source: str) -> None:
    """Deterministic structural assertions P1a's `validate_slots` does not cover (PROGRAM.md
    P4 item 5a): a bullet length ceiling, bullet-count ceiling per entry, an escaping
    round-trip against the already-emitted `.typ` `source`, and leftover template artifacts.
    Raises `LayoutViolation` (a `ResumeValidationError`), mirroring `validate_slots`'s shape
    and call convention. Pure — no subprocess, no DB, no filesystem.

    No length FLOOR: a short bullet ("Cut p99 latency 40%") renders and reads fine — there
    is no rendering defect a floor would catch that `validate_slots` (empty/blank bullets)
    doesn't already, and this gate also runs on the untailored MASTER, so a floor would risk
    dropping every lead over one legitimately concise bullet in the authored résumé."""
    for entry in resume.entries:
        if len(entry.bullets) > MAX_BULLETS_PER_ENTRY:
            raise LayoutViolation(
                GateReason.TOO_MANY_BULLETS,
                f"entry {entry.entry_id!r} has {len(entry.bullets)} bullets "
                f"(ceiling {MAX_BULLETS_PER_ENTRY})",
            )
        for bullet in entry.bullets:
            length = len(bullet.text)
            if length > BULLET_MAX_LENGTH:
                raise LayoutViolation(
                    GateReason.BULLET_TOO_LONG,
                    f"bullet {bullet.bullet_id!r} is {length} chars "
                    f"(ceiling {BULLET_MAX_LENGTH})",
                )

    for h in resume.header:
        _assert_escaped_round_trip(source, f'#resume-header("{escape(h)}")', "header")
    for ed in resume.education:
        _assert_escaped_round_trip(source, f'#resume-education("{escape(ed)}")', "education")
    for g in resume.skill_groups:
        items = ", ".join(g.items)
        _assert_escaped_round_trip(
            source,
            f'#resume-skills("{escape(g.label)}", "{escape(items)}")',
            f"skill group {g.label!r}",
        )
    for e in resume.entries:
        _assert_escaped_round_trip(
            source, f'#resume-entry("{escape(e.heading)}")', f"entry {e.entry_id!r} heading"
        )
        for b in e.bullets:
            _assert_escaped_round_trip(
                source, f'#resume-bullet("{escape(b.text)}")', f"bullet {b.bullet_id!r}"
            )

    for text, where in layout_scan_fields(resume):
        token = contains_template_artifact(text)
        if token is not None:
            raise LayoutViolation(
                GateReason.TEMPLATE_ARTIFACT, f"{where} contains template artifact {token!r}"
            )
