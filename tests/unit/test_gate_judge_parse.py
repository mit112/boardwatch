"""`gate_judge._parse_verdicts` binds a verdict to its lead by LABEL, never by position or count.

Runs 45 and 48 (2026-09-09, 2026-09-12) each failed a whole batch of 13 leads open because the
model answered 12 — "expected a JSON array of 13 verdicts, got 12". Every verdict names its lead
and `apply_gate_verdicts` binds on that name, so twelve sound verdicts were thrown away for one
skipped lead. Only the skipped lead is unjudged now; a response that names a lead the batch did
not contain, names one twice, or answers more than it was asked still fails the whole batch open.
"""

from __future__ import annotations

import json

import pytest

from boardwatch.llm.gate_judge import _parse_verdicts


def _stdout(verdicts: list[dict[str, object]]) -> str:
    return json.dumps({"is_error": False, "result": json.dumps(verdicts)})


def _verdict(label: str) -> dict[str, object]:
    return {"label": label, "decision": "eligible", "reason": None, "evidence": "",
            "confidence": "high"}


def test_a_skipped_lead_is_reported_missing_and_the_rest_are_kept() -> None:
    """RED before: `ValueError: expected a JSON array of 3 verdicts, got 2`."""
    verdicts, missing = _parse_verdicts(_stdout([_verdict("1"), _verdict("3")]), ["1", "2", "3"])
    assert [v.label for v in verdicts] == ["1", "3"]
    assert missing == ("2",)


def test_a_complete_answer_reports_nothing_missing() -> None:
    verdicts, missing = _parse_verdicts(_stdout([_verdict("2"), _verdict("1")]), ["1", "2"])
    assert sorted(v.label for v in verdicts) == ["1", "2"]
    assert missing == ()


@pytest.mark.parametrize(
    ("answered", "why"),
    [
        (["1", "9"], "a label the batch never asked about"),
        (["1", "1"], "the same label answered twice"),
        (["1", "2", "3"], "more verdicts than leads"),
    ],
)
def test_an_answer_this_stage_cannot_trust_fails_the_whole_batch_open(
    answered: list[str], why: str
) -> None:
    with pytest.raises(ValueError):
        _parse_verdicts(_stdout([_verdict(label) for label in answered]), ["1", "2"])
