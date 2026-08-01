"""Adversarial suite for the grounding validator (D-P3: anti-fabrication core).

Every negative case sits beside a positive control in the same payload
(`test_fabricated_span_is_dropped_but_real_control_kept`), so a permissive
`ground()` that skipped the substring check would keep both spans and fail
that test. That locks the strict behaviour without any throwaway stub.
"""

import json

from boardwatch.eligibility.ground import ground

JD = "We require a minimum of 5 years of experience. Security clearance is a plus."


def test_grounded_span_present_is_kept() -> None:
    out = ground(JD, json.dumps([{"family": "experience_years", "span_quote": "minimum of 5 years"}]))
    assert len(out) == 1 and out[0].family == "experience_years"
    assert JD[out[0].span[0] : out[0].span[1]] == "minimum of 5 years"


def test_fabricated_span_is_dropped_but_real_control_kept() -> None:
    raw = json.dumps(
        [
            {"family": "degree", "span_quote": "PhD in astrophysics required"},  # not in JD -> drop
            {"family": "experience_years", "span_quote": "5 years of experience"},  # in JD -> keep
        ]
    )
    out = ground(JD, raw)
    assert [g.family for g in out] == ["experience_years"]


def test_unknown_family_becomes_other_not_dropped() -> None:
    out = ground(JD, json.dumps([{"family": "salary", "span_quote": "Security clearance is a plus"}]))
    assert len(out) == 1 and out[0].family == "other"


def test_fail_closed_on_malformed_and_empty() -> None:
    assert ground(JD, "not json") == []
    assert ground(JD, "") == []
    assert ground(JD, json.dumps([{"family": "degree"}])) == []  # missing span_quote
    assert ground(JD, json.dumps([{"family": "degree", "span_quote": ""}])) == []  # empty span_quote


def test_broken_baseline_permissive_stub_would_fail() -> None:
    # Non-vacuity: a validator that skips the substring check keeps the fabricated span.
    # The strict validator drops it, which also is what keeps the control test above
    # discriminating rather than vacuous.
    raw = json.dumps([{"family": "degree", "span_quote": "PhD in astrophysics required"}])
    assert ground(JD, raw) == []


def test_fail_closed_when_top_level_is_not_a_list() -> None:
    assert ground(JD, json.dumps({"family": "degree", "span_quote": "minimum of 5 years"})) == []


def test_fail_closed_when_element_is_not_a_dict() -> None:
    assert ground(JD, json.dumps(["minimum of 5 years"])) == []


def test_fail_closed_on_non_string_family_or_span_quote() -> None:
    assert ground(JD, json.dumps([{"family": 1, "span_quote": "minimum of 5 years"}])) == []
    assert ground(JD, json.dumps([{"family": "degree", "span_quote": 5}])) == []


def test_first_occurrence_offsets_used_for_duplicate_substring() -> None:
    jd = "5 years. Later, 5 years again."
    out = ground(jd, json.dumps([{"family": "experience_years", "span_quote": "5 years"}]))
    assert len(out) == 1
    assert out[0].span == (0, 7)
