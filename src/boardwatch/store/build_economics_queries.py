"""Résumé build economics (T310): does building ahead of the fill session pay off?

Two reads over `artifacts`, both read-only.

Per run: how many résumés each run built, from its own `resume_tailored` rows. A review-lane lead
is delivered as a `.tex` stub with `meta_json.pending_tailor` set and no render (T43), so it is
counted apart as `not_rendered`: a stub cost no build and is never "a wasted build".

Per lead: the cohort is every job with a RENDERED résumé (a compiled PDF: a stub, or a tailor whose
PDF failed with `typst_pdf_built` false, gave the owner nothing to send), credited to its FIRST
delivery and that delivery's board exactly as `lead_aging_queries._first_deliveries` does (T298,
T306), so a lead delivered twice counts once and the figures agree with the other panels. A lead
that was only ever delivered without one is in `not_rendered_leads`, outside the cohort; so is a
lead whose first dated application came before its first rendered résumé, in
`applied_before_build_leads`: the owner applied without the build, so it says nothing about whether
building ahead pays. Each cohort lead then ends in exactly one state:

  applied  an application was recorded, whenever (an import with an unknown date counts: this
           asks whether the build was used, not how long it waited, so no duration is measured
           and an import's stamped time is never read as a date);
  closed   never applied, and the delivered posting closed (or, if both happened, closed before
           the owner skipped it): a wasted build;
  skipped  never applied, and the owner skipped it before it closed: a wasted build the owner chose;
  open     never applied, not skipped, posting not closed: still waiting, NOT wasted. A lead
           delivered last night is here; `open` is what moves as the fill session runs.

`settled_rate` divides applied by applied + closed + skipped, leaving `open` out of both sides,
so a young backlog does not read as waste. `apply_rate` (applied / built) is the all-in figure.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, select

from boardwatch.store.lead_aging_queries import (
    _first_applied,
    _first_deliveries,
    _naive,
    _naive_utc,
)
from boardwatch.store.queue_state import skipped_job_ids
from boardwatch.store.run_funnel_queries import TAILORED_KIND
from boardwatch.store.tables import artifacts, posting_versions, postings

STATES = ("applied", "closed", "skipped", "open")


def _pending(meta: object) -> bool:
    """A review-lane stub: delivered, never rendered (`runner._deliver_pending_review_lead`)."""
    return isinstance(meta, dict) and bool(meta.get("pending_tailor"))


def _rates(row: dict[str, Any]) -> dict[str, Any]:
    settled = row["applied"] + row["closed"] + row["skipped"]
    row["apply_rate"] = row["applied"] / row["built"] if row["built"] else None
    row["settled_rate"] = row["applied"] / settled if settled else None
    return row


def _blank() -> dict[str, Any]:
    return {"built": 0, "applied": 0, "closed": 0, "skipped": 0, "open": 0}


def built_per_run(conn: Connection, run_ids: Sequence[int]) -> dict[int, dict[str, int]]:
    """run id -> résumés rendered and review-lane stubs that run delivered. Every id is present."""
    out = {run_id: {"built": 0, "not_rendered": 0} for run_id in run_ids}
    if not out:
        return out
    for r in conn.execute(
        select(artifacts.c.run_id, artifacts.c.meta_json).where(
            artifacts.c.kind == TAILORED_KIND, artifacts.c.run_id.in_(list(out))
        )
    ):
        out[int(r.run_id)]["not_rendered" if _pending(r.meta_json) else "built"] += 1
    return out


def _rendered(meta: object) -> bool:
    """A `resume_tailored` row with a compiled PDF: not a stub, and not a failed compile."""
    return not _pending(meta) and not (
        isinstance(meta, dict) and meta.get("typst_pdf_built") is False
    )


def _rendered_jobs(conn: Connection) -> dict[int, datetime]:
    """job id -> when its first rendered `resume_tailored` row was recorded (a later `tailor run`
    promotes a stub). The earliest is taken in Python after normalising, never with SQL `MIN()`:
    the column mixes naive-UTC and offset-carrying text."""
    rendered: dict[int, datetime] = {}
    for r in conn.execute(
        select(postings.c.job_id, artifacts.c.meta_json, artifacts.c.created_at)
        .join(posting_versions, artifacts.c.posting_version_id == posting_versions.c.id)
        .join(postings, posting_versions.c.posting_id == postings.c.id)
        .where(artifacts.c.kind == TAILORED_KIND, postings.c.job_id.is_not(None))
    ):
        if _rendered(r.meta_json):
            job, at = int(r.job_id), _naive(r.created_at)
            if job not in rendered or at < rendered[job]:
                rendered[job] = at
    return rendered


def lead_outcomes(conn: Connection) -> dict[str, Any]:
    """Where every built résumé ended up, in total and per board (the first delivery's source)."""
    first = _first_deliveries(conn)
    rendered = _rendered_jobs(conn)
    dated, undated = _first_applied(conn)
    applied = set(dated) | undated
    # A dated attempt before the first build is evidence the owner applied without it, even when
    # the job also has an undated import. An undated import alone may precede or follow the build:
    # nobody recorded when, so it stays applied.
    before_build = {job for job, at in dated.items() if job in rendered and at < rendered[job]}
    skipped = {
        job: stamp
        for job, raw in skipped_job_ids(conn).items()
        if (stamp := _naive_utc(raw)) is not None
    }

    total = _blank()
    boards: dict[str, dict[str, Any]] = {}
    for job_id, lead in first.items():
        if job_id not in rendered or job_id in before_build:
            continue
        if job_id in applied:
            state = "applied"
        elif job_id in skipped and (lead.closed_at is None or skipped[job_id] <= lead.closed_at):
            state = "skipped"
        elif lead.closed_at is not None:
            state = "closed"
        else:
            state = "open"
        for row in (total, boards.setdefault(lead.board, _blank())):
            row["built"] += 1
            row[state] += 1
    return {
        "not_rendered_leads": sum(1 for job_id in first if job_id not in rendered),
        "applied_before_build_leads": sum(1 for job_id in first if job_id in before_build),
        "totals": _rates(total),
        "boards": [
            {"board": name, **_rates(row)}
            for name, row in sorted(boards.items(), key=lambda kv: (-kv[1]["built"], kv[0]))
        ],
    }
