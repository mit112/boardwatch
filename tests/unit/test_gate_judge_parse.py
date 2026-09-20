"""`gate_judge._parse_verdicts` binds a verdict to its lead by LABEL, never by position or count.

Runs 45 and 48 (2026-09-09, 2026-09-12) each failed a whole batch of 13 leads open because the
model answered 12 — "expected a JSON array of 13 verdicts, got 12". Every verdict names its lead
and `apply_gate_verdicts` binds on that name, so twelve sound verdicts were thrown away for one
skipped lead. Only the skipped lead is unjudged now; a response that names a lead the batch did
not contain, names one twice, or answers more than it was asked still fails the whole batch open.
"""

from __future__ import annotations

import errno
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, insert, select

from boardwatch.core.clock import utcnow
from boardwatch.core.settings import GateTier, Settings
from boardwatch.eligibility.final_gate import gate_engine_version
from boardwatch.eligibility.oracle import OracleVerdict
from boardwatch.llm import gate_judge
from boardwatch.llm.gate_judge import _judge_batch, _parse_verdicts, run_gate_stage
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema


def _stdout(verdicts: list[dict[str, object]]) -> str:
    return json.dumps({"is_error": False, "result": json.dumps(verdicts)})


def _verdict(label: str) -> dict[str, object]:
    return {"label": label, "decision": "eligible", "reason": None, "evidence": "",
            "confidence": "high"}


def test_a_skipped_lead_is_reported_missing_and_the_rest_are_kept() -> None:
    """RED before: `ValueError: expected a JSON array of 3 verdicts, got 2`."""
    verdicts, missing, _ = _parse_verdicts(
        _stdout([_verdict("1"), _verdict("3")]), ["1", "2", "3"]
    )
    assert [v.label for v in verdicts] == ["1", "3"]
    assert missing == ("2",)


def test_a_complete_answer_reports_nothing_missing() -> None:
    verdicts, missing, _ = _parse_verdicts(_stdout([_verdict("2"), _verdict("1")]), ["1", "2"])
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


# ---------------------------------------------------------------- `seniority_fit`, fail-open


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param({}, id="absent — a judge under the old policy"),
        pytest.param({"seniority_fit": None}, id="null"),
        pytest.param({"seniority_fit": "NO"}, id="wrong case"),
        pytest.param({"seniority_fit": "senior"}, id="out of catalog"),
        pytest.param({"seniority_fit": 0}, id="wrong type"),
        pytest.param({"seniority_fit": "unclear"}, id="the inert value itself"),
    ],
)
def test_an_unreadable_seniority_answer_reads_unclear_and_never_no(
    answer: dict[str, object],
) -> None:
    """**The direction is the whole point, and nothing else in the suite pins it.**

    `seniority_fit == "no"` WITHHOLDS a lead from the apply lane. If an absent, null, misspelled
    or wrongly-typed answer defaulted to `"no"` instead of `"unclear"`, then every lead judged
    before this field existed — every row under `p5-oracle-1`, which is the entire live store at
    the moment this ships — would be withheld on a reading nobody ever made. A mutation flipping
    the default to `"no"` passes the rest of this suite and the whole gate-stage suite; it fails
    here.

    Out-of-catalog is `"unclear"` and NOT a raise, unlike every other field this parser reads:
    those decide a VERDICT, and this one only decides a delivery lane. A batch that answered the
    six families correctly must not be thrown away over a tenth field it spelled oddly.
    """
    verdicts, missing, _ = _parse_verdicts(_stdout([{**_verdict("1"), **answer}]), ["1"])
    assert missing == ()
    assert verdicts[0].seniority_fit == "unclear"


def test_a_well_formed_seniority_answer_is_carried_through() -> None:
    """The other half: the control that keeps the test above from passing on a parser that
    hard-codes `"unclear"` for everything."""
    for value in ("yes", "no", "unclear"):
        verdicts, _, _ = _parse_verdicts(
            _stdout([{**_verdict("1"), "seniority_fit": value}]), ["1"]
        )
        assert verdicts[0].seniority_fit == value


