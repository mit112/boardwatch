"""P5b oracle judge — provenance gate + best-effort span (task 1 foundations).

Pins the calibration that motivates this port: job-apps' original judge.py used a
`{2,}`-char tokenizer and a >=4-total-token floor, which drops terse hard-stop sentences
like "U.S. citizenship required." (the `{2,}` regex erases "U.S." down to single-letter
tokens "u"/"s", leaving too few tokens to clear the floor). `resolve_provenance` here uses
a min-1-char tokenizer and a lowered total-token floor so those clearance/citizenship
stops still pass, while an all-stopword span ("now or in the") still fails on the content
floor. See oracle.py's module docstring and D-010/D-066/D-067 for the design record.
"""

from __future__ import annotations

from boardwatch.eligibility.oracle import resolve_provenance, span_of

JD = "About us. We are great. Active TS/SCI required. Apply now."


def test_provenance_accepts_verbatim_informative_span():
    assert resolve_provenance("Active TS/SCI required.", JD) is True


def test_provenance_accepts_terse_citizenship_stop():
    jd = "Role details. U.S. citizenship required. EOE."
    assert resolve_provenance("U.S. citizenship required.", jd) is True


def test_provenance_rejects_all_stopword_span():
    # the "now or in the" case: present verbatim but 0 content tokens
    assert resolve_provenance("now or in the", "work now or in the future") is False


def test_provenance_rejects_absent_span():
    assert resolve_provenance("no sponsorship offered", JD) is False


def test_provenance_matches_after_normalization_dash():
    jd = "We do not offer visa sponsorship—now or later."
    assert resolve_provenance("do not offer visa sponsorship-now or later", jd) is True


def test_span_of_returns_literal_offsets():
    s = span_of("Active TS/SCI required.", JD)
    assert s is not None and JD[s[0] : s[1]] == "Active TS/SCI required."


def test_span_of_tolerates_normalized_only_match():
    jd = "We do not offer visa sponsorship—now."
    # matches only after normalization -> no clean literal offset -> None (tolerated)
    assert span_of("do not offer visa sponsorship-now", jd) is None
