"""doctor's typst probe (P1a): the résumé PDF gate requires typst 0.15.1 — the page-count
`typst eval` syntax it relies on is version-sensitive. Missing binary is an actionable
failure; a version other than the pin is a loud warning, not a hard fail."""

from __future__ import annotations

from types import SimpleNamespace

from boardwatch.cli.doctor_cmd import check_typst


def test_typst_present_pinned_version_passes(monkeypatch) -> None:
    monkeypatch.setattr("boardwatch.cli.doctor_cmd.shutil.which", lambda name: "/usr/local/bin/typst")
    monkeypatch.setattr(
        "boardwatch.cli.doctor_cmd.subprocess.run",
        lambda *a, **k: SimpleNamespace(stdout="typst 0.15.1 (abc1234)", stderr="", returncode=0),
    )
    result = check_typst()
    assert result.found is True
    assert result.failed is False
    assert result.message is None
    assert result.version == "0.15.1"


def test_typst_missing_binary_is_actionable_failure(monkeypatch) -> None:
    monkeypatch.setattr("boardwatch.cli.doctor_cmd.shutil.which", lambda name: None)

    def _boom(*a, **k):  # subprocess must never be invoked when the binary is absent
        raise AssertionError("subprocess.run should not be called when typst is missing")

    monkeypatch.setattr("boardwatch.cli.doctor_cmd.subprocess.run", _boom)
    result = check_typst()
    assert result.found is False
    assert result.failed is True
    assert result.message is not None
    assert "typst" in result.message.lower()


def test_typst_version_mismatch_is_warning_not_failure(monkeypatch) -> None:
    monkeypatch.setattr("boardwatch.cli.doctor_cmd.shutil.which", lambda name: "/usr/local/bin/typst")
    monkeypatch.setattr(
        "boardwatch.cli.doctor_cmd.subprocess.run",
        lambda *a, **k: SimpleNamespace(stdout="typst 0.14.0 (def5678)", stderr="", returncode=0),
    )
    result = check_typst()
    assert result.found is True
    assert result.failed is False  # a version mismatch must not fail the run
    assert result.message is not None
    assert "0.14.0" in result.message
    assert "0.15.1" in result.message


def test_typst_present_but_broken_binary_is_actionable_failure(monkeypatch) -> None:
    # present on PATH but exits non-zero (wrong arch, corrupt install, ...) — the PDF gate
    # cannot use it either way, so this must fail, not fall into the "unknown version" warning
    monkeypatch.setattr("boardwatch.cli.doctor_cmd.shutil.which", lambda name: "/usr/local/bin/typst")
    monkeypatch.setattr(
        "boardwatch.cli.doctor_cmd.subprocess.run",
        lambda *a, **k: SimpleNamespace(stdout="", stderr="exec format error", returncode=1),
    )
    result = check_typst()
    assert result.found is True
    assert result.failed is True
    assert result.message is not None
