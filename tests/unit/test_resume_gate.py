from __future__ import annotations

from pathlib import Path

import pytest

from boardwatch.reports.resume_gate import (
    GateReason,
    ResumeValidationError,
    evaluate_compile,
    validate_slots,
)
from boardwatch.tailor.model import Bullet, Entry, Resume, SkillGroup
from boardwatch.tailor.render.outcome import CompileOutcome, CompileReason


def _ok(pages: int = 1) -> CompileOutcome:
    return CompileOutcome(CompileReason.OK, Path("/x/r.pdf"), pages, "log")


def test_ok_within_limit_is_shippable() -> None:
    r = evaluate_compile(_ok(1), max_pages=1)
    assert r.reason is GateReason.OK and r.shippable and r.page_count == 1


def test_fewer_pages_than_limit_is_shippable() -> None:
    assert evaluate_compile(_ok(1), max_pages=2).shippable


def test_over_limit_is_page_limit_exceeded() -> None:
    r = evaluate_compile(_ok(2), max_pages=1)
    assert r.reason is GateReason.PAGE_LIMIT_EXCEEDED and not r.shippable


def test_binary_missing_passes_through() -> None:
    r = evaluate_compile(CompileOutcome(CompileReason.BINARY_MISSING, None, None, ""), max_pages=1)
    assert r.reason is GateReason.BINARY_MISSING and not r.shippable


def test_compile_failed_passes_through() -> None:
    r = evaluate_compile(CompileOutcome(CompileReason.COMPILE_FAILED, None, None, "boom"), max_pages=1)
    assert r.reason is GateReason.COMPILE_FAILED and not r.shippable and r.log == "boom"


def test_compile_outcome_invariant_ok_requires_pdf_and_pages() -> None:
    with pytest.raises(ValueError):
        CompileOutcome(CompileReason.OK, None, 1, "")
    with pytest.raises(ValueError):
        CompileOutcome(CompileReason.OK, Path("/x.pdf"), None, "")
    with pytest.raises(ValueError):
        CompileOutcome(CompileReason.COMPILE_FAILED, Path("/x.pdf"), 1, "")


def _resume(bullets: list[str] | None = None, *, header: list[str] | None = None,
            entries: list[Entry] | None = None) -> Resume:
    ents = entries if entries is not None else [
        Entry(entry_id="e1", heading="Co", bullets=[Bullet(bullet_id="b1", text=t) for t in (bullets or ["did x"])])
    ]
    return Resume(header=header if header is not None else ["Jane"], education=[],
                  skill_groups=[SkillGroup(label="L", items=["Python"])], entries=ents)


def test_validate_slots_passes_a_full_resume() -> None:
    validate_slots(_resume())  # no raise


def test_validate_slots_rejects_empty_header() -> None:
    with pytest.raises(ResumeValidationError):
        validate_slots(_resume(header=[]))


def test_validate_slots_rejects_no_entries() -> None:
    with pytest.raises(ResumeValidationError):
        validate_slots(_resume(entries=[]))


def test_validate_slots_rejects_entry_with_no_bullets() -> None:
    with pytest.raises(ResumeValidationError):
        validate_slots(_resume(entries=[Entry(entry_id="e1", heading="Co", bullets=[])]))


def test_validate_slots_rejects_blank_bullet() -> None:
    with pytest.raises(ResumeValidationError):
        validate_slots(_resume(entries=[Entry(entry_id="e1", heading="Co", bullets=[Bullet(bullet_id="b1", text=" ")])]))
