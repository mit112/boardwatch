"""The projection stamp is bound to a digest, and editing the declaration reopens the gate.

Deliberately not `profile_bundle.ApprovalStamp` — see `stamp.py`'s module docstring for why reuse
was ruled out. These tests pin the one property that makes that separation matter: a stamp keyed
by digest must not be found, or found valid, for any digest other than the one it was written for.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import pytest

from boardwatch.profile_bundle.errors import BundlePathError
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from boardwatch.projection.stamp import (
    ProjectionStamp,
    read_stamp,
    stamp_exists,
    stamp_path,
    write_stamp,
)

D1 = "sha256:" + "a" * 64
D2 = "sha256:" + "b" * 64
BD1 = "sha256:" + "c" * 64
NOW = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)

#: Malformed digests the fix must reject: missing the `sha256:` prefix, hex too short, hex too
#: long, and a path separator or `..` where hex is expected. `require_digest` (reached through
#: `digest_token`) rejects all four by the same `^sha256:[0-9a-f]{64}$` regex — none of them match.
MALFORMED_DIGESTS = [
    pytest.param("a" * 64, id="missing_sha256_prefix"),
    pytest.param("sha256:" + "a" * 63, id="hex_one_short"),
    pytest.param("sha256:" + "a" * 65, id="hex_one_long"),
    pytest.param("sha256:" + "a" * 60 + "/../", id="path_separator_and_dot_dot"),
]


def test_no_stamp_exists_before_one_is_written(tmp_path: Path) -> None:
    assert stamp_exists(tmp_path, D1) is False


def test_a_written_stamp_is_found_for_its_own_digest_only(tmp_path: Path) -> None:
    """Keyed by digest, so the lookup itself is the binding: an edited declaration has a
    different digest and simply has no stamp. This is the property that makes reusing the
    bundle's `ApprovalStamp` (keyed by a *candidate* digest, a different fact) unsafe — a stamp
    for one digest must never read as present for another.
    """
    path = write_stamp(tmp_path, digest=D1, bundle_digest=BD1, approved_at=NOW)
    assert path == stamp_path(tmp_path, D1)
    assert stamp_exists(tmp_path, D1) is True
    assert stamp_exists(tmp_path, D2) is False


def test_the_written_stamp_content_matches_the_requested_digest(tmp_path: Path) -> None:
    """Not just the filename: the stored bytes, read back through the SAME restricted loader the
    bundle uses, must carry the digest that was actually requested — not a hardcoded or
    default-object stand-in. This is what would fail if the stamp were computed over the wrong
    bytes, or recorded a digest other than the one it was asked to bind.
    """
    path = write_stamp(tmp_path, digest=D1, bundle_digest=BD1, approved_at=NOW)
    logical = PurePosixPath(f"projection-approvals/{path.name}")
    reloaded = load_yaml_bytes(path.read_bytes(), logical_path=logical)
    stamp = ProjectionStamp.model_validate(reloaded)
    assert stamp.projection_digest == D1
    assert stamp.bundle_digest == BD1
    assert stamp.approved_at == NOW
    assert stamp.approved_via == "controlling_terminal"


def test_read_stamp_returns_the_bundle_digest_it_was_written_with(tmp_path: Path) -> None:
    """`read_stamp` is the read side `project --check` uses; it must not merely find the file, it
    must recover the exact `bundle_digest` `write_stamp` bound — not the projection digest, and
    not a default."""
    write_stamp(tmp_path, digest=D1, bundle_digest=BD1, approved_at=NOW)
    stamp = read_stamp(tmp_path, D1)
    assert stamp.projection_digest == D1
    assert stamp.bundle_digest == BD1
    assert stamp.bundle_digest != stamp.projection_digest


def test_two_writes_of_one_digest_do_not_produce_two_files(tmp_path: Path) -> None:
    write_stamp(tmp_path, digest=D1, bundle_digest=BD1, approved_at=NOW)
    write_stamp(tmp_path, digest=D1, bundle_digest=BD1, approved_at=NOW)
    assert len(list((tmp_path / "projection-approvals").iterdir())) == 1


def test_two_different_digests_produce_two_files_with_different_stamp_ids(tmp_path: Path) -> None:
    """The collision-free-id property: two distinct declarations approved in the same config
    directory must not alias to one stamp, and must not derive the same stamp id."""
    path1 = write_stamp(tmp_path, digest=D1, bundle_digest=BD1, approved_at=NOW)
    path2 = write_stamp(tmp_path, digest=D2, bundle_digest=BD1, approved_at=NOW)
    assert path1 != path2
    assert len(list((tmp_path / "projection-approvals").iterdir())) == 2

    stamp1 = ProjectionStamp.model_validate(
        load_yaml_bytes(path1.read_bytes(), logical_path=PurePosixPath(path1.name))
    )
    stamp2 = ProjectionStamp.model_validate(
        load_yaml_bytes(path2.read_bytes(), logical_path=PurePosixPath(path2.name))
    )
    assert stamp1.projection_stamp_id != stamp2.projection_stamp_id


@pytest.mark.parametrize("malformed", MALFORMED_DIGESTS)
def test_stamp_path_rejects_a_malformed_digest(tmp_path: Path, malformed: str) -> None:
    """A digest that does not match `^sha256:[0-9a-f]{64}$` must not become a path — it must be
    refused with the same typed error `profile_bundle` raises for its own malformed digests, not
    silently accepted."""
    with pytest.raises(BundlePathError):
        stamp_path(tmp_path, malformed)


@pytest.mark.parametrize("malformed", MALFORMED_DIGESTS)
def test_write_stamp_rejects_a_malformed_digest(tmp_path: Path, malformed: str) -> None:
    with pytest.raises(BundlePathError):
        write_stamp(tmp_path, digest=malformed, bundle_digest=BD1, approved_at=NOW)


def test_write_stamp_leaves_no_file_behind_for_a_malformed_digest(tmp_path: Path) -> None:
    """The rejection happens before any I/O: a malformed digest must not leave a partially
    written stamp, or even an empty `projection-approvals/` directory, behind."""
    with pytest.raises(BundlePathError):
        write_stamp(tmp_path, digest="not-a-digest", bundle_digest=BD1, approved_at=NOW)
    assert not (tmp_path / "projection-approvals").exists()


def test_stamp_exists_rejects_a_malformed_digest(tmp_path: Path) -> None:
    """`stamp_exists` delegates to `stamp_path`, so it inherits the same rejection rather than
    answering `False` for a digest that was never a valid digest to begin with."""
    with pytest.raises(BundlePathError):
        stamp_exists(tmp_path, "not-a-digest")
