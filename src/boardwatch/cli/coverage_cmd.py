"""boardwatch coverage — what each board states it holds, against what we actually hold.

This is BOARD DISCOVERY coverage. It is unrelated to `tailor/coverage.py`, which measures how
much of a job description's keyword set a résumé covers, and to the `coverage` key in the
funnel artifact, which is that one. Every internal name and JSON key here is `board_coverage`.

Read-only apart from `get_engine`: it issues only SELECTs via `load_board_coverage` and never
calls `ensure_schema`'s migration path, for the reason `doctor_cmd.py` gives for `ensure=False`.
It is not read-only at the FILESYSTEM, though — `build_context` calls `get_engine`, which
`mkdir(parents=True)`s the data dir and lets SQLite create an empty database file, so
`boardwatch --data-dir <nonexistent> coverage` leaves both behind before reporting that the
schema is absent. Harmless, shared with `doctor`, and stated here rather than contradicted.
"""

from __future__ import annotations

import json
from dataclasses import asdict

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from boardwatch.cli.context import build_context
from boardwatch.reports.board_coverage import BoardCoverage, build_report
from boardwatch.store.coverage_queries import load_board_coverage
from boardwatch.store.db import db_revision, schema_revision
from boardwatch.store.tables import runs

console = Console()


def _ratio_text(board: BoardCoverage) -> str:
    return "—" if board.ratio is None else f"{100 * board.ratio:.1f}%"


def _shortfall_text(board: BoardCoverage) -> str:
    return "—" if board.shortfall is None else f"{board.shortfall:+,}"


def coverage(
    ctx: typer.Context,
    run: int | None = typer.Option(
        None,
        "--run",
        help=(
            "Scan run to report. Default: latest. The board totals come from this run, but "
            "`held` is counted as of NOW, not as of the run."
        ),
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON instead of a table."),
) -> None:
    """Per-board BOARD DISCOVERY coverage: held postings against each board's stated total.

    Not resume keyword coverage (that is `tailor/coverage.py`, reported in the funnel).
    """
    app_ctx = build_context(ctx.obj, ensure=False)

    # `ensure=False` means nothing on this path ever migrates, so the schema can be absent OR
    # merely old, and BOTH end in a raw traceback out of the CLI: no `board_scans` table at all
    # ("no such table"), or a pre-D-271 revision with the table but none of its four coverage
    # columns ("no such column: board_scans.board_reported_total"). Reproduced by stamping a
    # store back to `p_seniority_band` and dropping the columns. `doctor` already compares
    # against `schema_revision()` rather than checking for absence; this does the same, and
    # fails the way doctor does — report and stop, do not traceback.
    with app_ctx.engine.connect() as conn:
        revision = db_revision(conn)
    if revision is None:
        console.print("schema: ABSENT — run `boardwatch init` first")
        raise typer.Exit(code=1)
    if revision != schema_revision():
        console.print(
            f"schema: STALE — run `boardwatch init` "
            f"(db={revision}, code={schema_revision()})"
        )
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
                    "censored_shortfall": report.censored_shortfall,
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
    # The censored boards publish NO ratio, so they contribute nothing to the line above — and
    # they hold the biggest known holes in the corpus (Citi: 600 held against a facet-recovered
    # 4,589). Printed unconditionally for the same reason as the note above.
    censored_n = report.bucket_counts["censored"]
    if report.censored_shortfall is None:
        console.print(
            f"{censored_n} censored board(s) recovered no uncapped total, so their shortfall "
            "is UNKNOWN, not zero; no ratio is published for them."
        )
    else:
        console.print(
            f"[yellow]{censored_n} censored board(s) are short {report.censored_shortfall:,} "
            "postings against their facet-recovered totals; no ratio is published for "
            "them.[/yellow]"
        )
    # `--run` selects which run's stated totals are read; `held` is a live count of open
    # postings and has no run dimension (store/coverage_queries.py). Stated rather than fixed:
    # making `held` run-scoped is a larger change than this report.
    console.print(
        "held is counted as of now, not as of the selected run; stated totals are the "
        "selected run's."
    )
