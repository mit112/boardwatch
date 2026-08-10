"""The content-addressed blob store: exclusive writes, verified reads, quarantine without deletion.

The tests that matter most here are the ones about what the store *refuses* to do. A blob store that
overwrote, or that trusted a filename, or that "repaired" a corrupt blob by moving it aside would pass
a naive suite and quietly break the bundle's identity guarantee — so each of those is asserted
explicitly, including that the corrupt bytes are still byte-for-byte on disk afterwards.
"""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

import pytest

from boardwatch.profile_bundle.blobs import (
    MAX_CAPTURE_BYTES,
    BlobDigestMismatchError,
    BlobNotFoundError,
    blob_exists,
    blob_size,
    digest_bytes,
    read_blob,
    stored_digests,
    write_blob,
)
from boardwatch.profile_bundle.errors import BundleIoError, ProfileBundleError
from boardwatch.profile_bundle.models.evidence import CaptureMediaType
from boardwatch.profile_bundle.paths import blob_path, blobs_dir

TEXT = b"# A capture\n\nSustained approximately 120 items/s over five minutes.\n"
DIGEST = hashlib.sha256(TEXT).hexdigest()
PLAIN = CaptureMediaType.TEXT_PLAIN


@pytest.fixture
def bundle_root(tmp_path: Path) -> Path:
    root = tmp_path / "career-profile"
    root.mkdir()
    return root


def store(root: Path, raw: bytes = TEXT) -> str:
    result = write_blob(root, raw, expected_digest=digest_bytes(raw), media_type=PLAIN)
    return result.digest


# --------------------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------------------


def test_a_written_blob_lands_under_its_digest_and_reads_back_identical(
    bundle_root: Path,
) -> None:
    result = write_blob(bundle_root, TEXT, expected_digest=DIGEST, media_type=PLAIN)
    assert result.outcome == "written"
    assert result.created
    assert result.digest == DIGEST
    assert result.size == len(TEXT)
    assert result.path == blob_path(bundle_root, DIGEST)
    assert read_blob(bundle_root, DIGEST) == TEXT


def test_writing_creates_the_blob_directory_when_it_is_absent(bundle_root: Path) -> None:
    """`init` need not have run: `add-evidence` may be the first thing to touch the store."""
    assert not blobs_dir(bundle_root).exists()
    store(bundle_root)
    assert blobs_dir(bundle_root).is_dir()


def test_a_digest_that_does_not_match_the_bytes_is_refused_and_nothing_is_written(
    bundle_root: Path,
) -> None:
    """The caller passes the digest it already recorded in the evidence record, so a mismatch means
    the record and the bytes disagree — caught at capture time, not at the next validation run."""
    wrong = "0" * 64
    with pytest.raises(BlobDigestMismatchError) as raised:
        write_blob(bundle_root, TEXT, expected_digest=wrong, media_type=PLAIN)
    assert raised.value.expected == wrong
    assert raised.value.actual == DIGEST
    assert not blob_path(bundle_root, wrong).exists()
    assert not blob_path(bundle_root, DIGEST).exists()


def test_a_capture_over_the_per_capture_limit_is_refused(bundle_root: Path) -> None:
    """§12.2's 1 MiB is a hard limit, not a recommendation, and it is enforced before the write so
    an oversized capture never reaches the disk at all."""
    oversized = b"x" * (MAX_CAPTURE_BYTES + 1)
    with pytest.raises(ProfileBundleError, match="per-capture limit"):
        write_blob(
            bundle_root,
            oversized,
            expected_digest=digest_bytes(oversized),
            media_type=PLAIN,
        )
    assert stored_digests(bundle_root) == ()


def test_a_capture_exactly_at_the_limit_is_accepted(bundle_root: Path) -> None:
    """The boundary, asserted in both directions so the comparison cannot be off by one."""
    exact = b"y" * MAX_CAPTURE_BYTES
    result = write_blob(
        bundle_root, exact, expected_digest=digest_bytes(exact), media_type=PLAIN
    )
    assert result.size == MAX_CAPTURE_BYTES


def test_no_temporary_files_survive_a_successful_write(bundle_root: Path) -> None:
    store(bundle_root)
    leftovers = [p.name for p in blobs_dir(bundle_root).iterdir() if p.name.startswith(".tmp-")]
    assert leftovers == []


