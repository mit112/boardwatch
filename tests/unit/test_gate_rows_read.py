"""The gate-row read behind `current_gate_verdicts` reaches the gate rows through their own index.

`_latest_gate_rows` walks every eligibility input of every asked-about version, 500 versions a
statement, and joins each input to its evaluations under `engine_kind = 'llm'`. With no index on the
gate rows each probe landed in the whole table's `input_id` index: 66 s for the ranker's 748,661
open versions on a clone of the live store (2026-11-27). The partial index
`ix_eligibility_evaluations_llm` holds only the gate rows (about 19.5k of 6.5M), and the same read
takes 3.6 s through it, with identical results. These pin that the read keeps its answer and that
SQLite keeps choosing that index.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event, select

from boardwatch.eligibility import final_gate
from boardwatch.eligibility.facts import Facts, Policy
from boardwatch.eligibility.oracle import OracleVerdict
from boardwatch.eligibility.read import current_gate_verdicts
from boardwatch.store.db import ensure_schema
from boardwatch.store.tables import posting_versions
from tests.unit.test_final_gate_persistence import _catalog, seed_posting_version

JD = "We are hiring a backend engineer for our Python services."


def _judge(engine: Engine, pv_id: int, decision: str, *, model: str = "sonnet") -> None:
    v = OracleVerdict(label="1", decision=decision, reason=None, evidence="", confidence="high")
    with engine.begin() as conn:
        final_gate.record_gate_verdict(
            conn, posting_version_id=pv_id, jd_text=JD, facts=Facts(), policy=Policy(families={}),
            catalog=_catalog(Path("/nonexistent")), verdict=v, model=model, target_band="any",
        )


def _read(engine: Engine, pv_ids: list[int]) -> dict[int, str | None]:
    with engine.connect() as conn:
        return current_gate_verdicts(
            conn, pv_ids, Facts(), _catalog(Path("/nonexistent")), model="sonnet",
            effort=final_gate.gate_effort_key(None), target_band="any",
        )


def _posting_of(engine: Engine, pv_id: int) -> int:
    with engine.connect() as conn:
        return int(conn.execute(
            select(posting_versions.c.posting_id).where(posting_versions.c.id == pv_id)
        ).scalar_one())


def test_only_the_versions_asked_about_are_returned_with_their_newest_row(tmp_path: Path) -> None:
    """A, B and C are judged; A twice (the newer row wins) and B also by another model. Asking
    for A and C returns exactly those two, though the read now groups over every gate row."""
    engine = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    ensure_schema(engine)
    with engine.begin() as conn:
        a, b, c = (seed_posting_version(conn, body_text=JD, slug=s) for s in ("a", "b", "c"))
    _judge(engine, a, "uncertain")
    _judge(engine, a, "eligible")
    _judge(engine, b, "eligible")
    _judge(engine, b, "uncertain", model="opus")  # newer, but another judge: out of scope
    _judge(engine, c, "uncertain")

    assert _read(engine, [a, c]) == {_posting_of(engine, a): "eligible",
                                     _posting_of(engine, c): "uncertain"}
    assert _read(engine, [b]) == {_posting_of(engine, b): "eligible"}
    assert _read(engine, []) == {}


def test_every_gate_row_statement_probes_the_gate_row_index(tmp_path: Path) -> None:
    """1,200 versions asked about take three chunked statements, and SQLite reaches the
    evaluations in each through `ix_eligibility_evaluations_llm`, not through the whole table's
    `input_id` index."""
    engine = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    ensure_schema(engine)
    with engine.begin() as conn:
        pv_id = seed_posting_version(conn, body_text=JD)
    _judge(engine, pv_id, "eligible")

    seen: list[tuple[str, object]] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _spy(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        if "max(eligibility_evaluations.id)" in statement:
            seen.append((statement, parameters))

    asked = [pv_id, *range(10_000, 11_199)]
    assert _read(engine, asked) == {_posting_of(engine, pv_id): "eligible"}
    event.remove(engine, "before_cursor_execute", _spy)

    assert len(seen) == 3, [s for s, _ in seen]  # 1,200 ids, 500 a chunk
    with engine.connect() as conn:
        for statement, parameters in seen:
            plan = " | ".join(
                str(row[-1])
                for row in conn.exec_driver_sql(f"EXPLAIN QUERY PLAN {statement}", parameters)
            )
            assert "INDEX ix_eligibility_evaluations_llm" in plan, plan
            assert "ix_eligibility_evaluations_input_created" not in plan, plan
