"""boardwatch seeds — the `lane_seeds` handoff, and the part of it no resolver can drain (D-422).

Read-only apart from `get_engine`, and not read-only at the FILESYSTEM, for exactly the reason
`coverage_cmd.py` states: `build_context` creates the data dir and an empty database file before
this can report that the schema is absent. Shared with `doctor` and `coverage`, stated rather
than contradicted.
"""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table

from boardwatch.cli.context import build_context
from boardwatch.reports.seed_claims import (
    SEED_RESOLVERS,
    build_seed_claim_report,
    enabled_catalogs,
)
from boardwatch.store.db import db_revision, schema_revision
from boardwatch.store.seed_queries import read_seed_claims

console = Console()


def seeds(
    ctx: typer.Context,
    limit: int = typer.Option(
        20, "--limit", help="Unclaimed hosts to list, largest first. 0 lists every one."
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON instead of a table."),
) -> None:
    """Unresolved lane seeds, split by whether any registered resolver's catalog claims them.

    A seed on an unclaimed host is not slow, it is INVISIBLE: `unresolved_seeds` selects by host
    catalog, so nothing selects it, nothing attempts it, and the `attempts` ceiling never ages it
    out. This is the only thing that can see that population.
    """
    # Validated BEFORE anything is read or printed. Below the `--json` return it never runs on
    # that path at all, and below the summary lines a script sees plausible stdout followed by
    # exit 1. `limit == 0` means every host, matching `--limit 0` elsewhere; a NEGATIVE value is
    # Python's spelling of "all but the last N", which is not a bound at all, so it is refused
    # rather than silently reinterpreted.
    if limit < 0:
        console.print("[red]--limit must be non-negative[/red]")
        raise typer.Exit(code=1)

    app_ctx = build_context(ctx.obj, ensure=False)

    with app_ctx.engine.connect() as conn:
        revision = db_revision(conn)
    if revision is None:
        console.print("schema: ABSENT — run `boardwatch init` first")
        raise typer.Exit(code=1)
    if revision != schema_revision():
        console.print(
            f"schema: STALE — run `boardwatch init` (db={revision}, code={schema_revision()})"
        )
        raise typer.Exit(code=1)

    catalogs = enabled_catalogs(app_ctx.settings.lanes_enabled)
    enabled = [n for n in app_ctx.settings.lanes_enabled if n in SEED_RESOLVERS]
    with app_ctx.engine.connect() as conn:
        # ONE statement behind this call, and a transaction would NOT have been enough: pysqlite
        # does not begin one for a SELECT, so two reads straddle a concurrent insert even inside
        # `conn.begin()` and print a negative `claimable`. See `read_seed_claims`.
        reading = read_seed_claims(conn, catalogs=catalogs)
    report = build_seed_claim_report(
        unresolved=reading.unresolved, hosts=reading.unclaimed_hosts
    )

    shown = report.hosts if limit == 0 else report.hosts[:limit]

    if as_json:
        typer.echo(
            json.dumps(
                {
                    "unresolved": report.unresolved,
                    "claimed": report.claimed,
                    "unclaimed": report.unclaimed,
                    "unclaimed_share": report.unclaimed_share,
                    "resolvers_registered": sorted(SEED_RESOLVERS),
                    "resolvers_enabled": enabled,
                    "hosts_total": len(report.hosts),
                    "unclaimed_hosts": [
                        {
                            "host": h.host,
                            "seeds": h.seeds,
                            "discovered_by": list(h.discovered_by),
                            "first_seen_run_id": h.first_seen_run_id,
                            "max_attempts_spent": h.max_attempts_spent,
                        }
                        for h in shown
                    ],
                },
                indent=2,
            )
        )
        return

    share = "—" if report.unclaimed_share is None else f"{100 * report.unclaimed_share:.1f}%"
    console.print(
        f"unresolved seeds: {report.unresolved:,}   "
        f"claimable {report.claimed:,}   [bold]unclaimed {report.unclaimed:,} ({share})[/bold] "
        f"across {len(report.hosts):,} host(s)"
    )
    console.print(
        f"resolvers enabled: {', '.join(enabled) or 'NONE'}"
        + (
            f"   (registered but OFF: {', '.join(sorted(set(SEED_RESOLVERS) - set(enabled)))})"
            if set(SEED_RESOLVERS) - set(enabled)
            else ""
        )
    )
    if not report.hosts:
        return
    table = Table("seeds", "host", "discovered by", "since run", "attempts")
    for h in shown:
        table.add_row(
            f"{h.seeds:,}",
            h.host,
            ", ".join(h.discovered_by),
            str(h.first_seen_run_id),
            str(h.max_attempts_spent),
        )
    console.print(table)
    if len(shown) < len(report.hosts):
        console.print(f"… {len(report.hosts) - len(shown):,} more host(s); --limit 0 for all")
