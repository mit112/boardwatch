"""T304: deterministic vs LLM judge on the same input. Expected values are by hand."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, insert, select

from boardwatch.eligibility.final_gate import GATE_VERSION_PREFIX
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.judge_agreement_queries import judge_agreement
from boardwatch.store.tables import (
    eligibility_evaluations as ev,
)
from boardwatch.store.tables import (
    eligibility_inputs,
    posting_versions,
)
from tests.unit.test_web_server import JD_ELIGIBLE, _deliver, _run

GATE = f"{GATE_VERSION_PREFIX}test"


@pytest.fixture(autouse=True)
def _scratch_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(tmp_path / "data"))


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path / "data")
    ensure_schema(eng)
    return eng


def _det_input(conn: Connection, posting_id: int) -> tuple[int, str]:
    row = conn.execute(
        select(ev.c.input_id, ev.c.verdict)
        .join(eligibility_inputs, ev.c.input_id == eligibility_inputs.c.id)
        .join(posting_versions, eligibility_inputs.c.posting_version_id == posting_versions.c.id)
        .where(posting_versions.c.posting_id == posting_id, ev.c.engine_kind == "deterministic")
    ).one()
    return int(row.input_id), str(row.verdict)


def _llm(conn: Connection, input_id: int, verdict: str, run_id: int, version: str = GATE) -> None:
    conn.execute(
        insert(ev).values(
            input_id=input_id,
            engine_kind="llm",
            engine_version=version,
            verdict=verdict,
            created_at=datetime(2026, 11, 17),
            run_id=run_id,
        )
    )


def test_pairs_each_llm_verdict_with_the_deterministic_one_on_the_same_input(
    engine: Engine,
) -> None:
    with engine.begin() as conn:
        run = _run(conn)
        posting, _ = _deliver(conn, "j1", body=JD_ELIGIBLE)
        input_id, det = _det_input(conn, posting)
        flipped = "ineligible" if det != "ineligible" else "eligible"
        _llm(conn, input_id, det, run)  # agrees
        _llm(conn, input_id, flipped, run)  # now disagrees: the newest LLM row decides the split
        _llm(conn, input_id, flipped, run, version="extract_llm:v1")  # advisory, reported apart
        got = judge_agreement(conn)

    (gate_run,) = got["lanes"]["final_gate"]
    assert (gate_run["run_id"], gate_run["total"], gate_run["agree"]) == (run, 2, 1)
    assert {(c["deterministic"], c["llm"]): c["count"] for c in gate_run["cells"]} == {
        (det, det): 1,
        (det, flipped): 1,
    }
    (advisory_run,) = got["lanes"]["advisory"]
    assert (advisory_run["total"], advisory_run["agree"]) == (1, 0)
    assert got["final_gate_splits"] == 1
    (split,) = got["splits"]
    assert (split["posting_id"], split["deterministic"], split["llm"]) == (posting, det, flipped)


def test_an_llm_row_with_no_deterministic_partner_is_its_own_cell(engine: Engine) -> None:
    with engine.begin() as conn:
        run = _run(conn)
        posting, _ = _deliver(conn, "j2", body=JD_ELIGIBLE)
        input_id, det = _det_input(conn, posting)
        # A second input for the same version that only the LLM read (the store is append-only,
        # so the deterministic row cannot be removed; a fresh input has none).
        src = conn.execute(
            select(eligibility_inputs).where(eligibility_inputs.c.id == input_id)
        ).one()
        lone = conn.execute(
            insert(eligibility_inputs).values(
                posting_version_id=src.posting_version_id,
                profile_hash="other-profile",
                profile_snapshot_json=src.profile_snapshot_json,
                rules_hash=src.rules_hash,
                rules_snapshot_json=src.rules_snapshot_json,
                input_fingerprint="lone-input",
                created_at=datetime(2026, 11, 17),
            )
        ).inserted_primary_key[0]
        _llm(conn, int(lone), "eligible", run)
        got = judge_agreement(conn)
    (gate_run,) = got["lanes"]["final_gate"]
    assert gate_run["cells"] == [{"deterministic": "none", "llm": "eligible", "count": 1}]
    assert gate_run["agree"] == 0
    assert got["final_gate_splits"] == 0
