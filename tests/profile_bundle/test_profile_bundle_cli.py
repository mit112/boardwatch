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
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import pytest
import typer.main
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.profile_bundle.errors import COULD_NOT_COMPLETE_CODES, IssueCode
from boardwatch.profile_bundle.models.manifests import DraftManifest
from boardwatch.profile_bundle.paths import BUNDLE_DIR_NAME, drafts_dir
from boardwatch.profile_bundle.paths import draft_root as draft_root_for
from tests.profile_bundle.conftest import (
    PromotedRevisionTree,
    SyntheticBundle,
    parse_documents,
    quoted_yaml,
)

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


# --------------------------------------------------------------------------------------
# Authoring, through the command layer
# --------------------------------------------------------------------------------------


def _bundle_args(bundle: SyntheticBundle) -> list[str]:
    return ["--bundle", str(bundle.root), "--draft", bundle.draft_name]


def _write(path: Path, payload: object, logical: str) -> Path:
    path.write_bytes(quoted_yaml(payload, logical_path=PurePosixPath(logical)))
    return path


def _inline_evidence(text: str) -> dict[str, object]:
    return {
        "evidence_id": "evidence.example.cli.001",
        "title": "A note added through the command layer",
        "capture": {"kind": "inline", "text": text, "media_type": "text/plain"},
        "captured_at": "2026-08-11T09:00:00Z",
        "reviewed_at": "2026-08-11",
        "sufficiency_review": {"state": "owner_approved"},
        "redactions": [],
        "supports_record_ids": [SUPPORTED_FACT],
        "contradicts_record_ids": [],
        "contextualizes_record_ids": [],
        "evidence_class": "owner_attestation",
        "attested_at": "2026-08-11",
    }


#: The fact the captured attestation supports. An `owner_attestation` must support at least one
#: fact (the evidence model says so) and §12 requires that fact to cite the evidence back — an edit
#: `add_evidence` now makes in the same operation (D-143), so this flow ends clean rather than
#: leaving `evidence_link_asymmetry` for the operator. The revalidation must therefore report
#: *nothing at all*, and in particular nothing about digest integrity.
SUPPORTED_FACT = "fact.example.name.001"


def test_add_evidence_records_the_capture_and_revalidates(
    env: Env, synthetic_bundle: SyntheticBundle, tmp_path: Path
) -> None:
    """§19 step 6: an authoring command ends by revalidating the draft it changed.

    The revalidation's findings share the command's exit code, so one answer says both "the change
    landed" and "what the draft still owes". The code set is asserted whole rather than by
    membership: the defect this pins was `add_evidence` writing an evidence set its own manifest no
    longer described, which reported `evidence_set_digest_mismatch` — §21's "evidence mutated after
    promotion" — on every successful capture, so an extra code here is the failure mode. That is
    what the empty set below is for, and asserting it whole is why it caught D-143's change to this
    flow instead of passing through it.

    Since D-143 the set is empty rather than `{evidence_link_asymmetry}`: the back-citation the fact
    owes is written by the same operation, so a capture supporting a fact ends clean at exit 0 and
    the gate it incurs is reported instead.
    """
    text = "The owner attests to the professional name recorded in this bundle."
    record = _write(tmp_path / "e.yaml", _inline_evidence(text), "evidence-record.yaml")
    capture = tmp_path / "c.txt"
    capture.write_text(text, encoding="utf-8")

    result = run(
        env,
        ["add-evidence", *_bundle_args(synthetic_bundle), "--evidence-file", str(record),
         "--capture", str(capture), "--json"],
    )
    body = json.loads(result.output)
    assert {finding["code"] for finding in body["diagnostics"]} == set(), result.output
    # The outcome the codes imply, asserted rather than assumed. Without it the always-exit-1
    # answer of a capture that never restated its evidence-set digest was invisible to the suite.
    assert result.exit_code == 0, result.output
    # The back-citation is the reason the set above is empty, so it is asserted here rather than
    # inferred from the absence of a finding: a fix that stopped REPORTING the asymmetry without
    # writing the citation would pass every line above.
    assert "evidence.example.cli.001" in synthetic_bundle.read("facts/identity.yaml")
    assert {
        (gate["action"], gate["target_record_id"]) for gate in body["result"]["owner_gates"]
    } == {
        ("approve_evidence_sufficiency", "evidence.example.cli.001"),
        ("confirm_fact", SUPPORTED_FACT),
    }, result.output
    assert body["result"]["evidence_id"] == "evidence.example.cli.001"
    assert body["result"]["capture_kind"] == "inline"
    assert body["result"]["blob_digest"] is None
    assert "evidence.example.cli.001" in synthetic_bundle.read("evidence/records.yaml")


