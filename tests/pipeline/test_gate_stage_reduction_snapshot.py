"""T139 — the judge stage's REDUCTION onto the run, snapshotted before it is extracted (F10 #1).

`run_gate_stage` returns a structured `GateStageResult`; `run_pipeline` copies its counters onto
`summary.gate_*` and appends its notes to the console, to `stage_errors` (the `runs` row) and to
`summary.errors` (the funnel). This test pins everything that reduction produces for one fixed
verdict mix, as it stood BEFORE the reduction moved into its own function, so the move is proven
against the pre-move behaviour rather than against a restatement of it:

* the funnel JSON's `gate` block, which reads the summary's counters;
* every `summary.gate_*` field, including the ones written beside the reduction and not by it
  (`gate_beyond_slate` by the T63 cut, `gate_readings_absent` by the lane split);
* `summary.errors` and `runs.errors_json`, whose ORDER is part of the claim;
* the console lines of the gate section, whose order is too: the stage's summary line prints
  BEFORE its notes.

The mix, one batch each of four, four and two, with `gate.depth` one past what survives:

1. answered in full — eligible, ineligible with a quoted span, uncertain, and an eligible whose
   seniority answer was unreadable;
2. failed open (the process exited non-zero);
3. partly answered — one verdict `_accepted` refuses, one label missing.

The stub stands in for `_judge_batch`, not for the `claude` process, and has to: a refused item is
unreachable through a real response on this base, because `_parse_verdicts` validates `decision`
against the same vocabulary `accept_oracle_verdict` refuses on. Nothing is normalized: in a fresh
store every run id and posting id is fixed, and none of what is snapshotted carries a timestamp
or a path.
"""

from __future__ import annotations

import io
import json
from dataclasses import fields
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console
from sqlalchemy import select

from boardwatch.core.settings import Settings, load_settings
from boardwatch.eligibility.oracle import OracleVerdict
from boardwatch.llm import gate_judge
from boardwatch.pipeline.runner import PipelineSummary, run_pipeline
from boardwatch.store import tables
from boardwatch.store.db import get_engine
from tests.pipeline.test_gate_stage import EVIDENCE, _ready, _seed
from tests.pipeline.test_run_pdf_gate import _ok


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _verdict(label: str, decision: str, **kw: str) -> OracleVerdict:
    return OracleVerdict(
        label=label,
        decision=decision,
        reason=kw.get("reason"),
        evidence=kw.get("evidence", ""),
        confidence=kw.get("confidence", "high"),
        seniority_fit=kw.get("seniority_fit", "unclear"),
    )


