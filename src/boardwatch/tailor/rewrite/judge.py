from __future__ import annotations

import re
from typing import Literal

Verdict = Literal["ENTAILED", "NOT_ENTAILED", "UNSURE"]

_NON_ALPHA = re.compile(r"[^A-Z]")
_NEGATED = ("NOTENTAILED", "NONENTAILED", "UNENTAILED")


def parse_verdict(reply: str) -> Verdict:
    """Map a judge reply to a verdict, erring toward rejection.

    Separators and surrounding prose are ignored so that a reply which drifts
    from the prompted token format (``not-entailed``, ``NOT  ENTAILED``) is
    still read as a rejection rather than an acceptance.
    """
    squashed = _NON_ALPHA.sub("", reply.upper())
    if any(neg in squashed for neg in _NEGATED):
        return "NOT_ENTAILED"
    if "ENTAILED" in squashed:
        return "ENTAILED"
    return "UNSURE"
