"""The content-addressed blob store under `blobs/sha256/` (design §6, §12, §12.2).

Three properties are load-bearing and are why this is not two lines of `write_bytes`.

**The digest is verified before the bytes become visible.** Writing goes to an exclusive temporary
file in the same directory, is hashed, is compared against the caller's expected digest, and only
then is atomically renamed into place. A blob that appeared under its digest and did not match it
would make `evidence_set_digest` a statement about bytes nobody has.

**An existing blob is reused, never overwritten.** Two evidence records may capture the same bytes,
and the store is shared across every revision in the bundle. Overwriting would rewrite history; §6
forbids deleting or rewriting captured blobs at all.

**Corruption is quarantined logically, never moved or deleted.** §12.1 is explicit: a corrupt blob
leaves its bytes exactly where they are, and the active revision stays unusable until the exact
digest is restored from backup or the evidence is recaptured into a NEW blob. So nothing here
renames, truncates, or unlinks a blob that fails verification — the finding is the quarantine.
"""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from boardwatch.profile_bundle.errors import BundleIoError, ProfileBundleError
from boardwatch.profile_bundle.models.evidence import CaptureMediaType
from boardwatch.profile_bundle.paths import blob_path, blobs_dir, require_bare_digest

#: Per-capture hard limit, inline or blob (§12.2). A limit, not a recommendation.
MAX_CAPTURE_BYTES: Final = 1_048_576

#: Per-revision aggregate: inline UTF-8 byte lengths plus the raw sizes of UNIQUE referenced blobs.
#: Uniqueness is by full digest, so two records citing one blob count its bytes once
#: (§12.2, §22.18).
MAX_REVISION_EVIDENCE_BYTES: Final = 52_428_800


class BlobDigestMismatchError(ProfileBundleError):
    """Bytes did not hash to the digest they were filed or requested under.

    Carries both digests so a caller can report the finding without reading the bytes again.
    """

    def __init__(self, *, expected: str, actual: str, path: Path | None = None) -> None:
        where = f" at {path}" if path is not None else ""
        super().__init__(
            f"blob{where} hashes to {actual}, not the expected {expected}; "
            "the bytes are left exactly where they are"
        )
        self.expected = expected
        self.actual = actual


class BlobNotFoundError(ProfileBundleError):
    """No blob is stored under this digest."""

    def __init__(self, digest: str) -> None:
        super().__init__(f"no blob is stored under sha256:{digest}")
        self.digest = digest


def digest_bytes(raw: bytes) -> str:
    """The bare lowercase hex sha256 of `raw`. The one place blob digests are computed."""
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class BlobWriteResult:
    """What `write_blob` did, and where.

    `outcome` distinguishes a fresh write from reuse because the caller reports them differently:
    reuse is the normal case for a re-captured identical excerpt and is not a conflict.
    """

    digest: str
    path: Path
    outcome: Literal["written", "reused"]
    size: int

    @property
    def created(self) -> bool:
        return self.outcome == "written"


