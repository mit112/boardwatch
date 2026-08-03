from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from boardwatch.extract.taxonomy import Taxonomy
from boardwatch.tailor.equivalences import EquivalenceTable
from boardwatch.tailor.model import Bullet, Resume
from boardwatch.tailor.tokens import has_whole_token


class _Op(BaseModel):
    model_config = ConfigDict(frozen=True)


class Select(_Op):
    bullet_id: str
    keep: bool


class Reorder(_Op):
    entry_id: str
    order: tuple[str, ...]


class Delete(_Op):
    bullet_id: str


class EquivalenceSwap(_Op):
    bullet_id: str
    from_phrase: str
    to_phrase: str


Op = Select | Reorder | Delete | EquivalenceSwap


class TailorPlan(BaseModel):
    model_config = ConfigDict(frozen=True)
    ops: tuple[Op, ...]


MAX_BULLETS_PER_ENTRY = 6


def _applicable_swaps(
    text: str, jd_skills: set[str], table: EquivalenceTable
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for p in table.as_pairs():
        if (
            p.to_phrase in jd_skills
            and has_whole_token(text, p.from_phrase)
            and not has_whole_token(text, p.to_phrase)
        ):
            out.append((p.from_phrase, p.to_phrase))
    return out


def build_plan(
    resume: Resume, jd_skills: set[str], table: EquivalenceTable, taxonomy: Taxonomy
) -> TailorPlan:
    if not jd_skills:
        return TailorPlan(ops=())
    swaps_by_bullet = {
        b.bullet_id: _applicable_swaps(b.text, jd_skills, table)
        for e in resume.entries
        for b in e.bullets
    }

    def cover(b: Bullet) -> int:
        eff = taxonomy.extract(b.text) | {to for _, to in swaps_by_bullet[b.bullet_id]}
        return len(eff & jd_skills)

    coverage = {b.bullet_id: cover(b) for e in resume.entries for b in e.bullets}
    if not any(coverage.values()):
        return TailorPlan(ops=())
    ops: list[Op] = []
    kept: set[str] = set()
    for e in resume.entries:
        idx = sorted(enumerate(e.bullets), key=lambda t: (-coverage[t[1].bullet_id], t[0]))
        keep = idx[:MAX_BULLETS_PER_ENTRY]
        ops.append(Reorder(entry_id=e.entry_id, order=tuple(b.bullet_id for _, b in keep)))
        for _, b in idx[MAX_BULLETS_PER_ENTRY:]:
            ops.append(Delete(bullet_id=b.bullet_id))
        kept.update(b.bullet_id for _, b in keep)
    for p in table.as_pairs():  # table order
        for e in resume.entries:  # then bullet order
            for b in e.bullets:
                if (
                    b.bullet_id in kept
                    and (p.from_phrase, p.to_phrase) in swaps_by_bullet[b.bullet_id]
                ):
                    ops.append(
                        EquivalenceSwap(
                            bullet_id=b.bullet_id, from_phrase=p.from_phrase, to_phrase=p.to_phrase
                        )
                    )
    return TailorPlan(ops=tuple(ops))
