"""Clause- and sentence-bounded requirement detection over ONE immutable posting version.

Matching is never a free substring, so a negation or an alternative cannot sit outside the
matched region unnoticed (spec §4.2). Polarity and a grammatical SUBJECT belong to a
CLAUSE; a qualifying ESCAPE belongs to the POSTING, and one mechanism cannot serve both.
Searching the whole unit was correct while every pattern was clause-scoped and became wrong
the moment patterns moved to sentence scope, because a cue or hedge in ANY clause then
cancelled a requirement in a DIFFERENT one and returned `eligible` with zero rows.

The scopes, all applied per match:

  negation cue (outside)  CLAUSE-scoped. A cue in the span's own clause, outside the span,
                          drops it. A pattern that consumes its own negation survives.
  negation cue (inside)   A cue INSIDE the span that the pattern does not declare it
                          consumes drops it: the cue was hidden in a wildcard gap.
  suppressed_by           DOCUMENT-scoped. "A more specific statement exists somewhere in
                          this posting, so stand down."
  suppressed_by_sentence  UNIT-scoped, unbounded. A same-sentence qualifying escape.
  suppressed_by_unit      CLAUSE-scoped hedge, plus an introducer allowance for a hedge
                          separated from its clause by delimiters only ("Nice to have: ...").
  subject_suppressors     CLAUSE-scoped grammatical subject that must PRECEDE the span.
  abstain_by              DOCUMENT-scoped, and does NOT drop: it marks the row undecidable
                          so the resolver renders UNKNOWN. Dropping would return `eligible`
                          by silence, the worst direction.
  abstain_by_sentence     The same abstain, UNIT-scoped. An escape that waives the bar its
                          own sentence states, and reaches no bar in any other sentence.

Every dropping rule only ever removes a detection, so a mistake is toward zero rows rather
than toward a verdict. Zero rows stores `eligible`, which every surface must render as "no
catalogued disqualifier detected" (D-P2-18), never as a clean bill of health.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from boardwatch.eligibility.catalog import PatternSpec, RulesCatalog

# The (?<!\.[A-Za-z]\.) guard stops a split inside a dotted abbreviation: for "U.S. citizens"
# the three characters before the boundary are ".S." so no split happens, while "AWS.
# Candidates" sees "WS." and splits normally. Without it, "U.S. citizens or permanent
# residents" was two units and the citizen-or-LPR pattern could never match.
_SENTENCE_SPLIT = re.compile(r"(?<!\.[A-Za-z]\.)(?<=[.!?])\s+|\n+|(?:^|\s)[•‣●\-\*]\s+")
_CLAUSE_SPLIT = re.compile(r"[;:,]")

# Where one clause ends and the next begins, for scoping polarity and subject. `or` is
# deliberately NOT here: "We do not require a degree or 5 years of experience." needs the
# `not` to reach the second item, and making `or` a boundary would fabricate a requirement.
# `and` IS here, the accepted trade: it costs a wrong `ineligible` on "...a degree and 5
# years..." (rare, the bad direction) and buys the floor back on "5 years is required, but
# 10 is preferred" (the commonest phrasing, the worst direction).
_CLAUSE_BOUNDARY = re.compile(r"[;:,]|(?<!\w)(?:and|but|while|whereas)(?!\w)", re.IGNORECASE)

_ONLY_DELIMS = re.compile(r"^[\s;:,()\[\]\-–—]*$")


@dataclass(frozen=True)
class Detection:
    family: str
    pattern: PatternSpec
    span: tuple[int, int]
    values: dict[str, str]
    # The `abstain_by` text that may waive this requirement, if any. Set means "detected,
    # real, and undecidable", which the resolver renders UNKNOWN. Distinct from a drop: the
    # row survives so it stays visible rather than lost to silence.
    abstained: str | None = None


def jd_locator(detection: Detection) -> dict[str, object]:
    start, end = detection.span
    return {"field": "body_text", "span": [start, end]}


def split_units(text: str, scope: str) -> list[tuple[int, str]]:
    """(absolute offset, unit text) pairs. Offsets index into `text` unchanged, because a
    span is persisted as a locator and must stay sliceable from the stored version."""
    units: list[tuple[int, str]] = []
    cursor = 0
    for piece in _SENTENCE_SPLIT.split(text):
        if not piece:
            continue
        start = text.find(piece, cursor)
        if start < 0:
            continue
        cursor = start + len(piece)
        if scope == "sentence":
            units.append((start, piece))
            continue
        inner = 0
        for clause in _CLAUSE_SPLIT.split(piece):
            offset = piece.find(clause, inner)
            if offset < 0:
                continue
            inner = offset + len(clause)
            units.append((start + offset, clause))
    return units


def _clause_bounds(unit: str, lo: int, hi: int) -> tuple[int, int]:
    """The bounds of the clause CONTAINING [lo, hi), for a cue or subject search.

    A span that CROSSES a boundary grows its clause to contain itself rather than being
    reported as an empty or inverted range. That case is real, not defensive: the
    sentence-scoped patterns exist precisely because their match spans a comma.
    """
    clo, chi = 0, len(unit)
    for match in _CLAUSE_BOUNDARY.finditer(unit):
        if match.end() <= lo:
            clo = match.end()
        elif match.start() >= hi:
            chi = match.start()
            break
    return clo, chi


def _in_idiom(
    low: str, span_lo: int, span_hi: int, idioms: tuple[re.Pattern[str], ...]
) -> bool:
    """Is this cue occurrence wholly inside a fixed idiom where it carries no polarity?

    An idiom is NOT a suppressor and not a hedge: it cancels nothing, it makes the cue
    INVISIBLE, so detection proceeds as if the words were absent. Applied to both cue
    searches, because the same boilerplate lands inside a span as often as outside one.
    """
    return any(
        m.start() <= span_lo and span_hi <= m.end()
        for rx in idioms
        for m in rx.finditer(low)
    )


def _cue_outside(
    unit: str,
    lo: int,
    hi: int,
    cues: tuple[str, ...],
    idioms: tuple[re.Pattern[str], ...],
) -> str | None:
    """A polarity cue outside the span but inside the span's own CLAUSE.

    Clause-bounded, not unit-bounded. Unit-bounded, "We do not require a degree, but 5 years
    of experience is required." dropped the genuine floor because of the `not` in the FIRST
    clause and returned `eligible` with zero rows.
    """
    clo, chi = _clause_bounds(unit, lo, hi)
    low = unit.casefold()
    for cue in cues:
        for match in re.finditer(rf"(?<!\w){re.escape(cue)}(?!\w)", low):
            if match.start() < clo or match.end() > chi:
                continue
            if _in_idiom(low, match.start(), match.end(), idioms):
                continue
            if match.end() <= lo or match.start() >= hi:
                return cue
    return None


def _cue_inside(
    unit: str,
    lo: int,
    hi: int,
    cues: tuple[str, ...],
    consumes: tuple[str, ...],
    idioms: tuple[re.Pattern[str], ...],
) -> str | None:
    """A cue INSIDE the span is invisible to _cue_outside, and that blind spot is a wrong
    verdict in both directions.

    "A current polygraph is not required for this position." matched from `polygraph` through
    `required`, hiding the `not` in the pattern's own wildcard gap. A pattern whose subject
    IS the restriction declares the cues it legitimately consumes in the catalog.
    """
    low = unit.casefold()
    keep = {c.casefold() for c in consumes}
    for cue in cues:
        if cue.casefold() in keep:
            continue
        for match in re.finditer(rf"(?<!\w){re.escape(cue)}(?!\w)", low):
            if _in_idiom(low, match.start(), match.end(), idioms):
                continue
            if match.start() >= lo and match.end() <= hi:
                return cue
    return None


def _suppressed(
    text: str,
    lo: int,
    hi: int,
    suppressors: tuple[re.Pattern[str], ...],
    bounds: tuple[int, int] | None = None,
    before_only: bool = False,
    introducer: bool = False,
    inside_span: bool = False,
) -> str | None:
    """Run a suppressor list against whatever string it is handed, outside the span.

    Scope is the caller's choice and the scopes are NOT interchangeable: polarity and
    SUBJECT belong to a CLAUSE, a qualifying ESCAPE belongs to the POSTING.

    `bounds` restricts the search to a clause (`suppressed_by_unit`, `subject_suppressors`).
    `introducer` additionally admits a hedge separated from the clause by delimiters ONLY,
    so "Nice to have: 10 years of experience." is not read as a hard requirement, while
    "Ideally 10 years; 5 years is required." keeps the second floor. `before_only` requires
    the match to precede the span, because a grammatical subject precedes its predicate.
    `inside_span` is for `abstain_by` alone (finding 45): an abstention is not a
    cancellation, so admitting a match inside the span can only turn a decided row into
    `unknown`, never the reverse, and the in-field patterns swallow the escape into the span.
    """
    clo, chi = bounds if bounds is not None else (0, len(text))
    for rx in suppressors:
        for match in rx.finditer(text):
            inside = clo <= match.start() and match.end() <= chi
            intro = (
                introducer
                and match.end() <= clo
                and _ONLY_DELIMS.match(text[match.end():clo]) is not None
            )
            if not (inside or intro):
                continue
            if before_only:
                if match.end() <= lo:
                    return match.group(0)
                continue
            if inside_span or match.end() <= lo or match.start() >= hi:
                return match.group(0)
    return None


def detect(
    body_text: str, catalog: RulesCatalog, *, enabled_families: frozenset[str]
) -> list[Detection]:
    """Every catalogued detection in one posting version's body text.

    Ordered by (family order in the catalog, span start). Requirement ordinal is dense from
    0 in exactly this order, and store/eligibility.py assigns ordinals by enumerate, so the
    caller passes a pre-sorted list rather than setting ordinals itself.
    """
    found: list[Detection] = []
    # `split_units` is pure in (text, scope) and this loop only READS `offset` and `unit`,
    # never mutating the list or the tuples, so one split per scope is shared across every
    # pattern instead of being recomputed once per pattern (~55 times per posting).
    # Keyed on the scope string a pattern actually declares, so a scope no enabled pattern
    # uses is never computed and nothing here depends on how many scopes the catalog allows.
    units_by_scope: dict[str, list[tuple[int, str]]] = {}
    for family in catalog.families:
        if family.id not in enabled_families:
            continue
        for pattern in family.patterns:
            if (units := units_by_scope.get(pattern.scope)) is None:
                units = units_by_scope[pattern.scope] = split_units(body_text, pattern.scope)
            for offset, unit in units:
                for match in pattern.regex.finditer(unit):
                    lo, hi = match.start(), match.end()
                    if _cue_outside(unit, lo, hi, catalog.negation_cues, pattern.cue_idioms):
                        continue
                    if _cue_inside(
                        unit, lo, hi, catalog.negation_cues, pattern.consumes_cues,
                        pattern.cue_idioms,
                    ):
                        continue
                    if _suppressed(
                        body_text, offset + lo, offset + hi, pattern.suppressed_by
                    ):
                        continue
                    if _suppressed(unit, lo, hi, pattern.suppressed_by_sentence):
                        continue
                    bounds = _clause_bounds(unit, lo, hi)
                    if _suppressed(
                        unit, lo, hi, pattern.suppressed_by_unit,
                        bounds=bounds, introducer=True,
                    ):
                        continue
                    if _suppressed(
                        unit, lo, hi, pattern.subject_suppressors,
                        bounds=bounds, before_only=True,
                    ):
                        continue
                    abstained = _suppressed(
                        body_text, offset + lo, offset + hi, pattern.abstain_by,
                        inside_span=True,
                    )
                    if abstained is None:
                        # Searched over the UNIT, not over `body_text` with unit bounds: a
                        # bounded search on the whole body can be defeated by a longer match
                        # that starts inside the unit and ends past it, which `finditer`
                        # returns instead of the shorter one that fits. The unit string
                        # cannot produce that match at all.
                        abstained = _suppressed(
                            unit, lo, hi, pattern.abstain_by_sentence, inside_span=True
                        )
                    found.append(
                        Detection(
                            family=family.id,
                            pattern=pattern,
                            span=(offset + lo, offset + hi),
                            values={
                                name: value
                                for name, value in match.groupdict().items()
                                if value
                            },
                            abstained=abstained,
                        )
                    )
    order_of = {family.id: index for index, family in enumerate(catalog.families)}
    found.sort(key=lambda d: (order_of[d.family], d.span[0]))
    return found
