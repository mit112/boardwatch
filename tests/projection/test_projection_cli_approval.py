"""`approve-projection`: a controlling terminal, or nothing is approved.

Every test drives the real Typer app (`boardwatch.cli.app.app`) through `CliRunner`, exactly as
`tests/profile_bundle/test_profile_bundle_cli_approval.py` does for `approve`. The only thing any
test replaces is the `ApprovalTerminal` — everything downstream (digest, resolution, the stamp
file) is the production code, so a test cannot approve anything by a route a script could not also
take.

`example_declaration` (`tests/projection/conftest.py`) sets `BOARDWATCH_CONFIG_DIR` and
materialises a promoted synthetic bundle at the CLI's own default bundle location
(`config_dir / "career-profile"`), so a test that passes no `--bundle` still resolves one. It
returns the declaration's path; `path.parent` is the config dir a test needs to check what the
command did — or did not — write.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from typer.testing import CliRunner

from boardwatch.cli import projection_cmd
from boardwatch.cli.app import app
from boardwatch.profile_bundle.paths import BUNDLE_DIR_NAME
from boardwatch.profile_bundle.storage import read_current_once
from boardwatch.projection.declaration import load_declaration, projection_digest
from boardwatch.projection.stamp import APPROVALS_DIR, read_stamp


@dataclass
class FakeTerminal:
    """The only thing a test replaces. It answers; it decides nothing."""

    controlling: bool = True
    answer: str = "approve"
    shown: list[str] = field(default_factory=list)

    def is_controlling(self) -> bool:
        return self.controlling

    def show(self, text: str) -> None:
        self.shown.append(text)

    def ask(self, prompt: str) -> str:
        return self.answer


def _run(
    terminal: FakeTerminal,
    monkeypatch: pytest.MonkeyPatch,
    decl: Path,
    *extra_args: str,
):
    monkeypatch.setattr(projection_cmd, "approval_terminal", lambda: terminal)
    return CliRunner().invoke(
        app, ["profile-bundle", "approve-projection", "--declaration", str(decl), *extra_args]
    )


def test_a_non_controlling_terminal_writes_nothing(monkeypatch, example_declaration) -> None:
    result = _run(FakeTerminal(controlling=False), monkeypatch, example_declaration)
    assert result.exit_code == 1
    assert not (example_declaration.parent / APPROVALS_DIR).exists()


def test_declining_writes_nothing(monkeypatch, example_declaration) -> None:
    result = _run(FakeTerminal(answer="no"), monkeypatch, example_declaration)
    assert result.exit_code == 1
    assert not (example_declaration.parent / APPROVALS_DIR).exists()


@pytest.mark.parametrize("answer", ["y", "yes", "APPROVE", " approve", "approve ", ""])
def test_only_the_exact_word_approves(monkeypatch, example_declaration, answer) -> None:
    result = _run(FakeTerminal(answer=answer), monkeypatch, example_declaration)
    assert result.exit_code == 1
    assert not (example_declaration.parent / APPROVALS_DIR).exists()


def test_approving_writes_exactly_one_stamp(monkeypatch, example_declaration) -> None:
    result = _run(FakeTerminal(), monkeypatch, example_declaration)
    assert result.exit_code == 0
    assert len(list((example_declaration.parent / APPROVALS_DIR).iterdir())) == 1


def test_the_owner_is_shown_resolved_values_not_template_source(
    monkeypatch, example_declaration
) -> None:
    """The gate's whole point: approving `{@display_name}` tells the owner nothing."""
    terminal = FakeTerminal()
    _run(terminal, monkeypatch, example_declaration)
    shown = "\n".join(terminal.shown)
    assert "{@display_name}" not in shown
    assert "Packet Pantry" in shown


@pytest.mark.parametrize(
    "variable",
    [
        "CI",
        "BOARDWATCH_YES",
        "BOARDWATCH_ASSUME_YES",
        "BOARDWATCH_NON_INTERACTIVE",
        "DEBIAN_FRONTEND",
    ],
)
def test_no_environment_variable_bypasses_the_prompt(
    monkeypatch, example_declaration, variable
) -> None:
    """The spellings are written out rather than derived, because the property is an absence.

    This test replaces nothing — it drives the REAL `approval_terminal()`, whose
    `_StandardTerminal.is_controlling()` reads `CliRunner`'s own non-tty stdin/stdout, not any of
    these variables. It exists to catch a *future* bypass, not to exercise a guard that exists
    today; see the report for the mutation that proves it can still fail.
    """
    monkeypatch.setenv(variable, "1")
    result = CliRunner().invoke(
        app,
        ["profile-bundle", "approve-projection", "--declaration", str(example_declaration)],
    )
    assert result.exit_code != 0
    assert not (example_declaration.parent / APPROVALS_DIR).exists()


