"""boardwatch init — minimal P0 path (§8): paste Greenhouse slugs + profile.

Idempotent: re-running updates watches and the singleton profile, never
duplicates (UNIQUE(provider, slug) upsert + profile id=1 upsert). The starter
set, registry search, and board-URL parsing are P1."""

from __future__ import annotations

import typer
from rich.console import Console

from boardwatch.cli.context import build_context
from boardwatch.cli.profile_cmd import persist_profile, split_csv
from boardwatch.store.queries import upsert_watched_company

console = Console()


def init(ctx: typer.Context) -> None:
    """Interactive first-run: companies (paste slugs), profile, filters."""
    app_ctx = build_context(ctx.obj)
    slugs_raw = typer.prompt("Greenhouse slugs to watch (comma or newline separated)")
    text = typer.prompt("Profile text (paste resume text or a short profile)")
    targets = typer.prompt("Target titles (comma separated, blank for none)", default="")
    excludes = typer.prompt("Exclude titles (comma separated, blank for none)", default="")
    locations = typer.prompt("Locations (comma separated, blank for none)", default="")
    remote_only = typer.confirm("Remote only?", default=False)

    slugs = [slug.lower() for slug in split_csv(slugs_raw)]
    with app_ctx.engine.begin() as conn:
        for slug in slugs:
            upsert_watched_company(conn, provider="greenhouse", slug=slug, name=slug.title())
    persist_profile(
        app_ctx.engine,
        app_ctx.settings,
        text=text,
        target_titles=split_csv(targets),
        exclude_titles=split_csv(excludes),
        locations=split_csv(locations),
        remote_only=remote_only,
    )
    console.print(f"Watching {len(slugs)} companies. Run `boardwatch scan` next.")
