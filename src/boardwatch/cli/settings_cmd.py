"""boardwatch settings (P11): a readable, honest view of every opt-in feature — state, what
it does, and what it sends anywhere — plus `settings toggle` (interactive). Numeric tuning
stays in `boardwatch config`."""

from __future__ import annotations

import tomllib
from pathlib import Path

import typer
from pydantic import ValidationError
from rich.console import Console

from boardwatch.core.features import FEATURES, feature_state, unmet_prerequisites
from boardwatch.core.secrets import LLM_API_KEY_ENV, resolve_secret
from boardwatch.core.settings import Settings, load_settings
from boardwatch.notify.webhook import WEBHOOK_URL_ENV

settings_app = typer.Typer(no_args_is_help=False, help="View and change opt-in features.")
console = Console()


def _load_or_exit(data_dir: Path | None) -> Settings:
    """Load settings, or print a named error (not a traceback) for a hand-broken config."""
    try:
        return load_settings(data_dir=data_dir)
    except (ValidationError, tomllib.TOMLDecodeError) as exc:
        console.print(f"[red]config.toml is invalid: {exc}[/red]")
        raise typer.Exit(code=1) from exc


def _secret_line(name: str) -> str:
    return f"{name}: {'set' if resolve_secret(name) is not None else 'unset'}"


def _print_menu(settings: Settings) -> None:
    console.print("[bold]Always on[/bold] (core function, not a toggle):")
    console.print(
        "  Scanning boards — every `scan` connects over HTTPS to each ATS host you watch "
        "to read public postings."
    )
    console.print("")
    console.print("[bold]Features[/bold] (state · what it does · what it sends):")
    for i, feat in enumerate(FEATURES, start=1):
        on = feature_state(feat, settings)
        console.print(f"{i:>2}. {feat.name}  [{'ON ' if on else 'OFF'}]")
        console.print(f"    {feat.description}")
        console.print(f"    sends: {feat.sends}")
        unmet = unmet_prerequisites(feat, settings)
        if on and unmet:
            console.print(f"    [yellow]needs: {', '.join(unmet)}[/yellow]")
    console.print("")
    console.print(_secret_line(LLM_API_KEY_ENV))
    console.print(_secret_line(WEBHOOK_URL_ENV))
    console.print("")
    console.print("For scan politeness and ranking weights, see `boardwatch config`.")


@settings_app.callback(invoke_without_command=True)
def _default(ctx: typer.Context) -> None:
    """Print the features menu when run with no subcommand."""
    if ctx.invoked_subcommand is not None:
        return
    _print_menu(_load_or_exit(ctx.obj))
