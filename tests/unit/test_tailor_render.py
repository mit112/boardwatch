from __future__ import annotations

import re

from boardwatch.tailor.model import Bullet, Entry, Resume, SkillGroup
from boardwatch.tailor.render import parse_bullets
from boardwatch.tailor.render.typst import TypstRenderer


def R(b1: str = "Shipped JS", b2: str = "Built Python") -> Resume:
    return Resume(
        header=["Ada", "ada@x"],
        education=["BSc"],
        skill_groups=[SkillGroup(label="L", items=["Python"])],
        entries=[
            Entry(
                entry_id="e1",
                heading="Eng — Acme",
                bullets=[Bullet(bullet_id="b1", text=b1), Bullet(bullet_id="b2", text=b2)],
            )
        ],
    )


def test_emit_is_source_deterministic() -> None:
    r = R()
    rnd = TypstRenderer()
    assert rnd.emit(r) == rnd.emit(r)


def test_bullet_fidelity_roundtrip_adversarial() -> None:
    adv = 'weird "quote" and \\ backslash and # hash and {brace}'
    r = R(b1=adv)
    src = TypstRenderer().emit(r)
    assert parse_bullets(src) == [adv, "Built Python"]


def test_non_bullet_firewall() -> None:
    rnd = TypstRenderer()
    base = rnd.emit(R(b1="normal"))
    adv = rnd.emit(R(b1='"); #heading[HACKED]; #resume-bullet("x'))

    def strip(src: str) -> str:
        return re.sub(r'#resume-bullet\("(?:[^"\\]|\\.)*"\)', "#B", src)

    assert strip(base) == strip(adv)  # non-bullet regions identical


def test_to_pdf_uses_injected_runner(tmp_path):  # type: ignore[no-untyped-def]
    rnd = TypstRenderer()
    src = rnd.emit(R())
    ok = rnd.to_pdf(src, tmp_path, "out", runner=lambda typ, pdf: pdf.write_bytes(b"%PDF") or True)
    assert ok and ok.suffix == ".pdf" and ok.exists()
    missing = rnd.to_pdf(src, tmp_path, "out2", runner=lambda typ, pdf: False)
    assert missing is None


def test_parse_bullets_count_excludes_preamble_definition() -> None:
    r = R()
    src = TypstRenderer().emit(r)
    total_bullets = sum(len(e.bullets) for e in r.entries)
    assert len(parse_bullets(src)) == total_bullets
