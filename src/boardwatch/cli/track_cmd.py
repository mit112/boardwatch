"""track: your application funnel (D31).

boardwatch never submits an application. This group records what you did, so the state is
yours to advance. Every move appends an immutable application_events row, which is why
there is no edit or delete verb.
"""

from __future__ import annotations

from typing import get_args

import typer
from rich.console import Console
from rich.table import Table

from boardwatch.cli.context import build_context
from boardwatch.store.applications import (
    ApplicationStatus,
    create_application,
    get_application,
    get_application_events,
    get_applications,
    set_application_status,
)
from boardwatch.store.funnel_queries import job_id_for_posting, list_funnel
from boardwatch.store.queries import current_posting_versions

track_app = typer.Typer(no_args_is_help=True, help="Track your own applications.")
console = Console()

_STATUSES: tuple[str, ...] = get_args(ApplicationStatus)


def _validate_status(value: str) -> str:
    if value not in _STATUSES:
        raise typer.BadParameter(
            f"{value!r} is not a status. Choose one of: {', '.join(_STATUSES)}."
        )
    return value


@track_app.command("add")
def add(
    ctx: typer.Context,
    posting_id: int = typer.Argument(..., help="Posting id from `top` or `show`."),
    status: str = typer.Option("interested", "--status", help="Starting status."),
    new_attempt: bool = typer.Option(
        False, "--new-attempt", help="Start a new attempt even if the job is already tracked."
    ),
) -> None:
    """Start tracking a posting."""
    _validate_status(status)
    app_ctx = build_context(ctx.obj)
    with app_ctx.engine.begin() as conn:
        job_id = job_id_for_posting(conn, posting_id)
        if job_id is None:
            console.print(f"no posting {posting_id}. Run `boardwatch top` to see ids.")
            raise typer.Exit(code=1)
        existing = get_applications(conn, job_id)
        if existing and not new_attempt:
            first = existing[0]
            console.print(
                f"already tracking posting {posting_id} as application "
                f"{first.id} ({first.status})"
            )
            return
        # A4: link the posting version the application was made against.
        versions = current_posting_versions(conn, [posting_id])
        version_id = versions[posting_id].posting_version_id if posting_id in versions else None
        application_id = create_application(
            conn,
            job_id=job_id,
            posting_version_id=version_id,
            status=status,  # type: ignore[arg-type]
            source="user",
        )
    console.print(f"tracking posting {posting_id} as application {application_id} ({status})")


@track_app.command("status")
def status_(
    ctx: typer.Context,
    application_id: int = typer.Argument(..., help="Application id from `track list`."),
    status: str = typer.Argument(..., help="New status."),
    note: str | None = typer.Option(None, "--note", help="Free-text note for the ledger."),
) -> None:
    """Move an application to a new status."""
    _validate_status(status)
    app_ctx = build_context(ctx.obj)
    with app_ctx.engine.begin() as conn:
        if get_application(conn, application_id) is None:
            console.print(f"no application {application_id}. Run `boardwatch track list`.")
            raise typer.Exit(code=1)
        set_application_status(
            conn,
            application_id=application_id,
            to_status=status,  # type: ignore[arg-type]
            source="user",
            note=note,
        )
    console.print(f"application {application_id} is now {status}")


@track_app.command("list")
def list_(
    ctx: typer.Context,
    status: str | None = typer.Option(None, "--status", help="Show only this status."),
) -> None:
    """Show your funnel, most recently touched first."""
    if status is not None:
        _validate_status(status)
    app_ctx = build_context(ctx.obj)
    with app_ctx.engine.connect() as conn:
        rows = list_funnel(conn, status=status)
    if not rows:
        console.print("nothing tracked yet. Add one with `boardwatch track add <posting id>`.")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("App", style="dim")
    table.add_column("Posting", style="dim")
    table.add_column("Title")
    table.add_column("Company")
    table.add_column("Status")
    table.add_column("Try", style="dim")
    for row in rows:
        table.add_row(
            str(row.application_id),
            str(row.posting_id) if row.posting_id is not None else "-",
            row.title or "(posting no longer stored)",
            row.company or "-",
            row.status,
            str(row.attempt_no),
        )
    console.print(table)


@track_app.command("log")
def log(
    ctx: typer.Context,
    application_id: int = typer.Argument(..., help="Application id from `track list`."),
) -> None:
    """Show the immutable event ledger for one application."""
    app_ctx = build_context(ctx.obj)
    with app_ctx.engine.connect() as conn:
        if get_application(conn, application_id) is None:
            console.print(f"no application {application_id}. Run `boardwatch track list`.")
            raise typer.Exit(code=1)
        events = get_application_events(conn, application_id)
    table = Table(show_header=True, header_style="bold")
    table.add_column("When")
    table.add_column("Event")
    table.add_column("From")
    table.add_column("To")
    table.add_column("Note", overflow="fold")
    for event in events:
        table.add_row(
            event.occurred_at.isoformat(timespec="seconds"),
            event.event_type,
            event.from_status or "-",
            event.to_status or "-",
            event.note or "",
        )
    console.print(table)
