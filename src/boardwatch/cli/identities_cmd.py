"""`boardwatch identities backfill|verify` (design §6.3, §7)."""

from __future__ import annotations

import typer

from boardwatch.cli.context import build_context
from boardwatch.core.clock import utcnow
from boardwatch.core.posting_identity import compute_identities
from boardwatch.store.identity_queries import (
    load_identities,
    load_identity_inputs,
    write_identities,
)

identities_app = typer.Typer(no_args_is_help=True, help="Posting identity maintenance (dedup).")


@identities_app.command("backfill")
def backfill(ctx: typer.Context) -> None:
    """Compute and store identities for every open posting. Safe to re-run."""
    engine = build_context(ctx.obj).engine
    now = utcnow()
    written = 0
    with engine.begin() as conn:
        for row in load_identity_inputs(conn):
            written += write_identities(conn, row.posting_id, compute_identities(row), now=now)
    typer.echo(f"identities: wrote {written} rows")


@identities_app.command("verify")
def verify(ctx: typer.Context) -> None:
    """Recount identities independently and fail on any disagreement.

    Path A: stored posting_identities rows. Path B: recomputed from postings. They differ
    exactly when a posting changed and *nothing called the writer* — the writer itself
    upserts (§2.3), so a clean `backfill` clears any disagreement it can reach. What
    survives a backfill is a real defect: a scan path that mutates a posting without
    recomputing its identity.

    This is a staleness and consistency check, not a proof that the normalizers are
    correct — both paths call the same `normalize_title`/`normalized_locations`. Design
    §6.3 says so plainly; do not oversell it in the output text.

    Missing identities fail too. "Nothing is deduped because nothing was backfilled" is
    not a healthy subsystem, and the message says which command fixes it.
    """
    engine = build_context(ctx.obj).engine
    stale: list[int] = []
    missing: list[int] = []
    with engine.connect() as conn:
        rows = load_identity_inputs(conn)
        # No id list: at corpus scale it would exceed SQLite's bound-parameter cap and make
        # the verification path itself the thing that fails. See load_identities.
        stored = load_identities(conn)
        for row in rows:
            expected = set(compute_identities(row))
            have = set(stored.get(row.posting_id, ()))
            if not have:
                missing.append(row.posting_id)
            elif have != expected:
                stale.append(row.posting_id)
    if missing:
        typer.echo(f"identities: {len(missing)} postings have no identity (run backfill)")
    if stale:
        typer.echo(f"identities: {len(stale)} stale rows: {sorted(stale)[:20]}")
    if missing or stale:
        raise typer.Exit(code=1)
    typer.echo(f"identities: {len(rows)} postings verified")
