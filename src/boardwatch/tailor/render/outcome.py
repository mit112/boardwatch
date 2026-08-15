"""Typed result of one typst compile — P1a. Pure; no subprocess here."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class CompileReason(StrEnum):
    OK = "ok"
    BINARY_MISSING = "binary_missing"
    COMPILE_FAILED = "compile_failed"


@dataclass(frozen=True)
class CompileOutcome:
    """What one `typst compile` (+ page-count query) observed. `OK` carries a real PDF and page
    count; every non-OK carries neither. The invariant is enforced at construction so a buggy or
    fabricated runner cannot smuggle an inconsistent outcome past the gate."""

    reason: CompileReason
    pdf_path: Path | None
    page_count: int | None
    log: str
    # Which render-toolchain binary was missing when `reason` is BINARY_MISSING ("tectonic" or
    # "pdfinfo"); `None` for every other reason, and also the safe default for a BINARY_MISSING
    # outcome from a caller that predates this field. `reports/tailor.py` selects the correct
    # install-guidance message from this typed value, never by string-matching `log`.
    tool: str | None = None

    def __post_init__(self) -> None:
        ok = self.reason is CompileReason.OK
        if ok != (self.pdf_path is not None) or ok != (self.page_count is not None):
            raise ValueError(
                f"CompileOutcome invariant violated: {self.reason} "
                f"pdf={self.pdf_path} page_count={self.page_count}"
            )


CompileRunner = Callable[[Path, Path], CompileOutcome]
