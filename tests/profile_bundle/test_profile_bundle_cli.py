"""The `profile-bundle` command family: registration, path resolution, and the no-database rule.

Three properties live here, and each is the kind that only a command-level test can see:

- **The surface is exactly the twelve commands design §7/§19 name.** The expected list is written
  out here rather than read back off the Typer app, because a test that asked the app what it
  registers would agree with any surface at all.
- **The bundle root is `config_dir / "career-profile"` unless `--bundle` says otherwise.** That is
  `paths.resolve_bundle_root`'s contract, and the command layer is the only place it is applied.
- **No `profile-bundle` command opens the database.** The bundle is a filesystem-only subsystem
  (`profile_bundle/__init__.py` says so); a command that reached `build_context` would create and
  migrate `boardwatch.db` in a pristine data dir, and the cheapest way to find that out is to look
  for the file afterwards.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
import typer.main
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.profile_bundle.paths import BUNDLE_DIR_NAME, drafts_dir

#: Design §19's command surface, transcribed. The outside fact this file pins.
EXPECTED_COMMANDS = (
    "add-evidence",
    "approve",
    "checkout",
    "conflicts",
    "init",
    "inspect",
    "inventory",
    "migrate",
    "promote",
    "rebase-draft",
    "resolve-conflict",
    "validate",
)


@dataclass(frozen=True)
class Env:
    data_dir: Path
    config_dir: Path

    @property
    def bundle_root(self) -> Path:
        return self.config_dir / BUNDLE_DIR_NAME

    @property
    def database(self) -> Path:
        return self.data_dir / "boardwatch.db"


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    config_dir = tmp_path / "cfg"
    config_dir.mkdir(parents=True)
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(config_dir))
    return Env(data_dir=tmp_path / "data", config_dir=config_dir)


def run(env: Env, args: list[str]):  # type: ignore[no-untyped-def]
    return CliRunner().invoke(app, ["--data-dir", str(env.data_dir), "profile-bundle", *args])


# --------------------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------------------


def test_the_group_lists_every_command_design_names() -> None:
    result = CliRunner().invoke(app, ["profile-bundle", "--help"])
    assert result.exit_code == 0, result.output
    for name in EXPECTED_COMMANDS:
        assert name in result.output, f"{name} is not offered by profile-bundle"


def test_migrate_takes_no_draft_argument() -> None:
    """T17 writes nothing at schema v1, so a `--draft` here could only be silently ignored.

    Accepting an argument that cannot affect the outcome discards the operator's stated intent,
    which is worse than refusing it. Design §7 lists the bare command.
    """
    result = CliRunner().invoke(app, ["profile-bundle", "migrate", "--help"])
    assert result.exit_code == 0, result.output
    assert "--draft" not in result.output


def test_approve_offers_no_confirmation_bypass() -> None:
    """§13: no `--yes`, and none of its usual synonyms either.

    Asserted against the registered options rather than the help text, because the help text
    *mentions* `--yes` in order to say it does not exist. The list of spellings is written out here
    — a test that asked the command which flags it has could never fail.
    """
    approve = typer.main.get_command(app).commands["profile-bundle"].commands["approve"]  # type: ignore[attr-defined]
    registered = {name for param in approve.params for name in param.opts}
    assert registered.isdisjoint(
        {"--yes", "-y", "--force", "-f", "--no-confirm", "--non-interactive", "--assume-yes"}
    ), registered


# --------------------------------------------------------------------------------------
# Where the bundle lives
# --------------------------------------------------------------------------------------


def test_init_defaults_to_the_career_profile_directory_under_config(env: Env) -> None:
    result = run(env, ["init", "--draft", "baseline"])
    assert result.exit_code == 0, result.output
    assert (drafts_dir(env.bundle_root) / "baseline" / "manifest.yaml").is_file()


def test_bundle_option_overrides_the_default_root(env: Env, tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    result = run(env, ["init", "--bundle", str(elsewhere), "--draft", "baseline"])
    assert result.exit_code == 0, result.output
    assert (drafts_dir(elsewhere) / "baseline" / "manifest.yaml").is_file()
    assert not env.bundle_root.exists()


# --------------------------------------------------------------------------------------
# No database
# --------------------------------------------------------------------------------------


def test_no_command_creates_the_database(env: Env, tmp_path: Path) -> None:
    """Every one of the twelve, against a pristine data dir.

    Run in an order that reaches real work rather than an early refusal, so the assertion covers
    the paths that actually touch the filesystem — a command that refused at its first line would
    never have got near `build_context` either way.
    """
    assert run(env, ["init", "--draft", "baseline"]).exit_code == 0
    invocations = [
        ["inventory"],
        ["conflicts"],
        ["migrate"],
        ["validate", "--draft", "baseline"],
        ["inspect", "fact.example.name.001"],
        ["checkout", "--draft", "second"],
        ["rebase-draft", "--draft", "baseline"],
        ["approve", "--draft", "baseline"],
        ["promote", "--draft", "baseline", "--summary", "nothing"],
        ["add-evidence", "--draft", "baseline", "--evidence-file",
         str(tmp_path / "absent.yaml"), "--capture", str(tmp_path / "absent.txt")],
        ["resolve-conflict", "--draft", "baseline", "--ruling-file", str(tmp_path / "absent.yaml")],
    ]
    for args in invocations:
        run(env, args)
        assert not env.database.exists(), f"{args} created {env.database.name}"
    assert not env.data_dir.exists(), "no profile-bundle command should create the data directory"


def test_the_command_module_imports_no_store_module() -> None:
    """Checked in a fresh interpreter, because this session has already imported half of boardwatch.

    `sys.modules` after the import is the whole transitive closure, so this sees an indirect
    import the module's own `import` lines would not show.
    """
    probe = (
        "import sys; import boardwatch.cli.profile_bundle_cmd; "
        "print([m for m in sys.modules if m.startswith('boardwatch.store')])"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )
    assert completed.stdout.strip() == "[]", completed.stdout


def test_the_tailor_command_module_still_does_not_reach_the_bundle() -> None:
    """The §4.2 boundary, from the side T18 could break: `app.py` now imports both.

    T19 owns the full isolation contract; this is the one-line regression guard for the change
    that introduced the risk.
    """
    probe = (
        "import sys; import boardwatch.cli.tailor_cmd; "
        "print([m for m in sys.modules if m.startswith('boardwatch.profile_bundle')])"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )
    assert completed.stdout.strip() == "[]", completed.stdout


# --------------------------------------------------------------------------------------
# The one message a fresh bundle always produces
# --------------------------------------------------------------------------------------


def test_a_fresh_draft_is_told_where_to_author_its_identity(env: Env) -> None:
    """`init` deliberately leaves `facts/identity.yaml` absent (drafts.py says why).

    The structural layer reports it as a missing declared file, which reads as corruption. The
    command layer is where that becomes an instruction, and the machine message must not change:
    a script matching on the diagnostic would break if it did.
    """
    assert run(env, ["init", "--draft", "baseline"]).exit_code == 0
    human = run(env, ["validate", "--draft", "baseline"])
    assert human.exit_code == 1, human.output
    assert "facts/identity.yaml" in human.output
    assert "author" in human.output.lower()

    machine = run(env, ["validate", "--draft", "baseline", "--json"])
    payload = json.loads(machine.output)
    identity = [
        finding for finding in payload["diagnostics"] if finding["path"] == "facts/identity.yaml"
    ]
    assert identity, payload
    assert identity[0]["code"] == "missing_required_file"
    assert "an absent catalog is not an empty one" in identity[0]["message"]
    assert "author" not in identity[0]["message"].lower()
