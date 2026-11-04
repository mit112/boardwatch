"""boardwatch sponsors build — turn US DOL LCA disclosure workbooks into `sponsors.json`.

Does not open the store: it reads the workbooks and writes one file under the config directory.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape

from boardwatch.core.clock import utcnow
from boardwatch.core.settings import default_config_dir
from boardwatch.rank.sponsors_build import SponsorBuildError, build_sponsors

sponsors_app = typer.Typer(no_args_is_help=True, help="H-1B sponsor data (DOL LCA disclosure).")
console = Console()


@sponsors_app.command("build")
def build(
    files: list[Path] = typer.Argument(  # noqa: B008
        ..., exists=True, dir_okay=False, readable=True, help="LCA disclosure .xlsx files."
    ),
) -> None:
    """Write `sponsors.json` in the config directory from one or more LCA disclosure files."""
    try:
        result = build_sponsors(files, default_config_dir(), today=utcnow().date())
    except SponsorBuildError as exc:
        console.print(f"[red]{escape(str(exc))}[/red]", highlight=False)
        raise typer.Exit(code=1) from exc
    for source in result.sources:
        console.print(
            f"{source.file}: read {source.rows_read} rows, "
            f"{source.h1b_rows} H-1B, counted {source.rows_counted}",
            highlight=False,
        )
    dropped = result.dropped_short_name + result.dropped_no_computing + result.dropped_secondary
    console.print(
        f"employers: seen {result.employers_seen}, kept {result.kept}, dropped {dropped} "
        f"(no computing row {result.dropped_no_computing}, "
        f"secondary-entity share at least 50% {result.dropped_secondary}, "
        f"name too short {result.dropped_short_name})",
        highlight=False,
    )
    console.print(f"wrote {result.path}", highlight=False, soft_wrap=True)
