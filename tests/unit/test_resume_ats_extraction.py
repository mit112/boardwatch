"""The rendered résumé PDF must be ATS-parsable: a plain-text extraction of it must contain
the résumé's words as pure ASCII.

The defect this guards: XeTeX's default Computer Modern emits the ff/ffi/ffl ligatures as
single glyphs in the U+FB00-FB04 block with no decomposing ToUnicode map, so `pdftotext`
(and every ATS, which parses the same text layer) extracts "efficiency" as
"e" + U+FB00 + "iciency". A recruiter's keyword search for "efficiency" or "traffic" then
misses the résumé entirely. The bundled template loads Latin Modern via fontspec with the
common ligatures disabled so every glyph maps back to plain ASCII.

This compiles a real résumé through the production renderer + tectonic and extracts it with
poppler's `pdftotext` — a DIFFERENT path from the one that produced the PDF (CLAUDE.md: count
the deliverable through a different path than the one that produced it). It is skipped, not
xfailed, when the render toolchain is absent: like `test_tectonic_runner.py`, tectonic fetches
its package bundle on first compile, so an installed-but-offline env would fail rather than skip
— run online once to warm the cache.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from boardwatch.reports.tailor import _default_runner
from boardwatch.tailor.model import Bullet, Entry, Resume, SkillGroup
from boardwatch.tailor.render.latex import LatexRenderer
from boardwatch.tailor.render.outcome import CompileReason

_requires_toolchain = pytest.mark.skipif(
    shutil.which("tectonic") is None or shutil.which("pdftotext") is None,
    reason="tectonic and/or pdftotext (poppler) not installed",
)

# The U+FB00-FB06 block: the Latin f/s/t ligatures pdftotext leaks when a font ligates
# without a decomposing ToUnicode. FB00 ff, FB01 fi, FB02 fl, FB03 ffi, FB04 ffl, FB05/06 st.
_LIGATURE_RANGE = range(0xFB00, 0xFB07)


def _ats_resume() -> Resume:
    """A résumé whose bullets carry the ff-family words that broke under Computer Modern:
    efficiency (ff), traffic (ff), office (ff), staffing (ff), affluent (ffl)."""
    return Resume(
        header=["Jordan Rivera", "Boston, MA · jordan@example.com"],
        education=["MS Computer Science — Example University — 2025"],
        title="Backend Software Engineer",
        skill_groups=[SkillGroup(label="Languages", items=["Python", "Go", "SQL"])],
        entries=[
            Entry(
                entry_id="e1", heading="ig", kind="experience", title="Software Engineer",
                dates="Jul 2024 -- Feb 2025", subtitle="Acme Corp", location="Boston, MA",
                bullets=[
                    Bullet(bullet_id="b1", text="Improved pipeline efficiency 40% by batching writes"),
                    Bullet(bullet_id="b2", text="Cut traffic to the origin server via edge caching"),
                    Bullet(bullet_id="b3", text="Automated office staffing reports across teams"),
                ],
            ),
            Entry(
                entry_id="p1", heading="ig", kind="project", title="Knowledge Forge",
                dates="Sep 2023 -- Dec 2023", subtitle="Python, Django",
                bullets=[
                    Bullet(bullet_id="b4", text="Designed an affluent-tier billing flow"),
                ],
            ),
        ],
    )


@_requires_toolchain
def test_rendered_pdf_extracts_ff_words_as_ascii(tmp_path: Path) -> None:
    renderer = LatexRenderer()  # config_dir=None -> the bundled default template
    source = renderer.emit(_ats_resume())
    outcome = renderer.to_pdf(source, tmp_path, "ats", _default_runner)
    assert outcome.reason is CompileReason.OK, outcome.log[-2000:]

    pdf = tmp_path / "ats.pdf"
    txt = tmp_path / "ats.txt"
    subprocess.run(["pdftotext", str(pdf), str(txt)], check=True)
    text = txt.read_text(encoding="utf-8", errors="replace")

    # The ff-family words extract as plain ASCII, so a keyword search finds them.
    for word in ("efficiency", "traffic", "office", "staffing", "affluent"):
        assert word in text, f"{word!r} not found as ASCII in the extracted text: {text!r}"

    # No character from the U+FB00-FB06 ligature block survives into the text layer, and no
    # NUL bytes (the failure mode of \XeTeXgenerateactualtext with the legacy CM fonts).
    leaked = sorted({hex(ord(c)) for c in text if ord(c) in _LIGATURE_RANGE})
    assert not leaked, f"ligature codepoints leaked into the ATS text layer: {leaked}"
    assert "\x00" not in text, "NUL bytes in the extracted text layer"
