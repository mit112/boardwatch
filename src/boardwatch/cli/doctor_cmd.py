"""boardwatch doctor — connectivity, per-board health + freshness, DB integrity (§2.3).

Runtime is healthy-path-only: ~15 boards ≈ seconds when healthy; DEAD/ERROR/
UNREACHABLE paths can take minutes (tenacity retries + timeouts)."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import timedelta
from importlib.metadata import version as package_version

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import Connection, select, text

from boardwatch.cli.context import build_context
from boardwatch.core.clock import utcnow
from boardwatch.scan.coordinator import default_providers
from boardwatch.scan.health import probe_health
from boardwatch.store import tables
from boardwatch.store.db import db_revision, schema_revision
from boardwatch.store.queries import RUN_RUNNING, last_complete_scan_ages, reap_stale_runs

console = Console()

_TECTONIC_MIN_VERSION = (0, 15, 0)


@dataclass(frozen=True)
class TectonicCheck:
    available: bool
    version: str | None
    failed: bool  # missing/broken binary — contributes to doctor's non-zero exit
    warning: str | None  # below-floor version warning (not a failure)
    detail: str  # install guidance (failure) or a human-readable status line


def check_tectonic() -> TectonicCheck:
    """Probe for the tectonic binary (résumé PDF gate, Increment-1). Missing binary is an
    actionable failure; tectonic auto-fetches packages on demand, so a below-floor version
    is a loud warning rather than a hard fail — unlike typst, no exact pin is required."""
    if shutil.which("tectonic") is None:
        detail = (
            "tectonic not found on PATH; install it (`brew install tectonic` / "
            "https://tectonic-typesetting.github.io) to render résumé PDFs"
        )
        return TectonicCheck(
            available=False, version=None, failed=True, warning=None, detail=detail
        )
    result = subprocess.run(["tectonic", "--version"], capture_output=True, text=True)
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", result.stdout)
    version = match.group(0) if match else None
    if result.returncode != 0 or match is None:
        # a present binary that fails to run (wrong arch, corrupt install, ...) is exactly
        # as broken as a missing one — the PDF gate cannot use it either way
        detail = (
            f"tectonic --version failed (exit {result.returncode}); reinstall tectonic "
            "— required for the résumé PDF gate"
        )
        return TectonicCheck(
            available=True, version=version, failed=True, warning=None, detail=detail
        )
    parsed = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    warning = None
    # tuple compare — a string compare mis-orders "0.9.0" < "0.15.0"
    if parsed < _TECTONIC_MIN_VERSION:
        floor = ".".join(str(p) for p in _TECTONIC_MIN_VERSION)
        warning = f"tectonic version is {version}, below the recommended {floor} floor"
    return TectonicCheck(
        available=True, version=version, failed=False, warning=warning, detail=f"tectonic {version}"
    )


def check_pdfinfo() -> bool:
    """Is poppler's `pdfinfo` on PATH? Missing is an actionable failure, same as tectonic.

    It *was* a hard dependency wearing a soft failure, which is why this probe exists:
    `_pdf_page_count` (`reports/tailor.py`) returned `None` when the binary was absent and
    `_default_runner` laundered that into `COMPILE_FAILED` for **every** lead, so a user with
    tectonic but no poppler got an empty run every morning and the cause was never named. D-204
    lifted the check into `_default_runner`, where a missing `pdfinfo` is now `BINARY_MISSING` —
    run-level fatal, exactly like tectonic. The probe stays because naming a missing binary
    before a run beats aborting partway through one.
    """
    return shutil.which("pdfinfo") is not None


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
        revision = db_revision(conn)
    schema_ok = revision == schema_revision()
    if revision is None:  # absent/unversioned schema — report and stop before probing
        console.print(f"boardwatch {package_version('boardwatch')}")
        console.print("schema: ABSENT (run a boardwatch command that initializes the database)")
        raise typer.Exit(code=1)

    report = probe_health(app_ctx.engine, app_ctx.settings, offline=offline)

    # P3 slice 2 (D-046): the operator-facing drain. Reports and reaps in the same call —
    # idempotent, safe to invoke anytime — so a stale `running` row never needs a separate
    # command to clear. Swallowed and logged, mirroring `runner.py`'s guard on the same call:
    # `doctor` must stay usable (print its diagnostics, compute its exit code) even when the
    # write contends with a concurrent `run` under the busy_timeout and raises.
    try:
        reaped = reap_stale_runs(
            app_ctx.engine, older_than=timedelta(hours=app_ctx.settings.reap_stale_after_hours)
        )
    except Exception as exc:  # noqa: BLE001 - never block doctor's own diagnostics
        reaped = []
        console.print(f"  ! stale-run reap failed: {exc}", markup=False)
    if reaped:
        console.print(
            f"[yellow]reaped {len(reaped)} stale run(s) (running with no terminal status "
            f"for > {app_ctx.settings.reap_stale_after_hours}h): {reaped}[/yellow]"
        )

    with app_ctx.engine.connect() as conn:
        ages = last_complete_scan_ages(conn)
        watches = conn.execute(
            select(tables.companies).where(tables.companies.c.watched.is_(True))
        ).all()
        running = conn.execute(
            select(tables.runs.c.id).where(tables.runs.c.finished_at.is_(None))
        ).first()
        # The inverse combination, and it is an INVARIANT rather than a state: every writer that
        # stamps `finished_at` stamps `status` in the same UPDATE (`record_scan_run(finished=True)`,
        # `finish_run`, `reap_stale_runs`), so no write path can leave a row `running` once it is
        # closed. `p0_run_status`'s `DEFAULT 'running'` backfill produced exactly that and no drain
        # could reach it — `reap_stale_runs` requires `finished_at IS NULL`. Repaired by
        # `runs_status_backfill_repair`; asserted here so a second one is loud instead of inert.
        unreachable = conn.execute(
            select(tables.runs.c.id)
            .where(tables.runs.c.status == RUN_RUNNING)
            .where(tables.runs.c.finished_at.is_not(None))
        ).all()
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
    if report.migrations:
        # A dead/empty watched board often means the company moved its board to another ATS, not
        # that it stopped hiring. Suggest-only: the operator re-points the watch (the same
        # human-in-the-loop rule `companies discover`/`import` follow). Informational — this does
        # NOT set the exit code; the dead board it derives from already did.
        console.print(
            "\n[yellow]Possible board migrations[/yellow] (a watched board is unhealthy, but the "
            "same company is live on another provider):"
        )
        for m in report.migrations:
            console.print(f"  {m.old_provider}:{m.old_slug}", markup=False)
            console.print(f"    → [green]{m.new_provider}:{m.new_slug}[/green] is OK. Re-point:")
            console.print(
                f"      boardwatch companies remove {m.old_provider}:{m.old_slug} && "
                f"boardwatch companies add {m.new_provider}:{m.new_slug}",
                markup=False,
            )
    if running:
        # Deliberately not "a scan is in progress": since run attribution landed, an
        # unfinished run is also a `boardwatch run` still tailoring, or a standalone
        # eligibility pass still judging. Naming it a scan sent users looking for a held
        # scan lock that is in fact free.
        console.print(f"[yellow]a run is in progress (run {running.id})[/yellow]")
    if unreachable:
        ids = [row.id for row in unreachable]
        console.print(
            f"[red]{len(ids)} run(s) are '{RUN_RUNNING}' with finished_at set, which no write "
            f"path can produce: {ids}. This is a schema-backfill artifact or direct database "
            f"surgery, and no reaper can drain it — `reap_stale_runs` requires finished_at "
            f"IS NULL. Run the migrations (`runs_status_backfill_repair` repairs it).[/red]"
        )

    # schema check compares the DB's applied revision against the code's expected script head
    schema_ok = revision == schema_revision()
    integrity_ok = integrity == "ok"
    console.print(f"boardwatch {package_version('boardwatch')}")
    console.print(
        f"integrity: {integrity} · schema: "
        f"{'ok' if schema_ok else f'MISMATCH (db={revision}, code={schema_revision()})'}"
    )

    tectonic_check = check_tectonic()
    console.print(f"tectonic: {tectonic_check.version or 'NOT FOUND'}")
    if tectonic_check.failed:
        console.print(f"[red]{tectonic_check.detail}[/red]")
    elif tectonic_check.warning:
        console.print(f"[yellow]{tectonic_check.warning}[/yellow]")

    pdfinfo_ok = check_pdfinfo()
    console.print(f"pdfinfo (poppler): {'found' if pdfinfo_ok else 'NOT FOUND'}")
    if not pdfinfo_ok:
        console.print(
            "[red]pdfinfo not found on PATH; install poppler (`brew install poppler` / "
            "`apt-get install poppler-utils`) — without it every résumé fails its page-count "
            "gate and no leads are built[/red]"
        )

    failed = (
        report.actionable
        or not integrity_ok
        or not schema_ok
        or tectonic_check.failed
        or not pdfinfo_ok
        or bool(unreachable)
    )
    raise typer.Exit(code=1 if failed else 0)
