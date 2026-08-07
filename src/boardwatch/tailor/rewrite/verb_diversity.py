"""Résumé-wide verb-opening diversity post-pass (P4 item 3a, 2c): a Tier-B rewrite is
never allowed to push a verb's SHIPPED count above `max_repeats` when a diversifying
Tier-A fallback exists (roadmap: "no more than 2 bullets... with the same opening
verb"). Unlike the per-bullet register/overmatch/provenance gates, this is a property of
*which bullets co-exist*, so it cannot be a gate inside the per-bullet loop -- it runs
once, over the assembled `TierBResult`, after that loop finishes (see
item3-guard-extensions-design.md §2c).

Honest invariant (corrected 2026-08-07 -- the original wording claimed an absolute cap
that reverting to Tier-A cannot always deliver): demoting a rewrite only helps when its
OWN Tier-A original opens with a DIFFERENT, still-under-cap verb. If the Tier-A original
shares the rewrite's verb, or the Tier-A verb is itself already at/over cap, reverting
ships the same violation for nothing -- the rewrite is kept instead, sacrificing no good
rewrite for zero diversity gain. The Tier-A baseline (bullets never rewritten, or
dropped by an earlier gate) is NEVER modified and MAY legitimately exceed the cap on its
own; Mit's authored content is never audited or demoted. Pure: no I/O, no LLM call.
"""

from __future__ import annotations

import re
from dataclasses import replace

from boardwatch.tailor.model import Resume
from boardwatch.tailor.plan import Rewrite
from boardwatch.tailor.rewrite.result import RewriteRow, TierBResult

VERB_DIVERSITY_VERSION = "p4-verb-diversity-1"

_OPENING_WORD = re.compile(r"[A-Za-z]+")


def _opening_verb(text: str) -> str:
    match = _OPENING_WORD.search(text)
    return match.group(0).lower() if match else ""


def enforce_verb_diversity(
    tailored_a: Resume, result: TierBResult, *, max_repeats: int = 2
) -> TierBResult:
    """Seed the opening-verb histogram from the Tier-A bullets that are IMMOVABLE --
    every bullet NOT in `result.accepted` (never rewritten, or dropped by an earlier
    gate), which ships its Tier-A text regardless of anything below. A bullet currently
    accepted must be excluded here: its own contribution is folded in one at a time,
    under whichever verb (rewrite's or its own Tier-A fallback's) actually ends up
    shipping, as that decision is made below -- seeding it here too would count the same
    bullet under a verb it may never ship.

    Then walk the accepted rewrites IN BULLET ORDER (the order `run_tier_b_core`'s loop
    already produced `result.accepted` in). For each: keep it if doing so would not push
    its own verb over the cap; otherwise demote it to Tier-A ONLY IF that fallback opens
    with a different verb that is itself still under cap (a real diversity gain), and
    keep the rewrite (over cap) otherwise.
    """
    a_text_by_id = {b.bullet_id: b.text for entry in tailored_a.entries for b in entry.bullets}
    accepted_ids = {r.bullet_id for r in result.accepted}

    histogram: dict[str, int] = {}
    for bullet_id, text in a_text_by_id.items():
        if bullet_id in accepted_ids:
            continue  # immovable only for bullets NOT currently accepted
        verb = _opening_verb(text)
        histogram[verb] = histogram.get(verb, 0) + 1

    kept_accepted: list[Rewrite] = []
    demoted_ids: set[str] = set()
    for rewrite in result.accepted:
        rw_verb = _opening_verb(rewrite.text)
        ta_verb = _opening_verb(a_text_by_id[rewrite.bullet_id])
        rw_count = histogram.get(rw_verb, 0)

        if rw_count < max_repeats:
            histogram[rw_verb] = rw_count + 1
            kept_accepted.append(rewrite)
            continue

        if ta_verb != rw_verb and histogram.get(ta_verb, 0) < max_repeats:
            # Demoting genuinely diversifies: the Tier-A fallback ships a different,
            # still-under-cap verb.
            demoted_ids.add(rewrite.bullet_id)
            histogram[ta_verb] = histogram.get(ta_verb, 0) + 1
        else:
            # Demoting would ship the same verb (or one already at/over cap) -- no
            # diversity gain, so keep the rewrite rather than sacrifice it for nothing.
            histogram[rw_verb] = rw_count + 1
            kept_accepted.append(rewrite)

    if not demoted_ids:
        return result

    new_rows: list[RewriteRow] = [
        replace(row, kept=False, drop_reason="verb_repeat")
        if row.bullet_id in demoted_ids and row.kept
        else row
        for row in result.rows
    ]
    return TierBResult(accepted=kept_accepted, rows=new_rows, calls_made=result.calls_made)
