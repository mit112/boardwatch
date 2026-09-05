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
    tokens = toks(b_text)
    lowered = [tok.lower() for tok in tokens]
    # A multi-word image can never match token by token: `ML -> machine learning` puts the whole
    # phrase in `images` and the loop below then asks whether the token "machine" is in it. Both
    # words came back offending and the reword was vetoed — the equivalence table's own approved
    # substitution rejected by the check that exists to authorise it.
    #
    # Matched as a CONTIGUOUS token run, never as a set of extra allowed words: half an approved
    # image is not an approved image, and authorising "machine" on its own would let a reword
    # introduce "machine operator" from an `ML` source. Punctuation between the words breaks the
    # run, which is right — "machine, learning" is not the phrase the table approved.
    phrased: set[int] = set()
    for phrase in {tuple(img.lower().split()) for img in images if len(img.split()) > 1}:
        span = len(phrase)
        for start in range(len(lowered) - span + 1):
            if tuple(lowered[start : start + span]) == phrase:
                phrased.update(range(start, start + span))
    offending: list[str] = []
    for index, tok in enumerate(tokens):
        if not _is_word(tok):
            continue  # punctuation / structural char
        low = tok.lower()
        if low in source or low in connectives or tok in images or low in images:
            continue
        if index in phrased:
            continue
        offending.append(tok)
    return ProvenanceResult(ok=not offending, offending=tuple(offending))
