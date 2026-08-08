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

import json
from pathlib import Path

import pytest

from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.oracle import (
    JUDGING_POLICY,
    POLICY_VERSION,
    PROMPT_VERSION,
    OracleVerdict,
    OracleVerdictError,
    accept_oracle_verdict,
    apply_oracle_verdicts,
    build_label_request,
    is_allowed_reason,
    read_worksheet,
    resolve_provenance,
    span_of,
)

JD = "About us. We are great. Active TS/SCI required. Apply now."
CAT = load_rules(Path("/nonexistent"))  # bundled catalog


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


def _v(decision, reason=None, evidence="", confidence="high", label="x"):
    return OracleVerdict(
        label=label, decision=decision, reason=reason, evidence=evidence, confidence=confidence
    )


def test_ineligible_accepted_on_full_conjunction():
    a = accept_oracle_verdict(
        _v("ineligible", "clearance", "Active TS/SCI required.", "high"), JD, CAT
    )
    assert a.expected_verdict == "ineligible" and a.downgraded is False
    assert a.spans and JD[a.spans[0][0] : a.spans[0][1]] == "Active TS/SCI required."


def test_downgrade_out_of_catalog_reason():
    a = accept_oracle_verdict(
        _v("ineligible", "seniority_language", "Active TS/SCI required.", "high"), JD, CAT
    )
    assert a.expected_verdict == "uncertain" and a.downgraded is True


def test_downgrade_low_confidence():
    a = accept_oracle_verdict(
        _v("ineligible", "clearance", "Active TS/SCI required.", "medium"), JD, CAT
    )
    assert a.expected_verdict == "uncertain" and a.downgraded is True


def test_downgrade_unprovenanced_evidence():
    a = accept_oracle_verdict(_v("ineligible", "clearance", "no sponsorship here", "high"), JD, CAT)
    assert a.expected_verdict == "uncertain" and a.downgraded is True


def test_confidence_case_insensitive():
    a = accept_oracle_verdict(
        _v("ineligible", "clearance", "Active TS/SCI required.", "  HIGH "), JD, CAT
    )
    assert a.expected_verdict == "ineligible"


def test_eligible_passes_through_no_span():
    a = accept_oracle_verdict(_v("eligible"), JD, CAT)
    assert a.expected_verdict == "eligible" and a.spans == () and a.downgraded is False


def test_uncertain_passes_through():
    a = accept_oracle_verdict(_v("uncertain"), JD, CAT)
    assert a.expected_verdict == "uncertain" and a.downgraded is False


def test_bad_decision_raises():
    with pytest.raises(OracleVerdictError):
        accept_oracle_verdict(_v("move"), JD, CAT)


def test_is_allowed_reason_membership():
    assert is_allowed_reason("clearance", CAT) is True
    assert is_allowed_reason("role_family", CAT) is False
    assert is_allowed_reason(None, CAT) is False


def test_judging_policy_states_no_force_fit_rule():
    # H2: the no-force-fit rule must be present verbatim, not paraphrased away.
    assert (
        "If the JD states a decisive hard stop whose category is NOT one of the "
        "reason_catalog families, output `uncertain` — never force-fit it into a "
        "different family."
    ) in JUDGING_POLICY


def test_build_request_excludes_hint_includes_policy(tmp_path):
    ws = tmp_path / "candidates.jsonl"
    ws.write_text(
        json.dumps(
            {
                "label": "skip/x",
                "expected_verdict": None,
                "hint": "secret guess",
                "company": "Acme",
                "title": "SWE",
                "source": "u",
                "facts": {"total_years_experience": 1},
                "body_text": "JD body",
            }
        )
        + "\n"
        + json.dumps(
            {
                "label": "applied/y",
                "expected_verdict": "eligible",  # already labeled
                "facts": {},
                "body_text": "done",
            }
        )
        + "\n"
    )
    rows = read_worksheet(ws)
    assert len(rows) == 2  # includes the null-verdict row (load_labeled_set would drop it)
    req = build_label_request(rows, CAT, request_id="r1")
    assert req["request_id"] == "r1"
    assert req["policy"] == {"families": {f.id: "blocker" for f in CAT.families}}  # M3
    assert set(req["reason_catalog"]) == {f.id for f in CAT.families}
    assert req["policy_version"] and req["prompt_version"]
    items = req["items"]
    assert len(items) == 1 and items[0]["label"] == "skip/x"  # only unlabeled
    assert "hint" not in items[0]  # independence
    assert items[0]["facts"] == {"total_years_experience": 1}
    assert items[0]["bucket"] == "hard_stop"  # H1: derived from label prefix
    assert items[0]["jd_text"] == "JD body"


