"""Typed result of one typst compile — P1a. Pure; no subprocess here."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

#: The render-toolchain binaries whose absence is a `BINARY_MISSING`. A closed two-member catalog
#: because the install-guidance selector in `reports/tailor.py` is exhaustive over exactly these;
#: adding a third render binary must be a type error there, not a silently mis-worded message.
RenderTool = Literal["tectonic", "pdfinfo"]


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
    # Which render-toolchain binary was missing when `reason` is BINARY_MISSING; `None` for every
    # other reason, and also the safe default for a BINARY_MISSING outcome from a caller that
    # predates this field. `reports/tailor.py` selects the correct install-guidance message from
    # this typed value, never by string-matching `log`. **Closed catalog, not an open string**: the
    # message selector maps anything that is not `"pdfinfo"` to the tectonic message, so a third
    # producer passing an unlisted name would silently get the wrong install guidance. `Literal`
    # makes that a type error at the call site instead.
    tool: RenderTool | None = None

    def __post_init__(self) -> None:
        ok = self.reason is CompileReason.OK
        if ok != (self.pdf_path is not None) or ok != (self.page_count is not None):
            raise ValueError(
                f"CompileOutcome invariant violated: {self.reason} "
                f"pdf={self.pdf_path} page_count={self.page_count}"
            )


CompileRunner = Callable[[Path, Path], CompileOutcome]
