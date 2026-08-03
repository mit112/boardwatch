from __future__ import annotations

import hashlib
from dataclasses import dataclass

from boardwatch.extract.taxonomy import Taxonomy
from boardwatch.llm.cache import ResponseCache
from boardwatch.llm.client import ModelClient
from boardwatch.tailor.model import Resume
from boardwatch.tailor.plan import Rewrite
from boardwatch.tailor.rewrite.filter import passes_overmatch_filter
from boardwatch.tailor.rewrite.judge import parse_verdict
from boardwatch.tailor.rewrite.prompt import (
    JUDGE_PROMPT_VERSION,
    REWRITE_PROMPT_VERSION,
    build_judge_payload,
    build_rewrite_payload,
)


@dataclass(frozen=True)
class RewriteRow:
    bullet_id: str
    entry_id: str
    a_text: str
    b_text: str
    filter_pass: bool
    judge_verdict: str | None
    kept: bool
    drop_reason: str | None


@dataclass(frozen=True)
class TierBResult:
    accepted: list[Rewrite]
    rows: list[RewriteRow]
    calls_made: int


class _BudgetExceeded(Exception):
    pass


def run_tier_b(
    tailored_a: Resume,
    client: ModelClient,
    cache: ResponseCache,
    *,
    jd_skills: set[str],
    taxonomy: Taxonomy,
    model: str,
    budget: int,
    provider: str | None = None,
    base_url: str | None = None,
) -> TierBResult:
    accepted: list[Rewrite] = []
    rows: list[RewriteRow] = []
    state: dict[str, int] = {"calls": 0}
    # ResponseCache.key() only takes a model STRING, but the same model name can point
    # at a different provider or endpoint (self-hosted vs. hosted, a base_url swap).
    # Fold provider + base_url into the identity so switching either is a cache MISS,
    # not a silent replay of a different provider's proposals/verdicts under a
    # provenance that no longer matches (reports/tailor.py records the NEW provider).
    model_identity = f"{provider or '-'}|{base_url or '-'}|{model}"

    def call(payload: dict[str, str], version: str) -> str:
        if state["calls"] >= budget:
            raise _BudgetExceeded
        key = cache.key(
            hashlib.sha256(payload["user"].encode()).hexdigest(), version, model_identity
        )
        state["calls"] += 1
        cached = cache.get(key)
        if cached is not None:
            return cached
        raw = client.complete(payload["user"], system=payload["system"])
        cache.put(key, raw)
        return raw

    for entry in tailored_a.entries:
        for b in entry.bullets:
            a_text = b.text

            rewrite_payload = build_rewrite_payload(a_text, jd_skills)
            try:
                candidate = call(rewrite_payload, REWRITE_PROMPT_VERSION).strip()
            except _BudgetExceeded:
                rows.append(
                    RewriteRow(
                        bullet_id=b.bullet_id,
                        entry_id=entry.entry_id,
                        a_text=a_text,
                        b_text=a_text,
                        filter_pass=False,
                        judge_verdict=None,
                        kept=False,
                        drop_reason="budget",
                    )
                )
                continue
            except Exception:  # containment boundary — provider failure drops rewrite, not the run
                rows.append(
                    RewriteRow(
                        bullet_id=b.bullet_id,
                        entry_id=entry.entry_id,
                        a_text=a_text,
                        b_text=a_text,
                        filter_pass=False,
                        judge_verdict=None,
                        kept=False,
                        drop_reason="error",
                    )
                )
                continue

            fr = passes_overmatch_filter(a_text, candidate, taxonomy)
            if not fr.passed:
                rows.append(
                    RewriteRow(
                        bullet_id=b.bullet_id,
                        entry_id=entry.entry_id,
                        a_text=a_text,
                        b_text=candidate,
                        filter_pass=False,
                        judge_verdict=None,
                        kept=False,
                        drop_reason="filter",
                    )
                )
                continue

            judge_payload = build_judge_payload(a_text, candidate)
            try:
                verdict = parse_verdict(call(judge_payload, JUDGE_PROMPT_VERSION))
            except _BudgetExceeded:
                rows.append(
                    RewriteRow(
                        bullet_id=b.bullet_id,
                        entry_id=entry.entry_id,
                        a_text=a_text,
                        b_text=candidate,
                        filter_pass=True,
                        judge_verdict=None,
                        kept=False,
                        drop_reason="budget",
                    )
                )
                continue
            except Exception:  # containment boundary — provider failure drops rewrite, not the run
                rows.append(
                    RewriteRow(
                        bullet_id=b.bullet_id,
                        entry_id=entry.entry_id,
                        a_text=a_text,
                        b_text=candidate,
                        filter_pass=True,
                        judge_verdict=None,
                        kept=False,
                        drop_reason="error",
                    )
                )
                continue

            if verdict == "ENTAILED":
                accepted.append(Rewrite(bullet_id=b.bullet_id, text=candidate))
                rows.append(
                    RewriteRow(
                        bullet_id=b.bullet_id,
                        entry_id=entry.entry_id,
                        a_text=a_text,
                        b_text=candidate,
                        filter_pass=True,
                        judge_verdict=verdict,
                        kept=True,
                        drop_reason=None,
                    )
                )
            else:
                rows.append(
                    RewriteRow(
                        bullet_id=b.bullet_id,
                        entry_id=entry.entry_id,
                        a_text=a_text,
                        b_text=candidate,
                        filter_pass=True,
                        judge_verdict=verdict,
                        kept=False,
                        drop_reason="judge",
                    )
                )

    return TierBResult(accepted=accepted, rows=rows, calls_made=state["calls"])
