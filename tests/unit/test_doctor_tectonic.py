from __future__ import annotations

import subprocess

from boardwatch.cli import doctor_cmd


def test_check_tectonic_missing(monkeypatch):
    monkeypatch.setattr(doctor_cmd.shutil, "which", lambda _: None)
    c = doctor_cmd.check_tectonic()
    assert c.available is False and c.failed is True
    assert "tectonic" in c.detail.lower()


def test_check_tectonic_ok(monkeypatch):
    monkeypatch.setattr(doctor_cmd.shutil, "which", lambda _: "/usr/local/bin/tectonic")
    monkeypatch.setattr(
        doctor_cmd.subprocess, "run",
        # re-review 2 M5: the real binary prints a CAPITAL "Tectonic" (verified locally:
        # `tectonic --version` -> "Tectonic 0.17.0"). Fixture derived from live output so a
        # case-sensitive `tectonic X.Y.Z` regex cannot false-green while reporting NOT FOUND in prod.
        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="Tectonic 0.17.0\n", stderr=""),
    )
    c = doctor_cmd.check_tectonic()
    assert c.available is True and c.failed is False and c.version == "0.17.0"


def test_check_pdfinfo_missing_is_a_failure(monkeypatch):
    """A hard dependency wearing a soft failure: without `pdfinfo`, `_pdf_page_count` returns
    None and every lead degrades to COMPILE_FAILED — an empty run every morning, which `doctor`
    used to call healthy because it probed only tectonic."""
    monkeypatch.setattr(doctor_cmd.shutil, "which", lambda _: None)
    assert doctor_cmd.check_pdfinfo() is False


def test_check_pdfinfo_present(monkeypatch):
    monkeypatch.setattr(doctor_cmd.shutil, "which", lambda _: "/opt/homebrew/bin/pdfinfo")
    assert doctor_cmd.check_pdfinfo() is True
