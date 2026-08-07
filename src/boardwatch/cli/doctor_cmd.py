"""boardwatch doctor — connectivity, per-board health + freshness, DB integrity (§2.3).

Runtime is healthy-path-only: ~15 boards ≈ seconds when healthy; DEAD/ERROR/
UNREACHABLE paths can take minutes (tenacity retries + timeouts)."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
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

_TYPST_PINNED_VERSION = "0.15.1"


@dataclass
class TypstCheck:
    found: bool
    version: str | None = None
    failed: bool = False  # missing binary — contributes to doctor's non-zero exit
    message: str | None = None  # install guidance (failure) or version-mismatch warning


def check_typst() -> TypstCheck:
    """Probe for the pinned typst binary (résumé PDF gate, P1a). Missing binary is an
    actionable failure; a version other than the pin is a loud warning, not a hard fail —
    the page-count `typst eval` syntax the gate relies on is version-sensitive."""
    if shutil.which("typst") is None:
        return TypstCheck(
            found=False,
            failed=True,
            message=(
                f"typst not found; install typst {_TYPST_PINNED_VERSION} "
                "(https://github.com/typst/typst/releases) — required for the résumé PDF gate"
            ),
        )
    result = subprocess.run(["typst", "--version"], capture_output=True, text=True)
    match = re.search(r"\d+\.\d+\.\d+", result.stdout)
    version = match.group(0) if match else None
    if result.returncode != 0 or version is None:
        # a present binary that fails to run (wrong arch, corrupt install, ...) is exactly
        # as broken as a missing one — the PDF gate cannot use it either way
        return TypstCheck(
            found=True,
            version=version,
            failed=True,
            message=(
                f"typst --version failed (exit {result.returncode}); reinstall typst "
                f"{_TYPST_PINNED_VERSION} — required for the résumé PDF gate"
            ),
        )
    message = None
    if version != _TYPST_PINNED_VERSION:
        message = (
            f"typst version is {version}, pinned version is "
            f"{_TYPST_PINNED_VERSION} — the page-count query syntax is version-sensitive"
        )
    return TypstCheck(found=True, version=version, message=message)


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
    """Connectivity, board health and freshness, and database integrity checks."""
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
            if c.from_fallback and c.fallback_status is None:
                # no watched board AND no catalog entry to probe (Workday ships none by
                # design, rule R8): nothing was checked, so "NO" would be a false negative
                conn_table.add_row(c.provider, "not checked (no registry entry)")
                continue
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
    if any(w.provider == "smartrecruiters" and w.last_health == "empty" for w in watches):
        console.print(
            "\n[dim]* SmartRecruiters returns an empty board for unknown companies, so "
            "'empty' here is unverifiable — it may be a typo'd slug.[/dim]"
        )
    if running:
        # Deliberately not "a scan is in progress": since run attribution landed, an
        # unfinished run is also a `boardwatch run` still tailoring, or a standalone
        # eligibility pass still judging. Naming it a scan sent users looking for a held
        # scan lock that is in fact free.
        console.print(f"[yellow]a run is in progress (run {running.id})[/yellow]")

    # schema check compares the DB's applied revision against the code's expected script head
    schema_ok = db_revision == schema_revision()
    integrity_ok = integrity == "ok"
    console.print(f"boardwatch {package_version('boardwatch')}")
    console.print(
        f"integrity: {integrity} · schema: "
        f"{'ok' if schema_ok else f'MISMATCH (db={db_revision}, code={schema_revision()})'}"
    )

    typst_check = check_typst()
    console.print(f"typst: {typst_check.version or 'NOT FOUND'}")
    if typst_check.failed:
        console.print(f"[red]{typst_check.message}[/red]")
    elif typst_check.message:
        console.print(f"[yellow]{typst_check.message}[/yellow]")

    failed = report.actionable or not integrity_ok or not schema_ok or typst_check.failed
    raise typer.Exit(code=1 if failed else 0)
