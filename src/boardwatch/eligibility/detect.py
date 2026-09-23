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
  hedged_by_tail          UNIT-scoped, but only a hedge that is the sentence-final PREDICATE
                          of the bar's own phrase (`_hedged_tail`). Drops the bar, or carries
                          it as the `hedged_as` preferred pattern.
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
from functools import cache

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


# ---------------------------------------------------------------- tail hedge (T170)
#
# "5+ years of experience, not required but preferred." put its hedge in a LATER clause than
# the bar, outside `_clause_bounds`, so the bar kept its required row and rejected a 2-year
# profile. Widening the hedge to the whole sentence is wrong the other way: after a bar, the
# commonest hedge qualifies a SUB-CLAUSE ("..., preferably in public accounting", "..., with a
# focus on RBAC preferred", "(financial services preferred)", "..., 10+ years preferred").
#
# So the test is structural. The hedge must be the sentence-final PREDICATE, and everything
# between the bar and it must be the bar's own COMPLEMENT: one phrase, which does not open with a
# delimiter or a coordinator, holds no clause break, no second duration or requirement marker, no
# adverbial or exemplifying introducer, no adjunct or `with` modifier phrase, no second
# `experience` head, and commas only inside a CLOSED list. The hedge words are the catalog's; the
# words here are closed grammatical classes (delimiters, copulas, coordinators, prepositions).

_TAIL_NEGATED_BAR = r"not\s+(?:strictly\s+|necessarily\s+)?(?:required|mandatory|necessary)"
_TAIL_INTENSITY = r"(?:(?:also|very|highly|strongly|much|greatly|especially)\s+)?"
_TAIL_ASIDE = re.compile(r"\(([^()]*)\)")
_TAIL_DURATION = re.compile(r"\d\s*\+?\s*(?:years?|yrs?|months?|mos?)(?!\w)", re.IGNORECASE)
# The complement continues the bar, so it cannot open a new constituent -- unless the bar stopped
# short of its own head (`2+ years of shipping`, `3+ years of experience leading`), where a comma
# or a coordinator continues the same phrase (`, receiving, or manufacturing experience`).
_TAIL_OPENS = re.compile(r"\s*(?:[,;:()\[\]–—-]|(?:and|or|but|&)(?!\w))", re.IGNORECASE)
_TAIL_CONTINUES = re.compile(r"\s*(?:,|(?:and/or|and|or|&)(?!\w))", re.IGNORECASE)
_TAIL_HEAD_END = re.compile(r"(?<!\w)(?:experiences?|years?|yrs?|months?)\W*\Z", re.IGNORECASE)
# A clause break, including a full stop the splitter could not see because no space follows it
# (" .Knowledge on ..."). Case-SENSITIVE, so `.NET`, `Node.js` and `U.S. Government` pass.
_TAIL_BREAK = re.compile(r"[;:()\[\]–—]|\s-\s|(?:\s|(?<=[a-z]{2}))\.(?=[A-Z][a-z])")
_TAIL_MARKER = re.compile(
    r"(?<!\w)(?:required|requirements?|requires?|must|minimum|mandatory|necessary|essential|"
    r"needed)(?!\w)",
    re.IGNORECASE,
)
_TAIL_INTRODUCER = re.compile(
    r"(?<!\w)(?:preferably|ideally|including|includes|such\s+as|e\.g\.|i\.e\.|especially|"
    r"particularly|specifically)(?!\w)",
    re.IGNORECASE,
)
# A comma then a subordinator or a preposition opens an ADJUNCT, and a hedge after it is its own.
_TAIL_ADJUNCT = re.compile(
    r",\s*(?:with|plus|along|where|which|who|whose|that|as|while|but|in|within|at|for|on|from|"
    r"across|to|of|through|under|by)(?!\w)",
    re.IGNORECASE,
)
_TAIL_NEW_HEAD = re.compile(
    r"(?<!\w)experiences?\s+(?:in|with|of|on|at|using|as|for|across|within)(?!\w)", re.IGNORECASE
)
# A capitalised determiner mid-sentence is a sentence break lost in extraction. Case-SENSITIVE.
_TAIL_LOST_BREAK = re.compile(r"(?<=[a-z0-9)])\s+(?:Some|The|A|An|Any|All|This|These|Our|Your)\s")
_TAIL_WITH = re.compile(r"(?<!\w)with(?!\w)", re.IGNORECASE)
_TAIL_GERUND = re.compile(r"\w+ing\s+\Z", re.IGNORECASE)
# Even the head's own `with` opens a MODIFIER phrase, not the bar's object, when a quality noun
# and its preposition follow within three words (`with a focus on`, `with a mix of`, `with
# demonstrated expertise in`). A determiner alone is not the test: `experience with a national
# securities exchange` is the bar's object. Searched over the span too, because a scoped span can
# end in its own `with`.
_TAIL_WITH_MODIFIER = re.compile(
    r"(?<!\w)with\s+(?:[\w-]+\s+(?:and\s+)?){0,3}?(?:focus|emphasis|mix|blend|combination|"
    r"expertise|knowledge|exposure|understanding|background|proficiency|familiarity)\s+"
    r"(?:in|on|of|to|with)(?!\w)",
    re.IGNORECASE,
)
# A hedge that is the object complement of `as` (`..., and/or Spark as a plus`) hedges that noun.
_TAIL_AS = re.compile(r"(?<!\w)as\s*\Z", re.IGNORECASE)
_TAIL_HEAD = re.compile(r"(?<!\w)experiences?(?!\w)", re.IGNORECASE)
_TAIL_COORDINATOR = re.compile(r"(?<!\w)(?:and|or|&)(?!\w)", re.IGNORECASE)
_TAIL_OXFORD = re.compile(r"\s*(?:and/or|and|or|&)(?!\w)", re.IGNORECASE)


