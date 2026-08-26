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
two mappings that remain here are built with `dict(...)` CONSTRUCTOR CALLS rather than literals,
the documented escape hatch `role_gate` uses via `tuple([...])`. R9 traverses dict KEYS as
strings, so a bare `{...}` literal fails even when its keys are grammar names rather than user
data — this module was caught by exactly that on first registration.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Literal

from boardwatch.rank.leveling import (
    KNOWN_GRAMMARS,
    FieldTier,
    LevelingCatalog,
    LevelScheme,
    SeniorityBand,
)

TargetBand = Literal["entry", "mid", "senior", "any"]
SeniorityVerdict = Literal["in_band", "above_band", "uncertain"]

BAND_ORDER: dict[str, int] = dict(entry=0, mid=1, senior=2, staff_plus=3)

# The regexes are CODE; which of them are live is CATALOG. Keyed by grammar name so the
# catalog's `grammars:` section actually decides behaviour — otherwise it is declared data
# nothing reads, and editing it would silently change nothing.
_PATTERNS: dict[str, re.Pattern[str]] = dict(
    # "Level 5" — measured unambiguous (33/33 live hits are real levels).
    level_n=re.compile(r"\blevel\s+(\d{1,2})\b", re.IGNORECASE),
    # Bare letter+digit. Measured NOT to be levels: OSI layer 2, support tiers, facility codes.
    # Matched only so the gate can ABSTAIN loudly instead of silently ignoring them.
    l_prefix=re.compile(r"\b(L\s?-?\d{1,2})\b"),
    e_prefix=re.compile(r"\b(E\s?-?\d{1,2})\b"),
    ic_prefix=re.compile(r"\b(IC\s?-?\d{1,2})\b"),
    t_prefix=re.compile(r"\b(T\s?-?\d{1,3})\b"),
)

# Closed vocabulary, enforced at import: a grammar this module cannot match must never be
# declarable, or the catalog could name one and it would silently do nothing.
assert set(_PATTERNS) == KNOWN_GRAMMARS, (
    f"grammar patterns disagree with the catalog vocabulary: "
    f"{set(_PATTERNS) ^ KNOWN_GRAMMARS}"
)

# Phrases that CONTAIN a seniority word but are NOT seniority. Masked out BEFORE word matching,
# the same rescue-first ordering discipline `role_gate` uses and for the same reason: an
# unguarded word match is how a real job disappears.
#
# "Member of Technical Staff" is the whole reason this exists. It is the standard IC title at
# Perplexity, xAI, Cohere, Cockroach Labs, Adyen and others — frequently entry-level — and
# `role_gate._TITLE_SWE_SIGNAL` already names it a POSITIVE software signal. Without this mask
# the two gates in this package contradict each other on the same string: measured over 26,997
# live open postings, `staff` falsely dropped **94** `swe`-classified MTS titles. The 19 that
# also carry a real senior word ("Sr. Member of Technical Staff") still drop, because only the
# phrase is masked, not the title.
_NOT_SENIORITY_PHRASES: tuple[re.Pattern[str], ...] = tuple([
    re.compile(r"\bmembers?\s+of\s+technical\s+staff\b", re.IGNORECASE),
])


def mask_non_seniority_phrases(title: str) -> str:
    """Blank out phrases whose seniority word does not mean seniority.

    Replaced with spaces rather than removed so that offsets, word boundaries and any
    surrounding tokens are all preserved exactly.
    """
    for pattern in _NOT_SENIORITY_PHRASES:
        title = pattern.sub(lambda m: " " * len(m.group(0)), title)
    return title


# Bare roman numerals. `I` is deliberately absent: it is entry, so it can never raise the band,
# and matching it would collide with initials and Roman-numeral product names.
_ROMAN = re.compile(r"\b(I{2,3}|IV)\b")

# Management words that are ALSO ordinary product/domain nouns. They raise the band only as a
# title qualifier that shares a role's comma-clause ("Engineering Manager", "Lead Engineer"),
# never inside a product-noun phrase ("Password Manager", "Lead Scoring") — measured false drops
# of real entry SWE roles otherwise. Guarded like the MTS mask above, and for the same reason:
# an unguarded word match is how a real job disappears. `frozenset([...])` is a constructor call,
# the escape hatch this module already uses for R9-scoped title data.
_MANAGEMENT_AMBIGUOUS = frozenset(["lead", "leader", "manager", "director"])
# `development` is a role token so "Software Development Manager" reads as management OF a dev
# discipline. It only ever matters beside a management-ambiguous word (this token is consulted
# nowhere else), so it cannot drop an IC role on its own; "Business Development Manager" it would
# now grade as senior is already `not_swe` at the role gate and never reaches this gate.
_ROLE_TOKEN = re.compile(
    r"\b(?:engineer|engineering|developer|development|dev|swe|sde|sdet|sre|programmer|architect)\b",
    re.IGNORECASE,
)