@pytest.mark.parametrize("state", ["detached", "closed", "tty"])
def test_the_real_adapter_answers_no_for_anything_not_plainly_a_terminal(
    monkeypatch, state
) -> None:
    """The production adapter across the states a LaunchAgent actually reaches. The `tty` case is
    the control: without it, an adapter that always answered False would pass."""

    class Closed:
        def isatty(self) -> bool:
            raise ValueError("I/O operation on closed file")

    class Terminal:
        def isatty(self) -> bool:
            return True

    replacement = {"detached": None, "closed": Closed(), "tty": Terminal()}[state]
    monkeypatch.setattr(projection_cmd.sys, "stdin", replacement)
    monkeypatch.setattr(projection_cmd.sys, "stdout", Terminal())
    assert projection_cmd.approval_terminal().is_controlling() is (state == "tty")


def test_approving_records_the_bundle_digest_not_the_projection_digest(
    monkeypatch, example_declaration
) -> None:
    """R30 required an end-to-end test that `approve-projection` threads
    `candidate.bundle_digest` through to the written stamp — not `candidate.projection_digest`.
    The pre-existing coverage in `test_projection_stamp.py` only calls `write_stamp`/`read_stamp`
    directly with a hand-supplied constant, which verifies the storage round-trip but not that
    `approve_projection` (`cli/projection_cmd.py`) actually threads the right field: the two
    sit adjacent in its `write_stamp` call, so a copy/paste slip (`bundle_digest=
    candidate.projection_digest`) would pass every test that never drives the real command.
    """
    result = _run(FakeTerminal(), monkeypatch, example_declaration)
    assert result.exit_code == 0

    config_dir = example_declaration.parent
    digest = projection_digest(load_declaration(example_declaration))
    stamp = read_stamp(config_dir, digest)

    # Independent oracle: the CURRENT bundle digest read straight off disk, through the same
    # route `project_pool` itself uses to compute `pool.bundle_digest` — never anything
    # `approve_projection` computed, so this does not verify the writer against itself.
    expected_bundle_digest = read_current_once(config_dir / BUNDLE_DIR_NAME).bundle_digest

    assert stamp.projection_digest == digest
    assert stamp.bundle_digest == expected_bundle_digest
    assert stamp.bundle_digest != stamp.projection_digest


# --------------------------------------------------------------------------------------
# Beyond the brief's sample: code paths this task's own implementation introduces that the
# brief's reference test never exercised (see the report for why each exists).
# --------------------------------------------------------------------------------------


def test_the_declaration_option_defaults_to_config_dir_projection_yaml(
    monkeypatch, example_declaration
) -> None:
    """`example_declaration` already writes the packaged example to
    `config_dir / "projection.yaml"` — the declared default — so omitting `--declaration`
    entirely must resolve the identical file and succeed exactly like passing it explicitly."""
    terminal = FakeTerminal()
    monkeypatch.setattr(projection_cmd, "approval_terminal", lambda: terminal)
    result = CliRunner().invoke(app, ["profile-bundle", "approve-projection"])
    assert result.exit_code == 0
    assert len(list((example_declaration.parent / APPROVALS_DIR).iterdir())) == 1


def test_an_explicit_bundle_override_that_has_no_revision_refuses(
    tmp_path, monkeypatch, example_declaration
) -> None:
    """`example_declaration`'s default bundle location resolves fine; a caller-supplied
    `--bundle` pointing somewhere with no promoted revision must still be the one consulted —
    proving the override is read, not silently ignored in favour of the working default."""
    no_bundle_here = tmp_path / "nowhere"
    result = _run(
        FakeTerminal(), monkeypatch, example_declaration, "--bundle", str(no_bundle_here)
    )
    assert result.exit_code == 1
    assert not (example_declaration.parent / APPROVALS_DIR).exists()


