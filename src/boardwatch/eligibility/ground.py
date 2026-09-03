"""Deterministic grounding: the anti-fabrication validator for LLM eligibility output.

An LLM can name any span it wants; nothing upstream can tell a cited quote from an
invented one. This module is the one place that checks a claimed `span_quote` against
the job description text it was supposedly read from, via a literal substring search
(`str.find`), and drops anything that does not match. A model that fabricates a
requirement gets dropped here, not carried forward as if it were read from the posting.

Fail-closed applies at two different scopes on purpose. A malformed TOP-LEVEL shape
(`raw_output` is not valid JSON, or the parsed value is not a list) means the whole
response is untrustworthy, so `ground` returns `[]` for all of it. Everything below the
top level is an ELEMENT-level problem: an element that is not a dict, a `family` or
`span_quote` that is missing or not a string, an empty `span_quote`, or a quote that is
not literally present in the job description all drop just THAT element, and the rest of
the payload is still evaluated. One model hallucination should not discard every other
span the same call grounded correctly. Weakening the top-level boundary would let an
untrustworthy payload masquerade as an empty (safe-looking) result instead of failing
closed.

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

    Fails closed to `[]` on a top-level parse error or a non-list top-level value.
    Every element-level problem (non-dict element, missing/non-string `family` or
    `span_quote`, empty `span_quote`, or a quote absent from `jd_text`) drops just that
    element; the rest of the payload is still evaluated. Pure: no network, no I/O.
    """
    coded_families = {
        "work_auth", "experience_years", "clearance", "degree", "student_status",
        "contract_not_fte", "internship",
    }

    try:
        parsed = json.loads(raw_output)
    except (json.JSONDecodeError, TypeError, RecursionError):
        return []
    if not isinstance(parsed, list):
        return []

    out: list[GroundedSpan] = []
    for element in parsed:
        if not isinstance(element, dict):
            continue
        family = element.get("family")
        span_quote = element.get("span_quote")
        if not isinstance(family, str) or not isinstance(span_quote, str):
            continue
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
