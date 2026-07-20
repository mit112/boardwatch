"""boardwatch init — §2.2 first-run (P1): companies via starter-set / registry
search / paste, then the P0 profile + filter flow (unchanged)."""

from __future__ import annotations

import typer
from rich.console import Console

from boardwatch.cli.context import build_context
from boardwatch.cli.profile_cmd import persist_profile, split_csv
from boardwatch.core.board_urls import UnknownBoardURL, parse_board_target
from boardwatch.registry.loader import load_catalog, starter_entries
from boardwatch.registry.validate import CompanyEntry
from boardwatch.store.queries import upsert_watch

console = Console()


def _paste_target(token: str) -> tuple[str, str]:
    token = token.strip()
    if ":" not in token and "/" not in token:  # deviation 9: bare token is a Greenhouse slug
        return "greenhouse", token.lower()
    return parse_board_target(token)


def init(ctx: typer.Context) -> None:
    """Interactive first-run: companies (3 paths), profile, filters."""
    app_ctx = build_context(ctx.obj)
    catalog = load_catalog()
    catalog_index: dict[tuple[str, str], CompanyEntry] = {
        (str(e.provider), e.slug): e for e in catalog
    }
    choice = typer.prompt(
        "Companies: [1] Starter set  [2] Search registry  [3] Paste slugs/URLs", default="1"
    )
    targets: list[tuple[str, str]] = []
    if choice == "1":
        targets = [(e.provider, e.slug) for e in starter_entries(catalog)]
    elif choice == "2":
        query = typer.prompt("Search registry").casefold()
        hits = [e for e in catalog if query in e.name.casefold() or query in e.slug.casefold()]
        for e in hits:
            if typer.confirm(f"Watch {e.name} ({e.provider}:{e.slug})?", default=True):
                targets.append((e.provider, e.slug))
    else:
        raw = typer.prompt("Paste slugs or board URLs (comma/newline separated)")
        for token in split_csv(raw):
            try:
                targets.append(_paste_target(token))
            except UnknownBoardURL as exc:
                console.print(f"[yellow]skipping {token!r}: {exc}[/yellow]")

    with app_ctx.engine.begin() as conn:
        for provider, slug in targets:
            entry = catalog_index.get((provider, slug))
            upsert_watch(
                conn, provider=provider, slug=slug,
                name=entry.name if entry else slug,
                source="registry" if entry else "user",
            )

    # ---- profile + filters: unchanged from P0 #11 (moved verbatim) ----
    text = typer.prompt("Profile text (paste resume text or a short profile)")
    targets_t = typer.prompt("Target titles (comma separated, blank for none)", default="")
    excludes = typer.prompt("Exclude titles (comma separated, blank for none)", default="")
    locations = typer.prompt("Locations (comma separated, blank for none)", default="")
    remote_only = typer.confirm("Remote only?", default=False)
    persist_profile(
        app_ctx.engine, app_ctx.settings, text=text,
        target_titles=split_csv(targets_t), exclude_titles=split_csv(excludes),
        locations=split_csv(locations), remote_only=remote_only,
    )
    console.print(f"Watching {len(targets)} companies. Run `boardwatch scan` next.")
