"""Deterministic engine vs LLM judge, on the same input (T304).

Every LLM evaluation is paired with the newest deterministic evaluation of the SAME input (same
posting version, profile and rules), so a disagreement is the two engines reading one posting
under one profile, never a profile change. The two LLM lanes are reported apart: the final gate
can block; the advisory extraction lane cannot.

Read-only. The LLM rows are the small side (thousands), so the pairing reads them first and then
looks up deterministic rows by `input_id`, which `ix_eligibility_evaluations_input_created` leads.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import Connection, select

from boardwatch.eligibility.final_gate import GATE_VERSION_PREFIX
from boardwatch.store.param_chunks import id_chunks
from boardwatch.store.tables import (
    companies,
    eligibility_inputs,
    posting_versions,
    postings,
)
from boardwatch.store.tables import (
    eligibility_evaluations as ev,
)
from boardwatch.store.tables import (
    eligibility_requirements as er,
)

RUNS_SHOWN = 14
SPLITS_SHOWN = 50
RULES_SHOWN = 10


def _lane(engine_version: str) -> str:
    return "final_gate" if engine_version.startswith(GATE_VERSION_PREFIX) else "advisory"


def judge_agreement(conn: Connection) -> dict[str, Any]:
    llm = conn.execute(
        select(ev.c.id, ev.c.input_id, ev.c.engine_version, ev.c.verdict, ev.c.run_id)
        .where(ev.c.engine_kind == "llm")
        .order_by(ev.c.created_at, ev.c.id)
    ).all()
    inputs = sorted({int(r.input_id) for r in llm})

    # Newest deterministic evaluation per input: (created_at, id) ascending, last one wins.
    det: dict[int, tuple[int, str]] = {}
    for chunk in id_chunks(inputs):
        for r in conn.execute(
            select(ev.c.id, ev.c.input_id, ev.c.verdict)
            .where(ev.c.engine_kind == "deterministic", ev.c.input_id.in_(chunk))
            .order_by(ev.c.created_at, ev.c.id)
        ):
            det[int(r.input_id)] = (int(r.id), str(r.verdict))

    # (lane, run) -> Counter[(deterministic, llm)]; an LLM row with no deterministic partner is
    # its own cell, `none`, never folded into a verdict.
    matrices: dict[tuple[str, int | None], Counter[tuple[str, str]]] = {}
    latest_split: dict[int, tuple[str, str, str, int]] = {}  # input -> (lane, det, llm, det id)
    for r in llm:
        lane = _lane(str(r.engine_version))
        pair = det.get(int(r.input_id))
        det_verdict = "none" if pair is None else pair[1]
        run = None if r.run_id is None else int(r.run_id)
        matrices.setdefault((lane, run), Counter())[(det_verdict, str(r.verdict))] += 1
        if pair is not None and lane == "final_gate":
            if pair[1] != r.verdict:
                latest_split[int(r.input_id)] = (lane, pair[1], str(r.verdict), pair[0])
            else:
                latest_split.pop(int(r.input_id), None)

    runs_by_lane: dict[str, list[dict[str, Any]]] = {}
    for (lane, run), cells in sorted(matrices.items(), key=lambda kv: (kv[0][0], -(kv[0][1] or 0))):
        rows = runs_by_lane.setdefault(lane, [])
        if len(rows) >= RUNS_SHOWN:
            continue
        total = sum(cells.values())
        agree = sum(n for (d, j), n in cells.items() if d == j)
        rows.append(
            {
                "run_id": run,
                "total": total,
                "agree": agree,
                "cells": [
                    {"deterministic": d, "llm": j, "count": n}
                    for (d, j), n in sorted(cells.items())
                ],
            }
        )

    # Which deterministic rules were unmet on the postings the final gate now reads differently.
    rule_counts: Counter[str] = Counter()
    det_ids = [split[3] for split in latest_split.values()]
    for chunk in id_chunks(det_ids):
        for r in conn.execute(
            select(er.c.rule_id).where(er.c.evaluation_id.in_(chunk), er.c.disposition == "unmet")
        ):
            rule_counts[str(r.rule_id)] += 1

    split_inputs = sorted(latest_split)[-SPLITS_SHOWN:]
    labels: dict[int, tuple[int, str, str]] = {}
    for chunk in id_chunks(split_inputs):
        for r in conn.execute(
            select(
                eligibility_inputs.c.id,
                postings.c.id.label("posting_id"),
                postings.c.title,
                companies.c.name,
            )
            .join(
                posting_versions, eligibility_inputs.c.posting_version_id == posting_versions.c.id
            )
            .join(postings, posting_versions.c.posting_id == postings.c.id)
            .join(companies, postings.c.company_id == companies.c.id)
            .where(eligibility_inputs.c.id.in_(chunk))
        ):
            labels[int(r.id)] = (int(r.posting_id), str(r.title), str(r.name))

    return {
        "lanes": runs_by_lane,
        "final_gate_splits": len(latest_split),
        "split_rules": [
            {"rule_id": k, "count": n} for k, n in rule_counts.most_common(RULES_SHOWN)
        ],
        "splits": [
            {
                "posting_id": labels[i][0],
                "title": labels[i][1],
                "company": labels[i][2],
                "deterministic": latest_split[i][1],
                "llm": latest_split[i][2],
            }
            for i in reversed(split_inputs)
            if i in labels
        ],
    }
