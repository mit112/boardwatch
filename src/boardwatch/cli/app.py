"""boardwatch CLI entry point."""

from importlib.metadata import version as package_version
from pathlib import Path

import typer
from rich.console import Console

from boardwatch.cli.companies_cmd import companies_app
from boardwatch.cli.config_cmd import config_app
from boardwatch.cli.coverage_cmd import coverage as _coverage
from boardwatch.cli.digest_cmd import digest as _digest
from boardwatch.cli.doctor_cmd import doctor as _doctor
from boardwatch.cli.eligibility_cmd import eligibility_app
from boardwatch.cli.export_cmd import export as _export
from boardwatch.cli.guide_cmd import guide as _guide
from boardwatch.cli.guide_cmd import skill as _skill
from boardwatch.cli.identities_cmd import identities_app
from boardwatch.cli.init_cmd import init as _init
from boardwatch.cli.init_cmd import role_taxonomy as _role_taxonomy
from boardwatch.cli.ledger_cmd import ledger_app
from boardwatch.cli.notify_cmd import notify as _notify
from boardwatch.cli.postings_cmd import postings_app
from boardwatch.cli.profile_bundle_cmd import profile_bundle_app
from boardwatch.cli.profile_cmd import profile_app
from boardwatch.cli.projection_cmd import resume_app
from boardwatch.cli.run_cmd import run as _run
from boardwatch.cli.scan_cmd import scan as _scan
from boardwatch.cli.seeds_cmd import seeds as _seeds
from boardwatch.cli.settings_cmd import settings_app
from boardwatch.cli.show_cmd import show as _show
from boardwatch.cli.stats_cmd import stats as _stats
from boardwatch.cli.tailor_cmd import tailor_app
from boardwatch.cli.top_cmd import top as _top
from boardwatch.cli.track_cmd import track_app
from boardwatch.cli.verify_cmd import verify as _verify
from boardwatch.cli.web_cmd import web as _web

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()


SETUP = "Set up"
DAILY = "Daily"
REVIEW = "Review and track"
AGENTS = "Help for agents"
ADVANCED = "Advanced and maintenance"


def _version_flag(value: bool) -> None:
    if value:
        version()
        raise typer.Exit


@app.callback()
def main(
    ctx: typer.Context,
    data_dir: Path | None = typer.Option(  # noqa: B008
        None, "--data-dir", help="Override the data directory (default: platform data dir)."
    ),
    _version: bool = typer.Option(
        False,
        "--version",
        callback=_version_flag,
        is_eager=True,
        help="Print the version and schema revision, then exit.",
    ),
) -> None:
    """boardwatch — self-hosted job radar over official ATS APIs."""
    ctx.obj = data_dir


@app.command(rich_help_panel=SETUP)
def version() -> None:
    """Print the boardwatch version and schema revision."""
    from boardwatch.store.db import schema_revision

    console.print(f"boardwatch {package_version('boardwatch')} · schema {schema_revision()}")


app.command("init", rich_help_panel=SETUP)(_init)
app.add_typer(companies_app, name="companies", rich_help_panel=SETUP)
app.add_typer(profile_app, name="profile", rich_help_panel=SETUP)
# Registered here rather than in profile_cmd: the gatherer lives in init_cmd (R11 pins its
# prompts), and init_cmd already imports profile_cmd.
profile_app.command("role-taxonomy")(_role_taxonomy)
app.command("doctor", rich_help_panel=SETUP)(_doctor)
app.command("scan", rich_help_panel=DAILY)(_scan)
app.command("top", rich_help_panel=DAILY)(_top)
app.command("show", rich_help_panel=DAILY)(_show)
app.command("digest", rich_help_panel=DAILY)(_digest)
app.command("run", rich_help_panel=DAILY)(_run)
app.command("web", rich_help_panel=DAILY)(_web)
app.command("notify", rich_help_panel=DAILY)(_notify)
app.add_typer(eligibility_app, name="eligibility", rich_help_panel=REVIEW)
app.add_typer(track_app, name="track", rich_help_panel=REVIEW)
app.add_typer(tailor_app, name="tailor", rich_help_panel=REVIEW)
app.command("stats", rich_help_panel=REVIEW)(_stats)
app.command("export", rich_help_panel=REVIEW)(_export)
app.add_typer(config_app, name="config", rich_help_panel=SETUP)
app.add_typer(settings_app, name="settings", rich_help_panel=SETUP)
app.command("guide", rich_help_panel=AGENTS)(_guide)
app.command("skill", rich_help_panel=AGENTS)(_skill)
app.command("coverage", rich_help_panel=ADVANCED)(_coverage)
app.command("seeds", rich_help_panel=ADVANCED)(_seeds)
app.add_typer(identities_app, name="identities", rich_help_panel=ADVANCED)
app.add_typer(postings_app, name="postings", rich_help_panel=ADVANCED)
app.add_typer(ledger_app, name="ledger", rich_help_panel=ADVANCED)
app.command("verify", rich_help_panel=ADVANCED)(_verify)
app.add_typer(profile_bundle_app, name="profile-bundle", rich_help_panel=ADVANCED)
app.add_typer(resume_app, name="resume", rich_help_panel=ADVANCED)
