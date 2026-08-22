"""boardwatch coverage — what each board states it holds, against what we actually hold.

Strictly read-only (§CLAUDE.md): opens a plain `engine.connect()`, issues only SELECTs via
`load_board_coverage`, and never calls `ensure_schema`'s migration path — the same reasoning
`doctor_cmd.py` gives for `ensure=False`, except `coverage` has no writes of its own to guard
against in the first place.
"""

from __future__ import annotations

import json
from dataclasses import asdict

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from boardwatch.cli.context import build_context
from boardwatch.cli.doctor_cmd import _db_revision
from boardwatch.reports.board_coverage import BoardCoverage, build_report
from boardwatch.store.coverage_queries import load_board_coverage
from boardwatch.store.tables import runs

console = Console()


def _ratio_text(board: BoardCoverage) -> str:
    return "—" if board.ratio is None else f"{100 * board.ratio:.1f}%"


def _shortfall_text(board: BoardCoverage) -> str:
    return "—" if board.shortfall is None else f"{board.shortfall:+,}"


def coverage(
    ctx: typer.Context,
    run: int | None = typer.Option(None, "--run", help="Scan run to report. Default: latest."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON instead of a table."),
) -> None:
    """Per-board discovery coverage: held postings against each board's stated total."""
    app_ctx = build_context(ctx.obj, ensure=False)

    # Fix round 1, finding 2: `ensure=False` means a never-`init`'d data dir has no tables at
    # all, and `load_board_coverage` would raise a raw `OperationalError` ("no such table:
    # board_scans") straight out of the CLI. `_db_revision` (`doctor_cmd.py`) is the same probe
    # `doctor` already uses to answer "has this database ever been migrated" — reused rather
    # than re-derived, and it fails the same way doctor does: report and stop, don't traceback.
    with app_ctx.engine.connect() as conn:
        db_revision = _db_revision(conn)
    if db_revision is None:
        console.print("schema: ABSENT — run `boardwatch init` first")
        raise typer.Exit(code=1)

    with app_ctx.engine.connect() as conn:
        # Fix round 1, minor 2: an unrecognised --run must say so, distinctly from "this run
        # exists and genuinely scanned nothing" (which now renders as an all-`unscanned` report
        # per finding 1's LEFT JOIN fix, not as an empty one).
        run_exists = conn.execute(select(runs.c.id).where(runs.c.id == run)).first() is not None
        if run is not None and not run_exists:
            console.print(f"[red]no such run: {run}[/red]")
            raise typer.Exit(code=1)
        report = build_report(load_board_coverage(conn, run_id=run))

    if as_json:
        typer.echo(
            json.dumps(
                {
                    "bucket_counts": report.bucket_counts,
                    "measured_held": report.measured_held,
                    "measured_total": report.measured_total,
                    "measured_zero_total": report.measured_zero_total,
                    "global_ratio": report.global_ratio,
                    "corpus_boards": report.corpus_boards,
                    "boards": [asdict(b) for b in report.boards],
                },
                indent=2,
            )
        )
        return

    table = Table("ratio", "bucket", "board", "held", "stated", "shortfall")
    # Worst coverage first; boards with no ratio (the other five buckets, plus a measured
    # board stating a total of zero) sort after every real ratio, in the order they came in.
    # `is not None`, not truthiness: a literal 0.0 ratio must sort with the real ratios, not
    # silently join the no-ratio boards at the bottom (fix round 1, minor 3).
    for b in sorted(
        report.boards, key=lambda x: (x.ratio is None, x.ratio if x.ratio is not None else 0.0)
    ):
        table.add_row(
            _ratio_text(b),
            b.bucket,
            f"{b.provider}:{b.name}",
            f"{b.held:,}",
            "—" if b.board_reported_total is None else f"{b.board_reported_total:,}",
            _shortfall_text(b),
        )
    console.print(table)

    counts = Table("bucket", "count")
    for bucket, n in report.bucket_counts.items():
        counts.add_row(bucket, str(n))
    console.print(counts)

    ratio = "not measurable" if report.global_ratio is None else f"{100 * report.global_ratio:.1f}%"
    console.print(
        f"measured coverage {ratio} ({report.measured_held:,} held of "
        f"{report.measured_total:,} stated) over {report.bucket_counts['measured']} of "
        f"{report.corpus_boards} watched boards"
    )
    # Fix round 1, minor 1: printed unconditionally, even at zero. A "0" line is evidence the
    # check ran; an absent line is ambiguous between "checked, found none" and "never checked".
    zero_total_note = (
        f"{report.measured_zero_total} measured board(s) state a total of 0 and are excluded "
        "from that ratio's numerator and denominator, not folded into it."
    )
    if report.measured_zero_total:
        console.print(f"[yellow]{zero_total_note}[/yellow]")
    else:
        console.print(zero_total_note)
