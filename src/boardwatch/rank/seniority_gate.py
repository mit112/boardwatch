"""Title seniority gate: is this posting above the band the operator is targeting? (D-246.)

Mirrors `role_gate` in shape and in discipline — ordered rules, and EVERY non-pass verdict
carries the text that decided it, because a gate you cannot audit is how a real job disappears.

ORDER IS LOAD-BEARING. Field-tier words run before level tokens so that "Staff Software
Engineer, Level 6" reports the word (universal, certain) rather than the level (which needs a
binding and might abstain). Ambiguous grammars are checked BEFORE self-describing ones so a
bound scheme can never rescue an `L2` that is really OSI layer 2.

The fail direction is fixed by the keystone invariant: only a confident word, roman numeral, or
bound-scheme hit may DROP. A level token with no binding, a level outside its scheme's range,
and every ambiguous bare-letter token all return `uncertain`, which the caller passes through
FLAGGED and COUNTS. Absence of any token is `in_band` — silence is never evidence of seniority.

R9 note: listed in `tools/generalization/defaults.py::SCOPED_MODULES` for the same reason
`role_gate` is — it holds TITLE data, and moving title data to an unscoped module to escape the
rule is the evasion R9 exists to catch. The word and band data live in `leveling.yaml`; the
patterns here are built with `tuple(...)` constructor calls, the documented escape hatch.
"""

from __future__ import annotations

import re
from typing import Literal

from boardwatch.rank.leveling import FieldTier, LevelingCatalog, LevelScheme, SeniorityBand

TargetBand = Literal["entry", "mid", "senior", "any"]
SeniorityVerdict = Literal["in_band", "above_band", "uncertain"]

BAND_ORDER: dict[str, int] = {"entry": 0, "mid": 1, "senior": 2, "staff_plus": 3}

# "Level 5" — the one grammar measured to be unambiguous (33/33 live hits are real levels).
_LEVEL_N = re.compile(r"\blevel\s+(\d{1,2})\b", re.IGNORECASE)

# Bare letter+digit. Measured NOT to be levels: OSI layer 2, support tiers, facility codes.
# Matched only so the gate can ABSTAIN loudly instead of silently ignoring them.
_AMBIGUOUS: tuple[re.Pattern[str], ...] = tuple([
    re.compile(r"\b(L\s?-?\d{1,2})\b"),
    re.compile(r"\b(E\s?-?\d{1,2})\b"),
    re.compile(r"\b(IC\s?-?\d{1,2})\b"),
    re.compile(r"\b(T\s?-?\d{1,3})\b"),
])

# Bare roman numerals. `I` is deliberately absent: it is entry, so it can never raise the band,
# and matching it would collide with initials and Roman-numeral product names.
_ROMAN = re.compile(r"\b(I{2,3}|IV)\b")


def parse_seniority(
    title: str,
    scheme: LevelScheme | None,
    tier: FieldTier,
    catalog: LevelingCatalog,
) -> tuple[SeniorityBand | None, str]:
    """Return the title's band and the text that decided it, or (None, reason) to abstain."""
    # 1. Field-tier words, longest first so "vice president" beats "vp".
    for word in sorted(tier.words, key=len, reverse=True):
        if re.search(rf"\b{re.escape(word)}\b", title, re.IGNORECASE):
            return tier.words[word], f'seniority word "{word}"'

    # 2. Ambiguous tokens abstain BEFORE any scheme can resolve them.
    for pattern in _AMBIGUOUS:
        found = pattern.search(title)
        if found is not None:
            return None, (
                f'"{found.group(1)}" looks like a level but that token shape is ambiguous '
                "(it is usually a network layer, support tier or site code), so it never resolves"
            )

    # 3. Self-describing level token.
    level = _LEVEL_N.search(title)
    if level is not None:
        if scheme is None:
            return None, (
                f'"{level.group(0)}" is a level but this company has no scheme bound; '
                "bind one in {config_dir}/leveling-bindings.yaml"
            )
        rung = level.group(1)
        if rung not in scheme.levels:
            return None, (
                f'"{level.group(0)}" is outside scheme {scheme.name!r}, which covers '
                f"{', '.join(sorted(scheme.levels))}"
            )
        return scheme.levels[rung], f'{scheme.name} "{level.group(0)}"'

    # 4. Bare roman numerals, from the field tier.
    roman = _ROMAN.search(title)
    if roman is not None:
        band = tier.roman.get(roman.group(1).upper())
        if band is not None:
            return band, f'roman numeral "{roman.group(1)}"'

    # 5. Nothing found. Absence of signal is never seniority.
    return "entry", "no seniority signal in title"


def seniority_verdict(
    title: str,
    scheme: LevelScheme | None,
    target_band: TargetBand,
    tier: FieldTier,
    catalog: LevelingCatalog,
) -> tuple[SeniorityVerdict, str]:
    """Classify a title against the operator's target band.

    `any` makes the gate inert, and says so rather than passing silently — an inert gate nobody
    knows about is the same monitoring failure as an unreported abstain.
    """
    if target_band == "any":
        return "in_band", "gate inert: target_seniority_band is `any`"
    band, reason = parse_seniority(title, scheme, tier, catalog)
    if band is None:
        return "uncertain", reason
    if BAND_ORDER[band] > BAND_ORDER[target_band]:
        return "above_band", f"{band} above target {target_band} ({reason})"
    return "in_band", reason