def test_add_evidence_refuses_a_secret_without_touching_the_draft(
    env: Env, synthetic_bundle: SyntheticBundle, tmp_path: Path
) -> None:
    secret = "AKIA" + "B" * 16
    text = f"Deployment note that leaked {secret} into the log."
    record = _write(tmp_path / "e.yaml", _inline_evidence(text), "evidence-record.yaml")
    capture = tmp_path / "c.txt"
    capture.write_text(text, encoding="utf-8")
    before = synthetic_bundle.read("evidence/records.yaml")

    result = run(
        env,
        ["add-evidence", *_bundle_args(synthetic_bundle), "--evidence-file", str(record),
         "--capture", str(capture), "--json"],
    )
    assert result.exit_code == 1
    body = json.loads(result.output)
    assert {finding["code"] for finding in body["diagnostics"]} == {"secret_detected"}
    assert body["result"] == {}
    assert synthetic_bundle.read("evidence/records.yaml") == before
    assert secret not in result.output


def _ruling_file(tmp_path: Path) -> Path:
    """One valid owner ruling on a conflict group the comprehensive example declares."""
    return _write(
        tmp_path / "r.yaml",
        {
            "ruling_id": "ruling.packet-pantry.end-date.001",
            "conflict_id": "conflict.packet-pantry.end-date",
            "decision": "select_candidate",
            "selected_fact_id": "fact.packet-pantry.end-date.002",
            "rejected_fact_ids": ["fact.packet-pantry.end-date.001"],
            "rationale": "The later date is when the work actually stopped.",
            "owner_evidence_id": "evidence.packet-pantry.owner-ruling.001",
            "decided_at": "2026-08-11",
        },
        "ruling-record.yaml",
    )


def test_resolve_conflict_settles_the_group_and_names_the_gate(
    env: Env, synthetic_bundle: SyntheticBundle, tmp_path: Path
) -> None:
    """And leaves the manifest alone, because a ruling changes nothing the evidence set covers.

    `canonical.evidence_set_digest` reads `evidence/records.yaml` and the blobs it names; a ruling
    touches neither, so the recompute `add_evidence` owes has no counterpart here. That is where the
    guarantee lands, and the empty diagnostic set below is what says so.
    """
    ruling = _ruling_file(tmp_path)
    manifest_before = synthetic_bundle.manifest_path.read_text(encoding="utf-8")
    result = run(
        env,
        ["resolve-conflict", *_bundle_args(synthetic_bundle), "--ruling-file", str(ruling),
         "--json"],
    )
    body = json.loads(result.output)
    assert body["diagnostics"] == [], result.output
    assert result.exit_code == 0, result.output
    assert body["result"]["conflict_state"] == "resolved"
    assert "authorize_conflict_ruling" in {
        gate["action"] for gate in body["result"]["owner_gates"]
    }
    assert (
        synthetic_bundle.manifest_path.read_text(encoding="utf-8") == manifest_before
    ), "a ruling must not rewrite the manifest"


@pytest.mark.skipif(os.name != "posix", reason="mode bits do not deny directory reads on Windows")
def test_a_revalidation_that_could_not_run_does_not_report_that_nothing_happened(
    env: Env, synthetic_bundle: SyntheticBundle, tmp_path: Path
) -> None:
    """§19 step 6 runs after the write. Its failure is not the command's failure.

    `outcome_with`'s could-not-complete precedence would make the revalidation's failure the whole
    command's category, so the answer was `could_not_complete` at exit 3 — §21's "nothing usable
    happened, retry" — beside a populated `result` and a ruling that had durably landed. A caller
    that retried on 3 would hit `duplicate_record_id` against its own ruling.

    **The distinction has to be typed, which is what this pins.** The first fix put it in the
    diagnostic's prose and left the code as `io_error`, a member of `COULD_NOT_COMPLETE_CODES` — so
    the only thing a consumer can branch on still said the opposite of the envelope, and telling the
    two apart meant reading English. `recheck_unavailable` is not in that set, and `details.cause`
    keeps the kind the old code carried. The assertion below is against the catalog rather than
    against the literal 1, so it cannot agree with a future change that puts the code back.

    The blob store is what is made unreadable: `resolve_conflict` never opens it, so the authoring
    step completes and only the revalidation fails. That is the whole point of the case.
    """
    if os.name != "posix" or os.geteuid() == 0:  # pragma: no cover - not a POSIX mode bit
        pytest.skip("running as root, so an unreadable directory is still readable")
    ruling = _ruling_file(tmp_path)
    blobs = synthetic_bundle.blob.parent
    blobs.chmod(0o000)
    try:
        result = run(
            env,
            ["resolve-conflict", *_bundle_args(synthetic_bundle), "--ruling-file", str(ruling),
             "--json"],
        )
    finally:
        blobs.chmod(0o755)

    body = json.loads(result.output)
    (finding,) = body["diagnostics"]
    assert finding["code"] == "recheck_unavailable", result.output
    assert finding["details"]["cause"] == "io", result.output
    assert body["outcome"] == "findings", result.output
    assert result.exit_code == 1, result.output
    assert body["result"]["ruling_id"] == "ruling.packet-pantry.end-date.001"
    # The envelope's category must follow from the CATALOG, not from this command's own opinion:
    # the code it reports is one the package does not classify as could-not-complete.
    assert IssueCode(finding["code"]) not in COULD_NOT_COMPLETE_CODES
    # The claim the message makes is checked against what is on disk, not taken on trust.
    assert "nothing was written" not in result.output
    assert "ruling.packet-pantry.end-date.001" in synthetic_bundle.read("conflicts/rulings.yaml")


