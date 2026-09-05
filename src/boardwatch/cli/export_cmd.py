"""export: take your data with you.

Writes every open or tracked posting with its eligibility verdict and your funnel state
as a flat snapshot (A6). Runs the eligibility preflight first so an export reflects the
current profile rather than a stale verdict, matching what `top` shows. Preflight
progress and the confirmation go to stderr; stdout carries ONLY data rows, so
`boardwatch export --format jsonl | jq` stays clean (A3).
"""

from __future__ import annotations

import io
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import IO, Annotated, Any

import typer
from rich.console import Console

from boardwatch.cli._profile_row import refuse_unusable_profile_row
from boardwatch.cli.context import build_context
from boardwatch.eligibility.facts import ProfileRowInvalid
from boardwatch.eligibility.preflight import run_eligibility
from boardwatch.eligibility.read import current_verdicts
from boardwatch.reports.export import export_rows, write_csv, write_jsonl
from boardwatch.store.funnel_queries import list_funnel
from boardwatch.store.queries import current_posting_versions

# A3: chatter goes to stderr, data rows to stdout.
console = Console(stderr=True)

_WRITERS = {"jsonl": write_jsonl, "csv": write_csv}


def _write_stdout_utf8(
    writer: Callable[[Iterable[dict[str, Any]], IO[str]], int],
    rows: Iterable[dict[str, Any]],
) -> int:
    """Run `writer` against the real process stdout, encoded as utf-8 regardless of its
    declared text encoding.

    A *redirected* Windows stdout reports the ANSI codepage (e.g. cp1252), not utf-8, so a
    non-ASCII company name written straight through `sys.stdout` raises `UnicodeEncodeError`
    and the export dies. Wrapping `sys.stdout.buffer` locally -- rather than mutating
    `sys.stdout` itself via `.reconfigure()` or reassignment -- keeps every other write in
    this process on its ambient encoding.

    The wrapper is flushed and detached (never left to be garbage-collected) before
    returning: `TextIOWrapper.close()` -- which is what runs if the wrapper is simply
    dropped -- closes the underlying buffer too, and that buffer is `sys.stdout`'s own, so a
    dropped wrapper would break every later write to stdout in the process. `detach()`
    flushes first, then severs the wrapper from the buffer without closing it.

    Some stdout substitutes (e.g. a bare `io.StringIO`) carry no `.buffer` at all; that path
    falls back to writing through `sys.stdout` directly, on its ambient encoding.
    """
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is None:
        return writer(rows, sys.stdout)
    wrapped = io.TextIOWrapper(buffer, encoding="utf-8", newline="")
    try:
        return writer(rows, wrapped)
    finally:
        wrapped.flush()
        wrapped.detach()


def export(
    ctx: typer.Context,
    format_: str = typer.Option("jsonl", "--format", help="jsonl or csv."),
    out: Annotated[
        Path | None, typer.Option("--out", help="Write to this file instead of stdout.")
    ] = None,
) -> None:
    """Export every open or tracked posting with its verdict and your funnel state."""
    writer = _WRITERS.get(format_)
    if writer is None:
        raise typer.BadParameter(
            f"{format_!r} is not a format. Choose jsonl or csv.", param_hint="--format"
        )
    app_ctx = build_context(ctx.obj)
    try:
        stats = run_eligibility(app_ctx.engine, app_ctx.settings, console)
    except ProfileRowInvalid as exc:
        refuse_unusable_profile_row(exc)
    with app_ctx.engine.connect() as conn:
        # Verdict scope: every open posting plus every tracked posting, closed or not, so a
        # closed tracked row carries the identity it was computed under (A6).
        open_versions = current_posting_versions(conn, None)
        tracked_ids = {
            row.posting_id for row in list_funnel(conn) if row.posting_id is not None
        }
        versions = current_posting_versions(conn, sorted(set(open_versions) | tracked_ids))
        verdicts = current_verdicts(
            conn,
            [cv.posting_version_id for cv in versions.values()],
            stats.profile_hash,
            stats.rules_hash,
        )
        # A10: stream the iterator straight to the writer while the connection is open;
        # the writer's return value is the count, so nothing is materialized.
        rows = export_rows(
            conn,
            verdicts=verdicts,
            profile_hash=stats.profile_hash,
            rules_hash=stats.rules_hash,
        )
        if out is None:
            _write_stdout_utf8(writer, rows)
            return
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8", newline="") as stream:
            count = writer(rows, stream)
    console.print(f"wrote {count} rows to {out}")
