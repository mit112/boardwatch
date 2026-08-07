"""Reconciliation core for `boardwatch verify` — P0 item 5 (D-030).

Pure: typed counts + filesystem-existence facts in, typed `Discrepancy` tuple out. No engine,
no clock, no filesystem — the CLI glue resolves all of those and hands this module facts.

Two invariant classes:
  * Class A — the frozen funnel artifact's run-keyed counts vs a fresh independent store
    re-query. A serialize-then-reload consistency check on immutable run-keyed rows: it fails
    only if the write serialized a different number than it stamped, or the rows were later
    mutated/deleted. Eval count and timestamps are NOT reconciled — they are identity-scoped or
    format-fragile and can only fail for the wrong reason (design §4).
  * Class B — every run-keyed tailored artifact the DB records must exist on disk. This is the
    genuinely-different path CLAUDE.md demands: "count the deliverable through a different path
    than the one that produced it." A row claiming a PDF with no file is the silent degrade B6
    exists to catch.

The catalog is CLOSED: `DiscrepancyKind` is constructed at the raise site so out-of-catalog is
impossible. `NO_ARTIFACT` and `MALFORMED_FUNNEL` are built by the glue (before counts exist) but
live in the catalog so a parse failure maps to a typed kind rather than crashing the sweep.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

TAILORED_KIND = "resume_tailored"


class DiscrepancyKind(StrEnum):
    NO_ARTIFACT = "no_artifact"
    MALFORMED_FUNNEL = "malformed_funnel"
    TAILORED_COUNT_MISMATCH = "tailored_count_mismatch"
    PDF_COUNT_MISMATCH = "pdf_count_mismatch"
    LEAD_COUNT_MISMATCH = "lead_count_mismatch"
    STATUS_MISMATCH = "status_mismatch"
    MISSING_TYP_FILE = "missing_typ_file"
    MISSING_PDF_FILE = "missing_pdf_file"


@dataclass(frozen=True)
class Discrepancy:
    run_id: int
    kind: DiscrepancyKind
    expected: str | None = None
    actual: str | None = None
    path: str | None = None
    note: str = ""


@dataclass(frozen=True)
class ArtifactCounts:
    """Run-keyed quantities read out of the frozen funnel JSON. `status` is None for a v2 /
    no-manifest artifact, which suppresses the status comparison rather than erroring."""

    tailored_rows: int
    tailored_with_pdf: int
    lead_count: int
    status: str | None


@dataclass(frozen=True)
class DbCounts:
    """The same quantities re-queried from the store now, through a different query surface."""

    tailored_rows: int
    tailored_with_pdf: int
    distinct_lead_postings: int
    run_status: str


@dataclass(frozen=True)
class FileCheck:
    """One tailored artifact's on-disk existence. `typ_exists`/`pdf_exists` are resolved by the
    glue (the only layer allowed to stat), never here. `pdf_expected` is True only for a
    resume_tailored row whose meta says a PDF was built; resume_tailored_llm never expects one."""

    kind: str
    typ_uri: str
    typ_exists: bool
    pdf_expected: bool
    pdf_uri: str | None
    pdf_exists: bool


@dataclass(frozen=True)
class ReconcileReport:
    run_id: int
    discrepancies: tuple[Discrepancy, ...]

    @property
    def ok(self) -> bool:
        return not self.discrepancies


def reconcile(
    *, run_id: int, artifact: ArtifactCounts, db: DbCounts, files: Sequence[FileCheck]
) -> ReconcileReport:
    found: list[Discrepancy] = []

    # Class A — frozen self-report vs fresh independent re-query, run-keyed immutables only.
    if artifact.tailored_rows != db.tailored_rows:
        found.append(Discrepancy(
            run_id, DiscrepancyKind.TAILORED_COUNT_MISMATCH,
            expected=str(artifact.tailored_rows), actual=str(db.tailored_rows),
            note="frozen resume_tailored count vs fresh store re-query",
        ))
    if artifact.tailored_with_pdf != db.tailored_with_pdf:
        found.append(Discrepancy(
            run_id, DiscrepancyKind.PDF_COUNT_MISMATCH,
            expected=str(artifact.tailored_with_pdf), actual=str(db.tailored_with_pdf),
            note="frozen pdf-built count vs fresh store re-query",
        ))
    if artifact.lead_count != db.distinct_lead_postings:
        found.append(Discrepancy(
            run_id, DiscrepancyKind.LEAD_COUNT_MISMATCH,
            expected=str(artifact.lead_count), actual=str(db.distinct_lead_postings),
            note="len(leads) vs DISTINCT posting_version_id over resume_tailored rows",
        ))
    # None means the artifact predates the manifest (v2); skipped rather than compared.
    if artifact.status is not None and artifact.status != db.run_status:
        found.append(Discrepancy(
            run_id, DiscrepancyKind.STATUS_MISMATCH,
            expected=artifact.status, actual=db.run_status,
            note="manifest.status vs runs.status — a post-hoc mutation anomaly",
        ))

    # Class B — the deliverable through a different path: the filesystem.
    for check in files:
        if not check.typ_exists:
            found.append(Discrepancy(
                run_id, DiscrepancyKind.MISSING_TYP_FILE, path=check.typ_uri, note=check.kind,
            ))
        if check.pdf_expected and not check.pdf_exists:
            found.append(Discrepancy(
                run_id, DiscrepancyKind.MISSING_PDF_FILE,
                path=check.pdf_uri or "", note=check.kind,
            ))

    return ReconcileReport(run_id=run_id, discrepancies=tuple(found))


def reconcile_to_dict(reports: Sequence[ReconcileReport]) -> dict[str, object]:
    return {
        "ok": all(report.ok for report in reports),
        "runs_checked": len(reports),
        "reports": [
            {
                "run_id": report.run_id,
                "ok": report.ok,
                "discrepancies": [
                    {
                        "kind": str(disc.kind),
                        "expected": disc.expected,
                        "actual": disc.actual,
                        "path": disc.path,
                        "note": disc.note,
                    }
                    for disc in report.discrepancies
                ],
            }
            for report in reports
        ],
    }


def reconcile_to_markdown(reports: Sequence[ReconcileReport]) -> str:
    verdict = "RECONCILES" if all(report.ok for report in reports) else "DOES NOT RECONCILE"
    lines = [
        "# boardwatch verify — DB ↔ artifact reconciliation",
        "",
        f"- **runs checked:** {len(reports)}",
        f"- **verdict:** {verdict}",
        "",
    ]
    if not reports:
        lines.append("no funnel artifacts found to verify.")
        return "\n".join(lines) + "\n"
    for report in reports:
        mark = "**yes**" if report.ok else "**NO**"
        lines += [f"## run {report.run_id} — reconciles: {mark}", ""]
        if report.ok:
            lines += ["no discrepancies.", ""]
            continue
        lines += ["| kind | expected | actual | path | note |", "|---|---|---|---|---|"]
        for disc in report.discrepancies:
            lines.append(
                f"| {disc.kind} | {disc.expected or '—'} | {disc.actual or '—'} | "
                f"{disc.path or '—'} | {disc.note or '—'} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"
