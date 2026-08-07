"""Tests for the deterministic overmatch (verbatim-lift / unusual-caps) guard (P4 item 1,
D-047/D-048). Ported near-verbatim from job-apps `resume_tailor/overmatch.py`; the one
change is that `canonical` is an injected frozenset, not a module-level vocab import.
"""

from boardwatch.tailor.overmatch import OVERMATCH_VERSION, overmatch_reasons

_EMPTY: frozenset[str] = frozenset()


def test_overmatch_version_is_defined():
    assert isinstance(OVERMATCH_VERSION, str)
    assert OVERMATCH_VERSION == "p4-overmatch-1"


def test_clean_rewrite_is_empty():
    jd = "We are looking for a backend engineer with strong Python skills and API design experience."
    rewrite = "Built REST APIs in Python for a growing backend team"
    assert overmatch_reasons(rewrite, jd, canonical=_EMPTY) == []


def test_verbatim_seven_gram_lift_is_flagged():
    jd = "You will design and build scalable distributed systems using modern cloud infrastructure daily"
    # Lifts the 7-token span "design and build scalable distributed systems using" verbatim.
    rewrite = "Helped design and build scalable distributed systems using open tools"
    reasons = overmatch_reasons(rewrite, jd, canonical=_EMPTY)
    assert len(reasons) == 1
    assert "verbatim 7-gram lifted from JD" in reasons[0]
    assert "design and build scalable distributed systems using" in reasons[0]


def test_six_token_overlap_is_the_clean_boundary():
    jd = "You will design and build scalable distributed systems using modern cloud infrastructure daily"
    # Only 6 tokens overlap ("design and build scalable distributed systems") -- one token
    # short of the default min_ngram=7, so this must NOT be flagged.
    rewrite = "Helped design and build scalable distributed systems for a small team"
    assert overmatch_reasons(rewrite, jd, canonical=_EMPTY) == []


def test_studlycaps_token_copied_from_jd_is_flagged():
    jd = "Experience with our in-house FooBarWidget platform is required for this role"
    rewrite = "Maintained the FooBarWidget platform used by internal teams"
    reasons = overmatch_reasons(rewrite, jd, canonical=_EMPTY)
    assert len(reasons) == 1
    assert "copies JD's unusual capitalization of non-canonical term" in reasons[0]
    assert "FooBarWidget" in reasons[0]


def test_allcaps_token_copied_from_jd_is_flagged():
    jd = "Familiarity with our internal ZORPUS reporting system is a plus"
    rewrite = "Used the ZORPUS reporting system to track team output"
    reasons = overmatch_reasons(rewrite, jd, canonical=_EMPTY)
    assert len(reasons) == 1
    assert "ZORPUS" in reasons[0]


def test_same_token_exempt_when_in_canonical():
    jd = "Experience with GraphQL and PostgreSQL is strongly preferred for this position"
    rewrite = "Built GraphQL APIs backed by PostgreSQL for production workloads"
    canonical = frozenset({"graphql", "postgresql"})
    assert overmatch_reasons(rewrite, jd, canonical=canonical) == []


def test_titlecase_or_lowercase_copy_is_clean():
    jd = "Our Platform team owns the checkout service end to end for the whole company"
    rewrite = "Worked closely with the Platform team on checkout reliability improvements"
    assert overmatch_reasons(rewrite, jd, canonical=_EMPTY) == []


def test_unusual_caps_must_be_copied_verbatim_not_just_case_insensitively():
    """The JD's own casing must match exactly. If the JD spells a term lowercase and the
    rewrite renders it as StudlyCaps, that capitalization is the writer's own choice, not a
    copy of anything unusual in the JD -- must stay clean."""
    jd = "Experience with our foobarwidget platform is required for this role"
    rewrite = "Maintained the FooBarWidget platform used by internal teams"
    assert overmatch_reasons(rewrite, jd, canonical=_EMPTY) == []


def test_min_ngram_is_configurable():
    jd = "alpha bravo charlie delta echo foxtrot golf hotel"
    rewrite = "alpha bravo charlie delta echo foxtrot golf india"
    # 7-token overlap ("alpha bravo charlie delta echo foxtrot golf") at the default n=7.
    assert overmatch_reasons(rewrite, jd, canonical=_EMPTY) != []
    # Raising min_ngram past the overlap length must clear it.
    assert overmatch_reasons(rewrite, jd, canonical=_EMPTY, min_ngram=8) == []
