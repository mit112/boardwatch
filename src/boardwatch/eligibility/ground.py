"""Deterministic grounding: the anti-fabrication validator for LLM eligibility output.

An LLM can name any span it wants; nothing upstream can tell a cited quote from an
invented one. This module is the one place that checks a claimed `span_quote` against
the job description text it was supposedly read from, via a literal substring search
(`str.find`), and drops anything that does not match. A model that fabricates a
requirement gets dropped here, not carried forward as if it were read from the posting.

Fail-closed applies at two different scopes on purpose. A malformed top-level shape
(not JSON, not a list, an element that is not a dict, or a `family`/`span_quote` that is
missing or not a string) means the whole response is untrustworthy, so `ground` returns
`[]` for all of it. A single element whose `span_quote` is empty or is not literally
present in the job description is a fabricated citation, so only THAT element is dropped;
the rest of the payload is still evaluated. Weakening either boundary would let a
fabricated span slip through as if it had been grounded.

No module-level string collection lives here (R9 scopes eligibility modules): the coded
family ids sit inside `ground`, not as a module constant.
"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class GroundedSpan:
    family: str
    span: tuple[int, int]
    quote: str


def ground(jd_text: str, raw_output: str) -> list[GroundedSpan]:
    """Validate `raw_output` (JSON from an LLM) against `jd_text`, dropping anything
    that was not literally quoted from the job description.

    Fails closed to `[]` on any top-level parse or shape error. Per-element problems
    (empty/missing `span_quote`, or a quote absent from `jd_text`) drop just that
    element. Pure: no network, no I/O.
    """
    coded_families = {"work_auth", "experience_years", "clearance", "degree"}

    try:
        parsed = json.loads(raw_output)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []

    out: list[GroundedSpan] = []
    for element in parsed:
        if not isinstance(element, dict):
            return []
        family = element.get("family")
        span_quote = element.get("span_quote")
        if not isinstance(family, str) or not isinstance(span_quote, str):
            return []
        if not span_quote:
            continue
        # jd_text.find returns the FIRST occurrence. If span_quote repeats in the job
        # description, the earlier offsets win; later repeats are not separately grounded.
        start = jd_text.find(span_quote)
        if start == -1:
            continue
        end = start + len(span_quote)
        resolved_family = family if family in coded_families else "other"
        out.append(GroundedSpan(family=resolved_family, span=(start, end), quote=span_quote))
    return out
