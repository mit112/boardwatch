"""`boardwatch profile-bundle project` — Stage 1 serialization for review, JD-blind, no database.

Every test drives the real Typer app (`boardwatch.cli.app.app`) through `CliRunner`, mirroring
`tests/profile_bundle/test_profile_bundle_cli_exit_codes.py`'s own `Env`/`run` shape. Two fixtures
cover the two owner-gate states: `approved_env` (a promoted bundle, a matching stamp) and
`unapproved_env` (the same bundle, no stamp at all).

There used to be a `--check` flag here for the case an unedited, still-approved declaration cannot
otherwise reveal: the bundle moving out from under an approval that never recorded which revision
it was made against. D-167 made that comparison unconditional inside `project_pool` itself and
deleted the flag: an opt-in check on a consent control is the wrong shape, and once the comparison
fires on every call, a flag that only ever repeated it is a check that cannot fire differently —
this repo's own rule for deleting one. `promote_next_revision` (`tests.profile_bundle.conftest`) is
what produces a second, genuinely different bundle digest at the same `bundle_root` without
touching `projection.yaml` at all — the scenario this file's bundle-drift tests exercise.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Any

import pytest
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.profile_bundle.errors import IssueCode
from boardwatch.profile_bundle.paths import BUNDLE_DIR_NAME
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from boardwatch.profile_bundle.yaml_writer import document_bytes
from boardwatch.projection.declaration import load_declaration, projection_digest
from boardwatch.projection.stamp import APPROVALS_DIR, stamp_path, write_stamp
from tests.profile_bundle.conftest import (
    PromotedRevisionTree,
    promote_example_tree,
    promote_next_revision,
)
from tests.profile_bundle.test_profile_bundle_cli_exit_codes import REQUIRED_JSON_KEYS

_SHELL_BODY = (
    "header:\n"
    "  - Example Candidate\n"
    "  - candidate@example.com\n"
    "education:\n"
    "  - Example University\n"
)


def _add_second_skill(data: Any) -> None:
    """Clone the example's one skill under a new id.

    An ADDITION, not an edit — mirrors `tests/profile_bundle/test_profile_bundle_rebase.py`'s own
    `_add_second_skill` — so it changes the bundle's content digest without invalidating any
    reference `projection.example.yaml` makes (nothing in the declaration names the new id).
    """
    clone = copy.deepcopy(data["skills"][0])
    clone["skill_id"] = "skill.projection-cli-test-added"
    clone["canonical_name"] = "Projection CLI Test Skill"
    clone["aliases"] = ["projection-cli-test-skill"]
    data["skills"].append(clone)


@dataclass(frozen=True)
class Env:
    data_dir: Path
    config_dir: Path
    declaration: Path
    tree: PromotedRevisionTree

    @property
    def bundle_root(self) -> Path:
        return self.config_dir / BUNDLE_DIR_NAME

    @property
    def database(self) -> Path:
        return self.data_dir / "boardwatch.db"


def _make_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, approve: bool) -> Env:
    config_dir = tmp_path / "cfg"
    config_dir.mkdir(parents=True)
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(config_dir))

    tree = promote_example_tree(config_dir / BUNDLE_DIR_NAME)
    (config_dir / "master_resume.yaml").write_text(_SHELL_BODY, encoding="utf-8")

    traversable = resources.files("boardwatch.projection.examples").joinpath(
        "projection.example.yaml"
    )
    with resources.as_file(traversable) as packaged:
        declaration_text = packaged.read_text(encoding="utf-8")
    declaration_path = config_dir / "projection.yaml"
    declaration_path.write_text(declaration_text, encoding="utf-8")

    if approve:
        digest = projection_digest(load_declaration(declaration_path))
        write_stamp(
            config_dir,
            digest=digest,
            bundle_digest=tree.bundle_digest,
            approved_at=datetime(2026, 8, 13, 12, tzinfo=UTC),
        )

    return Env(
        data_dir=tmp_path / "data",
        config_dir=config_dir,
        declaration=declaration_path,
        tree=tree,
    )


@pytest.fixture
def approved_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    """A promoted bundle and a `projection.yaml` approved against its exact current digest."""
    return _make_env(tmp_path, monkeypatch, approve=True)


@pytest.fixture
def unapproved_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    """The identical bundle and declaration, with no approval stamp on file at all."""
    return _make_env(tmp_path, monkeypatch, approve=False)


def run(env: Env, args: list[str]):  # type: ignore[no-untyped-def]
    return CliRunner().invoke(
        app, ["--data-dir", str(env.data_dir), "profile-bundle", "project", *args]
    )


def payload(result) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return json.loads(result.output)


# --------------------------------------------------------------------------------------
# The brief's required cases
# --------------------------------------------------------------------------------------


def test_json_envelope_carries_all_seven_keys(approved_env: Env) -> None:
    result = run(approved_env, ["--json"])
    assert result.exit_code == 0, result.output
    body = payload(result)
    assert set(body.keys()) == REQUIRED_JSON_KEYS


def test_exits_nonzero_after_the_declaration_is_edited(approved_env: Env) -> None:
    """The declaration's own digest changed, so the stamp bound to the OLD digest no longer
    matches — `project_pool`'s owner gate (`stamp_exists`) fires this, distinct from the
    bundle-drift comparison the sibling tests below exercise."""
    text = approved_env.declaration.read_text(encoding="utf-8")
    edited = text.replace("open_range_label: Present", "open_range_label: Ongoing")
    assert edited != text, "the fixture's own anchor text was not found"
    approved_env.declaration.write_text(edited, encoding="utf-8")

    result = run(approved_env, ["--json"])
    assert result.exit_code != 0
    body = payload(result)
    assert body["outcome"] == "findings"
    codes = [d["code"] for d in body["diagnostics"]]
    assert IssueCode.PROJECTION_REFUSED.value in codes
    issues = [d["details"].get("projection_issue") for d in body["diagnostics"]]
    assert "missing_projection_approval" in issues


def test_no_boardwatch_db_is_created_anywhere_under_the_data_dir(approved_env: Env) -> None:
    for args in (["--json"], []):
        run(approved_env, args)
        assert not approved_env.database.exists(), f"{args} created {approved_env.database.name}"
    assert not approved_env.data_dir.exists(), "project should not create the data directory"


# --------------------------------------------------------------------------------------
# D-167: the bundle-digest comparison is unconditional inside `project_pool` — bundle drift an
# unedited declaration hides is refused on every path, not behind an opt-in flag.
# --------------------------------------------------------------------------------------


def test_exits_zero_when_neither_bundle_nor_declaration_changed(approved_env: Env) -> None:
    result = run(approved_env, ["--json"])
    assert result.exit_code == 0, result.output
    assert payload(result)["outcome"] == "clean"


def test_exits_nonzero_when_only_the_bundle_changed(approved_env: Env) -> None:
    """The declaration is byte-for-byte what was approved; only the bundle moved.
    `project_pool` reads the stamp back and compares its `bundle_digest` against the bundle
    actually being read, unconditionally (D-167) — this used to be `--check`'s own,
    otherwise-unreachable job; now plain `project` refuses here on its own."""
    promote_next_revision(approved_env.tree, mutate=_add_second_skill)

    result = run(approved_env, ["--json"])
    assert result.exit_code != 0
    body = payload(result)
    assert body["outcome"] == "findings"
    codes = [d["code"] for d in body["diagnostics"]]
    assert IssueCode.STALE_APPROVAL_STAMP.value in codes
    issues = [d["details"].get("projection_issue") for d in body["diagnostics"]]
    assert "stale_projection_approval" in issues


# --------------------------------------------------------------------------------------
# The owner gate itself, unrelated to `--check`
# --------------------------------------------------------------------------------------


def test_project_refuses_without_any_approval(unapproved_env: Env) -> None:
    result = run(unapproved_env, ["--json"])
    assert result.exit_code != 0
    body = payload(result)
    assert body["outcome"] == "findings"
    codes = [d["code"] for d in body["diagnostics"]]
    assert IssueCode.PROJECTION_REFUSED.value in codes
    issues = [d["details"].get("projection_issue") for d in body["diagnostics"]]
    assert "missing_projection_approval" in issues


# --------------------------------------------------------------------------------------
# What a clean run actually serializes
# --------------------------------------------------------------------------------------


def test_json_result_carries_the_pool_identity_and_the_resolved_document(
    approved_env: Env,
) -> None:
    result = run(approved_env, ["--json"])
    assert result.exit_code == 0, result.output
    body = payload(result)
    outcome_result = body["result"]
    assert isinstance(outcome_result, dict)
    assert outcome_result["bundle_digest"] == approved_env.tree.bundle_digest
    assert outcome_result["pinned_entry_ids"] == ["entry.employment.example-labs"]
    assert outcome_result["candidate_entry_ids"] == ["entry.project.packet-pantry"]
    document = outcome_result["resume"]
    assert isinstance(document, str)
    # The resolved value, never the raw template: the whole point of the owner gate this command
    # sits behind.
    assert "{@display_name}" not in document
    assert "Packet Pantry" in document


def test_plain_text_output_never_leaks_an_absolute_bundle_path(unapproved_env: Env) -> None:
    """Family rule #2: no absolute path in any diagnostic. `BUNDLE_UNREADABLE` is the one
    reachable `ProjectionIssue` whose own message embeds `str(bundle_root)`; this asserts the CLI
    boundary's sanitization actually strips it rather than merely existing in the source.

    Reached by removing the CURRENT pointer this fixture just wrote, not by editing the
    declaration — `unapproved_env` alone would raise `MISSING_PROJECTION_APPROVAL` first, which is
    a different, already-covered code path.
    """
    digest = projection_digest(load_declaration(unapproved_env.declaration))
    write_stamp(
        unapproved_env.config_dir,
        digest=digest,
        bundle_digest=unapproved_env.tree.bundle_digest,
        approved_at=datetime(2026, 8, 13, 12, tzinfo=UTC),
    )
    (unapproved_env.bundle_root / "CURRENT").unlink()

    result = run(unapproved_env, ["--json"])
    assert result.exit_code != 0
    assert str(unapproved_env.bundle_root) not in result.output
    assert str(unapproved_env.config_dir) not in result.output
    body = payload(result)
    codes = [d["code"] for d in body["diagnostics"]]
    assert IssueCode.PROJECTION_REFUSED.value in codes
    issues = [d["details"].get("projection_issue") for d in body["diagnostics"]]
    assert "bundle_unreadable" in issues


# --------------------------------------------------------------------------------------
# Fix round 1, Finding 1 (CRITICAL): a legacy or malformed stamp on disk must not crash
# `read_stamp` — it must produce a typed diagnostic with a valid JSON envelope.
# --------------------------------------------------------------------------------------


def test_a_legacy_stamp_missing_bundle_digest_is_a_typed_refusal_not_a_crash(
    approved_env: Env,
) -> None:
    """The reviewer's own repro: a stamp written before `bundle_digest` was required — exactly
    what anyone who ran `approve-projection` before this commit has on disk — must not surface as
    a bare `pydantic.ValidationError`. `project_pool` reads the stamp back (`read_stamp`) on
    every call now (D-167), so plain `project` reaches this with no flag needed."""
    digest = projection_digest(load_declaration(approved_env.declaration))
    path = stamp_path(approved_env.config_dir, digest)
    logical = PurePosixPath(f"{APPROVALS_DIR}/{path.name}")
    raw = load_yaml_bytes(path.read_bytes(), logical_path=logical)
    assert isinstance(raw, dict)
    legacy = dict(raw)
    del legacy["bundle_digest"]
    path.write_bytes(document_bytes(legacy, logical_path=logical))

    result = run(approved_env, ["--json"])

    # `exit_code != 0` alone cannot discriminate a typed refusal from an uncaught crash — both
    # report the same code through `CliRunner`. `SystemExit` is what a clean `typer.Exit` raises;
    # an uncaught `ValidationError` would leave `result.exception` as that exception instead, and
    # `result.output` would be a traceback (or empty), not JSON.
    assert isinstance(result.exception, SystemExit), (
        f"expected a clean refusal, got an uncaught {result.exception!r}"
    )
    assert result.exit_code != 0
    body = payload(result)  # must parse as JSON: a crash leaves nothing valid on stdout
    assert body["outcome"] == "could_not_complete"
    codes = [d["code"] for d in body["diagnostics"]]
    assert IssueCode.INTERNAL_ERROR.value in codes


# --------------------------------------------------------------------------------------
# Fix round 1, Finding 2 (Important): mere absence of shell_source, not just a malformed file,
# reaches SHELL_SOURCE_UNREADABLE and must not leak an absolute path either.
# --------------------------------------------------------------------------------------


def test_plain_text_output_never_leaks_an_absolute_path_for_a_missing_shell_source(
    approved_env: Env,
) -> None:
    """Family rule #2 again, for the second leaking call site: `shell.py`'s message interpolates
    a caught `OSError`, whose `str()` embeds the shell file's absolute path. Mere absence — no
    malformed-file fixture needed — reaches it: an operator who has not yet created their shell
    file hits this on first run."""
    (approved_env.config_dir / "master_resume.yaml").unlink()

    result = run(approved_env, ["--json"])

    assert result.exit_code != 0
    assert str(approved_env.config_dir) not in result.output
    body = payload(result)
    codes = [d["code"] for d in body["diagnostics"]]
    assert IssueCode.PROJECTION_REFUSED.value in codes
    issues = [d["details"].get("projection_issue") for d in body["diagnostics"]]
    assert "shell_source_unreadable" in issues
