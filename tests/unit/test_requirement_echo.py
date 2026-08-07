"""Tests for the deterministic requirement-echo guard (P4 item 3b). Pure
`(bullet, qualification_sentences, canonical, qualification_cues) -> reasons` predicate,
plus the qualifications-span header heuristic it corroborates against. Mirrors
test_overmatch.py's shape -- no Resume/lane fixtures needed for these.

The AND-gate (structural (a)-AND-(b), corroboration via a 4-gram sharing a non-canonical
token) is exactly what makes this guard hard to get right without false positives, so most
of this file is the red-team set from the buildable spec: genuine accomplishment bullets
that legitimately share vocabulary with a JD and must NOT flag.
"""

from __future__ import annotations

from boardwatch.tailor.requirement_echo import (
    REQUIREMENT_ECHO_VERSION,
    jd_qualification_sentences,
    qualifications_span,
    requirement_echo_reasons,
)

_CUES = (
    "experience with",
    "experience building",
    "experience in",
    "knowledge of",
    "familiarity with",
    "ability to",
    "proven ability to",
    "strong understanding of",
    "understanding of",
    "years of experience",
)
_EMPTY: frozenset[str] = frozenset()


def test_requirement_echo_version_is_defined():
    assert isinstance(REQUIREMENT_ECHO_VERSION, str)
    assert REQUIREMENT_ECHO_VERSION == "p4-requirement-echo-1"


# -- requirement_echo_reasons: the MUST FLAG case -----------------------------------


def test_paraphrase_echo_of_a_jd_qualification_is_flagged():
    bullet = "Experience with building scalable REST APIs using Python and Django"
    qual = "You have experience building scalable REST APIs in Python or a similar framework."
    reasons = requirement_echo_reasons(
        bullet, [qual], canonical=_EMPTY, qualification_cues=_CUES
    )
    assert len(reasons) == 1
    assert "requirement echo" in reasons[0]


# -- requirement_echo_reasons: the red-team MUST NOT FLAG set -----------------------


def test_action_verb_opener_is_never_flagged_even_with_a_qualification_cue():
    """(a) fails: "Built" is a completed-action opener, even though the bullet contains
    no cue here either -- kept simple to isolate the opener check."""
    bullet = "Built scalable REST APIs in Python, cutting p99 latency 40%"
    qual = "You have experience building scalable REST APIs in Python or a similar framework."
    assert (
        requirement_echo_reasons(bullet, [qual], canonical=_EMPTY, qualification_cues=_CUES)
        == []
    )


def test_headline_fragment_with_no_register_cue_is_not_flagged():
    """(b) fails: no qualification-register phrase, even though the opener is a bare
    noun phrase (a) would otherwise satisfy -- this is the false-positive the deepseek
    review's AND-gate fix (vs. the grounding doc's ambiguous OR) exists to prevent."""
    bullet = "Scalable data pipelines serving 1M requests per day"
    qual = "You have experience building scalable data pipelines at high throughput."
    assert (
        requirement_echo_reasons(bullet, [qual], canonical=_EMPTY, qualification_cues=_CUES)
        == []
    )


def test_action_verb_opener_beats_a_shared_generic_word_run():
    """"Led" ends in "ed" -- (a) fails -- even though the bullet shares ordinary English
    words with a JD qualification sentence. Structural must gate on the OPENER, not on
    whether generic vocabulary happens to overlap."""
    bullet = "Led a team building scalable systems that reduced cost 40%"
    qual = "You have experience building scalable systems that reduce operating cost."
    assert (
        requirement_echo_reasons(bullet, [qual], canonical=_EMPTY, qualification_cues=_CUES)
        == []
    )


def test_pure_canonical_tech_overlap_never_corroborates():
    """Structural (a) AND (b) both fire, but the ONLY shared 4-gram is pure tech
    vocabulary -- tech overlap is what GOOD tailoring produces on purpose (item 2's
    canonical-vocab re-spelling), so it must never corroborate an echo."""
    bullet = "Ability to use Python Django React Node daily"
    qual = "Our stack uses Python Django React Node in production daily."
    canonical = frozenset({"python", "django", "react", "node"})
    assert (
        requirement_echo_reasons(bullet, [qual], canonical=canonical, qualification_cues=_CUES)
        == []
    )


