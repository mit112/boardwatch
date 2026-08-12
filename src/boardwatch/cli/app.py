"""boardwatch CLI entry point."""

from importlib.metadata import version as package_version
from pathlib import Path

import typer
from rich.console import Console

from boardwatch.cli.companies_cmd import companies_app
from boardwatch.cli.config_cmd import config_app
from boardwatch.cli.digest_cmd import digest as _digest
from boardwatch.cli.doctor_cmd import doctor as _doctor
from boardwatch.cli.eligibility_cmd import eligibility_app
from boardwatch.cli.export_cmd import export as _export
from boardwatch.cli.identities_cmd import identities_app
from boardwatch.cli.init_cmd import init as _init
from boardwatch.cli.ledger_cmd import ledger_app
from boardwatch.cli.notify_cmd import notify as _notify
from boardwatch.cli.profile_bundle_cmd import profile_bundle_app
from boardwatch.cli.profile_cmd import profile_app
from boardwatch.cli.run_cmd import run as _run
from boardwatch.cli.scan_cmd import scan as _scan
from boardwatch.cli.settings_cmd import settings_app
from boardwatch.cli.show_cmd import show as _show
from boardwatch.cli.stats_cmd import stats as _stats
from boardwatch.cli.tailor_cmd import tailor_app
from boardwatch.cli.top_cmd import top as _top
from boardwatch.cli.track_cmd import track_app
from boardwatch.cli.verify_cmd import verify as _verify

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


app.add_typer(companies_app, name="companies")
app.command("scan")(_scan)
app.command("init")(_init)
app.add_typer(profile_app, name="profile")
app.command("top")(_top)
app.command("show")(_show)
app.add_typer(config_app, name="config")
app.add_typer(settings_app, name="settings")
app.command("doctor")(_doctor)
app.command("digest")(_digest)
app.command("notify")(_notify)
app.add_typer(eligibility_app, name="eligibility")
app.add_typer(track_app, name="track")
app.add_typer(identities_app, name="identities")
app.add_typer(ledger_app, name="ledger")
app.command("export")(_export)
app.add_typer(tailor_app, name="tailor")
app.command("stats")(_stats)
app.command("run")(_run)
app.command("verify")(_verify)
app.add_typer(profile_bundle_app, name="profile-bundle")