@cache
def _tail_predicate(hedges: tuple[re.Pattern[str], ...]) -> re.Pattern[str]:
    """The sentence-final predicate over the catalog's hedge words: `, preferred.`,
    ` is highly preferred`, `, not required but preferred.`, ` a plus`, ` (preferred)`,
    ` – Highly preferred`."""
    hedge = "(?:" + "|".join(rx.pattern for rx in hedges) + ")"
    return re.compile(
        r"(?P<pred>\s*[,–—-]?\s*(?:"
        r"(?:(?:is|are|would\s+be|will\s+be|(?:is\s+|are\s+)?considered)\s+)?"
        rf"{_TAIL_INTENSITY}(?:an?\s+)?{hedge}"
        rf"(?:\s*,?\s*(?:but|though|although)?\s*{_TAIL_NEGATED_BAR})?"
        rf"|{_TAIL_NEGATED_BAR}\s*,?\s*(?:but|though|although)\s+(?:(?:is|are)\s+)?"
        rf"{_TAIL_INTENSITY}(?:an?\s+)?{hedge}"
        rf"|\(\s*{_TAIL_INTENSITY}{hedge}\s*\)"
        r"))[\s.!?]*\Z",
        re.IGNORECASE,
    )


def _hedged_tail(
    unit: str, lo: int, hi: int, hedges: tuple[re.Pattern[str], ...]
) -> int | None:
    """Where the hedge that predicates the WHOLE bar at [lo, hi) ends in `unit`, or None."""
    tail = unit[hi:]
    found = _tail_predicate(hedges).search(tail)
    if found is None:
        return None
    end = hi + found.end("pred")
    bar = unit[lo:hi]
    complement = tail[: found.start()]
    if not complement.strip():
        return end
    # A bare aside glued to a word, `Pega(Preferred)`, hedges that word, not the bar.
    if found.group("pred").startswith("(") and complement[-1].isalnum():
        return None
    # The span already crossed into a second noun phrase with its own head.
    if len(_TAIL_HEAD.findall(bar)) > 1:
        return None
    # An aside that is neither a hedge nor a bar is part of the phrase: `Kubernetes (K8s) ...`.
    complement = _TAIL_ASIDE.sub(
        lambda aside: aside.group(0)
        if _TAIL_DURATION.search(aside.group(1)) or any(rx.search(aside.group(1)) for rx in hedges)
        else " " * len(aside.group(0)),
        complement,
    )
    if _TAIL_OPENS.match(complement) and not (
        _TAIL_CONTINUES.match(complement) and _TAIL_HEAD_END.search(bar) is None
    ):
        return None
    for guard in (
        _TAIL_BREAK, _TAIL_DURATION, _TAIL_MARKER, _TAIL_INTRODUCER, _TAIL_ADJUNCT,
        _TAIL_NEW_HEAD, _TAIL_LOST_BREAK,
    ):
        if guard.search(complement):
            return None
    if any(rx.search(complement) for rx in hedges):
        return None
    # `with` is the bar's own preposition only straight after its head or after a gerund.
    for word in _TAIL_WITH.finditer(complement):
        before = complement[: word.start()]
        if before.strip() and not _TAIL_GERUND.search(bar + before):
            return None
    if _TAIL_WITH_MODIFIER.search(bar + complement) or _TAIL_AS.search(complement):
        return None
    if "," in complement:
        last = complement[complement.rfind(",") + 1 :]
        closed = _TAIL_OXFORD.match(last) is not None or (
            complement.count(",") + bar.count(",") >= 2
            and _TAIL_COORDINATOR.search(last) is not None
        )
        if not closed:
            return None
    return end


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


