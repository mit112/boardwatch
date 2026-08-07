"""The independent re-query reads for `boardwatch verify` (P0 item 5).

A DIFFERENT query surface from `run_funnel_queries.py` on purpose: reusing
`count_tailored_artifacts` would re-count through the same code the artifact used, defeating the
"different path" mandate. These are simple `WHERE run_id = X` reads — the independence that
matters is the CLI's filesystem stat (Class B), not query cleverness. The eval count is NOT
re-queried here: it is identity-scoped in the artifact and a naive COUNT would fail for the wrong
reason (design §4).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Connection, case, func, select

from boardwatch.reports.reconcile import TAILORED_KIND, DbCounts
from boardwatch.store.tables import artifacts, runs

TAILORED_LLM_KIND = "resume_tailored_llm"


@dataclass(frozen=True)
class TailoredFileRow:
    """A tailored artifact's on-disk references, before any stat. `pdf_uri` is None for an
    LLM row (its meta carries no PDF) or a Tier-A row that never built one."""

    kind: str
    typ_uri: str
    pdf_built: bool
    pdf_uri: str | None


def db_counts_for_run(conn: Connection, run_id: int) -> DbCounts:
    """Class-A counts, re-derived from the store now. NULL-run_id rows excluded by the filter."""
    pdf_built = func.json_extract(artifacts.c.meta_json, "$.typst_pdf_built")
    rows, with_pdf = conn.execute(
        select(
            func.count(),
            func.coalesce(func.sum(case((pdf_built == 1, 1), else_=0)), 0),
        ).where(artifacts.c.run_id == run_id, artifacts.c.kind == TAILORED_KIND)
    ).one()
    distinct_leads = conn.execute(
        select(func.count(func.distinct(artifacts.c.posting_version_id))).where(
            artifacts.c.run_id == run_id, artifacts.c.kind == TAILORED_KIND
        )
    ).scalar_one()
    status = conn.execute(
        select(runs.c.status).where(runs.c.id == run_id)
    ).scalar_one_or_none()
    return DbCounts(
        tailored_rows=int(rows),
        tailored_with_pdf=int(with_pdf),
        distinct_lead_postings=int(distinct_leads),
        # "" (never a valid status) when the run row is gone but the artifact remains — itself an
        # anomaly a manifest-bearing artifact will surface as STATUS_MISMATCH.
        run_status=status if status is not None else "",
    )


def tailored_file_rows(conn: Connection, run_id: int) -> tuple[TailoredFileRow, ...]:
    """Every run-keyed tailored artifact (both tiers), with the paths the CLI will stat."""
    pdf_built = func.json_extract(artifacts.c.meta_json, "$.typst_pdf_built")
    pdf_uri = func.json_extract(artifacts.c.meta_json, "$.pdf_uri")
    rows = conn.execute(
        select(artifacts.c.kind, artifacts.c.uri, pdf_built, pdf_uri).where(
            artifacts.c.run_id == run_id,
            artifacts.c.kind.in_([TAILORED_KIND, TAILORED_LLM_KIND]),
        )
    ).all()
    return tuple(
        TailoredFileRow(
            kind=str(row[0]),
            typ_uri=str(row[1]),
            pdf_built=row[2] == 1,
            pdf_uri=str(row[3]) if row[3] is not None else None,
        )
        for row in rows
    )
