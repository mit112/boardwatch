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
                          A hedge inside a parenthetical that states its own duration bar
                          belongs to THAT bar and reaches nothing outside the aside.
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
from collections.abc import Callable, Iterator
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

# A parenthetical aside, and the shape that makes one a requirement in its own right.
# "0-1 years of professional software development experience (1+ years of internship
# experience desirable)" carries no comma and no conjunction, so the whole sentence is one
# clause and the aside's `desirable` stood the floor down -- the posting then wrote NO
# experience row at all, which is the zero-row shape the keystone calls a monitoring failure.
#
# Bounded to an aside that states its OWN duration, not to asides in general: a bare
# "(preferred)", "(strongly preferred)" or "(nice to have)" IS the sentence's hedge and must
# keep suppressing, because a stated preference read as a hard floor is the worst wrong
# verdict this engine can produce. The duration is what says the aside has a bar of its own
# for the hedge to belong to.
_ASIDE = re.compile(r"\(([^()]*)\)")
_ASIDE_DURATION = re.compile(r"\d\s*\+?\s*(?:years?|yrs?|months?|mos?)\b", re.IGNORECASE)


def _hedge_owned_by_an_aside(unit: str, lo: int, hi: int, mlo: int, mhi: int) -> bool:
    """Does the hedge at [mlo, mhi) belong to a parenthetical bar rather than to the span?

    False whenever the span sits in the same aside: there the hedge is the span's own.
    """
    for aside in _ASIDE.finditer(unit):
        if not (aside.start() <= mlo and mhi <= aside.end()):
            continue
        if aside.start() <= lo and hi <= aside.end():
            return False
        return _ASIDE_DURATION.search(aside.group(1)) is not None
    return False


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


# ---------------------------------------------------------------- heading context (T105)
#
# A heading and its bullets are never in one unit, so no suppressor above can see a hedge or
# an `OR` that a heading line states. This is a SEPARATE channel, bounded three ways and
# carried beside the unit list rather than inside it, so `split_units` stays byte-identical:
#   forward only, from a heading to the next header-like line or EOF (`qualifications_span`'s
#   rule); one level, because the nearest heading is the only one that governs; and it can only
#   drop a detection or mark it undecidable, never create one or decide an abstain.
# The heading vocabulary is shared with tailor/requirement_echo.py and lives here so that
# ENGINE_VERSION covers it.

# A line matching one of the qualifications-section header phrasings the spec names.
# `(?:Basic|Preferred|Minimum)\s+` is optional so "Requirements" and "Basic Qualifications"
# are both recognized by one pattern.
_QUAL_HEADER = re.compile(
    r"^\s*(?:(?:Basic|Preferred|Minimum)\s+)?"
    r"(?:Requirements|Qualifications|What You'?ll Need|Nice to Have|"
    r"You(?:'ll Have| Have)|Must Have)\s*:?\s*$",
    re.IGNORECASE,
)

# The generic "this line reads as SOME section heading" test used only to find where a
# qualifications span ENDS -- deliberately looser than _QUAL_HEADER (which names what a
# qualifications heading specifically says): short, no sentence-ending punctuation.
# Over-matching here only SHRINKS the span, which is the fail-safe direction (less
# corroboration material, never more).
_ANY_HEADER = re.compile(r"^[A-Za-z][A-Za-z /&'-]{0,58}:?$")

# Closed-class "glue" words that make up short, real section headers whose words AFTER
# the first are NOT capitalized ("What you will get", "About the team") -- fix for a
# real false-positive hole: the original end-boundary test required EVERY word
# capitalized, so this common header shape ran the span past it into benefits/perks
# prose. Deliberately NOT extended to open-class nouns: a genuine qualification line
# ("Bachelors degree preferred", "Experience with distributed systems") has real
# content words after the first, none of which are glue, so it is never mistaken for a
# header by this path.
_HEADER_GLUE_WORDS: frozenset[str] = frozenset(
    {"you", "your", "we", "us", "our", "will", "get", "gets", "the", "a", "an", "team"}
)


