from __future__ import annotations

from boardwatch.tailor.equivalences import EquivalenceTable
from boardwatch.tailor.model import Bullet, Entry, Resume
from boardwatch.tailor.plan import Delete, EquivalenceSwap, Reorder, Select, TailorPlan
from boardwatch.tailor.tokens import whole_token_sub


class ApplyError(ValueError):
    """A plan op is invalid against the given resume or equivalence table."""


def apply_plan(resume: Resume, plan: TailorPlan, table: EquivalenceTable) -> Resume:
    pairs = {(p.from_phrase, p.to_phrase) for p in table.as_pairs()}
    all_bids = {b.bullet_id for e in resume.entries for b in e.bullets}
    all_eids = {e.entry_id for e in resume.entries}
    removed: set[str] = set()
    reorders: dict[str, tuple[str, ...]] = {}
    swaps: dict[str, list[tuple[str, str]]] = {}
    for op in plan.ops:
        if isinstance(op, Delete) or (isinstance(op, Select) and not op.keep):
            if op.bullet_id not in all_bids:
                raise ApplyError(f"unknown bullet_id {op.bullet_id!r}")
            removed.add(op.bullet_id)
        elif isinstance(op, Select):  # keep=True is a no-op marker
            if op.bullet_id not in all_bids:
                raise ApplyError(f"unknown bullet_id {op.bullet_id!r}")
        elif isinstance(op, Reorder):
            if op.entry_id not in all_eids:
                raise ApplyError(f"unknown entry_id {op.entry_id!r}")
            reorders[op.entry_id] = op.order
        elif isinstance(op, EquivalenceSwap):
            if op.bullet_id not in all_bids:
                raise ApplyError(f"unknown bullet_id {op.bullet_id!r}")
            if (op.from_phrase, op.to_phrase) not in pairs:
                raise ApplyError(f"swap {op.from_phrase}->{op.to_phrase} not in frozen table")
            swaps.setdefault(op.bullet_id, []).append((op.from_phrase, op.to_phrase))

    new_entries: list[Entry] = []
    for e in resume.entries:
        kept = [b for b in e.bullets if b.bullet_id not in removed]
        if e.entry_id in reorders:
            order = [bid for bid in reorders[e.entry_id] if bid not in removed]
            by_id = {b.bullet_id: b for b in kept}
            if set(order) != set(by_id):
                raise ApplyError(f"reorder of {e.entry_id} must cover exactly the kept bullets")
            kept = [by_id[bid] for bid in order]
        out_bullets: list[Bullet] = []
        for b in kept:
            text = b.text
            for frm, to in swaps.get(b.bullet_id, []):
                res = whole_token_sub(text, frm, to)
                if res is None:
                    raise ApplyError(f"swap {frm}->{to} has no whole-token match in {b.bullet_id}")
                text = res
            out_bullets.append(b if text == b.text else b.model_copy(update={"text": text}))
        new_entries.append(e.model_copy(update={"bullets": out_bullets}))
    return resume.model_copy(update={"entries": new_entries})