def test_migrate_reports_already_current_on_a_promoted_bundle(
    env: Env, promoted_tree: PromotedRevisionTree
) -> None:
    result = run(env, ["migrate", "--bundle", str(promoted_tree.bundle_root), "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["result"] == {
        "status": "already_current",
        "schema_version": 2,
    }


def test_rebase_draft_drains_a_stale_draft_onto_the_selected_revision(
    env: Env, chained_tree: PromotedRevisionTree
) -> None:
    """`rebase-draft` is the drain design §19 requires for a draft whose parent moved.

    The backup path is deterministic, so the check is that the old draft is still there under the
    derived name — nothing an owner authored is deleted by the command that moves it.
    """
    root = chained_tree.bundle_root
    parent_digest = chained_tree.documents.manifest.parent_bundle_digest
    assert parent_digest is not None
    stale = draft_root_for(root, "stale")
    shutil.copytree(
        root / "revisions" / f"sha256-{parent_digest.removeprefix('sha256:')}", stale
    )
    (stale / "COMPLETE").unlink(missing_ok=True)
    _as_draft(stale, parent_digest, chained_tree.revision - 1)

    result = run(env, ["rebase-draft", "--bundle", str(root), "--draft", "stale", "--json"])
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["result"]["parent_bundle_digest"] == chained_tree.bundle_digest
    backup = draft_root_for(root, f"stale.pre-rebase-sha256-{parent_digest.removeprefix('sha256:')}")
    assert backup.is_dir(), sorted(p.name for p in (root / "drafts").iterdir())


def _as_draft(tree: Path, parent_digest: str, parent_revision: int) -> None:
    """Turn a copied revision tree into a draft of that revision."""
    manifest = parse_documents(tree, final_revision=True).manifest
    values = manifest.model_dump(mode="json")
    for derived in ("revision", "created_at", "created_by"):
        values.pop(derived, None)
    values.update(
        {
            "state": "draft",
            "draft_of_revision": parent_revision,
            "parent_bundle_digest": parent_digest,
            "bundle_digest": "",
            "approved_candidate_digest": "",
            "approval_stamp_id": "",
            "change_id": "",
        }
    )
    (tree / "manifest.yaml").write_bytes(
        quoted_yaml(
            DraftManifest.model_validate(values).model_dump(mode="json"),
            logical_path=PurePosixPath("manifest.yaml"),
        )
    )


def test_an_unreadable_blob_file_is_reported_as_io_not_as_a_defect(
    env: Env, synthetic_bundle: SyntheticBundle, tmp_path: Path
) -> None:
    """`BundleIoError` is a `ProfileBundleError`, so `except` ORDER is all that separates them.

    Caught by the base-class arm, an unreadable blob became `cause: internal` with "This is a defect
    — please report the error type" — telling the owner their filesystem permissions were our bug.
    The two arms disagree about whose problem it is, so the distinction cannot rest on which
    `except` happened to match first.

    A blob *file* rather than the store directory: `chmod 000` on the directory raises `OSError`
    straight out and lands on the `OSError` arm, which was always right. Only the file case is
    wrapped in `BundleIoError`, which is why it was the one reported wrongly.
    """
    if os.name != "posix" or os.geteuid() == 0:  # pragma: no cover - not a POSIX mode bit
        pytest.skip("running as root, so an unreadable file is still readable")
    ruling = _ruling_file(tmp_path)
    synthetic_bundle.blob.chmod(0o000)
    try:
        result = run(
            env,
            ["resolve-conflict", *_bundle_args(synthetic_bundle), "--ruling-file", str(ruling),
             "--json"],
        )
    finally:
        synthetic_bundle.blob.chmod(0o644)

    body = json.loads(result.output)
    (finding,) = body["diagnostics"]
    # The CODE first: it is the one field a consumer branches on, and asserting only `cause` left
    # this arm free to report `io_error` -- a could-not-complete member -- with 63 tests still green.
    assert finding["code"] == "recheck_unavailable", result.output
    assert IssueCode(finding["code"]) not in COULD_NOT_COMPLETE_CODES
    assert finding["details"].get("cause") == "io", result.output
    # The strerror survives, path-free, so the operator learns it is theirs to fix.
    assert "Permission denied" in finding["message"], result.output
    assert "This is a defect" not in result.output
    assert "error_type" not in finding["details"], result.output
    # And no absolute path: BundleIoError's own message carries one, so it must not be interpolated.
    assert str(synthetic_bundle.root) not in result.output