def test_no_temporary_files_survive_a_refused_write(bundle_root: Path) -> None:
    """A failed write must not leave a partial blob behind for the next run to trip over."""
    blobs_dir(bundle_root).mkdir(parents=True)
    with pytest.raises(BlobDigestMismatchError):
        write_blob(bundle_root, TEXT, expected_digest="1" * 64, media_type=PLAIN)
    assert list(blobs_dir(bundle_root).iterdir()) == []


def test_the_written_blob_is_read_only_where_the_platform_allows_it(
    bundle_root: Path,
) -> None:
    """Accidental-write protection, not a bit-rot guarantee (§12.1) — so this asserts the intent and
    tolerates a filesystem that does not carry write bits."""
    path = blob_path(bundle_root, store(bundle_root))
    mode = stat.S_IMODE(path.stat().st_mode)
    if os.name == "posix":
        assert not mode & stat.S_IWUSR
    assert path.read_bytes() == TEXT


# --------------------------------------------------------------------------------------
# Reuse, never overwrite
# --------------------------------------------------------------------------------------


def test_storing_identical_bytes_twice_reuses_the_existing_blob(bundle_root: Path) -> None:
    """Two evidence records may capture the same excerpt. The second write is reuse, not a conflict,
    and not a second copy."""
    first = write_blob(bundle_root, TEXT, expected_digest=DIGEST, media_type=PLAIN)
    second = write_blob(bundle_root, TEXT, expected_digest=DIGEST, media_type=PLAIN)
    assert first.outcome == "written"
    assert second.outcome == "reused"
    assert not second.created
    assert second.path == first.path
    assert second.size == len(TEXT)
    assert stored_digests(bundle_root) == (DIGEST,)


def test_reuse_verifies_the_existing_bytes_rather_than_trusting_the_filename(
    bundle_root: Path,
) -> None:
    """A corrupt existing blob must surface on reuse. Otherwise a fresh capture of the same content
    would report success while the store still held the wrong bytes."""
    path = blob_path(bundle_root, store(bundle_root))
    path.chmod(0o600)
    path.write_bytes(b"corrupted")
    with pytest.raises(BlobDigestMismatchError):
        write_blob(bundle_root, TEXT, expected_digest=DIGEST, media_type=PLAIN)


def test_an_existing_blob_is_never_overwritten(bundle_root: Path) -> None:
    """§6 forbids rewriting captured blobs. Recorded by mtime and inode, because equal content would
    make a byte comparison pass even if the file had been rewritten."""
    path = blob_path(bundle_root, store(bundle_root))
    before = path.stat()
    write_blob(bundle_root, TEXT, expected_digest=DIGEST, media_type=PLAIN)
    after = path.stat()
    assert (after.st_ino, after.st_mtime_ns) == (before.st_ino, before.st_mtime_ns)


# --------------------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------------------


def test_reading_an_absent_blob_raises_a_typed_not_found(bundle_root: Path) -> None:
    with pytest.raises(BlobNotFoundError) as raised:
        read_blob(bundle_root, DIGEST)
    assert raised.value.digest == DIGEST


def test_reading_a_corrupt_blob_raises_and_leaves_the_bytes_exactly_where_they_are(
    bundle_root: Path,
) -> None:
    """The quarantine property, stated as a test.

    §12.1: a corrupted blob is "logically quarantined by validation without moving or deleting its
    bytes". So the read fails, and afterwards the corrupt file is still at the same path with the
    same content — an owner restoring the exact digest from backup must not find that the store has
    already tidied it away.
    """
    path = blob_path(bundle_root, store(bundle_root))
    path.chmod(0o600)
    corrupt = b"not the original bytes"
    path.write_bytes(corrupt)

    with pytest.raises(BlobDigestMismatchError) as raised:
        read_blob(bundle_root, DIGEST)
    assert raised.value.expected == DIGEST
    assert raised.value.actual == digest_bytes(corrupt)

    assert path.exists()
    assert path.read_bytes() == corrupt
    assert stored_digests(bundle_root) == (DIGEST,)
    siblings = sorted(p.name for p in blobs_dir(bundle_root).iterdir())
    assert siblings == [DIGEST], "nothing was moved aside, renamed, or quarantined on disk"


def test_the_mismatch_message_never_contains_the_stored_bytes(bundle_root: Path) -> None:
    """A capture's bytes may be exactly the material the bundle exists to protect, so an integrity
    error reports digests and a path — never content."""
    path = blob_path(bundle_root, store(bundle_root))
    path.chmod(0o600)
    secret = b"api_key = AKIAIOSFODNN7EXAMPLE"
    path.write_bytes(secret)
    with pytest.raises(BlobDigestMismatchError) as raised:
        read_blob(bundle_root, DIGEST)
    assert "AKIA" not in str(raised.value)
    assert secret.decode() not in str(raised.value)


