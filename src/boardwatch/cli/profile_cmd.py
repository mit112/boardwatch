"""boardwatch profile show|edit (§2.3, §3.6).

Profile skills are extracted by THE SAME taxonomy engine as postings, on every
save, and stored with the taxonomy_version used; a stale version is repaired
by the D21 preflight (Task 12)."""

from __future__ import annotations

import typer
from pydantic import BaseModel, ConfigDict, Field
from rich.console import Console
from sqlalchemy import Engine

from boardwatch.cli.context import build_context
from boardwatch.core.settings import Settings
from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.store.queries import get_profile, save_profile

console = Console()
profile_app = typer.Typer(no_args_is_help=True, help="Profile management.")

ZERO_SKILL_WARNING = (
    "warning: no recognized skills in your profile — "
    "ranking will use title/recency/location only"
)


class ProfileInput(BaseModel):
    """Pydantic boundary validation for profile saves (issue #11, §6.1)."""

    model_config = ConfigDict(frozen=True)

    text: str = Field(min_length=1)
    target_titles: list[str]
    exclude_titles: list[str]
    locations: list[str]
    remote_only: bool


def persist_profile(
    engine: Engine,
    settings: Settings,
    *,
    text: str,
    target_titles: list[str],
    exclude_titles: list[str],
    locations: list[str],
    remote_only: bool,
) -> list[str]:
    """Save the singleton profile, re-deriving skills via the taxonomy engine.

    Inputs pass through ProfileInput first — Pydantic at the boundary; a
    whitespace-only profile text is rejected before anything is persisted.
    """
    data = ProfileInput(
        text=text.strip(),
        target_titles=target_titles,
        exclude_titles=exclude_titles,
        locations=locations,
        remote_only=remote_only,
    )
    taxonomy = load_taxonomy(settings.config_dir)
    skills = sorted(taxonomy.extract(data.text))
    with engine.begin() as conn:
        save_profile(
            conn,
            text=data.text,
            target_titles=data.target_titles,
            exclude_titles=data.exclude_titles,
            locations=data.locations,
            remote_only=data.remote_only,
            skills=skills,
            taxonomy_version=taxonomy.version,
        )
    if not skills:
        console.print(ZERO_SKILL_WARNING)
    else:
        console.print(f"Recognized {len(skills)} skills from your profile.")
    return skills


def split_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.replace("\n", ",").split(",") if item.strip()]


@profile_app.command("show")
def show(ctx: typer.Context) -> None:
    """Render profile, recognized skills, and the taxonomy version used."""
    app_ctx = build_context(ctx.obj)
    with app_ctx.engine.connect() as conn:
        row = get_profile(conn)
    if row is None:
        console.print("no profile yet — run `boardwatch init` first")
        raise typer.Exit(code=1)
    console.print(f"Profile text: {row.text[:120]}{'…' if len(row.text) > 120 else ''}")
    skills = row.skills_json or []
    console.print(f"Skills ({len(skills)}): {', '.join(skills) if skills else '—'}")
    console.print(f"Taxonomy version: {row.taxonomy_version}")
    console.print(f"Target titles: {', '.join(row.target_titles_json or []) or '—'}")
    console.print(f"Exclude titles: {', '.join(row.exclude_titles_json or []) or '—'}")
    console.print(
        f"Locations: {', '.join(row.locations_json or []) or '—'} · "
        f"Remote only: {'yes' if row.remote_only else 'no'}"
    )


@profile_app.command("edit")
def edit(ctx: typer.Context) -> None:
    """Edit the profile; skills are re-derived on save (§3.6)."""
    app_ctx = build_context(ctx.obj)
    with app_ctx.engine.connect() as conn:
        row = get_profile(conn)
    if row is None:
        console.print("no profile yet — run `boardwatch init` first")
        raise typer.Exit(code=1)
    text = typer.prompt("Profile text", default=row.text)
    targets = typer.prompt(
        "Target titles (comma separated)", default=", ".join(row.target_titles_json or [])
    )
    excludes = typer.prompt(
        "Exclude titles (comma separated)", default=", ".join(row.exclude_titles_json or [])
    )
    locations = typer.prompt(
        "Locations (comma separated)", default=", ".join(row.locations_json or [])
    )
    remote_only = typer.confirm("Remote only?", default=bool(row.remote_only))
    persist_profile(
        app_ctx.engine,
        app_ctx.settings,
        text=text,
        target_titles=split_csv(targets),
        exclude_titles=split_csv(excludes),
        locations=split_csv(locations),
        remote_only=remote_only,
    )