def _on_heading_line(text: str, offset: int, unit: str) -> tuple[bool, int, int]:
    """Whether the unit at `offset` is a heading, where its line starts, and which heading it
    is: a heading LINE may hold several units and the first governs, so it is keyed on the line;
    a heading ITEM is its own unit, so two on one line are two headings.

    A line that is only `OR` passes `_looks_like_header` as one capitalised word, and read as
    a heading it would govern the arm after it and split the alternative in two.

    A list item (a line, or a unit after an inline bullet) that opens with a heading label is
    one too: `Requirements: • 8 years of experience.` and `• Requirements: • 8 years ...` on
    one line, or `Requirements: 8 years of experience.` after plain lines. The whole line does
    not read as a heading, and missing it would leave an earlier `Nice to have:` governing a
    genuine bar.
    """
    start = text.rfind("\n", 0, offset) + 1
    end = text.find("\n", offset)
    line = text[start : len(text) if end < 0 else end]
    if _looks_like_header(line) and not _or_only(line):
        return True, start, start
    if text[start:offset].strip() and not _opens_item(text, offset):
        return False, start, offset
    item = unit[_BULLET_LEAD.match(unit).end() :]  # type: ignore[union-attr]
    label = _LEADING_LABEL.match(item)
    if label is None:
        return False, start, offset
    # A label ALONE is read by the generic test. A label ahead of content must name a
    # qualification section: `Experience: 5 years ...` is a field inside the list, and read as
    # a heading it would reset an earlier `Nice to have:` and restore the bar it hedged.
    reads = _QUAL_HEADER.match if item[label.end() :].strip() else _looks_like_header
    return bool(reads(label.group(0))), start, offset


# A list item that opens with its own heading label, alone (`Requirements:` before an inline
# bullet) or ahead of its content (`Requirements: 8 years of experience.`). Either way it ends an
# earlier heading's reach; with content after it, it cannot hedge what follows, because the hedge
# test admits delimiters only between a heading and the clause it governs.
_LEADING_LABEL = re.compile(r"[^:\n]{1,60}:")

# A HEDGE heading whose hedge is followed by a section noun: `Preferred Qualifications:`,
# `Desired Skills:`. Replayed through the introducer as the full label, the noun is not a
# delimiter, so the hedge could never reach a bullet, and these are the commonest hedge headings
# there are. Closed on both words, anchored at both ends, so `Required and Preferred
# Qualifications:` and `Minimum Qualifications:` are not hedges.
_HEDGE_HEADING = re.compile(
    r"^[\s•‣●\-\*]*(?:preferred|desired|desirable|bonus|nice[\s-]to[\s-]have)"
    r"(?=(?:\s+(?:qualifications?|skills?|requirements?|experience|knowledge|abilities|"
    r"attributes|competencies))?\s*:?\s*$)",
    re.IGNORECASE,
)


