"""Why `EntryKind` is a closed catalog: the renderer drops what it cannot section.

The design said an out-of-catalog `kind` "falls through to Experience", so a typo "would render
silently". It does not. BOTH section filters are equality tests, so the entry matches neither and
vanishes from the PDF with no error at all. This test pins the real behaviour as an OUTSIDE fact,
so if the renderer ever gains a fall-through the catalog's rationale is revisited deliberately.
"""

from __future__ import annotations

from boardwatch.tailor.model import Bullet, Entry, Resume
from boardwatch.tailor.render.latex import LatexRenderer


def _resume(kind: str) -> Resume:
    return Resume(
        header=["Example Candidate", "candidate@example.com"],
        education=["Example University"],
        skill_groups=[],
        entries=[
            Entry(
                entry_id="entry.one",
                heading="Findable Heading",
                kind=kind,
                title="Findable Title",
                bullets=[Bullet(bullet_id="b1", text="A findable bullet sentence")],
            )
        ],
    )


def test_an_out_of_catalog_kind_disappears_from_the_rendered_source() -> None:
    source = LatexRenderer(config_dir=None).emit(_resume("publication"))
    assert "Findable Title" not in source
    assert "A findable bullet sentence" not in source


def test_both_catalog_values_do_reach_the_source() -> None:
    """Non-vacuity: the assertion above is about the KIND, not about the renderer being empty."""
    for kind in ("experience", "project"):
        source = LatexRenderer(config_dir=None).emit(_resume(kind))
        assert "A findable bullet sentence" in source, kind
