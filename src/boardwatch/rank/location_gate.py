"""US-only location classifier for the hard location gate (Mit's visa requirement, D-251).

`classify_location` labels a posting's location strings `us` / `non_us` / `unknown`. It is a
POSITIVE US allowlist, not a non-US denylist: a hard gate must confirm the US, because a
denylist lets anything it has not heard of leak through (job-apps' `_radancy_location_is_us`
lesson). The gate keeps `us` and — fail-open, Mit's ruling — `unknown`, and drops `non_us`.

The per-segment resolution ORDER is load-bearing:

  ambiguous-region → US-marker → non-US-country → non-US-city → non-US-region →
  US-state-name → US-ZIP → US-state-abbrev → bare-"US" → US-city → unknown

Non-US city/country are checked BEFORE the US state-abbrev heuristic so "Bangalore, IN" reads
as India (city wins) rather than Indiana (", IN" suffix). Ambiguous whole-segment names that
INCLUDE the US ("Americas", "Worldwide") short-circuit to `unknown` rather than guessing.
Matching is word-bounded, so region token "uk" does not fire inside "Milwaukee".
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Literal

from boardwatch.rank.location_data import (
    AMBIGUOUS_REGIONS,
    NON_US_CITIES,
    NON_US_COUNTRIES,
    NON_US_REGIONS,
    POLICY_ONLY,
    US_CITIES,
    US_MARKERS,
    US_STATE_ABBREVS,
    US_STATE_NAMES,
)

LocationClass = Literal["us", "non_us", "unknown"]

_SEGMENT_SPLIT = re.compile(r"[;|/•]| or ", re.IGNORECASE)


def _alternation(tokens: Sequence[str] | frozenset[str]) -> re.Pattern[str]:
    """Word-bounded alternation over casefolded tokens, longest match first.

    `(?<![a-z])`/`(?![a-z])` rather than `\\b` because tokens carry dots ("u.s.") where `\\b`
    asserts the wrong side. Longest-first so "united states of america" wins over "u.s.".
    """
    body = "|".join(re.escape(t) for t in sorted(tokens, key=len, reverse=True))
    return re.compile(rf"(?<![a-z]){body}(?![a-z])")


_US_MARKER_RE = _alternation(US_MARKERS)
_NON_US_COUNTRY_RE = _alternation(NON_US_COUNTRIES)
_NON_US_CITY_RE = _alternation(NON_US_CITIES)
_NON_US_REGION_RE = _alternation(NON_US_REGIONS)
_US_STATE_NAME_RE = _alternation(US_STATE_NAMES)
_US_CITY_RE = _alternation(US_CITIES)
_US_BARE_RE = re.compile(r"(?<![a-z])(?:us|u\.s\.?)(?![a-z])")
_US_ZIP_RE = re.compile(r"(?<!\d)\d{5}(?:-\d{4})?(?!\d)")
# A US state abbrev as a "City, ST" suffix. Requires the comma AND an UPPERCASE code in the
# ORIGINAL text (the "City, ST" convention), so a lowercase "in"/"or" inside prose never fires.
_STATE_ABBREV_RE = re.compile(r",\s*([A-Z]{2})(?![A-Za-z])")


def _classify_segment(segment: str) -> LocationClass:
    low = segment.strip().casefold()
    if not low or low in POLICY_ONLY:
        return "unknown"
    if low in AMBIGUOUS_REGIONS:  # "Americas" / "Worldwide" — includes the US, undecidable
        return "unknown"
    if _US_MARKER_RE.search(low):
        return "us"
    if _NON_US_COUNTRY_RE.search(low) or _NON_US_CITY_RE.search(low):
        return "non_us"
    if _NON_US_REGION_RE.search(low):
        return "non_us"
    if _US_STATE_NAME_RE.search(low) or _US_ZIP_RE.search(segment):
        return "us"
    for match in _STATE_ABBREV_RE.finditer(segment):
        if match.group(1).casefold() in US_STATE_ABBREVS:
            return "us"
    if _US_BARE_RE.search(low) or _US_CITY_RE.search(low):
        return "us"
    return "unknown"


def classify_location(locations: Sequence[str]) -> LocationClass:
    """Label a posting's locations `us` / `non_us` / `unknown`.

    A posting offered in several places keeps its US eligibility if ANY location is US — the
    applicant can take that one — so `us` wins over everything. Absent a US location, a single
    non-US signal makes it `non_us`; a posting with no geographic signal at all (bare "Remote",
    an office nickname, empty) is `unknown`. Policy-only segments ("Hybrid", "Remote") are
    skipped so a real place beside them still decides.
    """
    verdicts: list[LocationClass] = []
    for location in locations:
        for segment in _SEGMENT_SPLIT.split(location):
            if segment.strip().casefold() in POLICY_ONLY:
                continue
            verdicts.append(_classify_segment(segment))
    if "us" in verdicts:
        return "us"
    if "non_us" in verdicts:
        return "non_us"
    return "unknown"
