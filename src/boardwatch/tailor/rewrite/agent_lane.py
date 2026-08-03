"""Pure logic for the subscription Tier B agent lane's step 1 (P7b task 4): turn a
Tier-A-planned résumé + its JD skills into the JSON `RewriteRequest` a rewriter agent
consumes. No I/O here — the CLI (`boardwatch tailor rewrite request`) drives
`reports.tailor.plan_tier_a` for the résumé/jd_skills and writes the result via
`agent_io.dump_json`.
"""

from __future__ import annotations

from dataclasses import dataclass

from boardwatch.extract.taxonomy import Taxonomy
from boardwatch.tailor.model import Resume
from boardwatch.tailor.rewrite.agent_io import (
    BulletRef,
    CandidatesFile,
    JudgeItem,
    JudgeRequest,
    RewriteRequest,
)
from boardwatch.tailor.rewrite.filter import passes_overmatch_filter


def build_rewrite_request(
    tailored: Resume, jd_skills: set[str], *, request_id: str
) -> RewriteRequest:
    """Flatten the Tier-A-tailored résumé's surviving bullets into a rewrite request.

    `jd_skills` is sorted for a deterministic, diffable request file.
    """
    bullets = [
        BulletRef(bullet_id=bullet.bullet_id, entry_id=entry.entry_id, a_text=bullet.text)
        for entry in tailored.entries
        for bullet in entry.bullets
    ]
    return RewriteRequest(request_id=request_id, jd_skills=sorted(jd_skills), bullets=bullets)


@dataclass(frozen=True)
class ScreenDrop:
    """A candidate excluded from the judge request, with why."""

    bullet_id: str
    reason: str


def screen_candidates(
    tailored: Resume,
    candidates: CandidatesFile,
    taxonomy: Taxonomy,
    *,
    request_id: str,
) -> tuple[JudgeRequest, list[ScreenDrop]]:
    """Re-derive `a_text` authoritatively from the freshly Tier-A-tailored résumé (never
    trusting the agent's copy in `candidates`), run the deterministic overmatch filter,
    and emit a JD-free `JudgeRequest` containing only filter-survivors.
    """
    a_text_by_bullet_id = {
        bullet.bullet_id: bullet.text for entry in tailored.entries for bullet in entry.bullets
    }
    items: list[JudgeItem] = []
    drops: list[ScreenDrop] = []
    for candidate in candidates.candidates:
        bullet_id = candidate.bullet_id
        a_text = a_text_by_bullet_id.get(bullet_id)
        if a_text is None:
            drops.append(ScreenDrop(bullet_id=bullet_id, reason="unknown_bullet"))
            continue
        if candidate.candidate == a_text:
            drops.append(ScreenDrop(bullet_id=bullet_id, reason="unchanged"))
            continue
        result = passes_overmatch_filter(a_text, candidate.candidate, taxonomy)
        if not result.passed:
            drops.append(ScreenDrop(bullet_id=bullet_id, reason=f"filter:{result.reason}"))
            continue
        items.append(JudgeItem(bullet_id=bullet_id, a_text=a_text, candidate=candidate.candidate))
    return JudgeRequest(request_id=request_id, items=items), drops
