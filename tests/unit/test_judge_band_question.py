"""T188 (DESIGN-T183 D1/J1): the judge's `seniority_fit` question is asked against the profile's
`target_seniority_band`, and not asked at all when the band is `any`.

Before this the question was always "is this an entry-level / new-grad / early-career role", so a
mid or senior tenant's leads were held for reading senior, and a tenant who declared no band was
asked about entry level anyway.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy import Engine, select, update

from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.oracle import build_label_request, judging_policy
from boardwatch.llm import gate_judge
from boardwatch.llm.gate_judge import _parse_verdicts, run_gate_stage
from boardwatch.rank.tenant_assumptions import ungrounded_reasons
from boardwatch.store import tables
from tests.unit.test_gate_judge_parse import _Lead, _seed, _settings, _stdout, _store, _verdict

CAT = load_rules(Path("/nonexistent"))

#: sha256 of `oracle.JUDGING_POLICY` as shipped before T188 (prompt `p5-oracle-1`).
_PRE_T188_POLICY_SHA256 = "ac1f4ae949e9055675448f2f9ee240953172675572f0b89fe6d969639c619456"
#: The one sentence of that prompt that named a band.
_PRE_T188_BAND_SENTENCE = (
    "is this an entry-level / new-grad / early-career role\n"
    "for a candidate with the `facts`' years of experience?"
)
_ENTRY_BAND_SENTENCE = (
    "is this role at or below the candidate's target seniority band, `entry`\n"
    "(entry-level / new-grad / early-career), for a candidate with the `facts`' years of "
    "experience?"
)


def test_the_entry_band_prompt_is_the_old_prompt_but_for_its_band_sentence() -> None:
    """CONTROL for the owner's band (`entry`, the value every entry-band test fixture seeds): put
    the old sentence back and the rendered prompt is byte-identical to the pre-T188 one."""
    rendered = judging_policy("entry")
    assert rendered.count(_ENTRY_BAND_SENTENCE) == 1
    restored = rendered.replace(_ENTRY_BAND_SENTENCE, _PRE_T188_BAND_SENTENCE)
    assert hashlib.sha256(restored.encode()).hexdigest() == _PRE_T188_POLICY_SHA256


@pytest.mark.parametrize("band", ["mid", "senior"])
def test_a_non_entry_band_is_asked_against_itself(band: str) -> None:
    rendered = judging_policy(band)
    assert f"target seniority band, `{band}`" in rendered
    assert "entry-level / new-grad / early-career" not in rendered
    assert 'seniority_fit: "yes" | "no" | "unclear"' in rendered


def test_a_senior_band_does_not_answer_senior_roles_no() -> None:
    assert "Senior," not in judging_policy("senior")
    assert "Senior," in judging_policy("mid")


def test_the_any_band_is_not_asked_seniority_at_all() -> None:
    rendered = judging_policy("any")
    assert "seniority_fit" not in rendered
    assert "SENIORITY IS ASKED" not in rendered


def test_an_out_of_catalog_band_is_refused() -> None:
    with pytest.raises(ValueError, match="staff_plus"):
        judging_policy("staff_plus")


def test_the_request_carries_the_band_it_asked_against() -> None:
    rows = [{"label": "1", "expected_verdict": None, "facts": {}, "body_text": "Employer JD."}]
    request = build_label_request(rows, CAT, request_id="r", target_band="mid")
    assert request["target_band"] == "mid"
    assert request["judging_policy"] == judging_policy("mid")


def test_an_unasked_seniority_answer_is_not_read() -> None:
    """A judge that answers anyway is ignored: the value is the inert `unclear` and the token
    says it was skipped, so it is counted neither as an answer nor as unreadable."""
    verdicts, _, seniority = _parse_verdicts(
        _stdout([{**_verdict("1"), "seniority_fit": "no"}]), ["1"], seniority_asked=False
    )
    assert verdicts[0].seniority_fit == "unclear"
    assert seniority == ("skipped",)


def _set_band(engine: Engine, band: str) -> None:
    with engine.begin() as conn:
        conn.execute(update(tables.profile).values(target_seniority_band=band))


def _stored_fit(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        raws = conn.execute(select(tables.eligibility_evaluations.c.raw_output_json)).scalars()
        return [raw["gate_verdict"]["seniority_fit"] for raw in raws]


@pytest.mark.parametrize(
    ("band", "asked", "fit", "counts"),
    [
        pytest.param("any", False, "unclear", (0, 1), id="any: skipped"),
        pytest.param("entry", True, "no", (1, 0), id="entry: asked (control)"),
        pytest.param("senior", True, "no", (1, 0), id="senior: asked"),
    ],
)
def test_the_stage_asks_seniority_only_under_a_declared_band(
    band: str, asked: bool, fit: str, counts: tuple[int, int],
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _store(tmp_path)
    _set_band(engine, band)
    posting_id, _ = _seed(engine, "acme-band")
    prompts: list[str] = []

    def call(prompt: str, **_: object) -> str:
        prompts.append(prompt)
        return _stdout([{**_verdict(str(posting_id)), "seniority_fit": "no"}])

    monkeypatch.setattr(gate_judge, "_call_claude", call)

    _, result = run_gate_stage(engine, _settings(tmp_path), [_Lead(posting_id)], run_id=None)

    assert result.judged == 1, result.errors
    assert ("seniority_fit" in prompts[0]) is asked
    assert (f"target seniority band, `{band}`" in prompts[0]) is asked
    assert (result.seniority_answered, result.seniority_skipped) == counts
    assert _stored_fit(engine) == [fit]
    assert json.loads(prompts[0].split("ITEMS:\n", 1)[1])[0]["label"] == str(posting_id)


@pytest.mark.parametrize(
    ("band", "expected"),
    [
        ("entry", None),
        ("mid", None),
        ("senior", None),
        ("any", "not_asked:target_seniority_band=any"),
    ],
)
def test_the_judge_seniority_gate_is_grounded_on_any_declared_band(
    band: str, expected: str | None
) -> None:
    reasons = ungrounded_reasons(
        field="software", taxonomy_field="software", field_tiers={"software"},
        target_seniority_band=band, seniority_hold=True, target_countries=("USA",),
    )
    assert reasons["judge_seniority"] == expected
