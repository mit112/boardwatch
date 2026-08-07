"""_default_runner against the real typst binary — the richer compile runner (P1a Task 3).

Skipped wholesale when typst is absent (CI without the binary); this environment has it.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from boardwatch.reports.tailor import _default_runner
from boardwatch.tailor.render.outcome import CompileReason

pytestmark = pytest.mark.skipif(shutil.which("typst") is None, reason="typst not installed")

_LABEL = "#context [#metadata(counter(page).final().first()) <total-pages>]"


def _write(tmp_path: Path, body: str) -> tuple[Path, Path]:
    typ = tmp_path / "r.typ"
    typ.write_text(f'#set page(paper: "us-letter", margin: 1cm)\n{body}\n{_LABEL}\n', encoding="utf-8")
    return typ, tmp_path / "r.pdf"


def test_runner_reports_ok_and_one_page(tmp_path: Path) -> None:
    typ, pdf = _write(tmp_path, "= Jane\n#lorem(30)")
    out = _default_runner(typ, pdf)
    assert out.reason is CompileReason.OK and out.page_count == 1 and pdf.exists()


def test_runner_reports_multiple_pages_on_overflow(tmp_path: Path) -> None:
    typ, pdf = _write(tmp_path, "#lorem(2000)")
    out = _default_runner(typ, pdf)
    assert out.reason is CompileReason.OK and out.page_count >= 2


def test_runner_reports_compile_failed_on_broken_source(tmp_path: Path) -> None:
    typ = tmp_path / "b.typ"
    typ.write_text("#set page(\n= broken", encoding="utf-8")
    out = _default_runner(typ, tmp_path / "b.pdf")
    assert out.reason is CompileReason.COMPILE_FAILED and out.log


def test_runner_reports_binary_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("boardwatch.reports.tailor.shutil.which", lambda _: None)
    typ, pdf = _write(tmp_path, "= Jane")
    out = _default_runner(typ, pdf)
    assert out.reason is CompileReason.BINARY_MISSING
