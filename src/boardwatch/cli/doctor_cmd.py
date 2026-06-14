"""boardwatch doctor — connectivity, per-board health + freshness, DB integrity (§2.3).

Runtime is healthy-path-only: ~15 boards ≈ seconds when healthy; DEAD/ERROR/
UNREACHABLE paths can take minutes (tenacity retries + timeouts)."""

from __future__ import annotations

from importlib.metadata import version as package_version

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import Connection, select, text
from sqlalchemy.exc import OperationalError

from boardwatch.cli.context import build_context
from boardwatch.core.clock import utcnow
from boardwatch.scan.coordinator import default_providers
from boardwatch.scan.health import probe_health
from boardwatch.store import tables
from boardwatch.store.db import schema_revision
from boardwatch.store.queries import last_complete_scan_ages

console = Console()


def _db_revision(conn: Connection) -> str | None:
    """The DB's applied Alembic revision, or None if the DB is unversioned/uninitialized."""
    try:
        result = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    except OperationalError:  # alembic_version table absent → schema never applied
        return None
    return str(result) if result is not None else None


def _integrity_check(conn: Connection) -> str:
    """PRAGMA integrity_check result ('ok' on a healthy DB). A module-level seam so tests
    can force a corruption result without writing bad SQLite pages."""
    return str(conn.execute(text("PRAGMA integrity_check")).scalar_one())


def doctor(ctx: typer.Context, offline: bool = typer.Option(False, "--offline")) -> None:
    # ensure=False (context.py supports it): doctor must INSPECT the schema, never migrate it —
    # otherwise a corrupted/absent revision would be silently upgraded before we could report it
    app_ctx = build_context(ctx.obj, ensure=False)

    with app_ctx.engine.connect() as conn:
        db_revision = _db_revision(conn)
    schema_ok = db_revision == schema_revision()
    if db_revision is None:  # absent/unversioned schema — report and stop before probing
        console.print(f"boardwatch {package_version('boardwatch')}")
        console.print("schema: ABSENT (run a boardwatch command that initializes the database)")
        raise typer.Exit(code=1)

    report = probe_health(app_ctx.engine, app_ctx.settings, offline=offline)

    with app_ctx.engine.connect() as conn:
        ages = last_complete_scan_ages(conn)
        watches = conn.execute(
            select(tables.companies).where(tables.companies.c.watched.is_(True))
        ).all()
        running = conn.execute(
            select(tables.runs.c.id).where(tables.runs.c.finished_at.is_(None))
        ).first()
        integrity = _integrity_check(conn)

    # connectivity: offline renders "not checked" for EVERY registered provider (not just those
    # with watches — the offline contract); online renders the probed result
    conn_table = Table("provider", "reachable")
    if offline:
        for provider in sorted(default_providers()):
            conn_table.add_row(provider, "not checked")
    else:
        for c in report.connectivity:
            label = "yes" if c.reachable else "NO"
            conn_table.add_row(c.provider, label + (" (fallback)" if c.from_fallback else ""))
    console.print(conn_table)

    # per-board health + freshness; freshness renders an AGE (duration), not a raw timestamp;
    # offline renders the STORED columns (last_health + last_ok_at)
    now = utcnow()
    health_table = Table("board", "last_health", "last_ok_at", "last_complete_scan_age")
    for w in watches:
        stored = " (stored)" if offline else ""
        ts = ages.get(w.id)
        age = "never" if ts is None else f"{(now - ts).days}d ago"
        health_table.add_row(
            f"{w.provider}:{w.slug}", (w.last_health or "—") + stored,
            str(w.last_ok_at or "—"), age,
        )
    console.print(health_table)
    if running:
        console.print(f"[yellow]a scan is in progress (run {running.id})[/yellow]")

    # schema check compares the DB's applied revision against the code's expected script head
    schema_ok = db_revision == schema_revision()
    integrity_ok = integrity == "ok"
    console.print(f"boardwatch {package_version('boardwatch')}")
    console.print(
        f"integrity: {integrity} · schema: "
        f"{'ok' if schema_ok else f'MISMATCH (db={db_revision}, code={schema_revision()})'}"
    )

    failed = report.actionable or not integrity_ok or not schema_ok
    raise typer.Exit(code=1 if failed else 0)
