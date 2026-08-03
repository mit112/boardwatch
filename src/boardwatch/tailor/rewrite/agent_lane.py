"""Pure logic for the subscription Tier B agent lane's step 1 (P7b task 4): turn a
Tier-A-planned résumé + its JD skills into the JSON `RewriteRequest` a rewriter agent
consumes. No I/O here — the CLI (`boardwatch tailor rewrite request`) drives
`reports.tailor.plan_tier_a` for the résumé/jd_skills and writes the result via
`agent_io.dump_json`.
"""

from __future__ import annotations

from boardwatch.tailor.model import Resume
from boardwatch.tailor.rewrite.agent_io import BulletRef, RewriteRequest


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
