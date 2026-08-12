"""`profile-bundle approve`: the one operator interaction in the family (design §13, §19).

§13 is explicit that this is a deliberate operator-interaction seam and **not** access control: any
process with write permission to the bundle can construct a valid stamp file. What the command owes
is therefore not a security property but three narrower ones, and each has a test here:

- **It refuses without a controlling terminal**, and nothing — no flag, no environment variable, no
  answer piped into stdin — changes that.
- **What the owner sees is what gets recorded**: the candidate digest and the owner-gated
  transitions, in the order the stamp lists them.
- **There is one way to file a stamp.** The tests replace only the terminal, so the digest, the
  decisions, the stamp, its bytes and its path are all the production code. A test that could
  approve by another route would be describing a route a script could take too.

The strongest assertion in the file is the last one: `promote` accepts what `approve` filed. That
reaches the answer through a different path than the one that produced it — promotion recomputes
the candidate digest from disk and looks for a stamp under it, so a stamp filed under the wrong
digest, or in a form the loader cannot read, fails there rather than here.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import pytest
from typer.testing import CliRunner

from boardwatch.cli import profile_bundle_cmd
from boardwatch.cli.app import app
from boardwatch.profile_bundle.approvals import (
    approval_stamp_bytes,
    build_approval_stamp,
    required_approval_decisions,
)
from boardwatch.profile_bundle.canonical import candidate_content_digest
from boardwatch.profile_bundle.models.history import ApprovalStamp
from boardwatch.profile_bundle.paths import approval_path, approvals_dir
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from tests.profile_bundle.conftest import (
    SyntheticBundle,
    parse_documents,
    stored_blob_reader,
)


@dataclass
class FakeTerminal:
    """The only thing a test replaces. It answers; it decides nothing."""

    controlling: bool = True
    answer: str = profile_bundle_cmd.CONFIRMATION_WORD
    shown: list[str] = field(default_factory=list)
    asked: list[str] = field(default_factory=list)

    def is_controlling(self) -> bool:
        return self.controlling

    def show(self, text: str) -> None:
        self.shown.append(text)

    def ask(self, prompt: str) -> str:
        self.asked.append(prompt)
        return self.answer


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config_dir = tmp_path / "cfg"
    config_dir.mkdir(parents=True)
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(config_dir))
    return tmp_path / "data"


def run(data_dir: Path, bundle: SyntheticBundle, args: list[str]):  # type: ignore[no-untyped-def]
    return CliRunner().invoke(
        app,
        [
            "--data-dir",
            str(data_dir),
            "profile-bundle",
            *args,
            "--bundle",
            str(bundle.root),
        ],
    )


def approve(  # type: ignore[no-untyped-def]
    data_dir: Path,
    bundle: SyntheticBundle,
    terminal: FakeTerminal,
    monkeypatch: pytest.MonkeyPatch,
    *,
    extra: list[str] | None = None,
):
    monkeypatch.setattr(profile_bundle_cmd, "approval_terminal", lambda: terminal)
    return run(
        data_dir, bundle, ["approve", "--draft", bundle.draft_name, *(extra or [])]
    )


def expected_candidate(bundle: SyntheticBundle) -> str:
    """The digest computed by a different route than the command's.

    In-memory blob reader against the store's real contents, rather than the filesystem reader the
    command uses, so agreement is not two calls into the same code path.
    """
    return candidate_content_digest(
        parse_documents(bundle.draft), stored_blob_reader(bundle.root), None
    )


# --------------------------------------------------------------------------------------
# There is no way in without a terminal
# --------------------------------------------------------------------------------------


def test_a_pipe_is_refused_by_the_real_terminal_adapter(
    env: Path, synthetic_bundle: SyntheticBundle
) -> None:
    """No patching at all: the production adapter, under a test runner that is not a terminal."""
    result = run(env, synthetic_bundle, ["approve", "--draft", synthetic_bundle.draft_name,
                                         "--json"])
    assert result.exit_code == 1
    codes = {finding["code"] for finding in json.loads(result.output)["diagnostics"]}
    assert codes == {"approval_requires_controlling_tty"}
    assert not approvals_dir(synthetic_bundle.root).exists()


def test_an_answer_piped_into_stdin_does_not_approve(
    env: Path, synthetic_bundle: SyntheticBundle
) -> None:
    result = CliRunner().invoke(
        app,
        [
            "--data-dir",
            str(env),
            "profile-bundle",
            "approve",
            "--draft",
            synthetic_bundle.draft_name,
            "--bundle",
            str(synthetic_bundle.root),
        ],
        input=f"{profile_bundle_cmd.CONFIRMATION_WORD}\n" * 3,
    )
    assert result.exit_code == 1
    assert "controlling terminal" in result.output
    assert not approvals_dir(synthetic_bundle.root).exists()


@pytest.mark.parametrize(
    "variable",
    ["CI", "BOARDWATCH_YES", "BOARDWATCH_ASSUME_YES", "BOARDWATCH_NON_INTERACTIVE", "DEBIAN_FRONTEND"],
)
def test_no_environment_variable_bypasses_the_prompt(
    env: Path,
    synthetic_bundle: SyntheticBundle,
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
) -> None:
    """The spellings are written out here rather than derived, because the property is an absence.

    A test that asked the code which variables it consults could only ever confirm the answer it
    was given.
    """
    monkeypatch.setenv(variable, "1")
    result = run(env, synthetic_bundle, ["approve", "--draft", synthetic_bundle.draft_name])
    assert result.exit_code == 1
    assert not approvals_dir(synthetic_bundle.root).exists()


def test_a_terminal_on_only_one_stream_is_not_a_controlling_terminal(
    env: Path, synthetic_bundle: SyntheticBundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§13 says stdin *or* stdout. Redirecting either one is how a script would run this."""
    terminal = FakeTerminal(controlling=False)
    result = approve(env, synthetic_bundle, terminal, monkeypatch)
    assert result.exit_code == 1
    assert terminal.asked == []
    assert not approvals_dir(synthetic_bundle.root).exists()


