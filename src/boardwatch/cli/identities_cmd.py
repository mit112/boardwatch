"""`boardwatch identities backfill|reap|regroup|verify|leakage` (design §6.3, §7)."""

from __future__ import annotations

import json
from dataclasses import asdict

import typer

from boardwatch.cli.context import build_context
from boardwatch.core.clock import utcnow
from boardwatch.core.dedup import resolve_duplicates
from boardwatch.core.identity_kinds import IDENTITY_ALGORITHM_VERSION
from boardwatch.core.posting_identity import compute_identities
from boardwatch.core.regroup import plan_regrouping
from boardwatch.reports.leakage import DEFAULT_WINDOW_DAYS, compute_leakage_report
from boardwatch.store.identity_queries import (
    count_stale_identities,
    delete_stale_identities,
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


@identities_app.command("reap")
def reap(
    ctx: typer.Context,
    apply_: bool = typer.Option(
        False, "--apply", help="Actually delete. Without it this only reports."
    ),
) -> None:
    """Delete identity rows left behind by a retired IDENTITY_ALGORITHM_VERSION.

    `write_identities` only rewrites a posting's rows at the CURRENT version, so a version
    bump writes a whole new generation BESIDE the old one and nothing ever removes the old
    one. The live table held 476,277 rows at a single version on 2026-08-28 (~5 per posting);
    the next bump takes it past 950k with half of it permanently unread, because every reader
    filters to the current version.

    **Only retired generations are reaped.** Rows on CLOSED postings at the current version
    are left alone on purpose: postings reopen (run 127 reopened 18), `identities_complete()`
    gates suppression over ALL open postings, and a reopened posting with no identity rows
    drops the corpus below complete — silently disarming dedup store-wide until a backfill.
    See `store/identity_queries.count_stale_identities`.

    Reports by default and deletes only under `--apply`, and nothing else in the CLI reaps as
    a side effect: this is the only path that removes an identity row.
    """
    engine = build_context(ctx.obj).engine
    with engine.begin() as conn:
        generations = count_stale_identities(conn)
        total = sum(g.rows for g in generations)
        deleted = delete_stale_identities(conn) if apply_ and total else 0
    if not generations:
        typer.echo(
            f"reap: nothing stale — every identity row is at {IDENTITY_ALGORITHM_VERSION}. "
            "Rows on closed postings at the current version are NOT reapable; see --help."
        )
        return
    for generation in generations:
        typer.echo(
            f"  {generation.algorithm_version}: {generation.rows} row(s) across "
            f"{generation.postings} posting(s)"
        )
    if apply_:
        typer.echo(f"reap: deleted {deleted} row(s) at {len(generations)} retired version(s)")
        typer.echo(
            "  space returned to SQLite's free list and is reused by later inserts; run "
            "VACUUM separately to shrink the file itself"
        )
        return
    typer.echo(
        f"reap: would delete {total} row(s) at {len(generations)} retired version(s). "
        "Re-run with --apply to delete."
    )


@identities_app.command("regroup")
def regroup(
    ctx: typer.Context,
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Report what would move without writing anything."
    ),
) -> None:
    """Move every duplicate posting onto its survivor's canonical job (P6 slice 2 §3).

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
        member_ids = sorted(
            {s.posting_id for s in suppressions} | {s.survivor_posting_id for s in suppressions}
        )
        plan = plan_regrouping(
            suppressions,
            job_anchors(conn, member_ids),
            protected_job_ids=protected_job_ids(conn),
        )
        moved = 0 if dry_run else apply_merges(
            conn, plan.merges, identity_kind="exact_quad", now=utcnow()
        )
    verb = "would move" if dry_run else "moved"
    count = len(plan.merges) if dry_run else moved
    typer.echo(
        f"regroup: {len(suppressions)} suppressed postings, {verb} {count} onto a "
        f"canonical job, {len(plan.refusals)} group(s) refused"
    )
    for refusal in plan.refusals:
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

    A second line reports the `company_title_location` class as an UPPER BOUND. That class is
    not a duplicate count — measured by hand on 2026-08-27, 3 of 17 such groups among the
    delivered population were true duplicates and 14 were genuinely different jobs — so it is
    printed beside the gate's number, never inside it, and nothing in it is suppressed.

    Prints "not measurable" rather than 0% or 100% when nothing in the window carries an
    identity, on either line.
    """
    engine = build_context(ctx.obj).engine
    report = compute_leakage_report(engine, window_days=days)
    if as_json:
        typer.echo(
            json.dumps(
                {**asdict(report), "rate": report.rate, "candidate_rate": report.candidate_rate}
            )
        )
        return
    if report.identified == 0:
        typer.echo(
            f"leakage (last {report.window_days}d): not measurable — "
            f"{report.surfaced_total} job(s) reached leads, {report.unidentified} of them "
            "unidentified, 0 carry an exact_quad identity"
        )
    else:
        assert report.rate is not None  # narrowed by the identified == 0 check above
        typer.echo(
            f"leakage (last {report.window_days}d): {report.rate:.1%} "
            f"({report.redundant} redundant of {report.identified} identified across "
            f"{report.distinct_groups} distinct exact_quad group(s); "
            f"{report.unidentified} unidentified excluded; {report.surfaced_total} total "
            "reached leads)"
        )
    if report.candidate_rate is None:
        typer.echo(
            f"  near-duplicate bound ({report.candidate_kind}): not measurable — "
            f"0 job(s) in the window carry a {report.candidate_kind} identity"
        )
        return
    typer.echo(
        f"  near-duplicate bound ({report.candidate_kind}): <= {report.candidate_rate:.1%} "
        f"({report.candidate_redundant} redundant of {report.candidate_identified} "
        f"identified across {report.candidate_groups} group(s); "
        f"{report.candidate_distinguished} proven distinct and excluded). "
        "An UPPER bound, not a duplicate count — this key spans genuinely different jobs "
        "and nothing here is suppressed."
    )
