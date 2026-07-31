"""digest: what changed since you last looked (D18).

Reads the event window past the stored cursor, renders it, and advances the cursor.
Issues BEGIN IMMEDIATE before the first cursor read so two concurrent digests cannot
both read the same window (A1). --peek renders without advancing.

A crash after terminal output can still re-render a window. Exactly-once terminal
rendering is not achievable transactionally, and claiming it would be false.
"""

from __future__ import annotations

from collections.abc import Callable

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import text

from boardwatch.cli.context import build_context
from boardwatch.reports.digest import DigestEntry, DigestSummary, summarize_events
from boardwatch.store.app_state import get_digest_cursor, set_digest_cursor

console = Console()

# Explicit accessors rather than getattr: mypy --strict cannot type a getattr lookup, and
# a typo in a section name would then only surface at runtime.
_SECTIONS: tuple[tuple[str, Callable[[DigestSummary], tuple[DigestEntry, ...]]], ...] = (
    ("New", lambda s: s.new),
    ("Reopened", lambda s: s.reopened),
    ("Updated", lambda s: s.revised),
)


def render(summary: DigestSummary) -> None:
    for heading, accessor in _SECTIONS:
        entries = accessor(summary)
        if not entries:
            continue
        table = Table(title=heading, show_header=True, header_style="bold", title_justify="left")
        table.add_column("#", style="dim")
        table.add_column("Title")
        table.add_column("Company")
        for entry in entries:
            table.add_row(str(entry.posting_id), entry.title, entry.company)
        console.print(table)
    if summary.closed_count:
        console.print(f"{summary.closed_count} closed since your last digest.")


def digest(
    ctx: typer.Context,
    peek: bool = typer.Option(
        False, "--peek", help="Show the same digest without advancing the cursor."
    ),
) -> None:
    """New, reopened, updated and closed postings since your last digest."""
    app_ctx = build_context(ctx.obj)
    with app_ctx.engine.connect() as conn:
        # A1: BEGIN IMMEDIATE serializes before the first cursor read so two
        # overlapping digests cannot read the same window.
        conn.execute(text("BEGIN IMMEDIATE"))
        try:
            summary = summarize_events(conn, get_digest_cursor(conn))
            if summary.is_empty:
                console.print("nothing new since your last digest")
                return
            render(summary)
            if not peek:
                set_digest_cursor(conn, summary.max_event_id)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    if peek:
        console.print("peeked, so the cursor did not move")
