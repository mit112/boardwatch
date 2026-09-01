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
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import typer
from sqlalchemy import select, update

from boardwatch.cli.context import build_context
from boardwatch.core.clock import utcnow
from boardwatch.core.normalize import content_hash
from boardwatch.core.posting_identity import compute_identities

# `_body_text` is imported private deliberately: it IS the provider's body contract, and
# re-exporting it as public API would create a second name for one behaviour — the drain has to
# run the exact function the scan path runs, or it repairs rows into a third, different shape.
from boardwatch.providers.smartrecruiters import _body_text as _smartrecruiters_body
from boardwatch.store.identity_queries import load_identity_inputs, write_identities
from boardwatch.store.tables import companies, posting_versions, postings

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

    with engine.begin() as conn:
        rows = conn.execute(
            select(postings.c.id, postings.c.content_hash, postings.c.raw_json)
            .join(companies, companies.c.id == postings.c.company_id)
            .where(companies.c.provider == provider)
        ).all()
        for posting_id, old_hash, raw_json in rows:
            scanned += 1
            try:
                raw = json.loads(raw_json) if raw_json else {}
            except json.JSONDecodeError:
                skipped += 1
                continue
            if not isinstance(raw, dict):
                skipped += 1
                continue
            body = reparse(raw)
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
            conn.execute(
                update(postings)
                .where(postings.c.id == posting_id)
                .values(content_hash=new_hash, body_text=body)
            )
            conn.execute(
                posting_versions.insert().values(
                    posting_id=posting_id,
                    content_hash=new_hash,
                    body_text=body,
                    captured_at=now,
                    run_id=None,
                    capture_reason="revised",
                )
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