# ------------------------------------- T106: EVERY external defect fails its BATCH, not the run
#
# The module has always promised D-074 at every seam — an unusable response drops that BATCH's
# verdicts, never a real job. Three classes of external defect escaped that boundary and aborted
# the whole RUN instead: a non-mapping envelope (`AttributeError`, not in the catch tuple), an
# out-of-vocabulary `decision` or `confidence` (refused only later, by `accept_oracle_verdict`
# inside the write transaction), and any process-launch failure other than the three named ones.
# `run_pipeline` catches the escapee at its outer boundary, sets `summary.fatal` and re-raises
# BEFORE tailoring — so what one malformed response actually cost was the day's tailoring and PDF
# render, its new deliveries, the `seen` dispositions and the heartbeat.


BODY = (
    "We are hiring a backend engineer to work on Python and PostgreSQL services. "
    "Relocation to our Antarctica research base is mandatory within 30 days of starting."
)


def _settings(tmp_path: Path, *, batch_size: int = 13) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "no-such-cfg-dir",
        gate=GateTier(enabled=True, batch_size=batch_size),
    )


def _batch(*labels: str) -> list[dict[str, object]]:
    return [{"label": label, "facts": {}, "jd_text": BODY} for label in labels]


def _returns(monkeypatch: pytest.MonkeyPatch, *stdouts: str) -> None:
    """Drive `_judge_batch` with canned stdout, one entry per call, no subprocess."""
    remaining = list(stdouts)
    monkeypatch.setattr(gate_judge, "_call_claude", lambda *a, **k: remaining.pop(0))


def _raises(monkeypatch: pytest.MonkeyPatch, exc: BaseException) -> None:
    def _boom(*_a: object, **_k: object) -> str:
        raise exc

    monkeypatch.setattr(gate_judge, "_call_claude", _boom)


