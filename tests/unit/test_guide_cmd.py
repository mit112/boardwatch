"""`boardwatch guide` / `boardwatch skill` — the generated agent guide and the file it points at.

The properties that matter: every command this program has is described, nothing described is
missing from the program, every effect label is one of the closed set, and a label cannot claim
less than the code does — a command whose source opens the store through the migrating context
must say it touches the store, and a command that never opens the store must not claim to.
"""

from __future__ import annotations

import inspect
import json
import re

from typer.core import TyperCommand, TyperGroup
from typer.testing import CliRunner

from boardwatch.cli import guide_cmd
from boardwatch.cli.app import app
from boardwatch.cli.guide_cmd import (
    EFFECTS,
    ENTRIES,
    SECTIONS,
    SKILL_VERSION,
    STORE_EFFECTS,
    leaf_commands,
    migrates,
    render_guide,
)

runner = CliRunner()


def _leaves() -> dict[str, TyperCommand | TyperGroup]:
    return dict(leaf_commands(app))


def test_every_command_has_an_entry_and_every_entry_names_a_command() -> None:
    leaves = set(_leaves())
    assert leaves - set(ENTRIES) == set(), "commands with no guide entry"
    assert set(ENTRIES) - leaves == set(), "guide entries for commands that do not exist"


def test_every_effect_label_is_from_the_closed_set() -> None:
    for name, entry in ENTRIES.items():
        assert entry.effects, name
        assert set(entry.effects) <= EFFECTS, (name, entry.effects)
        if "pure" in entry.effects:
            assert entry.effects == ("pure",), name


def test_a_command_that_migrates_declares_a_store_effect() -> None:
    for name, command in _leaves().items():
        if migrates(command):
            assert set(ENTRIES[name].effects) & STORE_EFFECTS, (
                f"{name} opens the store through the default context but its entry says "
                f"{ENTRIES[name].effects}"
            )


def test_a_command_without_a_context_does_not_claim_the_store() -> None:
    for name, command in _leaves().items():
        assert command.callback is not None, name
        source = inspect.getsource(inspect.unwrap(command.callback))
        if "build_context(" not in source:
            assert not set(ENTRIES[name].effects) & STORE_EFFECTS, (
                f"{name} never opens the store but its entry says {ENTRIES[name].effects}"
            )


def test_the_guide_prints_every_command_and_section_in_order() -> None:
    result = runner.invoke(app, ["guide"])
    assert result.exit_code == 0, result.output
    out = result.stdout
    for name, _ in SECTIONS:
        assert name.upper() in out
    commands = out[out.index("COMMANDS\n") :]
    usage_names = [
        line[len("boardwatch ") :].split(" <")[0].split(" [")[0]
        for line in commands.splitlines()
        if line.startswith("boardwatch ")
    ]
    assert usage_names == list(_leaves())
    # the beginner journey and the differentiator are still named, in order
    steps = [
        "boardwatch init",
        "boardwatch scan",
        "boardwatch top",
        "boardwatch show",
        "boardwatch track add",
    ]
    journey = out[out.index("JOURNEY") : out.index("STORE")]
    order = [journey.index(step) for step in steps]
    assert order == sorted(order)
    assert "boardwatch run" in journey
    assert "eligible" in out


def test_the_migration_line_is_derived_from_the_source_not_the_entry() -> None:
    leaves = _leaves()
    show = render_guide(app, ["show"])
    assert "applies pending schema migrations" in show
    assert migrates(leaves["show"])
    coverage = render_guide(app, ["coverage"])
    assert "applies pending schema migrations" not in coverage
    assert not migrates(leaves["coverage"])


def test_one_part_prints_only_that_part() -> None:
    result = runner.invoke(app, ["guide", "track", "add"])
    assert result.exit_code == 0
    assert result.stdout.startswith("boardwatch track add ")
    assert "boardwatch track list" not in result.stdout
    section = runner.invoke(app, ["guide", "store"])
    assert section.exit_code == 0
    assert section.stdout.startswith("STORE\n")
    missing = runner.invoke(app, ["guide", "no", "such"])
    assert missing.exit_code == 1
    assert "no command or section named 'no such'" in missing.stderr
    assert missing.stdout == ""


def test_guide_needs_no_profile_or_store() -> None:
    result = runner.invoke(app, ["guide"])
    assert result.exit_code == 0
    assert "no profile yet" not in result.stdout


def test_skill_names_one_command_and_its_version() -> None:
    result = runner.invoke(app, ["skill"])
    assert result.exit_code == 0
    text = result.stdout
    assert f"boardwatch guide --skill {SKILL_VERSION}" in text
    # The skill file sits in someone's skills folder for months. The only commands it may name
    # are the three whose names are load-bearing and stable; every other command is described
    # by the guide the program itself prints, so a stale copy cannot describe one that moved.
    named = set(re.findall(r"`boardwatch ([a-z-]+)", text))
    assert named <= {"guide", "run", "scan"}, named
    assert "--json" not in text


def test_a_stale_skill_file_is_announced_and_a_current_one_is_not() -> None:
    stale = runner.invoke(app, ["guide", "--skill", str(SKILL_VERSION - 1), "version"])
    assert stale.exit_code == 0
    assert stale.stdout.startswith(
        "The copy of the boardwatch skill file you have saved is out of date"
    )
    current = runner.invoke(app, ["guide", "--skill", str(SKILL_VERSION), "version"])
    assert current.exit_code == 0
    assert current.stdout.startswith("boardwatch version")


def test_the_guide_is_plain_text_a_pipe_can_carry() -> None:
    text = render_guide(app)
    assert "[bold]" not in text and "[/" not in text
    json.dumps(text)  # nothing in it that is not a string
    assert guide_cmd.SKILL_TEXT.endswith("\n")
