"""boardwatch companies — search / add / remove / list / import / export (§2.3).
`export` is the registry-format contribution funnel; data-portability export
(--format jsonl|csv) is P2 and intentionally absent."""

from __future__ import annotations

import typer
import yaml
from rich.console import Console
from rich.table import Table

from boardwatch.cli.context import build_context
from boardwatch.core.board_urls import UnknownBoardURL, parse_board_target
from boardwatch.registry.loader import load_catalog
from boardwatch.registry.validate import CatalogError, CompanyEntry
from boardwatch.store.queries import list_watches, unwatch, upsert_watch

companies_app = typer.Typer(no_args_is_help=True, help="Manage watched company boards.")
console = Console()


def _catalog_index() -> dict[tuple[str, str], CompanyEntry]:
    # widen the Provider Literal to str in the key so str-keyed lookups type-check
    return {(str(e.provider), e.slug): e for e in load_catalog()}


@companies_app.command("add")
def add(ctx: typer.Context, target: str) -> None:
    """Watch a board by provider:slug or board URL."""
    try:
        provider, slug = parse_board_target(target)
    except UnknownBoardURL as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc  # no DB write on the failed-validation path
    entry = _catalog_index().get((provider, slug))
    source = "registry" if entry else "user"
    name = entry.name if entry else slug
    app_ctx = build_context(ctx.obj)
    with app_ctx.engine.begin() as conn:
        upsert_watch(conn, provider=provider, slug=slug, name=name, source=source)
    console.print(f"Watching {provider}:{slug} (source={source}).")


@companies_app.command("remove")
def remove(ctx: typer.Context, target: str) -> None:
    provider, slug = parse_board_target(target)
    app_ctx = build_context(ctx.obj)
    with app_ctx.engine.begin() as conn:
        changed = unwatch(conn, provider=provider, slug=slug)
    console.print(f"Unwatched {provider}:{slug}." if changed else "No such watch.")


@companies_app.command("search")
def search(ctx: typer.Context, query: str) -> None:
    """Case-insensitive substring search over the bundled catalog (offline)."""
    q = query.casefold()
    hits = [e for e in load_catalog() if q in e.name.casefold() or q in e.slug.casefold()]
    table = Table("name", "provider", "slug", "starter")
    for e in hits:
        table.add_row(e.name, e.provider, e.slug, "★" if "starter" in e.tags else "")
    console.print(table)


@companies_app.command("list")
def list_(ctx: typer.Context) -> None:
    app_ctx = build_context(ctx.obj)
    with app_ctx.engine.connect() as conn:
        rows = list_watches(conn)
    table = Table("provider", "slug", "source", "watched", "last_health", "last_ok_at")
    for r in rows:
        table.add_row(
            r.provider, r.slug, r.source, "yes" if r.watched else "no",
            r.last_health or "—", str(r.last_ok_at or "—"),
        )
    console.print(table)


@companies_app.command("export")
def export(ctx: typer.Context) -> None:
    """Emit the user's watches as registry-format YAML (the §3.2 contribution funnel)."""
    app_ctx = build_context(ctx.obj)
    with app_ctx.engine.connect() as conn:
        rows = list_watches(conn)
    payload = {"companies": [
        {"name": r.slug, "provider": r.provider, "slug": r.slug, "tags": []} for r in rows
    ]}
    console.print(yaml.safe_dump(payload, sort_keys=False))


@companies_app.command("import")
def import_(ctx: typer.Context, path: typer.FileText) -> None:
    """Validate registry-format YAML, then watch each entry."""
    try:
        raw = yaml.safe_load(path.read()) or {}
        entries = [CompanyEntry.model_validate(row) for row in (raw.get("companies") or [])]
    except (CatalogError, ValueError) as exc:
        console.print(f"[red]invalid import file: {exc}[/red]")
        raise typer.Exit(code=1) from exc
    app_ctx = build_context(ctx.obj)
    with app_ctx.engine.begin() as conn:
        for e in entries:
            in_catalog = (e.provider, e.slug) in _catalog_index()
            upsert_watch(conn, provider=e.provider, slug=e.slug, name=e.name,
                         source="registry" if in_catalog else "user")
    console.print(f"Imported {len(entries)} watches.")
