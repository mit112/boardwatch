"""US-only location classifier for the hard location gate (Mit's visa requirement, D-251).

`classify_location` labels a posting's location strings `us` / `non_us` / `unknown`. It is a
POSITIVE US allowlist, not a non-US denylist: a hard gate must confirm the US, because a
denylist lets anything it has not heard of leak through (job-apps' `_radancy_location_is_us`
lesson). The gate keeps `us` and — fail-open, Mit's ruling — `unknown`, and drops `non_us`.

The per-segment resolution ORDER is load-bearing:

  ambiguous-region → US-marker → US-state-abbrev → US-state-name → bare-"US" →
  non-US-country → non-US-city → non-US-region → US-ZIP → US-city → unknown

Bare "US"/"U.S." is checked BEFORE the non-US tokens so an explicit US signal wins within a
segment that also names a foreign place ("US, Canada") — the posting is offered in the US.
US-city stays AFTER them so a foreign city sharing a US name ("Manchester, UK") reads non-US.

US STATE signals (abbrev / full name) are checked BEFORE any non-US token, so a US town that
shares a foreign name — "Vienna, VA", "Athens, GA", "Lebanon, NH", "Mexico, MO" — is KEPT, not
silently dropped (a false US drop is the worst error a visa gate can make). The residual
collision is a foreign city carrying a token that is also a US state code ("Bangalore, IN"):
it resolves `us` (kept) — a fail-open leak, never a drop; the spelled-out "Bangalore, India"
still reads non-US via the country name. Ambiguous whole-segment names that INCLUDE the US
("Americas", "Worldwide") short-circuit to `unknown` rather than guessing. Matching is
word-bounded, so region token "uk" does not fire inside "Milwaukee".
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

    The `(?:...)` around the body is LOAD-BEARING and its absence was a live defect. `|` binds
    looser than concatenation, so an ungrouped body compiles as
    `((?<![a-z])first) | (second) | ... | (last(?![a-z]))`: the lookbehind guards only the
    first token, the lookahead only the last, and every token between them matches as a bare
    substring. The observed damage was that region token "uk" fired inside "Waukesha" and
    "West Milwaukee", so 41 real GE HealthCare Wisconsin postings — "Software Engineer" among
    them — were dropped by a US-only gate as non-US. It was intermittent, not constant: which
    token lands last depends on `frozenset` iteration order, which varies with per-process hash
    randomisation, so the same store and the same code classified a city differently run to
    run. `test_no_token_matches_inside_a_longer_word` pins the invariant seed-independently.
    """
    body = "|".join(re.escape(t) for t in sorted(tokens, key=len, reverse=True))
    return re.compile(rf"(?<![a-z])(?:{body})(?![a-z])")


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
    # US STATE signals (abbrev / full name) are checked BEFORE any non-US token, so a US town
    # that shares a foreign name — "Vienna, VA", "Athens, GA", "Lebanon, NH", "Mexico, MO" — is
    # kept, not silently dropped. This ordering is the whole defense against false US drops in
    # hard mode (the worst error for the visa gate); the reviewer found the reverse order
    # deleting real US postings. The remaining collision is a foreign city carrying a token
    # that is ALSO a US state code ("Bangalore, IN"): it resolves US (kept) — a fail-open leak,
    # never a drop, which is the safe direction. A bare "Bangalore, India" still reads non-US
    # via the country name below.
    for match in _STATE_ABBREV_RE.finditer(segment):
        if match.group(1).casefold() in US_STATE_ABBREVS:
            return "us"
    if _US_STATE_NAME_RE.search(low):
        return "us"
    # A bare "US"/"U.S." is an EXPLICIT US signal and must win within a segment that also names
    # a foreign place ("US, Canada", "Remote - US, Canada", "US, EMEA") — the posting is offered
    # in the US, so it is US-eligible. `_SEGMENT_SPLIT` never separates a comma / "and" / "&", so
    # such a pair arrives as one segment and the explicit US token would otherwise lose to the
    # foreign country below. A US CITY name, by contrast, stays AFTER the non-US tokens: a
    # foreign city sharing a US city's name ("Manchester, UK") must still read non-US, so only
    # the explicit bare token is promoted here, not the city allowlist.
    if _US_BARE_RE.search(low):
        return "us"
    if _NON_US_COUNTRY_RE.search(low) or _NON_US_CITY_RE.search(low):
        return "non_us"
    if _NON_US_REGION_RE.search(low):
        return "non_us"
    # US ZIP is checked AFTER non-US country/region so a foreign postal beside its country
    # ("Berlin, Germany 10115") reads non-US; a bare US ZIP with no other signal still reads US.
    if _US_ZIP_RE.search(segment):
        return "us"
    if _US_CITY_RE.search(low):
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
