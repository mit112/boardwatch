"""boardwatch CLI entry point."""

from importlib.metadata import version as package_version

import typer
from rich.console import Console

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()


@app.callback()
def main() -> None:
    """boardwatch — self-hosted job radar over official ATS APIs."""


@app.command()
def version() -> None:
    """Print the boardwatch version."""
    console.print(f"boardwatch {package_version('boardwatch')}")
