from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from boardwatch.reports.tailor import _default_runner, _pdf_page_count
from boardwatch.tailor.render.outcome import CompileReason

# NOTE (plan-review m1): this guard only checks the binary is present. tectonic fetches its
# package bundle (hundreds of MB) on FIRST compile — an installed-but-offline env will FAIL the
# OK test, not skip it. Task 1's Dockerfile warms the bundle at image-build time; run locally
# online at least once so the bundle is cached before `make check` in an offline setting.
#
# NOTE (fix round 1, review m1): this used to be a module-level `pytestmark`, which skipped
# ALL tests in this file — including `test_pdf_page_count_parses_multiline_pdfinfo_output`,
# which monkeypatches `subprocess.run` and needs neither tectonic nor pdfinfo. That test's
# whole purpose is to catch a regression of the `re.MULTILINE` fix, so it must run in exactly
# the environments (pdfinfo present, tectonic not yet installed) where the regression is most
# likely. The skip is now applied per-test, only to the two real-compile tests below.
_requires_tectonic = pytest.mark.skipif(
    shutil.which("tectonic") is None, reason="tectonic not installed"
)

_MINIMAL = "\\documentclass{article}\n\\begin{document}\nHello \\% world\n\\end{document}\n"


@_requires_tectonic
def test_default_runner_compiles_and_counts_pages(tmp_path: Path):
    tex = tmp_path / "r.tex"
    tex.write_text(_MINIMAL)
    out = _default_runner(tex, tmp_path / "r.pdf")
    assert out.reason is CompileReason.OK and out.page_count == 1 and out.pdf_path.exists()


@_requires_tectonic
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


# --- the defect: a missing pdfinfo must not launder into COMPILE_FAILED ------------------


def test_default_runner_missing_pdfinfo_is_binary_missing_not_compile_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The defect this closes: today, a missing `pdfinfo` is only checked inside
    `_pdf_page_count`, called AFTER tectonic has already compiled -- so it comes back as
    COMPILE_FAILED, indistinguishable from a real compile defect. `_default_runner` must
    preflight `pdfinfo` beside its existing tectonic check and report BINARY_MISSING
    instead, naming pdfinfo as the missing tool."""

    def fake_which(name: str) -> str | None:
        return "/usr/bin/tectonic" if name == "tectonic" else None

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        # Under the fix this is never called at all (the preflight returns first); under
        # today's code it is the real tectonic compile step, which must succeed so the bug
        # under test -- what happens AFTER a successful compile -- is isolated.
        (tmp_path / "r.pdf").write_bytes(b"%PDF-1.7\n%stub\n")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("boardwatch.reports.tailor.shutil.which", fake_which)
    monkeypatch.setattr("boardwatch.reports.tailor.subprocess.run", fake_run)
    tex = tmp_path / "r.tex"
    tex.write_text(_MINIMAL)
    out = _default_runner(tex, tmp_path / "r.pdf")
    assert out.reason is CompileReason.BINARY_MISSING
    assert out.tool == "pdfinfo"


def test_default_runner_missing_tectonic_tool_is_tectonic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: the pre-existing tectonic-missing path must keep reporting BINARY_MISSING,
    and the new `tool` field must name tectonic, not pdfinfo -- the added field's default must
    not make this report the wrong tool."""
    monkeypatch.setattr("boardwatch.reports.tailor.shutil.which", lambda _name: None)
    tex = tmp_path / "r.tex"
    tex.write_text(_MINIMAL)
    out = _default_runner(tex, tmp_path / "r.pdf")
    assert out.reason is CompileReason.BINARY_MISSING
    assert out.tool == "tectonic"


def test_default_runner_pdfinfo_present_nonzero_exit_is_compile_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Narrow-guard proof: with BOTH binaries reported present, a real pdfinfo failure (a
    non-zero exit, e.g. a corrupt PDF) must still surface as COMPILE_FAILED, not
    BINARY_MISSING -- the new preflight must not swallow genuine compile failures."""

    def fake_which(name: str) -> str | None:
        return f"/usr/bin/{name}"

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if cmd[0] == "tectonic":
            (tmp_path / "r.pdf").write_bytes(b"%PDF-1.7\n%stub\n")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        assert cmd[0] == "pdfinfo"
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="Error: corrupt xref")

    monkeypatch.setattr("boardwatch.reports.tailor.shutil.which", fake_which)
    monkeypatch.setattr("boardwatch.reports.tailor.subprocess.run", fake_run)
    tex = tmp_path / "r.tex"
    tex.write_text(_MINIMAL)
    out = _default_runner(tex, tmp_path / "r.pdf")
    assert out.reason is CompileReason.COMPILE_FAILED


def test_pdf_page_count_returns_none_on_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One of `_pdf_page_count`'s two remaining (non-binary-missing) failure causes: a
    present pdfinfo that exits non-zero. Must keep returning None -- untouched by the
    binary-missing fix."""

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 1, stdout="", stderr="Error: corrupt xref")

    monkeypatch.setattr("boardwatch.reports.tailor.subprocess.run", fake_run)
    assert _pdf_page_count(tmp_path / "whatever.pdf") is None


def test_pdf_page_count_returns_none_on_unparseable_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other remaining cause: a present pdfinfo whose output has no parseable `Pages:`
    line. Must keep returning None -- untouched by the binary-missing fix."""

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            [], 0, stdout="Creator: nothing useful here\n", stderr=""
        )

    monkeypatch.setattr("boardwatch.reports.tailor.subprocess.run", fake_run)
    assert _pdf_page_count(tmp_path / "whatever.pdf") is None
