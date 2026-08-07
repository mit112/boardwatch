"""Deterministic token-provenance check for Tier-B rewords (P1b, D-033).

A reword is kept only if every CONTENT token is justified: it appears in the source, is an
approved equivalence image, or is a claim-free structural connective. No stemmer and no
modals/auxiliaries — both were shown (deepseek design review) to let fabrications through
(verb→agent-noun via stem; future commitment via `will`). Fail-closed: an unjustified token
vetoes the reword, keeping the Tier-A bullet. Pure: no LLM, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from boardwatch.tailor.equivalences import EquivalenceTable
from boardwatch.tailor.tokens import toks  # verified: toks lives in boardwatch.tailor.tokens

PROVENANCE_VERSION = "p1b-provenance-1"

# Claim-free STRUCTURAL words only — articles, prepositions, coordinators. Deliberately NO verbs,
# auxiliaries, or modals: those change truth conditions (tense/future/obligation) and are claims.
CONNECTIVES: frozenset[str] = frozenset(
    {
        "the", "a", "an", "of", "to", "for", "and", "or", "with", "in",
        "on", "at", "from", "by", "as", "that"
    }
)


@dataclass(frozen=True)
class ProvenanceResult:
    ok: bool
    offending: tuple[str, ...]


def _is_word(tok: str) -> bool:
    return any(ch.isalnum() for ch in tok)


def reword_is_provenanced(
    a_text: str, b_text: str, *, table: EquivalenceTable, connectives: frozenset[str] = CONNECTIVES
) -> ProvenanceResult:
    source = {t.lower() for t in toks(a_text) if _is_word(t)}
    # Approved equivalence images of source tokens (swap maps source-token.lower() -> image).
    # as_pairs() yields EquivalencePair(from_phrase, to_phrase) — same construction safety.py uses.
    swap = {p.from_phrase.lower(): p.to_phrase for p in table.as_pairs()}
    images = {swap[s] for s in source if s in swap}
    images |= {img.lower() for img in images}
    offending: list[str] = []
    for tok in toks(b_text):
        if not _is_word(tok):
            continue  # punctuation / structural char
        low = tok.lower()
        if low in source or low in connectives or tok in images or low in images:
            continue
        offending.append(tok)
    return ProvenanceResult(ok=not offending, offending=tuple(offending))