def _make_read_only(path: Path) -> None:
    """Drop write bits where the platform supports it.

    Best effort by design (§12.1: "accidental-write protection, not a bit-rot guarantee"), so a
    filesystem that refuses the chmod must not fail the write — the digest is the real integrity
    mechanism, and treating a permissions failure as a write failure would make the store unusable
    on filesystems that never supported the guarantee anyway.
    """
    try:
        mode = path.stat().st_mode
        path.chmod(stat.S_IMODE(mode) & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    except OSError:
        pass


def write_blob(
    bundle_root: Path,
    raw: bytes,
    *,
    expected_digest: str,
    media_type: CaptureMediaType,
) -> BlobWriteResult:
    """Store `raw` under its digest, verifying before and after the rename.

    `expected_digest` is required rather than derived: the caller already recorded a digest in the
    evidence record it is about to write, and passing it here is what makes a mismatch between the
    record and the bytes fail at capture time instead of at the next validation run.

    `media_type` is required but not re-checked against an allowlist: `CaptureMediaType` IS the v1
    allowlist (§12.2), so a value outside it cannot be constructed and a second check here would be
    a branch that can never run. It is still taken, because `add-evidence` must record the type it
    captured and a caller that has not decided the media type has not decided what it is storing.
    """
    del media_type  # see docstring: the enum is the allowlist
    digest = require_bare_digest(expected_digest)
    if len(raw) > MAX_CAPTURE_BYTES:
        raise ProfileBundleError(
            f"capture is {len(raw)} bytes, over the {MAX_CAPTURE_BYTES}-byte per-capture limit"
        )
    actual = digest_bytes(raw)
    if actual != digest:
        raise BlobDigestMismatchError(expected=digest, actual=actual)

    target = blob_path(bundle_root, digest)
    if target.exists():
        # Reuse, and verify what is already there rather than trusting the filename. A corrupt
        # existing blob must surface here, not silently satisfy a new capture of the same bytes.
        stored = _read_exact(target, digest)
        return BlobWriteResult(
            digest=digest, path=target, outcome="reused", size=len(stored)
        )

    directory = blobs_dir(bundle_root)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        # Exclusive temp file in the SAME directory, so the rename is atomic on one filesystem.
        handle, temporary = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".blob")
        temp_path = Path(temporary)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            # Re-hash what actually landed on disk, not the argument: a short write or a failing
            # device is exactly the case the pre-write hash cannot see.
            written = temp_path.read_bytes()
            if digest_bytes(written) != digest:
                raise BlobDigestMismatchError(
                    expected=digest, actual=digest_bytes(written), path=temp_path
                )
            os.replace(temp_path, target)
        except BaseException:
            temp_path.unlink(missing_ok=True)
            raise
    except OSError as exc:
        raise BundleIoError(f"could not write blob {digest}: {exc}") from exc

    _make_read_only(target)
    return BlobWriteResult(digest=digest, path=target, outcome="written", size=len(raw))


def _read_exact(path: Path, digest: str) -> bytes:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise BundleIoError(f"could not read blob {digest}: {exc}") from exc
    actual = digest_bytes(raw)
    if actual != digest:
        raise BlobDigestMismatchError(expected=digest, actual=actual, path=path)
    return raw


def read_blob(bundle_root: Path, digest: str) -> bytes:
    """The bytes stored under `digest`, verified.

    Verification is not optional and there is no unchecked variant: a reader that trusted the
    filename would let a corrupt blob flow into a digest computation, and the bundle's whole
    self-containment claim rests on those bytes being the ones the manifest names.
    """
    bare = require_bare_digest(digest)
    target = blob_path(bundle_root, bare)
    if not target.exists():
        raise BlobNotFoundError(bare)
    return _read_exact(target, bare)


def blob_size(bundle_root: Path, digest: str) -> int:
    """The stored size, without holding the bytes.

    Used for the aggregate budget, where reading 50 MiB of captures into memory to add up their
    lengths would be the wrong shape. The digest is NOT verified here — a size is not a claim about
    content, and `validate_evidence_structural` verifies integrity separately for every blob.
    """
    bare = require_bare_digest(digest)
    target = blob_path(bundle_root, bare)
    try:
        return target.stat().st_size
    except FileNotFoundError:
        raise BlobNotFoundError(bare) from None
    except OSError as exc:
        raise BundleIoError(f"could not stat blob {bare}: {exc}") from exc


def blob_exists(bundle_root: Path, digest: str) -> bool:
    return blob_path(bundle_root, require_bare_digest(digest)).exists()


def stored_digests(bundle_root: Path) -> tuple[str, ...]:
    """Every blob in the store, sorted. Used by `inventory` to report unreferenced blobs.

    Reported, never collected: §6 forbids automatic blob garbage collection, so this exists to make
    an orphan visible to the owner rather than to find something to delete.
    """
    directory = blobs_dir(bundle_root)
    if not directory.is_dir():
        return ()
    found: list[str] = []
    for entry in directory.iterdir():
        if not entry.is_file() or entry.name.startswith(".tmp-"):
            continue
        try:
            found.append(require_bare_digest(entry.name))
        except ProfileBundleError:
            # A file under `blobs/sha256/` whose name is not a digest is not a blob. It is reported
            # as an orphaned artefact by `inventory`, which owns that finding.
            continue
    return tuple(sorted(found))
