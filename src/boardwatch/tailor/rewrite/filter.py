from __future__ import annotations

import re
from dataclasses import dataclass

from boardwatch.extract.taxonomy import Taxonomy

LENGTH_SLACK: float = 1.5

_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9+.#]*")
_NUM = re.compile(r"\d+")


@dataclass(frozen=True)
class FilterResult:
    passed: bool
    reason: str | None


def _entities(text: str) -> set[str]:
    out: set[str] = set()
    for t in _TOKEN.findall(text):
        if (t.isupper() and len(t) >= 2) or (t != t.lower() and t != t.capitalize()):
            out.add(t.lower())
    return out


def _proper_nouns(text: str) -> set[str]:
    """Title-case tokens AFTER the first token -- brand/company names like Google or Stripe.

    ``_entities()`` deliberately excludes plain Title-case tokens so a sentence-initial
    action verb ("Built", "Led") never trips the invented-entity check -- but that same
    exemption let an invented mid-sentence brand name slip through untouched, and a live
    judge cannot be relied on to catch it either (empirically confirmed). This picks up
    Title-case tokens anywhere except position 0, so the leading verb stays exempt while a
    fabricated "Google"/"Stripe" is caught deterministically.
    """
    out: set[str] = set()
    for i, t in enumerate(_TOKEN.findall(text)):
        if i > 0 and len(t) >= 2 and t[0].isupper() and t[1:].islower():
            out.add(t.lower())
    return out


def passes_overmatch_filter(a_text: str, b_text: str, taxonomy: Taxonomy) -> FilterResult:
    if b_text.strip() == "":
        return FilterResult(False, "empty")
    if "\n" in b_text or "\r" in b_text:
        return FilterResult(False, "not_single_line")
    if len(b_text) > int(len(a_text) * LENGTH_SLACK):
        return FilterResult(False, "too_long")
    if set(_NUM.findall(b_text)) - set(_NUM.findall(a_text)):
        return FilterResult(False, "added_number")
    if _entities(b_text) - _entities(a_text):
        return FilterResult(False, "invented_entity")
    b_skills = taxonomy.extract(b_text)
    if b_skills - taxonomy.extract(a_text):
        return FilterResult(False, "invented_skill")
    # A new mid-sentence Title-case brand/company name (Google, Stripe) is an invented
    # entity too. Run this AFTER the taxonomy check and subtract known skills so a
    # Title-case skill (Kubernetes) keeps the more specific "invented_skill" reason and
    # only genuine non-skill proper nouns land here.
    if _proper_nouns(b_text) - _proper_nouns(a_text) - {s.lower() for s in b_skills}:
        return FilterResult(False, "invented_entity")
    return FilterResult(True, None)
