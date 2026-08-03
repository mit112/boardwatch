from __future__ import annotations

import re
from typing import Literal

Verdict = Literal["ENTAILED", "NOT_ENTAILED", "UNSURE"]

_NON_ALPHA = re.compile(r"[^A-Z]")
_NEGATED = ("NOTENTAILED", "NONENTAILED", "UNENTAILED")
_NEGATION_WORD = re.compile(r"\b(?:NOT|NON|NEVER|NO|CANNOT|FALSE|UNSUPPORTED)\b")
_UNCERTAIN_WORD = re.compile(
    r"\b(?:UNSURE|UNCERTAIN|UNCLEAR|MAYBE|POSSIBLY|PROBABLY|LIKELY|PERHAPS|AMBIGUOUS)\b"
)


def parse_verdict(reply: str) -> Verdict:
    """Map a judge reply to a verdict, erring toward rejection.

    Fail-closed on four levels: separators and surrounding prose are ignored so a
    drifted rejection (``not-entailed``, ``NOT  ENTAILED``) still reads as one; a
    hedge word anywhere in the reply (``UNSURE``, ``maybe ENTAILED``, ``ENTAILED
    (probably)``) is read as non-accepting even though ``UNSURE`` is itself one of the
    judge's three legal replies, since a hedged ``ENTAILED`` is not a clean accept; a
    negation word anywhere alongside ``ENTAILED`` is read as a rejection even when
    words intervene (``NOT really entailed``); and anything unrecognized is ``UNSURE``.
    Only a clean, unhedged, unnegated ``ENTAILED`` accepts the rewrite.

    Uncertainty is checked before the negation-word check: both are non-accepting, so
    when a reply hedges *and* carries a negation word (``"Probably NOT_ENTAILED"``),
    which one "wins" makes no safety difference — UNSURE is returned rather than
    NOT_ENTAILED because the reply is genuinely ambiguous about which verdict the judge
    meant, and UNSURE is the more honest label for that case.
    """
    upper = reply.upper()
    squashed = _NON_ALPHA.sub("", upper)
    if any(neg in squashed for neg in _NEGATED):
        return "NOT_ENTAILED"
    if "ENTAILED" not in squashed:
        return "UNSURE"
    if _UNCERTAIN_WORD.search(upper):
        return "UNSURE"
    if _NEGATION_WORD.search(upper):
        return "NOT_ENTAILED"
    return "ENTAILED"