# A FIELD label opening a list item (`- Experience: 5 years ...`). It names what the bar is
# about, not how binding it is, so a hedge heading reads through it; kept out of the hedge's
# introducer, it would break the delimiters-only chain and restore the bar. Closed, so
# `- Required: 5 years ...` is never read through.
_FIELD_LABEL = re.compile(
    r"(?:(?:total|work|professional|relevant|industry)\s+)?"
    r"(?:experience|education|degree|skills?|background|certifications?|training)\s*:\s*",
    re.IGNORECASE,
)


def _item_start(unit: str) -> int:
    """Where a governed item's own text starts: past its bullet and any field label."""
    lead = _BULLET_LEAD.match(unit).end()  # type: ignore[union-attr]
    field = _FIELD_LABEL.match(unit, lead)
    return lead if field is None else field.end()


def _heading_text(head: str) -> str:
    """The heading as its hedge reads: `Preferred Qualifications:` -> `Preferred:`.

    A PREFIX of the heading, never a rewrite, so an offset into it is an offset into the body's
    own heading and a span `_views` builds across it stays a slice of the stored body. Every
    family's own hedge vocabulary then decides, exactly as it does for `Preferred: 5 years`.
    """
    match = _HEDGE_HEADING.match(head)
    return head if match is None else f"{head[: match.end()]}:"


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
    current_key = prev_line = -1
    governed = listed = False
    prev_end = 0
    for index, (offset, unit) in enumerate(units):
        heading, line, key = _on_heading_line(text, offset, unit)
        if heading:
            if key != current_key:
                current, current_key = index, key
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


# The bullet `_SENTENCE_SPLIT` consumes before an inline item, so the item's own text no longer
# shows it. Same marker class as the splitter's bullet branch.
_INLINE_BULLET_BEFORE = re.compile(r"[•‣●\-\*]\s+$")


def _opens_item(text: str, offset: int) -> bool:
    """Whether the unit at `offset` starts a list item: a line, or an inline bullet."""
    return (
        offset == 0
        or text[offset - 1] == "\n"
        or _INLINE_BULLET_BEFORE.search(text[max(0, offset - 8):offset]) is not None
    )


