"""The fourth eligibility seam: the `eligibility label` oracle handshake (D-406).

The other three seams (deterministic preflight, final-gate request, final-gate apply) already
refuse an aggregator's rendered PAGE as an eligibility input. This one is the answer-key seam,
and it is the most dangerous of the four: a foreign body accepted here does not just misjudge one
posting, it writes a FALSE ground-truth row that every precision measurement is then scored
against. The reproduction below is the reviewer's own: `H1B Sponsor Likely` is jobright's own
derived label sitting inside what boardwatch froze as the JD, so the raw gate accepts
`ineligible(work_auth)` citing a third party's guess with a real span behind it — the one
keystone violation the evidence chain cannot detect after the fact.

These tests are written to FAIL against the pre-guard code: without the precondition,
`build_label_request` selects the foreign row and `apply_oracle_verdicts` persists the false
`ineligible`. They assert the guard mirrors the other three seams' refusal exactly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.oracle import (
    OracleVerdict,
    accept_oracle_verdict,
    apply_oracle_verdicts,
    build_label_request,
)
from tests.unit.test_lane_body_precondition import JOBRIGHT_PAGE

CAT = load_rules(Path("/nonexistent"))  # bundled catalog

# A clean employer body carrying an in-catalog hard stop — the CONTROL that proves the guard is
# not over-broad: a real JD still reaches the judge and still labels `ineligible`.
CLEAN_JD = "About us. We are great. Active TS/SCI required. Apply now."

# The reviewer's exact repro verdict: jobright's own derived `H1B Sponsor Likely` label, offered
# as `ineligible(work_auth)`. Against JOBRIGHT_PAGE the raw gate accepts it (span [262,280],
# downgraded=0) — which is precisely why the precondition, not the gate, has to stop it.
FOREIGN_INELIGIBLE = OracleVerdict(
    label="hard_stop/jobright",
    decision="ineligible",
    reason="work_auth",
    evidence="H1B Sponsor Likely",
    confidence="high",
)


def _foreign_row(
    label: str, *, verdict: str | None = None, prov: str | None = None
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "label": label,
        "expected_verdict": verdict,
        "facts": {},
        "body_text": JOBRIGHT_PAGE,
    }
    if prov:
        row["label_provenance"] = prov
        row["oracle_policy_version"] = "old"
        row["oracle_prompt_version"] = "old"
    return row


def test_the_raw_gate_alone_would_accept_the_foreign_ineligible() -> None:
    """The danger is real, stated where the fix can be seen: the four-ANDed ineligible-gate, run
    on jobright's page, produces `ineligible(work_auth)` citing `H1B Sponsor Likely`. The
    precondition is the ONLY thing between this and a false answer-key row."""
    accepted = accept_oracle_verdict(FOREIGN_INELIGIBLE, JOBRIGHT_PAGE, CAT)
    assert accepted.expected_verdict == "ineligible"
    assert accepted.downgraded is False
    assert accepted.spans == ((262, 280),)
    assert JOBRIGHT_PAGE[262:280] == "H1B Sponsor Likely"


def test_build_label_request_refuses_a_foreign_body_but_keeps_a_clean_one() -> None:
    """SEND boundary: the foreign page must never reach the judge; a real JD still does."""
    rows = [
        _foreign_row("hard_stop/jobright"),
        {"label": "hard_stop/clean", "expected_verdict": None, "facts": {}, "body_text": CLEAN_JD},
    ]
    req = build_label_request(rows, CAT, request_id="r1")
    labels = [item["label"] for item in req["items"]]
    assert labels == ["hard_stop/clean"], "the foreign body must not be sent to the judge"


def test_apply_oracle_verdicts_refuses_to_write_a_foreign_ineligible() -> None:
    """WRITE boundary, the exact repro: a fresh unlabeled foreign row named by the judge's
    `ineligible(work_auth)` verdict must NOT become an answer-key row."""
    rows = [_foreign_row("hard_stop/jobright")]
    merged, res = apply_oracle_verdicts(rows, [FOREIGN_INELIGIBLE], CAT)
    assert merged[0]["expected_verdict"] is None, "a foreign body must never be labeled ineligible"
    assert res.labeled == 0
    assert "ineligible" not in res.by_verdict


def test_apply_oracle_verdicts_refuses_a_stale_hand_authored_foreign_verdict() -> None:
    """WRITE boundary, the stale/hand-authored case: a verdicts file may name a foreign-body row
    that `build_label_request` never selected. The write side must refuse it independently, so a
    stale `oracle` row is not re-judged into a fresh false `ineligible`."""
    rows = [_foreign_row("hard_stop/jobright", verdict="uncertain", prov="oracle")]
    merged, res = apply_oracle_verdicts(rows, [FOREIGN_INELIGIBLE], CAT)
    assert merged[0]["expected_verdict"] == "uncertain", "must not be overwritten to ineligible"
    assert res.labeled == 0
    assert res.overwritten == 0


def test_apply_oracle_verdicts_still_labels_a_clean_employer_body() -> None:
    """The control: the guard does not eat the corpus — a real JD's ineligible still persists."""
    rows: list[dict[str, Any]] = [
        {"label": "hard_stop/clean", "expected_verdict": None, "facts": {}, "body_text": CLEAN_JD}
    ]
    verdict = OracleVerdict(
        "hard_stop/clean", "ineligible", "clearance", "Active TS/SCI required.", "high"
    )
    merged, res = apply_oracle_verdicts(rows, [verdict], CAT)
    assert merged[0]["expected_verdict"] == "ineligible"
    assert res.by_verdict["ineligible"] == 1
