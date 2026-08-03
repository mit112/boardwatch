from __future__ import annotations

from typing import Literal

Verdict = Literal["ENTAILED", "NOT_ENTAILED", "UNSURE"]


def parse_verdict(reply: str) -> Verdict:
    upper = reply.upper()
    if "NOT_ENTAILED" in upper or "NOT ENTAILED" in upper:
        return "NOT_ENTAILED"
    if "ENTAILED" in upper:
        return "ENTAILED"
    return "UNSURE"
