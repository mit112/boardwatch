from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from boardwatch.extract.taxonomy import Taxonomy
from boardwatch.llm.cache import ResponseCache
from boardwatch.llm.client import ModelClient
from boardwatch.tailor.canonical import build_canonical_vocab
from boardwatch.tailor.equivalences import EquivalenceTable
from boardwatch.tailor.model import Resume
from boardwatch.tailor.overmatch import overmatch_reasons
from boardwatch.tailor.plan import Rewrite
from boardwatch.tailor.rewrite.filter import passes_overmatch_filter
from boardwatch.tailor.rewrite.judge import parse_verdict
from boardwatch.tailor.rewrite.prompt import (
    JUDGE_PROMPT_VERSION,
    REWRITE_PROMPT_VERSION,
    build_judge_payload,
    build_rewrite_payload,
)
from boardwatch.tailor.rewrite.provenance import reword_is_provenanced

# (a_text, jd_skills) -> candidate rewrite text (already stripped), or None.
Proposer = Callable[[str, set[str]], str | None]
# (a_text, candidate) -> raw judge reply.
Judge = Callable[[str, str], str]


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


_T = TypeVar("_T")


def run_tier_b_core(
    tailored_a: Resume,
    *,
    propose: Proposer,
    judge: Judge,
    taxonomy: Taxonomy,
    table: EquivalenceTable,
    jd_skills: set[str],
    budget: int,
    jd_text: str = "",
    canonical: frozenset[str] = frozenset(),
) -> TierBResult:
    accepted: list[Rewrite] = []
    rows: list[RewriteRow] = []
    state: dict[str, int] = {"calls": 0}

    def _guarded(fn: Callable[..., _T], *args: object) -> _T:
        if state["calls"] >= budget:
            raise _BudgetExceeded
        state["calls"] += 1
        return fn(*args)

    for entry in tailored_a.entries:
        for b in entry.bullets:
            a_text = b.text

            try:
                candidate = _guarded(propose, a_text, jd_skills)
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

            if candidate is None:
                # The proposer declined to produce a candidate for this bullet (e.g. a
                # future subscription lane opting out). Not reachable from the current
                # API lane's propose closure, which always returns a stripped string.
                rows.append(
                    RewriteRow(
                        bullet_id=b.bullet_id,
                        entry_id=entry.entry_id,
                        a_text=a_text,
                        b_text=a_text,
                        filter_pass=False,
                        judge_verdict=None,
                        kept=False,
                        drop_reason="no_candidate",
                    )
                )
                continue

            if candidate == a_text:
                # The provider echoed the bullet back unchanged. It would trivially pass
                # the filter and could still be sent to the judge, but that spends a call
                # to adjudicate a rewrite that changed nothing — and if kept, it would
                # render a `// reworded (Tier B)` marker on a bullet byte-identical to
                # Tier A's, telling the reader to review a non-change. Drop it here,
                # before the judge call, so no budget is spent on it.
                rows.append(
                    RewriteRow(
                        bullet_id=b.bullet_id,
                        entry_id=entry.entry_id,
                        a_text=a_text,
                        b_text=candidate,
                        filter_pass=True,
                        judge_verdict=None,
                        kept=False,
                        drop_reason="unchanged",
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
                        # Carry the filter's specific reason (e.g. "invented_skill",
                        # "too_long") rather than the flat "filter", so the audit trail and
                        # CLI can distinguish a prompt problem from a safety catch. The
                        # "filter:" prefix is kept so existing consumers keying on that
                        # prefix (CLI, tests) still recognize a filter drop.
                        drop_reason=f"filter:{fr.reason}",
                    )
                )
                continue

            pr = reword_is_provenanced(a_text, candidate, table=table)
            if not pr.ok:
                # Every content token in the reword must trace to the source, an
                # approved equivalence image, or a claim-free connective (P1b, D-033).
                # A fabrication here is caught deterministically and cheaply -- veto
                # before spending a judge call on a reword that can never be trusted,
                # and keep the Tier-A bullet (only `accepted` rewrites are ever applied).
                rows.append(
                    RewriteRow(
                        bullet_id=b.bullet_id,
                        entry_id=entry.entry_id,
                        a_text=a_text,
                        b_text=candidate,
                        filter_pass=True,
                        judge_verdict=None,
                        kept=False,
                        drop_reason="provenance",
                    )
                )
                continue

            reasons = overmatch_reasons(candidate, jd_text, canonical=canonical)
            if reasons:
                # A bullet that lifts a long verbatim JD span, or copies the JD's own
                # unusual capitalization of a non-canonical term, reads as bot copy-paste
                # even when every token is fact-provenanced (P4 item 1, D-048). Same
                # fail-safe shape as the provenance veto above: revert to Tier-A before
                # spending a judge call on a reword that can never be trusted stylistically.
                rows.append(
                    RewriteRow(
                        bullet_id=b.bullet_id,
                        entry_id=entry.entry_id,
                        a_text=a_text,
                        b_text=candidate,
                        filter_pass=True,
                        judge_verdict=None,
                        kept=False,
                        drop_reason="overmatch",
                    )
                )
                continue

            try:
                verdict = parse_verdict(_guarded(judge, a_text, candidate))
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


def run_tier_b(
    tailored_a: Resume,
    client: ModelClient,
    cache: ResponseCache,
    *,
    jd_skills: set[str],
    taxonomy: Taxonomy,
    table: EquivalenceTable,
    model: str,
    budget: int,
    provider: str | None = None,
    base_url: str | None = None,
    jd_text: str = "",
) -> TierBResult:
    # ResponseCache.key() only takes a model STRING, but the same model name can point
    # at a different provider or endpoint (self-hosted vs. hosted, a base_url swap).
    # Fold provider + base_url into the identity so switching either is a cache MISS,
    # not a silent replay of a different provider's proposals/verdicts under a
    # provenance that no longer matches (reports/tailor.py records the NEW provider).
    model_identity = f"{provider or '-'}|{base_url or '-'}|{model}"

    def call(payload: dict[str, str], version: str) -> str:
        key = cache.key(
            hashlib.sha256(payload["user"].encode()).hexdigest(), version, model_identity
        )
        cached = cache.get(key)
        if cached is not None:
            return cached
        raw = client.complete(payload["user"], system=payload["system"])
        cache.put(key, raw)
        return raw

    propose: Proposer = lambda a, sk: call(  # noqa: E731
        build_rewrite_payload(a, sk), REWRITE_PROMPT_VERSION
    ).strip()
    judge: Judge = lambda a, c: call(  # noqa: E731
        build_judge_payload(a, c), JUDGE_PROMPT_VERSION
    )

    # The canonical-tech vocab overmatch's caps check exempts (P4 item 1, D-048), sourced
    # from the shared accessor (P4 item 2): overmatch_reasons itself stays agnostic to
    # where it came from.
    canonical = build_canonical_vocab(taxonomy, table).terms

    return run_tier_b_core(
        tailored_a,
        propose=propose,
        judge=judge,
        taxonomy=taxonomy,
        table=table,
        jd_skills=jd_skills,
        budget=budget,
        jd_text=jd_text,
        canonical=canonical,
    )
