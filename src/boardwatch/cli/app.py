"""boardwatch CLI entry point."""

from importlib.metadata import version as package_version
from pathlib import Path

import typer
from rich.console import Console

from boardwatch.cli.scan_cmd import scan as _scan

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()


@app.callback()
def main(
    ctx: typer.Context,
    data_dir: Path | None = typer.Option(  # noqa: B008
        None, "--data-dir", help="Override the data directory (default: platform data dir)."
    ),
) -> None:
    """boardwatch — self-hosted job radar over official ATS APIs."""
    ctx.obj = data_dir


@app.command()
def version() -> None:
    """Print the boardwatch version and schema revision."""
    from boardwatch.store.db import schema_revision

    console.print(f"boardwatch {package_version('boardwatch')} · schema {schema_revision()}")


app.command("scan")(_scan)
