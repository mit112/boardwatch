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
    if taxonomy.extract(b_text) - taxonomy.extract(a_text):
        return FilterResult(False, "invented_skill")
    return FilterResult(True, None)