def test_the_terminal_is_consulted_before_the_bundle_is_read(
    env: Path, synthetic_bundle: SyntheticBundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A piped caller gets the same answer whatever state the bundle is in.

    Otherwise the refusal an automated caller sees would depend on the bundle, and a script could
    learn from it which drafts exist and whether they are approvable.
    """
    terminal = FakeTerminal(controlling=False)
    monkeypatch.setattr(profile_bundle_cmd, "approval_terminal", lambda: terminal)
    absent = run(env, synthetic_bundle, ["approve", "--draft", "no-such-draft", "--json"])
    present = run(
        env, synthetic_bundle, ["approve", "--draft", synthetic_bundle.draft_name, "--json"]
    )
    assert {finding["code"] for finding in json.loads(absent.output)["diagnostics"]} == {
        finding["code"] for finding in json.loads(present.output)["diagnostics"]
    } == {"approval_requires_controlling_tty"}


# --------------------------------------------------------------------------------------
# On a terminal
# --------------------------------------------------------------------------------------


def test_the_owner_is_shown_the_digest_and_the_gated_transitions(
    env: Path, synthetic_bundle: SyntheticBundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    terminal = FakeTerminal()
    result = approve(env, synthetic_bundle, terminal, monkeypatch)
    assert result.exit_code == 0, result.output
    shown = "\n".join(terminal.shown)
    assert expected_candidate(synthetic_bundle) in shown

    decisions = required_approval_decisions(parse_documents(synthetic_bundle.draft), None)
    assert decisions, "the example must require at least one owner gate for this to mean anything"
    for decision in decisions:
        assert decision.target_record_id in shown


def test_the_transitions_are_shown_in_the_order_the_stamp_records_them(
    env: Path, synthetic_bundle: SyntheticBundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sorted by action then target — the order `required_approval_decisions` returns.

    The expected order is computed here by sorting the targets independently, so this fails if the
    prompt ever reorders them, and it does not simply agree with whatever order it was handed.
    """
    terminal = FakeTerminal()
    assert approve(env, synthetic_bundle, terminal, monkeypatch).exit_code == 0
    shown = "\n".join(terminal.shown)

    decisions = required_approval_decisions(parse_documents(synthetic_bundle.draft), None)
    keys = [(decision.action.value, decision.target_record_id) for decision in decisions]
    assert keys == sorted(keys)
    positions = [shown.index(f"{action} {target}") for action, target in keys]
    assert positions == sorted(positions)


def test_an_inexact_confirmation_declines_and_writes_nothing(
    env: Path, synthetic_bundle: SyntheticBundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    for answer in ("y", "yes", "APPROVE", " approve", "approve ", ""):
        terminal = FakeTerminal(answer=answer)
        result = approve(env, synthetic_bundle, terminal, monkeypatch, extra=["--json"])
        assert result.exit_code == 1, answer
        codes = {finding["code"] for finding in json.loads(result.output)["diagnostics"]}
        assert codes == {"approval_declined"}, answer
        assert not approvals_dir(synthetic_bundle.root).exists(), answer


def test_the_stamp_lands_under_the_candidate_digest_in_the_form_promote_reads(
    env: Path, synthetic_bundle: SyntheticBundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bytes are compared against an independently built stamp, field by field.

    Not byte-for-byte: `approved_at` is the moment the owner answered, and the command reads the
    clock the package deliberately does not. Everything the approval *binds* is compared.
    """
    terminal = FakeTerminal()
    assert approve(env, synthetic_bundle, terminal, monkeypatch).exit_code == 0

    candidate = expected_candidate(synthetic_bundle)
    path = approval_path(synthetic_bundle.root, candidate)
    assert path.is_file(), sorted(p.name for p in approvals_dir(synthetic_bundle.root).iterdir())

    stamp = ApprovalStamp.model_validate(
        load_yaml_bytes(path.read_bytes(), logical_path=PurePosixPath(f"approvals/{path.name}"))
    )
    expected = build_approval_stamp(
        stamp_id="approval-stamp.000001",
        candidate_digest=candidate,
        approved_at=stamp.approved_at,
        decisions=required_approval_decisions(parse_documents(synthetic_bundle.draft), None),
    )
    assert stamp == expected
    assert path.read_bytes() == approval_stamp_bytes(
        expected, logical_path=PurePosixPath(f"approvals/{path.name}")
    )
    assert stamp.approved_via == "controlling_terminal"
    assert stamp.approved_at.tzinfo is not None


def test_promote_accepts_exactly_what_approve_filed(
    env: Path, synthetic_bundle: SyntheticBundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second path: promotion recomputes the digest from disk and looks for a stamp under it."""
    assert approve(env, synthetic_bundle, FakeTerminal(), monkeypatch).exit_code == 0
    promoted = run(
        env,
        synthetic_bundle,
        [
            "promote",
            "--draft",
            synthetic_bundle.draft_name,
            "--summary",
            "the first synthetic revision",
            "--json",
        ],
    )
    assert promoted.exit_code == 0, promoted.output
    body = json.loads(promoted.output)
    assert body["result"]["revision"] == 1
    assert body["result"]["bundle_digest"].startswith("sha256:")


def test_editing_the_draft_after_approval_makes_the_stamp_stale(
    env: Path, synthetic_bundle: SyntheticBundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§13: any subsequent content edit invalidates the approval, by digest rather than by flag."""
    assert approve(env, synthetic_bundle, FakeTerminal(), monkeypatch).exit_code == 0
    manifest = synthetic_bundle.read("manifest.yaml")
    synthetic_bundle.write(
        "manifest.yaml", manifest.replace("predicate_catalog_version: 1", "predicate_catalog_version: 2")
    )
    promoted = run(
        env,
        synthetic_bundle,
        ["promote", "--draft", synthetic_bundle.draft_name, "--summary", "edited", "--json"],
    )
    assert promoted.exit_code == 1
    assert "missing_approval_stamp" in {
        finding["code"] for finding in json.loads(promoted.output)["diagnostics"]
    }


def test_approving_twice_is_idempotent(
    env: Path, synthetic_bundle: SyntheticBundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One candidate, one stamp file. Re-running must not accumulate approvals."""
    assert approve(env, synthetic_bundle, FakeTerminal(), monkeypatch).exit_code == 0
    first = sorted(approvals_dir(synthetic_bundle.root).iterdir())
    assert approve(env, synthetic_bundle, FakeTerminal(), monkeypatch).exit_code == 0
    assert sorted(approvals_dir(synthetic_bundle.root).iterdir()) == first


def test_a_stale_draft_is_refused_rather_than_stamped(
    env: Path, synthetic_bundle: SyntheticBundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stamp for a candidate no promotion will look for is a file with no drain.

    After the first promotion the draft's parent is `null` while the bundle selects revision 1, so
    the candidate digest it would produce is one `promote` never computes. `rebase-draft` is the
    way forward, and it changes the digest — which is what makes the old stamp stale.
    """
    assert approve(env, synthetic_bundle, FakeTerminal(), monkeypatch).exit_code == 0
    assert (
        run(
            env,
            synthetic_bundle,
            ["promote", "--draft", synthetic_bundle.draft_name, "--summary", "first"],
        ).exit_code
        == 0
    )
    # The draft directory is consumed by promotion, so re-create a parentless one to be stale.
    import shutil

    from boardwatch.profile_bundle.paths import draft_root

    stale = draft_root(synthetic_bundle.root, "stale")
    shutil.copytree(
        synthetic_bundle.root / "revisions" / next(
            entry.name for entry in (synthetic_bundle.root / "revisions").iterdir()
        ),
        stale,
    )
    (stale / "COMPLETE").unlink(missing_ok=True)

    terminal = FakeTerminal()
    monkeypatch.setattr(profile_bundle_cmd, "approval_terminal", lambda: terminal)
    result = run(env, synthetic_bundle, ["approve", "--draft", "stale", "--json"])
    assert result.exit_code == 1
    assert terminal.asked == []
    codes = {finding["code"] for finding in json.loads(result.output)["diagnostics"]}
    assert codes in ({"stale_draft_parent"}, {"draft_manifest_invalid"}), codes


# --------------------------------------------------------------------------------------
# One writer
# --------------------------------------------------------------------------------------


def test_production_has_exactly_one_approval_stamp_writer() -> None:
    """`approval_stamp_bytes` is the stored form; whoever calls it is a way to approve.

    Scanned over `src/` rather than asserted about the command, because the property being tested
    is that no *second* place exists — and only a search over the tree can see that.
    """
    source_root = Path(profile_bundle_cmd.__file__).resolve().parents[2]
    callers = sorted(
        path.relative_to(source_root).as_posix()
        for path in source_root.rglob("*.py")
        if "approval_stamp_bytes(" in path.read_text(encoding="utf-8")
    )
    assert callers == [
        # The module that defines the form …
        "boardwatch/profile_bundle/approvals.py",
        # … and the one function that files it. The command layer asks the owner and calls this;
        # it never touches the stamp itself, because the candidate digest is computed with the
        # bundle's private serializer, which `test_profile_bundle_hash_isolation` keeps inside the
        # package. `promotion` reads stamps back but never emits one, which is why it is not here.
        "boardwatch/profile_bundle/authoring.py",
    ], callers


def test_the_clock_the_stamp_records_is_the_command_layer_s(
    env: Path, synthetic_bundle: SyntheticBundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The package reads no clock; `approve` supplies one, and it is UTC-aware."""
    before = datetime.now(UTC)
    assert approve(env, synthetic_bundle, FakeTerminal(), monkeypatch).exit_code == 0
    path = approval_path(synthetic_bundle.root, expected_candidate(synthetic_bundle))
    stamp = ApprovalStamp.model_validate(
        load_yaml_bytes(path.read_bytes(), logical_path=PurePosixPath(f"approvals/{path.name}"))
    )
    assert before <= stamp.approved_at <= datetime.now(UTC)


def test_a_draft_that_will_not_parse_is_reported_as_itself(
    env: Path, synthetic_bundle: SyntheticBundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A document the loader refuses is a finding about the draft, not an internal failure.

    Without the typed arm this reaches the command boundary's last-resort handler and comes back as
    `internal_error` — "please file a bug" for a file the owner mistyped.
    """
    synthetic_bundle.write("skills/inventory.yaml", "skills: [ this is not\n")
    terminal = FakeTerminal()
    result = approve(env, synthetic_bundle, terminal, monkeypatch, extra=["--json"])
    assert result.exit_code == 1
    codes = {finding["code"] for finding in json.loads(result.output)["diagnostics"]}
    assert "internal_error" not in codes, codes
    assert codes <= {"invalid_yaml", "restricted_yaml_violation", "model_validation_error"}, codes
    assert terminal.asked == []
    assert not approvals_dir(synthetic_bundle.root).exists()


def test_a_draft_citing_a_capture_the_store_cannot_produce_is_refused(
    env: Path, synthetic_bundle: SyntheticBundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The candidate digest is computed from the capture bytes, so a missing one has no digest.

    Without this check the missing blob escapes as a typed exception the command boundary can only
    report as `internal_error` — a bug report for a bundle whose evidence simply needs recapturing.
    §6's recovery path is `checkout`, recapture, promote; approving on the way through would bind
    the owner's decision to bytes nobody can read back.
    """
    synthetic_bundle.blob.unlink()
    terminal = FakeTerminal()
    result = approve(env, synthetic_bundle, terminal, monkeypatch, extra=["--json"])
    assert result.exit_code == 1
    codes = {finding["code"] for finding in json.loads(result.output)["diagnostics"]}
    assert codes == {"corrupt_blob_quarantine"}, codes
    assert terminal.asked == []
    assert not approvals_dir(synthetic_bundle.root).exists()


@pytest.mark.parametrize("state", ["detached", "closed", "tty"])
def test_the_real_adapter_answers_no_for_anything_that_is_not_plainly_a_terminal(
    monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    """The production adapter, exercised directly across the states a daemon reaches.

    Boardwatch runs unattended under a LaunchAgent, where `sys.stdin` is `None` or closed. Either
    would raise out of a bare `sys.stdin.isatty()` and reach the operator as a traceback; §13 fixes
    the fail-safe direction, so both answer "not a terminal".

    The `tty` case is the control: without it a adapter that always answered `False` would pass.
    """

    class Closed:
        def isatty(self) -> bool:
            raise ValueError("I/O operation on closed file")

    class Terminal:
        def isatty(self) -> bool:
            return True

    replacement = {"detached": None, "closed": Closed(), "tty": Terminal()}[state]
    monkeypatch.setattr(profile_bundle_cmd.sys, "stdin", replacement)
    monkeypatch.setattr(profile_bundle_cmd.sys, "stdout", Terminal())
    assert profile_bundle_cmd.approval_terminal().is_controlling() is (state == "tty")


def test_the_operator_interaction_never_lands_on_stdout(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stdout carries the command's answer, and `approve --json` is a document a script parses.

    With the prompt on stdout the two arms were mutually exclusive: on a terminal the JSON was
    preceded by the whole prompt on the same stream, and redirecting stdout so it could be captured
    made `is_controlling` refuse the run. There was no third option, so the one command §21 gives
    `approval_declined` and `approval_requires_controlling_tty` had no usable machine rendering.

    Exercised against the production adapter — it is the only implementation, and the fake the rest
    of this file uses appends to a list rather than writing to a stream at all.
    """
    terminal = profile_bundle_cmd.approval_terminal()
    monkeypatch.setattr("sys.stdin", io.StringIO(f"{profile_bundle_cmd.CONFIRMATION_WORD}\n"))

    terminal.show("Candidate content digest: sha256:" + "0" * 64)
    answer = terminal.ask(f"Type {profile_bundle_cmd.CONFIRMATION_WORD!r} to approve")

    captured = capsys.readouterr()
    assert answer == profile_bundle_cmd.CONFIRMATION_WORD
    # `typer.prompt` hands the prompt's LAST character to `input()` whatever `err` says — a
    # deliberate readline workaround in the library. One space is all stdout may carry, and
    # `json.loads` skips leading whitespace, so the machine rendering stays parseable.
    assert captured.out.strip() == "", repr(captured.out)
    assert "Candidate content digest" in captured.err
    assert profile_bundle_cmd.CONFIRMATION_WORD in captured.err


def test_approve_json_writes_a_parseable_document_to_stdout(
    env: Path, synthetic_bundle: SyntheticBundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point of the stream split, through the command rather than the adapter.

    Only the controlling-terminal question is replaced; the prompt text, the confirmation read and
    the envelope are all the production path, so the assertion is that those three can coexist on
    one invocation — which is exactly what they could not do while the prompt shared stdout.
    """
    monkeypatch.setattr(
        profile_bundle_cmd._StandardTerminal, "is_controlling", lambda self: True
    )
    result = CliRunner().invoke(
        app,
        [
            "--data-dir", str(env), "profile-bundle", "approve",
            "--draft", synthetic_bundle.draft_name,
            "--bundle", str(synthetic_bundle.root), "--json",
        ],
        input=f"{profile_bundle_cmd.CONFIRMATION_WORD}\n",
    )
    assert result.exit_code == 0, result.output
    assert "Candidate content digest" in result.stderr
    assert "Candidate content digest" not in result.stdout, result.stdout
    # The runner simulates terminal echo by writing the answer it fed in back to stdout, which a
    # real tty driver would do outside the process. Everything after it is the command's answer.
    document = result.stdout[result.stdout.index("{") :]
    body = json.loads(document)
    assert body["command"] == "approve"
    assert body["result"]["candidate_digest"] == expected_candidate(synthetic_bundle)
