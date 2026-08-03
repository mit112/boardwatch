"""boardwatch tailor: init/validate/run for the Tier A résumé pipeline (P7, spec §5-6).

An authored, structured YAML résumé is the only input — boardwatch never parses a
résumé, it only renders one. `init` scaffolds that file, `validate` proves it loads and
shows what the taxonomy sees in each bullet, and `run` drives the deterministic,
no-fabrication tailoring pipeline (`reports.tailor.run_tailor`) against one posting.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from boardwatch.cli.context import build_context
from boardwatch.core.settings import Settings
from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.reports.tailor import (
    NoCurrentVersionError,
    UnsupportedFormatError,
    run_tailor,
)
from boardwatch.tailor.load import ResumeLoadError, load_resume, scaffold_template
from boardwatch.tailor.safety import TierASafetyError

console = Console()

tailor_app = typer.Typer(
    no_args_is_help=True, help="Tailor an authored résumé against a posting (local, no LLM)."
)

RESUME_OPTION = typer.Option(None, "--resume", help="Path to the authored résumé YAML.")


def _resume_path(settings: Settings, override: Path | None = None) -> Path:
    return override if override is not None else settings.config_dir / "resume.yaml"


@tailor_app.command("init")
def init_cmd(
    ctx: typer.Context,
    force: bool = typer.Option(  # noqa: B008
        False, "--force", help="Overwrite an existing resume.yaml."
    ),
) -> None:
    """Scaffold an authored résumé YAML at {config_dir}/resume.yaml."""
    app_ctx = build_context(ctx.obj, ensure=False)
    path = _resume_path(app_ctx.settings)
    if path.exists() and not force:
        console.print(f"{path} already exists; pass --force to overwrite")
        raise typer.Exit(code=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(scaffold_template(), encoding="utf-8")
    console.print(f"wrote {path}")


@tailor_app.command("validate")
def validate_cmd(ctx: typer.Context, resume_path: Path | None = RESUME_OPTION) -> None:
    """Load the authored résumé and report entry/bullet counts plus per-bullet skills."""
    app_ctx = build_context(ctx.obj, ensure=False)
    settings = app_ctx.settings
    try:
        resume = load_resume(_resume_path(settings, resume_path))
    except ResumeLoadError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1) from exc
    taxonomy = load_taxonomy(settings.config_dir)
    bullet_count = sum(len(entry.bullets) for entry in resume.entries)
    console.print(f"{len(resume.entries)} entries · {bullet_count} bullets")
    for entry in resume.entries:
        for bullet in entry.bullets:
            skills = ", ".join(sorted(taxonomy.extract(bullet.text))) or "none"
            # markup=False: rich reads the [entry_id] bracket as a style tag and swallows it.
            console.print(f"  [{entry.entry_id}] {bullet.bullet_id}: {skills}", markup=False)


@tailor_app.command("run")
def run_cmd(
    ctx: typer.Context,
    posting_id: int = typer.Argument(..., help="Posting id (the # column of top)."),  # noqa: B008
    resume_path: Path | None = RESUME_OPTION,
    out_dir: Path | None = typer.Option(  # noqa: B008
        None, "--out", help="Output directory (default {data_dir}/tailored)."
    ),
    fmt: str = typer.Option(  # noqa: B008
        "typst", "--format", help="Render format (typst is the only 1.0 adapter)."
    ),
    dry_run: bool = typer.Option(  # noqa: B008
        False, "--dry-run", help="Render and report without writing artifacts."
    ),
) -> None:
    """Tailor the authored résumé against one posting's JD skills."""
    app_ctx = build_context(ctx.obj)
    settings = app_ctx.settings
    try:
        result = run_tailor(
            app_ctx.engine,
            settings,
            posting_id,
            resume_path=_resume_path(settings, resume_path),
            out_dir=out_dir if out_dir is not None else settings.data_dir / "tailored",
            fmt=fmt,
            dry_run=dry_run,
        )
    except (
        ResumeLoadError,
        NoCurrentVersionError,
        TierASafetyError,
        UnsupportedFormatError,
    ) as exc:
        console.print(str(exc))
        raise typer.Exit(code=1) from exc

    jd_skills = ", ".join(result.jd_skills) or "none"
    console.print(f"posting {result.posting_id} · jd skills: {jd_skills}")
    console.print(
        f"kept {len(result.kept)} · dropped {len(result.dropped)} · swaps {len(result.swaps)}"
    )
    for row in result.bullets:
        covered = ", ".join(row["jd_skills_covered"]) or "no jd skills"
        line = f"  {row['op']:<9} [{row['entry_id']}] {row['bullet_id']}: {covered}"
        if row["op"] == "swapped":
            swaps = ", ".join(f"{s['from']} -> {s['to']}" for s in row["swaps"])
            line += f" · {swaps}"
        console.print(line, markup=False)  # see validate_cmd: [entry_id] is not rich markup
    console.print("guarantee: PASS (Tier A no-fabrication check enforced before write)")
    if result.dry_run:
        console.print("dry run — source only, nothing written")
    elif result.pdf_path is not None:
        console.print(f"pdf: {result.pdf_path}")
    else:
        console.print("source only (no PDF; typst not available or compile failed)")
