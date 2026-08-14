"""`boardwatch profile-bundle project` — Stage 1 serialization for review, JD-blind, no database.

Every test drives the real Typer app (`boardwatch.cli.app.app`) through `CliRunner`, mirroring
`tests/profile_bundle/test_profile_bundle_cli_exit_codes.py`'s own `Env`/`run` shape. Two fixtures
cover the two owner-gate states: `approved_env` (a promoted bundle, a matching stamp) and
`unapproved_env` (the same bundle, no stamp at all).

`--check`'s whole point (R30) is the case an unedited, still-approved declaration cannot otherwise
reveal: the bundle moving out from under an approval that never recorded which revision it was
made against. `promote_next_revision` (`tests.profile_bundle.conftest`) is what produces a second,
genuinely different bundle digest at the same `bundle_root` without touching `projection.yaml` at
all — the one scenario `project_pool`'s own owner-gate check (keyed on `projection_digest` alone)
cannot see.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.profile_bundle.errors import IssueCode
from boardwatch.profile_bundle.paths import BUNDLE_DIR_NAME
from boardwatch.projection.declaration import load_declaration, projection_digest
from boardwatch.projection.stamp import write_stamp
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


def test_check_exits_nonzero_after_the_declaration_is_edited(approved_env: Env) -> None:
    """The declaration's own digest changed, so the stamp bound to the OLD digest no longer
    matches — `project_pool`'s owner gate fires this, not `--check`'s own bundle comparison (see
    the sibling test below, which proves the two are distinguishable)."""
    text = approved_env.declaration.read_text(encoding="utf-8")
    edited = text.replace("open_range_label: Present", "open_range_label: Ongoing")
    assert edited != text, "the fixture's own anchor text was not found"
    approved_env.declaration.write_text(edited, encoding="utf-8")

    result = run(approved_env, ["--check", "--json"])
    assert result.exit_code != 0
    body = payload(result)
    assert body["outcome"] == "findings"
    codes = [d["code"] for d in body["diagnostics"]]
    assert IssueCode.PROJECTION_REFUSED.value in codes
    issues = [d["details"].get("projection_issue") for d in body["diagnostics"]]
    assert "missing_projection_approval" in issues


def test_no_boardwatch_db_is_created_anywhere_under_the_data_dir(approved_env: Env) -> None:
    for args in (["--json"], ["--check"], ["--check", "--json"], []):
        run(approved_env, args)
        assert not approved_env.database.exists(), f"{args} created {approved_env.database.name}"
    assert not approved_env.data_dir.exists(), "project should not create the data directory"


# --------------------------------------------------------------------------------------
# R30: --check's own, otherwise-unreachable job — bundle drift an unedited declaration hides
# --------------------------------------------------------------------------------------


def test_check_exits_zero_when_neither_bundle_nor_declaration_changed(approved_env: Env) -> None:
    result = run(approved_env, ["--check", "--json"])
    assert result.exit_code == 0, result.output
    assert payload(result)["outcome"] == "clean"


def test_check_exits_nonzero_when_only_the_bundle_changed(approved_env: Env) -> None:
    """The declaration is byte-for-byte what was approved; only the bundle moved. Plain
    `project_pool` cannot see this at all (its owner gate keys on `projection_digest` alone) — this
    is the one case `--check`'s own stamp-vs-pool `bundle_digest` comparison exists for."""
    promote_next_revision(approved_env.tree, mutate=_add_second_skill)

    result = run(approved_env, ["--check", "--json"])
    assert result.exit_code != 0
    body = payload(result)
    assert body["outcome"] == "findings"
    codes = [d["code"] for d in body["diagnostics"]]
    assert IssueCode.STALE_APPROVAL_STAMP.value in codes
    issues = [d["details"].get("projection_issue") for d in body["diagnostics"]]
    assert "stale_projection_approval" in issues


def test_plain_project_exits_zero_when_only_the_bundle_changed(approved_env: Env) -> None:
    """The other half of the same scenario, WITHOUT `--check`: proves `--check` is not a no-op
    that merely repeats what plain `project` already does. If this test could not be written —
    if plain `project` also refused here — `--check` would never change any outcome, exactly the
    "a check that cannot fire is deleted" trap R30 exists to avoid."""
    promote_next_revision(approved_env.tree, mutate=_add_second_skill)

    result = run(approved_env, ["--json"])
    assert result.exit_code == 0, result.output
    assert payload(result)["outcome"] == "clean"


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
