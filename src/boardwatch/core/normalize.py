"""Dedup normalization, ported function-by-function from the private pipeline (D9/§6.6).

content_hash is a pure, documented function of normalized body text:
SHA-256 over normalize_body(text) — lowercase, all whitespace runs collapsed
to single spaces, stripped. Whitespace-only and case-only changes therefore
never change the hash. (Port note: the source pipeline used MD5; the public
port uses SHA-256 — plan deviation 3.)
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from boardwatch.rank.location_data import (
    US_COUNTRY_SEGMENTS,
    US_STATE_ABBREVS,
    US_STATE_NAME_TO_ABBREV,
)

_NON_ALNUM_SPACE = re.compile(r"[^a-z0-9 ]")
_COMPANY_SUFFIXES = re.compile(r"\b(inc|llc|corp|co|ltd|technologies|technology|labs)\b")
# Title normalization is Unicode-aware (unlike normalize_company's pinned ASCII-only
# caveat): an all-non-ASCII title (e.g. Korean) must keep its letters, otherwise it
# collapses to "" and every such posting collides into one bucket. \W is Unicode-aware
# for str patterns, and _ is excluded so titles fold the same way ASCII ones do.
_NON_ALNUM_TO_SPACE = re.compile(r"[\W_]")
_WS = re.compile(r"\s+")

# Folded to words BEFORE the punctuation strip, which would otherwise erase them and make
# "C++ Developer", "C# Developer" and "C Developer" all normalize to "c developer" — three
# different roles sharing one identity component. `exact_quad` also requires an identical
# content_hash, so the collision only bites when a poster reuses one body across a role
# family, which is exactly what boilerplate reqs do. Precision is the invariant here.
#
# Only these two characters are folded, not punctuation generally: measured on a live
# 23,455-posting corpus, 8 of 147 suppression groups differ in raw title and all 8 differ
# only in punctuation/case noise on the same role (hyphen vs comma, "Store-in-Store" vs
# "Store in Store", "Javascript" vs "JavaScript"). Folding more would leak those 8 real
# duplicates to defend a collision that does not occur. 123 open titles contain "+" and 16
# contain "#", and none of them sits in any suppression group, so this costs no recall.
_LANG_TOKENS = (("+", " plus "), ("#", " sharp "))


def normalize_company(name: str) -> str:
    c = name.lower().strip()
    c = _NON_ALNUM_SPACE.sub("", c)
    c = _COMPANY_SUFFIXES.sub("", c)
    return _WS.sub(" ", c).strip()


def normalize_title(title: str) -> str:
    t = title.lower()
    for char, word in _LANG_TOKENS:
        t = t.replace(char, word)
    t = _NON_ALNUM_TO_SPACE.sub(" ", t)
    return _WS.sub(" ", t).strip()


# --- location canonicalization -------------------------------------------------------------
# One place written two ways is one place. Measured on the live queue tree, 46 of 70 redundant
# folders differ ONLY in the location string, and two of those pairs are literally the same
# city: "Austin, Texas, United States" vs "Austin, TX", and "San Francisco, CA, San Francisco
# Office" vs "San Francisco County, CA". `normalized_locations` is a component of every
# location-bearing identity key, so those never grouped.
#
# Every rule below is a SPELLING rule, applied per comma-separated segment. None of them merges
# two different places: cross-city merging (PayPal's San Jose / Austin / Scottsdale / NYC),
# subset/superset lists (Twitch) and country folding (Affirm's "Remote US" vs "Remote Canada")
# are all deliberately NOT done here — they are owner policy calls, and each would hide a
# genuinely different posting. Over-merging deletes a real job from the owner's view, which is
# the failure this repo refuses (fail-safe direction: never silently delete a real job).
#
# Out-of-catalog segments are LEFT ALONE, never guessed. A non-US location therefore passes
# through untouched: "London, United Kingdom", "Bengaluru, Karnataka, India" and "Toronto, ON,
# Canada" all canonicalize to themselves. The one ambiguity in the catalog is "georgia", which
# is both a US state and a country, so "Tbilisi, Georgia" becomes "tbilisi, ga". That cannot
# produce a wrong merge — nothing spells the country "GA" — and both spellings already
# collided under the previous normalizer when the string was the bare word "Georgia".
_TRAILING_PAREN = re.compile(r"\s*\([^()]*\)$")
_OFFICE = " office"


def _strip_site_code(segment: str) -> str:
    """Drop a trailing parenthetical site code, but only from a bare state segment.

    "Costa Mesa, CA (OC-00)" and "Costa Mesa, California, United States" are one place; the
    parenthesis is Vantage's internal building code. The guard is what keeps this narrow: the
    parenthetical is dropped only when what remains IS a US state, so "Remote (IND)" — the
    ISO alpha-3 country signal the location gate reads — is untouched, and so is any
    parenthetical carrying real geography ("San Jose (Costa Rica)").
    """
    remainder = _TRAILING_PAREN.sub("", segment).strip()
    return remainder if remainder != segment and _is_us_state(remainder) else segment


def _is_us_state(segment: str) -> bool:
    return segment in US_STATE_ABBREVS or segment in US_STATE_NAME_TO_ABBREV


def canonical_location(text: str) -> str:
    """One spelling for one place, or the input folded but otherwise unchanged.

    Segment-wise and catalog-driven; see the block comment above for what this deliberately
    does NOT do. Any change here is a normalizer change and requires an
    IDENTITY_ALGORITHM_VERSION bump (core/identity_kinds.py).
    """
    folded = normalize_body(text)
    segments = [seg.strip() for seg in folded.split(",")]
    segments = [_strip_site_code(seg) for seg in segments if seg.strip()]
    if not segments:
        return folded
    # A trailing office/site name. "san francisco, ca, san francisco office" is the SF office,
    # which is San Francisco. Never the only segment: "home office" alone is all the evidence
    # the posting carries, and dropping it would invent an empty location.
    while len(segments) > 1 and (segments[-1] == "office" or segments[-1].endswith(_OFFICE)):
        segments.pop()
    # A trailing "United States", but only when a US state still names the place. Without the
    # guard, "Remote, US" would fold to "remote" and lose the only country evidence it has.
    if len(segments) > 1 and segments[-1] in US_COUNTRY_SEGMENTS and _is_us_state(segments[-2]):
        segments.pop()
    # State name -> USPS abbreviation, NEVER in the first segment: "New York, NY" must not
    # become "ny, ny" and "Washington, DC" must not become "wa, dc". A bare "New York" or
    # "Washington" is a city as often as a state, so it is left exactly as written.
    segments = [segments[0]] + [US_STATE_NAME_TO_ABBREV.get(s, s) for s in segments[1:]]
    # "X County, ST" -> "X, ST", only with a US state immediately after it, so a bare
    # "Orange County" and Ireland's "County Cork" are both untouched.
    segments = [
        seg[: -len(" county")].strip()
        if seg.endswith(" county") and i + 1 < len(segments) and _is_us_state(segments[i + 1])
        else seg
        for i, seg in enumerate(segments)
    ]
    return ", ".join(segments)


def canonical_locations(locations: Iterable[str]) -> list[str]:
    """The sorted, de-duplicated canonical form of a posting's whole location list.

    Canonicalization can make two ITEMS of one list equal — Brex publishes the primary city
    in long form beside the same city in short form — and a place named twice is one place,
    so the result is a set. That is de-duplication WITHIN one posting's evidence, not
    subset/superset merging across postings, which stays out of scope.

    The office-alias fold is the same rule reaching across two items: Lyft publishes
    `["San Francisco, CA", "San Francisco Office"]`, where the second item is the first
    city's office, not a second city. It is dropped only when the city it names is already
    in the list, so `["Seattle, WA", "San Francisco Office"]` keeps both and a list that is
    ONLY an office name keeps it — this can never empty the evidence.
    """
    canon = {canonical_location(item) for item in locations}
    cities = {item.split(",", 1)[0].strip() for item in canon}
    kept = {
        item
        for item in canon
        if not (item.endswith(_OFFICE) and item[: -len(_OFFICE)].strip() in cities)
    }
    return sorted(kept)


def normalize_body(text: str) -> str:
    return _WS.sub(" ", text).strip().lower()


def content_hash(body_text: str) -> str:
    return hashlib.sha256(normalize_body(body_text).encode("utf-8")).hexdigest()


# Allowlist, not denylist (design §4.1). Compared case-insensitively; anything not
# listed is dropped, including every utm_*, gh_src, ref and whatever is invented next.
_URL_PARAM_ALLOWLIST = frozenset(
    {"gh_jid", "jid", "id", "jobid", "req_id", "requisitionid", "posting_id", "lever_id"}
)
_DUP_SLASH = re.compile(r"/{2,}")


def normalize_url(url: str) -> str:
    """Canonical URL for host classification and survivor election.

    Not part of any identity key in P6 slice 1 — identity keys are built from company,
    title, locations and content hash. This exists so two spellings of the same posting
    URL classify and elect identically, and so slice 2's ledger has a stable key.
    """
    raw = url.strip()
    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw
    if not parts.netloc:
        return raw
    host = parts.hostname or ""
    if host.startswith("www."):
        host = host[4:]
    path = _DUP_SLASH.sub("/", parts.path)
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    kept = [
        f"{name}={value}"
        for name, value in parse_qsl(parts.query, keep_blank_values=True)
        if name.lower() in _URL_PARAM_ALLOWLIST
    ]
    # sorted() so param order is not identity.
    return urlunsplit(("https", host, path, "&".join(sorted(kept)), ""))
