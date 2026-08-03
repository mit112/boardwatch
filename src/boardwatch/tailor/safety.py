from __future__ import annotations

from boardwatch.tailor.equivalences import EquivalenceTable
from boardwatch.tailor.model import Resume
from boardwatch.tailor.plan import Delete, EquivalenceSwap, Reorder, Select, TailorPlan
from boardwatch.tailor.tokens import has_whole_token, toks


class TierASafetyError(RuntimeError):
    """The produced resume or plan failed the Tier A no-fabrication guarantee."""


def plan_is_structurally_safe(
    resume: Resume, plan: TailorPlan, table: EquivalenceTable
) -> bool:
    bullets = {b.bullet_id: b for e in resume.entries for b in e.bullets}
    entry_bids = {e.entry_id: {b.bullet_id for b in e.bullets} for e in resume.entries}
    pairs = {(p.from_phrase, p.to_phrase) for p in table.as_pairs()}
    for op in plan.ops:
        if isinstance(op, (Select, Delete)):
            if op.bullet_id not in bullets:
                return False
        elif isinstance(op, Reorder):
            if op.entry_id not in entry_bids:
                return False
            # "Every referenced id exists" (L6a) covers the order list too: an order naming
            # ids from another entry — or none at all — is not a reordering of this entry.
            # apply_plan also rejects it, but this limb must stand on its own.
            if len(set(op.order)) != len(op.order):
                return False
            if not set(op.order).issubset(entry_bids[op.entry_id]):
                return False
        elif isinstance(op, EquivalenceSwap):
            if op.bullet_id not in bullets:
                return False
            if (op.from_phrase, op.to_phrase) not in pairs:
                return False
            if not has_whole_token(bullets[op.bullet_id].text, op.from_phrase):
                return False
        else:
            return False
    return True


def output_is_entailed(
    master: Resume, tailored: Resume, table: EquivalenceTable
) -> bool:
    if (
        master.header != tailored.header
        or master.education != tailored.education
        or master.skill_groups != tailored.skill_groups
    ):
        return False
    if [e.entry_id for e in master.entries] != [e.entry_id for e in tailored.entries]:
        return False
    swap = {p.from_phrase.lower(): p.to_phrase for p in table.as_pairs()}
    m_bullets = {b.bullet_id: b for e in master.entries for b in e.bullets}
    for me, te in zip(master.entries, tailored.entries, strict=True):
        if me.heading != te.heading:
            return False
        t_ids = {b.bullet_id for b in te.bullets}
        if not t_ids.issubset({b.bullet_id for b in me.bullets}):  # no new bullets
            return False
        for tb in te.bullets:
            mb = m_bullets[tb.bullet_id]
            mt, tt = toks(mb.text), toks(tb.text)
            if len(mt) != len(tt):
                return False
            for mtok, ttok in zip(mt, tt, strict=True):
                if ttok == mtok:
                    continue
                if swap.get(mtok.lower()) == ttok:  # ttok is the table image of mtok
                    continue
                return False
    return True


def enforce_tier_a(
    master: Resume, tailored: Resume, plan: TailorPlan, table: EquivalenceTable
) -> None:
    if not (
        plan_is_structurally_safe(master, plan, table)
        and output_is_entailed(master, tailored, table)
    ):
        raise TierASafetyError("Tier A safety check failed; refusing to render")
