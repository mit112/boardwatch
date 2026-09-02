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
    claimed_hosts,
)
from boardwatch.store.db import db_revision, schema_revision
from boardwatch.store.seed_queries import count_unresolved_seeds, unclaimed_seed_hosts

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

    hosts, suffixes = claimed_hosts()
    with app_ctx.engine.connect() as conn:
        report = build_seed_claim_report(
            unresolved=count_unresolved_seeds(conn),
            hosts=unclaimed_seed_hosts(conn, hosts=hosts, host_suffixes=suffixes),
        )

    if as_json:
        typer.echo(
            json.dumps(
                {
                    "unresolved": report.unresolved,
                    "claimed": report.claimed,
                    "unclaimed": report.unclaimed,
                    "unclaimed_share": report.unclaimed_share,
                    "resolvers": sorted(SEED_RESOLVERS),
                    "unclaimed_hosts": [
                        {
                            "host": h.host,
                            "seeds": h.seeds,
                            "discovered_by": list(h.discovered_by),
                            "first_seen_run_id": h.first_seen_run_id,
                        }
                        for h in report.hosts
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
    console.print(f"registered resolvers: {', '.join(sorted(SEED_RESOLVERS)) or 'NONE'}")
    if not report.hosts:
        return
    table = Table("seeds", "host", "discovered by", "since run")
    # `limit=0` means every host, matching `--limit 0` elsewhere; a negative value is Python's
    # spelling of "all but the last N", which is not a bound at all, so it is refused rather
    # than silently reinterpreted.
    if limit < 0:
        console.print("[red]--limit must be non-negative[/red]")
        raise typer.Exit(code=1)
    shown = report.hosts if limit == 0 else report.hosts[:limit]
    for h in shown:
        table.add_row(f"{h.seeds:,}", h.host, ", ".join(h.discovered_by), str(h.first_seen_run_id))
    console.print(table)
    if len(shown) < len(report.hosts):
        console.print(f"… {len(report.hosts) - len(shown):,} more host(s); --limit 0 for all")
