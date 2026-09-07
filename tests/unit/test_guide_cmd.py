"""`boardwatch guide` / `boardwatch skill` — the generated agent guide and the file it points at.

The properties that matter: every command this program has is described, nothing described is
missing from the program, every effect label is one of the closed set, and a label cannot claim
less than the code does — a command whose source opens the store through the migrating context
must say it touches the store, and a command that never opens the store must not claim to.

Both of those last two are TEXTUAL proxies for a real property, and for the two commands that
reach the store one frame down they certify the wrong answer. Those two carry an explicit
`Entry.migrates`, are exempt from the proxies, and are pinned instead by
`OVERRIDE_EVIDENCE` and `CORRECTED_EFFECTS` below, which were read off the commands' sources.
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
from boardwatch.store.applications import APPLIED_STATUSES

runner = CliRunner()


#: The two commands whose store access is one frame down, where `migrates()` and the
#: `build_context(`-absence proxy below both read the wrong frame and answer wrong. An entry may
#: override the derivation only if its own text says where the store is really reached — so the
#: exemption below can never quietly certify a third command's wrong label.
OVERRIDE_EVIDENCE = {
    "settings toggle": "through `toggle_feature`, which opens the default context and migrates",
    "web": (
        "opens the store read-only through `get_readonly_engine`, never migrating; the four "
        "mark routes write"
    ),
}

#: Every effect label this branch's review corrected after reading the command's source:
#: `companies discover` / `discover-grnh` (`companies_cmd.py` point-queries the store, and
#: `grnh_resolve` fetches), `eligibility summary` / `abstain` (`run_eligibility` is called only
#: from `eligibility run`, so neither writes a row), `settings toggle` (`toggle_feature` →
#: `build_context`), `web` (`get_readonly_engine` plus four mark routes), `profile-bundle project`
#: (serialises to stdout and takes no `--out`). Exact tuples: each was wrong in a direction an
#: unattended agent would act on, so a regression toward the old label has to fail here.
CORRECTED_EFFECTS = {
    "companies discover": ("network", "reads store", "writes files"),
    "companies discover-grnh": ("network", "reads store", "writes files"),
    "eligibility summary": ("reads store",),
    "eligibility abstain": ("reads store",),
    "settings toggle": ("interactive", "writes files", "writes store"),
    "web": ("reads store", "writes store", "writes files", "network"),
    "profile-bundle project": ("pure",),
}


def _leaves() -> dict[str, TyperCommand | TyperGroup]:
    return dict(leaf_commands(app))


def _flat(text: str) -> str:
    """One entry's text with its wrapping collapsed, so a phrase can be asserted across lines."""
    return " ".join(text.split())


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
        if ENTRIES[name].migrates is not None:
            continue  # the derivation reads the wrong frame here; see OVERRIDE_EVIDENCE
        if migrates(command):
            assert set(ENTRIES[name].effects) & STORE_EFFECTS, (
                f"{name} opens the store through the default context but its entry says "
                f"{ENTRIES[name].effects}"
            )


def test_a_command_without_a_context_does_not_claim_the_store() -> None:
    for name, command in _leaves().items():
        if ENTRIES[name].migrates is not None:
            continue  # this proxy is exactly what it gets wrong; see OVERRIDE_EVIDENCE
        assert command.callback is not None, name
        source = inspect.getsource(inspect.unwrap(command.callback))
        if "build_context(" not in source:
            assert not set(ENTRIES[name].effects) & STORE_EFFECTS, (
                f"{name} never opens the store but its entry says {ENTRIES[name].effects}"
            )


def test_every_migration_override_says_where_the_store_is_really_reached() -> None:
    """The exemption above is only sound while each override is justified in its own text."""
    overridden = {name for name, entry in ENTRIES.items() if entry.migrates is not None}
    assert overridden == set(OVERRIDE_EVIDENCE), overridden
    for name, phrase in OVERRIDE_EVIDENCE.items():
        assert phrase in _flat(ENTRIES[name].text), name


def test_the_labels_the_source_disagreed_with_stay_corrected() -> None:
    for name, effects in CORRECTED_EFFECTS.items():
        assert ENTRIES[name].effects == effects, (name, ENTRIES[name].effects)


def test_settings_toggle_carries_the_migration_note_and_web_does_not() -> None:
    """The override reaches the rendered guide, in both directions."""
    note = "applies pending schema migrations first"
    assert note in render_guide(app, ["settings", "toggle"])
    assert note not in render_guide(app, ["web"])


def test_the_guide_only_teaches_a_status_that_actually_suppresses() -> None:
    """`track add`'s default status is `interested`, which is deliberately outside
    `APPLIED_STATUSES` — so the bare command the journey used to teach suppresses nothing and
    the role re-surfaces on the next `top`."""
    journey = dict(SECTIONS)["journey"]
    line = next(line for line in journey.splitlines() if "track add" in line)
    assert any(f"--status {status}" in line for status in APPLIED_STATUSES), line
    entry = _flat(ENTRIES["track add"].text)
    assert "`interested`" in entry and "suppresses nothing" in entry, entry
    for status in APPLIED_STATUSES:
        assert f"`{status}`" in entry, (status, entry)


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
