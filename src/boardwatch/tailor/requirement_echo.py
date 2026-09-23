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

  structural       (a) the bullet does NOT open with a past-tense/gerund action verb --
                    checked as "ends in ed/ing" (regular verbs) OR is one of a small
                    closed set of common IRREGULAR past-tense résumé openers
                    (`_IRREGULAR_ACTION_VERBS`: Built, Grew, Drove, ...), which do not
                    end in "ed"/"ing" as literal characters -- AND
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

from boardwatch.eligibility.detect import qualifications_span, split_units
from boardwatch.tailor.overmatch import _ngrams, _tokens
from boardwatch.tailor.register import qualification_cue_reasons
from boardwatch.tailor.rewrite.verb_diversity import _opening_verb

REQUIREMENT_ECHO_VERSION = "p4-requirement-echo-1"

_ECHO_NGRAM = 4

# The qualifications-heading vocabulary and `qualifications_span` live in
# `eligibility/detect.py`, which bounds heading context with them, so ENGINE_VERSION covers
# any edit to them.


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


# Common IRREGULAR past-tense résumé-bullet openers -- these do not end in "ed"/"ing" as
# literal characters (unlike "Built"'s regular cousins "Designed"/"Reduced"), so the
# suffix check alone misses them and treats a genuine completed-action opener as a
# capability claim. Closed, greppable, tunable set; no POS tagger.
_IRREGULAR_ACTION_VERBS: frozenset[str] = frozenset(
    {
        "built", "ran", "drove", "wrote", "made", "grew", "sold", "set", "cut", "won",
        "held", "kept", "chose", "took", "gave", "began", "brought", "met", "sent",
        "spent", "taught", "oversaw", "rebuilt", "drew", "rose", "spoke", "led",
    }
)


def _opens_with_action_verb(bullet: str) -> bool:
    verb = _opening_verb(bullet)
    return verb.endswith("ed") or verb.endswith("ing") or verb in _IRREGULAR_ACTION_VERBS


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
