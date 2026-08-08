from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from boardwatch.reports.tailor import _default_runner, _pdf_page_count
from boardwatch.tailor.render.outcome import CompileReason

# NOTE (plan-review m1): this guard only checks the binary is present. tectonic fetches its
# package bundle (hundreds of MB) on FIRST compile — an installed-but-offline env will FAIL the
# OK test, not skip it. Task 1's Dockerfile warms the bundle at image-build time; run locally
# online at least once so the bundle is cached before `make check` in an offline setting.
pytestmark = pytest.mark.skipif(shutil.which("tectonic") is None, reason="tectonic not installed")

_MINIMAL = "\\documentclass{article}\n\\begin{document}\nHello \\% world\n\\end{document}\n"


def test_default_runner_compiles_and_counts_pages(tmp_path: Path):
    tex = tmp_path / "r.tex"
    tex.write_text(_MINIMAL)
    out = _default_runner(tex, tmp_path / "r.pdf")
    assert out.reason is CompileReason.OK and out.page_count == 1 and out.pdf_path.exists()


def test_default_runner_reports_compile_failure(tmp_path: Path):
    # Robust failure (not halt-on-error dependent): a document class that cannot exist.
    tex = tmp_path / "bad.tex"
    tex.write_text("\\documentclass{thisclassdoesnotexist9999}\n\\begin{document}x\\end{document}\n")
    out = _default_runner(tex, tmp_path / "bad.pdf")
    assert out.reason is CompileReason.COMPILE_FAILED


def test_pdf_page_count_parses_multiline_pdfinfo_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Realistic pdfinfo output: `Pages:` is NOT on line 1 — it comes after Creator/Producer/
    # CreationDate/etc. A non-MULTILINE `^Pages:` regex would never match this and silently
    # return None for every real compile.
    fixture = (
        "Creator:        LaTeX with hyperref\n"
        "Producer:       xdvipdfmx (0.1)\n"
        "CreationDate:   Sat Aug  8 00:00:00 2026\n"
        "Pages:           2\n"
        "Encrypted:      no\n"
    )

    class _Result:
        stdout = fixture
        returncode = 0

    def _fake_run(*args: object, **kwargs: object) -> _Result:
        return _Result()

    monkeypatch.setattr("boardwatch.reports.tailor.subprocess.run", _fake_run)
    assert _pdf_page_count(tmp_path / "whatever.pdf") == 2