def test_pure_canonical_tech_overlap_would_flag_without_the_non_canonical_requirement():
    """Mutation check for the corroboration signal's non-canonical-token requirement:
    the SAME fixture as the test above, but with an empty canonical set -- proving the
    shared 4-gram is real and would corroborate if the exclusion were dropped."""
    bullet = "Ability to use Python Django React Node daily"
    qual = "Our stack uses Python Django React Node in production daily."
    assert (
        requirement_echo_reasons(bullet, [qual], canonical=_EMPTY, qualification_cues=_CUES)
        != []
    )


def test_shared_three_gram_alone_does_not_corroborate():
    """Structural (a) AND (b) both fire, and the bullet shares a 3-word run with the
    qualification sentence, but no 4-gram -- below the corroboration threshold, so this
    must stay clean. (Mutation check: widening the threshold to 3 would flag this.)"""
    bullet = "Familiarity with scalable microservice deployments across teams"
    qual = "You should have familiarity with scalable containerized deployments in production."
    assert (
        requirement_echo_reasons(bullet, [qual], canonical=_EMPTY, qualification_cues=_CUES)
        == []
    )


def test_and_gate_structural_alone_without_a_register_cue_does_not_flag():
    """Corroboration fires (a shared non-canonical 4-gram exists) and the opener is a
    bare noun phrase ((a) alone would fire), but there is no qualification-register cue
    ((b) fails) -- the AND-gate must not flag on (a) alone. (Mutation check: an OR-gate
    would flag this.)"""
    bullet = "Scalable data pipelines processing large customer datasets nightly"
    qual = "You will build scalable data pipelines processing large volumes of data."
    assert (
        requirement_echo_reasons(bullet, [qual], canonical=_EMPTY, qualification_cues=_CUES)
        == []
    )


def test_empty_qualification_sentences_never_flags():
    """A JD whose qualifications span could not be located (no header, or no sentences
    within it) supplies no corroboration material -- fail-safe silent miss, never a
    false positive, regardless of how echo-y the bullet reads."""
    bullet = "Experience with building scalable REST APIs using Python and Django"
    assert requirement_echo_reasons(bullet, [], canonical=_EMPTY, qualification_cues=_CUES) == []


def test_empty_qualification_cues_never_flags():
    bullet = "Experience with building scalable REST APIs using Python and Django"
    qual = "You have experience building scalable REST APIs in Python or a similar framework."
    assert requirement_echo_reasons(bullet, [qual], canonical=_EMPTY, qualification_cues=()) == []


# -- qualifications_span -------------------------------------------------------


def test_requirements_header_slices_the_span_correctly():
    body = (
        "About the role\n"
        "We build great things.\n"
        "\n"
        "Requirements:\n"
        "3+ years of experience with Python\n"
        "Experience with distributed systems\n"
        "Bachelors degree preferred\n"
        "Benefits:\n"
        "Health insurance\n"
        "401k match\n"
    )
    span = qualifications_span(body)
    assert span == [
        "3+ years of experience with Python",
        "Experience with distributed systems",
        "Bachelors degree preferred",
    ]


def test_no_header_returns_an_empty_span():
    body = "We are a fast-growing company looking for a great engineer to join our team."
    assert qualifications_span(body) == []


def test_qualifications_header_runs_to_eof_when_no_later_header_exists():
    body = "Qualifications:\nExperience with Python\nAbility to work independently\n"
    span = qualifications_span(body)
    assert span == ["Experience with Python", "Ability to work independently"]


def test_jd_qualification_sentences_is_empty_when_span_is_empty():
    assert jd_qualification_sentences("No headers here at all, just prose.") == []


def test_jd_qualification_sentences_splits_the_span_into_sentences():
    body = (
        "Requirements:\n"
        "You have experience building scalable systems. "
        "You have strong understanding of distributed databases.\n"
    )
    sentences = jd_qualification_sentences(body)
    assert len(sentences) == 2
    assert any("scalable systems" in s for s in sentences)
    assert any("distributed databases" in s for s in sentences)


def test_no_header_means_a_would_be_echo_bullet_still_does_not_flag():
    """End-to-end fail-safe check: a JD with no recognizable qualifications header
    supplies [] to requirement_echo_reasons via jd_qualification_sentences, so even the
    canonical MUST-FLAG bullet from this file's first test cannot be flagged."""
    body = "We are a fast-growing company looking for a great engineer to join our team."
    bullet = "Experience with building scalable REST APIs using Python and Django"
    sentences = jd_qualification_sentences(body)
    assert (
        requirement_echo_reasons(bullet, sentences, canonical=_EMPTY, qualification_cues=_CUES)
        == []
    )
