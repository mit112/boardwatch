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
from datetime import UTC, datetime
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


def _order(row: Any) -> tuple[datetime, int]:
    """(instant, id). Ordered in Python: `created_at` mixes naive-UTC and offset-carrying text,
    and SQLite's `ORDER BY` would compare the text."""
    at: datetime = row.created_at
    if at.tzinfo is not None:
        at = at.astimezone(UTC).replace(tzinfo=None)
    return at, int(row.id)


def judge_agreement(conn: Connection) -> dict[str, Any]:
    llm = sorted(
        conn.execute(
            select(
                ev.c.id, ev.c.input_id, ev.c.engine_version, ev.c.verdict, ev.c.run_id,
                ev.c.created_at,
            ).where(ev.c.engine_kind == "llm")
        ),
        key=_order,
    )
    inputs = sorted({int(r.input_id) for r in llm})

    # Newest deterministic evaluation per input: ascending (instant, id), last one wins.
    det: dict[int, tuple[int, str]] = {}
    for chunk in id_chunks(inputs):
        found = conn.execute(
            select(ev.c.id, ev.c.input_id, ev.c.verdict, ev.c.created_at).where(
                ev.c.engine_kind == "deterministic", ev.c.input_id.in_(chunk)
            )
        )
        for r in sorted(found, key=_order):
            det[int(r.input_id)] = (int(r.id), str(r.verdict))

    # input -> (posting id, title, company). A posting's split is tracked per POSTING: a profile
    # change or JD revision makes a new input, and the newest gate reading of the posting is the
    # one that stands, so an old input's disagreement cannot outlive a newer agreement.
    labels: dict[int, tuple[int, str, str]] = {}
    for chunk in id_chunks(inputs):
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

    # (lane, run) -> Counter[(deterministic, llm)]; an LLM row with no deterministic partner is
    # its own cell, `none`, never folded into a verdict.
    matrices: dict[tuple[str, int | None], Counter[tuple[str, str]]] = {}
    # posting -> (gate evaluation order, input, det, llm, det id)
    latest_split: dict[int, tuple[tuple[datetime, int], int, str, str, int]] = {}
    for r in llm:
        lane = _lane(str(r.engine_version))
        pair = det.get(int(r.input_id))
        det_verdict = "none" if pair is None else pair[1]
        run = None if r.run_id is None else int(r.run_id)
        matrices.setdefault((lane, run), Counter())[(det_verdict, str(r.verdict))] += 1
        label = labels.get(int(r.input_id))
        if lane == "final_gate" and label is not None:
            if pair is not None and pair[1] != r.verdict:
                latest_split[label[0]] = (
                    _order(r), int(r.input_id), pair[1], str(r.verdict), pair[0]
                )
            else:
                latest_split.pop(label[0], None)

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
    det_ids = [split[4] for split in latest_split.values()]
    for chunk in id_chunks(det_ids):
        for r in conn.execute(
            select(er.c.rule_id).where(er.c.evaluation_id.in_(chunk), er.c.disposition == "unmet")
        ):
            rule_counts[str(r.rule_id)] += 1

    # Newest gate disagreements first, by when the gate read them.
    newest = sorted(latest_split.values(), reverse=True)[:SPLITS_SHOWN]

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
                "deterministic": d,
                "llm": j,
            }
            for _, i, d, j, _ in newest
        ],
    }
