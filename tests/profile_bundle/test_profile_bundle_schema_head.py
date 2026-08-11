"""T17 §7/§23: what a build does with a bundle whose schema it does not support.

The head constants and `require_supported_schema` itself are pinned by
`test_profile_bundle_schema_export.py` and are deliberately not restated here. What this module
owns is the property that one restatement of the head would silently break: the refusal an operator
actually sees must be the typed `unsupported_schema_version`, and it must come from the schema gate
rather than from a model that happened to reject an unfamiliar number.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from boardwatch.profile_bundle.errors import IssueCode
from boardwatch.profile_bundle.migrations import migrate_bundle
from boardwatch.profile_bundle.models.manifests import RevisionManifest
from boardwatch.profile_bundle.schema import CURRENT_SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from tests.profile_bundle.conftest import (
    PromotedRevisionTree,
    example_source_root,
    quoted_yaml,
)

NEWER_SCHEMA_VERSION = CURRENT_SCHEMA_VERSION + 1


def _rewrite_manifest(revision_dir: Path, mutate: Any) -> dict[str, Any]:
    path = revision_dir / "manifest.yaml"
    data = load_yaml_bytes(path.read_bytes(), logical_path=PurePosixPath("manifest.yaml"))
    assert isinstance(data, dict)
    mutate(data)
    path.write_bytes(quoted_yaml(data))
    return data


def test_a_newer_bundle_is_refused_with_the_typed_code_and_exit_three(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """§21: "Bundle schema newer than the validator | Exit 3 with `unsupported_schema_version`".

    Asserted through `migrate`, because that is the one command an operator reaches for when they
    are told their build is too old, and it is the command that must not answer `already_current`.
    """
    _rewrite_manifest(
        promoted_tree.revision_dir,
        lambda data: data.update({"schema_version": NEWER_SCHEMA_VERSION}),
    )

    outcome = migrate_bundle(promoted_tree.bundle_root)

    assert (outcome.category, outcome.exit_code) == ("could_not_complete", 3)
    assert [d.code for d in outcome.diagnostics] == [IssueCode.UNSUPPORTED_SCHEMA_VERSION]
    assert outcome.value is None


def test_the_manifest_accepts_a_newer_version_so_the_schema_gate_is_what_refuses_it(
    promoted_tree: PromotedRevisionTree,
) -> None:
    """The manifest's `schema_version` is an unconstrained positive integer on purpose.

    Had it been declared as an enum or a `Literal[1]`, a v2 bundle would be reported as a
    `model_validation_error` on `manifest.yaml` — a message that reads as a corrupt file and sends
    the operator to fix bytes that are perfectly well-formed. The refusal above is an exact
    single-code list, so it already excludes that; what this test pins is the reason it can be:
    D-115, name where the guarantee lands. The model admits the version and the schema gate rejects
    it, which is what keeps the two failures distinguishable.
    """
    values = _rewrite_manifest(
        promoted_tree.revision_dir,
        lambda data: data.update({"schema_version": NEWER_SCHEMA_VERSION}),
    )

    accepted = RevisionManifest.model_validate(values)

    assert accepted.schema_version == NEWER_SCHEMA_VERSION
    assert NEWER_SCHEMA_VERSION not in SUPPORTED_SCHEMA_VERSIONS


def test_no_packaged_fixture_declares_a_schema_other_than_the_head() -> None:
    """§7: there is no invented v0 document shape, so there is no v0 fixture to find one in.

    A fabricated previous-version tree would be the only thing exercising a migration path that
    does not exist, and the first real bump would then have two "previous" schemas to reason about.
    """
    manifests = sorted(example_source_root().rglob("manifest.yaml"))
    assert manifests, "the packaged example must ship a manifest for this check to mean anything"
    for path in manifests:
        data = load_yaml_bytes(path.read_bytes(), logical_path=PurePosixPath("manifest.yaml"))
        assert isinstance(data, dict)
        assert data["schema_version"] == CURRENT_SCHEMA_VERSION