def test_an_unresolvable_declaration_reference_refuses_without_writing_a_stamp(
    monkeypatch, example_declaration
) -> None:
    """`projection_candidate` (new in this task) runs `check_references` against the bundle
    before the owner is ever asked. A declaration naming an entity the bundle does not have must
    refuse cleanly, leaving no stamp — the brief's sample never authored a broken declaration."""
    text = example_declaration.read_text(encoding="utf-8")
    broken = text.replace(
        "no_match_fallback:",
        "  - entity_id: employment.does-not-exist\n"
        "    kind: experience\n"
        "    pinned: true\n"
        "    heading: '{@display_name}'\n"
        "\nno_match_fallback:",
        1,
    )
    assert broken != text, "the fixture's own text no longer contains the anchor being edited"
    example_declaration.write_text(broken, encoding="utf-8")

    result = _run(FakeTerminal(), monkeypatch, example_declaration)
    assert result.exit_code == 1
    assert not (example_declaration.parent / APPROVALS_DIR).exists()
    # `exit_code == 1` alone does not discriminate a typed refusal from an unhandled crash:
    # `CliRunner` reports exit code 1 for BOTH a clean `typer.Exit(code=1)` and an uncaught
    # `KeyError` from `_build_entry` reading a reference `check_references` should have caught
    # first — the mutation below proves it. `SystemExit` is what a clean `typer.Exit` raises;
    # printing the typed issue text is what a caught `ProjectionError` does and a crash does not.
    assert isinstance(result.exception, SystemExit)
    assert "unknown_bundle_id" in result.output
    assert "employment.does-not-exist" in result.output


def test_the_owner_is_shown_every_bullet_the_resume_would_carry(
    monkeypatch, example_declaration
) -> None:
    """T9. `stamp.py` states the gate guarantees no literal reaches a résumé the owner has not
    read, and the screen printed headings, titles, subtitles, dates and locations — and not one
    bullet. Bullets are the bulk of the document and the part a claim edit changes, so the
    approval was being taken on the entry scaffolding rather than on the text.

    Derived from the SAME candidate the command resolves, not from a literal pinned here: a
    fixture-shaped expectation would keep passing if the resolver stopped emitting bullets.
    """
    from boardwatch.core.clock import utcnow
    from boardwatch.projection.pool import projection_candidate

    terminal = FakeTerminal()
    result = _run(terminal, monkeypatch, example_declaration)
    assert result.exit_code == 0

    candidate = projection_candidate(
        example_declaration.parent / BUNDLE_DIR_NAME,
        example_declaration,
        config_dir=example_declaration.parent,
        as_of=utcnow().date(),
    )
    texts = [bullet.text for entry in candidate.entries for bullet in entry.bullets]
    assert texts, "the fixture declares no bullets, so this proves nothing"
    shown = "\n".join(terminal.shown)
    for text in texts:
        assert text in shown, f"the owner never saw the bullet {text!r} they approved"


def test_the_owner_is_shown_the_resume_shell(monkeypatch, example_declaration) -> None:
    """T32. The shell's header and education are rendered onto the projected résumé and are now
    inside the approval's content digest, so they have to be on the screen: a gate that stales on
    text the owner was never shown is a gate they cannot act on (the same argument the skills
    section is on screen for).

    Sentinel values, not the fixture's own "Example …" strings: the packaged bundle's entries
    legitimately mention an example university, so asserting the fixture's default text would
    pass on output that never printed the shell at all.
    """
    from boardwatch.projection.shell import load_shell

    shell_path = example_declaration.parent / "master_resume.yaml"
    shell_path.write_text(
        "header:\n"
        "  - Zzyzx Candidate\n"
        "  - zzyzx@example.com\n"
        "education:\n"
        "  - University of Zzyzx\n",
        encoding="utf-8",
    )

    terminal = FakeTerminal()
    result = _run(terminal, monkeypatch, example_declaration)
    assert result.exit_code == 0

    header, education = load_shell(shell_path)
    assert header and education, "the fixture declares no shell, so this proves nothing"
    shown = "\n".join(terminal.shown)
    for line in (*header, *education):
        assert line in shown, f"the owner never saw the shell line {line!r} they approved"
