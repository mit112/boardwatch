"""`boardwatch ledger show|reopen` — the decision ledger's drain (P6 slice 2, design §6).

The standing invariant: every quarantine needs a drain, designed in the same change, running on
both sides of the gate. `top --include-handled` is the read side; this is the write side, plus an
audit surface that does not depend on the ranker running at all.
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from boardwatch.cli.context import build_context
from boardwatch.core.clock import utcnow
from boardwatch.core.ledger import is_live
from boardwatch.pipeline.policy import run_policy_version
from boardwatch.store.ledger_queries import (
    live_dispositions,
    load_dispositions,
    reopen_jobs,
    stale_dispositions,
)
from boardwatch.store.tables import postings

ledger_app = typer.Typer(no_args_is_help=True, help="The durable decision ledger (dedup/queue).")
console = Console()


@ledger_app.command("show")
def show(
    ctx: typer.Context,
    stale: bool = typer.Option(
        False,
        "--stale",
        help="Only permanent decisions whose policy stamp is no longer the current one.",
    ),
    expired: bool = typer.Option(
        False, "--expired", help="Include lapsed and reopened rows, which no longer govern."
    ),
) -> None:
    """List the jobs the ledger is suppressing, and why.

    A suppression that cannot be listed is a leak rather than a filter, so this reads the bucket
    directly instead of inferring it from what `top` happened to hide.
    """
    app_ctx = build_context(ctx.obj)
    now = utcnow()
    with app_ctx.engine.connect() as conn:
        if stale:
            rows = stale_dispositions(
                conn, policy_version=run_policy_version(conn, app_ctx.settings), now=now
            )
        elif expired:
            rows = load_dispositions(conn)
        else:
            rows = live_dispositions(conn, now=now)
        # Which posting each job now anchors, so a row is identifiable without a second lookup.
        # After regrouping one job can anchor several postings; all of them are listed, because
        # naming only one would hide the group the disposition actually covers.
        titles: dict[int, list[str]] = {}
        if rows:
            for anchored in conn.execute(
                select(postings.c.job_id, postings.c.id, postings.c.title).where(
                    postings.c.job_id.in_(sorted(rows))
                )
            ).all():
                titles.setdefault(int(anchored.job_id), []).append(
                    f"{anchored.id} {anchored.title}"
                )

    if not rows:
        console.print("ledger: nothing to show" if not stale else "ledger: no stale decisions")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Job", style="dim")
    table.add_column("Disposition")
    table.add_column("Reason")
    table.add_column("Governs")
    table.add_column("Expires / stamp")
    table.add_column("Postings")
    for job_id, row in sorted(rows.items()):
        governs = is_live(expires_at=row.expires_at, reopened_at=row.reopened_at, now=now)
        if row.reopened_at is not None:
            detail = f"reopened {row.reopened_at:%Y-%m-%d}"
        elif row.expires_at is not None:
            detail = f"expires {row.expires_at:%Y-%m-%d}"
        else:
            detail = f"stamp {(row.policy_version or '')[:12]}"
        table.add_row(
            str(job_id),
            row.disposition,
            row.reason,
            "yes" if governs else "no",
            detail,
            "; ".join(titles.get(job_id, [])) or "-",
        )
    console.print(table)
    if not stale and not expired:
        console.print(
            "`seen` rows lapse on their own. `built`/`skipped` are permanent — release them "
            "with `ledger reopen`.",
            markup=False,
        )


@ledger_app.command("reopen")
def reopen(
    ctx: typer.Context,
    job: list[int] = typer.Option(  # noqa: B008 - typer declares options at def time
        [], "--job", help="Job id to release. Repeatable."
    ),
    stale: bool = typer.Option(
        False, "--stale", help="Release every permanent decision whose policy stamp has moved."
    ),
) -> None:
    """Release decisions so their jobs re-enter the shortlist.

    Sets `reopened_at` rather than deleting: draining a bucket must not erase the record that it
    ever held anything. A released job can be decided again, and the next decision is live.

    `--stale` is the policy-drift drain. A stamp mismatch is never released automatically
    (design §2.4) — auto-expiry on mismatch would rebuild the whole shortlist on any settings
    tweak, and an automatic re-open cannot be reviewed before it happens. This is that review.
    """
    if not job and not stale:
        console.print("nothing to do: pass --job <id> (repeatable) or --stale")
        raise typer.Exit(code=2)
    app_ctx = build_context(ctx.obj)
    now = utcnow()
    with app_ctx.engine.begin() as conn:
        job_ids = list(job)
        if stale:
            job_ids += sorted(
                stale_dispositions(
                    conn, policy_version=run_policy_version(conn, app_ctx.settings), now=now
                )
            )
        released = reopen_jobs(conn, sorted(set(job_ids)), now=now)
    console.print(f"ledger: released {released} decision(s)")
