"""Non-US job-ad conventions read off a posting TITLE — the hard location gate's second axis.

`classify_location` reads places, and a place catalog is structurally incomplete: it can only
drop a city it has already heard of, and the next foreign site is always one it has not — Buc,
Basel, Penzberg and Kleinmachnow every one reached a shortlist as an unrecognised name. Worse,
three GE HealthCare postings carry `locations_json` of exactly `["Remote"]` and name no place
at all, so no catalog can ever reach them.

A job ad written in German or French is not a US role whatever city it names. That is a
different axis from geography, so it lives in its own module and its own gate clause rather
than inside `classify_location`, whose contract stays location-only and independently testable.

Only STRUCTURAL conventions are read, never vocabulary:

  - the DACH gender marker — "(m/w/d)", "(w/m/d)", "(d/f/m)", "(m/f/d)" — which German,
    Austrian and Swiss equal-treatment law makes near-universal in job ads;
  - the French equivalent "(H/F)";
  - "Ingénieur" / "Ingenieur", the French job noun and its German cognate.

Measured over 28,287 live open postings, these fire on **0** US-classified postings. A
hand-picked German role-noun list was measured and REMOVED: every token either never fired or
was already caught by the gender marker, and a bare "koch" would fire on "Koch Industries".

KNOWN, BOUNDED EXPOSURE — recorded, not widened. US job ads carry their own slash-separated
marker, the EEO string "M/F/D/V". The four-letter form does not match (V is not a gendered
letter here) and neither does the unparenthesised "EOE M/F/D/V", but a bare "(M/F/D)" or
"(M/F)" in a TITLE would. Two things bound it: the caller only consults this where
`classify_location` has NOT confirmed the US, and the corpus contains zero such titles — all 28
"M/F"-shaped titles in it are German postings in Munich, Frankfurt, Geneva and Witten. If a US
posting ever does carry one it will be kept anyway unless its location is also unresolvable.
"""

from __future__ import annotations

import re

# One to three gendered letters separated by slashes inside parentheses. The slash is REQUIRED:
# "(m)" and "(f)" are an ordinary parenthesised letter, not the convention.
_DACH_GENDER_MARKER = re.compile(r"\((?:\s*[mwfdx]\s*/){1,3}\s*[mwfdx]\s*\)", re.IGNORECASE)
_FRENCH_GENDER_MARKER = re.compile(r"\(\s*h\s*/\s*f\s*\)", re.IGNORECASE)
# Deliberately NOT word-bounded on the left: the French inclusive suffix ("Ingénieur(e)") and
# the German compound ("Betriebsingenieur") both have to hit. No English word contains it.
_ENGINEER_FR_DE = re.compile(r"ing[eé]nieur", re.IGNORECASE)

_MARKERS = (_DACH_GENDER_MARKER, _FRENCH_GENDER_MARKER, _ENGINEER_FR_DE)


def has_non_us_ad_marker(title: str) -> bool:
    """True when a title carries a non-US job-ad convention.

    The caller applies this only where `classify_location` has NOT confirmed the US, and folds
    the drop into the existing `hidden_hard_filter` count the run funnel already reports — a
    veto nobody can see is how a real job disappears unnoticed.
    """
    return any(pattern.search(title) for pattern in _MARKERS)