def _looks_like_header(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if _QUAL_HEADER.match(stripped):
        return True
    if not _ANY_HEADER.match(stripped):
        return False
    words = stripped.rstrip(":").split()
    if not words or len(words) > 6 or not words[0][0].isupper():
        return False
    # Path 1: every significant word capitalized (Title-Case/ALL-CAPS headers like
    # "Benefits:", "REQUIREMENTS", "Nice To Have Skills").
    if all(w[0].isupper() for w in words if w[0].isalpha()):
        return True
    # Path 2: a lowercase-continuation header whose words AFTER the first are all
    # closed-class glue. A genuine qualification line's later words are real content,
    # never glue-only, so this path never swallows one.
    return all(w.lower() in _HEADER_GLUE_WORDS for w in words[1:])


def qualifications_span(body_text: str) -> list[str]:
    """The lines between a qualifications-section header and the next header-like line
    (or EOF). `[]` if no header matches -- the fail-safe silent-miss case: corroboration
    below can never fire against an empty span, so a JD with no recognizable header
    structure simply cannot trigger requirement-echo, never a false positive."""
    lines = body_text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if _QUAL_HEADER.match(line.strip()):
            start = i + 1
            break
    if start is None:
        return []
    span: list[str] = []
    for line in lines[start:]:
        if _looks_like_header(line):
            break
        span.append(line)
    return span


def _on_heading_line(text: str, offset: int) -> tuple[bool, int]:
    """Whether the line holding `offset` reads as a heading, and where that line starts.

    A line that is only `OR` passes `_looks_like_header` as one capitalised word, and read as
    a heading it would govern the arm after it and split the alternative in two.
    """
    start = text.rfind("\n", 0, offset) + 1
    end = text.find("\n", offset)
    line = text[start : len(text) if end < 0 else end]
    return _looks_like_header(line) and not _or_only(line), start


def governing_headings(text: str, units: list[tuple[int, str]]) -> list[int | None]:
    """For each unit, the index of the heading unit that governs it, or None.

    A heading unit is itself ungoverned, and a later heading ENDS the earlier one's reach
    whether or not it says anything, so context never passes through a nested heading.

    The reach also ends where the list does, because `qualifications_span`'s own bound (the
    next header-like line or EOF) would carry `Nice to have:` over the paragraph after its
    bullets and drop a genuine `We require 8 years of experience.` there. So an UNMARKED line
    ends it after a bulleted one, or after a BLANK LINE once the heading has governed something
    (a list of plain lines). A bulleted line after a blank one continues it, since a loose list
    separates its items that way, and an OR link line never ends it, since it joins two items.
    """
    governing: list[int | None] = []
    current: int | None = None
    current_line = prev_line = -1
    governed = listed = False
    prev_end = 0
    for index, (offset, unit) in enumerate(units):
        heading, line = _on_heading_line(text, offset)
        if heading:
            if line != current_line:
                current, current_line = index, line
                governed = listed = False
        elif current is not None and line != prev_line:
            marked = _LIST_MARK.match(text, line) is not None
            if not marked and _OR_LEAD.match(unit) is None and (
                listed or (governed and _BLANK_LINE.search(text, prev_end, offset))
            ):
                current = None
            listed = listed or marked
        governing.append(None if heading else current)
        governed = governed or (current is not None and not heading)
        prev_end, prev_line = offset + len(unit), line
    return governing


_LIST_MARK = re.compile(r"[ \t]*[•‣●\-\*]")
_BLANK_LINE = re.compile(r"\n[ \t]*\n")


_BULLET_LEAD = re.compile(r"[\s•‣●\-\*]*")
_OR_LEAD = re.compile(_BULLET_LEAD.pattern + r"or(?:\s+|$)", re.IGNORECASE)
# One arm of the inline twin: the bullet without its marker, its leading OR or its full stop,
# because the alternative escapes read `[^.\n]` across the `or` they join.
_ARM_LEAD = re.compile(_BULLET_LEAD.pattern + r"(?:or(?:\s+|$))?", re.IGNORECASE)
_ARM_TAIL = re.compile(r"[\s.;!?]*$")


def _or_only(unit: str) -> bool:
    return _OR_LEAD.fullmatch(unit) is not None


def _arm(unit: str) -> str:
    return _ARM_TAIL.sub("", _ARM_LEAD.sub("", unit, count=1), count=1)


def alternative_groups(
    text: str, units: list[tuple[int, str]], governing: list[int | None]
) -> list[str | None]:
    """For each unit joined to its neighbours by an explicit OR between lines, the group
    written as its inline twin (`arm or arm or arm`), else None.

    The link is a line that is only `OR`, or a line that opens with it. It joins the units
    either side, never a heading, and never across one. The group is then read by each
    pattern's OWN alternative escapes, exactly as the one-line sentence would be: `or` stays
    out of `_CLAUSE_BOUNDARY`, and a list form waives nothing its inline twin would not.
    """
    groups: list[list[int] | None] = [None] * len(units)
    for index, (offset, unit) in enumerate(units):
        if not (offset == 0 or text[offset - 1] == "\n") or not _OR_LEAD.match(unit):
            continue
        before, after = index - 1, index + 1 if _or_only(unit) else index
        if before < 0 or after >= len(units) or _or_only(units[before][1]):
            continue
        if _or_only(units[after][1]) or governing[before] != governing[after]:
            continue
        if any(_on_heading_line(text, units[i][0])[0] for i in (before, after)):
            continue
        group = groups[before] or [before]
        group.append(after)
        groups[before] = groups[after] = group
    return [
        None if group is None else " or ".join(_arm(units[i][1]) for i in group)
        for group in groups
    ]


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
    aside_owned: bool = False,
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
    `aside_owned` is for the hedge path alone: it drops a hedge that a parenthetical bar of
    its own has claimed (`_hedge_owned_by_an_aside`).
    """
    clo, chi = bounds if bounds is not None else (0, len(text))
    for rx in suppressors:
        for match in rx.finditer(text):
            if aside_owned and _hedge_owned_by_an_aside(
                text, lo, hi, match.start(), match.end()
            ):
                continue
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


def _hedged_by_heading(
    heading: str, unit: str, lo: int, hi: int, hedges: tuple[re.Pattern[str], ...]
) -> str | None:
    """The hedge introducer allowance, read over the inline twin `heading + " " + unit`.

    "Nice to have:\n- 5 years" then drops exactly when "Nice to have: - 5 years" would, and a
    heading whose hedge is followed by more than delimiters ("Preferred Qualifications:")
    reaches nothing, as its one-line form reaches nothing.
    """
    intro = f"{heading} {unit}"
    shift = len(heading) + 1
    lo, hi = lo + shift, hi + shift
    return _suppressed(
        intro, lo, hi, hedges,
        bounds=_clause_bounds(intro, lo, hi), introducer=True, aside_owned=True,
    )


def _shifted(offset: int) -> Callable[[int], int]:
    return lambda p: offset + p


def _views(
    units: list[tuple[int, str]], governing: list[int | None], pattern: PatternSpec
) -> Iterator[tuple[int, str, Callable[[int], int], int | None]]:
    """(unit index, text to match, text position -> absolute offset, join) for every unit.

    A PREFERRED pattern also reads each governed unit as its inline twin, heading then bullet,
    so "Nice to have:\n- 5 years of experience." carries the same `preferred` row as its
    one-line form. `join` is where the bullet starts in that text, and only a match that
    crosses it is new. A required pattern never gets this view: a heading may weaken a bar,
    and "Must Have:\n- A bachelor's degree." must never read as the bar its one-line form is.
    """
    for index, (offset, unit) in enumerate(units):
        yield index, unit, _shifted(offset), None
        heading = governing[index]
        if heading is None or pattern.requiredness != "preferred":
            continue
        head_offset, head = units[heading]
        lead = _BULLET_LEAD.match(unit).end()  # type: ignore[union-attr]
        join = len(head) + 1

        def at(p: int, h: int = head_offset, o: int = offset + lead, j: int = join) -> int:
            return h + p if p < j else o + p - j

        yield index, f"{head} {unit[lead:]}", at, join


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
    # Heading context, computed once per scope beside the units and never folded into them.
    context_by_scope: dict[str, tuple[list[int | None], list[str | None]]] = {}
    for family in catalog.families:
        if family.id not in enabled_families:
            continue
        for pattern in family.patterns:
            if (units := units_by_scope.get(pattern.scope)) is None:
                units = units_by_scope[pattern.scope] = split_units(body_text, pattern.scope)
                governing = governing_headings(body_text, units)
                context_by_scope[pattern.scope] = (
                    governing, alternative_groups(body_text, units, governing)
                )
            governing, alternatives = context_by_scope[pattern.scope]
            for index, unit, at, join in _views(units, governing, pattern):
                for match in pattern.regex.finditer(unit):
                    lo, hi = match.start(), match.end()
                    if join is not None and not lo < join < hi:
                        continue
                    if _cue_outside(unit, lo, hi, catalog.negation_cues, pattern.cue_idioms):
                        continue
                    if _cue_inside(
                        unit, lo, hi, catalog.negation_cues, pattern.consumes_cues,
                        pattern.cue_idioms,
                    ):
                        continue
                    if _suppressed(body_text, at(lo), at(hi), pattern.suppressed_by):
                        continue
                    if _suppressed(unit, lo, hi, pattern.suppressed_by_sentence):
                        continue
                    bounds = _clause_bounds(unit, lo, hi)
                    if _suppressed(
                        unit, lo, hi, pattern.suppressed_by_unit,
                        bounds=bounds, introducer=True, aside_owned=True,
                    ):
                        continue
                    heading = governing[index]
                    if join is None and heading is not None and _hedged_by_heading(
                        units[heading][1], unit, lo, hi, pattern.suppressed_by_unit
                    ):
                        continue
                    if _suppressed(
                        unit, lo, hi, pattern.subject_suppressors,
                        bounds=bounds, before_only=True,
                    ):
                        continue
                    abstained = _suppressed(
                        body_text, at(lo), at(hi), pattern.abstain_by, inside_span=True
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
                    if abstained is None and pattern.abstain_by_adjacent:
                        # Own unit first, then the one immediately after it and no further.
                        # The forward step is the whole point: an equivalence escape is
                        # normally written as the NEXT sentence, while document scope let an
                        # alternative waive a bar arbitrarily far away (finding 4).
                        abstained = _suppressed(
                            unit, lo, hi, pattern.abstain_by_adjacent, inside_span=True
                        )
                        if abstained is None and index + 1 < len(units):
                            following = units[index + 1][1]
                            # The escape reaches back only if the following unit states no
                            # requirement of its OWN in this family. Distance alone cannot
                            # decide it (D-531): "A PhD is required. Equivalent experience
                            # may be substituted." and "A PhD is required. A bachelor's
                            # degree or equivalent experience is preferred." put the same
                            # escape regex at the same distance and must resolve OPPOSITELY.
                            # What separates them is ownership -- the second sentence states
                            # its own bar, so its `or equivalent` belongs to THAT bar and
                            # cannot waive the one before it.
                            owned = any(
                                other.regex.search(following) for other in family.patterns
                            )
                            if not owned:
                                abstained = _suppressed(
                                    following, 0, len(following),
                                    pattern.abstain_by_adjacent, inside_span=True,
                                )
                    if abstained is None and (group := alternatives[index]) is not None:
                        # An OR between lines, read as the one-line sentence it stands for,
                        # by the pattern's own same-sentence and adjacent escapes only.
                        abstained = _suppressed(
                            group, 0, len(group),
                            pattern.abstain_by_sentence + pattern.abstain_by_adjacent,
                            inside_span=True,
                        )
                    found.append(
                        Detection(
                            family=family.id,
                            pattern=pattern,
                            span=(at(lo), at(hi)),
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
