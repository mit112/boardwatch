from __future__ import annotations

import re
from typing import Literal

Verdict = Literal["ENTAILED", "NOT_ENTAILED", "UNSURE"]

_NON_ALPHA = re.compile(r"[^A-Z]")
_NEGATED = ("NOTENTAILED", "NONENTAILED", "UNENTAILED")
_NEGATION_WORD = re.compile(r"\b(?:NOT|NON|NEVER|NO|CANNOT|FALSE|UNSUPPORTED)\b")


def parse_verdict(reply: str) -> Verdict:
    """Map a judge reply to a verdict, erring toward rejection.

    Fail-closed on three levels: separators and surrounding prose are ignored so a
    drifted rejection (``not-entailed``, ``NOT  ENTAILED``) still reads as one; a
    negation word anywhere alongside ``ENTAILED`` is read as a rejection even when
    words intervene (``NOT really entailed``); and anything unrecognized is ``UNSURE``.
    Only a clean, unnegated ``ENTAILED`` accepts the rewrite.
    """
    upper = reply.upper()
    squashed = _NON_ALPHA.sub("", upper)
    if any(neg in squashed for neg in _NEGATED):
        return "NOT_ENTAILED"
    if "ENTAILED" not in squashed:
        return "UNSURE"
    if _NEGATION_WORD.search(upper):
        return "NOT_ENTAILED"
    return "ENTAILED"
