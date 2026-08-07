"""Pure logic for the subscription Tier B agent lane's step 1 (P7b task 4): turn a
Tier-A-planned résumé + its JD skills into the JSON `RewriteRequest` a rewriter agent
consumes. No I/O here — the CLI (`boardwatch tailor rewrite request`) drives
`reports.tailor.plan_tier_a` for the résumé/jd_skills and writes the result via
`agent_io.dump_json`.
"""

from __future__ import annotations

from dataclasses import dataclass

from boardwatch.extract.taxonomy import Taxonomy
from boardwatch.tailor.equivalences import load_equivalences
from boardwatch.tailor.model import Resume
from boardwatch.tailor.rewrite.agent_io import (
    BulletRef,
    CandidatesFile,
    JudgeItem,
    JudgeRequest,
    RewriteRequest,
    VerdictsFile,
)
from boardwatch.tailor.rewrite.filter import passes_overmatch_filter
from boardwatch.tailor.rewrite.lane import TierBResult, run_tier_b_core
from boardwatch.tailor.rewrite.provenance import reword_is_provenanced


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
    table = load_equivalences()
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
        # Same veto as run_tier_b_core, applied here too: this step's whole purpose is to
        # screen out candidates before spending an external judge agent call, and an
        # un-provenanced reword is exactly the kind of call not worth spending (P1b, D-033).
        pr = reword_is_provenanced(a_text, candidate.candidate, table=table)
        if not pr.ok:
            drops.append(ScreenDrop(bullet_id=bullet_id, reason="provenance"))
            continue
        items.append(JudgeItem(bullet_id=bullet_id, a_text=a_text, candidate=candidate.candidate))
    return JudgeRequest(request_id=request_id, items=items), drops


def apply_agent_rewrites(
    tailored: Resume,
    candidates: CandidatesFile,
    verdicts: VerdictsFile,
    taxonomy: Taxonomy,
    jd_skills: set[str],
) -> TierBResult:
    """Step 3 of the subscription Tier B agent lane: replay the agent's candidates +
    the judge's verdicts through `run_tier_b_core` — the SAME filter/verdict/row path
    the live-client API lane uses — without ever calling a live LLM.

    `run_tier_b_core`'s `propose`/`judge` closures only ever see `(a_text, ...)`, never
    `bullet_id` (that is the API lane's shape, driven by a real provider call keyed on
    the bullet text it was given). To bridge the JSON files — which are keyed by
    `bullet_id` — into that shape, re-derive a_text-keyed maps from the AUTHORITATIVE
    freshly Tier-A-tailored résumé (never trusting a_text implied by the candidates/
    verdicts files themselves).
    """
    cand_by_id = {c.bullet_id: c.candidate for c in candidates.candidates}
    verdict_by_id = {v.bullet_id: v.raw_reply for v in verdicts.verdicts}

    # Keyed by a_text rather than bullet_id because propose/judge below only receive
    # a_text. This assumes bullet a_texts are unique within a résumé (true for authored
    # résumés — bullet_ids map to distinct authored lines); on the pathological
    # duplicate-text case, last-write-wins.
    candidate_by_atext: dict[str, str | None] = {}
    verdict_by_atext: dict[str, str | None] = {}
    for entry in tailored.entries:
        for b in entry.bullets:
            bid, at = b.bullet_id, b.text
            candidate_by_atext[at] = cand_by_id.get(bid)
            verdict_by_atext[at] = verdict_by_id.get(bid)

    def propose(a_text: str, _jd_skills: set[str]) -> str | None:
        # None (no candidate supplied for this bullet) -> run_tier_b_core drops it
        # "no_candidate", spending no judge call on it.
        return candidate_by_atext.get(a_text)

    def judge(a_text: str, _candidate: str) -> str:
        # A missing or empty verdict must fail closed, not pass through: return a
        # non-canonical sentinel so `parse_verdict` (the exact-token allowlist) rejects
        # it and `run_tier_b_core` drops the rewrite with reason "judge", exactly as it
        # would a live judge's off-contract reply.
        return verdict_by_atext.get(a_text) or "MISSING"

    # run_tier_b_core counts BOTH a propose call and a judge call against `budget` (2 per
    # bullet reaching the judge). Unlike the API lane, "calls" here are free dict lookups
    # — there is no live provider to rate-limit — so the budget must never truncate a
    # legitimate replay. Set it to 2x the total bullet count so every bullet can be both
    # proposed and judged; see design §5 for why this budget is advisory-only in the
    # agent lane (subscription calls aren't API-metered).
    budget = 2 * sum(len(e.bullets) for e in tailored.entries)

    return run_tier_b_core(
        tailored,
        propose=propose,
        judge=judge,
        taxonomy=taxonomy,
        table=load_equivalences(),
        jd_skills=jd_skills,
        budget=budget,
    )
