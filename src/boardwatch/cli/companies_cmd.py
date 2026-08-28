"""boardwatch companies — search / add / remove / list / discover / import / export (§2.3).
`export` is the registry-format contribution funnel; data-portability export
(--format jsonl|csv) is P2 and intentionally absent."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
import yaml
from rich.console import Console
from rich.table import Table
from sqlalchemy import inspect

from boardwatch.cli.context import build_context
from boardwatch.core.board_urls import UnknownBoardURL, parse_board_target
from boardwatch.core.clock import utcnow
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.lanes.admission import CompanyBudget
from boardwatch.lanes.github_lists import candidate_document, discover, fetch_listings, select
from boardwatch.providers.base import BoardHealth, Provider
from boardwatch.registry.loader import load_catalog
from boardwatch.registry.validate import CatalogError, CompanyEntry, validate_entries
from boardwatch.scan.coordinator import default_providers
from boardwatch.store.queries import company_exists, list_watches, unwatch, upsert_watch

companies_app = typer.Typer(no_args_is_help=True, help="Manage watched company boards.")
console = Console()

# D27 vocabulary: OK/EMPTY are positive evidence the board exists; DEAD means the slug is
# wrong; ERROR/UNREACHABLE are absence of evidence, which is not evidence of absence — so
# --verify skips them rather than writing a watch it could not substantiate.
_UNPROVEN = frozenset({BoardHealth.DEAD, BoardHealth.ERROR, BoardHealth.UNREACHABLE})

_VERIFY_HELP = "Probe each board before watching it; skip any that cannot be confirmed."


def _probe(
    targets: list[tuple[str, str]], settings: Settings
) -> dict[tuple[str, str], BoardHealth]:
    """Live-healthcheck (provider, slug) pairs. One Fetcher for the whole set, so its
    per-host pacing applies across the batch instead of per board."""
    providers = default_providers()
    fetcher = Fetcher(settings)
    return {(p, s): _healthcheck(providers[p], fetcher, s) for p, s in targets}


def _healthcheck(provider: Provider, fetcher: Fetcher, slug: str) -> BoardHealth:
    """Providers map FetchFailure to a BoardHealth, but Fetcher.get only converts
    TransportError and retryable statuses — httpx.TooManyRedirects and DecodingError are
    RequestError, not TransportError, so they escape both. A CLI flag whose whole job is
    to report unreachable boards must not traceback on one; bucket it as UNREACHABLE
    (same skip decision either way) the way the scan coordinator already does."""
    try:
        return provider.healthcheck(fetcher, slug)
    except Exception:
        return BoardHealth.UNREACHABLE


def _catalog_index() -> dict[tuple[str, str], CompanyEntry]:
    return {(e.provider, e.slug): e for e in load_catalog()}


def _nothing_stored(provider: str, slug: str) -> bool:
    """No `companies` table, so nothing is stored and every candidate is new.

    Reached by ASKING the schema (`inspect(...).has_table`), not by catching the query's failure.
    Two reasons. Classifying behaviour by string-matching an `OperationalError` message is exactly
    what this repo forbids; and a bare `except OperationalError` would equally swallow a locked or
    corrupt store, which is a different problem with a different answer.

    On a fresh machine an absent schema is not an error — nothing is watched, so every board really
    is new, and the header's "already stored 0" says so. A named function rather than
    `lambda p, s: False` so the reason lives with the behaviour and it cannot be mistaken for a
    stub somebody forgot to finish.
    """
    return False


def _normalized(entry: CompanyEntry) -> CompanyEntry:
    """Apply the provider's slug normalization, which `add` gets from parse_board_target
    and the import path otherwise skips entirely."""
    _, slug = parse_board_target(f"{entry.provider}:{entry.slug}")
    return entry if slug == entry.slug else entry.model_copy(update={"slug": slug})


@companies_app.command("add")
def add(
    ctx: typer.Context,
    target: str,
    verify: bool = typer.Option(False, "--verify", help=_VERIFY_HELP),
) -> None:
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
    if verify:
        health = _probe([(provider, slug)], app_ctx.settings)[(provider, slug)]
        if health in _UNPROVEN:
            console.print(f"[red]not watching {provider}:{slug} — probe returned {health}.[/red]")
            raise typer.Exit(code=1)  # unproven board: no DB write
        if health is BoardHealth.EMPTY:
            console.print(
                f"[yellow]note:[/yellow] {provider}:{slug} is reachable but returned no "
                "postings. Watching it anyway."
            )
    with app_ctx.engine.begin() as conn:
        watched = upsert_watch(conn, provider=provider, slug=slug, name=name, source=source)
    if watched == slug:
        console.print(f"Watching {provider}:{slug} (source={source}).")
    else:
        # A silent no-op would leave the operator believing a new board was added. Say which
        # row the watch landed on, and do not claim `source`: the stored row keeps its own.
        console.print(
            f"[yellow]note:[/yellow] {provider}:{slug} differs only in slug case from the "
            f"board already stored as {provider}:{watched}; no second board was added."
        )
        console.print(f"Watching {provider}:{watched}.")
    if provider == "smartrecruiters":
        console.print(
            "[yellow]note:[/yellow] SmartRecruiters cannot confirm a board exists — "
            "an unknown company returns an empty board, not an error. If scans stay "
            "empty, re-check the slug."
        )


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


@companies_app.command("discover")
def discover_(
    ctx: typer.Context,
    limit: int | None = typer.Option(
        None, "--limit", min=0,
        help="How many new boards to propose (default: lane_new_companies_per_run).",
    ),
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Write the candidate file here instead of stdout."),
    ] = None,
) -> None:
    """Propose company boards from the two public GitHub new-grad lists, for review.

    Writes a registry-format file and NOTHING ELSE — no store write, watched or otherwise. Review
    it, delete any row whose evidence URL is not an employer board, then `companies import` it.
    That human step is the owner's ruling (D-291 build): a bad slug becomes a permanently failing
    board, and this repo has no quarantine and no backoff for one.
    """
    # ensure=False, the same reason `doctor` uses it: this command reads the store and must never
    # migrate it. `build_context`'s default runs `alembic upgrade head`, so without this a command
    # whose own docstring promises no store write would silently upgrade a 1.4 GB production
    # database as a side effect of being asked what boards exist (D-279).
    app_ctx = build_context(ctx.obj, ensure=False)
    cap = app_ctx.settings.lane_new_companies_per_run if limit is None else limit
    result = discover(fetch_listings(Fetcher(app_ctx.settings)))
    if not inspect(app_ctx.engine).has_table("companies"):
        # Nothing stored, so every candidate is new. `ensure=False` deliberately does not create
        # the schema here; `companies import` does, which is the write half of this workflow and
        # the right place for it.
        selection = select(result, is_known=_nothing_stored, budget=CompanyBudget(cap))
    else:
        with app_ctx.engine.connect() as conn:
            # One point query per candidate rather than one `IN (...)` over the whole set.
            # Deliberate: `(provider, slug)` is UNIQUE and indexed so this is a few hundred index
            # seeks, and a corpus-sized `IN` list is the exact shape that crossed SQLite's 32,766
            # bound-parameter cap and killed run 70 (D-287). It also reuses the sanctioned
            # lookup — `company_exists`, not the watched-only view, because an unwatched row
            # would read as new forever.
            selection = select(
                result,
                is_known=lambda provider, slug: company_exists(
                    conn, provider=provider, slug=slug
                ),
                budget=CompanyBudget(cap),
            )
    document = candidate_document(
        selection, census=result.census, generated_on=utcnow().date()
    )
    if out is None:
        # Plain stdout, not `console.print`: the document is YAML a human pipes into a file, and
        # rich would read its brackets as markup.
        typer.echo(document, nl=False)
        return
    out.write_text(document, encoding="utf-8")
    console.print(
        f"Wrote {len(selection.admitted)} candidate board(s) to {out} "
        f"({len(selection.already_known)} already stored, {len(selection.refused)} held back by "
        f"the cap of {cap}). Review it, then: boardwatch companies import {out}"
    )


@companies_app.command("import")
def import_(
    ctx: typer.Context,
    path: typer.FileText,
    verify: bool = typer.Option(False, "--verify", help=_VERIFY_HELP),
) -> None:
    """Validate registry-format YAML, then watch each entry."""
    try:
        raw = yaml.safe_load(path.read()) or {}
        # Normalize through the same path `add` uses before the duplicate check, so
        # case-variant slugs on a case-insensitive provider (smartrecruiters) collapse
        # instead of writing two rows for one board — one of which `remove` could never
        # match, because it normalizes the slug the caller types.
        entries = validate_entries(
            [_normalized(CompanyEntry.model_validate(row)) for row in (raw.get("companies") or [])]
        )
    except (CatalogError, UnknownBoardURL, ValueError, yaml.YAMLError) as exc:
        # `yaml.YAMLError` subclasses Exception, NOT ValueError, so it escaped this clause and the
        # operator got a traceback. `companies discover` exists to hand a human a YAML file to edit
        # before importing it, which makes a hand-introduced syntax error an ordinary event.
        console.print(f"[red]invalid import file: {exc}[/red]")
        raise typer.Exit(code=1) from exc
    app_ctx = build_context(ctx.obj)
    skipped: list[tuple[str, str, BoardHealth]] = []
    empty: list[str] = []
    if verify:
        health = _probe([(e.provider, e.slug) for e in entries], app_ctx.settings)
        kept: list[CompanyEntry] = []
        for e in entries:
            status = health[(e.provider, e.slug)]
            if status in _UNPROVEN:
                skipped.append((e.provider, e.slug, status))
                continue
            if status is BoardHealth.EMPTY:
                empty.append(f"{e.provider}:{e.slug}")
            kept.append(e)
        entries = kept
    recased: list[str] = []
    with app_ctx.engine.begin() as conn:
        for e in entries:
            in_catalog = (e.provider, e.slug) in _catalog_index()
            watched = upsert_watch(conn, provider=e.provider, slug=e.slug, name=e.name,
                                   source="registry" if in_catalog else "user")
            if watched != e.slug:
                recased.append(f"{e.provider}:{e.slug} -> {e.provider}:{watched}")
    console.print(f"Imported {len(entries)} watches.")
    if recased:
        # Reported, not silent: the count above would otherwise imply N new boards.
        console.print(
            "[yellow]note:[/yellow] already stored under a different slug case, watched in "
            f"place rather than added a second time: {', '.join(recased)}"
        )
    if empty:
        console.print(
            f"[yellow]note:[/yellow] reachable but currently empty (watched anyway): "
            f"{', '.join(empty)}"
        )
        if any(name.startswith("smartrecruiters:") for name in empty):
            # SmartRecruiters returns an empty board for an unknown company rather than a
            # 404, so 'empty' there is NOT evidence the board exists (see doctor's caveat).
            console.print(
                "[yellow]note:[/yellow] for smartrecruiters, 'empty' is unverifiable — it may "
                "be a typo'd slug rather than a real board with no open roles."
            )
    if skipped:
        for provider, slug, status in skipped:
            console.print(f"[red]skipped {provider}:{slug} — probe returned {status}.[/red]")
        # a partial import must not report success: the operator has to see the shortfall
        raise typer.Exit(code=1)
