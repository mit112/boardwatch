"""US-only location classifier for the hard location gate (Mit's visa requirement, D-251).

`classify_location` labels a posting's location strings `us` / `non_us` / `unknown`. It is a
POSITIVE US allowlist, not a non-US denylist: a hard gate must confirm the US, because a
denylist lets anything it has not heard of leak through (job-apps' `_radancy_location_is_us`
lesson). The gate keeps `us` and — fail-open, Mit's ruling — `unknown`, and drops `non_us`.

The per-segment resolution ORDER is load-bearing:

  ambiguous-region → US-marker → US-state-abbrev → US-state-name → bare-"US" →
  non-US-country → non-US-city → non-US-ISO3-code → non-US-region → US-ZIP → US-city → unknown

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
word-bounded, so region token "uk" does not fire inside "Milwaukee", and every lexical test
runs on a Unicode-normalized form so "Montréal" resolves exactly as "Montreal" does.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from typing import Literal

from boardwatch.rank.location_data import (
    AMBIGUOUS_REGIONS,
    BUNDLED_PACKS,
    CITIES_BY_ISO3,
    COUNTRY_NAMES_BY_ISO3,
    NON_US_CITIES,
    NON_US_COUNTRIES,
    NON_US_ISO3,
    NON_US_ISO3_SUFFIX,
    NON_US_REGIONS,
    POLICY_ONLY,
    REGIONS_TO_ISO3,
    CountryPack,
)

LocationClass = Literal["us", "non_us", "unknown"]

_SEGMENT_SPLIT = re.compile(r"[;|/•]| or ", re.IGNORECASE)


def _fold(text: str) -> str:
    """The single lexical form every catalog test is written against.

    NFKD plus combining-mark stripping, then casefold: an accented spelling of a catalogued
    city has to reach the same token as its plain spelling. "Montréal" was only casefolded, so
    it matched no catalog at all and resolved `unknown` — kept, fail-open, while "Montreal"
    read `non_us`. Applied to the CATALOG TOKENS as well as the input, because a token whose
    only spelling is accented ("łódź" — `ł` carries no combining mark, so it normalizes to
    "łodz", which no catalog spells) would otherwise stop matching its own city.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).strip().casefold()


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
    body = "|".join(
        re.escape(t) for t in sorted({_fold(t) for t in tokens}, key=len, reverse=True)
    )
    return re.compile(rf"(?<![a-z])(?:{body})(?![a-z])")


def _token_map(by_country: dict[str, frozenset[str]]) -> dict[str, frozenset[str]]:
    """Folded token -> the countries it names, inverted from a per-country catalog."""
    inverted: dict[str, set[str]] = {}
    for iso3, tokens in by_country.items():
        for token in tokens:
            inverted.setdefault(_fold(token), set()).add(iso3)
    return {token: frozenset(codes) for token, codes in inverted.items()}


_COUNTRY_NAME_RE = _alternation(NON_US_COUNTRIES)
_CITY_RE = _alternation(NON_US_CITIES)
_REGION_RE = _alternation(NON_US_REGIONS)
_COUNTRY_NAME_TO_ISO3 = _token_map(COUNTRY_NAMES_BY_ISO3)
_CITY_TO_ISO3 = _token_map(CITIES_BY_ISO3)
_REGION_TO_ISO3 = {_fold(token): codes for token, codes in REGIONS_TO_ISO3.items()}
_NOWHERE: frozenset[str] = frozenset()
# A pack's subdivision code as a "City, ST" suffix. Requires the comma AND an UPPERCASE code in
# the ORIGINAL text (the "City, ST" convention), so a lowercase "in"/"or" inside prose never fires.
_SUBDIVISION_CODE_RE = re.compile(r",\s*([A-Z]{2})(?![A-Za-z])")
# An ISO-3166 alpha-3 country code where a provider names no city: a site code
# ("VNM06-01-Ho Chi Minh"), a dash prefix ("BGR-Varna"), or a parenthesised suffix
# ("Remote (IND)"). UPPERCASE in the ORIGINAL text is required for the same reason
# `_STATE_ABBREV_RE` requires it: a lowercase "can-do" must never read as Canada.
_ISO3_PREFIX_RE = re.compile(r"^([A-Z]{3})(?:[-.]|\d)")
_ISO3_PAREN_RE = re.compile(r"\(([A-Z]{3})\)\s*$")
# The LAST comma component, exactly three uppercase letters as written ("Dublin, IRL",
# "San Francisco,CRI"). Uppercase-only is what keeps the English words "Can", "Per" and "Ind"
# from ever reading as Canada, Peru and India. Checked against `NON_US_ISO3_SUFFIX`, a curated
# inclusion list, because a US location can also end in an uppercase code ("Remote, EST").
_ISO3_SUFFIX_RE = re.compile(r",\s*([A-Z]{3})\s*$")


def _country_code(segment: str) -> str | None:
    """The structural non-US alpha-3 country code a segment carries, uppercase, if any."""
    stripped = segment.strip()
    for pattern in (_ISO3_PREFIX_RE, _ISO3_PAREN_RE):
        match = pattern.search(stripped)
        if match and match.group(1).casefold() in NON_US_ISO3:
            return match.group(1)
    match = _ISO3_SUFFIX_RE.search(stripped)
    if match is not None and match.group(1).casefold() in NON_US_ISO3_SUFFIX:
        return match.group(1)
    return None


