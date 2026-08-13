"""`approve-projection`: a controlling terminal, or nothing is approved.

Registered onto `profile_bundle_app` by `cli/profile_bundle_cmd.py`, never the other way — that
module imports this one to register the command, so this module must not import anything back from
it. `CONFIRMATION_WORD` and `approval_terminal` come from `cli/_approval.py`, the shared leaf
module both command modules import; a leaf import satisfies the one-way registration direction
without duplicating the seam.

**No `--yes`, no environment variable and no piped answer.** The refusal is structural: there is
no code path in this module that reads an environment variable to decide whether to prompt, and
`approval_terminal()`'s `is_controlling()` is what a detached or redirected process actually
reaches.

The command shows the owner every declared entry's templated fields already resolved against the
bundle's CURRENT revision — `projection.pool.projection_candidate` — never the template source, so
approving means having seen the literal words a résumé would carry. That resolution needs no
existing approval: `projection_candidate` performs no owner-gate check, because it computes the
very thing the gate is checked against (see its own docstring in `projection/pool.py`).

**`projection.pool` is imported inside the command, not at module level, and this is load-bearing,
not style.** `profile_bundle_cmd.py`'s own docstring states "No database" as one of the three
rules it is answerable for, and `tests/profile_bundle/test_profile_bundle_cli.py`'s
`test_the_command_module_imports_no_store_module` enforces it structurally: importing
`profile_bundle_cmd` must not pull `boardwatch.store` into `sys.modules` at all, regardless of
whether anything is ever queried. `projection.pool` transitively reaches
`projection.shell` → `tailor.load` → `reports.resume_gate` → `tailor.plan` →
`extract.taxonomy` → `boardwatch.store.tables` — a pre-existing chain in already-shipped code
(Tasks 7 and 12), not something this task adds. Importing `projection_cmd` eagerly from
`profile_bundle_cmd.py` would drag that whole chain in at CLI-module-import time and break the
guard. `cli/app.py`'s `version()` command defers `from boardwatch.store.db import
schema_revision` the same way, for the identical reason — this is that codebase's own idiom for
it, not a new one.
"""

from __future__ import annotations

# `sys` is not read anywhere below: `_StandardTerminal.is_controlling` lives in `cli/_approval.py`.
# The import stays so `monkeypatch.setattr(projection_cmd.sys, "stdin", …)`
# (`tests/projection/test_projection_cli_approval.py`) still finds a `sys` attribute here — it
# patches the one shared `sys` module, which `_approval.py`'s `sys.stdin`/`sys.stdout` reads too.
import sys  # noqa: F401
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from boardwatch.cli._approval import CONFIRMATION_WORD, approval_terminal
from boardwatch.core.settings import load_settings
from boardwatch.profile_bundle.errors import ProfileBundleError
from boardwatch.profile_bundle.paths import resolve_bundle_root
from boardwatch.projection.errors import ProjectionError
from boardwatch.projection.stamp import write_stamp

if TYPE_CHECKING:
    # Type-only: `boardwatch.projection.pool` is imported for real inside `approve_projection`
    # itself, never at module level. See the module docstring.
    from boardwatch.projection.pool import ProjectionCandidate

DECLARATION_OPTION = typer.Option(  # noqa: B008
    None,
    "--declaration",
    help="Projection declaration path (default: <config dir>/projection.yaml).",
)
BUNDLE_OPTION = typer.Option(  # noqa: B008
    None, "--bundle", help="Bundle root (default: <config dir>/career-profile)."
)


def _prompt_text(candidate: ProjectionCandidate) -> str:
    """What the owner reads before answering: every declared entry's resolved template fields.

    Prints the resolved value from `candidate.entries` — never the raw template string from
    `projection.yaml` — so the owner approves the literal text a résumé would carry.
    """
    lines = [
        "Approving projection.yaml.",
        f"Projection digest: {candidate.projection_digest}",
        "",
    ]
    if candidate.entries:
        noun = "entry" if len(candidate.entries) == 1 else "entries"
        lines.append(f"{len(candidate.entries)} declared {noun} with resolved template values:")
        for entry in candidate.entries:
            lines.append(f"  {entry.entry_id}:")
            lines.append(f"    heading: {entry.heading}")
            if entry.title is not None:
                lines.append(f"    title: {entry.title}")
            if entry.subtitle is not None:
                lines.append(f"    subtitle: {entry.subtitle}")
            if entry.dates is not None:
                lines.append(f"    dates: {entry.dates}")
            if entry.location is not None:
                lines.append(f"    location: {entry.location}")
    else:
        lines.append("No entries declared; the stamp authorises the declaration itself.")
    lines.append("")
    return "\n".join(lines)


def approve_projection(
    ctx: typer.Context,
    declaration: Path | None = DECLARATION_OPTION,
    bundle: Path | None = BUNDLE_OPTION,
) -> None:
    """Record the owner's approval of `projection.yaml`'s exact resolved content, on a
    controlling terminal.

    Mirrors `profile-bundle approve` (`cli/profile_bundle_cmd.py:979-1051`): there is no `--yes`,
    no environment variable and no piped answer. §13's fail-safe direction applies identically —
    a run that cannot establish it has the owner's attention has not got it, so it refuses rather
    than assuming consent.
    """
    config_dir = load_settings(data_dir=ctx.obj).config_dir
    declaration_path = declaration if declaration is not None else config_dir / "projection.yaml"
    bundle_root = resolve_bundle_root(config_dir, bundle)
    terminal = approval_terminal()

    if not terminal.is_controlling():
        typer.echo(
            "approve-projection needs a controlling terminal on both stdin and stdout. There is "
            "no --yes and no environment override: the owner is asked, or nothing is approved. "
            "Run it yourself in a terminal",
            err=True,
        )
        raise typer.Exit(code=1)

    # Deferred: see the module docstring on why `projection.pool` is never imported at module
    # level here.
    from boardwatch.projection.pool import projection_candidate

    try:
        candidate = projection_candidate(bundle_root, declaration_path, as_of=date.today())
    except (ProjectionError, ProfileBundleError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    terminal.show(_prompt_text(candidate))
    if terminal.ask(f"Type {CONFIRMATION_WORD!r} to approve") != CONFIRMATION_WORD:
        typer.echo(
            "the confirmation did not match, so nothing was approved and nothing was written",
            err=True,
        )
        raise typer.Exit(code=1)

    path = write_stamp(
        config_dir, digest=candidate.projection_digest, approved_at=datetime.now(UTC)
    )
    typer.echo(f"approved projection {candidate.projection_digest}")
    typer.echo(f"stamp: {path}")
