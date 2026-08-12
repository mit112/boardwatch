"""Design §21's exit contract, characterised through the commands that produce it.

The four tiers are the family's whole promise to an automated caller:

| tier | meaning |
|---|---|
| `0` | the check completed and found nothing at the requested tier |
| `1` | it completed and found errors, blockers, or a typed state refusal |
| `2` | a command-line usage error, produced **before** the command ran |
| `3` | it could not complete: I/O, lock contention, internal failure, unsupported schema |

Two things this file deliberately does **not** do. It does not restate the code-to-tier table —
`errors.STATE_REFUSAL_CODES` and `errors.COULD_NOT_COMPLETE_CODES` own that, and
`test_profile_bundle_outcomes.py` pins it. And it does not assert an exit code that a library
function chose in isolation: every case here goes through a real command, because the question is
whether the *command layer* carries the library's answer out intact.

Exit 2 gets the extra assertion that nothing happened, because "produced before command execution"
is the part of §21 a usage error could quietly violate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.profile_bundle.errors import IssueCode, diagnostic
from boardwatch.profile_bundle.locking import bundle_lock
from boardwatch.profile_bundle.paths import BUNDLE_DIR_NAME
from boardwatch.profile_bundle.reports import diagnostic_json, diagnostic_line
from tests.profile_bundle.conftest import SyntheticBundle

#: Every command's JSON must carry these, whatever happened. `result` may be empty — a refusal has
#: no result — but the key is always there, so a consumer never has to branch on its absence.
REQUIRED_JSON_KEYS = frozenset(
    {"as_of", "command", "diagnostics", "exit_code", "outcome", "report_schema", "result"}
)


@dataclass(frozen=True)
class Env:
    data_dir: Path
    config_dir: Path

    @property
    def bundle_root(self) -> Path:
        return self.config_dir / BUNDLE_DIR_NAME


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    config_dir = tmp_path / "cfg"
    config_dir.mkdir(parents=True)
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(config_dir))
    return Env(data_dir=tmp_path / "data", config_dir=config_dir)


def run(env: Env, args: list[str]):  # type: ignore[no-untyped-def]
    return CliRunner().invoke(app, ["--data-dir", str(env.data_dir), "profile-bundle", *args])


def payload(result) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return json.loads(result.output)


# --------------------------------------------------------------------------------------
# 0 — completed, nothing found
# --------------------------------------------------------------------------------------


def test_a_command_that_completed_cleanly_exits_zero(env: Env) -> None:
    assert run(env, ["init"]).exit_code == 0
    clean = run(env, ["inventory", "--json"])
    assert clean.exit_code == 0
    assert payload(clean)["outcome"] == "clean"


# --------------------------------------------------------------------------------------
# 1 — findings, and typed state refusals
# --------------------------------------------------------------------------------------


def test_findings_exit_one(env: Env) -> None:
    assert run(env, ["init"]).exit_code == 0
    found = run(env, ["validate", "--draft", "baseline", "--json"])
    assert found.exit_code == 1
    body = payload(found)
    assert body["outcome"] == "findings"
    assert body["exit_code"] == 1


@pytest.mark.parametrize(
    ("args", "code"),
    [
        (["checkout", "--draft", "second"], "no_current_revision"),
        (["inventory"], None),
        (["conflicts"], "no_current_revision"),
        (["migrate"], "no_current_revision"),
        (["inspect", "fact.nothing.001"], "no_current_revision"),
    ],
)
def test_a_bundle_with_no_revision_refuses_by_its_own_typed_code(
    env: Env, args: list[str], code: str | None
) -> None:
    """A state refusal is a *finding*, not a could-not-complete: the operator has an action.

    `inventory` is in the list as the control — it is the one command that has a real answer for a
    bundle with no revision, so a run that reported `no_current_revision` for everything would not
    be distinguishable from one that reported it for nothing.
    """
    assert run(env, ["init"]).exit_code == 0
    result = run(env, [*args, "--json"])
    if code is None:
        assert result.exit_code == 0
        return
    assert result.exit_code == 1
    assert {finding["code"] for finding in payload(result)["diagnostics"]} == {code}  # type: ignore[index,union-attr]


def test_promoting_without_an_approval_stamp_is_a_state_refusal(
    env: Env, synthetic_bundle: SyntheticBundle
) -> None:
    result = run(
        env,
        [
            "promote",
            "--bundle",
            str(synthetic_bundle.root),
            "--draft",
            synthetic_bundle.draft_name,
            "--summary",
            "nothing was approved",
            "--json",
        ],
    )
    assert result.exit_code == 1
    assert {finding["code"] for finding in payload(result)["diagnostics"]} == {  # type: ignore[index,union-attr]
        "missing_approval_stamp"
    }


# --------------------------------------------------------------------------------------
# 2 — usage, before the command ran
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "args",
    [
        ["init", "--draft", "Not A Draft Name"],
        ["init", "--draft", "trailing-"],
        ["init", "--draft", "a" * 97],
        ["init", "--no-such-option"],
        ["validate", "--as-of", "2026-08-11"],
        ["validate", "--completeness", "--as-of", "the eleventh"],
        ["validate", "--deep-history"],
        ["promote", "--draft", "baseline"],
    ],
)
def test_a_usage_error_exits_two_and_the_command_never_ran(env: Env, args: list[str]) -> None:
    """The second half is the part §21 actually constrains.

    A pristine config directory has no bundle in it, so "the command never ran" is checkable by
    looking for the directory `init` would have created — including for the `init` cases, which are
    the ones where an argument accepted too late would have left a bundle behind.
    """
    result = run(env, args)
    assert result.exit_code == 2, result.output
    assert not env.bundle_root.exists(), result.output


def test_a_draft_name_inventory_reports_is_accepted_by_the_commands_that_address_it(
    env: Env,
) -> None:
    """The wide grammar, from the other side: a derived backup name must not be a usage error.

    96 characters is the operator-facing cap; the backup `rebase-draft` derives from a name that
    long is 83 characters longer, and it is the only copy of that draft. A command that addresses
    an existing draft has to take it, or the drain has no way back in.
    """
    long_name = "d" * 96
    derived = f"{long_name}.pre-rebase-sha256-{'0' * 64}"
    assert run(env, ["init", "--draft", long_name]).exit_code == 0

    # Requesting a NEW draft with the derived name is still a usage error: the shorter cap governs
    # what can be created.
    assert run(env, ["checkout", "--draft", derived]).exit_code == 2

    # Addressing one is not. The refusal that comes back is about the draft, not about its name.
    for args in (
        ["validate", "--draft", derived],
        ["rebase-draft", "--draft", derived],
        ["promote", "--draft", derived, "--summary", "x"],
    ):
        result = run(env, [*args, "--json"])
        assert result.exit_code != 2, f"{args}: {result.output}"


# --------------------------------------------------------------------------------------
# 3 — could not complete
# --------------------------------------------------------------------------------------


def test_lock_contention_could_not_complete(
    env: Env, synthetic_bundle: SyntheticBundle
) -> None:
    """§21: exit 3, no wait, no mutation. The lock is non-blocking by design."""
    with bundle_lock(synthetic_bundle.root):
        result = run(
            env,
            [
                "promote",
                "--bundle",
                str(synthetic_bundle.root),
                "--draft",
                synthetic_bundle.draft_name,
                "--summary",
                "contended",
                "--json",
            ],
        )
    assert result.exit_code == 3
    body = payload(result)
    assert body["outcome"] == "could_not_complete"
    assert {finding["code"] for finding in body["diagnostics"]} == {"bundle_lock_held"}  # type: ignore[index,union-attr]


def test_a_bundle_root_that_is_a_file_could_not_complete(env: Env, tmp_path: Path) -> None:
    not_a_bundle = tmp_path / "file-not-a-directory"
    not_a_bundle.write_text("", encoding="utf-8")
    result = run(env, ["init", "--bundle", str(not_a_bundle), "--json"])
    assert result.exit_code == 3
    assert payload(result)["outcome"] == "could_not_complete"


# --------------------------------------------------------------------------------------
# The machine shape, across the matrix
# --------------------------------------------------------------------------------------


def test_every_json_answer_carries_the_same_envelope(
    env: Env, synthetic_bundle: SyntheticBundle
) -> None:
    """One shape for clean runs, findings and could-not-completes alike.

    A consumer that had to know which of three shapes a command produced would branch on the very
    thing it is trying to read.
    """
    bundle = ["--bundle", str(synthetic_bundle.root)]
    draft = ["--draft", synthetic_bundle.draft_name]
    invocations = [
        ["inventory", *bundle],
        ["conflicts", *bundle],
        ["migrate", *bundle],
        ["validate", *bundle, *draft],
        ["validate", *bundle, *draft, "--completeness"],
        ["inspect", "fact.example.name.001", *bundle],
        ["checkout", *bundle, "--draft", "second"],
        ["rebase-draft", *bundle, *draft],
        ["approve", *bundle, *draft],
        ["promote", *bundle, *draft, "--summary", "s"],
    ]
    for args in invocations:
        result = run(env, [*args, "--json"])
        body = payload(result)
        assert set(body) == REQUIRED_JSON_KEYS, f"{args}: {sorted(body)}"
        assert body["exit_code"] == result.exit_code, args
        assert body["command"] == args[0], args
        assert isinstance(body["diagnostics"], list), args
        assert isinstance(body["result"], dict), args


def test_only_a_dated_run_reports_a_date(env: Env, synthetic_bundle: SyntheticBundle) -> None:
    """`as_of` states when the dated checks ran, so a run with none reports `null`.

    Reporting today's date for an undated run would make a check nobody performed indistinguishable
    from one that found nothing.
    """
    bundle = ["--bundle", str(synthetic_bundle.root), "--draft", synthetic_bundle.draft_name]
    undated = payload(run(env, ["validate", *bundle, "--json"]))
    dated = payload(
        run(env, ["validate", *bundle, "--completeness", "--as-of", "2026-08-11", "--json"])
    )
    assert undated["as_of"] is None
    assert dated["as_of"] == "2026-08-11"


def test_no_diagnostic_names_an_absolute_path(
    env: Env, synthetic_bundle: SyntheticBundle, tmp_path: Path
) -> None:
    """Every path in a diagnostic is logical, or the name of the option that carried the input.

    The check is against the tmp root the bundle actually lives under rather than `$HOME`, because
    that is the absolute prefix these runs could leak — and it is the same class of value.
    """
    bundle = ["--bundle", str(synthetic_bundle.root)]
    invocations = [
        ["init", *bundle],
        ["checkout", *bundle],
        ["validate", *bundle, "--draft", synthetic_bundle.draft_name],
        ["promote", *bundle, "--draft", synthetic_bundle.draft_name, "--summary", "s"],
        ["approve", *bundle, "--draft", synthetic_bundle.draft_name],
        ["inspect", "fact.example.name.001", *bundle],
        ["inventory", *bundle],
        ["migrate", *bundle],
        ["init", "--bundle", str(tmp_path / "missing" / "deeper"), "--json"],
    ]
    for args in invocations:
        body = payload(run(env, [*args, "--json"]))
        rendered = json.dumps(body["diagnostics"])
        assert str(tmp_path) not in rendered, f"{args}: {rendered}"


def test_a_diagnostic_s_details_survive_the_command_layer(
    env: Env, synthetic_bundle: SyntheticBundle
) -> None:
    """`details` is where machine-readable context lives, including `record_ids` (D-129).

    A command layer that rendered only tier, code, path and message would drop exactly the field a
    script needs, and the human rendering would look identical either way.
    """
    result = run(
        env,
        [
            "promote",
            "--bundle",
            str(synthetic_bundle.root),
            "--draft",
            synthetic_bundle.draft_name,
            "--summary",
            "unapproved",
            "--json",
        ],
    )
    (finding,) = payload(result)["diagnostics"]  # type: ignore[misc]
    assert finding["details"]["candidate_content_digest"].startswith("sha256:")  # type: ignore[index]


def test_an_empty_record_ids_list_is_never_glossed_as_no_records(
    env: Env, synthetic_bundle: SyntheticBundle
) -> None:
    """D-129: empty `record_ids` means the conflicting unit has no addressable records.

    `path`, with `details.field` where there is one, is then the whole locator. Rendering it as
    "no records were affected" would be reassurance about precisely the case where a whole document
    is in conflict, so both renderings must carry the locator and neither may add a gloss.
    """
    finding = diagnostic(
        IssueCode.DRAFT_REBASE_CONFLICT,
        "policy/predicates.yaml changed on both sides; the conflict is the document itself",
        path="policy/predicates.yaml",
        record_ids=[],
        field="catalog_version",
    )
    machine = diagnostic_json(finding)
    assert machine["details"] == {"record_ids": [], "field": "catalog_version"}

    human = diagnostic_line(finding)
    assert "policy/predicates.yaml" in human
    assert "no record" not in human.lower()
    assert "not affected" not in human.lower()