def test_build_request_marks_applied_as_hard_negative(tmp_path):
    ws = tmp_path / "c.jsonl"
    ws.write_text(
        json.dumps(
            {"label": "applied/z", "expected_verdict": None, "facts": {}, "body_text": "b"}
        )
        + "\n"
    )
    req = build_label_request(read_worksheet(ws), CAT, request_id="r")
    assert req["items"][0]["bucket"] == "hard_negative"  # H1: applied/ prefix


def _row(label, verdict=None, prov=None):
    r = {
        "label": label,
        "expected_verdict": verdict,
        "facts": {},
        "body_text": "Active TS/SCI required.",
        "hint": "h",
        "company": "C",
        "title": "T",
        "source": "s",
    }
    if prov:
        r["label_provenance"] = prov
        # the real writer always stamps both version fields together, so the
        # fixture must too — a fixture that only stamps one masks the strict
        # both-fields-must-match comparison in `_skip_row`.
        r["oracle_policy_version"] = "old"
        r["oracle_prompt_version"] = "old"
    return r


def test_apply_merges_and_preserves_columns():
    rows = [_row("skip/a")]
    v = [OracleVerdict("skip/a", "ineligible", "clearance", "Active TS/SCI required.", "high")]
    merged, res = apply_oracle_verdicts(rows, v, CAT)
    m = merged[0]
    assert m["expected_verdict"] == "ineligible" and m["label_provenance"] == "oracle"
    assert m["hint"] == "h" and m["company"] == "C" and m["title"] == "T"  # M5 survive
    assert m["source"] == "s" and m["facts"] == {}  # M5 survive
    assert m["oracle_policy_version"] == POLICY_VERSION
    assert res.labeled == 1 and res.by_verdict["ineligible"] == 1


def test_apply_idempotent_skips_current_version():  # M4
    rows = [_row("skip/a", "ineligible", prov="oracle")]
    rows[0]["oracle_policy_version"] = POLICY_VERSION  # already current
    rows[0]["oracle_prompt_version"] = PROMPT_VERSION  # already current
    v = [OracleVerdict("skip/a", "eligible", None, "", "high")]
    merged, res = apply_oracle_verdicts(rows, v, CAT)
    assert merged[0]["expected_verdict"] == "ineligible"  # untouched
    assert res.overwritten == 0


def test_apply_overwrites_stale_oracle_version():  # M4
    rows = [_row("skip/a", "ineligible", prov="oracle")]  # both version fields = "old"
    v = [OracleVerdict("skip/a", "eligible", None, "", "high")]
    merged, res = apply_oracle_verdicts(rows, v, CAT)
    assert merged[0]["expected_verdict"] == "eligible" and res.overwritten == 1


def test_apply_never_touches_audited():  # M4
    rows = [_row("skip/a", "ineligible", prov="audited")]
    v = [OracleVerdict("skip/a", "eligible", None, "", "high")]
    merged, res = apply_oracle_verdicts(rows, v, CAT)
    assert merged[0]["expected_verdict"] == "ineligible" and res.overwritten == 0


def test_apply_never_touches_human_label():  # M4 skip-condition 3
    # a hand label: non-null expected_verdict, no label_provenance at all (never
    # previously written by apply_oracle_verdicts) — must be skipped, not overwritten.
    rows = [_row("skip/a", "ineligible")]
    v = [OracleVerdict("skip/a", "eligible", None, "", "high")]
    merged, res = apply_oracle_verdicts(rows, v, CAT)
    assert merged[0]["expected_verdict"] == "ineligible"  # untouched
    assert res.overwritten == 0
    assert res.labeled == 0


def test_apply_flags_hard_negative_ineligible():  # H1
    rows = [_row("applied/a")]
    v = [OracleVerdict("applied/a", "ineligible", "clearance", "Active TS/SCI required.", "high")]
    merged, res = apply_oracle_verdicts(rows, v, CAT)
    assert res.hard_negative_ineligible == ("applied/a",)
