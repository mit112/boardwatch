"""boardwatch verify — DB ↔ artifact reconciliation (P0 item 5, D-030).

The only layer that touches the store, the funnel JSON on disk, AND the filesystem. It resolves
which artifacts to check, loads each (a parse/field failure becomes a typed MALFORMED_FUNNEL, not
an exception), re-queries the store, stats every tailored file, hands the pure core its facts,
prints the report, and sets the exit code. Read-only: it reports, never fixes.

Two modes with an explicit exit policy:
  * `--run X` verifies exactly that run; a missing artifact is NO_ARTIFACT and a non-zero exit —
    you asked for a run that cannot be verified.
  * no `--run` sweeps every funnel-*.json present on disk and verifies each. It does not demand
    an artifact per runs-table row: pre-item-1 runs legitimately have none, so a run with no
    on-disk artifact is out of scope, not a silent pass.

Exit 0 iff every EXAMINED artifact reconciles with zero discrepancies.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from sqlalchemy import Engine

from boardwatch.cli.context import build_context
from boardwatch.cli.run_cmd import DEFAULT_OUT_ROOT
from boardwatch.reports.reconcile import (
    ArtifactCounts,
    Discrepancy,
    DiscrepancyKind,
    FileCheck,
    ReconcileReport,
    reconcile,
    reconcile_to_markdown,
)
from boardwatch.store.reconcile_queries import (
    TailoredFileRow,
    db_counts_for_run,
    tailored_file_rows,
)

console = Console()


def verify(
    ctx: typer.Context,
    run: int | None = typer.Option(
        None, "--run", help="Verify one run by id (default: sweep every artifact on disk)."
    ),
    out_root: Path = typer.Option(  # noqa: B008
        DEFAULT_OUT_ROOT, "--out-root", help="Where per-run funnel artifacts were written."
    ),
) -> None:
    """Assert the DB rows and on-disk artifacts for a run (or all runs) agree."""
    engine = build_context(ctx.obj).engine
    if run is not None:
        path = _resolve_run_artifact(out_root, run)
        if path is None:
            reports = [ReconcileReport(run, (Discrepancy(
                run, DiscrepancyKind.NO_ARTIFACT,
                note="no funnel artifact on disk for the requested run",
            ),))]
        else:
            reports = [_verify_one(engine, path, run)]
    else:
        reports = []
        for path in sorted(out_root.glob("*/funnel-*.json")):
            run_id = _run_id_from_name(path)
            if run_id is not None:
                reports.append(_verify_one(engine, path, run_id))

    console.print(reconcile_to_markdown(reports), markup=False)
    if not all(report.ok for report in reports):
        raise typer.Exit(code=1)


def _resolve_run_artifact(out_root: Path, run_id: int) -> Path | None:
    """Locate funnel-<id>.json by globbing the day-folders, NOT by reconstructing the path from
    the run's start date. The glob finds an artifact even when its `runs` row was deleted — the
    orphaned-artifact case whose `run_status=""` anomaly the reconciliation exists to surface.
    The numeric filename is exact (`funnel-7.json` never matches `funnel-70.json`)."""
    return next(iter(sorted(out_root.glob(f"funnel-{run_id}.json"))
                     or sorted(out_root.glob(f"*/funnel-{run_id}.json"))), None)


def _run_id_from_name(path: Path) -> int | None:
    # funnel-<id>.json -> <id>
    try:
        return int(path.stem.split("-", 1)[1])
    except (IndexError, ValueError):
        return None


def _verify_one(engine: Engine, path: Path, run_id: int) -> ReconcileReport:
    try:
        artifact = _artifact_counts(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, OSError) as exc:
        return ReconcileReport(run_id, (Discrepancy(
            run_id, DiscrepancyKind.MALFORMED_FUNNEL, note=f"{type(exc).__name__}: {exc}",
        ),))
    with engine.connect() as conn:
        db = db_counts_for_run(conn, run_id)
        file_rows = tailored_file_rows(conn, run_id)
    files = tuple(_file_check(row) for row in file_rows)
    return reconcile(run_id=run_id, artifact=artifact, db=db, files=files)


def _artifact_counts(data: dict[str, object]) -> ArtifactCounts:
    """Pull the four reconcilable quantities out of the frozen funnel JSON. A missing key raises
    KeyError/TypeError, which the caller maps to MALFORMED_FUNNEL."""
    checks = {check["name"]: check for check in data["cross_checks"]}  # type: ignore[attr-defined]
    manifest = data.get("manifest") or {}
    status = manifest.get("status") if isinstance(manifest, dict) else None
    return ArtifactCounts(
        tailored_rows=int(checks["tailored"]["from_store"]),
        tailored_with_pdf=int(checks["leads_with_pdf"]["from_store"]),
        lead_count=len(data["leads"]),  # type: ignore[arg-type]
        status=status if isinstance(status, str) else None,
    )


def _file_check(row: TailoredFileRow) -> FileCheck:
    pdf_expected = row.kind == "resume_tailored" and row.pdf_built
    pdf_exists = bool(row.pdf_uri) and Path(row.pdf_uri).exists()  # type: ignore[arg-type]
    return FileCheck(
        kind=row.kind,
        typ_uri=row.typ_uri,
        typ_exists=Path(row.typ_uri).exists(),
        pdf_expected=pdf_expected,
        pdf_uri=row.pdf_uri,
        pdf_exists=pdf_exists,
    )
