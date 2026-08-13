"""The projection stamp is bound to a digest, and editing the declaration reopens the gate.

Deliberately not `profile_bundle.ApprovalStamp` — see `stamp.py`'s module docstring for why reuse
was ruled out. These tests pin the one property that makes that separation matter: a stamp keyed
by digest must not be found, or found valid, for any digest other than the one it was written for.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from boardwatch.projection.stamp import ProjectionStamp, stamp_exists, stamp_path, write_stamp

D1 = "sha256:" + "a" * 64
D2 = "sha256:" + "b" * 64
NOW = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)


def test_no_stamp_exists_before_one_is_written(tmp_path: Path) -> None:
    assert stamp_exists(tmp_path, D1) is False


def test_a_written_stamp_is_found_for_its_own_digest_only(tmp_path: Path) -> None:
    """Keyed by digest, so the lookup itself is the binding: an edited declaration has a
    different digest and simply has no stamp. This is the property that makes reusing the
    bundle's `ApprovalStamp` (keyed by a *candidate* digest, a different fact) unsafe — a stamp
    for one digest must never read as present for another.
    """
    path = write_stamp(tmp_path, digest=D1, approved_at=NOW)
    assert path == stamp_path(tmp_path, D1)
    assert stamp_exists(tmp_path, D1) is True
    assert stamp_exists(tmp_path, D2) is False


def test_the_written_stamp_content_matches_the_requested_digest(tmp_path: Path) -> None:
    """Not just the filename: the stored bytes, read back through the SAME restricted loader the
    bundle uses, must carry the digest that was actually requested — not a hardcoded or
    default-object stand-in. This is what would fail if the stamp were computed over the wrong
    bytes, or recorded a digest other than the one it was asked to bind.
    """
    path = write_stamp(tmp_path, digest=D1, approved_at=NOW)
    logical = PurePosixPath(f"projection-approvals/{path.name}")
    reloaded = load_yaml_bytes(path.read_bytes(), logical_path=logical)
    stamp = ProjectionStamp.model_validate(reloaded)
    assert stamp.projection_digest == D1
    assert stamp.approved_at == NOW
    assert stamp.approved_via == "controlling_terminal"


def test_two_writes_of_one_digest_do_not_produce_two_files(tmp_path: Path) -> None:
    write_stamp(tmp_path, digest=D1, approved_at=NOW)
    write_stamp(tmp_path, digest=D1, approved_at=NOW)
    assert len(list((tmp_path / "projection-approvals").iterdir())) == 1


def test_two_different_digests_produce_two_files_with_different_stamp_ids(tmp_path: Path) -> None:
    """The collision-free-id property: two distinct declarations approved in the same config
    directory must not alias to one stamp, and must not derive the same stamp id."""
    path1 = write_stamp(tmp_path, digest=D1, approved_at=NOW)
    path2 = write_stamp(tmp_path, digest=D2, approved_at=NOW)
    assert path1 != path2
    assert len(list((tmp_path / "projection-approvals").iterdir())) == 2

    stamp1 = ProjectionStamp.model_validate(
        load_yaml_bytes(path1.read_bytes(), logical_path=PurePosixPath(path1.name))
    )
    stamp2 = ProjectionStamp.model_validate(
        load_yaml_bytes(path2.read_bytes(), logical_path=PurePosixPath(path2.name))
    )
    assert stamp1.projection_stamp_id != stamp2.projection_stamp_id