def test_blob_size_reports_bytes_without_verifying_them(bundle_root: Path) -> None:
    """The aggregate budget needs sizes for up to 50 MiB of captures; reading them all to add up
    lengths would be the wrong shape. Integrity is checked separately, per blob."""
    path = blob_path(bundle_root, store(bundle_root))
    assert blob_size(bundle_root, DIGEST) == len(TEXT)
    path.chmod(0o600)
    path.write_bytes(b"short")
    assert blob_size(bundle_root, DIGEST) == len(b"short")


def test_blob_size_of_an_absent_blob_raises_not_found(bundle_root: Path) -> None:
    with pytest.raises(BlobNotFoundError):
        blob_size(bundle_root, DIGEST)


def test_blob_exists_does_not_read_or_verify(bundle_root: Path) -> None:
    assert not blob_exists(bundle_root, DIGEST)
    store(bundle_root)
    assert blob_exists(bundle_root, DIGEST)


# --------------------------------------------------------------------------------------
# Digest hygiene and enumeration
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "malformed",
    [
        "sha256:" + "a" * 64,  # prefixed form; the store takes bare digests
        "A" * 64,  # uppercase
        "a" * 63,
        "a" * 65,
        "z" * 64,
        "",
        "../escape",
    ],
)
def test_a_malformed_digest_is_refused_by_every_entry_point(
    bundle_root: Path, malformed: str
) -> None:
    """Including the traversal case: a digest is the only thing that names a blob, so a path
    separator reaching `blob_path` would let a caller address bytes outside the store."""
    for call in (
        lambda: read_blob(bundle_root, malformed),
        lambda: blob_size(bundle_root, malformed),
        lambda: blob_exists(bundle_root, malformed),
        lambda: write_blob(bundle_root, TEXT, expected_digest=malformed, media_type=PLAIN),
    ):
        with pytest.raises(ProfileBundleError):
            call()


def test_stored_digests_lists_every_blob_sorted(bundle_root: Path) -> None:
    digests = {store(bundle_root, raw) for raw in (b"one", b"two", b"three")}
    assert stored_digests(bundle_root) == tuple(sorted(digests))


def test_stored_digests_is_empty_when_the_store_does_not_exist(bundle_root: Path) -> None:
    assert stored_digests(bundle_root) == ()


def test_stored_digests_skips_non_digest_filenames_rather_than_failing(
    bundle_root: Path,
) -> None:
    """A stray file under `blobs/sha256/` is not a blob. It is reported as an orphaned artefact by
    `inventory`, which owns that finding — enumeration must not crash on it, and must not adopt it."""
    digest = store(bundle_root)
    (blobs_dir(bundle_root) / "README").write_text("not a blob", encoding="utf-8")
    (blobs_dir(bundle_root) / ".tmp-leftover.blob").write_bytes(b"partial")
    assert stored_digests(bundle_root) == (digest,)


def test_stored_digests_never_deletes_anything_it_skips(bundle_root: Path) -> None:
    """§6 forbids automatic blob garbage collection, so enumeration is read-only by contract."""
    store(bundle_root)
    stray = blobs_dir(bundle_root) / "README"
    stray.write_text("not a blob", encoding="utf-8")
    stored_digests(bundle_root)
    assert stray.exists()


def test_digest_bytes_is_plain_sha256_hex(bundle_root: Path) -> None:
    """Pinned against `hashlib` directly: the blob digest is a raw-byte sha256 with no canonical-JSON
    or Unicode normalisation step, unlike the bundle's document digests."""
    assert digest_bytes(TEXT) == hashlib.sha256(TEXT).hexdigest()
    assert digest_bytes(b"") == hashlib.sha256(b"").hexdigest()


def test_an_unreadable_blob_directory_raises_a_typed_io_error(bundle_root: Path) -> None:
    """Exit 3 territory: the check could not run. Distinct from a missing or corrupt blob, which are
    findings about the bundle rather than about the environment."""
    if os.name != "posix" or os.geteuid() == 0:
        pytest.skip("permission bits do not restrict this user")
    directory = blobs_dir(bundle_root)
    directory.mkdir(parents=True)
    path = blob_path(bundle_root, DIGEST)
    path.write_bytes(TEXT)
    path.chmod(0o000)
    try:
        with pytest.raises(BundleIoError):
            read_blob(bundle_root, DIGEST)
    finally:
        path.chmod(0o600)