def alternative_groups(
    text: str, units: list[tuple[int, str]], governing: list[int | None]
) -> list[str | None]:
    """For each unit joined to its neighbours by an explicit OR between lines, the group
    written as its inline twin (`arm or arm or arm`), else None.

    The link is a list item that is only `OR`, or one that opens with it. An item opens a line,
    or follows an inline bullet the splitter cut on (`… • OR Associate's Degree …`, one line
    holding the whole list, which is how posting 261677 states its ladder). It joins the units
    either side, never a heading, and never across one. The group is then read by each
    pattern's OWN alternative escapes, exactly as the one-line sentence would be: `or` stays
    out of `_CLAUSE_BOUNDARY`, and a list form waives nothing its inline twin would not.
    """
    groups: list[list[int] | None] = [None] * len(units)
    for index, (offset, unit) in enumerate(units):
        if not _opens_item(text, offset) or not _OR_LEAD.match(unit):
            continue
        before, after = index - 1, index + 1 if _or_only(unit) else index
        if before < 0 or after >= len(units) or _or_only(units[before][1]):
            continue
        if _or_only(units[after][1]) or governing[before] != governing[after]:
            continue
        if any(_on_heading_line(text, *units[i])[0] for i in (before, after)):
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

    "Nice to have:\n- 5 years" then drops exactly when "Nice to have: - 5 years" would. The
    caller passes `_heading_text`, so `Preferred Qualifications:` reads as `Preferred:`, and a
    field label opening the item (`- Experience: 5 years`) is read through (`_FIELD_LABEL`).
    """
    lead = _BULLET_LEAD.match(unit).end()  # type: ignore[union-attr]
    start = _item_start(unit)
    if start > lo:
        start = lead
    intro = f"{heading} {unit[:lead]}{unit[start:]}"
    shift = len(heading) + 1 - (start - lead)
    lo, hi = lo + shift, hi + shift
    return _suppressed(
        intro, lo, hi, hedges,
        bounds=_clause_bounds(intro, lo, hi), introducer=True, aside_owned=True,
    )


def _reading(values: dict[str, str]) -> frozenset[tuple[str, str]]:
    """A detection's captures, each `_alt` group under the name it stands in for.

    One regex cannot name a group twice, so a pattern's second layout captures the same value
    as `years_alt` (the resolver reads either). A bullet's own view and its heading view can
    read one bar through the two layouts, and this is what says it is the same bar.
    """
    return frozenset((name.removesuffix("_alt"), value) for name, value in values.items())


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
        head_offset, head = units[heading][0], _heading_text(units[heading][1])
        lead = _item_start(unit)
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
    # Tail-hedged bars carried as their family's `preferred` twin, merged after the loop so a
    # twin that already reached the same hedge is not written twice.
    carried: list[Detection] = []
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
        twins = {pattern.id: pattern for pattern in family.patterns}
        for pattern in family.patterns:
            if (units := units_by_scope.get(pattern.scope)) is None:
                units = units_by_scope[pattern.scope] = split_units(body_text, pattern.scope)
                governing = governing_headings(body_text, units)
                context_by_scope[pattern.scope] = (
                    governing, alternative_groups(body_text, units, governing)
                )
            governing, alternatives = context_by_scope[pattern.scope]
            # What each unit's OWN view appended, with its absolute span, so its heading view
            # adds only a new reading.
            own: dict[tuple[int, frozenset[tuple[str, str]]], list[tuple[int, int]]] = {}
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
                        _heading_text(units[heading][1]), unit, lo, hi,
                        pattern.suppressed_by_unit,
                    ):
                        continue
                    if _suppressed(
                        unit, lo, hi, pattern.subject_suppressors,
                        bounds=bounds, before_only=True,
                    ):
                        continue
                    if pattern.hedged_by_tail and (
                        end := _hedged_tail(unit, lo, hi, pattern.hedged_by_tail)
                    ) is not None:
                        if pattern.hedged_as is not None:
                            carried.append(
                                Detection(
                                    family=family.id,
                                    pattern=twins[pattern.hedged_as],
                                    span=(at(lo), at(end)),
                                    values={k: v for k, v in match.groupdict().items() if v},
                                )
                            )
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
                    values = {name: value for name, value in match.groupdict().items() if value}
                    # Checked after every drop, so a suppressed own-view match hides nothing.
                    # "Preferred Qualifications:\n- 5 years of experience preferred." otherwise
                    # wrote its one preferred bar twice, once per view (T163).
                    # The same bar means the same captures AND the same text: the heading
                    # view's bullet-side part must overlap the own-view row. Equal captures
                    # alone would stand down a different bar in the same bullet, e.g. "3-5
                    # years ...; 3-7 years ... preferred." (both capture a lower bound of 3).
                    reading = (index, _reading(values))
                    if join is None:
                        own.setdefault(reading, []).append((at(lo), at(hi)))
                    elif any(
                        start < at(hi) and at(join) < end for start, end in own.get(reading, ())
                    ):
                        continue
                    found.append(
                        Detection(
                            family=family.id,
                            pattern=pattern,
                            span=(at(lo), at(hi)),
                            values=values,
                            abstained=abstained,
                        )
                    )
    for detection in carried:
        if not any(
            other.pattern is detection.pattern
            and other.span[0] < detection.span[1]
            and detection.span[0] < other.span[1]
            for other in found
        ):
            found.append(detection)
    order_of = {family.id: index for index, family in enumerate(catalog.families)}
    found.sort(key=lambda d: (order_of[d.family], d.span[0]))
    return found
