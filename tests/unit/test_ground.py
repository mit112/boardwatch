"""Adversarial suite for the grounding validator (D-P3: anti-fabrication core).

Every negative case sits beside a positive control in the same payload
(`test_fabricated_span_is_dropped_but_real_control_kept`), so a permissive
`ground()` that skipped the substring check would keep both spans and fail
that test. That locks the strict behaviour without any throwaway stub.
"""

import json

import pytest

import boardwatch.eligibility.ground as ground_module
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


def test_element_not_a_dict_is_dropped_not_global() -> None:
    # element-level problem: drops just that element, not the whole call.
    assert ground(JD, json.dumps(["minimum of 5 years"])) == []


def test_non_string_family_or_span_quote_is_dropped_not_global() -> None:
    # element-level problem: drops just that element, not the whole call.
    assert ground(JD, json.dumps([{"family": 1, "span_quote": "minimum of 5 years"}])) == []
    assert ground(JD, json.dumps([{"family": "degree", "span_quote": 5}])) == []


def test_first_occurrence_offsets_used_for_duplicate_substring() -> None:
    jd = "5 years. Later, 5 years again."
    out = ground(jd, json.dumps([{"family": "experience_years", "span_quote": "5 years"}]))
    assert len(out) == 1
    assert out[0].span == (0, 7)


def test_fail_closed_on_a_recursion_error_from_the_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`ground()` must fail closed on `RecursionError`, exactly as it does on malformed JSON.

    The fault is PATCHED IN rather than provoked with 20,000 nested brackets. That input was the
    original probe and it stopped working: CPython 3.14 no longer recurses in `json.loads` there,
    so the test's own precondition (`pytest.raises(RecursionError)`) failed and the test reported
    a broken guard when the guard was fine. A test that can only run on one interpreter is an
    environment check wearing an assertion's clothes.

    Patching `json.loads` AS SEEN BY `ground` keeps what the old test was actually for — that
    `RecursionError` is in the except tuple — on every interpreter. Mutation-checked: removing
    `RecursionError` from the tuple at `ground.py` makes this raise.
    """

    def raiser(_payload: str) -> object:
        raise RecursionError("maximum recursion depth exceeded while decoding a JSON object")

    monkeypatch.setattr(ground_module.json, "loads", raiser)
    assert ground(JD, "[]") == []


def test_broken_element_drops_only_itself() -> None:
    valid = {"family": "experience_years", "span_quote": "minimum of 5 years"}
    missing_span_quote = {"family": "degree"}
    not_a_dict = "oops"

    out_valid_then_broken = ground(JD, json.dumps([valid, missing_span_quote, not_a_dict]))
    assert [g.family for g in out_valid_then_broken] == ["experience_years"]

    out_broken_then_valid = ground(JD, json.dumps([not_a_dict, missing_span_quote, valid]))
    assert [g.family for g in out_broken_then_valid] == ["experience_years"]


def test_span_quote_at_end_of_jd() -> None:
    quote = "Security clearance is a plus."
    out = ground(JD, json.dumps([{"family": "clearance", "span_quote": quote}]))
    assert len(out) == 1
    start, end = out[0].span
    assert JD[start:end] == quote
