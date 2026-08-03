from pathlib import Path

from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.tailor.apply import apply_plan
from boardwatch.tailor.equivalences import load_equivalences
from boardwatch.tailor.model import Bullet, Entry, Resume
from boardwatch.tailor.plan import MAX_BULLETS_PER_ENTRY, build_plan

TBL = load_equivalences()
TAX = load_taxonomy(Path("/nonexistent"))  # bundled taxonomy


def test_identity_plan_on_zero_overlap() -> None:
    r = Resume(
        header=["h"],
        education=[],
        skill_groups=[],
        entries=[Entry(entry_id="e1", heading="H", bullets=[Bullet(bullet_id="b1", text="Wrote docs")])],
    )
    assert build_plan(r, set(), TBL, TAX).ops == ()
    assert build_plan(r, {"Python"}, TBL, TAX).ops == ()  # no Python in résumé


def test_reorder_leads_with_covering_bullet() -> None:
    r = Resume(
        header=["h"],
        education=[],
        skill_groups=[],
        entries=[
            Entry(
                entry_id="e1",
                heading="H",
                bullets=[
                    Bullet(bullet_id="b1", text="Wrote docs"),
                    Bullet(bullet_id="b2", text="Built a Python service"),
                ],
            )
        ],
    )
    out = apply_plan(r, build_plan(r, {"Python"}, TBL, TAX), TBL)
    assert out.entries[0].bullets[0].bullet_id == "b2"  # Python bullet leads


def test_drops_beyond_cap() -> None:
    bullets = [Bullet(bullet_id=f"b{i}", text="Wrote docs") for i in range(MAX_BULLETS_PER_ENTRY + 2)]
    bullets[0] = Bullet(bullet_id="b0", text="Built a Python service")
    r = Resume(
        header=["h"],
        education=[],
        skill_groups=[],
        entries=[Entry(entry_id="e1", heading="H", bullets=bullets)],
    )
    out = apply_plan(r, build_plan(r, {"Python"}, TBL, TAX), TBL)
    assert len(out.entries[0].bullets) == MAX_BULLETS_PER_ENTRY
    assert out.entries[0].bullets[0].bullet_id == "b0"


def test_swap_emitted_only_when_to_is_jd_skill() -> None:
    r = Resume(
        header=["h"],
        education=[],
        skill_groups=[],
        entries=[Entry(entry_id="e1", heading="H", bullets=[Bullet(bullet_id="b1", text="Shipped JS at scale")])],
    )
    out = apply_plan(r, build_plan(r, {"JavaScript"}, TBL, TAX), TBL)
    assert "JavaScript" in out.entries[0].bullets[0].text
    out2 = apply_plan(r, build_plan(r, {"Rust"}, TBL, TAX), TBL)  # JavaScript not wanted
    assert out2.entries[0].bullets[0].text == "Shipped JS at scale"


def test_deterministic() -> None:
    r = Resume(
        header=["h"],
        education=[],
        skill_groups=[],
        entries=[
            Entry(
                entry_id="e1",
                heading="H",
                bullets=[
                    Bullet(bullet_id="b1", text="Built a Python service"),
                    Bullet(bullet_id="b2", text="Also Python here"),
                ],
            )
        ],
    )
    assert build_plan(r, {"Python"}, TBL, TAX) == build_plan(r, {"Python"}, TBL, TAX)
