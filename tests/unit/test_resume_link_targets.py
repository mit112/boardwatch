r"""A link target must survive the render, and a target that cannot must never reach the render.

`\href{<url>}` is emitted inside the template's `\resumeProjectHeading{...}` macro ARGUMENT.
That placement is the whole problem: hyperref's `\href` changes catcodes to read its target
verbatim, but only when TeX has not already tokenized it — and inside a macro argument it has.
So `&`, `#` and `%` reach the engine as alignment tab, parameter and comment, and the compile
dies. Per LEAD, which the tailor stage reports as a run-level fatal with guidance pointing at
bullets.

Measured against tectonic 0.17 through this very emitter (probe:
`.agent/2026-09-04e-session/t10probe/render_probe.py`), for a target `https://example.com/a<X>b`:

    raw       escaped      character
    FAIL      OK           &  #  %
    OK        OK           _
    OK        DRIFT        $        (escaping yields `\protect \TU\textdollar`)
    OK        n/a          ~  ^
    FAIL      DRIFT        {  }     (escaped `{` renders the backslash into the target)
    FAIL      FAIL         \

So the emitter escapes exactly `&`, `#`, `%`, and `projection/pool.py` refuses exactly `{`,
`}`, `\` — the three no escaping can carry.

The PDF's own link annotation is read back, which is a DIFFERENT path from the one that wrote
it (CLAUDE.md: count the deliverable through a different path than the one that produced it) —
asserting on the `.tex` would only prove the emitter agrees with itself.
"""

from __future__ import annotations

import re
import shutil
import zlib
from pathlib import Path

import pytest

from boardwatch.reports.tailor import _default_runner
from boardwatch.tailor.model import Bullet, Entry, Resume, SkillGroup
from boardwatch.tailor.render.latex import LatexRenderer
from boardwatch.tailor.render.outcome import CompileReason

_requires_tectonic = pytest.mark.skipif(
    shutil.which("tectonic") is None, reason="tectonic not installed"
)


def _resume(link_url: str) -> Resume:
    return Resume(
        header=["Jordan Rivera", "Boston, MA"],
        education=["MS Computer Science — Example University — 2025"],
        skill_groups=[SkillGroup(label="Languages", items=["Python"])],
        entries=[
            Entry(
                entry_id="p1", heading="Packet Pantry", kind="project", title="Packet Pantry",
                subtitle="Python", dates="2024",
                link_url=link_url, link_label="repo",
                bullets=[Bullet(bullet_id="b1", text="Built a thing.")],
            )
        ],
    )


def _link_targets(pdf: Path) -> list[str]:
    """Every `/URI` in the PDF's link annotations, decompressing object streams."""
    data = pdf.read_bytes()
    found: list[bytes] = re.findall(rb"/URI\s*\(([^)]*)\)", data)
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        try:
            body = zlib.decompress(match.group(1))
        except zlib.error:
            continue
        found += re.findall(rb"/URI\s*\(([^)]*)\)", body)
    # PDF string syntax escapes `\` and the parens; nothing else here needs unescaping.
    return [raw.decode("latin-1").replace("\\\\", "\\") for raw in found]


@_requires_tectonic
@pytest.mark.parametrize(
    "url",
    [
        "https://example.test/a?x=1&y=2",
        "https://example.test/a#readme",
        "https://example.test/a%20b",
        "https://example.test/a_b",
        "https://example.test/a~b",
        "https://example.test/a$b",
    ],
    ids=["amp", "hash", "percent", "underscore", "tilde", "dollar"],
)
def test_a_special_character_link_target_renders_and_arrives_intact(
    url: str, tmp_path: Path
) -> None:
    renderer = LatexRenderer()  # config_dir=None -> the bundled default template
    outcome = renderer.to_pdf(renderer.emit(_resume(url)), tmp_path, "link", _default_runner)
    assert outcome.reason is CompileReason.OK, outcome.log[-2000:]
    assert url in _link_targets(tmp_path / "link.pdf")
