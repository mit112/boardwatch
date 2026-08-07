"""Deterministic requirement-echo guard (P4 item 3b): a Tier-B rewrite that RESTATES a JD
qualification instead of describing real work -- "Experience with building scalable REST
APIs using Python and Django" echoing a JD's "You have experience building scalable REST
APIs in Python or a similar framework". Item 1's `overmatch.py` already catches VERBATIM
lift (a shared 7-gram); this catches the sub-7-gram PARAPHRASE overmatch is silent on.
No model call. Fail-safe: a flag reverts the bullet to Tier-A, same shape as every other
craft/register/lift guard in `rewrite/lane.py`.

See `.superpowers/sdd/p4-craft/item3b-requirement-echo-design.md` (the buildable spec) and
`item3-guard-extensions-design.md` §2d (background rationale).

AND-gate, both signals required to flag:

  structural       (a) the bullet does NOT open with a past-tense/gerund action verb, AND
                    (b) it contains a qualification-register phrase ("experience with",
                        "knowledge of", ...) from register.yaml's `qualification_cues`.
  corroboration     the bullet shares at least one 4-gram (4 consecutive lowercased word
                    tokens, same tokenizer as `overmatch.py`) with SOME sentence from the
                    JD's qualifications section, where at least one of the four tokens is
                    NOT in the canonical tech vocabulary -- pure tech-token overlap is
                    expected from good tailoring and must never corroborate.

Signature note (build-time resolution, recorded here since the buildable spec's signature
omits it): `requirement_echo_reasons` takes `qualification_cues` as an explicit parameter,
matching every other pure predicate in this guard family (`overmatch_reasons`'s
`canonical`, `banned_register_reasons`'s `banned_phrases`) -- the catalog is caller-supplied
data, not something this module loads itself, so the function stays pure/no-I/O and
independently testable without `register.yaml`.
"""

from __future__ import annotations

import re

from boardwatch.eligibility.detect import split_units
from boardwatch.tailor.overmatch import _ngrams, _tokens
from boardwatch.tailor.register import qualification_cue_reasons
from boardwatch.tailor.rewrite.verb_diversity import _opening_verb

REQUIREMENT_ECHO_VERSION = "p4-requirement-echo-1"

_ECHO_NGRAM = 4

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
# qualifications heading specifically says): short, no sentence-ending punctuation, every
# significant word capitalized. Over-matching here only SHRINKS the span, which is the
# fail-safe direction (less corroboration material, never more).
_ANY_HEADER = re.compile(r"^[A-Za-z][A-Za-z /&'-]{0,58}:?$")


def _looks_like_header(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if _QUAL_HEADER.match(stripped):
        return True
    if not _ANY_HEADER.match(stripped):
        return False
    words = stripped.rstrip(":").split()
    return bool(words) and len(words) <= 6 and all(w[0].isupper() for w in words if w[0].isalpha())


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


def jd_qualification_sentences(body_text: str) -> list[str]:
    """`qualifications_span` sliced into sentences by REUSING `eligibility/detect.py`'s
    sentence splitter (already handles abbreviation dots, bullet markers, newlines --
    reimplementing that here would be duplicated, worse-tested code for a solved
    problem). `[]` whenever the span is empty. Named distinctly from
    `requirement_echo_reasons`'s `qualification_sentences` PARAMETER (the buildable
    spec's exact name for that argument) to avoid one identifier meaning two things in
    this module."""
    span = qualifications_span(body_text)
    if not span:
        return []
    text = "\n".join(span)
    return [unit_text for _offset, unit_text in split_units(text, scope="sentence")]


def _opens_with_action_verb(bullet: str) -> bool:
    verb = _opening_verb(bullet)
    return verb.endswith("ed") or verb.endswith("ing")


def requirement_echo_reasons(
    bullet: str,
    qualification_sentences: list[str],
    *,
    canonical: frozenset[str],
    qualification_cues: tuple[str, ...],
) -> list[str]:
    """Empty == clean. See module docstring for the AND-gate this implements."""
    if not qualification_sentences or not qualification_cues:
        return []  # corroboration/structural material unavailable -- cannot flag

    # Structural: (a) AND (b).
    if _opens_with_action_verb(bullet):
        return []  # (a) fails -- reads like a completed action, not a capability claim
    cue_hits = qualification_cue_reasons(bullet, qualification_cues)
    if not cue_hits:
        return []  # (b) fails -- no qualification-register phrasing

    # Corroboration: a shared 4-gram with a qualification sentence, containing at least
    # one token NOT in the canonical tech vocabulary (pure tech overlap is expected from
    # good tailoring and must never corroborate).
    bullet_grams = _ngrams(_tokens(bullet), _ECHO_NGRAM)
    if not bullet_grams:
        return []
    for sentence in qualification_sentences:
        shared = bullet_grams & _ngrams(_tokens(sentence), _ECHO_NGRAM)
        for gram in shared:
            if any(tok not in canonical for tok in gram):
                span = " ".join(gram)
                return [
                    f"requirement echo: shares '{span}' with a JD qualification "
                    f"sentence ({cue_hits[0]})"
                ]
    return []
