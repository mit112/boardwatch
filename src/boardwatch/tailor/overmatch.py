"""Deterministic over-match guard (P4 item 1, D-047/D-048): a rewrite that lifts long
verbatim spans from the JD, or copies the JD's unusual capitalization of a non-canonical
term, reads as bot/AI copy-paste and is reverted to its source. Facts are already guarded
by `rewrite/provenance.py`; this guards *style/lift*. Empty list == clean.

Ported near-verbatim from job-apps `resume_tailor/overmatch.py` (48 lines). The one change:
`canonical` is an INJECTED frozenset, not a module-level import of a vocab file -- the
per-field canonical vocab is a separate slice (P4 item 2). Pure: no I/O, no config load.
"""

from __future__ import annotations

import re

OVERMATCH_VERSION = "p4-overmatch-1"

_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+/#-]*")


def _tokens(s: str) -> list[str]:
    return _WORD.findall(s)


def _ngrams(tokens: list[str], n: int) -> set[tuple[str, ...]]:
    low = [t.lower() for t in tokens]
    return {tuple(low[i : i + n]) for i in range(len(low) - n + 1)} if len(low) >= n else set()


def _unusual_caps(tok: str) -> bool:
    """ALLCAPS (len>3) or internal capital (camelCase / StudlyCaps), i.e. not a normal
    Titlecase or lowercase word."""
    if len(tok) < 4:
        return False
    if tok.isupper():
        return True
    return bool(re.search(r"[a-z][A-Z]", tok)) or bool(re.search(r"[A-Z].*[A-Z]", tok))


def overmatch_reasons(
    rewrite: str, jd: str, *, canonical: frozenset[str], min_ngram: int = 7
) -> list[str]:
    reasons: list[str] = []
    rw_tokens, jd_tokens = _tokens(rewrite), _tokens(jd)

    shared = _ngrams(rw_tokens, min_ngram) & _ngrams(jd_tokens, min_ngram)
    if shared:
        span = " ".join(next(iter(shared)))
        reasons.append(f"verbatim {min_ngram}-gram lifted from JD: '{span}'")

    jd_verbatim = set(jd_tokens)  # case-sensitive membership
    for tok in rw_tokens:
        if tok.lower() in canonical:
            continue
        if _unusual_caps(tok) and tok in jd_verbatim:
            reasons.append(f"copies JD's unusual capitalization of non-canonical term: '{tok}'")
    return reasons