@dataclass(frozen=True)
class _CompiledPack:
    iso3: str
    strong: re.Pattern[str] | None
    subdivision_codes: frozenset[str]
    postal: re.Pattern[str] | None
    cities: re.Pattern[str] | None


@cache
def _compiled(pack: CountryPack) -> _CompiledPack:
    # An empty alternation compiles to a pattern that matches everywhere, so an empty token set
    # is `None`, never `_alternation(())`.
    strong = pack.markers | pack.bare_tokens | pack.subdivision_names
    return _CompiledPack(
        iso3=pack.iso3,
        strong=_alternation(strong) if strong else None,
        subdivision_codes=frozenset(code.casefold() for code in pack.subdivision_codes),
        postal=re.compile(pack.postal_pattern) if pack.postal_pattern else None,
        cities=_alternation(pack.cities) if pack.cities else None,
    )


def _strong_signal(pack: _CompiledPack, segment: str, low: str) -> bool:
    if pack.strong is not None and pack.strong.search(low):
        return True
    return any(
        match.group(1).casefold() in pack.subdivision_codes
        for match in _SUBDIVISION_CODE_RE.finditer(segment)
    )


def _weak_signal(pack: _CompiledPack, segment: str, low: str) -> bool:
    return bool(
        (pack.postal is not None and pack.postal.search(segment))
        or (pack.cities is not None and pack.cities.search(low))
    )


def _named(pattern: re.Pattern[str], to_iso3: dict[str, frozenset[str]], low: str) -> set[str]:
    return {code for match in pattern.finditer(low) for code in to_iso3[match.group(0)]}


def _resolve_segment(segment: str, packs: tuple[_CompiledPack, ...]) -> frozenset[str]:
    low = _fold(segment)
    if not low or low in POLICY_ONLY:
        return _NOWHERE
    if low in AMBIGUOUS_REGIONS:  # "Americas" / "Worldwide" — includes the US, undecidable
        return _NOWHERE
    # A pack's STRONG signals (country marker, bare country token, subdivision code or name)
    # are checked BEFORE any foreign token, so a US town that shares a foreign name — "Vienna,
    # VA", "Athens, GA", "Lebanon, NH", "Mexico, MO" — is kept, not silently dropped. This
    # ordering is the whole defense against a false drop of a pack country's posting in hard
    # mode; the reviewer found the reverse order deleting real US postings. The remaining
    # collision is a foreign city carrying a token that is ALSO a subdivision code ("Bangalore,
    # IN"): it resolves to the pack's country (kept) — a fail-open leak, never a drop. A bare
    # "Bangalore, India" still resolves IND via the country name below.
    #
    # A bare "US"/"U.S." is among the strong signals so it wins within a segment that also names
    # a foreign place ("US, Canada", "Remote - US, Canada", "US, EMEA") — the posting is offered
    # in the US. `_SEGMENT_SPLIT` never separates a comma / "and" / "&", so such a pair arrives
    # as one segment. A pack CITY, by contrast, stays AFTER the foreign tokens: a foreign city
    # sharing a US city's name ("Manchester, UK") must still read foreign.
    for pack in packs:
        if _strong_signal(pack, segment, low):
            return frozenset({pack.iso3})
    named = _named(_COUNTRY_NAME_RE, _COUNTRY_NAME_TO_ISO3, low) | _named(
        _CITY_RE, _CITY_TO_ISO3, low
    )
    if named:
        return frozenset(named)
    # After every strong signal above, so "USA-GA-Remote Location" has already resolved US and a
    # US state code in the same shape can never reach here. BEFORE the pack cities, so an
    # explicit country code beats a curated city name: "Kirkland, QC, CAN" is Quebec.
    code = _country_code(segment)
    if code is not None:
        return frozenset({code})
    regions = _named(_REGION_RE, _REGION_TO_ISO3, low)
    if regions:
        return frozenset(regions)
    # A postal code is checked AFTER foreign countries and regions so a foreign postal beside
    # its country ("Berlin, Germany 10115") reads foreign; a bare US ZIP with no other signal
    # still reads US.
    for pack in packs:
        if _weak_signal(pack, segment, low):
            return frozenset({pack.iso3})
    return _NOWHERE


def resolve_countries(
    locations: Sequence[str], packs: Sequence[CountryPack] = BUNDLED_PACKS
) -> frozenset[str]:
    """The ISO-3 countries a posting's locations name; empty when none can be resolved.

    `packs` is in PRECEDENCE order: when two packs both claim a segment, the first one wins,
    so a caller that puts the tenant's target countries first gets the target-first reading.
    Policy-only segments ("Hybrid", "Remote") are skipped so a real place beside them decides.
    """
    compiled = tuple(_compiled(pack) for pack in packs)
    found: set[str] = set()
    for location in locations:
        for segment in _SEGMENT_SPLIT.split(location):
            if segment.strip().casefold() in POLICY_ONLY:
                continue
            found |= _resolve_segment(segment, compiled)
    return frozenset(found)


def classify_location(locations: Sequence[str]) -> LocationClass:
    """Label a posting's locations `us` / `non_us` / `unknown` — the US reading of the resolver.

    A posting offered in several places keeps its US eligibility if ANY location is US — the
    applicant can take that one — so `us` wins over everything. Absent a US location, a single
    foreign signal makes it `non_us`; a posting with no geographic signal at all (bare "Remote",
    an office nickname, empty) is `unknown`.
    """
    countries = resolve_countries(locations)
    if "USA" in countries:
        return "us"
    return "non_us" if countries else "unknown"