def _stub_judge(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Answers batch N with mix N above, in the `(verdicts, note, seniority)` shape
    `_judge_batch` returns, and records the labels each batch carried."""
    batches: list[list[str]] = []
    answered = gate_judge._SENIORITY_ANSWERED
    unclear = gate_judge._SENIORITY_UNCLEAR
    unreadable = gate_judge._SENIORITY_UNREADABLE

    def judge(
        batch: list[dict[str, object]], judging_policy: str, settings: Settings
    ) -> tuple[list[OracleVerdict] | None, str | None, tuple[str, ...]]:
        labels = [str(item["label"]) for item in batch]
        batches.append(labels)
        if len(batches) == 1:
            eligible, rejected, unsure, unread = labels
            return (
                [
                    _verdict(eligible, "eligible", seniority_fit="yes"),
                    _verdict(
                        rejected, "ineligible", reason="work_auth", evidence=EVIDENCE,
                        seniority_fit="no",
                    ),
                    _verdict(unsure, "uncertain", confidence="low"),
                    _verdict(unread, "eligible"),
                ],
                None,
                (answered, answered, unclear, unreadable),
            )
        if len(batches) == 2:
            return None, "claude exited 1: simulated outage", ()
        refused, missing = labels
        return (
            [_verdict(refused, "maybe")],
            f"1 of 2 verdicts missing (labels {missing}); those leads were left unchanged, "
            "never dropped",
            (answered,),
        )

    monkeypatch.setattr(gate_judge, "_judge_batch", judge)
    return batches


def _gate_console_lines(text: str) -> list[str]:
    """The lines from the `gate` stage header up to the `tailor` header, exclusive."""
    lines = [line.rstrip() for line in text.splitlines()]
    start = lines.index("gate")
    end = next(index for index in range(start, len(lines)) if lines[index].startswith("tailor"))
    return lines[start:end]


def _observe(env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    _ready(env)
    for n in range(10):
        _seed(env, slug=f"acme-snap-{n}")
    settings = load_settings(data_dir=env)
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    (settings.config_dir / "config.toml").write_text(
        '[gate]\nenabled = true\nmodel = "sonnet"\nbatch_size = 4\ncall_timeout_s = 30\n'
        "depth = 10\n",
        encoding="utf-8",
    )
    settings = load_settings(data_dir=env)
    monkeypatch.setattr("boardwatch.reports.tailor._default_runner", lambda tex, pdf: _ok(pdf))
    batches = _stub_judge(monkeypatch)
    out = io.StringIO()
    engine = get_engine(env)

    summary = run_pipeline(
        engine,
        settings,
        console=Console(file=out, width=400),
        out_root=tmp_path / "apps",
        resume_path=settings.config_dir / "resume.yaml",
        skip_scan=True,
        top_n=8,
    )

    assert [len(batch) for batch in batches] == [4, 4, 2], batches
    assert summary.funnel is not None
    with engine.connect() as conn:
        errors_json = conn.execute(
            select(tables.runs.c.errors_json).where(tables.runs.c.id == summary.run_id)
        ).scalar_one()
    return {
        "run_id": summary.run_id,
        "fatal": summary.fatal,
        "funnel_gate": json.loads(summary.funnel.json_path.read_text(encoding="utf-8"))["gate"],
        "summary_gate": {
            item.name: getattr(summary, item.name)
            for item in fields(PipelineSummary)
            if item.name.startswith("gate_")
        },
        "summary_errors": summary.errors,
        "errors_json": errors_json,
        "console_gate": _gate_console_lines(out.getvalue()),
    }


def test_the_gate_stage_reduction_matches_its_pre_extraction_snapshot(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed = _observe(env, tmp_path, monkeypatch)
    assert observed == EXPECTED


#: Taken on the unchanged code (T139 commit 1). Regenerate it only for a DELIBERATE change to what
#: the gate stage reports, and say so in that change.
EXPECTED: dict[str, Any] = {
    "run_id": 1,
    "fatal": None,
    "funnel_gate": {
        "instrumented": True,
        "judged": 4,
        "eligible": 2,
        "ineligible": 1,
        "uncertain": 1,
        "failed_open_batches": 1,
        "beyond_slate": 1,
        "candidates": 10,
        "cached": 0,
        "sent": 10,
        "missing_items": 5,
        "refused_items": 1,
        "seniority_answered": 3,
        "seniority_unclear": 1,
        "seniority_unreadable": 1,
        "readings_absent": 5,
        "refresh_budget": 0,
        "refresh_candidates": None,
        "refresh_sent": None,
        "refresh_pending_after": None
    },
    "summary_gate": {
        "gate_excluded_ids": [
            2
        ],
        "gate_judged": 4,
        "gate_eligible": 2,
        "gate_ineligible": 1,
        "gate_uncertain": 1,
        "gate_failed_open": 1,
        "gate_beyond_slate": 1,
        "gate_candidates": 10,
        "gate_cached": 0,
        "gate_sent": 10,
        "gate_missing_items": 5,
        "gate_refused_items": 1,
        "gate_seniority_answered": 3,
        "gate_seniority_unclear": 1,
        "gate_seniority_unreadable": 1,
        "gate_readings_absent": 5,
        "gate_refresh_candidates": 0,
        "gate_refresh_sent": 0,
        "gate_refresh_pending_after": 0
    },
    "summary_errors": [
        "gate: batch 2/3 failed open: claude exited 1: simulated outage",
        "gate: batch 3/3 partly failed open: 1 of 2 verdicts missing (labels 10); those leads were left unchanged, never dropped",
        "gate: verdict for lead 9 refused: decision 'maybe' not in ['eligible', 'ineligible', 'uncertain']",
        "apply lane: 2 lead(s) reached the blind-apply queue, under B8's bar of 20 — 8 placeable, 6 held for review (no_requirements_found 6)",
        "gate: 1 batch(es) failed open this run (4 judged clean) — the judge did not run for those leads; they were left unchanged, never dropped",
        "gate: 5 of 10 judged items came back with no verdict and 1 were answered then refused — those leads were left unchanged, never dropped, and carry no gate row at all",
        "gate: no readable gate reading under the judge's current inputs for 5 of 8 delivered lead(s) — a stored reading counts only for the same facts, `gate.model` and gate policy/prompt version, and the read fails open, so every gate-derived hold on them has RELEASED, not merely failed to apply (D-537). A changed fact, judge or gate version does this silently; re-judge before trusting the apply lane"
    ],
    "errors_json": [
        "gate: batch 2/3 failed open: claude exited 1: simulated outage",
        "gate: batch 3/3 partly failed open: 1 of 2 verdicts missing (labels 10); those leads were left unchanged, never dropped",
        "gate: verdict for lead 9 refused: decision 'maybe' not in ['eligible', 'ineligible', 'uncertain']",
        "apply lane: 2 lead(s) reached the blind-apply queue, under B8's bar of 20 — 8 placeable, 6 held for review (no_requirements_found 6)",
        "gate: 1 batch(es) failed open this run (4 judged clean) — the judge did not run for those leads; they were left unchanged, never dropped",
        "gate: 5 of 10 judged items came back with no verdict and 1 were answered then refused — those leads were left unchanged, never dropped, and carry no gate row at all",
        "gate: no readable gate reading under the judge's current inputs for 5 of 8 delivered lead(s) — a stored reading counts only for the same facts, `gate.model` and gate policy/prompt version, and the read fails open, so every gate-derived hold on them has RELEASED, not merely failed to apply (D-537). A changed fact, judge or gate version does this silently; re-judge before trusting the apply lane"
    ],
    "console_gate": [
        "gate",
        "gate: 4 judged (2 eligible, 1 ineligible, 1 uncertain), 1 batch(es) failed open, 1 beyond the delivered slate",
        "  ! gate: batch 2/3 failed open: claude exited 1: simulated outage",
        "  ! gate: batch 3/3 partly failed open: 1 of 2 verdicts missing (labels 10); those leads were left unchanged, never dropped",
        "  ! gate: verdict for lead 9 refused: decision 'maybe' not in ['eligible', 'ineligible', 'uncertain']"
    ]
}
