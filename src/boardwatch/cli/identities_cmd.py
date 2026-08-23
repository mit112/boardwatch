"""`boardwatch identities backfill|regroup|verify|leakage` (design §6.3, §7)."""

from __future__ import annotations

import json
from dataclasses import asdict

import typer

from boardwatch.cli.context import build_context
from boardwatch.core.clock import utcnow
from boardwatch.core.dedup import mergeable_suppressions, resolve_duplicates
from boardwatch.core.posting_identity import compute_identities
from boardwatch.core.regroup import Refusal, plan_regrouping
from boardwatch.reports.leakage import DEFAULT_WINDOW_DAYS, compute_leakage_report
from boardwatch.store.identity_queries import (
    identities_complete,
    load_identities,
    load_identity_inputs,
    write_identities,
)
from boardwatch.store.regroup import apply_merges, job_anchors, protected_job_ids

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


@identities_app.command("regroup")
def regroup(
    ctx: typer.Context,
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Report what would move without writing anything."
    ),
) -> None:
    """Move every MERGEABLE duplicate posting onto its survivor's canonical job (P6 slice 2 §3).

    "Mergeable" is the catalog's word, not this command's: `company_title_location` suppresses
    at rank time but may not rewrite a job anchor (D-294), so the count of suppressed postings
    and the count considered for a merge are reported separately rather than folded.

    The corpus-wide counterpart to what the pipeline does over the population it ranked. Safe to
    re-run: a posting already on the canonical job plans no move, so a second pass writes
    nothing and appends no event.

    Completeness-gated for a stronger reason than the ranker's (D-090). Survivor election over a
    partial corpus is backfill-order-dependent, and unlike the read path this writes that
    order-dependence to disk permanently.
    """
    engine = build_context(ctx.obj).engine
    with engine.begin() as conn:
        if not identities_complete(conn):
            typer.echo(
                "identities: incomplete — regrouping a partial corpus would persist a "
                "backfill-order-dependent grouping. Run `boardwatch identities backfill` first."
            )
            raise typer.Exit(code=1)
        rows = load_identity_inputs(conn)
        suppressions = resolve_duplicates(rows, load_identities(conn))
        planned = 0
        moved = 0
        refusals: list[Refusal] = []
        for kind, group in mergeable_suppressions(suppressions).items():
            member_ids = sorted(
                {s.posting_id for s in group} | {s.survivor_posting_id for s in group}
            )
            plan = plan_regrouping(
                group,
                job_anchors(conn, member_ids),
                protected_job_ids=protected_job_ids(conn),
            )
            planned += len(plan.merges)
            refusals.extend(plan.refusals)
            if not dry_run:
                moved += apply_merges(conn, plan.merges, identity_kind=kind, now=utcnow())
    verb = "would move" if dry_run else "moved"
    count = planned if dry_run else moved
    mergeable = sum(len(g) for g in mergeable_suppressions(suppressions).values())
    typer.echo(
        f"regroup: {len(suppressions)} suppressed postings ({mergeable} mergeable), "
        f"{verb} {count} onto a canonical job, {len(refusals)} group(s) refused"
    )
    for refusal in refusals:
        typer.echo(
            f"  refused ({refusal.reason}): postings "
            f"{', '.join(str(p) for p in refusal.member_posting_ids)}"
        )


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


@identities_app.command("leakage")
def leakage(
    ctx: typer.Context,
    days: int = typer.Option(
        DEFAULT_WINDOW_DAYS,
        "--days",
        help="Trailing window, anchored on when each job FIRST reached leads.",
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON instead of text."),
) -> None:
    """Gate P6's "duplicate leakage over 7 days" number (design §2, `reports/leakage.py`).

    Only `exact_quad` counts as a duplicate (the owner's ruling — see
    `core/identity_kinds.py`), and only jobs that actually reached the operator
    (`job_dispositions`: `seen`, `skipped`, or `built`) count as "leaked" — a duplicate the
    ranker suppressed before it ever surfaced never leaked. Body-less/unbackfilled postings
    have no `exact_quad` identity by design and are reported as their own `unidentified`
    bucket, excluded from the rate rather than folded into "unique".

    Prints "not measurable" rather than 0% or 100% when nothing in the window carries an
    identity.
    """
    engine = build_context(ctx.obj).engine
    report = compute_leakage_report(engine, window_days=days)
    if as_json:
        typer.echo(json.dumps({**asdict(report), "rate": report.rate}))
        return
    if report.identified == 0:
        typer.echo(
            f"leakage (last {report.window_days}d): not measurable — "
            f"{report.surfaced_total} job(s) reached leads, {report.unidentified} of them "
            "unidentified, 0 carry an exact_quad identity"
        )
        return
    assert report.rate is not None  # narrowed by the identified == 0 check above
    typer.echo(
        f"leakage (last {report.window_days}d): {report.rate:.1%} "
        f"({report.redundant} redundant of {report.identified} identified across "
        f"{report.distinct_groups} distinct exact_quad group(s); "
        f"{report.unidentified} unidentified excluded; {report.surfaced_total} total "
        "reached leads)"
    )
