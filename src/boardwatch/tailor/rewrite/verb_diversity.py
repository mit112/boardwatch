"""Résumé-wide verb-opening diversity post-pass (P4 item 3a, 2c): no more than
`max_repeats` shipped bullets may open with the same verb (roadmap: "no more than 2
bullets... with the same opening verb"). Unlike the per-bullet register/overmatch/
provenance gates, this is a property of *which bullets co-exist*, so it cannot be a gate
inside the per-bullet loop -- it runs once, over the assembled `TierBResult`, after that
loop finishes (see item3-guard-extensions-design.md §2c).

CRITICAL: Mit's own Tier-A bullets seed the histogram and are NEVER demoted -- only
excess-repeat ACCEPTED Tier-B rewrites get reverted back to Tier-A. This guard stops the
LLM from introducing repetition; it does not audit Mit's authored content. Pure: no I/O,
no LLM call.
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
    """Seed the opening-verb histogram from the Tier-A bullets that are NOT superseded by
    an accepted Tier-B rewrite (the baseline). Then walk the accepted rewrites IN BULLET
    ORDER (the order `run_tier_b_core`'s loop already produced `result.accepted` in): the
    first `max_repeats` occurrences of a verb stand, later ones are demoted back to
    Tier-A with `drop_reason="verb_repeat"` and dropped from `accepted`.
    """
    a_text_by_id = {b.bullet_id: b.text for entry in tailored_a.entries for b in entry.bullets}
    accepted_ids = {r.bullet_id for r in result.accepted}

    histogram: dict[str, int] = {}
    for bullet_id, text in a_text_by_id.items():
        if bullet_id in accepted_ids:
            continue  # this bullet ships as its accepted Tier-B rewrite, not Tier-A
        verb = _opening_verb(text)
        histogram[verb] = histogram.get(verb, 0) + 1

    kept_accepted: list[Rewrite] = []
    demoted_ids: set[str] = set()
    for rewrite in result.accepted:
        verb = _opening_verb(rewrite.text)
        count = histogram.get(verb, 0)
        if count >= max_repeats:
            demoted_ids.add(rewrite.bullet_id)
            continue
        histogram[verb] = count + 1
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
