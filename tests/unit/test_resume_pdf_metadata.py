"""The delivered résumé's PDF /Info dictionary must name the document and its author.

The defect this guards, measured on a delivered artifact: the template loads
`\\usepackage[hidelinks]{hyperref}` and sets no `\\hypersetup`, so the /Info dictionary carries
`/Creator (LaTeX with hyperref)` — hyperref's own default, and correct as a *creator* — and no
`/Title` or `/Author` key at all. A recruiter's viewer then shows the tab, the print header and
the document properties as an untitled file by an unknown author.

Employer names are arbitrary text, so the metadata is the one place every LaTeX special has
to survive intact: `\\hypersetup{pdftitle={Procter & Gamble}}` does not compile, and hyperref
does not escape it for you. This compiles a real résumé through the production renderer +
tectonic and reads the result back with poppler's `pdfinfo` — a DIFFERENT path from the one
that produced the PDF (CLAUDE.md: count the deliverable through a different path).

Skipped, not xfailed, when the toolchain is absent: tectonic fetches its package bundle on
first compile, so an installed-but-offline env would fail rather than skip.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from boardwatch.delivery.names import plan_resume_naming
from boardwatch.reports.tailor import _default_runner
from boardwatch.tailor.model import Bullet, Entry, Resume, SkillGroup
from boardwatch.tailor.render.latex import LatexRenderer
from boardwatch.tailor.render.outcome import CompileReason

_requires_toolchain = pytest.mark.skipif(
    shutil.which("tectonic") is None or shutil.which("pdfinfo") is None,
    reason="tectonic and/or pdfinfo (poppler) not installed",
)

#: What hyperref stamps as `/Creator`. It must never end up in the author slot.
HYPERREF_CREATOR = "LaTeX with hyperref"

OWNER = "Ada Lovelace"
#: Every character `escape` has a rule for, inside a plausible employer name.
NASTY_COMPANY = r"Procter & Gamble_Labs #2 ~ $5 {x} ^y \z 100% Café"
ROLE = "Backend Engineer II"


def _resume() -> Resume:
    return Resume(
        header=[OWNER, "Boston, MA · ada@example.com"],
        education=["BSc Mathematics — Example University — 2018"],
        title=ROLE,
        skill_groups=[SkillGroup(label="Languages", items=["Python", "Go"])],
        entries=[
            Entry(
                entry_id="e1", heading="ig", kind="experience", title="Software Engineer",
                dates="Jul 2024 -- Feb 2025", subtitle="Acme Corp", location="Boston, MA",
                bullets=[Bullet(bullet_id="b1", text="Cut p99 latency 40% by batching writes")],
            )
        ],
    )


def _info(pdf: Path) -> dict[str, str]:
    """`pdfinfo`'s key/value report. Split on the FIRST colon only: a title carries its own.

    `encoding` is pinned rather than left to `text=True`: poppler writes UTF-8, and the
    locale codec is cp1252 on Windows, which turns the accent into two characters."""
    finished = subprocess.run(
        ["pdfinfo", str(pdf)], capture_output=True, encoding="utf-8", check=True, timeout=60
    )
    fields: dict[str, str] = {}
    for line in finished.stdout.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


@_requires_toolchain
def test_the_pdf_carries_the_planned_title_and_the_owner_as_author(tmp_path: Path) -> None:
    naming = plan_resume_naming(
        owner_name=OWNER, company=NASTY_COMPANY, role=ROLE, identity_hash="1"
    )
    renderer = LatexRenderer(pdf_title=naming.pdf_title, pdf_author=naming.pdf_author)
    outcome = renderer.to_pdf(renderer.emit(_resume()), tmp_path, naming.stem, _default_runner)

    assert outcome.reason is CompileReason.OK, outcome.log
    assert outcome.pdf_path is not None
    info = _info(outcome.pdf_path)

    # Every LaTeX special round-trips through hyperref's `\pdfstringdef` as itself, and the
    # non-ASCII accent survives as itself rather than as a mojibake or a dropped character.
    assert info["Title"] == f"{OWNER} - {ROLE} - {NASTY_COMPANY}"
    # Both keys are ABSENT before the fix, so reading them is itself the assertion.
    assert info["Author"] == OWNER
    assert info["Author"] != HYPERREF_CREATOR
