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
  - "Ingénieur" / "Ingenieur", the French job noun and its German cognate;
  - a title written in CJK script — Han ideographs, kana or hangul.

Measured over 28,287 live open postings, the first three fire on **0** US-classified
postings. A hand-picked German role-noun list was measured and REMOVED: every token either
never fired or was already caught by the gender marker, and a bare "koch" would fire on
"Koch Industries".

The CJK clause is the same shape as the other three and was added for the same reason
(D-294): 16 Genentech postings named Changchun, Jinan, Shijiazhuang, Changsha, Urumqi,
Zhengzhou, Shenyang, Shaoxing, Changde and Saitama — every one an explicit foreign city
the location catalog had simply never heard of — and cleared the hard US-only gate because
`classify_location` fails OPEN on `unknown`. Enumerating world cities is unbounded; a
script test is not. Measured over 33,572 live open postings: 379 titles carry CJK script
and **0** of them classify as US.

SCRIPT RANGES, NOT "NON-ASCII", and the difference is the whole point. Over the same
corpus, 1,440 titles contain a non-ASCII character and 1,061 of those carry no CJK script
at all — ordinary English titles punctuated with an en-dash or em-dash ("Staff Machine
Learning Engineer - (ADAS/Autonomous Driving)"), or carrying a trademark sign. A
non-ASCII test would drop every one of them.

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
# CJK script: Han ideographs (Extension A + Unified), kana, hangul. SCRIPT only — a Latin
# title that merely borrows a CJK punctuation mark is still a Latin title.
#
# Only ONE exclusion is an actual carve-out here: U+30FB "・" and U+30FC "ー" sit INSIDE the
# kana block but are punctuation, so the kana range is SPLIT around them and
# "Software Engineer・Remote" no longer fires. A title written in real kana always carries a
# kana letter as well, so the split costs nothing — verified against every live CJK title.
#
# Two other punctuation blocks were never in range and are named only so a future widening
# does not reach for them: the U+3000 block ("Software Engineer 【Remote】", U+3010/U+3011),
# and Halfwidth and Fullwidth Forms, which is where the parentheses in "（高级）治疗领域专员"
# actually live — U+FF08/U+FF09, NOT U+3000 as the shape of those characters suggests. That
# mistake matters: a test citing them as proof of the U+3000 exclusion proves nothing.
# Excluding U+FF00 also means halfwidth katakana (U+FF66-FF9D) cannot fire; 0 live titles.
_CJK_SCRIPT = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30fa\u30fd-\u30ff\uac00-\ud7af]"
)

_MARKERS = (_DACH_GENDER_MARKER, _FRENCH_GENDER_MARKER, _ENGINEER_FR_DE, _CJK_SCRIPT)


def has_non_us_ad_marker(title: str) -> bool:
    """True when a title carries a non-US job-ad convention.

    The caller applies this only where `classify_location` has NOT confirmed the US, and folds
    the drop into the existing `hidden_hard_filter` count the run funnel already reports — a
    veto nobody can see is how a real job disappears unnoticed.
    """
    return any(pattern.search(title) for pattern in _MARKERS)
