"""`boardwatch postings reparse-bodies` — re-derive `body_text` from stored `raw_json`.

WHY THIS EXISTS. A provider's body parser can be wrong, and the scan path cannot fix it on its
own: `known_posting_ids` excludes every posting the store already holds from detail fetching, so
a corrected parser only ever reaches NEW postings and the existing rows keep the bad body
indefinitely. The inputs are still on disk — providers persist the raw payload in
`postings.raw_json` — so the repair needs no network at all.

NOT A SCAN. This deliberately does not go through `apply_board`: that writes a `board_scans` row
and needs a `run_id`, which would both invent a run and make `load_board_coverage` count the
company twice. `posting_versions.run_id` is nullable precisely so a non-run writer can append a
version, and this is one. Shaped after `identities backfill`/`reap`: direct store work inside one
transaction, reports by default, writes only under `--apply`, safe to re-run.

CLOSED POSTINGS ARE INCLUDED. A body is wrong regardless of status and a closed posting reopens
(run 127 reopened 18) without ever being re-fetched, so skipping them would leave a bad body that
no later run can reach. Identities are recomputed only for the OPEN ones, which is what
`load_identity_inputs` already scopes itself to.

`postings refetch` is the network half: a row whose stored payload is not the board's own (the
job-apps lane's overwrite, D-500/D-502) cannot be re-derived, only re-read. It re-reads each named
posting from its OWN board and hands the result to `scan.apply.apply_refetched`, the scan's write
path, so no column is written by hand here.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import Any

import typer
from sqlalchemy import Engine, select

from boardwatch.cli.context import build_context
from boardwatch.core.clock import utcnow
from boardwatch.core.normalize import content_hash
from boardwatch.core.politeness import Fetcher
from boardwatch.core.posting_identity import compute_identities
from boardwatch.providers.base import Provider, RefetchUnsupported, posting_refetcher
from boardwatch.providers.registry import build_providers

# `_body_text` is imported private deliberately: it IS the provider's body contract, and
# re-exporting it as public API would create a second name for one behaviour — the drain has to
# run the exact function the scan path runs, or it repairs rows into a third, different shape.
from boardwatch.providers.smartrecruiters import _body_text as _smartrecruiters_body
from boardwatch.scan.apply import apply_refetched
from boardwatch.store.body_revision import record_body_revision
from boardwatch.store.db import write_connection
from boardwatch.store.identity_queries import load_identity_inputs, write_identities
from boardwatch.store.queries import RUN_RUNNING
from boardwatch.store.tables import companies, postings, runs

#: Closed catalog. A provider is repairable here only if its stored `raw_json` carries everything
#: its body parser reads; out-of-catalog is an error, never a new bucket.
_REPARSERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "smartrecruiters": lambda raw: _smartrecruiters_body(raw.get("detail") or {}),
}

postings_app = typer.Typer(no_args_is_help=True, help="Posting body maintenance.")


@postings_app.command("reparse-bodies")
def reparse_bodies(
    ctx: typer.Context,
    provider: str = typer.Option(..., "--provider", help="Provider whose bodies to re-derive."),
    apply_: bool = typer.Option(
        False, "--apply", help="Actually write. Without it this only reports."
    ),
) -> None:
    """Re-derive `body_text` from stored `raw_json` and record the change as a revision.

    A row is rewritten only when its `content_hash` actually moves, so a second pass reports
    zero. Each rewrite updates `postings.body_text`/`content_hash`, appends a `revised`
    `posting_versions` row with a NULL `run_id`, and — for open postings — rewrites the identity
    rows, because `content_hash` is one of `exact_quad`'s four components.
    """
    reparse = _REPARSERS.get(provider)
    if reparse is None:
        raise typer.BadParameter(
            f"no reparser for {provider!r}; known: {', '.join(sorted(_REPARSERS))}"
        )

    engine = build_context(ctx.obj).engine
    now = utcnow()
    changed: list[int] = []
    scanned = skipped = 0

    with write_connection(engine) as conn, conn.begin():  # T134: read-then-write
        rows = conn.execute(
            select(postings.c.id, postings.c.content_hash, postings.c.raw_json)
            .join(companies, companies.c.id == postings.c.company_id)
            .where(companies.c.provider == provider)
        ).all()
        for posting_id, old_hash, raw_json in rows:
            scanned += 1
            # `postings.raw_json` is a JSON column, so the driver hands back the decoded object,
            # not a string. Anything other than a mapping is a payload this drain cannot read.
            if not isinstance(raw_json, dict):
                skipped += 1
                continue
            body = reparse(raw_json)
            if not body:
                # No stored payload to re-derive from, or it yields nothing. Leaving the row as
                # it stands is right: an empty body would collide on `content_hash("")` with
                # every other body-less posting at the same company.
                skipped += 1
                continue
            new_hash = content_hash(body)
            if new_hash == old_hash:
                continue
            changed.append(posting_id)
            if not apply_:
                continue
            record_body_revision(
                conn,
                posting_id=posting_id,
                body_text=body,
                content_hash=new_hash,
                captured_at=now,
            )

        identity_rows = 0
        if apply_ and changed:
            for inputs in load_identity_inputs(conn, changed):
                identity_rows += write_identities(
                    conn, inputs.posting_id, compute_identities(inputs), now=now
                )

    verb = "rewrote" if apply_ else "would rewrite"
    typer.echo(
        f"reparse-bodies {provider}: {verb} {len(changed)} of {scanned} posting(s), "
        f"{skipped} without a usable stored payload"
    )
    if apply_:
        typer.echo(f"  identity rows touched: {identity_rows}")
    elif changed:
        typer.echo("  re-run with --apply to write.")


class Refetched(StrEnum):
    """What `postings refetch` did, or would do, to one posting. Closed catalog."""

    REVISED = "revised"  # the board's body differs: a `revised` version, hash moved
    REFRESHED = "refreshed"  # same body: `raw_json` and provider fields replaced only
    GONE = "gone"  # the board no longer serves it; reported, never closed from here
    UNSUPPORTED = "unsupported"  # the provider has no `fetch_posting`
    FAILED = "failed"  # the fetch or the parse failed, or the posting is not in the store


class RunInProgressError(Exception):
    """A `boardwatch run` holds a `running` row. Refused, never waited on."""


def _parse_ids(ids: str | None, ids_file: Path | None) -> list[int]:
    if (ids is None) == (ids_file is None):
        raise typer.BadParameter("give exactly one of --ids or --ids-file")
    text = ids_file.read_text() if ids_file is not None else str(ids)
    try:
        return [int(token) for token in text.replace(",", " ").split()]
    except ValueError as exc:
        raise typer.BadParameter(f"posting ids must be integers: {exc}") from None


def _refuse_while_running(engine: Engine) -> None:
    """The `runs` table's `running` row, the check `doctor` reports on. A run's scan writes the
    same postings, so a concurrent refetch would race it for the rows it is repairing."""
    with engine.connect() as conn:
        running = conn.execute(select(runs.c.id).where(runs.c.status == RUN_RUNNING)).first()
    if running is not None:
        raise RunInProgressError(f"run {running.id} is in progress; re-run after it finishes")


@postings_app.command("refetch")
def refetch(
    ctx: typer.Context,
    ids: str | None = typer.Option(None, "--ids", help="Comma-separated posting ids."),
    ids_file: Path | None = typer.Option(  # noqa: B008
        None, "--ids-file", help="File of posting ids, one per line or comma-separated."
    ),
    apply_: bool = typer.Option(
        False, "--apply", help="Actually write. Without it this fetches and only reports."
    ),
    limit: int | None = typer.Option(None, "--limit", min=1, help="Process at most N ids."),
) -> None:
    """Re-read named postings from their own board and apply them through the scan's writer.

    Per id: `revised` (body hash moves), `refreshed` (raw_json and fields only), `gone`,
    `unsupported`, `failed`. Without `--apply` every fetch still happens and nothing is written.
    Never closes a posting: `gone` is a report line, the death probe owns closing.
    """
    posting_ids = _parse_ids(ids, ids_file)[:limit]
    app_ctx = build_context(ctx.obj)
    engine = app_ctx.engine
    try:
        _refuse_while_running(engine)
    except RunInProgressError as exc:
        typer.echo(f"refetch refused: {exc}")
        raise typer.Exit(code=2) from None

    with engine.connect() as conn:
        held = {
            row.id: row
            for row in conn.execute(
                select(
                    postings.c.id, postings.c.company_id, postings.c.provider_posting_id,
                    postings.c.content_hash, companies.c.provider, companies.c.slug,
                )
                .join(companies, companies.c.id == postings.c.company_id)
                .where(postings.c.id.in_(posting_ids))
            ).all()
        }
    providers = build_providers()
    fetcher = Fetcher(app_ctx.settings)
    counts = dict.fromkeys(Refetched, 0)
    for posting_id in posting_ids:
        outcome, note = _refetch_one(held.get(posting_id), providers, fetcher, engine, apply_)
        counts[outcome] += 1
        typer.echo(f"  {posting_id}\t{outcome}" + (f"\t{note}" if note else ""))

    verb = "applied" if apply_ else "would apply"
    summary = ", ".join(f"{kind} {counts[kind]}" for kind in Refetched)
    typer.echo(f"refetch: {verb} {len(posting_ids)} posting(s): {summary}")
    if not apply_ and (counts[Refetched.REVISED] or counts[Refetched.REFRESHED]):
        typer.echo("  re-run with --apply to write.")


def _refetch_one(
    row: Any, providers: dict[str, Provider], fetcher: Fetcher, engine: Engine, apply_: bool
) -> tuple[Refetched, str]:
    if row is None:
        return Refetched.FAILED, "no such posting"
    provider = providers.get(row.provider)
    try:
        if provider is None:
            raise RefetchUnsupported(f"provider {row.provider!r} is not a registered board")
        refetcher = posting_refetcher(provider)
    except RefetchUnsupported as exc:
        return Refetched.UNSUPPORTED, str(exc)
    try:
        raw = refetcher.fetch_posting(fetcher, row.slug, row.provider_posting_id)
    except Exception as exc:  # noqa: BLE001 - per-posting isolation: one bad row, not the batch
        return Refetched.FAILED, f"{type(exc).__name__}: {exc}"
    if raw is None:
        return Refetched.GONE, ""
    if raw.provider_posting_id != row.provider_posting_id:
        return Refetched.FAILED, f"board answered for {raw.provider_posting_id!r}"
    outcome = (
        Refetched.REVISED
        if content_hash(raw.body_text) != row.content_hash
        else Refetched.REFRESHED
    )
    if apply_:
        result = apply_refetched(engine, raw, row.company_id, refetcher.board_url(row.slug))
        # The writer's own count, not the prediction above: the two must agree.
        outcome = Refetched.REVISED if result.revised else Refetched.REFRESHED
    return outcome, ""