def _qualifies_as_management_seniority(title: str, pos: int) -> bool:
    """Does the management word at `pos` grade a role, rather than name a product noun?

    Two shapes qualify:

    * It shares its comma-clause with a role token — the qualifier sits beside the role it
      grades ("Engineering Manager", "Lead Engineer", "Software Development Manager").
    * It HEADS the title and a later clause names the role ("Manager, Software Engineering",
      "Director, Back-End Engineering") — the inverted management title. This branch is
      DIRECTIONAL on purpose: the management word must PRECEDE the role, so a trailing
      product-noun "Manager" ("Software Engineer, Ads Manager") has the role first, never
      qualifies, and a real IC role is never dropped. The comma-delimiting is what tells the
      two apart — a product noun sits in its own clause after the role ("Software Engineer, Lead
      Scoring"), a management head noun sits in its own clause before it.
    """
    start = title.rfind(",", 0, pos) + 1
    end = title.find(",", pos)
    own = title[start:] if end == -1 else title[start:end]
    if _ROLE_TOKEN.search(own) is not None:
        return True
    # Inverted head-noun form: nothing before this clause names a role (so the management word
    # leads the title) and a later clause does.
    if end != -1 and _ROLE_TOKEN.search(title[:start]) is None:
        return _ROLE_TOKEN.search(title[end + 1 :]) is not None
    return False


def parse_seniority(
    title: str,
    scheme: LevelScheme | None,
    tier: FieldTier,
    catalog: LevelingCatalog,
) -> tuple[SeniorityBand | None, str]:
    """Return the title's band and the text that decided it, or (None, reason) to abstain."""
    # 1. Field-tier words, longest first so "vice president" beats "vp". Matched against the
    #    MASKED title so a phrase like "Member of Technical Staff" cannot read as `staff`.
    masked = mask_non_seniority_phrases(title)
    for word in sorted(tier.words, key=len, reverse=True):
        match = re.search(rf"\b{re.escape(word)}\b", masked, re.IGNORECASE)
        if match is None:
            continue
        # An ambiguous management word counts only when it shares a role's clause; otherwise it
        # is a product noun ("Password Manager") — skip it and keep looking for a real signal.
        if word.lower() in _MANAGEMENT_AMBIGUOUS and not _qualifies_as_management_seniority(
            masked, match.start()
        ):
            continue
        return tier.words[word], f'seniority word "{word}"'

    # 2. Ambiguous tokens abstain BEFORE any scheme can resolve them. Which grammars are
    #    ambiguous is the catalog's call, not this module's.
    for name in sorted(catalog.ambiguous_grammars):
        found = _PATTERNS[name].search(title)
        if found is not None:
            return None, (
                f'"{found.group(1)}" looks like a level but that token shape is ambiguous '
                "(it is usually a network layer, support tier or site code), so it never resolves"
            )

    # 3. Self-describing level token — again, only the grammars the catalog declares.
    level = None
    for name in sorted(catalog.self_describing_grammars):
        level = _PATTERNS[name].search(title)
        if level is not None:
            break
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


def build_token_probe(tier: FieldTier, catalog: LevelingCatalog) -> Callable[[str], bool]:
    """A predicate: would an ARMED gate have had something to say about this title?

    Used ONLY on the inert path (`target_seniority_band == "any"`), where `seniority_verdict`
    short-circuits before parsing. Without it "the gate is inert" is indistinguishable from
    "there was nothing to gate", and an inert gate nobody knows about is the same monitoring
    failure as an unreported abstain — the thing this module exists to prevent.

    It must answer for the gate that WOULD run, not for a looser one, because `top` turns a
    non-zero count into "set a target band". Every title it counts that the armed gate would
    ignore is a nag towards a setting that changes nothing. So it mirrors `parse_seniority`
    in both places that matters:

    * **Case sensitivity is per branch, never global.** `l_prefix`/`e_prefix`/`ic_prefix`/
      `t_prefix` and `_ROMAN` are deliberately case-SENSITIVE — lowercase `l2` is a network
      layer and lowercase `iv` is a word fragment — while `level_n` and the field-tier words
      match case-insensitively. Each branch is wrapped in a scoped `(?i:...)` only if its own
      compiled pattern carries `IGNORECASE`; compiling the whole alternation under one global
      `IGNORECASE` counted "Network Engineer l2" as a signal the gate can never act on.
    * **The title is MASKED first**, exactly as step 1 of `parse_seniority` masks it, so
      `staff` inside "Member of Technical Staff" is not counted. Measured for D-247, the
      unmasked probe counted 90 such titles the armed gate deliberately keeps. (Not the 94 in
      this module's header: that is D-246's count of titles the GATE falsely dropped, a
      different question over a different population. The two must not be conflated.)

    Built ONCE per rank by the caller, never per row: a single alternation scan plus one mask
    substitution is the whole cost, against the ~13 word searches a full parse would run.
    """
    alternatives = [rf"(?i:\b{re.escape(word)}\b)" for word in tier.words]
    alternatives += [rf"\b{re.escape(numeral)}\b" for numeral in tier.roman]
    alternatives += [
        f"(?i:{_PATTERNS[name].pattern})"
        if _PATTERNS[name].flags & re.IGNORECASE
        else _PATTERNS[name].pattern
        for name in sorted(catalog.ambiguous_grammars | catalog.self_describing_grammars)
    ]
    probe = re.compile("|".join(alternatives))

    def carries_a_band_token(title: str) -> bool:
        return probe.search(mask_non_seniority_phrases(title)) is not None

    return carries_a_band_token
