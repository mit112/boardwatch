"""Bundle path resolution and confinement.

The bundle root is resolved at the command boundary (design §5) and is never a `Settings`
field, so nothing here may read config. Every derived path is confined under the resolved
root: a draft name arrives from an operator or an agent, and a name that escapes the root
would let `promote`'s temporary tree, or a rebase backup, be written anywhere on disk.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from boardwatch.profile_bundle.errors import BundlePathError
from boardwatch.profile_bundle.paths import (
    approval_path,
    approvals_dir,
    blob_path,
    blobs_dir,
    current_path,
    draft_root,
    drafts_dir,
    local_sources_path,
    lock_path,
    resolve_bundle_root,
    revision_root,
    revisions_dir,
)


def test_bundle_default_is_config_dir_child_and_override_wins(tmp_path: Path) -> None:
    assert resolve_bundle_root(tmp_path / "cfg", None) == tmp_path / "cfg" / "career-profile"
    assert resolve_bundle_root(tmp_path / "cfg", tmp_path / "private") == tmp_path / "private"


@pytest.mark.parametrize("name", ["../escape", "/absolute", "a/b", "", ".", ".."])
def test_draft_name_cannot_escape_bundle(name: str, tmp_path: Path) -> None:
    with pytest.raises(BundlePathError):
        draft_root(tmp_path, name)


@pytest.mark.parametrize(
    "name",
    [
        "baseline",
        "recovery-1",
        "schema-migration",
        "baseline.pre-rebase-root",
        "baseline.pre-rebase-sha256-" + "a" * 64,
    ],
)
def test_derived_and_ordinary_draft_names_are_accepted(name: str, tmp_path: Path) -> None:
    """The rebase backup name is itself a draft directory, so the grammar must admit it."""
    assert draft_root(tmp_path, name) == tmp_path / "drafts" / name


@pytest.mark.parametrize("name", ["Up Per", "tab\there", "dot.", "-lead", "sub/dir", "a" * 200])
def test_hostile_or_overlong_draft_names_are_rejected(name: str, tmp_path: Path) -> None:
    with pytest.raises(BundlePathError):
        draft_root(tmp_path, name)


def test_fixed_root_members_are_the_closed_set(tmp_path: Path) -> None:
    assert current_path(tmp_path) == tmp_path / "CURRENT"
    assert lock_path(tmp_path) == tmp_path / "career-profile.lock"
    assert local_sources_path(tmp_path) == tmp_path / "local-sources.yaml"
    assert approvals_dir(tmp_path) == tmp_path / "approvals"
    assert revisions_dir(tmp_path) == tmp_path / "revisions"
    assert drafts_dir(tmp_path) == tmp_path / "drafts"
    assert blobs_dir(tmp_path) == tmp_path / "blobs" / "sha256"


def test_revision_directory_is_named_by_the_full_digest(tmp_path: Path) -> None:
    digest = "sha256:" + "0" * 64
    assert revision_root(tmp_path, digest) == tmp_path / "revisions" / ("sha256-" + "0" * 64)


def test_approval_stamp_path_is_derived_from_the_candidate_digest(tmp_path: Path) -> None:
    digest = "sha256:" + "1" * 64
    assert approval_path(tmp_path, digest) == tmp_path / "approvals" / f"sha256-{'1' * 64}.yaml"


def test_blob_path_is_content_addressed_by_the_bare_digest(tmp_path: Path) -> None:
    assert blob_path(tmp_path, "2" * 64) == tmp_path / "blobs" / "sha256" / ("2" * 64)


@pytest.mark.parametrize(
    "digest",
    ["sha256:" + "A" * 64, "sha256:" + "0" * 63, "0" * 64, "sha1:" + "0" * 40, "sha256:"],
)
def test_malformed_digests_are_refused_before_a_path_is_built(digest: str, tmp_path: Path) -> None:
    with pytest.raises(BundlePathError):
        revision_root(tmp_path, digest)


@pytest.mark.parametrize("bare", ["A" * 64, "0" * 63, "sha256:" + "0" * 64, "z" * 64])
def test_malformed_bare_digests_are_refused(bare: str, tmp_path: Path) -> None:
    with pytest.raises(BundlePathError):
        blob_path(tmp_path, bare)