@pytest.mark.parametrize(
    "outer",
    [pytest.param("[]", id="a bare array"), pytest.param("null", id="null")],
)
def test_a_non_mapping_envelope_fails_its_batch_open(
    outer: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_parse_verdicts` read `envelope.get("is_error")` before establishing that `envelope`
    is a mapping, so a top-level array or `null` raised `AttributeError` — which is NOT in
    `_judge_batch`'s catch tuple and therefore left the stage entirely."""
    _returns(monkeypatch, outer)

    verdicts, note, _ = _judge_batch(_batch("1"), "policy", _settings(tmp_path))

    assert verdicts is None
    assert note is not None and "unusable response" in note


def test_an_out_of_vocabulary_decision_fails_its_batch_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """job-apps' legacy `"move"`. `OracleVerdict` has no validating constructor, so this was
    carried out of the batch boundary intact and only refused later, by
    `accept_oracle_verdict` INSIDE `run_gate_stage`'s write transaction."""
    _returns(monkeypatch, _stdout([{**_verdict("1"), "decision": "move"}]))

    verdicts, note, _ = _judge_batch(_batch("1"), "policy", _settings(tmp_path))

    assert verdicts is None
    assert note is not None and "move" in note


def test_an_out_of_vocabulary_confidence_fails_its_batch_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`confidence` was validated against nothing, anywhere, and persisted verbatim."""
    _returns(monkeypatch, _stdout([{**_verdict("1"), "confidence": "nonsense"}]))

    verdicts, note, _ = _judge_batch(_batch("1"), "policy", _settings(tmp_path))

    assert verdicts is None
    assert note is not None and "nonsense" in note


@pytest.mark.parametrize(
    "exc",
    [
        pytest.param(PermissionError(errno.EACCES, "Permission denied", "claude"), id="EACCES"),
        pytest.param(OSError(errno.E2BIG, "Argument list too long"), id="E2BIG"),
    ],
)
def test_a_process_launch_failure_fails_its_batch_open(
    exc: OSError, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The caller caught `FileNotFoundError`, `TimeoutExpired` and `CalledProcessError` only.
    A non-executable binary (EACCES) and an argv over the platform limit (E2BIG) are both
    external, both `OSError`, and both escaped."""
    _raises(monkeypatch, exc)

    verdicts, note, _ = _judge_batch(_batch("1"), "policy", _settings(tmp_path))

    assert verdicts is None
    assert note is not None and "claude" in note
    assert str(exc.errno) in note, f"the note must name the errno to be diagnosable: {note}"


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        pytest.param(FileNotFoundError(), "not found on PATH", id="missing binary"),
        pytest.param(
            subprocess.TimeoutExpired(cmd="claude", timeout=300), "timed out", id="timeout"
        ),
        pytest.param(
            subprocess.CalledProcessError(returncode=2, cmd="claude", stderr="boom"),
            "exited 2",
            id="non-zero exit",
        ),
    ],
)
def test_the_three_named_process_failures_keep_their_own_notes(
    exc: BaseException, expected: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Control. `FileNotFoundError` is an `OSError` subclass, so widening the catch to the
    `OSError` family can silently swallow the three specific notes the run's soft alert and
    the morning digest print. Each must survive the widening verbatim."""
    _raises(monkeypatch, exc)

    verdicts, note, _ = _judge_batch(_batch("1"), "policy", _settings(tmp_path))

    assert verdicts is None
    assert note is not None and expected in note


# -------------------------------------------------- the same three, through the whole stage


@dataclass(frozen=True)
class _Lead:
    """Duck-types the one attribute `run_gate_stage` reads off a `RankedPosting`."""

    posting_id: int


def _store(tmp_path: Path) -> Engine:
    engine = create_engine(f"sqlite:///{tmp_path / 'gate.db'}")
    ensure_schema(engine)
    with engine.begin() as conn:
        conn.execute(insert(tables.profile).values(
            id=1, text="Backend engineer.", remote_only=False, resume_max_pages=1,
            updated_at=utcnow(),
        ))
    return engine


def _seed(engine: Engine, slug: str) -> tuple[int, int]:
    """One open posting with a current version carrying `BODY`. Returns (posting, version)."""
    now = utcnow()
    with engine.begin() as conn:
        company_id = int(conn.execute(insert(tables.companies).values(
            name=slug, provider="greenhouse", slug=slug, source="user", watched=True,
        )).inserted_primary_key[0])
        job_id = int(conn.execute(
            insert(tables.jobs).values(created_at=now)
        ).inserted_primary_key[0])
        posting_id = int(conn.execute(insert(tables.postings).values(
            company_id=company_id, job_id=job_id, provider_posting_id=f"p-{slug}",
            title="Backend Engineer", normalized_title="backend engineer",
            first_seen_at=now, last_seen_at=now, status="open", consecutive_missing=0,
            content_hash=f"h-{slug}", body_text=BODY,
        )).inserted_primary_key[0])
        version_id = int(conn.execute(insert(tables.posting_versions).values(
            posting_id=posting_id, content_hash=f"h-{slug}", body_text=BODY,
            captured_at=now, run_id=None, capture_reason="new",
        )).inserted_primary_key[0])
    return posting_id, version_id


def _persisted(engine: Engine) -> dict[int, str]:
    """posting_version_id -> persisted gate verdict, read straight off the ledger rather than
    through `current_gate_verdicts` — a different path than the one that wrote it."""
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                tables.eligibility_inputs.c.posting_version_id,
                tables.eligibility_evaluations.c.verdict,
            ).join(
                tables.eligibility_inputs,
                tables.eligibility_evaluations.c.input_id == tables.eligibility_inputs.c.id,
            ).where(
                tables.eligibility_evaluations.c.engine_version == gate_engine_version()
            )
        ).all()
    return {int(row.posting_version_id): str(row.verdict) for row in rows}


def test_the_stage_survives_an_out_of_vocabulary_decision_and_keeps_every_lead(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The escaping `OracleVerdictError` came out of `accept_oracle_verdict` INSIDE
    `with engine.begin()`, so the run aborted rather than the batch failing open."""
    engine = _store(tmp_path)
    posting_id, version_id = _seed(engine, "acme-move")
    _returns(monkeypatch, _stdout([{**_verdict(str(posting_id)), "decision": "move"}]))

    kept, result = run_gate_stage(
        engine, _settings(tmp_path), [_Lead(posting_id)], run_id=None
    )

    assert [lead.posting_id for lead in kept] == [posting_id], "no lead may leave the slate"
    assert result.judged == 0
    assert result.failed_open_batches == 1
    assert version_id not in _persisted(engine), "a refused verdict must never be persisted"


def test_a_malformed_batch_never_unwinds_the_valid_batch_beside_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Isolation control. One bad response must cost its own batch's leads and nothing else —
    today the escaping exception takes the whole run's gate stage down with it."""
    engine = _store(tmp_path)
    bad_id, bad_version = _seed(engine, "acme-bad")
    good_id, good_version = _seed(engine, "acme-good")
    _returns(monkeypatch, "[]", _stdout([_verdict(str(good_id))]))

    kept, result = run_gate_stage(
        engine, _settings(tmp_path, batch_size=1), [_Lead(bad_id), _Lead(good_id)], run_id=None
    )

    assert result.failed_open_batches == 1, result.errors
    assert result.judged == 1, "the valid batch must still be judged"
    assert result.eligible == 1
    assert sorted(lead.posting_id for lead in kept) == sorted([bad_id, good_id])
    assert _persisted(engine) == {good_version: "eligible"}
    assert bad_version not in _persisted(engine)


def test_a_verdict_that_fails_acceptance_costs_its_own_lead_and_no_other(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stage's own guard, independent of the parser's.

    `accept_oracle_verdict` runs at TWO uncaught sites: `apply_gate_verdicts` inside the write
    transaction, and `_tally_eligible_and_uncertain` AFTER it has committed — so a verdict the
    former skipped could still abort the run with its batch already persisted. Driven here by
    substituting `_judge_batch`, because the parser now refuses this shape one layer earlier;
    the property being pinned is that `run_gate_stage` does not depend on it having done so.
    """
    engine = _store(tmp_path)
    bad_id, bad_version = _seed(engine, "acme-bad")
    good_id, good_version = _seed(engine, "acme-good")
    verdicts = [
        OracleVerdict(label=str(bad_id), decision="move", reason=None, evidence="",
                      confidence="high"),
        OracleVerdict(label=str(good_id), decision="eligible", reason=None, evidence="",
                      confidence="high"),
    ]
    monkeypatch.setattr(
        gate_judge, "_judge_batch", lambda *a, **k: (verdicts, None, ("answered",) * 2)
    )

    kept, result = run_gate_stage(
        engine, _settings(tmp_path), [_Lead(bad_id), _Lead(good_id)], run_id=None
    )

    assert result.judged == 1
    assert sorted(lead.posting_id for lead in kept) == sorted([bad_id, good_id])
    assert _persisted(engine) == {good_version: "eligible"}
    assert bad_version not in _persisted(engine)
    assert any(str(bad_id) in error for error in result.errors), result.errors


# ------------------------------- T107: the three-way `seniority_fit` answer split
#
# `_seniority_fit` folds an absent or out-of-catalog answer to `"unclear"` — the inert value,
# which is the right DELIVERY direction and the wrong REPORTING one: `"unclear"` is also what a
# judge that genuinely could not tell returns. Of 1,999 stored gate verdicts 215 carry an
# explicit `"unclear"`, so a two-way split would report a real answer as a parse failure on a
# seventh of the corpus. The parser therefore reports HOW each answer read, beside the value.


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        pytest.param({"seniority_fit": "yes"}, "answered", id="yes"),
        pytest.param({"seniority_fit": "no"}, "answered", id="no"),
        pytest.param({"seniority_fit": "unclear"}, "unclear", id="a REAL explicit unclear"),
        pytest.param({}, "unreadable", id="absent — a judge under the old policy"),
        pytest.param({"seniority_fit": None}, "unreadable", id="null"),
        pytest.param({"seniority_fit": "NO"}, "unreadable", id="wrong case"),
        pytest.param({"seniority_fit": "senior"}, "unreadable", id="out of catalog"),
        pytest.param({"seniority_fit": 0}, "unreadable", id="wrong type"),
    ],
)
def test_the_parser_reports_how_each_seniority_answer_read(
    answer: dict[str, object], expected: str
) -> None:
    _, _, seniority = _parse_verdicts(_stdout([{**_verdict("1"), **answer}]), ["1"])
    assert seniority == (expected,)


def test_the_seniority_split_is_one_token_per_verdict_in_answer_order() -> None:
    """The split must survive a batch, not just a single item: the field-coverage alarm is a
    SHARE, and a parser that reported only the last answer's quality would read 1/13 as 1/1."""
    _, _, seniority = _parse_verdicts(
        _stdout([
            {**_verdict("1"), "seniority_fit": "yes"},
            {**_verdict("2"), "seniority_fit": "unclear"},
            _verdict("3"),
        ]),
        ["1", "2", "3"],
    )
    assert seniority == ("answered", "unclear", "unreadable")


def test_a_failed_batch_reports_no_seniority_answers_at_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A batch that failed open answered nothing, so it contributes nothing to the field
    coverage denominator — folding its items in as `unreadable` would make a process outage
    read as a parse-quality failure, and those need different fixes."""
    _returns(monkeypatch, "null")

    verdicts, note, seniority = _judge_batch(_batch("1"), "policy", _settings(tmp_path))

    assert verdicts is None and note is not None
    assert seniority == ()
